#!/usr/bin/env python3
"""
Verification script to check that all imports and references are correct
Run this to verify the refactored codebase is set up correctly
"""
import sys
import os

def check_imports():
    """Verify all critical imports work"""
    print("=" * 70)
    print("Checking Imports...")
    print("=" * 70)
    
    errors = []
    
    # Core modules
    try:
        from app import app, create_app
        print("✓ app.py")
    except Exception as e:
        errors.append(f"✗ app.py: {e}")
        print(f"✗ app.py: {e}")
    
    try:
        from config import config, get_config, LocalConfig, ProductionConfig
        print("✓ config.py")
    except Exception as e:
        errors.append(f"✗ config.py: {e}")
        print(f"✗ config.py: {e}")
    
    try:
        from exceptions import RELandException, DatabaseError, ValidationError, NotFoundError
        print("✓ exceptions.py")
    except Exception as e:
        errors.append(f"✗ exceptions.py: {e}")
        print(f"✗ exceptions.py: {e}")
    
    try:
        from models import db, Location, UserLabel, ConfirmedEvent, TrainingJob
        print("✓ models.py")
    except Exception as e:
        errors.append(f"✗ models.py: {e}")
        print(f"✗ models.py: {e}")
    
    # Services
    try:
        from services import LocationService, LabelService, EventService, MapService, TrainingService
        print("✓ services/")
    except Exception as e:
        errors.append(f"✗ services/: {e}")
        print(f"✗ services/: {e}")
    
    # Utils
    try:
        from utils import RiskCalculator, DistanceCalculator, ModelFinder, GeocodingService
        print("✓ utils/")
    except Exception as e:
        errors.append(f"✗ utils/: {e}")
        print(f"✗ utils/: {e}")
    
    # Routes
    try:
        from routes import api_bp
        from routes.health import health_bp
        print("✓ routes/")
    except Exception as e:
        errors.append(f"✗ routes/: {e}")
        print(f"✗ routes/: {e}")
    
    # Optional modules
    try:
        from municipality_borders import get_municipality_borders
        print("✓ municipality_borders.py (optional)")
    except Exception as e:
        print(f"⚠ municipality_borders.py: {e} (optional, may not be available)")
    
    try:
        from aws_ec2_helper import trigger_worker_instance
        print("✓ aws_ec2_helper.py")
    except Exception as e:
        errors.append(f"✗ aws_ec2_helper.py: {e}")
        print(f"✗ aws_ec2_helper.py: {e}")
    
    return errors


def check_app_structure():
    """Verify Flask app structure"""
    print("\n" + "=" * 70)
    print("Checking App Structure...")
    print("=" * 70)
    
    errors = []
    
    try:
        from app import create_app
        app = create_app()
        
        # Check blueprints are registered
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        if 'api' not in blueprint_names:
            errors.append("API blueprint not registered")
            print("✗ API blueprint not registered")
        else:
            print("✓ API blueprint registered")
        
        if 'health' not in blueprint_names:
            errors.append("Health blueprint not registered")
            print("✗ Health blueprint not registered")
        else:
            print("✓ Health blueprint registered")
        
        # Check routes are registered
        routes = [str(rule) for rule in app.url_map.iter_rules()]
        expected_routes = [
            '/',
            '/health',
            '/api/initial_data',
            '/api/map_data',
            '/api/labels',
            '/api/confirmed_events',
            '/api/locations',
            '/api/geocode',
            '/api/municipality_borders',
            '/api/retrain_model',
            '/api/jobs',
            '/api/recalculate_and_predict'
        ]
        
        for route in expected_routes:
            if route in routes:
                print(f"✓ Route {route}")
            else:
                # Some routes have parameters, check pattern
                found = any(route.split('<')[0] in r for r in routes)
                if found:
                    print(f"✓ Route {route} (with parameters)")
                else:
                    errors.append(f"Route {route} not found")
                    print(f"✗ Route {route} not found")
        
    except Exception as e:
        errors.append(f"App structure check failed: {e}")
        print(f"✗ App structure check failed: {e}")
        import traceback
        traceback.print_exc()
    
    return errors


