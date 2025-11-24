# Database Integration for Predictions

This document explains how to use the new database-integrated prediction system.

## Overview

The system now supports a **hybrid approach** that:
1. Loads static features from CSV (fast, one-time read)
2. Loads dynamic features (`dist_old_mine`) from database (updated in real-time)
3. Saves predictions directly to database (no manual import needed)

## Features

### 1. Hybrid Dataset (`dataset_db.py`)
- Reads static features from `processed_dataset/resolution_0.5.csv`
- Loads `dist_old_mine` from database (updated when you click "Update Predictions")
- Merges data efficiently using coordinate matching
- **Performance**: ~2-3 seconds total (vs 5-10 seconds for full database)

### 2. Database-Backed Predictions (`main.py`)
- New flags: `--use_db` and `--save_to_db`
- Automatically saves predictions to database after training
- Still saves CSV backup for compatibility

### 3. Backend API (`/api/recalculate_predictions`)
- Recalculates `dist_old_mine` based on current confirmed events
- Optionally triggers model training (via `run_model` parameter)
- Returns statistics about the recalculation

## Usage

### Option 1: Via Frontend (Recommended for Feature Updates)

1. Click "🔄 Update Predictions" button in the frontend
2. Choose whether to:
   - Just update features (fast, ~2-3 seconds)
   - Update features + run model (slow, several minutes)

### Option 2: Via Command Line (For Full Model Training)

```bash
# Set database URL
export DATABASE_URL="postgresql://user:password@host:port/database"

# Run predictions with database integration
python main.py \
    --timestamp $(date +"%m%d%Y%H%M%S") \
    --municipio blockCV \
    --subset full \
    --model TabCmpt \
    --objective irm \
    --n_step 2 \
    --use_db \
    --save_to_db
```

### Option 3: Via Script (Easiest)

```bash
# Set database URL
export DATABASE_URL="postgresql://user:password@host:port/database"

# Run the script
./run_predictions.sh
```

You can customize the script by setting environment variables:
```bash
export MUNICIPIO=bolivar
export SUBSET=single
export MODEL=TabNet
./run_predictions.sh
```

## Workflow

### Step 1: Update Features
When labels or confirmed events change:
1. Click "🔄 Update Predictions" in frontend
2. System recalculates `dist_old_mine` for all locations
3. Updates database with new distances

### Step 2: Run Model (Optional)
To generate new predictions:
1. Use command line or script (model training is long-running)
2. Model reads from CSV + database (hybrid approach)
3. Predictions are saved to database automatically
4. Frontend will show updated predictions on next refresh

## Database Schema

The `Location` model now includes:
- `dist_old_mine`: Distance to closest confirmed event (in km) - **dynamically updated**
- `risk_score`: Prediction probability (0-1) - **updated by model**
- `risk_level`: 'Low', 'Medium', or 'High' - **calculated from risk_score**

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Update features only | 2-3 sec | Fast, can be done via frontend |
| Full model training | 5-30 min | Depends on model and data size |
| Save predictions to DB | 10-30 sec | Batch update, ~50k locations |

## Troubleshooting

### "DATABASE_URL not set"
Set the environment variable:
```bash
export DATABASE_URL="postgresql://user:password@host:port/database"
```

### "No locations found in database"
Make sure you've imported the initial data. Check `reland-backend/init_database.py`.

### Predictions not updating
1. Make sure you ran the model with `--save_to_db` flag
2. Check that predictions were saved: `SELECT COUNT(*) FROM locations WHERE risk_score IS NOT NULL;`
3. Refresh the frontend map

### Model training takes too long
- This is normal for full model training
- Consider using `--subset single` for faster training (only uses `dist_old_mine` feature)
- Or use a simpler model like `--model LR`

## Backward Compatibility

The system is fully backward compatible:
- Without `--use_db`: Uses original CSV-only approach
- Without `--save_to_db`: Saves to CSV only (original behavior)
- CSV files are always created as backup

## Next Steps

For production, consider:
1. **Task Queue**: Use Celery or similar for background model training
2. **Caching**: Cache feature calculations to avoid redundant work
3. **Incremental Updates**: Only retrain on changed data
4. **Monitoring**: Add logging and metrics for prediction quality


