# RELand — Professor Handover Guide

**Start here.** This guide is the single entry point for taking over the RELand (Landmine Risk Prediction) project.

---

## 1. Project Summary

RELand is a **full-stack web application** for landmine risk prediction. It combines:

- **React frontend** — Interactive map (Mapbox), layers, labels, confirmed events, export.
- **Flask backend** — REST API, map data, recalculate/retrain, EC2 worker orchestration.
- **PostgreSQL database** — Locations, risk scores, user labels, confirmed events, training jobs.
- **ML pipeline** — Training (local or EC2 GPU), prediction, recalc using a static feature grid (CSV) plus DB-backed columns.

**Run locally (quick):**

- **Backend:** See [reland-backend/README.md](../reland-backend/README.md). You need PostgreSQL, `LOCAL_DATABASE_URL` in `.env`, then `python init_database.py` and `python app.py`.
- **Frontend:** In `reland-frontend/`, set `REACT_APP_API_URL` (e.g. `http://localhost:5001`) and `REACT_APP_MAPBOX_TOKEN`, then `npm install` and `npm start`.
- **Training:** From project root, set `LOCAL_DATABASE_URL` (or `DATABASE_URL`) and run `python main.py --help` or `./run_predictions.sh`.

---

## 2. Where to Find What

| Topic | Document |
|-------|----------|
| **AWS architecture** (what runs where, components, data flow) | [AWS_ARCHITECTURE_EXPLAINED.md](AWS_ARCHITECTURE_EXPLAINED.md) |
| **How to deploy after you change frontend/backend/database** | [DEPLOY_AFTER_CHANGE.md](DEPLOY_AFTER_CHANGE.md) |
| **Manual deployment via AWS Console (step-by-step)** | [MANUAL_DEPLOYMENT_AWS_CONSOLE.md](MANUAL_DEPLOYMENT_AWS_CONSOLE.md) |
| **What each file and folder does** | [CODE_OVERVIEW.md](CODE_OVERVIEW.md) |
| **When we use database vs CSV data, and why** | [DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md) (full) and summary below |
| **Application features (user-facing)** | [FEATURES.md](FEATURES.md) |
| **Detailed deployment history and costs** | [DEPLOYMENT_DETAILED_DOCUMENTATION.md](DEPLOYMENT_DETAILED_DOCUMENTATION.md) |
| **Talking points for a handover meeting** | [TALKING_POINTS.md](TALKING_POINTS.md) |

---

## 3. Deploy After Changes (Short Version)

- **Frontend changed:** Build React → upload to S3 → invalidate CloudFront. Use [reland-frontend/deploy_to_cloudfront.sh](../reland-frontend/deploy_to_cloudfront.sh) or the unified script: `./scripts/deploy_reland.sh --frontend`. Alternatively, push to `main`/`production` (changes under `reland-frontend/`) to trigger GitHub Actions.
- **Backend changed:** Build Docker (linux/amd64) → push to ECR → update App Runner. Use [reland-backend/scripts/manual_deploy.sh](../reland-backend/scripts/manual_deploy.sh) or `./scripts/deploy_reland.sh --backend`. Or push to `main`/`production` (changes under `reland-backend/`) for CI/CD.
- **Database:** There is no “deploy” of the RDS instance itself. To **re-seed or set up schema**: run `reland-backend/init_database.py` (local) or `reland-backend/setup_rds_database.py --rds-url <URL>` (RDS). Requires `risk_map_predictions.csv` and `EO_events_2510.csv` in `reland-backend/`. Optionally use `./scripts/deploy_reland.sh --database` (see [DEPLOY_AFTER_CHANGE.md](DEPLOY_AFTER_CHANGE.md)).

Full steps, prerequisites, and env vars: [DEPLOY_AFTER_CHANGE.md](DEPLOY_AFTER_CHANGE.md).

---

## 4. Data Sources — When We Use DB vs CSV (Summary)

- **Database (RDS/local):** Map data (locations, risk_score, risk_level), user labels, confirmed events, training jobs. The API and frontend read/write this. **Source of truth for what users see.**
- **CSV (static):**
  - `processed_dataset/resolution_0.5.csv` — Static feature grid for training and recalc. EventDB loads this and merges in DB columns (e.g. dist_old_mine, labels). Kept for efficiency and so prediction uses the same feature set as training.
  - `reland-backend/risk_map_predictions.csv` and `EO_events_2510.csv` — One-time seed for `locations` and `confirmed_events` (used by init_database.py and setup_rds_database.py).

**Why both:** The large static grid is efficient as a single CSV read; the DB holds only dynamic and user-facing data. See [DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md) for full detail.

---

## 5. Prerequisites for Deployment

- **AWS CLI** — Installed and configured (e.g. `aws configure` or profile) for the account that owns the resources.
- **Docker** — For backend deploy (build and push image). Docker must be running.
- **Node.js 18+** and **npm** — For frontend build.
- **Secrets / config:** Backend needs `DATABASE_URL`, `S3_MODELS_BUCKET`, optionally `EC2_LAUNCH_TEMPLATE_NAME`, etc. These can come from GitHub Secrets (CI), AWS Systems Manager Parameter Store, or environment variables when running the deploy script. Frontend needs `REACT_APP_API_URL` and `REACT_APP_MAPBOX_TOKEN` at build time.

See [DEPLOY_AFTER_CHANGE.md](DEPLOY_AFTER_CHANGE.md) for the full list and where to set them.

---

## 6. Contact

- **Handover contact:** Krish Jani (kj2743@nyu.edu)

For architecture, deploy steps, and code layout, use the documents linked in Section 2.
