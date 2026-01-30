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
        
        # Find and load trained model
        print(f"  Looking for model: {model_name}, municipio: {municipio}")
        model_path, timestamp, detected_model_type = ModelFinder.find_latest_model(model_name, municipio)
        
        if not model_path:
            return jsonify({
                "message": "Distances recalculated successfully, but no trained model found for re-prediction.",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "note": f"Please train a {model_name} model first using the retrain endpoint."
            }), 200
        
        print(f"  Found model: {model_path} (detected type: {detected_model_type})")
        
        # Load model and make predictions
        try:
            # Import model classes
            import sys
            import os
            sys.path.insert(0, str(config.BACKEND_ROOT))
            sys.path.insert(0, str(config.PROJECT_ROOT))
            
            from dataset_db import EventDB
            from save_predictions_db import save_predictions_to_db_orm
            
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
            
            print(f"  Loaded {len(all_data)} locations from EventDB")
            print(f"  Locations shape: {all_data.locations.shape}")
            print(f"  TabX shape: {all_data.tabX.shape}")
            
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
                model = RELand(all_data.tabX.shape[1], args)
                
                # Load state dict
                print(f"  Loading model from: {model_path}")
                state_dict = torch.load(model_path, map_location=args.device)
                missing_keys, unexpected_keys = model.model.load_state_dict(state_dict, strict=False)
                if missing_keys:
                    print(f"  ⚠️  Warning: Missing keys in model: {len(missing_keys)} keys")
                if unexpected_keys:
                    print(f"  ⚠️  Warning: Unexpected keys in model: {len(unexpected_keys)} keys")
                print("  ✓ Model loaded successfully")
                
                # Make predictions
                print("  Making predictions...")
                predictions_result = model.predict_proba(test_dataset=all_data)
                
                # FIX: Validate predictions result structure
                if not isinstance(predictions_result, (tuple, list)):
                    raise ValueError(f"Unexpected predictions result type: {type(predictions_result)}")
                
                if len(predictions_result) < 5:
                    raise ValueError(f"Predictions result has {len(predictions_result)} elements, expected at least 5")
                
                predictions = predictions_result[4]  # Get the probability array
                
                # FIX: Validate predictions array
                if predictions is None:
                    raise ValueError("Predictions array is None")
                
                predictions = np.array(predictions)
                if len(predictions) != len(all_data):
                    raise ValueError(
                        f"Predictions length ({len(predictions)}) doesn't match dataset length ({len(all_data)})"
                    )
                
                print(f"  Generated {len(predictions)} predictions")
                print(f"  Prediction stats: min={predictions.min():.4f}, max={predictions.max():.4f}, mean={predictions.mean():.4f}")
                
            elif model_name == 'TabNet':
                import pytorch_tabnet.tab_model as erm_tab_model
                import pytorch_tabnet_irm.tab_model as irm_tab_model
                
                if objective == 'irm':
                    model = irm_tab_model.TabNetClassifier(seed=737, n_steps=2)
                else:
                    model = erm_tab_model.TabNetClassifier(seed=737, n_steps=2)
                
                model.load_model(str(model_path))
                predictions = model.predict_proba(all_data.tabX)[:, 1]
                
                # Validate predictions
                predictions = np.array(predictions)
                if len(predictions) != len(all_data):
                    raise ValueError(
                        f"Predictions length ({len(predictions)}) doesn't match dataset length ({len(all_data)})"
                    )
                
                print(f"  Generated {len(predictions)} predictions")
                print(f"  Prediction stats: min={predictions.min():.4f}, max={predictions.max():.4f}, mean={predictions.mean():.4f}")
            else:
                # For sklearn models
                import pickle
                with open(model_path, 'rb') as f:
                    model = pickle.load(f)
                predictions = model.predict_proba(all_data.tabX)[:, 1]
                
                # Validate predictions
                predictions = np.array(predictions)
                if len(predictions) != len(all_data):
                    raise ValueError(
                        f"Predictions length ({len(predictions)}) doesn't match dataset length ({len(all_data)})"
                    )
                
                print(f"  Generated {len(predictions)} predictions")
                print(f"  Prediction stats: min={predictions.min():.4f}, max={predictions.max():.4f}, mean={predictions.mean():.4f}")
            
            # Create predictions DataFrame
            predictions_df = pd.DataFrame({
                'LONGITUD_X': all_data.locations[:, 0],
                'LATITUD_Y': all_data.locations[:, 1],
                'predicted_proba': predictions
            })
            
            print(f"  Created predictions DataFrame with {len(predictions_df)} rows")
            print(f"  Unique coordinates: {len(predictions_df.drop_duplicates(subset=['LONGITUD_X', 'LATITUD_Y']))}")
            
            # Save predictions to database
            print("  Saving predictions to database...")
            updated_predictions_count = save_predictions_to_db_orm(predictions_df, db.session, Location)
            
            print(f"✓ Re-prediction completed successfully")
            print(f"  Updated {updated_predictions_count} locations with new predictions")
            
            return jsonify({
                "message": "Distances recalculated and predictions updated successfully",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "predictions_count": len(predictions_df),
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