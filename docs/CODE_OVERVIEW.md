# RELand — Code Overview

This document gives a short overview of **what each file and folder does** so you can quickly find “where is X.” For handover, start with [HANDOVER_GUIDE.md](HANDOVER_GUIDE.md).

---

## Project root (ML and shared)

| File / folder | Role |
|---------------|------|
| `main.py` | Training entry point: builds EventDB (CSV + DB), runs train/val splits, saves experiments. |
| `dataset_db.py` | **EventDB** class: loads `processed_dataset/resolution_0.5.csv`, merges in DB columns (e.g. dist_old_mine, user labels). Used by training and backend recalc. |
| `save_predictions_db.py` | Helpers to write predictions to PostgreSQL (by location or by coordinate match). |
| `model.py`, `reland.py`, `loss.py`, `utils.py` | ML components (model, training loop, loss, utilities). Used by `main.py` and by backend/worker for inference. |
| `run_predictions.sh`, `run_reland.sh` | Example scripts to run predictions or training (set `DATABASE_URL` or `LOCAL_DATABASE_URL`). |
| `processed_dataset/` | Contains `resolution_0.5.csv` — static feature grid for training and recalc (see [DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md)). |
| `scripts/` | Utilities: `run_checks.py` (DB + CSV checks), `diagnose_causes.py`, `csv_labels_check.py`, `deploy-helper.sh`, and **`deploy_reland.sh`** (unified deploy script). |
| `docs/` | All project documentation (this file, HANDOVER_GUIDE, AWS, deploy, data, etc.). |

---

## reland-backend (Flask API)

### Entry and config

| File | Role |
|------|------|
| `backend-app.py` | Main Flask app: registers routes, CORS, DB config; contains some recalc logic and inline route handlers. Primary application module. |
| `app.py` | Creates the Flask app (factory); used for local run and tests. |
| `wsgi.py` | WSGI entry for Gunicorn in production (imports the app). |
| `run.py` | Start command in Docker: sets PORT (default 8080), runs Gunicorn with `wsgi:application`. |
| `config.py` | Configuration (env-based): database URL, port, S3, EC2 template, etc. |
| `models.py` | SQLAlchemy models: **Location**, **UserLabel**, **ConfirmedEvent**, **TrainingJob**. |
| `exceptions.py` | Custom exceptions (e.g. RELandException, ModelError). |

### Routes (`routes/`)

| File | Role |
|------|------|
| `__init__.py` | Defines `api_bp` blueprint; imports all route modules. |
| `health.py` | Health check endpoint (e.g. `/health`) for load balancers and App Runner. |
| `labels.py` | GET/POST/DELETE user labels (`/api/labels`). |
| `events.py` | CRUD for confirmed events (`/api/confirmed_events`). |
| `map_data.py` | Map data for selected areas (`/api/map_data`). |
| `initial_data.py` | Initial data (areas, etc.) for app load (`/api/initial_data`). |
| `recalculate.py` | Recalculate distances and run predictions (`/api/recalculate_and_predict`). Uses EventDB (CSV + DB). |
| `training.py` | Retrain model, job status, list jobs, last trained model (`/api/retrain_model`, `/api/job_status/<id>`, `/api/jobs`, `/api/last_trained_model`). |
| `export.py` | Export predictions as Excel or GeoJSON (`/api/export_predictions`). |
| `geocode.py` | Geocode address (`/api/geocode`). |
| `municipality_borders.py` | Municipality borders for the map (`/api/municipality_borders`). |
| `locations.py` | Update single location, bulk update (`/api/locations/<id>`, `/api/locations/bulk_update`). |

### Services (`services/`)

| File | Role |
|------|------|
| `location_service.py` | Location operations (query, bulk update, risk levels). |
| `label_service.py` | User label operations. |
| `event_service.py` | Confirmed event CRUD. |
| `map_service.py` | Map data aggregation. |
| `training_service.py` | Create training job, trigger EC2 worker (via aws_ec2_helper). |

### Utils (`utils/`)

| File | Role |
|------|------|
| `distance_calculator.py` | Distance from locations to confirmed events. |
| `risk_calculator.py` | Risk level computation. |
| `model_finder.py` | Find and load trained model (local or S3). |
| `geocoding.py` | Geocoding (e.g. Google) for address search. |

### EC2 worker and AWS

| File | Role |
|------|------|
| `ec2_worker_main.py` | Runs on EC2: picks up training job, loads EventDB (CSV + DB), trains, saves model to S3, terminates instance. |
| `ec2-user-data.sh` | EC2 user data script: installs dependencies, pulls code, runs worker. |
| `aws_ec2_helper.py` | Triggers EC2 (e.g. Spot) from launch template for training. |

### Database init

| File | Role |
|------|------|
| `init_database.py` | One-time local DB setup: create tables, load `risk_map_predictions.csv` and `EO_events_2510.csv` into Location and ConfirmedEvent. |
| `setup_rds_database.py` | Same as init but for RDS: `--rds-url <URL>`, creates tables and seeds from the same CSVs. |

### Other

| File | Role |
|------|------|
| `municipality_borders.py` | (Backend root) Loads municipality borders (shapefile/GeoJSON); used by municipality_borders route. |
| `Dockerfile` | Container image for backend (Python, GDAL, app code); exposes 8080, runs `run.py`. |
| `scripts/` | Backend-specific scripts: `manual_deploy.sh`, health/log/deploy helpers. |

---

## reland-frontend (React UI)

| Path | Role |
|------|------|
| `src/App.js` | Main React app: map (Mapbox), layers, panels, API calls to backend, state. |
| `src/` | Other components, styles, and assets (if any). |
| `public/` | Static assets and `index.html`. |
| `build/` | Output of `npm run build` (uploaded to S3 for deploy). |

**Build-time env:** `REACT_APP_API_URL` (backend URL), `REACT_APP_MAPBOX_TOKEN` (Mapbox). Set in `.env` or in CI.

**Deploy:** `deploy_to_cloudfront.sh` (frontend-only) or `./scripts/deploy_reland.sh --frontend`.

---

## Quick “where is X?”

| What | Where |
|------|--------|
| API routes and app setup | `reland-backend/backend-app.py`, `reland-backend/routes/` |
| DB models | `reland-backend/models.py` |
| Recalculate / prediction logic | `reland-backend/routes/recalculate.py`, EventDB in `dataset_db.py` |
| Training job + EC2 trigger | `reland-backend/services/training_service.py`, `aws_ec2_helper.py` |
| EC2 worker entry | `reland-backend/ec2_worker_main.py` |
| Map and UI | `reland-frontend/src/App.js` |
| CSV + DB merge (training/recalc) | `dataset_db.py` (EventDB) |
| DB seed (locations, events) | `reland-backend/init_database.py`, `setup_rds_database.py` |
| Deploy all (frontend/backend/DB seed) | `scripts/deploy_reland.sh` |
