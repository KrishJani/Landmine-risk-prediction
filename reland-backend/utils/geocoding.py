"""
Geocoding service
"""
import requests
from typing import Dict, Optional
from config import config
from exceptions import RELandException


class GeocodingService:
    """Handles geocoding operations"""
    
    GEOCODING_API_URL = 'https://maps.googleapis.com/maps/api/geocode/json'
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize geocoding service
        
        Args:
            api_key: Google Geocoding API key (defaults to config value)
        """
        self.api_key = api_key or config.GOOGLE_GEOCODING_API_KEY
    
    def geocode_address(self, address: str, region: str = 'Antioquia, Colombia') -> Dict[str, float]:
        """
        Geocode an address using Google Geocoding API
        
        Args:
            address: Address to geocode
            region: Region to bias the search (default: 'Antioquia, Colombia')
            
        Returns:
            Dictionary with 'lat' and 'lon' keys
            
        Raises:
            RELandException: If geocoding fails
        """
        if not self.api_key:
            raise RELandException(
                "Google Geocoding API key not configured",
                status_code=500,
                details={'error': 'GOOGLE_GEOCODING_API_KEY not set'}
            )
        
        search_term = f"{address}, {region}"
        
        params = {
            'key': self.api_key,
            'address': search_term
        }
        
        try:
            response = requests.get(self.GEOCODING_API_URL, params=params, timeout=10)
            result = response.json()
            
            if result['status'] == 'OK':
                location = result['results'][0]['geometry']['location']
                return {
                    'lat': location['lat'],
                    'lon': location['lng']
                }
            else:
                raise RELandException(
                    f"Geocoding failed: {result['status']}",
                    status_code=404,
                    details={'status': result['status']}
                )
                
        except requests.RequestException as e:
            raise RELandException(
                f"Geocoding request failed: {str(e)}",
                status_code=500,
                details={'error': str(e)}
            )
