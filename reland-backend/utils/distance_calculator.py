"""
Distance calculation utilities
"""
import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
from typing import Union


class DistanceCalculator:
    """Handles distance calculations between points"""
    
    EARTH_RADIUS_KM = 6371.0
    
    @staticmethod
    def distance_to_closest_point(
        grid: pd.DataFrame,
        points_of_interest: pd.DataFrame
    ) -> np.ndarray:
        """
        Calculate distance to closest point of interest for each grid point.
        Uses NearestNeighbors with haversine distance.
        
        Args:
            grid: DataFrame with columns ['LATITUD_Y', 'LONGITUD_X'] (or ['lat', 'lon'])
            points_of_interest: DataFrame with columns ['LATITUD_Y', 'LONGITUD_X'] (or ['lat', 'lon'])
        
        Returns:
            Array of distances in kilometers
        """
        # Normalize column names
        grid_lat_col = DistanceCalculator._get_lat_column(grid.columns)
        grid_lon_col = DistanceCalculator._get_lon_column(grid.columns)
        poi_lat_col = DistanceCalculator._get_lat_column(points_of_interest.columns)
        poi_lon_col = DistanceCalculator._get_lon_column(points_of_interest.columns)
        
        # Convert to radians for haversine distance
        grid_coords = np.deg2rad(grid[[grid_lat_col, grid_lon_col]].values)
        poi_coords = np.deg2rad(points_of_interest[[poi_lat_col, poi_lon_col]].values)
        
        # Fit NearestNeighbors
        nbrs = NearestNeighbors(n_neighbors=1, algorithm="ball_tree", metric='haversine')
        nbrs = nbrs.fit(poi_coords)
        
        # Get distance to closest point (multiply by Earth radius in km)
        dist = nbrs.kneighbors(grid_coords)[0] * DistanceCalculator.EARTH_RADIUS_KM
        
        return dist.flatten()
    
    @staticmethod
    def _get_lat_column(columns: Union[pd.Index, list]) -> str:
        """Get latitude column name from available columns"""
        for col in ['LATITUDE_Y', 'LATITUD_Y', 'lat']:
            if col in columns:
                return col
        raise ValueError(f"Latitude column not found. Available columns: {list(columns)}")
    
    @staticmethod
    def _get_lon_column(columns: Union[pd.Index, list]) -> str:
        """Get longitude column name from available columns"""
        for col in ['LONGITUDE_X', 'LONGITUD_X', 'lon']:
            if col in columns:
                return col
        raise ValueError(f"Longitude column not found. Available columns: {list(columns)}")
