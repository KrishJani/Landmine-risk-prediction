# Deploy After Change — Frontend, Backend, Database

This guide explains **when** and **how** to deploy the frontend, backend, and database when you make changes. Use it together with [HANDOVER_GUIDE.md](HANDOVER_GUIDE.md) and [AWS_ARCHITECTURE_EXPLAINED.md](AWS_ARCHITECTURE_EXPLAINED.md).

---

## Prerequisites

- **AWS CLI** — Installed and configured for the account that owns S3, ECR, App Runner, and RDS.
- **Docker** — For backend deploy. Must be running (e.g. Docker Desktop).
- **Node.js 18+** and **npm** — For frontend build.
- **Secrets / config** — See “Required environment variables” below. Use GitHub Secrets for CI, or Parameter Store / shell env for the unified script.

---

## When You Change the Frontend

**What to do:** Build the React app → upload to S3 → invalidate CloudFront so users get the new files.

### Option A: Unified script (recommended for manual deploy)

```bash
./scripts/deploy_reland.sh --frontend
```

Configure via environment variables (or a `deploy.env` you source). Required:

- `S3_BUCKET` — Frontend S3 bucket name (e.g. `reland-frontend-348170387270` or `reland-web-<ACCOUNT_ID>`).
- `CLOUDFRONT_DISTRIBUTION_ID` — CloudFront distribution ID (e.g. `E3MS1AYMUSBSAQ`).
- `REACT_APP_API_URL` — Backend API URL (e.g. your App Runner URL). Used at **build time**.
- `REACT_APP_MAPBOX_TOKEN` — Mapbox token for the map (optional if already in env).

### Option B: Frontend-only script

```bash
cd reland-frontend
# Edit .env or export REACT_APP_API_URL and REACT_APP_MAPBOX_TOKEN
./deploy_to_cloudfront.sh
```

The script uses hardcoded bucket and distribution ID; edit the script if your values differ.

### Option C: GitHub Actions

Push to `main` or `production` with changes under `reland-frontend/` (or under `.github/workflows/deploy-frontend.yml`). The workflow will:

1. Checkout, configure AWS (OIDC), set up Node.
2. Build with `REACT_APP_API_URL` and `REACT_APP_MAPBOX_TOKEN` from GitHub Secrets.
3. Sync `build/` to the S3 bucket (from secrets or derived name).
4. Invalidate CloudFront.

Required GitHub Secrets: `AWS_ROLE_ARN`, `REACT_APP_API_URL`, `REACT_APP_MAPBOX_TOKEN`, and (if used) `CLOUDFRONT_DISTRIBUTION_ID`. The workflow may derive the bucket name from account ID (e.g. `reland-web-<ACCOUNT_ID>`); see [.github/workflows/deploy-frontend.yml](../.github/workflows/deploy-frontend.yml).

---

## When You Change the Backend

**What to do:** Build the Docker image for `linux/amd64` → push to ECR → update the App Runner service to use the new image → wait until the service is RUNNING.

### Option A: Unified script (recommended for manual deploy)

```bash
./scripts/deploy_reland.sh --backend
```

Required env (or Parameter Store, which the script can read):

- `AWS_REGION` — e.g. `us-east-1`.
- `ECR_REPOSITORY` — e.g. `reland-backend`.
- `APP_RUNNER_SERVICE` — e.g. `reland-backend`.
- `DATABASE_URL` — PostgreSQL connection string for RDS (or script reads from Parameter Store `/reland/database/url`).
- `S3_MODELS_BUCKET` — Models bucket name (or from Parameter Store `/reland/s3/models-bucket`).
- Optionally: `EC2_LAUNCH_TEMPLATE_NAME`, `SECRET_KEY`, `GOOGLE_GEOCODING_API_KEY`.

### Option B: Backend-only script

```bash
cd reland-backend/scripts
./manual_deploy.sh
```

Uses same env/Parameter Store for `DATABASE_URL` and `S3_MODELS_BUCKET`. Builds for `linux/amd64`, pushes to ECR, updates App Runner with Port 8080 and env vars, then waits for RUNNING.

### Option C: GitHub Actions

Push to `main` or `production` with changes under `reland-backend/` (or the workflow file). The workflow will:

1. Checkout, configure AWS, log in to ECR.
2. Build Docker image for `linux/amd64` and push to ECR.
3. Update App Runner with the new image and env vars from GitHub Secrets.
4. Start deployment and wait for RUNNING.
5. Run a health check on `/health`.

Required GitHub Secrets: `AWS_ROLE_ARN`, `DATABASE_URL`, `S3_MODELS_BUCKET`, and optionally `EC2_LAUNCH_TEMPLATE_NAME`, `SECRET_KEY`, `GOOGLE_GEOCODING_API_KEY`. See [.github/workflows/deploy-backend.yml](../.github/workflows/deploy-backend.yml).

