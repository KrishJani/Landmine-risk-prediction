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
import argparse
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project directories to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
reland_backend = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if reland_backend not in sys.path:
    sys.path.insert(0, reland_backend)

# Load .env so LOCAL_DATABASE_URL (and DATABASE_URL) are set when run manually
try:
    from dotenv import load_dotenv
    # Backend .env (primary); then project root .env if present
    load_dotenv(os.path.join(reland_backend, '.env'))
    load_dotenv(os.path.join(project_root, '.env'))
except ImportError:
    pass

from models import TrainingJob, Location, ConfirmedEvent, db
from sqlalchemy import text
from flask import Flask

# Database connection
# Match backend behavior:
# - Production: DATABASE_URL (RDS) is required
# - Local: LOCAL_DATABASE_URL is required (no fallback to production DB)
env_name = os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'local')).lower()
if env_name in ['production', 'prod']:
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable is required in production.")
        sys.exit(1)
else:
    # Local mode: ONLY use LOCAL_DATABASE_URL (never touch production DB)
    DATABASE_URL = os.getenv('LOCAL_DATABASE_URL')
    if not DATABASE_URL:
        print("ERROR: LOCAL_DATABASE_URL environment variable is required for local development.")
        print("Set it in your .env file to avoid accidentally connecting to production database.")
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
            elif status == 'completed':
                job.error_message = None  # Clear previous error on success
            
            if status == 'running' and not job.started_at:
                job.started_at = datetime.now(timezone.utc)
            elif status in ['completed', 'failed']:
                job.completed_at = datetime.now(timezone.utc)
            
            db.session.commit()
            return True
        except Exception as e:
            print(f"ERROR updating job status: {str(e)}")
            db.session.rollback()
            return False


