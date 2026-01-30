"""
Label management routes
"""
from flask import jsonify, request
from routes import api_bp
from services.label_service import LabelService
from exceptions import RELandException


@api_bp.route('/labels', methods=['GET'])
def get_labels():
    """Get all user labels"""
    try:
        labels = LabelService.get_all()
        return jsonify({
            "labels": [label.to_dict() for label in labels]
        })
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/labels', methods=['POST'])
def add_label():
    """Add or update a label for a location"""
    try:
        data = request.json
        location_id = data.get('location_id')
        existing_label = LabelService.get_by_location_id(location_id) if location_id else None
        label = LabelService.create_or_update(data)
        status_code = 201 if not existing_label else 200
        return jsonify(label.to_dict()), status_code
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/labels/<int:location_id>', methods=['DELETE'])
def delete_label(location_id):
    """Delete a label for a location"""
    try:
        LabelService.delete(location_id)
        return jsonify({"message": "Label deleted successfully"})
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
