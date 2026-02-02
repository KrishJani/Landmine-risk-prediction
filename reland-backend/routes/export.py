"""
Export routes - Excel and GeoJSON download of prediction data
"""
import json
from io import BytesIO
from datetime import datetime

from flask import send_file, request, Response
from routes import api_bp
from services.location_service import LocationService
from services.event_service import EventService
from utils.risk_calculator import RiskCalculator
from exceptions import RELandException


def _get_export_data(selected_areas, score_to_use='risk_score'):
    """Fetch locations and events for export. Returns (locations, risk_levels_map, confirmed_events)."""
    if selected_areas:
        locations = LocationService.get_by_municipios(selected_areas)
    else:
        locations = LocationService.get_all()
    risk_levels = RiskCalculator.calculate_risk_levels(locations, score_to_use)
    try:
        confirmed_events = EventService.get_all()
    except Exception:
        confirmed_events = []
    return locations, risk_levels, confirmed_events


def _location_row(loc, risk_level):
    """Build a flat row dict for one location (Excel-friendly)."""
    return {
        'location_id': loc.id,
        'latitude': loc.lat,
        'longitude': loc.lon,
        'municipio': loc.municipio or '',
        'risk_score': loc.risk_score,
        'risk_score_lr': loc.risk_score_lr,
        'risk_level': risk_level or loc.risk_level or '',
        'dist_old_mine_km': loc.dist_old_mine,
        'elevation': loc.elevation,
        'rainfall': loc.rainfall,
        'temperature': loc.temperature,
        'population_2012': loc.population_2012,
        'hist_mines': loc.hist_mines,
        'created_at': loc.created_at.isoformat() if loc.created_at else '',
        'updated_at': loc.updated_at.isoformat() if loc.updated_at else '',
    }


def _event_row(event):
    """Build a flat row dict for one confirmed event (Excel-friendly)."""
    return {
        'event_id': event.id,
        'latitude': event.lat,
        'longitude': event.lon,
        'municipio': event.municipio or '',
        'departamento': event.departamento or '',
        'event_date': event.event_date.strftime('%Y-%m-%d') if event.event_date else '',
        'description': event.description or '',
        'source': event.source or '',
        'location_id': event.location_id,
        'created_at': event.created_at.isoformat() if event.created_at else '',
        'updated_at': event.updated_at.isoformat() if event.updated_at else '',
    }


def _build_geojson(locations, risk_levels, confirmed_events):
    """Build a GeoJSON FeatureCollection from locations and confirmed events."""
    features = []
    for loc in locations:
        risk_level = risk_levels.get(loc.id, loc.risk_level or '') or ''
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [float(loc.lon), float(loc.lat)]
            },
            'properties': {
                'layer': 'prediction',
                'location_id': loc.id,
                'municipio': loc.municipio or '',
                'risk_score': loc.risk_score,
                'risk_score_lr': loc.risk_score_lr,
                'risk_level': risk_level,
                'dist_old_mine_km': loc.dist_old_mine,
                'elevation': loc.elevation,
                'rainfall': loc.rainfall,
                'temperature': loc.temperature,
                'population_2012': loc.population_2012,
                'hist_mines': loc.hist_mines,
                'created_at': loc.created_at.isoformat() if loc.created_at else '',
                'updated_at': loc.updated_at.isoformat() if loc.updated_at else '',
            }
        })
    for event in confirmed_events:
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [float(event.lon), float(event.lat)]
            },
            'properties': {
                'layer': 'confirmed_event',
                'event_id': event.id,
                'municipio': event.municipio or '',
                'departamento': event.departamento or '',
                'event_date': event.event_date.strftime('%Y-%m-%d') if event.event_date else '',
                'description': event.description or '',
                'source': event.source or '',
                'location_id': event.location_id,
                'created_at': event.created_at.isoformat() if event.created_at else '',
                'updated_at': event.updated_at.isoformat() if event.updated_at else '',
            }
        })
    return {'type': 'FeatureCollection', 'features': features}


@api_bp.route('/export_predictions', methods=['GET'])
def export_predictions():
    """
    Download prediction data as Excel (.xlsx) or GeoJSON (.geojson).
    Query params:
      format=geojson | (default: Excel)
      areas[] (optional) - restrict to these municipios; if omitted, export all.
    """
    try:
        selected_areas = request.args.getlist('areas[]')
        score_to_use = request.args.get('score_to_use', 'risk_score')
        export_format = (request.args.get('format') or '').strip().lower()

        locations, risk_levels, confirmed_events = _get_export_data(selected_areas, score_to_use)
        prediction_rows = [_location_row(loc, risk_levels.get(loc.id, loc.risk_level or '')) for loc in locations]
        event_rows = [_event_row(e) for e in confirmed_events]

        if export_format == 'geojson':
            geojson = _build_geojson(locations, risk_levels, confirmed_events)
            filename = f"RELand_predictions_{datetime.utcnow().strftime('%Y-%m-%d_%H%M')}Z.geojson"
            body = json.dumps(geojson, indent=2, ensure_ascii=False)
            return Response(
                body,
                mimetype='application/geo+json',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        # Default: Excel
        try:
            import openpyxl
        except ImportError:
            return {"error": "Excel export not available (openpyxl not installed)"}, 503

        wb = openpyxl.Workbook(write_only=False)
        wb.creator = 'RELand Backend'
        wb.title = 'RELand Predictions'

        # Sheet 1: Predictions
        ws_pred = wb.active
        ws_pred.title = 'Predictions'
        pred_headers = [
            'location_id', 'latitude', 'longitude', 'municipio', 'risk_score', 'risk_score_lr',
            'risk_level', 'dist_old_mine_km', 'elevation', 'rainfall', 'temperature',
            'population_2012', 'hist_mines', 'created_at', 'updated_at'
        ]
        ws_pred.append(pred_headers)
        for row in prediction_rows:
            ws_pred.append([row.get(h, '') for h in pred_headers])

        # Sheet 2: Confirmed Events
        ws_events = wb.create_sheet('Confirmed Events', 1)
        event_headers = [
            'event_id', 'latitude', 'longitude', 'municipio', 'departamento', 'event_date',
            'description', 'source', 'location_id', 'created_at', 'updated_at'
        ]
        ws_events.append(event_headers)
        for row in event_rows:
            ws_events.append([row.get(h, '') for h in event_headers])

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f"RELand_predictions_{datetime.utcnow().strftime('%Y-%m-%d_%H%M')}Z.xlsx"
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except RELandException as e:
        return {"error": e.message}, e.status_code
    except Exception as e:
        return {"error": str(e)}, 500