def _run_predict_per_db_location_after_train(job_id, timestamp, script_dir):
    """
    After training, run the same predict-per-DB-location flow as recalculate_and_predict
    so every map point (including Cartagena) gets one prediction from the newly trained model.
    Uses scaled features from nearest CSV row (no raw lon/lat overwrite).
    """
    import numpy as np
    from pathlib import Path
    from sklearn.neighbors import NearestNeighbors

    with app.app_context():
        job = TrainingJob.query.filter_by(id=job_id).first()
        if not job:
            return
        all_locations = Location.query.all()
        if not all_locations:
            print("No locations in DB, skipping predict-per-DB-location")
            return

        val_municipio = 'ALL' if (job.municipio or 'blockCV') == 'blockCV' else (job.municipio or 'blockCV').upper()
        subset = job.subset or 'full'
        model_name = job.model_name or 'TabCmpt'
        objective = job.objective or 'irm'

        sys.path.insert(0, str(script_dir))
        sys.path.insert(0, reland_backend)
        from dataset_db import EventDB
        from save_predictions_db import save_predictions_to_db_by_locations
        from utils.train_municipios_loader import load_train_municipios_for_repredict

        # Use same train_municipios as model training for correct scaler (Fix 2: align scaler with model)
        train_municipios = load_train_municipios_for_repredict(timestamp, job.municipio or 'blockCV')

        all_data = EventDB(
            train_municipios=train_municipios,
            val_municipio=val_municipio,
            subset=subset,
            split='val',
            db_url=DATABASE_URL
        )
        db_lon_lat = np.array([[loc.lon, loc.lat] for loc in all_locations], dtype=np.float64)
        csv_lon_lat = np.column_stack([all_data.locations[:, 0], all_data.locations[:, 1]])
        nn = NearestNeighbors(n_neighbors=1, metric='euclidean')
        nn.fit(csv_lon_lat)
        _, nearest_idx = nn.kneighbors(db_lon_lat)
        nearest_idx = nearest_idx.flatten()
        tabX_db = np.array(all_data.tabX[nearest_idx], dtype=np.float32)
        n_db = len(all_locations)

        class DBLocationDataset:
            def __init__(self, tabX, locations_xy):
                self.tabX = tabX
                self.locations = locations_xy
                self.y = np.zeros(len(tabX), dtype=np.float32)
                self.hist_mine = np.zeros(len(tabX), dtype=np.float32)
            def __len__(self):
                return len(self.tabX)
            def __getitem__(self, idx):
                import torch
                return (
                    torch.tensor(self.tabX[idx], dtype=torch.float32),
                    torch.tensor(self.y[idx], dtype=torch.float32),
                    torch.tensor((self.locations[idx, 0], self.locations[idx, 1]), dtype=torch.float32),
                    torch.tensor(self.hist_mine[idx], dtype=torch.float32),
                )
        db_dataset = DBLocationDataset(tabX_db, db_lon_lat)

        exp_dir = Path(script_dir) / 'experiments' / timestamp
        if model_name in ['TabCmpt', 'MLP']:
            fold_paths = list(exp_dir.glob('*.pth'))
        else:
            fold_paths = list(exp_dir.glob('*.pkl'))
        if not fold_paths:
            print(f"No model files in {exp_dir}, skipping predict-per-DB-location")
            return

        if model_name in ['TabCmpt', 'MLP']:
            import torch
            from reland import RELand
            from model import TabCmpt, MLP
            from utils.model_finder import ModelFinder
            detected_type = ModelFinder.detect_model_type(fold_paths[0])
            actual_model_name = detected_type if detected_type in ['TabCmpt', 'MLP'] else model_name
            class Args:
                def __init__(self):
                    self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
                    self.objective = objective
                    self.model = actual_model_name
                    self.n_step = 2
                    self.timestamp = timestamp
            args = Args()
            all_preds = []
            for fold_path in fold_paths:
                model = RELand(all_data.tabX.shape[1], args)
                state_dict = torch.load(str(fold_path), map_location=args.device)
                model.model.load_state_dict(state_dict, strict=False)
                pred_result = model.predict_proba(test_dataset=db_dataset)
                pred = pred_result[4] if isinstance(pred_result, (tuple, list)) and len(pred_result) >= 5 else None
                if pred is not None:
                    all_preds.append(np.array(pred))
            predictions = np.array(all_preds).mean(axis=0) if all_preds else None
        elif model_name == 'TabNet':
            import pytorch_tabnet.tab_model as erm_tab_model
            import pytorch_tabnet_irm.tab_model as irm_tab_model
            model = irm_tab_model.TabNetClassifier(seed=737, n_steps=2) if objective == 'irm' else erm_tab_model.TabNetClassifier(seed=737, n_steps=2)
            model.load_model(str(fold_paths[0]))
            predictions = model.predict_proba(tabX_db)[:, 1]
            predictions = np.array(predictions)
        else:
            import pickle
            all_preds = []
            for path in fold_paths:
                with open(path, 'rb') as f:
                    m = pickle.load(f)
                all_preds.append(m.predict_proba(tabX_db)[:, 1])
            predictions = np.array(all_preds).mean(axis=0)

        if predictions is None or len(predictions) != n_db:
            print(f"Predictions length mismatch, skipping save")
            return

        global_mean = float(np.mean(predictions))
        by_municipio = {}
        for i, loc in enumerate(all_locations):
            by_municipio.setdefault(loc.municipio, []).append(i)
        for m, indices in by_municipio.items():
            if len(indices) < 2:
                continue
            vals = predictions[indices]
            if np.std(vals) < 1e-6:
                blend = 0.5
                for idx in indices:
                    predictions[idx] = (1 - blend) * float(predictions[idx]) + blend * global_mean

        save_predictions_to_db_by_locations(all_locations, predictions, db.session, Location, use_quantiles=True)
        print("Saved predictions per DB location (post-train)")


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
                    
                    # Calculate distances (load backend's DistanceCalculator by path so project-root utils.py doesn't shadow it)
                    import pandas as pd
                    import importlib.util
                    _dc_path = os.path.join(reland_backend, 'utils', 'distance_calculator.py')
                    _spec = importlib.util.spec_from_file_location('distance_calculator', _dc_path)
                    _dc = importlib.util.module_from_spec(_spec)
                    _spec.loader.exec_module(_dc)
                    DistanceCalculator = _dc.DistanceCalculator
                    
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
                    
                    distances = DistanceCalculator.distance_to_closest_point(grid_df, poi_df)
                    
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
            
            # Run training (this may take hours). Timeout configurable via TRAINING_TIMEOUT_SECONDS (default 6 hours).
            training_timeout = int(os.environ.get('TRAINING_TIMEOUT_SECONDS', 21600))  # 6 hours default
            result = subprocess.run(
                cmd,
                cwd=script_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=training_timeout
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
            
            # Save results: run predict-per-DB-location (same flow as recalculate) so all map points including Cartagena get correct predictions
            update_job_status(job_id, 'running', progress=0.9, message="Saving results...")
            predict_per_db_error = None
            used_fallback = False
            try:
                _run_predict_per_db_location_after_train(job_id, timestamp, script_dir)
            except Exception as e:
                import traceback
                predict_per_db_error = f"{type(e).__name__}: {e}"
                print(f"Warning: Predict-per-DB-location failed: {e}")
                print(traceback.format_exc())
                # Fallback: save from predicted_proba.csv if present (legacy behavior)
                try:
                    predicted_proba_path = os.path.join(script_dir, f'experiments/{timestamp}/predicted_proba.csv')
                    if os.path.exists(predicted_proba_path):
                        import pandas as pd
                        from save_predictions_db import save_predictions_to_db_orm
                        predictions_df = pd.read_csv(predicted_proba_path)
                        save_predictions_to_db_orm(predictions_df, db.session, Location)
                        used_fallback = True
                        print("Saved predictions from predicted_proba.csv (fallback)")
                except Exception as e2:
                    print(f"Warning: Could not save predictions: {str(e2)}")
            
            # Update job with results; surface predict-per-DB failure so user can see it
            result_data = {
                "timestamp": timestamp,
                "experiment_dir": f"./experiments/{timestamp}/",
                "return_code": result.returncode
            }
            if predict_per_db_error:
                result_data["predict_per_db_error"] = predict_per_db_error
                result_data["predictions_from_fallback"] = used_fallback
            final_message = "Training completed successfully"
            if predict_per_db_error:
                final_message = "Training completed; predictions saved from validation set only (predict-per-DB failed: " + predict_per_db_error[:200] + ")"
            
            # Get job again to update result
            job = TrainingJob.query.filter_by(id=job_id).first()
            if job:
                job.result = json.dumps(result_data)
                db.session.commit()
            
            update_job_status(
                job_id, 
                'completed', 
                progress=1.0,
                message=final_message
            )
            
            return True
        
        except subprocess.TimeoutExpired:
            training_timeout = int(os.environ.get('TRAINING_TIMEOUT_SECONDS', 21600))
            hours = training_timeout // 3600
            update_job_status(
                job_id, 
                'failed', 
                progress=1.0,
                error=f"Training timed out after {hours} hours (TRAINING_TIMEOUT_SECONDS={training_timeout}). Increase TRAINING_TIMEOUT_SECONDS or optimize training."
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

def run_once(job_id: str) -> int:
    """Process exactly one job and exit."""
    with app.app_context():
        job = TrainingJob.query.filter_by(id=job_id).first()
        if not job:
            print(f"ERROR: Job {job_id} not found")
            return 2
        print(f"Processing single job: {job.id}")
        ok = process_training_job(job)
        return 0 if ok else 1


def main(poll: bool = True):
    """Main worker loop (poll DB for pending jobs)."""
    print("RELand EC2 Worker starting...")
    print(f"Database: {DATABASE_URL[:50]}...")
    
    # Get instance ID for tracking
    try:
        import requests
        instance_id = requests.get('http://169.254.169.254/latest/meta-data/instance-id', timeout=2).text
        print(f"Instance ID: {instance_id}")
    except:
        instance_id = None
    
    if not poll:
        return

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
    parser = argparse.ArgumentParser(description="RELand training worker")
    parser.add_argument('--job-id', help="Process a specific job id and exit (for local execution)")
    args = parser.parse_args()

    if args.job_id:
        # Local mode: process single job and exit
        raise SystemExit(run_once(args.job_id))

    # Default behavior (EC2): poll for jobs until idle then terminate
    main(poll=True)

