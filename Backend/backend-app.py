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
    risk_file = os.path.join(os.path.dirname(__file__), 'risk_map_predictions.csv')
    if os.path.exists(risk_file):
        print(f"Loading data from local file: {risk_file}")
        df = pd.read_csv(risk_file)
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
def get_color_list(df_to_color, score_column='risk_score'):
    """
    This new helper creates risk "bins" from a continuous
    risk score and assigns a color.
    """
    df_to_color = df_to_color.copy()

    # Use pd.qcut to automatically create 3 bins (quantiles)
    # This is robust even if the scores are very small.
    # It will label points as 'Low', 'Medium', or 'High'
    try:
        df_to_color['risk_level'] = pd.qcut(
            df_to_color[score_column], 
            q=3, 
            labels=['Low', 'Medium', 'High']
        )
    except ValueError:
        # This can happen if there's not enough data to split
        # Just assign 'Low' to all in that case
        df_to_color['risk_level'] = 'Low'

    # Map those labels to colors
    color_map = {
        'Low': 'rgb(0, 255, 0)',  # Green
        'Medium': 'rgb(245, 221, 43)', # Yellow
        'High': 'rgb(255, 0, 0)'    # Red
    }
    
    df_to_color['color'] = df_to_color['risk_level'].map(color_map)
    
    # Handle historical data
    # Let's assign a color for historical mines (e.g., 'hist_mines' > 0)
    # We'll make them purple to stand out
    df_to_color.loc[df_to_color['hist_mines'] > 0, 'hist_color'] = 'purple'
    
    return df_to_color

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
    This is the main endpoint, updated for the new dataset.
    It returns a risk heatmap and a set of historical mine points.
    """
    
    # 1. Get filter values from the request
    selected_areas = request.args.getlist('areas[]')
    
    # You might want to let the user choose which risk score to use
    # For now, we'll hardcode 'risk_score'
    score_to_use = 'risk_score' # or 'risk_score_lr'
    
    # 2. Filter the DataFrame (the core pandas logic)
    if not selected_areas:
        # If no areas are selected, return empty data
        return jsonify({
            "risk_heatmap_points": [],
            "historical_points": []
        })

    df_1 = df[df['Municipio'].isin(selected_areas)]
    
    # 3. Add color data using our NEW helper function
    df_1_with_colors = get_color_list(df_1, score_to_use)
    
    # 4. Separate the data for each layer
    
    # Layer 1: Risk Heatmap (All points)
    # We select the columns React will need
    df_heatmap = df_1_with_colors[
        ['LATITUD_Y', 'LONGITUD_X', score_to_use, 'risk_level', 'color']
    ]
    
    # Layer 2: Historical Mines (Only where hist_mines > 0)
    df_historical = df_1_with_colors[
        df_1_with_colors['hist_mines'] > 0
    ][['LATITUD_Y', 'LONGITUD_X', 'hist_mines', 'hist_color']]
    
    # 5. Convert data to JSON and return it
    return jsonify({
        "risk_heatmap_points": df_heatmap.to_dict(orient='records'),
        "historical_points": df_historical.to_dict(orient='records')
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