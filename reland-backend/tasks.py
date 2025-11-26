"""
Background tasks for model training using RQ (Redis Queue).
This module contains long-running tasks that should be executed asynchronously.
"""
import os
import subprocess
import sys
import traceback
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import text, inspect, create_engine
from sklearn.neighbors import NearestNeighbors
from models import db, Location, ConfirmedEvent
from flask import Flask

# Optional imports for Redis Queue (background jobs)
try:
    from rq import get_current_job
    from rq.job import Job
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    get_current_job = None
    Job = None

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
    # Get current job if running in background (will be None if running synchronously)
    job = None
    if RQ_AVAILABLE and get_current_job:
        try:
            job = get_current_job()
        except:
            # Not running in a job context (synchronous mode)
            job = None
    
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
        else:
            print("  Step 1/3: Recalculating distances...")
        
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
                        db.session.rollback()
                        query = text("""
                            SELECT id, lat, lon, municipio, risk_score, risk_score_lr, risk_level,
                                   elevation, rainfall, temperature, population_2012, hist_mines,
                                   created_at, updated_at
                            FROM locations
                        """)
                        result = db.session.execute(query)
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
                        db.session.rollback()
                        raise
                
                if all_locations:
                    # Check if dist_old_mine column exists
                    inspector = inspect(db.engine)
                    columns = [col['name'] for col in inspector.get_columns('locations')]
                    column_exists = 'dist_old_mine' in columns
                    
                    if not column_exists:
                        db.session.execute(text("ALTER TABLE locations ADD COLUMN dist_old_mine FLOAT"))
                        db.session.commit()
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
                            db.session.execute(
                                update_query,
                                {'distance': float(distances[i]), 'location_id': location.id}
                            )
                        db.session.commit()
                    else:
                        for i, location in enumerate(all_locations):
                            location.dist_old_mine = float(distances[i])
                        db.session.commit()
        
        # Update progress
        if job:
            job.meta['progress'] = 'Starting model training script...'
            job.save_meta()
        else:
            print("  Step 2/3: Starting model training script...")
        
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
        
        # Find Python interpreter with ML dependencies
        # Prefer ML venv, then system Python (avoid backend venv)
        python_interpreter = None
        backend_venv_dir = os.path.dirname(os.path.abspath(__file__))
        
        # First, check for ML venv in project root (preferred)
        ml_venv_python = os.path.join(script_dir, 'ml_venv', 'bin', 'python')
        if os.path.exists(ml_venv_python):
            # Verify it has torch
            try:
                check_result = subprocess.run(
                    [ml_venv_python, '-c', 'import torch; print("OK")'],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                if check_result.returncode == 0:
                    python_interpreter = ml_venv_python
                    print(f"  ✓ Using ML venv Python: {python_interpreter}")
            except:
                pass
        
        # If ML venv not found, try system Python paths (avoid backend venv)
        if not python_interpreter:
            system_python_paths = [
                '/opt/homebrew/bin/python3',
                '/usr/local/bin/python3',
                '/usr/bin/python3',
            ]
            
            for python_path in system_python_paths:
                if os.path.exists(python_path):
                    # Resolve symlinks to get real path
                    try:
                        real_path = os.path.realpath(python_path)
                        # Check it's not inside the backend venv
                        if 'reland-backend' not in real_path or 'venv' not in real_path:
                            python_interpreter = python_path
                            print(f"  Using system Python: {python_interpreter}")
                            break
                    except:
                        # If realpath fails, just use it if it exists
                        python_interpreter = python_path
                        print(f"  Using system Python: {python_interpreter}")
                        break
        
        # If we still don't have one, try to find python3 while explicitly avoiding venv
        if not python_interpreter:
            try:
                # Use /usr/bin/env with a clean environment (no venv activation)
                env = os.environ.copy()
                # Remove VIRTUAL_ENV to avoid venv activation
                env.pop('VIRTUAL_ENV', None)
                env.pop('VIRTUAL_ENV_PROMPT', None)
                # Remove backend venv from PATH
                if 'PATH' in env:
                    paths = env['PATH'].split(os.pathsep)
                    paths = [p for p in paths if 'reland-backend/venv' not in p]
                    env['PATH'] = os.pathsep.join(paths)
                
                result = subprocess.run(
                    ['/usr/bin/env', 'python3', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    env=env
                )
                if result.returncode == 0:
                    # Get the actual path
                    which_result = subprocess.run(
                        ['/usr/bin/env', 'which', 'python3'],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        env=env
                    )
                    if which_result.returncode == 0:
                        candidate = which_result.stdout.strip()
                        # Double-check it's not the backend venv
                        if 'reland-backend/venv' not in candidate:
                            python_interpreter = candidate
                            print(f"  Using Python from PATH: {python_interpreter}")
            except:
                pass
        
        # Last resort: use /opt/homebrew/bin/python3 if it exists (common on macOS)
        if not python_interpreter and os.path.exists('/opt/homebrew/bin/python3'):
            python_interpreter = '/opt/homebrew/bin/python3'
            print(f"  Using fallback Python: {python_interpreter}")
        
        # Ultimate fallback: use sys.executable only if it's not the backend venv
        if not python_interpreter:
            sys_python = sys.executable
            # Check if it's the backend venv (check both forward and backslash paths)
            is_backend_venv = ('reland-backend/venv' in sys_python or 
                              'reland-backend\\venv' in sys_python or
                              os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/venv' in sys_python)
            if not is_backend_venv:
                python_interpreter = sys_python
                print(f"  Using sys.executable: {python_interpreter}")
            else:
                # Don't use backend venv - try one more time with which python3
                print(f"  ⚠️  sys.executable is backend venv, trying alternative...")
                try:
                    # Use which with clean environment
                    clean_env = os.environ.copy()
                    clean_env.pop('VIRTUAL_ENV', None)
                    clean_env.pop('VIRTUAL_ENV_PROMPT', None)
                    if 'PATH' in clean_env:
                        paths = clean_env['PATH'].split(os.pathsep)
                        paths = [p for p in paths if 'reland-backend' not in p and 'venv' not in p]
                        clean_env['PATH'] = os.pathsep.join(paths)
                    
                    which_result = subprocess.run(
                        ['which', 'python3'],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        env=clean_env
                    )
                    if which_result.returncode == 0:
                        candidate = which_result.stdout.strip()
                        if 'reland-backend' not in candidate:
                            python_interpreter = candidate
                            print(f"  Using alternative Python: {python_interpreter}")
                except:
                    pass
                
                # If still no interpreter, raise an error
                if not python_interpreter:
                    return {
                        "status": "error",
                        "error": "Could not find a suitable Python interpreter with ML dependencies",
                        "details": f"Backend venv Python ({sys_python}) lacks ML dependencies. Please use ML venv or system Python with torch installed.",
                        "timestamp": timestamp
                    }
        
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
        else:
            print(f"  Step 3/3: Training model (this may take 5-30 minutes)...")
        
        # Run the training script
        print(f"  Running: {' '.join(cmd)}")
        print(f"  Working directory: {script_dir}")
        try:
            # Run with real-time output for better debugging
            result = subprocess.run(
                cmd,
                cwd=script_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            # Print output immediately for debugging
            if result.stdout:
                print("STDOUT:", result.stdout[-2000:])  # Last 2000 chars
            if result.stderr:
                print("STDERR:", result.stderr[-2000:])  # Last 2000 chars
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
            
            # Print error to console for debugging
            print(f"❌ Model training failed with return code {result.returncode}")
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            
            return {
                "status": "error",
                "error": "Model training failed",
                "return_code": result.returncode,
                "details": relevant_error[:1000],
                "full_stderr": result.stderr[:2000] if result.stderr else None,
                "full_stdout": result.stdout[:2000] if result.stdout else None,
                "timestamp": timestamp
            }
        
        # Try to save predictions to database
        predictions_saved = False
        try:
            predicted_proba_path = os.path.join(script_dir, f'experiments/{timestamp}/predicted_proba.csv')
            if os.path.exists(predicted_proba_path):
                with worker_app.app_context():
                    # Add project root to Python path to find save_predictions_db
                    project_root = os.path.dirname(script_dir)
                    if project_root not in sys.path:
                        sys.path.insert(0, project_root)
                    
                    predictions_df = pd.read_csv(predicted_proba_path)
                    from save_predictions_db import save_predictions_to_db_orm
                    save_predictions_to_db_orm(predictions_df, db.session, Location)
                predictions_saved = True
        except Exception as e:
            print(f"⚠️  Could not save predictions to database: {str(e)}")
            import traceback
            print(f"   Full error: {traceback.format_exc()}")
        
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

