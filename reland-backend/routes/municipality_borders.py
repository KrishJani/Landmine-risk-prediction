"""
Municipality borders routes
"""
from flask import jsonify, request
from routes import api_bp

# Try to import municipality borders module
try:
    from municipality_borders import get_municipality_borders, get_all_municipality_names
    MUNICIPALITY_BORDERS_AVAILABLE = True
except (ImportError, FileNotFoundError):
    MUNICIPALITY_BORDERS_AVAILABLE = False
    get_municipality_borders = None
    get_all_municipality_names = None


@api_bp.route('/municipality_borders', methods=['GET'])
def get_municipality_borders_endpoint():
    """Get municipality borders as GeoJSON"""
    if not MUNICIPALITY_BORDERS_AVAILABLE:
        return jsonify({"error": "Municipality borders feature not available"}), 503
    
    try:
        municipality_names = request.args.getlist('municipalities[]')
        
        if not municipality_names:
            borders = get_municipality_borders()
        else:
            borders = get_municipality_borders(municipality_names)
        
        return jsonify(borders)
    except FileNotFoundError as e:
        return jsonify({"error": f"Shapefile not found: {str(e)}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
