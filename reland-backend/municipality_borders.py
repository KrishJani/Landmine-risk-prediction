"""
Utility module for loading and serving municipality borders from shapefile
"""
import geopandas as gpd
import os
from typing import List, Dict, Optional

# Path to the shapefile
SHAPEFILE_PATH = os.path.join(os.path.dirname(__file__), 'Muncipality Data', 'Municipios.shp')

# Cache for the GeoDataFrame
_municipality_gdf = None


def load_municipality_borders() -> gpd.GeoDataFrame:
    """
    Load municipality borders from shapefile.
    Returns a GeoDataFrame with municipality polygons.
    """
    global _municipality_gdf
    
    if _municipality_gdf is None:
        if not os.path.exists(SHAPEFILE_PATH):
            raise FileNotFoundError(f"Shapefile not found at {SHAPEFILE_PATH}")
        
        _municipality_gdf = gpd.read_file(SHAPEFILE_PATH)
        
        # Ensure CRS is WGS84 (EPSG:4326) for web mapping
        if _municipality_gdf.crs is None:
            _municipality_gdf.set_crs(epsg=4326, inplace=True)
        elif _municipality_gdf.crs.to_string() != 'EPSG:4326':
            _municipality_gdf = _municipality_gdf.to_crs(epsg=4326)
    
    return _municipality_gdf


def get_municipality_borders(municipality_names: Optional[List[str]] = None) -> Dict:
    """
    Get municipality borders as GeoJSON.
    
    Args:
        municipality_names: Optional list of municipality names to filter.
                           If None, returns all municipalities.
    
    Returns:
        GeoJSON FeatureCollection dictionary
    """
    gdf = load_municipality_borders()
    
    # Filter by municipality names if provided
    if municipality_names:
        # Normalize names for comparison (case-insensitive, remove accents/diacritics)
        import unicodedata
        import pandas as pd
        
        def normalize_name(name, remove_suffixes=False):
            """Normalize name for comparison"""
            if not name:
                return ""
            # Convert to lowercase and strip
            normalized = name.lower().strip()
            # Remove accents/diacritics
            normalized = unicodedata.normalize('NFD', normalized)
            normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
            # Only remove suffixes if explicitly requested (for partial matching)
            if remove_suffixes:
                normalized = normalized.replace(' de indias', '').replace(' del chaira', '')
                normalized = normalized.replace(' de ', ' ').replace(' del ', ' ')
            return normalized
        
        def match_single_municipality(municipality_name):
            """Match a single municipality name and return a mask"""
            # First try exact match (without removing suffixes)
            name_normalized = normalize_name(municipality_name, remove_suffixes=False)
            gdf_normalized = gdf['MPIO_CNMBR'].apply(lambda x: normalize_name(x, remove_suffixes=False))
            mask = gdf_normalized == name_normalized
            
            # If no exact match, try with suffix removal for partial matching
            if not mask.any():
                name_normalized = normalize_name(municipality_name, remove_suffixes=True)
                gdf_normalized = gdf['MPIO_CNMBR'].apply(lambda x: normalize_name(x, remove_suffixes=True))
                suffix_mask = gdf_normalized == name_normalized
                
                # If multiple matches after suffix removal, prefer shortest name
                if suffix_mask.sum() > 1:
                    candidates_indices = gdf_normalized[suffix_mask].index
                    original_names = gdf.loc[candidates_indices, 'MPIO_CNMBR']
                    shortest_idx = original_names.str.len().idxmin()
                    mask = gdf_normalized.index == shortest_idx
                else:
                    mask = suffix_mask
            
            # If still no match, try partial matching (e.g., "cartagena de indias" matches "cartagena")
            if not mask.any():
                name_normalized = normalize_name(municipality_name, remove_suffixes=True)
                gdf_normalized = gdf['MPIO_CNMBR'].apply(lambda x: normalize_name(x, remove_suffixes=True))
                
                # Extract the base name (first word) for better matching
                base_name = name_normalized.split()[0] if name_normalized.split() else name_normalized
                
                # Find candidates that start with the base name
                candidates_mask = gdf_normalized.str.startswith(base_name)
                candidates_indices = gdf_normalized[candidates_mask].index
                
                if len(candidates_indices) == 1:
                    # Only one candidate - use it
                    mask = candidates_mask
                elif len(candidates_indices) > 1:
                    # Multiple candidates - prefer the shortest original name
                    original_names = gdf.loc[candidates_indices, 'MPIO_CNMBR']
                    shortest_idx = original_names.str.len().idxmin()
                    mask = gdf_normalized.index == shortest_idx
                else:
                    # No candidates starting with base name, try contains
                    mask = gdf_normalized.apply(
                        lambda x: base_name in x and len(base_name) >= 4
                    )
            
            return mask
        
        # Process each municipality name separately and combine masks
        combined_mask = pd.Series([False] * len(gdf), index=gdf.index)
        for municipality_name in municipality_names:
            single_mask = match_single_municipality(municipality_name)
            combined_mask = combined_mask | single_mask
        
        filtered_gdf = gdf[combined_mask]
        
        if len(filtered_gdf) == 0:
            # If no matches, return empty FeatureCollection
            return {
                "type": "FeatureCollection",
                "features": []
            }
    else:
        filtered_gdf = gdf
    
    # Convert to GeoJSON
    geojson = filtered_gdf.to_json()
    
    # Parse and return as dict
    import json
    return json.loads(geojson)


def get_all_municipality_names() -> List[str]:
    """
    Get list of all municipality names from the shapefile.
    
    Returns:
        List of municipality names
    """
    gdf = load_municipality_borders()
    names = gdf['MPIO_CNMBR'].dropna().unique().tolist()
    return sorted(names)


def get_municipality_border_by_name(municipality_name: str) -> Optional[Dict]:
    """
    Get border for a single municipality by name.
    
    Args:
        municipality_name: Name of the municipality
    
    Returns:
        GeoJSON Feature dictionary or None if not found
    """
    borders = get_municipality_borders([municipality_name])
    
    if borders['features']:
        return borders['features'][0]
    return None

