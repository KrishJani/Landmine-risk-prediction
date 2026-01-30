"""
Map data routes
"""
from flask import jsonify, request
from routes import api_bp
from services.map_service import MapService
from exceptions import RELandException


@api_bp.route('/map_data', methods=['GET'])
def get_map_data():
    """Get map data (risk heatmap and historical points) from database"""
    try:
        selected_areas = request.args.getlist('areas[]')
        score_to_use = 'risk_score'
        
        map_data = MapService.get_map_data(selected_areas, score_to_use)
        return jsonify(map_data)
    except RELandException as e:
        return jsonify({
            "error": e.message,
            "risk_heatmap_points": [],
            "historical_points": [],
            "confirmed_events": []
        }), e.status_code
    except Exception as e:
        return jsonify({
            "error": f"Error fetching map data: {str(e)}",
            "risk_heatmap_points": [],
            "historical_points": [],
            "confirmed_events": []
        }), 500
