"""
Recalculate and prediction routes
"""
from flask import jsonify, request
from routes import api_bp
import pandas as pd
import numpy as np
from services.location_service import LocationService
from services.event_service import EventService
from utils.distance_calculator import DistanceCalculator
from utils.model_finder import ModelFinder
from exceptions import RELandException, ModelError
from models import db, Location, ConfirmedEvent
from config import config


@api_bp.route('/recalculate_and_predict', methods=['POST'])
def recalculate_and_predict():
    """
    Recalculate dist_old_mine for all locations based on confirmed events,
    then re-predict risk scores using existing trained model.
    """
    try:
        data = request.json or {}
        model_name = data.get('model', 'TabCmpt')
        municipio = data.get('municipio', 'blockCV')
        subset = data.get('subset', 'full')
        objective = data.get('objective', 'irm')
        
        print("🔄 Starting distance recalculation and re-prediction...")
        
        # Get all locations
        all_locations = LocationService.get_all()
        
        if not all_locations:
            return jsonify({"error": "No locations found in database"}), 404
        
        print(f"  Found {len(all_locations)} locations in database")
        
        # Get all confirmed events
        confirmed_events = EventService.get_all()
        print(f"  Found {len(confirmed_events)} confirmed events")
        
        if len(confirmed_events) == 0:
            return jsonify({
                "message": "No confirmed events found. Cannot recalculate distances.",
                "updated_count": 0
            }), 200
        
        # Prepare grid (all locations) as DataFrame
        grid_data = {
            'id': [loc.id for loc in all_locations],
            'lat': [loc.lat for loc in all_locations],
            'lon': [loc.lon for loc in all_locations]
        }
        grid_df = pd.DataFrame(grid_data)
        
        # Prepare points of interest (confirmed events) as DataFrame
        poi_data = {
            'lat': [event.lat for event in confirmed_events],
            'lon': [event.lon for event in confirmed_events]
        }
        poi_df = pd.DataFrame(poi_data)
        
        # Calculate distance to closest confirmed event
        print("  Calculating distances to closest confirmed events...")
        distances = DistanceCalculator.distance_to_closest_point(grid_df, poi_df)
        
        # Ensure dist_old_mine column exists
        LocationService.ensure_dist_old_mine_column()
        
        # Update locations with new distance feature
        location_ids = [loc.id for loc in all_locations]
        updated_count = LocationService.update_distances(location_ids, distances.tolist())
        
        print(f"✓ Recalculated distances for {len(all_locations)} locations")
        print(f"  Min distance: {distances.min():.4f} km")
        print(f"  Max distance: {distances.max():.4f} km")
        print(f"  Mean distance: {distances.mean():.4f} km")
        
        # Find and load trained model(s) - use multi-fold averaging for sklearn/Lightweight to avoid "all points = 1" in whole regions
        print(f"  Looking for model: {model_name}, municipio: {municipio}")
        timestamp, fold_paths = ModelFinder.find_all_fold_models_in_latest_experiment(model_name, municipio)
        if not fold_paths:
            model_path, timestamp, detected_model_type = ModelFinder.find_latest_model(model_name, municipio)
            fold_paths = [model_path] if model_path else []
        if not fold_paths:
            return jsonify({
                "message": "Distances recalculated successfully, but no trained model found for re-prediction.",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "note": f"Please train a {model_name} model first using the retrain endpoint."
            }), 200
        model_path = fold_paths[0]
        detected_model_type = model_name if model_name not in ['TabCmpt', 'MLP'] else ModelFinder.detect_model_type(model_path)
        print(f"  Found {len(fold_paths)} fold model(s) in experiment {timestamp}")
        
        # Load model and make predictions
        try:
            # Import model classes
            import sys
            import os
            sys.path.insert(0, str(config.BACKEND_ROOT))
            sys.path.insert(0, str(config.PROJECT_ROOT))
            
            from dataset_db import EventDB
            from save_predictions_db import save_predictions_to_db_orm, save_predictions_to_db_by_locations
            
            # Load dataset with updated dist_old_mine
            train_municipios = ['BOLÍVAR', 'MURINDÓ', 'PUERTO LIBERTADOR']
            # FIX: When municipio is 'blockCV', use 'ALL' to load ALL locations from CSV
            # EventDB will fall back to all locations when municipio is not found (see dataset_db.py line 260-264)
            if municipio == 'blockCV':
                val_municipio = 'ALL'  # This doesn't exist in CSV, so EventDB loads all locations
            else:
                val_municipio = municipio.upper()
            
            print(f"  Loading dataset with val_municipio='{val_municipio}' (will load all locations if not found)")
            all_data = EventDB(
                train_municipios=train_municipios,
                val_municipio=val_municipio,
                subset=subset,
                split='val',
                db_url=config.DATABASE_URL
            )
            
            print(f"  Loaded {len(all_data)} locations from EventDB (CSV grid)")
            print(f"  Locations shape: {all_data.locations.shape}")
            print(f"  TabX shape: {all_data.tabX.shape}")
            
            # Predict per DB location using nearest-CSV features so each map point gets its own prediction (spatial variation)
            from sklearn.neighbors import NearestNeighbors
            db_lon_lat = np.array([[loc.lon, loc.lat] for loc in all_locations], dtype=np.float64)
            csv_lon_lat = np.column_stack([all_data.locations[:, 0], all_data.locations[:, 1]])
            nn = NearestNeighbors(n_neighbors=1, metric='euclidean')
            nn.fit(csv_lon_lat)
            _, nearest_idx = nn.kneighbors(db_lon_lat)
            nearest_idx = nearest_idx.flatten()
            tabX_db = np.array(all_data.tabX[nearest_idx], dtype=np.float32)
            # Keep scaled lon/lat from nearest CSV row (do NOT overwrite with raw DB coords) so model input matches training scale
            n_db = len(all_locations)
            print(f"  Built feature matrix for {n_db} DB locations (nearest-CSV row per location)")
            
            # Minimal dataset for PyTorch/RELand: one row per DB location
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
            
            # Load model based on type
            if model_name in ['TabCmpt', 'MLP']:
                try:
                    import torch
                except ImportError:
                    raise ModelError("PyTorch is required for TabCmpt/MLP models. Please install torch.")
                
                from reland import RELand
                from model import TabCmpt, MLP
                
                actual_model_name = detected_model_type if detected_model_type in ['TabCmpt', 'MLP'] else model_name
                if detected_model_type != model_name and detected_model_type in ['TabCmpt', 'MLP']:
                    print(f"  ⚠️  Warning: Found {detected_model_type} model but requested {model_name}. Using {detected_model_type}.")
                
                # Create args object
                class Args:
                    def __init__(self, obj, ts, mname):
                        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
                        self.objective = obj
                        self.model = mname
                        self.n_step = 2
                        self.lr = 0.01
                        self.step_size = 75
                        self.gamma = 0.1
                        self.lambda_l2 = 5e-4
                        self.epochs = 500
                        self.batch_size = 2048
                        self.num_workers = 4
                        self.timestamp = ts
                
                args = Args(objective, timestamp, actual_model_name)
                all_preds = []
                for i, fold_path in enumerate(fold_paths):
                    model = RELand(all_data.tabX.shape[1], args)
                    print(f"  Loading fold {i + 1}/{len(fold_paths)} from: {fold_path}")
                    state_dict = torch.load(fold_path, map_location=args.device)
                    missing_keys, unexpected_keys = model.model.load_state_dict(state_dict, strict=False)
                    if missing_keys and i == 0:
                        print(f"  ⚠️  Warning: Missing keys in model: {len(missing_keys)} keys")
                    if unexpected_keys and i == 0:
                        print(f"  ⚠️  Warning: Unexpected keys in model: {len(unexpected_keys)} keys")
                    predictions_result = model.predict_proba(test_dataset=db_dataset)
                    if not isinstance(predictions_result, (tuple, list)) or len(predictions_result) < 5:
                        raise ValueError(f"Unexpected predictions result from fold {i + 1}")
                    pred = predictions_result[4]
                    if pred is None:
                        raise ValueError(f"Predictions array is None for fold {i + 1}")
                    all_preds.append(np.array(pred))
                predictions = np.array(all_preds).mean(axis=0)
                if len(predictions) != n_db:
                    raise ValueError(
                        f"Predictions length ({len(predictions)}) doesn't match DB locations ({n_db})"
                    )
                print(f"  ✓ Model loaded and predictions averaged over {len(fold_paths)} fold(s) (per DB location)")
                print(f"  Prediction stats: min={predictions.min():.4f}, max={predictions.max():.4f}, mean={predictions.mean():.4f}")
                
            elif model_name == 'TabNet':
                import pytorch_tabnet.tab_model as erm_tab_model
                import pytorch_tabnet_irm.tab_model as irm_tab_model
                
                if objective == 'irm':
                    model = irm_tab_model.TabNetClassifier(seed=737, n_steps=2)
                else:
                    model = erm_tab_model.TabNetClassifier(seed=737, n_steps=2)
                
                model.load_model(str(model_path))
                predictions = model.predict_proba(tabX_db)[:, 1]
                
                predictions = np.array(predictions)
                if len(predictions) != n_db:
                    raise ValueError(
                        f"Predictions length ({len(predictions)}) doesn't match DB locations ({n_db})"
                    )
                
                print(f"  Generated {len(predictions)} predictions (per DB location)")
                print(f"  Prediction stats: min={predictions.min():.4f}, max={predictions.max():.4f}, mean={predictions.mean():.4f}")
            else:
                # For sklearn models (Lightweight, LR, RF, etc.): average over all folds, predict per DB location
                import pickle
                all_preds = []
                for i, path in enumerate(fold_paths):
                    with open(path, 'rb') as f:
                        model = pickle.load(f)
                    pred = model.predict_proba(tabX_db)[:, 1]
                    all_preds.append(pred)
                predictions = np.array(all_preds).mean(axis=0)
                
                if len(predictions) != n_db:
                    raise ValueError(
                        f"Predictions length ({len(predictions)}) doesn't match DB locations ({n_db})"
                    )
                
                print(f"  Generated {len(predictions)} predictions (per DB location, averaged over {len(fold_paths)} folds)")
                print(f"  Prediction stats: min={predictions.min():.4f}, max={predictions.max():.4f}, mean={predictions.mean():.4f}")
            
            # Fix 3: Blend constant-municipality predictions with global mean so OOD municipalities don't show pure 0/1
            global_mean = float(np.mean(predictions))
            by_municipio = {}
            for i, loc in enumerate(all_locations):
                by_municipio.setdefault(loc.municipio, []).append(i)
            constant_municipalities = []
            for m, indices in by_municipio.items():
                if len(indices) < 2:
                    continue
                vals = predictions[indices]
                if np.std(vals) < 1e-6:
                    constant_municipalities.append(m)
                    blend = 0.5  # blend 50% with global mean
                    for idx in indices:
                        predictions[idx] = (1 - blend) * predictions[idx] + blend * global_mean
            if constant_municipalities:
                print(f"  Post-processed {len(constant_municipalities)} constant municipalities (blended with global mean): {constant_municipalities[:5]}{'...' if len(constant_municipalities) > 5 else ''}")
                print(f"  Tip: retrain with municipio=map_included for full variation in all municipalities.")
            
            # Save predictions to database (one per DB location, quantile-based risk_level)
            print("  Saving predictions to database (one per DB location)...")
            updated_predictions_count = save_predictions_to_db_by_locations(
                all_locations, predictions, db.session, Location, use_quantiles=True
            )
            
            print(f"✓ Re-prediction completed successfully")
            print(f"  Updated {updated_predictions_count} locations with new predictions (one per DB location)")
            
            return jsonify({
                "message": "Distances recalculated and predictions updated successfully (one prediction per map point)",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "predictions_count": n_db,
                "locations_updated": updated_predictions_count,
                "model_used": str(model_path),
                "prediction_stats": {
                    "min": float(predictions.min()),
                    "max": float(predictions.max()),
                    "mean": float(predictions.mean())
                }
            }), 200
            
        except Exception as e:
            import traceback
            print(f"  ⚠️  Error during re-prediction: {str(e)}")
            print(traceback.format_exc())
            # Still return success for distance recalculation
            return jsonify({
                "message": "Distances recalculated successfully, but re-prediction failed.",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "error": str(e),
                "note": "Distances have been updated. You may need to retrain the model."
            }), 200
        
    except RELandException as e:
        db.session.rollback()
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error in recalculate_and_predict: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@api_bp.route('/reset_predictions', methods=['POST'])
def reset_predictions():
    """
    Clear risk_score and risk_level for all locations (set to NULL).
    Use before testing retrain/repredict from a clean state.
    """
    try:
        from sqlalchemy import text
        total = Location.query.count()
        db.session.execute(text(
            "UPDATE locations SET risk_score = NULL, risk_level = NULL"
        ))
        db.session.commit()
        return jsonify({
            "message": "All predictions cleared. Run retrain then recalculate_and_predict to repopulate.",
            "locations_updated": total
        }), 200
    except Exception as e:
        db.session.rollback()
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500