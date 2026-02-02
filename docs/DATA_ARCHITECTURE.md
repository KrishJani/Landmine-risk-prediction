# Data Architecture: CSV vs Database

This document explains **what data source is used when**, **why** (ease, efficiency, or other), and whether **eliminating CSV files** is a good idea.

---

## 1. Data sources overview

| Source | Role | Used by |
|--------|------|---------|
| **processed_dataset/resolution_0.5.csv** | Static feature grid + municipio/splits | EventDB, main.py, diagnostics |
| **risk_map_predictions.csv** (backend) | Seed for `locations` table | init_database.py, setup_rds_database.py |
| **EO_events_2510.csv** (backend) | Seed for `confirmed_events` table | init_database.py, setup_rds_database.py |
| **Database (RDS/local)** | Dynamic data + map truth + user data | Backend API, worker, EventDB (merge), main.py via EventDB |
| **experiments/{ts}/predicted_proba.csv** | Training output (validation preds) | main.py (resume), worker fallback only |

---

## 2. When we use CSV files

### 2.1 resolution_0.5.csv (main feature dataset)

- **Where**: Project root `processed_dataset/resolution_0.5.csv`.
- **When**:
  - **Training (main.py)**: `EventDB` loads this CSV, then merges in from the DB: `dist_old_mine`, and labels from `user_labels` (mines_outcome_db). Train/val splits are driven by `Municipio` and fold configs that refer to rows in this CSV.
  - **Recalculate / re-prediction**: Backend loads `EventDB` with this CSV to get the **grid of points and all static features**. For each DB location we take the **nearest CSV row** (by lon/lat) to build the feature vector, then run the model and write one prediction per DB location.
  - **Worker after retrain**: Same as recalculate: load EventDB (CSV + DB merge), build one feature row per DB location from nearest CSV row, run the new model, write predictions to DB with `save_predictions_to_db_by_locations`.
- **Why CSV here**:
  - **Efficiency**: One read of a large static table; no DB round-trips for the many columns that never change (elevation, rainfall, land use, relief, distances to infrastructure, hist_mines, etc.).
  - **Model contract**: The model is trained on **scaled** features from this CSV (StandardScaler/KNNImputer fit on train split). Prediction must use the **same** feature set and scaling; the CSV is the canonical definition of that grid and those features.
  - **Pipeline design**: The ML pipeline (main.py, train_val_stream, municipio-based splits) was built around this file; EventDB was added to overlay DB-backed columns (dist_old_mine, user labels) without duplicating the whole grid in the DB.

So: **CSV = static feature grid + split logic; DB = dynamic columns and user/map data.**

### 2.2 risk_map_predictions.csv

- **Where**: `reland-backend/risk_map_predictions.csv`.
- **When**: Only during **database initialization** (local: `init_database.py`, RDS: `setup_rds_database.py`). Used to **populate the `locations` table** (id, lat, lon, municipio, risk_score, risk_level, optional extra columns).
- **Why CSV**: One-time seed; simple to run “load this file into DB” without touching the main feature pipeline. Often generated or derived from the same grid as resolution_0.5 (or an earlier export).

### 2.3 EO_events_2510.csv

- **Where**: `reland-backend/EO_events_2510.csv`.
- **When**: Only during **database initialization**. Used to **populate the `confirmed_events`** table.
- **Why CSV**: One-time seed for confirmed mine events.

### 2.4 experiments/…/predicted_proba.csv

- **When**: 
  - **main.py**: Written at the end of training (validation predictions); read on resume to continue appending folds.
  - **Worker**: Used **only as fallback** if the new “predict per DB location” flow fails; then predictions are matched to DB by coordinate and saved via `save_predictions_to_db_orm`. Normal path is: predict per DB location and save with `save_predictions_to_db_by_locations` (no dependency on this CSV for the map).
- **Why CSV**: Convenient output of the training loop; legacy matching-by-coordinate path. Not the source of truth for the map; the DB is.

---

## 3. When we read from the database

- **Map / GET locations**: Backend reads `Location` (risk_score, risk_level, lat, lon, municipio) for selected areas. This is what the frontend displays.
- **Recalculate and re-prediction**: Read all `Location` and all `ConfirmedEvent`; then EventDB loads the CSV and **merges** DB columns (dist_old_mine, user_labels) for features. So: CSV + DB together for the feature matrix; DB only for “which points to update” and dynamic fields.
- **Training (main.py)**: EventDB loads CSV and DB and merges; so DB is read for dist_old_mine and user labels (mines_outcome) per (lon, lat).
- **Worker**: Reads `TrainingJob`, `Location`, `ConfirmedEvent`; after training, reads `Location` again for the predict-per-DB-location step.
- **Label editing**: Read/update `UserLabel` and related `Location`.
- **Events**: Read/update/delete `ConfirmedEvent`.
- **Training jobs**: Read `TrainingJob` for status and results.

