import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
from math import isfinite
from dotenv import load_dotenv
from models import db, Location, UserLabel, ConfirmedEvent
from municipality_borders import get_municipality_borders, get_all_municipality_names

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
    
    selected_areas = request.args.getlist('areas[]')
    score_to_use = 'risk_score'
    
    if not selected_areas:
        return jsonify({
            "risk_heatmap_points": [],
            "historical_points": [],
            "confirmed_events": []
        })

    locations = Location.query.filter(Location.municipio.in_(selected_areas)).all()
    
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
    
    historical_points = [
        {
            'LATITUD_Y': loc.lat,
            'LONGITUD_X': loc.lon,
            'hist_mines': float(loc.hist_mines),
            'hist_color': 'purple'
        }
        for loc in locations
        if loc.hist_mines is not None and loc.hist_mines > 0
    ]
    
    try:
        confirmed_events = ConfirmedEvent.query.all()
    except Exception:
        confirmed_events = []
    
    return jsonify({
        "risk_heatmap_points": risk_points,
        "historical_points": historical_points,
        "confirmed_events": [event.to_dict() for event in confirmed_events]
    })

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
            existing_label.label = label
            existing_label.notes = notes
            existing_label.updated_at = datetime.utcnow()
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