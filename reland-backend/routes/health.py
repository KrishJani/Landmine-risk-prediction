"""
Health check routes - optimized for fast response
"""
from flask import jsonify, Blueprint
import time
import sys

health_bp = Blueprint('health', __name__)

# Track startup time
_start_time = time.time()

@health_bp.route('/health', methods=['GET'])
def health():
    """
    Ultra-fast health check endpoint - no database, no imports, minimal processing
    Returns immediately to avoid timeout issues
    """
    # Log health check request (for debugging)
    print(f"[HEALTH] Health check requested at {time.time()}", file=sys.stdout, flush=True)
    
    # Return immediately without any database checks or heavy operations
    response = jsonify({
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time)
    })
    
    print(f"[HEALTH] Health check response sent", file=sys.stdout, flush=True)
    return response, 200

@health_bp.route('/health/ready', methods=['GET'])
def readiness():
    """
    Readiness probe - checks if app is ready to serve traffic
    This can include database connectivity checks if needed
    """
    try:
        # Optional: Add database check here if needed
        # For now, just return ready if app is loaded
        return jsonify({"status": "ready"}), 200
    except Exception as e:
        return jsonify({"status": "not_ready", "error": str(e)}), 503
