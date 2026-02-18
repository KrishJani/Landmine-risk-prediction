# RELand AWS Architecture — Handover Explanation

This document explains the full AWS architecture of the RELand (Landmine Risk Prediction) project for handover to your professor.

---

## 1. High-Level Overview

The application is a **full-stack web app** for landmine risk prediction. It runs on AWS with:

- **Frontend:** React app served via **CloudFront** (CDN) and **S3**
- **Backend:** Flask API hosted on **AWS App Runner** (container service)
- **Database:** **Amazon RDS** (PostgreSQL)
- **ML training:** On-demand **EC2** GPU instances that train models and save them to **S3**
- **CI/CD:** **GitHub Actions** build and deploy frontend and backend on push to `main`/`production`

**Region:** `us-east-1` (N. Virginia)  
**Account (from docs):** 348170387270

---

## 2. Architecture Diagram (Conceptual)

```
                    ┌─────────────────────────────────────────┐
                    │           Users / Internet               │
                    └─────────────────────┬───────────────────┘
                                          │ HTTPS
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │     CloudFront (CDN)                     │
                    │     • HTTPS, global edge caching         │
                    │     • Custom domain / *.cloudfront.net   │
                    └─────────────────────┬───────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            │                             │                             │
            ▼                             │                             ▼
┌───────────────────────┐                 │                 ┌───────────────────────┐
│  S3 (Frontend)        │                 │                 │  App Runner (Backend)  │
│  • Static React app   │                 │                 │  • Flask API (Docker)  │
│  • index.html, JS,    │                 │                 │  • Port 8080          │
│    CSS, assets        │                 │                 │  • Auto-scaling/pause  │
└───────────────────────┘                 │                 └───────────┬───────────┘
                                          │                             │
                                          │                 ┌───────────┴───────────┐
                                          │                 │                       │
                                          │                 ▼                       ▼
                                          │     ┌─────────────────────┐   ┌─────────────────────┐
                                          │     │  RDS PostgreSQL     │   │  S3 (Models bucket)  │
                                          │     │  • App data, jobs,  │   │  • Trained ML models │
                                          │     │    predictions      │   │  • Private           │
                                          │     │  • Private in VPC   │   └──────────┬──────────┘
                                          │     └─────────────────────┘              │
                                          │                                          │
                                          │                 ┌────────────────────────┘
                                          │                 │
                                          │                 ▼
                                          │     ┌─────────────────────┐   ┌─────────────────────┐
                                          │     │  EC2 (GPU workers)  │   │  Systems Manager     │
                                          │     │  • On-demand/Spot    │   │  Parameter Store     │
                                          │     │  • g4dn.xlarge, T4   │   │  • DB URL, secrets   │
                                          │     │  • Train → S3, then  │   └─────────────────────┘
                                          │     │    self-terminate    │
                                          │     └─────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────────────────────────────────────┐
                    │  ECR (Elastic Container Registry) — Docker image for App Runner            │
                    │  GitHub Actions: build → push image → update App Runner service             │
                    └───────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component-by-Component Explanation

### 3.1 Frontend (User-Facing UI)

| Component | Role |
|-----------|------|
| **S3 bucket** | Stores the built React app (HTML, JS, CSS, assets). Configured for static website hosting. |
| **CloudFront** | CDN in front of S3: serves content over HTTPS, caches at edge locations, and handles custom error (e.g. 404 → `index.html` for React Router). |

**Flow:** User request → CloudFront → S3 → returns static files.  
**Deploy:** GitHub Actions (on push to `main`/`production` under `reland-frontend/`) builds the app, uploads to S3, and invalidates CloudFront cache. Manual option: `reland-frontend/deploy_to_cloudfront.sh`.

---

### 3.2 Backend (API and Business Logic)

| Component | Role |
|-----------|------|
| **App Runner** | Runs the backend as a **container** (no EC2 to manage). Handles HTTPS, health checks, scaling, and (optional) auto-pause when idle. |
| **Docker image** | Built from `reland-backend/Dockerfile`; includes Flask app, dependencies, GDAL, etc. |
| **ECR** | Holds the backend Docker image. App Runner pulls from here. |

**Flow:** Frontend calls the App Runner URL (e.g. `REACT_APP_API_URL`) → App Runner runs the Flask app → API talks to RDS and S3 (and triggers EC2 when needed).  
**Deploy:** GitHub Actions builds the image for `linux/amd64`, pushes to ECR, updates the App Runner service with the new image, starts deployment, and runs a health check on `/health`. Secrets (e.g. `DATABASE_URL`, `S3_MODELS_BUCKET`, `EC2_LAUNCH_TEMPLATE_NAME`) are passed as environment variables from GitHub Secrets.

---

### 3.3 Database

| Component | Role |
|-----------|------|
| **RDS PostgreSQL** | Single instance (e.g. `db.t3.micro`), one database (e.g. `reland_db`). Used for users, labels, predictions, training jobs, map-related data. Can use PostGIS for geospatial data. |
| **VPC** | RDS is in a **private** subnet (no public IP). Only resources in the same VPC (e.g. App Runner in custom VPC) can connect. |
| **Security group** | Allows PostgreSQL (port 5432) from the VPC CIDR. |

**Connection:** Backend gets `DATABASE_URL` from the environment (in production, set by GitHub Secrets / Parameter Store). The app adds `sslmode=require` for RDS. Credentials are not stored in code; they live in Parameter Store or CI secrets.

---

### 3.4 ML Training (EC2 Workers)

Training is **heavy** (PyTorch, GPU), so it is not run on App Runner. Instead:

| Component | Role |
|-----------|------|
| **EC2 Launch Template** | Defines the worker: AMI (e.g. Deep Learning AMI), instance type (e.g. **g4dn.xlarge** with NVIDIA T4), storage, **user data** script, security group. |
| **User data script** (`ec2-user-data.sh`) | On first boot: installs Python, CUDA, PyTorch, project dependencies, pulls/clones code, then runs the worker script. |
| **Worker script** (`ec2_worker_main.py`) | Runs on the EC2 instance: picks up training jobs (from DB or queue), trains the model, uploads the model to the **S3 models bucket**, then **terminates the instance**. |
| **Spot instances** | Backend uses **Spot** (via `aws_ec2_helper.trigger_worker_instance`) to reduce cost; instances are one-time and terminate after training. |

**Flow:** User/admin triggers “train” from the app → Backend creates a training job in RDS and calls `trigger_worker_instance()` → EC2 Spot instance starts → User data runs → Worker runs training → Model saved to S3 → Instance terminates.  
**IAM:** App Runner needs permission to launch EC2 (and read ECR, read/write S3). EC2 worker role needs S3 (models bucket) and EC2 (e.g. for self-termination).

---

### 3.5 S3 Buckets (Two Roles)

| Bucket | Purpose | Access |
|--------|---------|--------|
| **Frontend bucket** | Static website (React build). Origin for CloudFront. | Public read for website; write via CI or deploy script with AWS credentials. |
| **Models bucket** | Trained ML model artifacts. | Private; only App Runner and EC2 workers (via IAM roles) should have read/write. |

---

### 3.6 Secrets and Configuration

| Component | Role |
|-----------|------|
| **Systems Manager Parameter Store** | Holds sensitive and non-sensitive config (e.g. `/reland/database/url` as SecureString, `/reland/s3/models-bucket`). Used so the app does not hardcode secrets. |
| **GitHub Secrets** | Used in CI: `AWS_ROLE_ARN` (for OIDC to AWS), `DATABASE_URL`, `S3_MODELS_BUCKET`, `EC2_LAUNCH_TEMPLATE_NAME`, `REACT_APP_API_URL`, `CLOUDFRONT_DISTRIBUTION_ID`, etc. |

App Runner can be configured to pull secrets from Parameter Store or to receive them as environment variables from the deployment pipeline (as in the current workflow).

---

### 3.7 CI/CD (GitHub Actions)

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| **Deploy Frontend** | Push to `main`/`production` under `reland-frontend/` or the workflow file | Checkout → AWS auth (OIDC) → Node build with `REACT_APP_API_URL` and Mapbox token → `aws s3 sync` to frontend bucket → CloudFront invalidation. |
| **Deploy Backend** | Push to `main`/`production` under `reland-backend/` or the workflow file | Checkout → AWS auth → ECR login → Docker build (linux/amd64) → push to ECR → update App Runner source to new image → set env vars (from secrets) → start deployment → wait for RUNNING → health check on `/health`. |

Both workflows use **OIDC** (`role-to-assume: ${{ secrets.AWS_ROLE_ARN }}`) so no long-lived AWS keys are stored in GitHub.

---

## 4. Step-by-Step: What Happens When You Deploy

### Frontend

1. You change code under `reland-frontend/`.
2. **Build:** `npm run build` produces the static app in `build/`.
3. **Upload:** Files are synced to the S3 frontend bucket (e.g. `aws s3 sync build/ s3://bucket/`). `index.html` is uploaded with no-cache so users get the latest entry point.
4. **Invalidate:** CloudFront cache is invalidated for `/*` so edge locations serve the new files.
5. Users receive the new frontend on next request (or after cache TTL).

