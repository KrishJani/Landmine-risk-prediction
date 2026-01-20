#!/usr/bin/env python3
"""
EC2 Worker Main Script
Runs on EC2 instance to process training jobs from the database.
This replaces the Redis-based worker for cost optimization.
"""

import os
import sys
import time
import subprocess
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project directories to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
reland_backend = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if reland_backend not in sys.path:
    sys.path.insert(0, reland_backend)

from models import TrainingJob, Location, ConfirmedEvent, db
from sqlalchemy import text
from flask import Flask

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

# Create Flask app for database operations
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def update_job_status(job_id, status, progress=None, message=None, error=None):
    """Update job status in database"""
    with app.app_context():
        try:
            job = TrainingJob.query.filter_by(id=job_id).first()
            if not job:
                print(f"ERROR: Job {job_id} not found")
                return False
            
            job.status = status
            if progress is not None:
                job.progress = progress
            if message:
                job.progress_message = message
            if error:
                job.error_message = error
            
            if status == 'running' and not job.started_at:
                job.started_at = datetime.utcnow()
            elif status in ['completed', 'failed']:
                job.completed_at = datetime.utcnow()
            
            db.session.commit()
            return True
        except Exception as e:
            print(f"ERROR updating job status: {str(e)}")
            db.session.rollback()
            return False

