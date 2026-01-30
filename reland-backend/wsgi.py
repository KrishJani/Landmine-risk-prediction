"""
WSGI entry point for production deployment (App Runner, Gunicorn, etc.)
"""
import sys
import os

print("=" * 70, file=sys.stdout, flush=True)
print("🚀 Starting RELand Backend Application", file=sys.stdout, flush=True)
print("=" * 70, file=sys.stdout, flush=True)

# Print environment info for debugging
print(f"Python version: {sys.version}", file=sys.stdout, flush=True)
print(f"Working directory: {os.getcwd()}", file=sys.stdout, flush=True)
print(f"DATABASE_URL set: {'Yes' if os.getenv('DATABASE_URL') else 'No'}", file=sys.stdout, flush=True)
print(f"AWS_REGION: {os.getenv('AWS_REGION', 'Not set')}", file=sys.stdout, flush=True)
print(f"ENVIRONMENT: {os.getenv('ENVIRONMENT', os.getenv('FLASK_ENV', 'Not set'))}", file=sys.stdout, flush=True)

try:
    # Import the refactored app
    print("📦 Importing Flask app...", file=sys.stdout, flush=True)
    from app import app
    print("✅ Flask app imported successfully", file=sys.stdout, flush=True)
    
    # Show database configuration (masked) for debugging
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')
    if db_url and '@' in db_url:
        parts = db_url.split('@')
        if ':' in parts[0]:
            user_pass = parts[0].split(':', 1)
            db_url_display = f"{user_pass[0]}:***@{parts[1]}"
        else:
            db_url_display = db_url
    else:
        db_url_display = db_url
    
    print(f"💾 Database: {db_url_display}", file=sys.stdout, flush=True)
    print(f"🔧 Environment: {os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'Not set'))}", file=sys.stdout, flush=True)
    
    # Skip database connection test during startup to avoid delays
    # Database will be tested on first actual request
    print("💡 Database connection will be tested on first request", file=sys.stdout, flush=True)
    
    # Verify health endpoint is registered
    try:
        with app.app_context():
            from flask import url_for
            # This will raise BuildError if route doesn't exist
            health_url = url_for('health.health')
            print(f"✅ Health endpoint registered: {health_url}", file=sys.stdout, flush=True)
    except Exception as route_error:
        print(f"⚠️  Warning: Could not verify health route: {route_error}", file=sys.stdout, flush=True)
        # List all registered routes for debugging
        print("Registered routes:", file=sys.stdout, flush=True)
        for rule in app.url_map.iter_rules():
            print(f"  {rule}", file=sys.stdout, flush=True)
    
    print("=" * 70, file=sys.stdout, flush=True)
    print("✅ Application ready to serve requests", file=sys.stdout, flush=True)
    print("=" * 70, file=sys.stdout, flush=True)
    
    # WSGI application
    application = app
    
except Exception as e:
    print("\n" + "=" * 70, file=sys.stderr, flush=True)
    print("❌ FAILED TO LOAD FLASK APP", file=sys.stderr, flush=True)
    print("=" * 70, file=sys.stderr, flush=True)
    print(f"Error: {str(e)}", file=sys.stderr, flush=True)
    print("\nEnvironment variables:", file=sys.stderr, flush=True)
    print(f"  DATABASE_URL: {'Set' if os.getenv('DATABASE_URL') else 'NOT SET'}", file=sys.stderr, flush=True)
    print(f"  FLASK_ENV: {os.getenv('FLASK_ENV', 'Not set')}", file=sys.stderr, flush=True)
    print(f"  ENVIRONMENT: {os.getenv('ENVIRONMENT', 'Not set')}", file=sys.stderr, flush=True)
    print("\nFull traceback:", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)
    print("=" * 70, file=sys.stderr, flush=True)
    raise

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    print(f"\n🌐 Running development server on port {port}", file=sys.stdout, flush=True)
    application.run(host='0.0.0.0', port=port, debug=False)
