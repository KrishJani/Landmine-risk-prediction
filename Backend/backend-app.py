import os
import json
import pandas as pd
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

# --- Initialization ---
app = Flask(__name__)
# CORS is a security feature we need to let our React app (on a different port)
# talk to our Python backend.
CORS(app)

# --- Load Data ONCE ---
# We load the data into memory when the server starts.
# This is much more efficient than loading it on every request.
try:
    # Try to load from local file first, fallback to URL
    local_file = os.path.join(os.path.dirname(__file__), 'website_table.csv')
    if os.path.exists(local_file):
        print(f"Loading data from local file: {local_file}")
        df = pd.read_csv(local_file)
    else:
        print("Local file not found, loading from URL...")
        df = pd.read_csv('https://raw.githubusercontent.com/annawangkkk/minesWeb/main/website_table.csv')
    area_list = df['Municipio'].unique().tolist()
    print(f"✓ Data loaded successfully. Found {len(df)} records and {len(area_list)} areas.")
except Exception as e:
    print(f"✗ Error loading data: {e}")
    df = pd.DataFrame() # Start with an empty DataFrame if loading fails
    area_list = []

# --- Helper Function ---
def get_color_list(df_1_unknow):
    # This logic from your Dash app is moved to the backend
    colorList_custer = ['cyan', 'rgb(245, 221, 43)', 'orangered']
    clusterList = [2, 0, 1]
    
    # Use .loc to avoid SettingWithCopyWarning
    df_1_unknow = df_1_unknow.copy()
    for item in zip(clusterList, colorList_custer):
        df_1_unknow.loc[df_1_unknow['cluster'] == item[0], 'colorBasedCluster'] = item[1]
        
    colorList = ['lightgrey', 'lime', 'red']
    labelList = [-1, 0, 1]
    
    for item in zip(labelList, colorList):
        df_1_unknow.loc[df_1_unknow['mines_outcome'] == item[0], 'colorBasedLabel'] = item[1]
    
    return df_1_unknow

# --- API Endpoints ---

@app.route('/')
def index():
    """
    Root endpoint - just a simple message
    """
    return jsonify({
        "message": "RELand Backend API",
        "endpoints": {
            "/api/initial_data": "GET - Get list of available areas",
            "/api/map_data": "GET - Get map data for selected areas",
            "/api/geocode": "GET - Geocode an address"
        }
    })

@app.route('/api/initial_data')
def get_initial_data():
    """
    An endpoint to give the React app the list of areas for the dropdown.
    """
    return jsonify({
        "areas": area_list
    })

@app.route('/api/map_data')
def get_map_data():
    """
    This is the main endpoint that replaces your `update_graph` logic.
    It accepts "query parameters" from the URL.
    e.g., /api/map_data?areas=Sonsón,Argelia
    """
    
    # 1. Get filter values from the request
    # .getlist() is used to get all values from a multi-select
    selected_areas = request.args.getlist('areas[]')
    
    # 2. Filter the DataFrame (the core pandas logic)
    if not selected_areas:
        # If no areas are selected, return empty data
        return jsonify({
            "prediction_points": [],
            "historical_points": [],
            "cluster_points": []
        })

    df_1 = df[df['Municipio'].isin(selected_areas)]
    df_1_with_colors = get_color_list(df_1) # Add color data
    
    # 3. Separate the data for each layer
    # This makes it *much* easier for React to handle
    
    # Prediction Layer
    df_prediction = df_1_with_colors[['LATITUD_Y', 'LONGITUD_X', 'sonson_avg']]
    
    # Historical Layer
    df_historical = df_1_with_colors[
        ['LATITUD_Y', 'LONGITUD_X', 'mines_outcome', 'colorBasedLabel']
    ]
    
    # Cluster Layer (for unknown outcomes)
    df_clusters = df_1_with_colors[
        df_1_with_colors['mines_outcome'] == -1
    ][['LATITUD_Y', 'LONGITUD_X', 'cluster', 'colorBasedCluster']]
    
    # 4. Convert data to JSON and return it
    # 'orient='records'' formats the JSON into a list of objects,
    # which is perfect for React.
    return jsonify({
        "prediction_points": df_prediction.to_dict(orient='records'),
        "historical_points": df_historical.to_dict(orient='records'),
        "cluster_points": df_clusters.to_dict(orient='records')
    })
    
@app.route('/api/geocode')
def geocode_address():
    """
    This endpoint securely handles the Google Geocoding request.
    The React app will send the address here.
    """
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "No address provided"}), 400

    # IMPORTANT: Your API key should NOT be in the code.
    # Use an environment variable.
    # We'll use your hardcoded one for now, but this is a security risk.
    google_api_key = 'AIzaSyDitOkTVs4g0ibg_Yt04DQqLaUYlxZ1o30'
    
    # Append the location, just like in your Dash app
    search_term = f"{address}, Antioquia, Colombia"
    
    params = {'key': google_api_key, 'address': search_term}
    url = 'https://maps.googleapis.com/maps/api/geocode/json?'
    
    try:
        response = requests.get(url, params)
        result = response.json()
        
        if result['status'] == 'OK':
            location = result['results'][0]['geometry']['location']
            return jsonify({
                "lat": location['lat'],
                "lon": location['lng']
            })
        else:
            return jsonify({"error": result['status']}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Run the Server ---
if __name__ == '__main__':
    # We run this on port 5000 (a common port for development backends)
    print("\n" + "="*50)
    print("🚀 RELand Backend Server Starting...")
    print("="*50)
    print(f"📊 Data loaded: {len(df)} records, {len(area_list)} areas")
    print(f"🌐 Server will run on: http://localhost:5001")
    print(f"📡 Available endpoints:")
    print(f"   - GET /")
    print(f"   - GET /api/initial_data")
    print(f"   - GET /api/map_data?areas[]=<area1>&areas[]=<area2>")
    print(f"   - GET /api/geocode?address=<address>")
    print("="*50 + "\n")
    app.run(debug=True, port=5001, host='127.0.0.1')