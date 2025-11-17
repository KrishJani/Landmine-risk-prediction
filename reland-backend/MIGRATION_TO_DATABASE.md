# Database-Only Migration Complete

## Overview
The backend has been completely migrated from CSV files to database-only operation. All data is now stored in and retrieved from PostgreSQL database.

## What Changed

### Removed
- ❌ CSV file loading on backend startup (`risk_map_predictions.csv`)
- ❌ Pandas DataFrame operations for map data
- ❌ CSV-based area list generation

### Added/Updated
- ✅ All data now comes from `Location` table in database
- ✅ `/api/initial_data` - Gets areas from database
- ✅ `/api/map_data` - Gets all location data from database
- ✅ Risk level calculation now works with database records
- ✅ Historical points come from database (`hist_mines` field)
- ✅ New endpoints for updating risk scores:
  - `PUT /api/locations/<id>` - Update single location
  - `POST /api/locations/bulk_update` - Bulk update locations

## Data Flow

### Initial Setup (One-time)
1. Run `python init_database.py` to load CSV data into database
2. This imports:
   - `risk_map_predictions.csv` → `Location` table
   - `EO_events_2510.csv` → `ConfirmedEvent` table

### Runtime (All Operations)
1. **User adds label** → Saved to `UserLabel` table → If label=1, creates `ConfirmedEvent`
2. **User views map** → Data loaded from `Location` table
3. **User updates risk scores** → Use `PUT /api/locations/<id>` or `POST /api/locations/bulk_update`
4. **All changes** → Instantly reflected in database

## Benefits

1. **Real-time Updates**: All user actions (add/remove/edit labels) are instantly saved to database
2. **No CSV Dependencies**: Backend no longer needs CSV files at runtime
3. **Re-prediction Support**: Users can update risk scores via API after re-running predictions
4. **Single Source of Truth**: Database is the only data source
5. **Better Performance**: Database queries are optimized with indexes

## API Endpoints for Re-running Predictions

### Update Single Location
```bash
PUT /api/locations/<location_id>
Content-Type: application/json

{
  "risk_score": 0.85,
  "risk_score_lr": 0.82,
  "risk_level": "High"
}
```

### Bulk Update (for re-running predictions)
```bash
POST /api/locations/bulk_update
Content-Type: application/json

{
  "locations": [
    {"id": 1, "risk_score": 0.85, "risk_score_lr": 0.82},
    {"id": 2, "risk_score": 0.23, "risk_score_lr": 0.25},
    ...
  ]
}
```

## Migration Notes

- CSV files are **only** used during initial database setup via `init_database.py`
- After initial setup, the backend operates completely independently of CSV files
- All user interactions modify the database directly
- The database should be backed up using PostgreSQL backup tools (pg_dump)

## Next Steps for Re-running Predictions

1. Run your prediction model with updated data (including new labels)
2. Export predictions to a format your backend can consume
3. Use `POST /api/locations/bulk_update` to update all risk scores
4. The map will automatically reflect the new predictions on next refresh

