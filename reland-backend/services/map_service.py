"""
Map service for providing map data
"""
from typing import List, Dict, Any
from math import isfinite
from models import Location, UserLabel
from services.location_service import LocationService
from services.event_service import EventService
from utils.risk_calculator import RiskCalculator
from exceptions import DatabaseError


class MapService:
    """Service for map data operations"""
    
    @staticmethod
    def get_map_data(selected_areas: List[str], score_to_use: str = 'risk_score') -> Dict[str, Any]:
        """
        Get map data (risk heatmap and historical points) for selected areas.
        Locations with a user label (0 or 1) show the corresponding color and risk:
        label 0 = mine-free -> Low risk (green); label 1 = confirmed mine -> High risk (red).
        """
        if not selected_areas:
            return {
                "risk_heatmap_points": [],
                "historical_points": [],
                "confirmed_events": []
            }
        
        try:
            # Get locations
            locations = LocationService.get_by_municipios(selected_areas)
            
            if not locations:
                return {
                    "risk_heatmap_points": [],
                    "historical_points": [],
                    "confirmed_events": []
                }
            
            # Get user labels for these locations so labeled points show correct color/risk
            location_ids = [loc.id for loc in locations]
            labels_by_location = {
                ul.location_id: ul.label
                for ul in UserLabel.query.filter(UserLabel.location_id.in_(location_ids)).all()
            }
            
            # Calculate risk levels from model (used when no user label)
            risk_levels = RiskCalculator.calculate_risk_levels(locations, score_to_use)
            
            # Build risk points: override risk/color for locations that have a user label
            risk_points = []
            for location in locations:
                user_label = labels_by_location.get(location.id)
                if user_label is not None:
                    # User label 0 = mine-free -> Low; label 1 = confirmed mine -> High
                    if user_label == 0:
                        risk_level = 'Low'
                        risk_score = 0.0
                    else:
                        risk_level = 'High'
                        risk_score = 1.0
                else:
                    risk_level = risk_levels.get(location.id, 'Low')
                    risk_score = getattr(location, score_to_use, None) or location.risk_score_lr
                    if risk_score is None or not isfinite(risk_score):
                        risk_score = 0.0
                    risk_score = float(risk_score)
                
                risk_points.append({
                    'LATITUD_Y': location.lat,
                    'LONGITUD_X': location.lon,
                    'risk_score': float(risk_score),
                    'risk_level': risk_level,
                    'color': RiskCalculator.get_color_for_risk_level(risk_level),
                    'location_id': location.id,
                    'Municipio': location.municipio
                })
            
            # Build historical points
            historical_points = []
            for loc in locations:
                if loc.hist_mines is not None and loc.hist_mines > 0:
                    try:
                        historical_points.append({
                            'LATITUD_Y': loc.lat,
                            'LONGITUD_X': loc.lon,
                            'hist_mines': float(loc.hist_mines),
                            'hist_color': 'purple'
                        })
                    except (ValueError, TypeError):
                        continue
            
            # Get confirmed events
            try:
                confirmed_events = EventService.get_all()
            except Exception:
                confirmed_events = []
            
            return {
                "risk_heatmap_points": risk_points,
                "historical_points": historical_points,
                "confirmed_events": [event.to_dict() for event in confirmed_events]
            }
        except Exception as e:
            raise DatabaseError(f"Failed to get map data: {str(e)}")
