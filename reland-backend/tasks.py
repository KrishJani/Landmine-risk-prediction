"""
Background tasks for model training using RQ (Redis Queue).
This module contains long-running tasks that should be executed asynchronously.
"""
import os
import subprocess
import sys
import traceback
from datetime import datetime
from rq import get_current_job
from rq.job import Job
import pandas as pd
import numpy as np
from sqlalchemy import text, inspect, create_engine
from sklearn.neighbors import NearestNeighbors
from models import db, Location, ConfirmedEvent
from flask import Flask

# Create a minimal Flask app context for database operations
def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

# Distance calculation function (copied from backend_app to avoid circular imports)
def distance_to_closest_point(grid, points_of_interest):
    """
    Calculate distance from each grid point to the closest point of interest.
    Uses haversine distance (great circle distance on Earth).
    
    Args:
        grid: DataFrame with columns for latitude and longitude
        points_of_interest: DataFrame with columns for latitude and longitude
    
    Returns:
        numpy array of distances in kilometers
    """
    # Normalize column names
    grid_lat_col = 'LATITUDE_Y' if 'LATITUDE_Y' in grid.columns else ('LATITUD_Y' if 'LATITUD_Y' in grid.columns else 'lat')
    grid_lon_col = 'LONGITUDE_X' if 'LONGITUDE_X' in grid.columns else ('LONGITUD_X' if 'LONGITUD_X' in grid.columns else 'lon')
    poi_lat_col = 'LATITUDE_Y' if 'LATITUDE_Y' in points_of_interest.columns else ('LATITUD_Y' if 'LATITUD_Y' in points_of_interest.columns else 'lat')
    poi_lon_col = 'LONGITUDE_X' if 'LONGITUDE_X' in points_of_interest.columns else ('LONGITUD_X' if 'LONGITUD_X' in points_of_interest.columns else 'lon')
    
    # Convert to radians for haversine distance
    grid_coords = np.deg2rad(points_of_interest[[poi_lat_col, poi_lon_col]].values)
    poi_coords = np.deg2rad(grid[[grid_lat_col, grid_lon_col]].values)
    
    # Use NearestNeighbors with haversine metric
    nbrs = NearestNeighbors(n_neighbors=1, algorithm='ball_tree', metric='haversine')
    nbrs.fit(grid_coords)
    distances, _ = nbrs.kneighbors(poi_coords)
    
    # Convert from radians to kilometers (Earth radius = 6371 km)
    distances_km = distances.flatten() * 6371
    
    return distances_km

