"""
Initial data routes
"""
from flask import jsonify
from routes import api_bp
from services.location_service import LocationService
from exceptions import RELandException


@api_bp.route('/initial_data', methods=['GET'])
def get_initial_data():
    """Get list of available areas from database"""
    try:
        area_list = LocationService.get_distinct_municipios()
        return jsonify({"areas": area_list})
    except RELandException as e:
        return jsonify({"areas": [], "error": e.message}), e.status_code
    except Exception as e:
        return jsonify({"areas": [], "error": str(e)}), 500