So: **DB is read whenever we need up-to-date locations, events, labels, or job state.**

---

## 4. When we write to the database

- **Recalculate**: 
  - UPDATE `locations.dist_old_mine` for all locations from distances to confirmed events.
  - Then UPDATE `locations.risk_score` and `locations.risk_level` via `save_predictions_to_db_by_locations` (one prediction per DB location).
- **Worker after retrain**: Same as above: UPDATE dist_old_mine (if events exist), then run predict-per-DB-location and `save_predictions_to_db_by_locations`. Fallback: write from predicted_proba.csv by coordinate match.
- **Reset predictions**: UPDATE `locations` SET risk_score = NULL, risk_level = NULL.
- **User labels**: INSERT/UPDATE `user_labels`.
- **Confirmed events**: INSERT/UPDATE/DELETE `confirmed_events`.
- **Training jobs**: INSERT `TrainingJob`; UPDATE status, progress, result, error_message, timestamps.

So: **DB is written for all user-facing and dynamic state: predictions, labels, events, distances, and job status.**

---

## 5. Why this split (CSV vs DB)?

- **Ease**: 
  - One big static CSV is easy to version, share, and use in scripts (pandas, resolution changes, new columns) without DB migrations.
  - DB is used where data changes (user actions, new events, new predictions).
- **Efficiency**: 
  - Reading one CSV for the full feature grid is fast and avoids heavy DB usage for dozens of static columns.
  - DB is used for the relatively small, changing subset (dist_old_mine, labels, risk_score/risk_level, events, jobs).
- **Correctness**: 
  - The model is trained on scaled features from the CSV grid; prediction reuses that grid (nearest-neighbor from DB locations to CSV rows) so input distribution matches training.
  - The map and API use the DB as the single source of truth for risk_score and risk_level.

---

## 6. Can we eliminate CSV files?

### 6.1 resolution_0.5.csv

- **Possible**: Yes. You could put the full static feature set into the DB (e.g. one table “location_features” or extended “locations” with many columns) and have EventDB (and training) read only from the DB.
- **Trade-offs**:
  - **Pros**: Single source of truth; no CSV/DB sync; all access via DB.
  - **Cons**: 
    - Big schema and migrations (many columns); any new feature or resolution requires a DB change.
    - Training would read all features from the DB (slower unless you add caching or a materialized view).
    - You must ensure the DB grid and municipio/splits match what main.py and train_val_stream expect (same points, same Municipio, etc.).
- **Recommendation**: Keeping the CSV for the **static feature grid** is reasonable for efficiency and simplicity. If you later need a single source of truth and are willing to maintain a larger DB schema and possibly a cache layer, moving the grid into the DB is feasible but non-trivial.

### 6.2 risk_map_predictions.csv (and EO_events_2510.csv)

- **Possible**: Yes. These are only for **seeding**. You could:
  - Replace risk_map_predictions by a script that builds `locations` from resolution_0.5.csv (or from the same grid in DB if you move it there) plus initial risk scores.
  - Keep EO events seed as CSV or replace with a DB seed script.
- **Recommendation**: Eliminating these CSVs from **normal operation** is fine; they’re one-time bootstrap. You can keep them as a documented way to recreate the DB from scratch, or replace with a single “seed from resolution_0.5 + EO events” script.

### 6.3 predicted_proba.csv

- **Possible**: Yes. The map already uses the DB. The worker’s primary path is “predict per DB location” and save to DB; predicted_proba.csv is only a fallback and for main.py resume/aggregation.
- **Recommendation**: You can treat predicted_proba.csv as **optional**: keep it for debugging or resume, but the map and “correct” post-train state should not depend on it. Eliminating it from the critical path is already done once the worker always uses the predict-per-DB-location flow.

---

## 7. Summary

- **resolution_0.5.csv**: Used for the **static feature grid and scaling** in training and prediction; kept for **efficiency** and **model consistency**. Eliminating it means moving the full grid into the DB and is a larger project.
- **risk_map_predictions.csv / EO_events_2510.csv**: Used only to **seed** the DB; can be replaced by scripts without affecting day-to-day architecture.
- **Database**: **Read** for map, recalculate, training (merged with CSV), worker, labels, events, jobs. **Written** for predictions, dist_old_mine, labels, events, and job status. It is the source of truth for what the user sees.
- **predicted_proba.csv**: Output of training; **not** the source of truth for the map; can be made optional or internal.

So: **eliminating all CSVs is not required for correctness.** Eliminating the **seed** CSVs is easy; eliminating **resolution_0.5.csv** is a deliberate architectural change with trade-offs (single source of truth vs. schema size and read load). The current split (CSV for static grid, DB for dynamic and user-facing data) is a reasonable balance of ease and efficiency.
