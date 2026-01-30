"""
Location management routes
"""
from flask import jsonify, request
from routes import api_bp
from services.location_service import LocationService
from exceptions import RELandException


@api_bp.route('/locations/<int:location_id>', methods=['PUT'])
def update_location(location_id):
    """Update a location's risk score and other data"""
    try:
        data = request.json
        location = LocationService.update(location_id, data)
        return jsonify(location.to_dict())
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/locations/bulk_update', methods=['POST'])
def bulk_update_locations():
    """Bulk update locations with new risk scores"""
    try:
        data = request.json
        locations_data = data.get('locations', [])
        
        if not locations_data:
            return jsonify({"error": "No locations provided"}), 400
        
        updated_count = LocationService.bulk_update(locations_data)
        
        return jsonify({
            "message": f"Successfully updated {updated_count} locations",
            "updated_count": updated_count
        })
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
