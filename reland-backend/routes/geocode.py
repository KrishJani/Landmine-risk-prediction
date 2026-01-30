"""
Geocoding routes
"""
from flask import jsonify, request
from routes import api_bp
from utils.geocoding import GeocodingService
from exceptions import RELandException


@api_bp.route('/geocode', methods=['GET'])
def geocode_address():
    """Geocode an address using Google Geocoding API"""
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "No address provided"}), 400
    
    try:
        geocoding_service = GeocodingService()
        result = geocoding_service.geocode_address(address)
        return jsonify(result)
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