def train_model_task(municipio, subset, model_name, objective, n_step, db_url):
    """
    Background task to train the model.
    This function runs in a separate worker process and can take a long time.
    
    Args:
        municipio: Municipality/validation method (e.g., 'blockCV')
        subset: Feature subset ('single', 'geo', 'full')
        model_name: Model type ('TabCmpt', 'MLP', 'TabNet', etc.)
        objective: Training objective ('irm', 'erm', 'pnorm')
        n_step: Number of decision blocks
        db_url: Database URL for the worker to connect
    
    Returns:
        dict: Training results with status, timestamp, and any errors
    """
    job = get_current_job()
    if job:
        job.meta['progress'] = 'Starting model training...'
        job.save_meta()
    
    try:
        # Set up database connection for worker
        os.environ['DATABASE_URL'] = db_url
        
        # Update progress
        if job:
            job.meta['progress'] = 'Recalculating distances...'
            job.save_meta()
        
        # Create Flask app for database context
        worker_app = create_app()
        
        # First, recalculate distances if confirmed events exist
        with worker_app.app_context():
            confirmed_events = ConfirmedEvent.query.all()
            
            if len(confirmed_events) > 0:
                # Handle case where dist_old_mine column doesn't exist yet
                try:
                    all_locations = Location.query.all()
                except Exception as db_error:
                    if 'dist_old_mine' in str(db_error) or 'UndefinedColumn' in str(db_error):
                        worker_db.session.rollback()
                        query = text("""
                            SELECT id, lat, lon, municipio, risk_score, risk_score_lr, risk_level,
                                   elevation, rainfall, temperature, population_2012, hist_mines,
                                   created_at, updated_at
                            FROM locations
                        """)
                        result = worker_db.session.execute(query)
                        all_locations = []
                        for row in result:
                            loc = Location()
                            loc.id = row.id
                            loc.lat = row.lat
                            loc.lon = row.lon
                            loc.municipio = row.municipio
                            loc.risk_score = row.risk_score
                            loc.risk_score_lr = row.risk_score_lr
                            loc.risk_level = row.risk_level
                            loc.elevation = row.elevation
                            loc.rainfall = row.rainfall
                            loc.temperature = row.temperature
                            loc.population_2012 = row.population_2012
                            loc.hist_mines = row.hist_mines
                            loc.created_at = row.created_at
                            loc.updated_at = row.updated_at
                            loc.dist_old_mine = None
                            all_locations.append(loc)
                    else:
                        worker_db.session.rollback()
                        raise
                
                if all_locations:
                    # Check if dist_old_mine column exists
                    inspector = inspect(worker_db.engine)
                    columns = [col['name'] for col in inspector.get_columns('locations')]
                    column_exists = 'dist_old_mine' in columns
                    
                    if not column_exists:
                        worker_db.session.execute(text("ALTER TABLE locations ADD COLUMN dist_old_mine FLOAT"))
                        worker_db.session.commit()
                        column_exists = True
                    
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
                    
                    # Bulk update distances
                    if column_exists:
                        update_query = text("""
                            UPDATE locations 
                            SET dist_old_mine = :distance 
                            WHERE id = :location_id
                        """)
                        for i, location in enumerate(all_locations):
                            worker_db.session.execute(
                                update_query,
                                {'distance': float(distances[i]), 'location_id': location.id}
                            )
                        worker_db.session.commit()
                    else:
                        for i, location in enumerate(all_locations):
                            location.dist_old_mine = float(distances[i])
                        worker_db.session.commit()
        
        # Update progress
        if job:
            job.meta['progress'] = 'Starting model training script...'
            job.save_meta()
        
        # Generate timestamp for this training run
        timestamp = datetime.now().strftime("%m%d%Y%H%M%S")
        
        # Get script directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        main_script = os.path.join(script_dir, 'main.py')
        
        if not os.path.exists(main_script):
            return {
                "status": "error",
                "error": f"main.py not found at {main_script}",
                "timestamp": timestamp
            }
        
        # Verify train_val_stream directory exists
        train_val_dir = os.path.join(script_dir, 'train_val_stream', municipio)
        if not os.path.exists(train_val_dir):
            available_dirs = [d for d in os.listdir(os.path.join(script_dir, 'train_val_stream')) 
                            if os.path.isdir(os.path.join(script_dir, 'train_val_stream', d))]
            return {
                "status": "error",
                "error": f"Train/val split directory not found: {train_val_dir}",
                "available_directories": available_dirs,
                "timestamp": timestamp
            }
        
        # Find Python interpreter
        python_interpreter = None
        
        # Try to find python3 in PATH
        try:
            result = subprocess.run(
                ['which', 'python3'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                python_interpreter = result.stdout.strip()
        except:
            pass
        
        # Fallback to common paths
        if not python_interpreter:
            for path in ['/opt/homebrew/bin/python3', '/usr/local/bin/python3', '/usr/bin/python3']:
                if os.path.exists(path):
                    python_interpreter = path
                    break
        
        # Ultimate fallback
        if not python_interpreter:
            python_interpreter = sys.executable
        
        # Build command
        cmd = [
            python_interpreter, main_script,
            '--timestamp', timestamp,
            '--municipio', municipio,
            '--subset', subset,
            '--model', model_name,
            '--objective', objective,
            '--n_step', str(n_step)
        ]
        
        # Set environment variables
        env = os.environ.copy()
        env['DATABASE_URL'] = db_url
        
        if job:
            job.meta['progress'] = f'Training model (this may take 5-30 minutes)...'
            job.save_meta()
        
        # Run the training script
        try:
            result = subprocess.run(
                cmd,
                cwd=script_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "Model training timed out (exceeded 1 hour)",
                "timestamp": timestamp
            }
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            error_lines = error_msg.split('\n')
            relevant_error = '\n'.join(error_lines[-20:])
            
            return {
                "status": "error",
                "error": "Model training failed",
                "return_code": result.returncode,
                "details": relevant_error[:1000],
                "timestamp": timestamp
            }
        
        # Try to save predictions to database
        predictions_saved = False
        try:
            predicted_proba_path = os.path.join(script_dir, f'experiments/{timestamp}/predicted_proba.csv')
            if os.path.exists(predicted_proba_path):
                with worker_app.app_context():
                    predictions_df = pd.read_csv(predicted_proba_path)
                    from save_predictions_db import save_predictions_to_db_orm
                    save_predictions_to_db_orm(predictions_df, worker_db.session, Location)
                predictions_saved = True
        except Exception as e:
            print(f"⚠️  Could not save predictions to database: {str(e)}")
        
        return {
            "status": "completed",
            "timestamp": timestamp,
            "experiment_dir": f"./experiments/{timestamp}/",
            "predictions_saved": predictions_saved,
            "message": "Model training completed successfully"
        }
        
    except Exception as e:
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        print(f"❌ Error in train_model_task: {error_msg}")
        print(traceback_str)
        
        return {
            "status": "error",
            "error": error_msg,
            "traceback": traceback_str[:1000],
            "timestamp": datetime.now().strftime("%m%d%Y%H%M%S")
        }

