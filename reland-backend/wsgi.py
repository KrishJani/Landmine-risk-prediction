"""
Simple WSGI entry point for App Runner with better error handling.
"""
import sys
import os
import importlib.util

print("=" * 70, file=sys.stdout, flush=True)
print("🚀 Starting RELand Backend Application", file=sys.stdout, flush=True)
print("=" * 70, file=sys.stdout, flush=True)

# Print environment info for debugging
print(f"Python version: {sys.version}", file=sys.stdout, flush=True)
print(f"Working directory: {os.getcwd()}", file=sys.stdout, flush=True)
print(f"DATABASE_URL set: {'Yes' if os.getenv('DATABASE_URL') else 'No'}", file=sys.stdout, flush=True)
print(f"AWS_REGION: {os.getenv('AWS_REGION', 'Not set')}", file=sys.stdout, flush=True)

# Import backend-app.py using importlib (file has hyphen, so standard import won't work)
backend_app_path = os.path.join(os.path.dirname(__file__), 'backend-app.py')

print(f"\n📦 Importing Flask app from: {backend_app_path}", file=sys.stdout, flush=True)

try:
    spec = importlib.util.spec_from_file_location("backend_app", backend_app_path)
    if spec is None:
        raise ImportError(f"Could not load spec for {backend_app_path}")
    
    backend_app_module = importlib.util.module_from_spec(spec)
    sys.modules["backend_app"] = backend_app_module
    
    print("⏳ Executing module...", file=sys.stdout, flush=True)
    spec.loader.exec_module(backend_app_module)
    
    print("✅ Module executed successfully", file=sys.stdout, flush=True)
    
    # Get the Flask app
    app = backend_app_module.app
    application = app
    
    print("✅ Flask app loaded successfully", file=sys.stdout, flush=True)
    print("=" * 70, file=sys.stdout, flush=True)
    
except Exception as e:
    print("\n" + "=" * 70, file=sys.stderr, flush=True)
    print("❌ FAILED TO LOAD FLASK APP", file=sys.stderr, flush=True)
    print("=" * 70, file=sys.stderr, flush=True)
    print(f"Error: {str(e)}", file=sys.stderr, flush=True)
    print("\nFull traceback:", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)
    print("=" * 70, file=sys.stderr, flush=True)
    raise

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    print(f"\n🌐 Running development server on port {port}", file=sys.stdout, flush=True)
    application.run(host='0.0.0.0', port=port, debug=False)
