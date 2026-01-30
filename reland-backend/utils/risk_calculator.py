"""
Risk calculation utilities
"""
from typing import List, Dict
from math import isfinite
from models import Location


class RiskCalculator:
    """Handles risk level calculations"""
    
    RISK_COLORS = {
        'Low': 'rgb(0, 255, 0)',      # Green
        'Medium': 'rgb(245, 221, 43)', # Yellow
        'High': 'rgb(255, 0, 0)',      # Red
        'Unknown': 'rgb(128, 128, 128)' # Gray
    }
    
    @staticmethod
    def calculate_risk_levels(locations: List[Location], score_column: str = 'risk_score') -> Dict[int, str]:
        """
        Calculate risk levels for a list of Location objects.
        Uses quantile-based binning to categorize into Low/Medium/High.
        
        Args:
            locations: List of Location objects
            score_column: Column name to use for risk score
            
        Returns:
            Dictionary mapping location_id to risk level
        """
        if not locations:
            return {}
        
        # Extract valid scores
        scores = []
        for loc in locations:
            score = getattr(loc, score_column, None)
            if score is not None and not (isinstance(score, float) and (score != score or not isfinite(score))):
                scores.append(score)
        
        if not scores:
            # No valid scores, assign all as Low
            return {loc.id: 'Low' for loc in locations}
        
        # Calculate quantiles
        scores_sorted = sorted(scores)
        n = len(scores_sorted)
        low_threshold = scores_sorted[n // 3] if n >= 3 else scores_sorted[0]
        high_threshold = scores_sorted[2 * n // 3] if n >= 3 else scores_sorted[-1]
        
        # Assign risk levels
        risk_levels = {}
        for loc in locations:
            score = getattr(loc, score_column, None)
            if score is None or (isinstance(score, float) and (score != score or not isfinite(score))):
                risk_levels[loc.id] = 'Low'
            elif score <= low_threshold:
                risk_levels[loc.id] = 'Low'
            elif score <= high_threshold:
                risk_levels[loc.id] = 'Medium'
            else:
                risk_levels[loc.id] = 'High'
        
        return risk_levels
    
    @staticmethod
    def get_color_for_risk_level(risk_level: str) -> str:
        """
        Get color for a risk level
        
        Args:
            risk_level: Risk level string (Low, Medium, High)
            
        Returns:
            RGB color string
        """
        return RiskCalculator.RISK_COLORS.get(risk_level, RiskCalculator.RISK_COLORS['Unknown'])
