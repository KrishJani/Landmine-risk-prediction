#!/usr/bin/env python3
import os
import sys
import subprocess
import traceback

# Force unbuffered output for App Runner logs
os.environ['PYTHONUNBUFFERED'] = '1'

print("=" * 70, flush=True)
print("RELand Backend Starting", flush=True)
print("=" * 70, flush=True)

port = os.environ.get('PORT', '8080')
print(f"PORT: {port}", flush=True)
print(f"FLASK_ENV: {os.environ.get('FLASK_ENV', 'Not set')}", flush=True)
print(f"ENVIRONMENT: {os.environ.get('ENVIRONMENT', 'Not set')}", flush=True)
print(f"DATABASE_URL set: {'Yes' if os.environ.get('DATABASE_URL') else 'No'}", flush=True)
if os.environ.get('DATABASE_URL'):
    db_url = os.environ.get('DATABASE_URL')
    # Mask password
    if '@' in db_url:
        parts = db_url.split('@')
        if ':' in parts[0]:
            user_pass = parts[0].split(':', 1)
            masked = f"{user_pass[0]}:***@{parts[1]}"
        else:
            masked = db_url
    else:
        masked = db_url
    print(f"DATABASE_URL: {masked}", flush=True)
print("=" * 70, flush=True)

cmd = [
    'gunicorn',
    f'--bind=0.0.0.0:{port}',
    '--workers=2',
    '--timeout=120',
    '--keep-alive=5',
    '--worker-class=sync',
    '--access-logfile=-',
    '--error-logfile=-',
    '--log-level=info',
    '--capture-output',  # Capture stdout/stderr
    'wsgi:application'
]

print(f"Executing: {' '.join(cmd)}", flush=True)
print("=" * 70, flush=True)

# Verify Gunicorn is available
import shutil
gunicorn_path = shutil.which('gunicorn')
if not gunicorn_path:
    print("❌ ERROR: gunicorn not found in PATH", file=sys.stderr, flush=True)
    print("   Install with: pip install gunicorn", file=sys.stderr, flush=True)
    print("   Falling back to minimal health server...", file=sys.stderr, flush=True)
    # Fallback to minimal server
    os.execvp('python3', ['python3', '/app/minimal_health.py'])
    sys.exit(1)

print(f"✅ Gunicorn found at: {gunicorn_path}", flush=True)

# Test if we can import wsgi before starting Gunicorn
try:
    print("🧪 Testing wsgi import...", flush=True)
    import wsgi
    print("✅ wsgi module imported successfully", flush=True)
except Exception as e:
    print(f"❌ ERROR: Failed to import wsgi: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    print("   Falling back to minimal health server...", file=sys.stderr, flush=True)
    os.execvp('python3', ['python3', '/app/minimal_health.py'])
    sys.exit(1)

sys.stdout.flush()
sys.stderr.flush()

# Execute Gunicorn (this replaces the current process)
# Use execvp to ensure proper signal handling
print("🚀 Starting Gunicorn...", flush=True)
os.execvp(cmd[0], cmd)