**Scripts:** `reland-frontend/deploy_to_cloudfront.sh` or `./scripts/deploy_reland.sh --frontend`. Or push to `main`/`production` to trigger GitHub Actions.

### Backend

1. You change code under `reland-backend/`.
2. **Build:** Docker image is built for `linux/amd64` (e.g. `docker buildx build --platform linux/amd64 ...`).
3. **Push:** Image is tagged and pushed to ECR (e.g. `reland-backend:latest` or a commit SHA).
4. **Update:** App Runner service is updated to use the new image (and env vars such as `DATABASE_URL`, `S3_MODELS_BUCKET`).
5. **Deploy:** `aws apprunner start-deployment` is called; App Runner rolls out the new container.
6. When status is RUNNING, the new backend serves traffic (health check on `/health`).

**Scripts:** `reland-backend/scripts/manual_deploy.sh` or `./scripts/deploy_reland.sh --backend`. Or push to `main`/`production` for CI/CD.

### Database

There is **no “deploy” of the database** in the same sense as frontend/backend. The RDS instance is created once in AWS.

- **Initial setup or re-seed:** Run `reland-backend/init_database.py` (local DB) or `reland-backend/setup_rds_database.py --rds-url <URL>` (RDS). These create tables (if missing) and load seed data from `risk_map_predictions.csv` and `EO_events_2510.csv`. Optionally use `./scripts/deploy_reland.sh --database` (see [DEPLOY_AFTER_CHANGE.md](DEPLOY_AFTER_CHANGE.md)).
- **Schema changes:** Add migrations or run SQL/scripts manually; the app does not auto-migrate on deploy.

