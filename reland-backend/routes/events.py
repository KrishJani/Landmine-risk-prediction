"""
Confirmed events routes
"""
from flask import jsonify, request
from routes import api_bp
from services.event_service import EventService
from exceptions import RELandException


@api_bp.route('/confirmed_events', methods=['GET'])
def get_confirmed_events():
    """Get all confirmed events, optionally filtered by municipio"""
    try:
        municipio = request.args.get('municipio')
        events = EventService.get_all(municipio)
        return jsonify({
            "confirmed_events": [event.to_dict() for event in events]
        })
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/confirmed_events', methods=['POST'])
def add_confirmed_event():
    """Add a new confirmed event"""
    try:
        data = request.json
        event = EventService.create(data)
        return jsonify(event.to_dict()), 201
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/confirmed_events/<int:event_id>', methods=['PUT'])
def update_confirmed_event(event_id):
    """Update a confirmed event"""
    try:
        data = request.json
        event = EventService.update(event_id, data)
        return jsonify(event.to_dict())
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/confirmed_events/<int:event_id>', methods=['DELETE'])
def delete_confirmed_event(event_id):
    """Delete a confirmed event"""
    try:
        EventService.delete(event_id)
        return jsonify({"message": "Event deleted successfully"})
    except RELandException as e:
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
