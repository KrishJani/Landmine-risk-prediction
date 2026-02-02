#!/usr/bin/env python3
"""
Minimal health check server - use this if main app fails to start
"""
import os
import sys

# Force unbuffered output - MUST be first
os.environ['PYTHONUNBUFFERED'] = '1'

# Log immediately - before any imports
print("=" * 70, file=sys.stdout, flush=True)
print("MINIMAL HEALTH SERVER STARTING", file=sys.stdout, flush=True)
print("=" * 70, file=sys.stdout, flush=True)
print(f"Python: {sys.executable}", file=sys.stdout, flush=True)
print(f"Working dir: {os.getcwd()}", file=sys.stdout, flush=True)
print(f"PORT: {os.environ.get('PORT', 'NOT SET')}", file=sys.stdout, flush=True)
print("=" * 70, file=sys.stdout, flush=True)

try:
    print("Importing Flask...", file=sys.stdout, flush=True)
    from flask import Flask, jsonify
    print("✅ Flask imported successfully", file=sys.stdout, flush=True)
except Exception as e:
    print(f"❌ ERROR importing Flask: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

app = Flask(__name__)
print("✅ Flask app created", file=sys.stdout, flush=True)

@app.route('/health', methods=['GET'])
def health():
    """Ultra-minimal health check"""
    return jsonify({"status": "ok"}), 200

@app.route('/', methods=['GET'])
def root():
    """Root endpoint"""
    return jsonify({"message": "RELand Backend (minimal mode)"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting minimal health server on port {port}", file=sys.stdout, flush=True)
    print(f"Binding to: 0.0.0.0:{port}", file=sys.stdout, flush=True)
    print("=" * 70, file=sys.stdout, flush=True)
    print("Server starting...", file=sys.stdout, flush=True)
    try:
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        print(f"❌ ERROR starting server: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
