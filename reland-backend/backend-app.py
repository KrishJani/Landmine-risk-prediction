import os
import sys
# Set macOS fork safety BEFORE any imports that might trigger Objective-C
# This must be set before any imports to prevent fork() crashes on macOS
os.environ.setdefault('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', 'YES')

import requests
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timezone
from math import isfinite
from dotenv import load_dotenv
from models import db, Location, UserLabel, ConfirmedEvent, TrainingJob

# Optional municipality borders import (may fail if shapefile missing)
try:
    from municipality_borders import get_municipality_borders, get_all_municipality_names
    MUNICIPALITY_BORDERS_AVAILABLE = True
except (ImportError, FileNotFoundError) as e:
    print(f"⚠️  Warning: municipality_borders not available ({str(e)}). Municipality endpoints will not work.", file=sys.stdout, flush=True)
    MUNICIPALITY_BORDERS_AVAILABLE = False
    get_municipality_borders = None
    get_all_municipality_names = None
import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
import subprocess
import glob

# Redis/RQ removed - using database-based async job queue for cost optimization

# Optional imports for model prediction (only needed when recalculating predictions)
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Load environment variables from .env file
# Always load .env for local development; override=False so real env vars win
load_dotenv(override=False)

app = Flask(__name__)
CORS(app)

# Database configuration - PostgreSQL
# Behavior:
# - Local (default): LOCAL_DATABASE_URL is required (no fallback to production DATABASE_URL)
# - Production (FLASK_ENV/ENVIRONMENT == production/prod): require DATABASE_URL (RDS)
env = os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'local')).lower()
if env in ['production', 'prod']:
    # Production mode: use DATABASE_URL only (must be set by platform / AWS)
    DATABASE_URL = os.getenv('DATABASE_URL')
    db_source = "DATABASE_URL (Production/RDS)"
    if not DATABASE_URL:
        raise ValueError(
            "DATABASE_URL environment variable is required in production. "
            "Please set it in your deployment platform (AWS App Runner, Docker, etc.)."
        )
else:
    # Local mode: ONLY use LOCAL_DATABASE_URL (never touch production DATABASE_URL)
    DATABASE_URL = os.getenv('LOCAL_DATABASE_URL')
    if not DATABASE_URL:
        # Fallback to default localhost connection (not production)
        DATABASE_URL = 'postgresql://reland_user:reland_password123@localhost:5432/reland_db'
        db_source = "Default localhost (Local)"
        print("⚠️  WARNING: LOCAL_DATABASE_URL not set, using default localhost connection.", file=sys.stdout, flush=True)
        print("   Set LOCAL_DATABASE_URL in .env for explicit local database configuration.", file=sys.stdout, flush=True)
    else:
        db_source = "LOCAL_DATABASE_URL (Local)"

# Log which database we're using (mask password)
print(f"💾 Database source: {db_source}", file=sys.stdout, flush=True)
if '@' in DATABASE_URL:
    parts = DATABASE_URL.split('@')
    if len(parts) == 2:
        user_part = parts[0].rsplit('/', 1)[0] + '/***'
        db_url_display = user_part + '@' + parts[1]
    else:
        db_url_display = DATABASE_URL
else:
    db_url_display = DATABASE_URL
print(f"💾 Database URL: {db_url_display}", file=sys.stdout, flush=True)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Verify connections before using
    'pool_recycle': 300,    # Recycle connections after 5 minutes
    'pool_timeout': 10,     # 10 second timeout for getting connection from pool
    'connect_args': {
        'connect_timeout': 10  # 10 second connection timeout
    }
}

# Initialize database
db.init_app(app)

# Skip table creation on startup to avoid blocking container initialization
# Tables will be created on first database access or can be created manually
print("ℹ️  Skipping database table creation on startup (will be created on first access)", file=sys.stdout, flush=True)
# with app.app_context():
#     try:
#         db.create_all()
#         print("✓ Database tables created/verified", file=sys.stdout, flush=True)
#     except Exception as e:
#         print(f"⚠️  Warning: Could not create tables: {str(e)}", file=sys.stdout, flush=True)

