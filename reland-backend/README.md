# RELand Backend

Flask REST API backend for the RELand landmine risk prediction system.

## Setup

1. **Set up PostgreSQL database:**
   - Install PostgreSQL (see `README_POSTGRES.md` for detailed instructions)
   - Create database and user:
     ```sql
     CREATE DATABASE reland_db;
     CREATE USER reland_user WITH PASSWORD 'your_password';
     GRANT ALL PRIVILEGES ON DATABASE reland_db TO reland_user;
     ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and set your DATABASE_URL
   ```

3. **Create and activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Initialize database:**
   ```bash
   python init_database.py
   ```
   This creates tables and loads data from CSV files into PostgreSQL (one-time setup).

## Running the Server

**Option 1: Using the start script**
```bash
chmod +x start_backend.sh
./start_backend.sh
```

**Option 2: Manual start**
```bash
source .venv/bin/activate
python backend-app.py
```

The server will start on `http://127.0.0.1:5001`

## API Endpoints

### Core Endpoints
- `GET /` - API information
- `GET /api/initial_data` - Get list of available areas (from database)
- `GET /api/map_data?areas[]=<area1>&areas[]=<area2>` - Get map data (from database)
- `GET /api/geocode?address=<address>` - Geocode an address

### Label Management
- `GET /api/labels` - Get all user labels
- `POST /api/labels` - Add or update a label
- `DELETE /api/labels/<location_id>` - Delete a label

### Confirmed Events
- `GET /api/confirmed_events` - Get all confirmed events
- `POST /api/confirmed_events` - Add a confirmed event
- `PUT /api/confirmed_events/<id>` - Update a confirmed event
- `DELETE /api/confirmed_events/<id>` - Delete a confirmed event

### Location Updates (for re-running predictions)
- `PUT /api/locations/<id>` - Update a single location's risk score
- `POST /api/locations/bulk_update` - Bulk update risk scores

## Data Storage

All data is stored in PostgreSQL database. CSV files are only used during initial database setup via `init_database.py`. After setup, the backend operates completely database-driven.

See `README_POSTGRES.md` for PostgreSQL setup instructions and `README_DATABASE.md` for database schema and usage details.

