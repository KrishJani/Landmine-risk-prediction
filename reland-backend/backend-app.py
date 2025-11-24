import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
from math import isfinite
from dotenv import load_dotenv
from models import db, Location, UserLabel, ConfirmedEvent
from municipality_borders import get_municipality_borders, get_all_municipality_names
import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
import subprocess
import glob
import sys
from rq import Queue
from rq.job import Job
from redis import Redis

# Optional imports for model prediction (only needed when recalculating predictions)
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Database configuration - PostgreSQL
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is not set. "
        "Please create a .env file with DATABASE_URL=postgresql://user:password@localhost:5432/reland_db"
    )

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Verify connections before using
    'pool_recycle': 300,    # Recycle connections after 5 minutes
}

# Initialize database
db.init_app(app)

# Redis Queue configuration for background jobs
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
try:
    redis_conn = Redis.from_url(REDIS_URL)
    # Test connection
    redis_conn.ping()
    task_queue = Queue('model_training', connection=redis_conn)
    print("✓ Redis connection established for background jobs")
except Exception as e:
    print(f"⚠️  Warning: Redis not available ({str(e)}). Background jobs will not work.")
    print("   Set REDIS_URL environment variable to enable background model training.")
    redis_conn = None
    task_queue = None

# Helper Functions
def calculate_risk_levels(locations, score_column='risk_score'):
    """
    Calculate risk levels for a list of Location objects.
    Uses quantile-based binning to categorize into Low/Medium/High.
    """
    if not locations:
        return {}
    
    # Extract scores
    scores = []
    for loc in locations:
        score = getattr(loc, score_column, None)
        if score is not None and not (isinstance(score, float) and (score != score or not isfinite(score))):
            scores.append(score)
    
    if not scores:
        # No valid scores, assign all as Low
        return {loc.id: 'Low' for loc in locations}
    
    # Calculate quantiles
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    low_threshold = scores_sorted[n // 3] if n >= 3 else scores_sorted[0]
    high_threshold = scores_sorted[2 * n // 3] if n >= 3 else scores_sorted[-1]
    
    # Assign risk levels
    risk_levels = {}
    for loc in locations:
        score = getattr(loc, score_column, None)
        if score is None or (isinstance(score, float) and (score != score or not isfinite(score))):
            risk_levels[loc.id] = 'Low'
        elif score <= low_threshold:
            risk_levels[loc.id] = 'Low'
        elif score <= high_threshold:
            risk_levels[loc.id] = 'Medium'
        else:
            risk_levels[loc.id] = 'High'
    
    return risk_levels

def get_color_for_risk_level(risk_level):
    """Get color for a risk level"""
    color_map = {
        'Low': 'rgb(0, 255, 0)',      # Green
        'Medium': 'rgb(245, 221, 43)', # Yellow
        'High': 'rgb(255, 0, 0)'       # Red
    }
    return color_map.get(risk_level, 'rgb(128, 128, 128)')  # Gray as default

@app.route('/')
def index():
    """Root endpoint - API information"""
    return jsonify({
        "message": "RELand Backend API",
        "version": "2.0",
        "mode": "database-only",
        "endpoints": {
            "/api/initial_data": "GET - Get list of available areas",
            "/api/map_data": "GET - Get map data for selected areas",
            "/api/municipality_borders": "GET - Get municipality borders as GeoJSON",
            "/api/geocode": "GET - Geocode an address",
            "/api/labels": "GET/POST - Manage user labels",
            "/api/confirmed_events": "GET/POST/PUT/DELETE - Manage confirmed events",
            "/api/locations": "PUT/POST - Update location risk scores"
        }
    })

@app.route('/api/initial_data')
def get_initial_data():
    """Get list of available areas from database"""
    try:
        areas = db.session.query(Location.municipio).distinct().all()
        area_list = [area[0] for area in areas if area[0] and area[0].lower() != 'unknown']
        area_list.sort()
        return jsonify({"areas": area_list})
    except Exception:
        return jsonify({"areas": []})

@app.route('/api/map_data')
def get_map_data():
    """Get map data (risk heatmap and historical points) from database"""
    try:
        selected_areas = request.args.getlist('areas[]')
        score_to_use = 'risk_score'
        
        if not selected_areas:
            return jsonify({
                "risk_heatmap_points": [],
                "historical_points": [],
                "confirmed_events": []
            })

        # Query locations - handle case where dist_old_mine column doesn't exist yet
        try:
            # Try to query with all columns (including dist_old_mine)
            locations = Location.query.filter(Location.municipio.in_(selected_areas)).all()
        except Exception as db_error:
            # If dist_old_mine column doesn't exist, use raw SQL to query without it
            if 'dist_old_mine' in str(db_error) or 'UndefinedColumn' in str(db_error):
                print("⚠️  dist_old_mine column not found. Querying without it...")
                # Rollback the failed transaction
                db.session.rollback()
                from sqlalchemy import text
                query = text("""
                    SELECT id, lat, lon, municipio, risk_score, risk_score_lr, risk_level,
                           elevation, rainfall, temperature, population_2012, hist_mines,
                           created_at, updated_at
                    FROM locations
                    WHERE municipio = ANY(:municipios)
                """)
                result = db.session.execute(query, {'municipios': selected_areas})
                # Convert to Location objects manually
                locations = []
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
                    loc.dist_old_mine = None  # Set to None since column doesn't exist
                    locations.append(loc)
            else:
                # Rollback and re-raise if it's a different error
                db.session.rollback()
                raise
        
        if not locations:
            return jsonify({
                "risk_heatmap_points": [],
                "historical_points": [],
                "confirmed_events": []
            })
        
        risk_levels = calculate_risk_levels(locations, score_to_use)
        
        # Debug: Check actual risk score values
        all_scores = [getattr(loc, score_to_use, None) or loc.risk_score_lr for loc in locations if getattr(loc, score_to_use, None) or loc.risk_score_lr]
        valid_scores = [s for s in all_scores if s is not None and isfinite(s)]
        
        if valid_scores:
            sorted_scores = sorted(valid_scores)
            print(f"\n📊 Risk Score Statistics (for {len(valid_scores)} locations):")
            print(f"   Min: {sorted_scores[0]}")
            print(f"   25th percentile: {sorted_scores[len(sorted_scores)//4]}")
            print(f"   50th percentile (median): {sorted_scores[len(sorted_scores)//2]}")
            print(f"   75th percentile: {sorted_scores[3*len(sorted_scores)//4]}")
            print(f"   Max: {sorted_scores[-1]}")
            print(f"   Range: {sorted_scores[-1] - sorted_scores[0]}")
            if len(set(valid_scores)) == 1:
                print(f"   ⚠️  WARNING: All scores are identical ({valid_scores[0]})")
        
        risk_points = []
        for location in locations:
            risk_level = risk_levels.get(location.id, 'Low')
            risk_score = getattr(location, score_to_use, None) or location.risk_score_lr
            
            # Ensure we have a valid numeric score
            if risk_score is None or not isfinite(risk_score):
                risk_score = 0.0
            
            risk_points.append({
                'LATITUD_Y': location.lat,
                'LONGITUD_X': location.lon,
                'risk_score': float(risk_score),
                'risk_level': risk_level,
                'color': get_color_for_risk_level(risk_level),
                'location_id': location.id,
                'Municipio': location.municipio
            })
        
        historical_points = []
        for loc in locations:
            if loc.hist_mines is not None and loc.hist_mines > 0:
                try:
                    historical_points.append({
                        'LATITUD_Y': loc.lat,
                        'LONGITUD_X': loc.lon,
                        'hist_mines': float(loc.hist_mines),
                        'hist_color': 'purple'
                    })
                except (ValueError, TypeError):
                    # Skip invalid hist_mines values
                    continue
        
        try:
            confirmed_events = ConfirmedEvent.query.all()
        except Exception as e:
            print(f"Error fetching confirmed events: {str(e)}")
            confirmed_events = []
        
        return jsonify({
            "risk_heatmap_points": risk_points,
            "historical_points": historical_points,
            "confirmed_events": [event.to_dict() for event in confirmed_events]
        })
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        print(f"Error in /api/map_data: {error_msg}")
        return jsonify({
            "error": f"Error fetching map data: {error_msg}",
            "risk_heatmap_points": [],
            "historical_points": [],
            "confirmed_events": []
        }), 500

@app.route('/api/municipality_borders')
def get_municipality_borders_endpoint():
    """Get municipality borders as GeoJSON"""
    try:
        # Get municipality names from query parameters
        municipality_names = request.args.getlist('municipalities[]')
        
        if not municipality_names:
            # If no municipalities specified, return all borders
            borders = get_municipality_borders()
        else:
            # Filter by specified municipalities
            borders = get_municipality_borders(municipality_names)
        
        return jsonify(borders)
        
    except FileNotFoundError as e:
        return jsonify({"error": f"Shapefile not found: {str(e)}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/geocode')
def geocode_address():
    """Geocode an address using Google Geocoding API"""
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "No address provided"}), 400

    google_api_key = os.getenv('GOOGLE_GEOCODING_API_KEY', 'AIzaSyDitOkTVs4g0ibg_Yt04DQqLaUYlxZ1o30')
    
    search_term = f"{address}, Antioquia, Colombia"
    
    params = {'key': google_api_key, 'address': search_term}
    url = 'https://maps.googleapis.com/maps/api/geocode/json?'
    
    try:
        response = requests.get(url, params)
        result = response.json()
        
        if result['status'] == 'OK':
            location = result['results'][0]['geometry']['location']
            return jsonify({
                "lat": location['lat'],
                "lon": location['lng']
            })
        else:
            return jsonify({"error": result['status']}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/labels', methods=['GET'])
def get_labels():
    """Get all user labels"""
    try:
        labels = UserLabel.query.all()
        return jsonify({
            "labels": [label.to_dict() for label in labels]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/labels', methods=['POST'])
def add_label():
    """Add or update a label for a location"""
    try:
        data = request.json
        location_id = data.get('location_id')
        lat = data.get('lat')
        lon = data.get('lon')
        label = data.get('label')  # 0 or 1
        notes = data.get('notes', '')
        
        if label not in [0, 1]:
            return jsonify({"error": "label (0 or 1) is required"}), 400
        
        location = None
        
        if location_id:
            location = Location.query.get(location_id)
            if not location:
                return jsonify({"error": "Location not found"}), 404
        elif lat is not None and lon is not None:
            from sqlalchemy import func
            location = Location.query.filter(
                func.abs(Location.lat - float(lat)) < 0.0001,
                func.abs(Location.lon - float(lon)) < 0.0001
            ).first()
            
            if not location:
                nearby = Location.query.filter(
                    func.abs(Location.lat - float(lat)) < 0.01,
                    func.abs(Location.lon - float(lon)) < 0.01
                ).first()
                
                # Try to find the closest municipality from shapefile if available
                municipio_name = None
                if nearby:
                    municipio_name = nearby.municipio
                else:
                    # Try to find municipality from shapefile based on coordinates
                    try:
                        from municipality_borders import load_municipality_borders
                        import geopandas as gpd
                        from shapely.geometry import Point
                        gdf = load_municipality_borders()
                        point = Point(float(lon), float(lat))
                        # Find which municipality contains this point
                        containing = gdf[gdf.geometry.contains(point)]
                        if len(containing) > 0:
                            municipio_name = containing.iloc[0]['MPIO_CNMBR']
                    except Exception:
                        pass
                
                location = Location(
                    lat=float(lat),
                    lon=float(lon),
                    municipio=municipio_name if municipio_name else 'Unknown',
                    risk_score=None,
                    risk_level='Unknown'
                )
                db.session.add(location)
                db.session.flush()
        else:
            return jsonify({"error": "Either location_id or (lat, lon) coordinates are required"}), 400
        
        existing_label = UserLabel.query.filter_by(location_id=location.id).first()
        
        if existing_label:
            # Check if label is being changed from 1 to 0
            old_label = existing_label.label
            existing_label.label = label
            existing_label.notes = notes
            existing_label.updated_at = datetime.utcnow()
            
            # If changing from 1 to 0, remove the confirmed event
            if old_label == 1 and label == 0:
                _remove_confirmed_event_from_label(location.id)
            
            db.session.commit()
            
            if label == 1:
                _ensure_confirmed_event(location.id, location)
            
            return jsonify(existing_label.to_dict())
        else:
            new_label = UserLabel(location_id=location.id, label=label, notes=notes)
            db.session.add(new_label)
            db.session.commit()
            
            if label == 1:
                _ensure_confirmed_event(location.id, location)
            
            return jsonify(new_label.to_dict()), 201
            
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/labels/<int:location_id>', methods=['DELETE'])
def delete_label(location_id):
    """Delete a label for a location"""
    try:
        label = UserLabel.query.filter_by(location_id=location_id).first()
        if not label:
            return jsonify({"error": "Label not found"}), 404
        
        if label.label == 1:
            confirmed_event = ConfirmedEvent.query.filter_by(
                location_id=location_id,
                source='user_label'
            ).first()
            if confirmed_event:
                db.session.delete(confirmed_event)
        
        db.session.delete(label)
        db.session.commit()
        
        return jsonify({"message": "Label deleted successfully"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/confirmed_events', methods=['GET'])
def get_confirmed_events():
    """Get all confirmed events, optionally filtered by municipio"""
    try:
        municipio = request.args.get('municipio')
        query = ConfirmedEvent.query
        
        if municipio:
            query = query.filter_by(municipio=municipio)
        
        events = query.order_by(
            ConfirmedEvent.event_date.desc() if ConfirmedEvent.event_date 
            else ConfirmedEvent.created_at.desc()
        ).all()
        
        return jsonify({"confirmed_events": [event.to_dict() for event in events]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/confirmed_events', methods=['POST'])
def add_confirmed_event():
    """Add a new confirmed event"""
    try:
        data = request.json
        lat = data.get('lat')
        lon = data.get('lon')
        municipio = data.get('municipio')
        
        if not all([lat, lon, municipio]):
            return jsonify({"error": "lat, lon, and municipio are required"}), 400
        
        event = ConfirmedEvent(
            lat=float(lat),
            lon=float(lon),
            municipio=municipio,
            departamento=data.get('departamento'),
            event_date=datetime.fromisoformat(data['event_date']) if data.get('event_date') else None,
            description=data.get('description', ''),
            source=data.get('source', 'manual'),
            location_id=data.get('location_id')
        )
        
        db.session.add(event)
        db.session.commit()
        
        return jsonify(event.to_dict()), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/confirmed_events/<int:event_id>', methods=['PUT'])
def update_confirmed_event(event_id):
    """Update a confirmed event"""
    try:
        event = ConfirmedEvent.query.get(event_id)
        if not event:
            return jsonify({"error": "Event not found"}), 404
        
        data = request.json
        
        if 'lat' in data:
            event.lat = float(data['lat'])
        if 'lon' in data:
            event.lon = float(data['lon'])
        if 'municipio' in data:
            event.municipio = data['municipio']
        if 'departamento' in data:
            event.departamento = data['departamento']
        if 'event_date' in data:
            event.event_date = datetime.fromisoformat(data['event_date']) if data['event_date'] else None
        if 'description' in data:
            event.description = data['description']
        if 'source' in data:
            event.source = data['source']
        
        event.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify(event.to_dict())
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/confirmed_events/<int:event_id>', methods=['DELETE'])
def delete_confirmed_event(event_id):
    """Delete a confirmed event"""
    try:
        event = ConfirmedEvent.query.get(event_id)
        if not event:
            return jsonify({"error": "Event not found"}), 404
        
        db.session.delete(event)
        db.session.commit()
        
        return jsonify({"message": "Event deleted successfully"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/locations/<int:location_id>', methods=['PUT'])
def update_location(location_id):
    """Update a location's risk score and other data"""
    try:
        location = Location.query.get(location_id)
        if not location:
            return jsonify({"error": "Location not found"}), 404
        
        data = request.json
        
        if 'risk_score' in data:
            location.risk_score = float(data['risk_score']) if data['risk_score'] is not None else None
        if 'risk_score_lr' in data:
            location.risk_score_lr = float(data['risk_score_lr']) if data['risk_score_lr'] is not None else None
        if 'risk_level' in data:
            location.risk_level = data['risk_level']
        if 'municipio' in data:
            location.municipio = data['municipio']
        if 'elevation' in data:
            location.elevation = float(data['elevation']) if data['elevation'] is not None else None
        if 'rainfall' in data:
            location.rainfall = float(data['rainfall']) if data['rainfall'] is not None else None
        if 'temperature' in data:
            location.temperature = float(data['temperature']) if data['temperature'] is not None else None
        if 'population_2012' in data:
            location.population_2012 = float(data['population_2012']) if data['population_2012'] is not None else None
        if 'hist_mines' in data:
            location.hist_mines = float(data['hist_mines']) if data['hist_mines'] is not None else None
        
        location.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify(location.to_dict())
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/locations/bulk_update', methods=['POST'])
def bulk_update_locations():
    """Bulk update locations with new risk scores for re-running predictions"""
    try:
        data = request.json
        locations_data = data.get('locations', [])
        
        if not locations_data:
            return jsonify({"error": "No locations provided"}), 400
        
        updated_count = 0
        for loc_data in locations_data:
            location_id = loc_data.get('id')
            if not location_id:
                continue
            
            location = Location.query.get(location_id)
            if not location:
                continue
            
            if 'risk_score' in loc_data:
                location.risk_score = float(loc_data['risk_score']) if loc_data['risk_score'] is not None else None
            if 'risk_score_lr' in loc_data:
                location.risk_score_lr = float(loc_data['risk_score_lr']) if loc_data['risk_score_lr'] is not None else None
            if 'risk_level' in loc_data:
                location.risk_level = loc_data['risk_level']
            if 'municipio' in loc_data:
                location.municipio = loc_data['municipio']
            
            location.updated_at = datetime.utcnow()
            updated_count += 1
        
        db.session.commit()
        
        return jsonify({
            "message": f"Successfully updated {updated_count} locations",
            "updated_count": updated_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


def distance_to_closest_point(grid, points_of_interest):
    """
    Calculate distance to closest point of interest for each grid point.
    Based on the reference implementation using NearestNeighbors with haversine distance.
    
    Args:
        grid: DataFrame with columns ['LATITUD_Y', 'LONGITUD_X'] (or ['lat', 'lon'])
        points_of_interest: DataFrame with columns ['LATITUD_Y', 'LONGITUD_X'] (or ['lat', 'lon'])
    
    Returns:
        Array of distances in kilometers
    """
    # Normalize column names
    grid_lat_col = 'LATITUDE_Y' if 'LATITUDE_Y' in grid.columns else ('LATITUD_Y' if 'LATITUD_Y' in grid.columns else 'lat')
    grid_lon_col = 'LONGITUDE_X' if 'LONGITUDE_X' in grid.columns else ('LONGITUD_X' if 'LONGITUD_X' in grid.columns else 'lon')
    poi_lat_col = 'LATITUDE_Y' if 'LATITUDE_Y' in points_of_interest.columns else ('LATITUD_Y' if 'LATITUD_Y' in points_of_interest.columns else 'lat')
    poi_lon_col = 'LONGITUDE_X' if 'LONGITUDE_X' in points_of_interest.columns else ('LONGITUD_X' if 'LONGITUD_X' in points_of_interest.columns else 'lon')
    
    # Convert to radians for haversine distance
    grid_coords = np.deg2rad(grid[[grid_lat_col, grid_lon_col]].values)
    poi_coords = np.deg2rad(points_of_interest[[poi_lat_col, poi_lon_col]].values)
    
    # Fit NearestNeighbors
    nbrs = NearestNeighbors(n_neighbors=1, algorithm="ball_tree", metric='haversine')
    nbrs = nbrs.fit(poi_coords)
    
    # Get distance to closest point (multiply by Earth radius in km)
    dist = nbrs.kneighbors(grid_coords)[0] * 6371
    
    return dist.flatten()


def _find_latest_model(model_name='TabCmpt', municipio='blockCV'):
    """
    Find the most recent trained model file.
    
    Returns:
        tuple: (model_path, timestamp) or (None, None) if not found
    """
    experiments_dir = './experiments'
    if not os.path.exists(experiments_dir):
        return None, None
    
    # Find all experiment directories
    exp_dirs = glob.glob(os.path.join(experiments_dir, '*'))
    exp_dirs = [d for d in exp_dirs if os.path.isdir(d)]
    
    if not exp_dirs:
        return None, None
    
    # Sort by modification time (most recent first)
    exp_dirs.sort(key=os.path.getmtime, reverse=True)
    
    # Look for model files in most recent experiments
    for exp_dir in exp_dirs:
        # Try .pth for TabCmpt/MLP
        if model_name in ['TabCmpt', 'MLP']:
            model_path = os.path.join(exp_dir, f'{municipio}.pth')
            if os.path.exists(model_path):
                timestamp = os.path.basename(exp_dir)
                return model_path, timestamp
        # Try .pkl for other models
        else:
            model_path = os.path.join(exp_dir, f'{municipio}.pkl')
            if os.path.exists(model_path):
                timestamp = os.path.basename(exp_dir)
                return model_path, timestamp
    
    return None, None


@app.route('/api/recalculate_and_predict', methods=['POST'])
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
        
        # Get all locations from database - handle case where dist_old_mine column doesn't exist yet
        try:
            all_locations = Location.query.all()
        except Exception as db_error:
            # If dist_old_mine column doesn't exist, use raw SQL to query without it
            if 'dist_old_mine' in str(db_error) or 'UndefinedColumn' in str(db_error):
                print("⚠️  dist_old_mine column not found. Querying without it...")
                # Rollback the failed transaction
                db.session.rollback()
                from sqlalchemy import text
                query = text("""
                    SELECT id, lat, lon, municipio, risk_score, risk_score_lr, risk_level,
                           elevation, rainfall, temperature, population_2012, hist_mines,
                           created_at, updated_at
                    FROM locations
                """)
                result = db.session.execute(query)
                # Convert to Location objects manually
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
                    loc.dist_old_mine = None  # Set to None since column doesn't exist
                    all_locations.append(loc)
            else:
                # Rollback and re-raise if it's a different error
                db.session.rollback()
                raise
        
        if not all_locations:
            return jsonify({"error": "No locations found in database"}), 404
        
        print(f"  Found {len(all_locations)} locations")
        
        # Get all confirmed events
        confirmed_events = ConfirmedEvent.query.all()
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
        distances = distance_to_closest_point(grid_df, poi_df)
        
        # Check if dist_old_mine column exists, if not, add it
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('locations')]
        column_exists = 'dist_old_mine' in columns
        
        if not column_exists:
            print("  Adding dist_old_mine column to database...")
            db.session.execute(text("ALTER TABLE locations ADD COLUMN dist_old_mine FLOAT"))
            db.session.commit()
            print("  ✓ Column added successfully")
            column_exists = True
        
        # Update locations with new distance feature
        # Use bulk update for better performance
        updated_count = 0
        if column_exists:
            # Use bulk update with raw SQL for efficiency
            print("  Updating distances in database...")
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
                updated_count += 1
            
            db.session.commit()
        else:
            # Fallback: update each location object (slower but works)
            for i, location in enumerate(all_locations):
                location.dist_old_mine = float(distances[i])
                updated_count += 1
            db.session.commit()
        
        print(f"✓ Recalculated distances for {len(all_locations)} locations")
        print(f"  Min distance: {distances.min():.4f} km")
        print(f"  Max distance: {distances.max():.4f} km")
        print(f"  Mean distance: {distances.mean():.4f} km")
        
        # Find and load trained model
        model_path, timestamp = _find_latest_model(model_name, municipio)
        if not model_path:
            return jsonify({
                "message": "Distances recalculated successfully, but no trained model found for re-prediction.",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "note": "Please train a model first using the retrain endpoint."
            }), 200
        
        print(f"  Found model: {model_path}")
        
        # Load model and make predictions
        # This is a simplified version - you may need to adjust based on your model structure
        try:
            # Import model classes
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            from dataset_db import EventDB
            from save_predictions_db import save_predictions_to_db_orm
            
            # Load dataset with updated dist_old_mine
            # For prediction, we need all locations, so use a dummy validation municipio
            print("  Loading dataset with updated features...")
            train_municipios = ['BOLÍVAR', 'MURINDÓ', 'PUERTO LIBERTADOR']  # Default training set
            val_municipio = municipio.upper() if municipio != 'blockCV' else 'BOLÍVAR'
            
            # Create dataset for all locations (we'll predict on all)
            # Note: This is a simplified approach - you may need to adjust based on your data structure
            all_data = EventDB(
                train_municipios=train_municipios,
                val_municipio=val_municipio,
                subset=subset,
                split='val',
                db_url=DATABASE_URL
            )
            
            # Load model based on type
            if model_name in ['TabCmpt', 'MLP']:
                if not TORCH_AVAILABLE:
                    raise ImportError("PyTorch is required for TabCmpt/MLP models. Please install torch.")
                
                from reland import RELand
                from model import TabCmpt, MLP
                import argparse
                
                # Create args object
                class Args:
                    def __init__(self, obj, ts):
                        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
                        self.objective = obj
                        self.model = model_name
                        self.n_step = 2
                        self.lr = 0.01
                        self.step_size = 75
                        self.gamma = 0.1
                        self.lambda_l2 = 5e-4
                        self.epochs = 500
                        self.batch_size = 2048
                        self.num_workers = 4
                        self.timestamp = ts
                
                args = Args(objective, timestamp)
                model = RELand(all_data.tabX.shape[1], args)
                model.model.load_state_dict(torch.load(model_path, map_location=args.device))
                
                # Make predictions
                print("  Making predictions...")
                predictions = model.predict_proba(test_dataset=all_data)
                predictions = predictions[4]  # Get the probability array
                
            elif model_name == 'TabNet':
                import pytorch_tabnet.tab_model as erm_tab_model
                import pytorch_tabnet_irm.tab_model as irm_tab_model
                
                if objective == 'irm':
                    model = irm_tab_model.TabNetClassifier(seed=737, n_steps=2)
                else:
                    model = erm_tab_model.TabNetClassifier(seed=737, n_steps=2)
                
                model.load_model(model_path)
                predictions = model.predict_proba(all_data.tabX)[:, 1]
                
            else:
                # For sklearn models (LR, RF, etc.)
                import pickle
                with open(model_path, 'rb') as f:
                    model = pickle.load(f)
                predictions = model.predict_proba(all_data.tabX)[:, 1]
            
            # Create predictions DataFrame
            predictions_df = pd.DataFrame({
                'LONGITUD_X': all_data.locations[:, 0],
                'LATITUD_Y': all_data.locations[:, 1],
                'predicted_proba': predictions
            })
            
            # Save predictions to database
            print("  Saving predictions to database...")
            from save_predictions_db import save_predictions_to_db_orm
            save_predictions_to_db_orm(predictions_df, db.session, Location)
            
            print(f"✓ Re-prediction completed successfully")
            
            return jsonify({
                "message": "Distances recalculated and predictions updated successfully",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "predictions_count": len(predictions_df),
                "model_used": model_path
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
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Error in recalculate_and_predict: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/retrain_model', methods=['POST'])
def retrain_model():
    """
    Retrain the model with updated labels and confirmed events.
    This submits a background job and returns immediately.
    Use /api/job_status/<job_id> to check progress.
    """
    try:
        if not task_queue:
            return jsonify({
                "error": "Background job queue not available",
                "message": "Redis is not configured. Set REDIS_URL environment variable."
            }), 503
        
        data = request.json or {}
        municipio = data.get('municipio', 'blockCV')
        subset = data.get('subset', 'full')
        model_name = data.get('model', 'TabCmpt')
        objective = data.get('objective', 'irm')
        n_step = data.get('n_step', 2)
        
        print(f"🔄 Submitting model training job...")
        print(f"  Municipio: {municipio}")
        print(f"  Subset: {subset}")
        print(f"  Model: {model_name}")
        print(f"  Objective: {objective}")
        
        # Import task function
        from tasks import train_model_task
        
        # Submit job to queue
        job = task_queue.enqueue(
            train_model_task,
            municipio=municipio,
            subset=subset,
            model_name=model_name,
            objective=objective,
            n_step=n_step,
            db_url=DATABASE_URL,
            job_timeout=3600,  # 1 hour timeout
            result_ttl=86400   # Keep results for 24 hours
        )
        
        return jsonify({
            "message": "Model training job submitted successfully",
            "job_id": job.id,
            "status": "queued",
            "status_url": f"/api/job_status/{job.id}"
        }), 202
        
        # First, recalculate distances if confirmed events exist
        confirmed_events = ConfirmedEvent.query.all()
        if len(confirmed_events) > 0:
            print("  Recalculating distances first...")
            # Handle case where dist_old_mine column doesn't exist yet
            try:
                all_locations = Location.query.all()
            except Exception as db_error:
                # If dist_old_mine column doesn't exist, use raw SQL to query without it
                if 'dist_old_mine' in str(db_error) or 'UndefinedColumn' in str(db_error):
                    print("  ⚠️  dist_old_mine column not found. Querying without it...")
                    db.session.rollback()
                    from sqlalchemy import text
                    query = text("""
                        SELECT id, lat, lon, municipio, risk_score, risk_score_lr, risk_level,
                               elevation, rainfall, temperature, population_2012, hist_mines,
                               created_at, updated_at
                        FROM locations
                    """)
                    result = db.session.execute(query)
                    # Convert to Location objects manually
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
                # Check if dist_old_mine column exists, if not, add it
                from sqlalchemy import text, inspect
                inspector = inspect(db.engine)
                columns = [col['name'] for col in inspector.get_columns('locations')]
                column_exists = 'dist_old_mine' in columns
                
                if not column_exists:
                    print("  Adding dist_old_mine column to database...")
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
                
                # Use bulk update for better performance
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
                print("  ✓ Distances recalculated")
        
        # Generate timestamp for this training run
        timestamp = datetime.now().strftime("%m%d%Y%H%M%S")
        
        # Create experiments directory if it doesn't exist
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        experiments_dir = os.path.join(script_dir, 'experiments')
        os.makedirs(experiments_dir, exist_ok=True)
        os.makedirs(os.path.join(experiments_dir, timestamp), exist_ok=True)
        
        # Prepare command to run main.py
        main_script = os.path.join(script_dir, 'main.py')
        
        if not os.path.exists(main_script):
            return jsonify({
                "error": f"main.py not found at {main_script}"
            }), 404
        
        # Verify train_val_stream directory exists
        train_val_dir = os.path.join(script_dir, 'train_val_stream', municipio)
        if not os.path.exists(train_val_dir):
            return jsonify({
                "error": f"Train/val split directory not found: {train_val_dir}",
                "available_directories": [d for d in os.listdir(os.path.join(script_dir, 'train_val_stream')) if os.path.isdir(os.path.join(script_dir, 'train_val_stream', d))]
            }), 404
        
        # Find Python interpreter with ML dependencies (torch, etc.)
        # main.py needs torch and other ML libraries
        # Prefer project-level ML venv, then system Python (avoid backend venv)
        
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
        
        # If ML venv not found or doesn't have torch, try system Python paths
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
        
        # Verify torch is available
        if python_interpreter:
            torch_available = False
            try:
                check_result = subprocess.run(
                    [python_interpreter, '-c', 'import torch; print("OK")'],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                if check_result.returncode == 0:
                    torch_available = True
                    print(f"  ✓ Verified: torch is available")
            except:
                pass
            
            if not torch_available:
                print(f"  ❌ ERROR: torch not found in {python_interpreter}")
                print(f"  Please install torch: {python_interpreter} -m pip install torch")
                return jsonify({
                    "error": "PyTorch (torch) is not installed in the selected Python interpreter",
                    "python_interpreter": python_interpreter,
                    "solution": f"Install torch with: {python_interpreter} -m pip install torch",
                    "note": "The training script requires torch. Install it in the system Python, not the backend venv."
                }), 500
        else:
            return jsonify({
                "error": "Could not find a suitable Python interpreter",
                "note": "Please ensure system Python (not backend venv) is available and has torch installed."
            }), 500
        
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
        
        # Set environment variables for database access
        env = os.environ.copy()
        if DATABASE_URL:
            env['DATABASE_URL'] = DATABASE_URL
        
        print(f"  Running command: {' '.join(cmd)}")
        print(f"  Working directory: {script_dir}")
        print(f"  This may take several minutes...")
        
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
            return jsonify({
                "error": "Model training timed out (exceeded 1 hour)",
                "note": "Training may still be running in the background. Check logs."
            }), 500
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            print(f"  ❌ Training failed with return code {result.returncode}")
            print(f"  STDOUT:\n{result.stdout}")
            print(f"  STDERR:\n{result.stderr}")
            
            # Check for common errors and provide helpful messages
            error_lower = error_msg.lower()
            helpful_hint = None
            
            if 'modulenotfounderror' in error_lower and 'torch' in error_lower:
                helpful_hint = (
                    "PyTorch (torch) is not installed. "
                    "Install it with: pip install torch "
                    "Or install all ML dependencies in your Python environment."
                )
            elif 'modulenotfounderror' in error_lower:
                missing_module = error_msg.split("'")[1] if "'" in error_msg else "unknown module"
                helpful_hint = f"Missing Python module: {missing_module}. Install it with: pip install {missing_module}"
            
            # Try to extract the most relevant error message
            error_lines = error_msg.split('\n')
            relevant_error = '\n'.join(error_lines[-20:])  # Last 20 lines usually contain the error
            
            response_data = {
                "error": "Model training failed",
                "return_code": result.returncode,
                "details": relevant_error[:1000],  # Limit error message length
                "full_stderr": result.stderr[:2000] if result.stderr else None,
                "full_stdout": result.stdout[:2000] if result.stdout else None
            }
            
            if helpful_hint:
                response_data["hint"] = helpful_hint
            
            return jsonify(response_data), 500
        
        print(f"  ✓ Model training completed")
        print(f"  Results saved to: ./experiments/{timestamp}/")
        
        # Try to load and save predictions to database
        try:
            predicted_proba_path = os.path.join(script_dir, f'experiments/{timestamp}/predicted_proba.csv')
            if os.path.exists(predicted_proba_path):
                predictions_df = pd.read_csv(predicted_proba_path)
                from save_predictions_db import save_predictions_to_db_orm
                save_predictions_to_db_orm(predictions_df, db.session, Location)
                print(f"  ✓ Predictions saved to database")
        except Exception as e:
            print(f"  ⚠️  Could not save predictions to database: {str(e)}")
        
        return jsonify({
            "message": "Model retraining completed successfully",
            "timestamp": timestamp,
            "experiment_dir": f"./experiments/{timestamp}/",
            "predictions_saved": os.path.exists(predicted_proba_path) if 'predicted_proba_path' in locals() else False
        }), 200
        
    except Exception as e:
        import traceback
        print(f"Error in retrain_model: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/job_status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Get the status of a background job.
    Returns: queued, started, finished, failed, or not_found
    """
    try:
        if not redis_conn:
            return jsonify({
                "error": "Redis not available",
                "message": "Cannot check job status without Redis"
            }), 503
        
        job = Job.fetch(job_id, connection=redis_conn)
        
        response = {
            "job_id": job.id,
            "status": job.get_status(),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }
        
        # Add progress if available
        if job.meta and 'progress' in job.meta:
            response['progress'] = job.meta['progress']
        
        # Add result if job is finished
        if job.is_finished:
            try:
                result = job.result
                if result:
                    response['result'] = result
            except Exception as e:
                response['result_error'] = str(e)
        
        # Add error if job failed
        if job.is_failed:
            response['error'] = str(job.exc_info) if job.exc_info else "Job failed"
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            "error": "Job not found",
            "message": str(e),
            "job_id": job_id
        }), 404


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """
    List recent jobs in the queue.
    """
    try:
        if not task_queue:
            return jsonify({
                "error": "Background job queue not available"
            }), 503
        
        # Get jobs from different states
        queued_jobs = task_queue.get_jobs()
        started_jobs = task_queue.started_job_registry.get_job_ids()
        finished_jobs = task_queue.finished_job_registry.get_job_ids()
        failed_jobs = task_queue.failed_job_registry.get_job_ids()
        
        jobs = []
        
        # Add queued jobs
        for job in queued_jobs[:10]:  # Limit to 10 most recent
            jobs.append({
                "job_id": job.id,
                "status": "queued",
                "created_at": job.created_at.isoformat() if job.created_at else None
            })
        
        # Add started jobs
        for job_id in started_jobs[:10]:
            try:
                job = Job.fetch(job_id, connection=redis_conn)
                jobs.append({
                    "job_id": job.id,
                    "status": "started",
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "progress": job.meta.get('progress') if job.meta else None
                })
            except:
                pass
        
        # Add finished jobs
        for job_id in finished_jobs[:10]:
            try:
                job = Job.fetch(job_id, connection=redis_conn)
                jobs.append({
                    "job_id": job.id,
                    "status": "finished",
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "ended_at": job.ended_at.isoformat() if job.ended_at else None
                })
            except:
                pass
        
        # Add failed jobs
        for job_id in failed_jobs[:10]:
            try:
                job = Job.fetch(job_id, connection=redis_conn)
                jobs.append({
                    "job_id": job.id,
                    "status": "failed",
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "ended_at": job.ended_at.isoformat() if job.ended_at else None
                })
            except:
                pass
        
        # Sort by created_at (most recent first)
        jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return jsonify({
            "jobs": jobs[:20],  # Return top 20 most recent
            "total_queued": len(queued_jobs),
            "total_started": len(started_jobs),
            "total_finished": len(finished_jobs),
            "total_failed": len(failed_jobs)
        }), 200
        
    except Exception as e:
        import traceback
        print(f"Error listing jobs: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


def _ensure_confirmed_event(location_id, location):
    """Helper function to ensure a confirmed event exists for a location with label=1"""
    existing_event = ConfirmedEvent.query.filter_by(
        location_id=location_id,
        source='user_label'
    ).first()
    
    if not existing_event:
        event = ConfirmedEvent(
            lat=location.lat,
            lon=location.lon,
            municipio=location.municipio,
            source='user_label',
            location_id=location_id,
            description='Confirmed mine event from user label'
        )
        db.session.add(event)
        db.session.commit()


def _remove_confirmed_event_from_label(location_id):
    """Helper function to remove confirmed event when label is changed from 1 to 0"""
    existing_event = ConfirmedEvent.query.filter_by(
        location_id=location_id,
        source='user_label'
    ).first()
    
    if existing_event:
        db.session.delete(existing_event)
        db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Get database stats
        try:
            location_count = Location.query.count()
            area_count = db.session.query(Location.municipio).distinct().count()
            label_count = UserLabel.query.count()
            event_count = ConfirmedEvent.query.count()
        except Exception:
            location_count = area_count = label_count = event_count = 0
        
        print("\n" + "="*50)
        print("🚀 RELand Backend Server")
        print("="*50)
        # Mask password in connection string for security
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        if '@' in db_url:
            # Mask password: postgresql://user:password@host -> postgresql://user:***@host
            parts = db_url.split('@')
            if len(parts) == 2:
                user_part = parts[0].rsplit('/', 1)[0] + '/***'
                db_url_display = user_part + '@' + parts[1]
            else:
                db_url_display = db_url
        else:
            db_url_display = db_url
        print(f"💾 Database: {db_url_display}")
        print(f"📊 Stats: {location_count} locations, {area_count} areas, {label_count} labels, {event_count} events")
        print(f"🌐 Running on: http://localhost:5001")
        print("="*50 + "\n")
    
    app.run(debug=True, port=5001, host='127.0.0.1')