---

## When You Change the Database

There are two different cases.

### 1. Schema or seed data (re-seed / init)

You are **not** “deploying” the RDS instance itself. You are creating or updating tables and loading seed data.

- **Local database:**  
  From `reland-backend/`: ensure `LOCAL_DATABASE_URL` is set, then:
  ```bash
  python init_database.py
  ```
  This creates tables and loads from `risk_map_predictions.csv` and `EO_events_2510.csv` in `reland-backend/`.

- **RDS database:**  
  From `reland-backend/` (or project root with `PYTHONPATH`):
  ```bash
  python setup_rds_database.py --rds-url "postgresql://user:pass@host:5432/reland_db?sslmode=require"
  ```
  Or use the unified script (it will prompt for confirmation, as re-seeding can overwrite data):
  ```bash
  export DATABASE_URL="postgresql://..."
  ./scripts/deploy_reland.sh --database
  ```
  For local init instead of RDS:
  ```bash
  ./scripts/deploy_reland.sh --database --local
  ```

**Required files in `reland-backend/`:** `risk_map_predictions.csv`, `EO_events_2510.csv`. See [DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md).

### 2. RDS instance itself (create/delete/change size)

That is done in the **AWS Console** (or CloudFormation/Terraform), not by a project script. Connection details (endpoint, port, database name) are then stored in Parameter Store or GitHub Secrets as `DATABASE_URL`. The app never “deploys” the RDS instance; it only connects to it and runs init/seed scripts when you choose to.

---

## Unified Script: `scripts/deploy_reland.sh`

One script for manual deploys:

| Command | Effect |
|--------|--------|
| `./scripts/deploy_reland.sh --frontend` | Build frontend, upload to S3, invalidate CloudFront |
| `./scripts/deploy_reland.sh --backend` | Build Docker, push to ECR, update App Runner, wait for RUNNING |
| `./scripts/deploy_reland.sh --database` | Run RDS seed (`setup_rds_database.py`) using `DATABASE_URL` (or Parameter Store). Confirmation prompt before running. |
| `./scripts/deploy_reland.sh --database --local` | Run local init (`init_database.py`) using `LOCAL_DATABASE_URL` or default local URL. |
| `./scripts/deploy_reland.sh --all` | Run `--frontend` and `--backend` (not `--database` unless you add `--with-db-seed`; see script help). |

Configuration is via **environment variables**. Copy `deploy.env.example` to `deploy.env` in the project root or in `scripts/`, fill in your values, and the script will load it automatically. Do not commit `deploy.env` (it may contain secrets). See the script header or run `./scripts/deploy_reland.sh --help` for the full list of variables.

---

## Required Environment Variables (Summary)

### Frontend (build + deploy)

| Variable | Purpose |
|----------|---------|
| `S3_BUCKET` | S3 bucket for frontend static files |
| `CLOUDFRONT_DISTRIBUTION_ID` | CloudFront distribution to invalidate |
| `REACT_APP_API_URL` | Backend API URL (build-time) |
| `REACT_APP_MAPBOX_TOKEN` | Mapbox token (build-time, optional) |

### Backend (deploy)

| Variable | Purpose |
|----------|---------|
| `AWS_REGION` | e.g. `us-east-1` |
| `ECR_REPOSITORY` | ECR repository name (e.g. `reland-backend`) |
| `APP_RUNNER_SERVICE` | App Runner service name |
| `DATABASE_URL` | PostgreSQL connection string (RDS) |
| `S3_MODELS_BUCKET` | S3 bucket for ML models |
| `EC2_LAUNCH_TEMPLATE_NAME` | (Optional) Launch template for training workers |
| `SECRET_KEY` | (Optional) Flask secret key |
| `GOOGLE_GEOCODING_API_KEY` | (Optional) Geocoding API |

### Database (seed only)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` or `RDS_URL` | RDS connection string for `setup_rds_database.py` |
| `LOCAL_DATABASE_URL` | Local DB for `init_database.py` (or script default) |

---

## Troubleshooting

- **Frontend:** If the old version still appears, wait for CloudFront invalidation to finish (often 5–15 minutes) or check that `index.html` was uploaded with no-cache and that the correct bucket and distribution ID are used.
- **Backend:** If App Runner stays in UPDATE_IN_PROGRESS or fails, check CloudWatch logs for the service and ensure `/health` returns 200. Verify `DATABASE_URL` and that the container listens on the port App Runner expects (8080).
- **Database:** If connection fails, ensure `sslmode=require` is in the URL for RDS and that the security group allows the deploy host (or App Runner VPC) to reach the RDS port (5432).

For more detail, see [DEPLOYMENT_DETAILED_DOCUMENTATION.md](DEPLOYMENT_DETAILED_DOCUMENTATION.md) and the `reland-backend/docs/` folder in the repo (RDS, health checks, etc.).
