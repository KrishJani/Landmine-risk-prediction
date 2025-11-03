# RELand Backend

Flask REST API backend for the RELand landmine risk prediction system.

## Setup

1. **Create and activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate  # On Windows
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the Server

**Option 1: Using the start script**
```bash
./start_backend.sh
```

**Option 2: Manual start**
```bash
source .venv/bin/activate
python backend-app.py
```

The server will start on `http://127.0.0.1:5001`

## API Endpoints

- `GET /` - API information
- `GET /api/initial_data` - Get list of available areas
- `GET /api/map_data?areas[]=<area1>&areas[]=<area2>` - Get map data for selected areas
- `GET /api/geocode?address=<address>` - Geocode an address

## Data

The backend loads data from `website_table.csv` (local file) or falls back to the GitHub URL if the file is not found.