def process_training_job(job):
    """Process a training job"""
    job_id = job.id
    
    with app.app_context():
        try:
            # Update status to running
            update_job_status(job_id, 'running', progress=0.1, message="Starting training...")
            
            # Recalculate distances if needed
            update_job_status(job_id, 'running', progress=0.2, message="Recalculating distances...")
            confirmed_events = ConfirmedEvent.query.all()
        
            if len(confirmed_events) > 0:
                all_locations = Location.query.all()
                if all_locations:
                    # Check if dist_old_mine column exists
                    from sqlalchemy import inspect
                    inspector = inspect(db.engine)
                    columns = [col['name'] for col in inspector.get_columns('locations')]
                    column_exists = 'dist_old_mine' in columns
                    
                    if not column_exists:
                        db.session.execute(text("ALTER TABLE locations ADD COLUMN dist_old_mine FLOAT"))
                        db.session.commit()
                        column_exists = True
                    
                    # Calculate distances
                    import pandas as pd
                    # utils.py is in project root
                    from utils import distance_to_closest_point
                    
                    grid_data = {
                        'lat': [loc.lat for loc in all_locations],
                        'lon': [loc.lon for loc in all_locations]
                    }
                    grid_df = pd.DataFrame(grid_data)
                    
                    poi_data = {
                        'lat': [event.lat for event in confirmed_events],
                        'lon': [event.lon for event in confirmed_events]
                    }
                    poi_df = pd.DataFrame(poi_data)
                    
                    distances = distance_to_closest_point(grid_df, poi_df)
                    
                    # Update locations
                    update_query = text("""
                        UPDATE locations 
                        SET dist_old_mine = :distance 
                        WHERE id = :location_id
                    """)
                    
                    for i, location in enumerate(all_locations):
                        db.session.execute(
                            update_query,
                            {'distance': float(distances[i]), 'location_id': location.id}
                        )
                    db.session.commit()
            
            # Run training script
            update_job_status(job_id, 'running', progress=0.3, message="Running training script...")
            
            # Get project root directory
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            main_script = os.path.join(script_dir, 'main.py')
            
            if not os.path.exists(main_script):
                raise FileNotFoundError(f"main.py not found at {main_script}")
            
            # Generate timestamp
            timestamp = datetime.now().strftime("%m%d%Y%H%M%S")
            
            # Build command
            cmd = [
                sys.executable, main_script,
                '--timestamp', timestamp,
                '--municipio', job.municipio or 'blockCV',
                '--subset', job.subset or 'full',
                '--model', job.model_name or 'TabCmpt',
                '--objective', job.objective or 'irm',
                '--n_step', str(job.n_step or 2)
            ]
            
            # Set environment
            env = os.environ.copy()
            env['DATABASE_URL'] = DATABASE_URL
            
            update_job_status(job_id, 'running', progress=0.4, message="Training in progress...")
            
            # Run training (this may take hours)
            result = subprocess.run(
                cmd,
                cwd=script_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hour timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                update_job_status(
                    job_id, 
                    'failed', 
                    progress=1.0,
                    error=f"Training failed: {error_msg[:1000]}"
                )
                return False
            
            # Save results
            update_job_status(job_id, 'running', progress=0.9, message="Saving results...")
            
            # Try to save predictions to database
            try:
                predicted_proba_path = os.path.join(script_dir, f'experiments/{timestamp}/predicted_proba.csv')
                if os.path.exists(predicted_proba_path):
                    import pandas as pd
                    # save_predictions_db.py is in project root
                    from save_predictions_db import save_predictions_to_db_orm
                    predictions_df = pd.read_csv(predicted_proba_path)
                    save_predictions_to_db_orm(predictions_df, db.session, Location)
            except Exception as e:
                print(f"Warning: Could not save predictions: {str(e)}")
            
            # Update job with results
            result_data = {
                "timestamp": timestamp,
                "experiment_dir": f"./experiments/{timestamp}/",
                "return_code": result.returncode
            }
            
            # Get job again to update result
            job = TrainingJob.query.filter_by(id=job_id).first()
            if job:
                job.result = json.dumps(result_data)
                db.session.commit()
            
            update_job_status(
                job_id, 
                'completed', 
                progress=1.0,
                message="Training completed successfully"
            )
            
            return True
        
    except subprocess.TimeoutExpired:
        update_job_status(
            job_id, 
            'failed', 
            progress=1.0,
            error="Training timed out after 2 hours"
        )
        return False
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        update_job_status(
            job_id, 
            'failed', 
            progress=1.0,
            error=error_msg[:2000]
        )
        return False

def main():
    """Main worker loop"""
    print("RELand EC2 Worker starting...")
    print(f"Database: {DATABASE_URL[:50]}...")
    
    # Get instance ID for tracking
    try:
        import requests
        instance_id = requests.get('http://169.254.169.254/latest/meta-data/instance-id', timeout=2).text
        print(f"Instance ID: {instance_id}")
    except:
        instance_id = None
    
    # Find pending jobs
    while True:
        try:
            with app.app_context():
                # Get oldest pending job
                job = TrainingJob.query.filter(
                    TrainingJob.status == 'pending'
                ).order_by(TrainingJob.created_at.asc()).first()
                
                if job:
                    print(f"Processing job: {job.id}")
                    if instance_id:
                        job.ec2_instance_id = instance_id
                        db.session.commit()
                    
                    success = process_training_job(job)
                    
                    if success:
                        print(f"Job {job.id} completed successfully")
                    else:
                        print(f"Job {job.id} failed")
                    
                    # Check if there are more jobs
                    remaining = TrainingJob.query.filter(
                        TrainingJob.status == 'pending'
                    ).count()
                    
                    if remaining == 0:
                        print("No more pending jobs. Waiting 5 minutes before terminating...")
                        # Wait 5 minutes in case more jobs arrive
                        time.sleep(300)
                        # Check one more time
                        with app.app_context():
                            remaining = TrainingJob.query.filter(
                                TrainingJob.status == 'pending'
                            ).count()
                        if remaining == 0:
                            print("No jobs for 5 minutes. Terminating instance...")
                            # Self-terminate
                            if instance_id:
                                try:
                                    import boto3
                                    ec2 = boto3.client('ec2', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                                    ec2.terminate_instances(InstanceIds=[instance_id])
                                    print(f"Termination request sent for instance {instance_id}")
                                except Exception as e:
                                    print(f"Error terminating instance: {str(e)}")
                            break
                else:
                    print("No pending jobs. Waiting 30 seconds...")
                    time.sleep(30)
                    
        except KeyboardInterrupt:
            print("Worker interrupted. Exiting...")
            break
        except Exception as e:
            import traceback
            print(f"ERROR in worker loop: {str(e)}")
            print(traceback.format_exc())
            time.sleep(60)  # Wait before retrying
    
    print("RELand EC2 Worker stopped")

if __name__ == '__main__':
    main()

