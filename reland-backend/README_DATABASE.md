# Database Setup Guide

This application uses PostgreSQL for storing user labels and confirmed events.

## Database Schema

### Tables

1. **locations** - Stores risk prediction locations from `risk_map_predictions.csv`
   - id, lat, lon, municipio
   - risk_score, risk_score_lr, risk_level
   - Feature data (elevation, rainfall, temperature, etc.)

2. **user_labels** - Stores user-assigned labels (0 = mine-free, 1 = confirmed mine)
   - id, location_id, label (0 or 1), notes, user_id
   - Timestamps (created_at, updated_at)

3. **confirmed_events** - Stores confirmed mine events
   - id, lat, lon, municipio, departamento
   - event_date, description, source
   - Links to locations and EO events

## Initialization

### First Time Setup

1. **Install dependencies:**
   ```bash
   cd Backend
   pip install -r requirements.txt
   ```

2. **Initialize the database:**
   ```bash
   python init_database.py
   ```
   
   This will:
   - Create all database tables in PostgreSQL
   - Load locations from `risk_map_predictions.csv`
   - Load confirmed events from `EO_events_2510.csv` (if available)

3. **Start the backend:**
   ```bash
   python backend-app.py
   ```
   
   Make sure PostgreSQL is running and your `.env` file is configured with the correct `DATABASE_URL`.

## API Endpoints

### Labels
- `GET /api/labels` - Get all user labels
- `POST /api/labels` - Add or update a label
  ```json
  {
    "location_id": 123,
    "label": 1,
    "notes": "Optional notes"
  }
  ```
- `DELETE /api/labels/<location_id>` - Delete a label

### Confirmed Events
- `GET /api/confirmed_events` - Get all confirmed events
- `POST /api/confirmed_events` - Add a new event
- `PUT /api/confirmed_events/<id>` - Update an event
- `DELETE /api/confirmed_events/<id>` - Delete an event

## Usage

### Adding Labels via Frontend

1. Click on any point on the map
2. Select label: 0 (Mine-free) or 1 (Confirmed Mine)
3. Add optional notes
4. Click "Save"

**Note:** When you add a label with value "1", it automatically creates a confirmed event.

### Managing Confirmed Events

1. Click "Show Confirmed Events" button in the control panel
2. View all confirmed events in the side panel
3. Delete events using the "Delete" button

## Database Configuration

The database connection is configured via the `DATABASE_URL` environment variable in the `.env` file.

**Important:** 
- The database should be backed up regularly using PostgreSQL backup tools
- To reset the database, drop and recreate it, then run `init_database.py` again
- See `README_POSTGRES.md` for detailed PostgreSQL setup instructions

## Data Flow

1. **Initial Load:**
   - CSV files → Database (via `init_database.py`)
   
2. **User Interactions:**
   - User clicks point → Frontend sends label to backend
   - Backend saves to database
   - If label = 1, creates confirmed event automatically
   
3. **Map Display:**
   - Backend loads locations from CSV (for performance)
   - Backend matches locations to database records (for location_id)
   - Backend loads confirmed events from database
   - Frontend displays all data on map

## Troubleshooting

### Database not found
- Make sure you've run `init_database.py` at least once
- Or start the backend - it will create an empty database automatically

### Labels not saving
- Check that the backend is running on port 5001
- Check browser console for errors
- Verify the location has a `location_id` (points must be in the database)

### Confirmed events not showing
- Make sure you've added labels with value "1"
- Check the "Show Confirmed Events" panel is open
- Refresh the map data by changing area selection