# Using database-based async job queue (no Redis needed for cost optimization)
print("ℹ️  Using database-based async job queue (cost-optimized mode)", file=sys.stdout, flush=True)

# Helper Functions
def calculate_risk_levels(locations, score_column='risk_score'):
    """
    Calculate risk levels for a list of Location objects.
    Uses quantile-based binning: Low = bottom third, Medium = middle third, High = top third.
    """
    if not locations:
        return {}
    scores = []
    for loc in locations:
        score = getattr(loc, score_column, None)
        if score is not None and not (isinstance(score, float) and (score != score or not isfinite(score))):
            scores.append(score)
    if not scores:
        return {loc.id: 'Low' for loc in locations}
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    low_threshold = scores_sorted[n // 3] if n >= 3 else scores_sorted[0]
    high_threshold = scores_sorted[2 * n // 3] if n >= 3 else scores_sorted[-1]
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
    # This endpoint doesn't use database, should respond immediately
    print("Root endpoint called", file=sys.stdout, flush=True)
    try:
        response = jsonify({
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
        print("Root endpoint response prepared", file=sys.stdout, flush=True)
        return response
    except Exception as e:
        print(f"Error in root endpoint: {str(e)}", file=sys.stdout, flush=True)
        import traceback
        print(traceback.format_exc(), file=sys.stdout, flush=True)
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Simple health check endpoint - no database, no imports"""
    return jsonify({"status": "ok"}), 200

@app.route('/api/initial_data')
def get_initial_data():
    """Get list of available areas from database"""
    try:
        # Use raw SQL for faster query
        result = db.session.execute(db.text("SELECT DISTINCT municipio FROM locations WHERE municipio IS NOT NULL AND municipio != 'Unknown' ORDER BY municipio"))
        area_list = [row[0] for row in result if row[0]]
        return jsonify({"areas": area_list})
    except Exception as e:
        print(f"Error in /api/initial_data: {str(e)}", file=sys.stdout, flush=True)
        import traceback
        print(traceback.format_exc(), file=sys.stdout, flush=True)
        return jsonify({"areas": [], "error": str(e)}), 500

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
        
        # User labels: labeled points show correct color/risk (0 = Low, 1 = High)
        location_ids = [loc.id for loc in locations]
        labels_by_location = {
            ul.location_id: ul.label
            for ul in UserLabel.query.filter(UserLabel.location_id.in_(location_ids)).all()
        }
        
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
            user_label = labels_by_location.get(location.id)
            if user_label is not None:
                if user_label == 0:
                    risk_level = 'Low'
                    risk_score = 0.0
                else:
                    risk_level = 'High'
                    risk_score = 1.0
            else:
                risk_level = risk_levels.get(location.id, 'Low')
                risk_score = getattr(location, score_to_use, None) or location.risk_score_lr
                if risk_score is None or not isfinite(risk_score):
                    risk_score = 0.0
                risk_score = float(risk_score)
            
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
    if not MUNICIPALITY_BORDERS_AVAILABLE:
        return jsonify({"error": "Municipality borders feature not available"}), 503
    
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
            location = db.session.get(Location, location_id)
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
            
            # If changing from 1 to 0, remove the confirmed event (if it was auto-created)
            if old_label == 1 and label == 0:
                _remove_confirmed_event_from_label(location.id)
            
            db.session.commit()
            
            # Labels with value 1 are no longer automatically converted to confirmed events
            # Users must manually create confirmed events if needed
            
            return jsonify(existing_label.to_dict())
        else:
            new_label = UserLabel(location_id=location.id, label=label, notes=notes)
            db.session.add(new_label)
            db.session.commit()
            
            # Labels with value 1 are no longer automatically converted to confirmed events
            # Users must manually create confirmed events if needed
            
            return jsonify(new_label.to_dict()), 201
            
    except Exception as e:
        db.session.rollback()
        import traceback
        error_traceback = traceback.format_exc()
        print(f"❌ Error in /api/labels POST: {str(e)}", file=sys.stdout, flush=True)
        print(error_traceback, file=sys.stdout, flush=True)
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
        event = db.session.get(ConfirmedEvent, event_id)
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
        event = db.session.get(ConfirmedEvent, event_id)
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
        location = db.session.get(Location, location_id)
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
            
            location = db.session.get(Location, location_id)
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


def _detect_model_type(model_path):
    """
    Detect the model type (TabCmpt or MLP) by examining the state_dict keys.
    
    Args:
        model_path: Path to the .pth model file
        
    Returns:
        str: 'TabCmpt', 'MLP', or 'unknown'
    """
    if not TORCH_AVAILABLE:
        return 'unknown'
    
    try:
        state_dict = torch.load(model_path, map_location='cpu')
        keys = list(state_dict.keys())
        
        # TabCmpt has these specific keys
        if any('attentive_transformer' in k for k in keys) or any('mlp_steps' in k for k in keys):
            return 'TabCmpt'
        # MLP has simpler structure with 'base' or 'network' or 'fc'
        elif any('base' in k for k in keys) or any('network' in k for k in keys):
            return 'MLP'
        else:
            return 'unknown'
    except Exception as e:
        print(f"  Warning: Could not detect model type: {e}", file=sys.stdout, flush=True)
        return 'unknown'


def _find_latest_model(model_name='TabCmpt', municipio='blockCV'):
    """
    Find the most recent trained model file, ensuring it matches the requested model type.
    
    Returns:
        tuple: (model_path, timestamp, detected_model_type) or (None, None, None) if not found
    """
    # Get the project root directory (parent of reland-backend)
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    experiments_dir = os.path.join(project_root, 'experiments')
    
    # Fallback: also try relative to current working directory
    cwd_experiments = os.path.join(os.getcwd(), 'experiments')
    if not os.path.exists(experiments_dir) and os.path.exists(cwd_experiments):
        experiments_dir = cwd_experiments
    
    if not os.path.exists(experiments_dir):
        return None, None, None
    
    # Find all experiment directories
    exp_dirs = glob.glob(os.path.join(experiments_dir, '*'))
    exp_dirs = [d for d in exp_dirs if os.path.isdir(d)]
    
    if not exp_dirs:
        return None, None, None
    
    # Sort by modification time (most recent first)
    exp_dirs.sort(key=os.path.getmtime, reverse=True)
    
    # Look for model files in most recent experiments
    for exp_dir in exp_dirs:
        if model_name in ['TabCmpt', 'MLP']:
            # First try exact match with municipio name
            model_path = os.path.join(exp_dir, f'{municipio}.pth')
            if os.path.exists(model_path):
                detected_type = _detect_model_type(model_path)
                if detected_type == model_name or detected_type == 'unknown':
                    timestamp = os.path.basename(exp_dir)
                    print(f"  Found model: {os.path.basename(model_path)} (type: {detected_type})", file=sys.stdout, flush=True)
                    return model_path, timestamp, detected_type
            
            # Look for any .pth file in this experiment directory
            pth_files = glob.glob(os.path.join(exp_dir, '*.pth'))
            if pth_files:
                # Sort by modification time and check each one
                pth_files.sort(key=os.path.getmtime, reverse=True)
                for pth_file in pth_files:
                    detected_type = _detect_model_type(pth_file)
                    if detected_type == model_name:
                        timestamp = os.path.basename(exp_dir)
                        print(f"  Found {model_name} model: {os.path.basename(pth_file)}", file=sys.stdout, flush=True)
                        return pth_file, timestamp, detected_type
                
                # If no exact match, use the most recent one (might be wrong type, but we'll handle it)
                model_path = pth_files[0]
                detected_type = _detect_model_type(model_path)
                timestamp = os.path.basename(exp_dir)
                print(f"  Found model: {os.path.basename(model_path)} (type: {detected_type}, requested: {model_name})", file=sys.stdout, flush=True)
                return model_path, timestamp, detected_type
        else:
            # For sklearn models, look for .pkl files
            model_path = os.path.join(exp_dir, f'{municipio}.pkl')
            if os.path.exists(model_path):
                timestamp = os.path.basename(exp_dir)
                return model_path, timestamp, model_name
            
            pkl_files = glob.glob(os.path.join(exp_dir, '*.pkl'))
            if pkl_files:
                pkl_files.sort(key=os.path.getmtime, reverse=True)
                timestamp = os.path.basename(exp_dir)
                return pkl_files[0], timestamp, model_name
    
    return None, None, None


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
        
        # Find and load trained model(s) - use multi-fold averaging when available
        print(f"  Looking for model: {model_name}, municipio: {municipio}", file=sys.stdout, flush=True)
        try:
            from utils.model_finder import ModelFinder
            timestamp, fold_paths = ModelFinder.find_all_fold_models_in_latest_experiment(model_name, municipio)
            if not fold_paths:
                model_path, timestamp, detected_model_type = _find_latest_model(model_name, municipio)
                fold_paths = [model_path] if model_path else []
        except ImportError:
            model_path, timestamp, detected_model_type = _find_latest_model(model_name, municipio)
            fold_paths = [model_path] if model_path else []
        if not fold_paths:
            return jsonify({
                "message": "Distances recalculated successfully, but no trained model found for re-prediction.",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "note": f"Please train a {model_name} model first using the retrain endpoint."
            }), 200
        model_path = fold_paths[0]
        detected_model_type = model_name if model_name not in ['TabCmpt', 'MLP'] else _detect_model_type(model_path)
        print(f"  Found {len(fold_paths)} fold model(s) (experiment: {timestamp})", file=sys.stdout, flush=True)
        
        # Load model and make predictions
        # This is a simplified version - you may need to adjust based on your model structure
        try:
            # Import model classes
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            from dataset_db import EventDB
            from save_predictions_db import save_predictions_to_db_orm, save_predictions_to_db_by_locations
            from sklearn.neighbors import NearestNeighbors
            
            # Load dataset with updated dist_old_mine
            print("  Loading dataset with updated features...")
            train_municipios = ['BOLÍVAR', 'MURINDÓ', 'PUERTO LIBERTADOR']
            val_municipio = 'ALL' if municipio == 'blockCV' else municipio.upper()
            
            all_data = EventDB(
                train_municipios=train_municipios,
                val_municipio=val_municipio,
                subset=subset,
                split='val',
                db_url=DATABASE_URL
            )
            
            # Predict per DB location using nearest-CSV features (one prediction per map point)
            db_lon_lat = np.array([[loc.lon, loc.lat] for loc in all_locations], dtype=np.float64)
            csv_lon_lat = np.column_stack([all_data.locations[:, 0], all_data.locations[:, 1]])
            nn_fit = NearestNeighbors(n_neighbors=1, metric='euclidean')
            nn_fit.fit(csv_lon_lat)
            _, nearest_idx = nn_fit.kneighbors(db_lon_lat)
            nearest_idx = nearest_idx.flatten()
            tabX_db = np.array(all_data.tabX[nearest_idx], dtype=np.float32)
            # Keep scaled lon/lat from nearest CSV row (do NOT overwrite with raw DB coords) so model input matches training scale
            n_db = len(all_locations)
            print(f"  Built feature matrix for {n_db} DB locations (nearest-CSV row per location)", file=sys.stdout, flush=True)
            
            class DBLocationDataset:
                def __init__(self, tabX, locations_xy):
                    self.tabX = tabX
                    self.locations = locations_xy
                    self.y = np.zeros(len(tabX), dtype=np.float32)
                    self.hist_mine = np.zeros(len(tabX), dtype=np.float32)
                def __len__(self):
                    return len(self.tabX)
                def __getitem__(self, idx):
                    return (
                        torch.tensor(self.tabX[idx], dtype=torch.float32),
                        torch.tensor(self.y[idx], dtype=torch.float32),
                        torch.tensor((self.locations[idx, 0], self.locations[idx, 1]), dtype=torch.float32),
                        torch.tensor(self.hist_mine[idx], dtype=torch.float32),
                    )
            db_dataset = DBLocationDataset(tabX_db, db_lon_lat)
            
            # Load model based on type
            if model_name in ['TabCmpt', 'MLP']:
                if not TORCH_AVAILABLE:
                    raise ImportError("PyTorch is required for TabCmpt/MLP models. Please install torch.")
                
                from reland import RELand
                from model import TabCmpt, MLP
                
                actual_model_name = detected_model_type if detected_model_type in ['TabCmpt', 'MLP'] else model_name
                if detected_model_type != model_name and detected_model_type in ['TabCmpt', 'MLP']:
                    print(f"  ⚠️  Warning: Found {detected_model_type} model but requested {model_name}. Using {detected_model_type}.", file=sys.stdout, flush=True)
                
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
                    print(f"  Loading fold {i + 1}/{len(fold_paths)} from: {fold_path}", file=sys.stdout, flush=True)
                    state_dict = torch.load(fold_path, map_location=args.device)
                    missing_keys, unexpected_keys = model.model.load_state_dict(state_dict, strict=False)
                    if (missing_keys or unexpected_keys) and i == 0:
                        if missing_keys:
                            print(f"  ⚠️  Warning: Missing keys in model: {len(missing_keys)} keys", file=sys.stdout, flush=True)
                        if unexpected_keys:
                            print(f"  ⚠️  Warning: Unexpected keys in model: {len(unexpected_keys)} keys", file=sys.stdout, flush=True)
                    pred_result = model.predict_proba(test_dataset=db_dataset)
                    if not isinstance(pred_result, (tuple, list)) or len(pred_result) < 5:
                        raise ValueError(f"Unexpected predictions result from fold {i + 1}")
                    pred = pred_result[4]
                    if pred is None:
                        raise ValueError(f"Predictions array is None for fold {i + 1}")
                    all_preds.append(np.array(pred))
                predictions = np.array(all_preds).mean(axis=0)
                if len(predictions) != n_db:
                    raise ValueError(f"Predictions length ({len(predictions)}) doesn't match DB locations ({n_db})")
                print("  ✓ Predictions averaged over {0} fold(s) (per DB location)".format(len(fold_paths)), file=sys.stdout, flush=True)
                
            elif model_name == 'TabNet':
                import pytorch_tabnet.tab_model as erm_tab_model
                import pytorch_tabnet_irm.tab_model as irm_tab_model
                
                if objective == 'irm':
                    model = irm_tab_model.TabNetClassifier(seed=737, n_steps=2)
                else:
                    model = erm_tab_model.TabNetClassifier(seed=737, n_steps=2)
                
                model.load_model(model_path)
                predictions = model.predict_proba(tabX_db)[:, 1]
                predictions = np.array(predictions)
                if len(predictions) != n_db:
                    raise ValueError(f"Predictions length ({len(predictions)}) doesn't match DB locations ({n_db})")
                
            else:
                # For sklearn models (Lightweight, LR, RF, etc.): average over all folds, predict per DB location
                import pickle
                all_preds = []
                for path in fold_paths:
                    with open(path, 'rb') as f:
                        model = pickle.load(f)
                    all_preds.append(model.predict_proba(tabX_db)[:, 1])
                predictions = np.array(all_preds).mean(axis=0)
                if len(predictions) != n_db:
                    raise ValueError(f"Predictions length ({len(predictions)}) doesn't match DB locations ({n_db})")
            
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
                    blend = 0.5
                    for idx in indices:
                        predictions[idx] = (1 - blend) * float(predictions[idx]) + blend * global_mean
            if constant_municipalities:
                print("  Post-processed {0} constant municipalities (blended with global mean). Tip: retrain with municipio=map_included.".format(len(constant_municipalities)), file=sys.stdout, flush=True)
            
            # Save predictions (one per DB location, quantile-based risk_level)
            print("  Saving predictions to database (one per DB location)...", file=sys.stdout, flush=True)
            save_predictions_to_db_by_locations(all_locations, predictions, db.session, Location, use_quantiles=True)
            
            print(f"✓ Re-prediction completed successfully", file=sys.stdout, flush=True)
            
            return jsonify({
                "message": "Distances recalculated and predictions updated successfully (one prediction per map point)",
                "updated_count": updated_count,
                "confirmed_events_count": len(confirmed_events),
                "predictions_count": n_db,
                "model_used": str(model_path)
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
    Creates a job in the database and triggers worker (asynchronous).
    - Local: spawns local worker subprocess
    - Production: launches EC2 worker instance
    Returns immediately with job_id to prevent timeouts.
    Use /api/job_status/<job_id> to check progress.
    """
    try:
        data = request.json or {}
        municipio = data.get('municipio', 'blockCV')
        subset = data.get('subset', 'full')
        model_name = data.get('model', 'TabCmpt')
        objective = data.get('objective', 'irm')
        n_step = data.get('n_step', 2)
        
        # Asynchronous mode: Create job in database and trigger worker
        # This prevents timeout errors for long-running training jobs (hours)
        print(f"🔄 Creating training job in database (asynchronous mode)...")
        print(f"  Municipio: {municipio}")
        print(f"  Subset: {subset}")
        print(f"  Model: {model_name}")
        print(f"  Objective: {objective}")
        
        # Determine environment: local vs production
        env = os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'local')).lower()
        is_production = env in ['production', 'prod']
        
        # Generate unique job ID
        import uuid
        from datetime import datetime
        job_id = f"train_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # Create job record in database
        job = TrainingJob(
            id=job_id,
            job_type='retrain',
            status='pending',
            municipio=municipio,
            subset=subset,
            model_name=model_name,
            objective=objective,
            n_step=n_step,
            progress=0.0,
            progress_message="Job created..."
        )
        db.session.add(job)
        db.session.commit()
        
        ec2_instance_id = None
        if is_production:
            # Production: Launch EC2 worker instance
            job.progress_message = "Job created, waiting for EC2 worker..."
            db.session.commit()
            try:
                from aws_ec2_helper import trigger_worker_instance
                launch_template_name = os.getenv('EC2_LAUNCH_TEMPLATE_NAME', 'reland-worker-template')
                instance_info = trigger_worker_instance(launch_template_name=launch_template_name)
                
                if instance_info and isinstance(instance_info, dict):
                    ec2_instance_id = instance_info.get('instance_id')
                    if ec2_instance_id:
                        job.ec2_instance_id = ec2_instance_id
                        job.progress_message = f"EC2 worker instance {ec2_instance_id} launched"
                        db.session.commit()
                        print(f"  ✓ EC2 worker instance launched: {ec2_instance_id}")
                    else:
                        raise ValueError("EC2 instance ID not found in response")
                else:
                    raise ValueError("Failed to launch EC2 worker instance")
                    
            except Exception as e:
                print(f"  ⚠️  Error launching EC2 worker: {str(e)}")
                job.progress_message = f"Error launching EC2: {str(e)}"
                job.status = 'failed'
                db.session.commit()
                return jsonify({
                    "error": f"Failed to launch EC2 worker: {str(e)}",
                    "job_id": job_id
                }), 500
        else:
            # Local: Spawn local worker subprocess (log stdout/stderr so we can see failures)
            job.progress_message = "Job created, starting local worker..."
            db.session.commit()
            try:
                # Get path to worker script
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                worker_script = os.path.join(backend_dir, 'ec2_worker_main.py')
                
                if not os.path.exists(worker_script):
                    raise FileNotFoundError(f"Worker script not found: {worker_script}")
                
                # Log worker output to file so predict-per-DB and other errors are visible
                worker_log_dir = os.path.join(backend_dir, 'worker_logs')
                os.makedirs(worker_log_dir, exist_ok=True)
                worker_log_path = os.path.join(worker_log_dir, f'{job_id}.log')
                worker_log_file = open(worker_log_path, 'w')
                worker_log_file.write(f"Worker started for job {job_id} at {datetime.now(timezone.utc).isoformat()}\n")
                worker_log_file.flush()
                
                # Spawn worker subprocess (non-blocking); stdout/stderr go to log file
                subprocess.Popen(
                    [sys.executable, worker_script, '--job-id', job_id],
                    cwd=os.path.dirname(backend_dir),  # Project root
                    env=os.environ.copy(),  # Inherit environment (including LOCAL_DATABASE_URL)
                    stdout=worker_log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True  # Detach from parent
                )
                job.progress_message = "Local worker started"
                db.session.commit()
                print(f"  ✓ Local worker started for job {job_id} (log: {worker_log_path})")
            except Exception as e:
                print(f"  ⚠️  Error starting local worker: {str(e)}")
                job.progress_message = f"Error starting local worker: {str(e)}"
                job.status = 'failed'
                db.session.commit()
                return jsonify({
                    "error": f"Failed to start local worker: {str(e)}",
                    "job_id": job_id
                }), 500
        
        return jsonify({
            "message": "Model training job created successfully",
            "job_id": job_id,
            "status": "pending",
            "ec2_instance_id": ec2_instance_id,
            "status_url": f"/api/job_status/{job_id}"
        }), 202
        
    except Exception as e:
        import traceback
        print(f"Error in retrain_model: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/job_status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    Get the status of a training job from the database.
    Returns: pending, running, completed, failed
    """
    try:
        job = db.session.get(TrainingJob, job_id)
        
        if not job:
            return jsonify({
                "error": "Job not found",
                "job_id": job_id
            }), 404
        
        response = {
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "progress_message": job.progress_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "ec2_instance_id": job.ec2_instance_id
        }
        
        # Add result if job is completed
        if job.status == 'completed' and job.result:
            try:
                response['result'] = json.loads(job.result)
            except (json.JSONDecodeError, TypeError):
                response['result'] = job.result
        
        # Add error if job failed
        if job.status == 'failed':
            response['error'] = job.error_message or "Job failed"
        
        return jsonify(response), 200
        
    except Exception as e:
        import traceback
        print(f"Error in get_job_status: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "error": "Failed to get job status",
            "message": str(e)
        }), 500


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """
    List recent training jobs from the database.
    """
    try:
        # Get recent jobs from database (last 50)
        jobs_query = TrainingJob.query.order_by(TrainingJob.created_at.desc()).limit(50).all()
        
        # Use to_dict method from model for consistency
        jobs = [job.to_dict() for job in jobs_query]
        
        return jsonify({
            "jobs": jobs
        }), 200
        
    except Exception as e:
        import traceback
        print(f"Error in list_jobs: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "error": "Failed to list jobs",
            "message": str(e)
        }), 500


@app.route('/api/last_trained_model', methods=['GET'])
def get_last_trained_model():
    """
    Get when the last model was trained and its name (from most recent completed retrain job).
    """
    try:
        job = (
            TrainingJob.query.filter_by(job_type='retrain', status='completed')
            .order_by(TrainingJob.completed_at.desc())
            .first()
        )
        if not job:
            return jsonify({
                "message": "No model has been trained yet",
                "last_trained_at": None,
                "model_name": None,
                "municipio": None,
                "experiment_dir": None,
                "job_id": None
            }), 200
        result_data = None
        if job.result:
            try:
                result_data = json.loads(job.result)
            except (TypeError, ValueError):
                result_data = None
        experiment_dir = (result_data.get('experiment_dir') if isinstance(result_data, dict) else None) or ''
        return jsonify({
            "last_trained_at": job.completed_at.isoformat() if job.completed_at else None,
            "model_name": job.model_name or 'TabCmpt',
            "municipio": job.municipio or 'blockCV',
            "experiment_dir": experiment_dir,
            "job_id": job.id,
        }), 200
    except Exception as e:
        import traceback
        print(f"Error in get_last_trained_model: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            "error": "Failed to get last trained model",
            "message": str(e)
        }), 500


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
    
    # Use environment variable for port (EB sets PORT automatically)
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)