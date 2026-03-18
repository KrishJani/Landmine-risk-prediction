"""
Main Flask application factory for RELand Backend
Refactored to follow SOLID principles with proper separation of concerns
"""
import os
import sys

# Set macOS fork safety BEFORE any imports that might trigger Objective-C
os.environ.setdefault('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', 'YES')

from flask import Flask, jsonify
from flask_cors import CORS
from models import db
from config import config, get_config
from exceptions import RELandException
from routes import api_bp
from routes.health import health_bp


def create_app(config_class=None):
    """
    Application factory pattern for creating Flask app
    
    Args:
        config_class: Optional config class to use (defaults to auto-detection)
        
    Returns:
        Flask application instance
    """
    import sys
    print("[APP] Creating Flask app instance...", file=sys.stdout, flush=True)
    app = Flask(__name__)
    
    # Load configuration
    if config_class:
        if isinstance(config_class, type):
            cfg = config_class()
        else:
            cfg = config_class
        cfg.init_app(app)
    else:
        cfg = get_config()
        cfg.init_app(app)
    
    # Initialize CORS
    CORS(app)
    
    # Initialize database
    db.init_app(app)
    
    # Register blueprints
    print("[APP] Registering blueprints...", file=sys.stdout, flush=True)
    app.register_blueprint(api_bp)
    app.register_blueprint(health_bp)
    print("[APP] Blueprints registered", file=sys.stdout, flush=True)
    print("[APP] Note: If startup hangs at 'Connecting to database', ensure PostgreSQL is running and LOCAL_DATABASE_URL is correct.", file=sys.stdout, flush=True)
    
    # Root endpoint
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
                "/api/locations": "PUT/POST - Update location risk scores",
                "/api/recalculate_and_predict": "POST - Recalculate distances and re-predict",
                "/api/retrain_model": "POST - Retrain model",
                "/api/job_status/<job_id>": "GET - Get training job status",
                "/api/jobs": "GET - List training jobs",
                "/api/jobs/<job_id>/cancel": "POST - Cancel a running or pending job",
                "/api/last_trained_model": "GET - Last trained model (when and name)",
                "/api/export_predictions": "GET - Download prediction data as Excel (.xlsx) or GeoJSON (.geojson?format=geojson)"
            }
        })
    
    # Error handlers
    @app.errorhandler(RELandException)
    def handle_reland_exception(e):
        """Handle RELand custom exceptions"""
        return jsonify(e.to_dict()), e.status_code
    
    @app.errorhandler(404)
    def handle_not_found(e):
        """Handle 404 errors"""
        return jsonify({"error": "Resource not found"}), 404
    
    @app.errorhandler(500)
    def handle_internal_error(e):
        """Handle 500 errors"""
        return jsonify({"error": "Internal server error"}), 500
    
    return app


# Create app instance
# In production, this will use ProductionConfig which requires DATABASE_URL
# Errors will be caught by wsgi.py for better error reporting
app = create_app()

if __name__ == '__main__':
    print("[APP] Entering app context...", file=sys.stdout, flush=True)
    with app.app_context():
        # Create database tables (may hang if PostgreSQL is not running)
        print("[APP] Connecting to database and creating tables...", file=sys.stdout, flush=True)
        db.create_all()
        print("[APP] Database ready.", file=sys.stdout, flush=True)
        
        # Get database stats
        try:
            from models import Location, UserLabel, ConfirmedEvent
            location_count = Location.query.count()
            area_count = db.session.query(Location.municipio).distinct().count()
            label_count = UserLabel.query.count()
            event_count = ConfirmedEvent.query.count()
        except Exception:
            location_count = area_count = label_count = event_count = 0
        
        print("\n" + "="*50)
        print("🚀 RELand Backend Server")
        print("="*50)
        
        # Show which database URL source is being used
        env = os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'local')).lower()
        if env in ['production', 'prod']:
            db_source = "DATABASE_URL (Production/RDS)"
        else:
            if os.getenv('LOCAL_DATABASE_URL'):
                db_source = "LOCAL_DATABASE_URL (Local)"
            else:
                db_source = "DATABASE_URL (Local fallback)"
        
        # Mask password in connection string for security
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        if '@' in db_url:
            parts = db_url.split('@')
            if len(parts) == 2:
                user_part = parts[0].rsplit('/', 1)[0] + '/***'
                db_url_display = user_part + '@' + parts[1]
            else:
                db_url_display = db_url
        else:
            db_url_display = db_url
        
        print(f"💾 Database ({db_source}): {db_url_display}")
        print(f"📊 Stats: {location_count} locations, {area_count} areas, {label_count} labels, {event_count} events")
        print(f"🌐 Running on: http://localhost:{config.PORT}")
        print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
