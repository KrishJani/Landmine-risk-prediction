"""
Map service for providing map data
"""
from typing import List, Dict, Any
from math import isfinite
from models import Location
from services.location_service import LocationService
from services.event_service import EventService
from utils.risk_calculator import RiskCalculator
from exceptions import DatabaseError


class MapService:
    """Service for map data operations"""
    
    @staticmethod
    def get_map_data(selected_areas: List[str], score_to_use: str = 'risk_score') -> Dict[str, Any]:
        """
        Get map data (risk heatmap and historical points) for selected areas
        
        Args:
            selected_areas: List of municipio names
            score_to_use: Risk score column to use
            
        Returns:
            Dictionary with risk_heatmap_points, historical_points, and confirmed_events
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
            
            # Calculate risk levels
            risk_levels = RiskCalculator.calculate_risk_levels(locations, score_to_use)
            
            # Build risk points
            risk_points = []
            for location in locations:
                risk_level = risk_levels.get(location.id, 'Low')
                risk_score = getattr(location, score_to_use, None) or location.risk_score_lr
                
                # Ensure we have a valid numeric score
                if risk_score is None or not isfinite(risk_score):
                    risk_score = 0.0
                
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