---

## 5. Data Flows (Summary)

1. **Page load:** Browser → CloudFront → S3 → static files.
2. **API call:** Browser → App Runner → Flask → RDS (and/or S3). Response back to browser.
3. **Start training:** User action → App Runner → create job in RDS → launch EC2 (Spot) via launch template → EC2 runs user data → worker runs → train → save model to S3 → EC2 terminates.
4. **Use trained model:** Prediction request → App Runner → load model from S3 (or path configured from S3) → run inference → return result.

---

## 6. Security Highlights

- **RDS:** No public access; only in-VPC (e.g. App Runner in same VPC).
- **Database credentials:** In Parameter Store (SecureString) or GitHub Secrets, not in code.
- **Models bucket:** Private; access only via IAM roles (App Runner, EC2 worker).
- **Frontend bucket:** Public read only for hosting; write only via controlled deploy pipeline.
- **HTTPS:** CloudFront and App Runner serve over HTTPS.
- **Least privilege:** Separate IAM roles for App Runner (run API + launch EC2, access S3/ECR) and EC2 workers (S3 + terminate self).

---

## 7. Cost (Order of Magnitude)

From the deployment doc (approximate):

- **RDS** (db.t3.micro, 20 GB): ~\$17/month  
- **App Runner** (small, with auto-pause): ~\$2–3/month  
- **EC2 training** (g4dn.xlarge Spot, few hours/month): ~\$1–2/month  
- **S3 + CloudFront:** Low/free tier for small traffic  
- **ECR:** Small for one image  

**Total:** ~\$21–24/month (excluding any free-tier benefits).

---

## 8. Professor FAQ (What Your Professor Might Ask)

- **“Where is the backend?”** → AWS App Runner, one service, one container image from ECR.
- **“Where is the database?”** → Amazon RDS PostgreSQL in the same region and VPC; connection string from env/Parameter Store.
- **“How is the frontend served?”** → Built React app in an S3 bucket; CloudFront in front for HTTPS and caching.
- **“How does ML training work?”** → Backend creates a job and starts an EC2 Spot instance (GPU) from a launch template; the instance runs a script that trains, saves the model to S3, then shuts down.
- **“How do deployments work?”** → GitHub Actions: on push, build and deploy frontend (S3 + CloudFront) and/or backend (Docker → ECR → App Runner).
- **“Where are secrets?”** → Parameter Store and GitHub Secrets; not in the repo.

---

## 9. Key Repo Paths (for Handover)

| What | Where |
|------|--------|
| Backend app | `reland-backend/` (Flask, `backend-app.py`, `wsgi.py`) |
| Backend Docker | `reland-backend/Dockerfile` |
| EC2 worker entry | `reland-backend/ec2_worker_main.py` |
| EC2 user data | `reland-backend/ec2-user-data.sh` |
| EC2 launch helper | `reland-backend/aws_ec2_helper.py` |
| Training service (create job, launch EC2) | `reland-backend/services/training_service.py` |
| Backend config (env, RDS, S3, EC2 template) | `reland-backend/config.py` |
| Frontend | `reland-frontend/` |
| Frontend deploy script | `reland-frontend/deploy_to_cloudfront.sh` |
| Unified deploy script | `scripts/deploy_reland.sh` (--frontend, --backend, --database) |
| CI/CD | `.github/workflows/deploy-backend.yml`, `deploy-frontend.yml` |
| Deploy-after-change guide | `docs/DEPLOY_AFTER_CHANGE.md` |
| Detailed deployment steps | `docs/DEPLOYMENT_DETAILED_DOCUMENTATION.md` |

---

This gives a single place to understand and explain the whole AWS architecture during the handover. If you want, we can turn this into a short slide outline or a one-page diagram-only summary next.
