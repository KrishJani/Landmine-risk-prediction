#!/usr/bin/env python3
"""
Convert municipality shapefile to GeoJSON for static serving.
This script converts the shapefile to GeoJSON format that can be served
as a static asset from the frontend, eliminating the need for backend processing.
"""
import os
import sys
import geopandas as gpd
import json

# Path to the shapefile
SHAPEFILE_PATH = os.path.join(os.path.dirname(__file__), 'Muncipality Data', 'Municipios.shp')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'reland-frontend', 'public', 'municipality_borders.geojson')

def convert_shapefile_to_geojson():
    """Convert shapefile to GeoJSON format"""
    print("Converting municipality shapefile to GeoJSON...")
    
    # Check if shapefile exists
    if not os.path.exists(SHAPEFILE_PATH):
        print(f"❌ Error: Shapefile not found at {SHAPEFILE_PATH}")
        sys.exit(1)
    
    # Load shapefile
    print(f"Loading shapefile from {SHAPEFILE_PATH}...")
    gdf = gpd.read_file(SHAPEFILE_PATH)
    print(f"✓ Loaded {len(gdf)} municipalities")
    
    # Ensure CRS is WGS84 (EPSG:4326) for web mapping
    if gdf.crs is None:
        print("⚠️  No CRS found, setting to WGS84 (EPSG:4326)")
        gdf.set_crs(epsg=4326, inplace=True)
    elif gdf.crs.to_string() != 'EPSG:4326':
        print(f"Converting CRS from {gdf.crs.to_string()} to EPSG:4326...")
        gdf = gdf.to_crs(epsg=4326)
    
    # Convert to GeoJSON
    print("Converting to GeoJSON format...")
    geojson = gdf.to_json()
    
    # Parse and pretty-print for better readability (optional, but helpful)
    geojson_dict = json.loads(geojson)
    
    # Ensure output directory exists
    output_dir = os.path.dirname(OUTPUT_PATH)
    os.makedirs(output_dir, exist_ok=True)
    
    # Write to file
    print(f"Writing GeoJSON to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson_dict, f, ensure_ascii=False, indent=2)
    
    # Get file size
    file_size = os.path.getsize(OUTPUT_PATH)
    file_size_mb = file_size / (1024 * 1024)
    
    print(f"✓ Successfully converted shapefile to GeoJSON")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Features: {len(geojson_dict.get('features', []))}")
    print(f"  File size: {file_size_mb:.2f} MB")
    
    return OUTPUT_PATH

if __name__ == '__main__':
    try:
        convert_shapefile_to_geojson()
        print("\n✓ Conversion complete!")
        print("  The GeoJSON file is now in reland-frontend/public/")
        print("  It will be served as a static asset and can be cached by CDN.")
    except Exception as e:
        print(f"\n❌ Error during conversion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