def check_config():
    """Verify configuration"""
    print("\n" + "=" * 70)
    print("Checking Configuration...")
    print("=" * 70)
    
    errors = []
    
    try:
        from config import get_config, LocalConfig, ProductionConfig
        
        # Test local config
        os.environ['FLASK_ENV'] = 'local'
        local_config = get_config()
        if isinstance(local_config, LocalConfig):
            print("✓ LocalConfig detection works")
        else:
            errors.append("LocalConfig detection failed")
            print("✗ LocalConfig detection failed")
        
        # Test production config (may fail if DATABASE_URL not set, that's okay)
        os.environ['FLASK_ENV'] = 'production'
        try:
            prod_config = get_config()
            if isinstance(prod_config, ProductionConfig):
                print("✓ ProductionConfig detection works")
            else:
                errors.append("ProductionConfig detection failed")
                print("✗ ProductionConfig detection failed")
        except ValueError:
            print("⚠ ProductionConfig requires DATABASE_URL (expected in production)")
        
        # Reset
        os.environ['FLASK_ENV'] = 'local'
        
    except Exception as e:
        errors.append(f"Config check failed: {e}")
        print(f"✗ Config check failed: {e}")
    
    return errors


def check_services():
    """Verify services have required methods"""
    print("\n" + "=" * 70)
    print("Checking Services...")
    print("=" * 70)
    
    errors = []
    services_to_check = {
        'LocationService': ['get_all', 'get_by_id', 'get_by_municipios', 'update', 'bulk_update'],
        'LabelService': ['get_all', 'get_by_location_id', 'create_or_update', 'delete'],
        'EventService': ['get_all', 'get_by_id', 'create', 'update', 'delete'],
        'MapService': ['get_map_data'],
        'TrainingService': ['create_job', 'get_job', 'list_jobs']
    }
    
    try:
        from services import LocationService, LabelService, EventService, MapService, TrainingService
        
        for service_name, methods in services_to_check.items():
            service = globals()[service_name]
            for method in methods:
                if hasattr(service, method):
                    print(f"✓ {service_name}.{method}()")
                else:
                    errors.append(f"{service_name}.{method}() missing")
                    print(f"✗ {service_name}.{method}() missing")
    
    except Exception as e:
        errors.append(f"Service check failed: {e}")
        print(f"✗ Service check failed: {e}")
    
    return errors


def check_utils():
    """Verify utilities have required methods"""
    print("\n" + "=" * 70)
    print("Checking Utilities...")
    print("=" * 70)
    
    errors = []
    utils_to_check = {
        'RiskCalculator': ['calculate_risk_levels', 'get_color_for_risk_level'],
        'DistanceCalculator': ['distance_to_closest_point'],
        'ModelFinder': ['find_latest_model', 'detect_model_type'],
        'GeocodingService': ['geocode_address']
    }
    
    try:
        from utils import RiskCalculator, DistanceCalculator, ModelFinder, GeocodingService
        
        for util_name, methods in utils_to_check.items():
            util = globals()[util_name]
            for method in methods:
                if hasattr(util, method):
                    print(f"✓ {util_name}.{method}()")
                else:
                    errors.append(f"{util_name}.{method}() missing")
                    print(f"✗ {util_name}.{method}() missing")
    
    except Exception as e:
        errors.append(f"Utility check failed: {e}")
        print(f"✗ Utility check failed: {e}")
    
    return errors


def main():
    """Run all checks"""
    print("\n" + "=" * 70)
    print("RELand Backend - Setup Verification")
    print("=" * 70 + "\n")
    
    all_errors = []
    
    # Run checks
    all_errors.extend(check_imports())
    all_errors.extend(check_app_structure())
    all_errors.extend(check_config())
    all_errors.extend(check_services())
    all_errors.extend(check_utils())
    
    # Summary
    print("\n" + "=" * 70)
    print("Verification Summary")
    print("=" * 70)
    
    if all_errors:
        print(f"\n⚠️  Found {len(all_errors)} issue(s):")
        for error in all_errors:
            print(f"  - {error}")
        return 1
    else:
        print("\n✅ All checks passed! The codebase is properly set up.")
        return 0


if __name__ == '__main__':
    sys.exit(main())
