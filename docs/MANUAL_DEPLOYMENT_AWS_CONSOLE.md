# Manual Deployment via AWS Console (Step-by-Step)

This document explains how to deploy the **frontend**, **backend**, and **database** for RELand using the **AWS website (Console)** where possible. Steps that must be done from your computer (e.g. building the app or pushing the Docker image) are clearly marked.

**Region used in examples:** `us-east-1` (N. Virginia). Choose the same region for all resources.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Database (RDS) — Manual Setup via Console](#2-database-rds--manual-setup-via-console)
3. [Database — Seed Data (From Your Computer)](#3-database--seed-data-from-your-computer)
4. [Frontend — Manual Deploy via Console](#4-frontend--manual-deploy-via-console)
5. [Backend — Manual Deploy via Console](#5-backend--manual-deploy-via-console)
6. [After Deployment](#6-after-deployment)

---

## 1. Prerequisites

- An **AWS account** with permissions to create RDS, S3, CloudFront, ECR, App Runner, IAM (if creating roles), and Systems Manager Parameter Store.
- **From your computer:** Node.js 18+, Docker, Python 3, and AWS CLI (for pushing images and running the database seed script). Optional: use the script `./scripts/deploy_reland.sh` after Console setup.

---

## 2. Database (RDS) — Manual Setup via Console

These steps create the PostgreSQL database that the backend will use. You do not “deploy” the database code; you create the **RDS instance** and then **seed** it from your machine (Section 3).

### Step 2.1: Create a DB subnet group (if you do not have one)

1. In the AWS Console, open **RDS** (search for “RDS” in the top search bar).
2. In the left sidebar, click **Subnet groups**.
3. Click **Create DB subnet group**.
4. **Name:** e.g. `reland-db-subnet-group`.
5. **Description:** e.g. `RELand RDS subnet group`.
6. **VPC:** Choose your default VPC (or the VPC where App Runner will run).
7. **Add subnets:** Select at least two subnets in different Availability Zones (e.g. `us-east-1a`, `us-east-1b`).
8. Click **Create**.

### Step 2.2: Create a security group for RDS

1. Open **EC2** in the Console (search “EC2”).
2. Left sidebar: **Network & Security** → **Security Groups**.
3. Click **Create security group**.
4. **Name:** e.g. `reland-rds-sg`.
5. **Description:** e.g. `Allow PostgreSQL from VPC`.
6. **VPC:** Same VPC as your subnets.
7. **Inbound rules:** Add rule:
   - **Type:** PostgreSQL.
   - **Port:** 5432.
   - **Source:** Your VPC CIDR (e.g. `172.31.0.0/16`) or the security group that App Runner will use so the backend can reach RDS.
8. Click **Create security group**.

### Step 2.3: Create the RDS instance

1. Go back to **RDS** → **Databases**.
2. Click **Create database**.
3. **Engine:** Amazon PostgreSQL (e.g. PostgreSQL 15 or 17).
4. **Templates:** e.g. **Free tier** or **Dev/Test** (or Production if needed).
5. **Settings:**
   - **DB instance identifier:** e.g. `reland-db`.
   - **Master username:** e.g. `reland_admin`.
   - **Master password:** Choose a strong password and **save it**; you will need it for the connection string and Parameter Store.
6. **Instance configuration:** e.g. `db.t3.micro` (1 vCPU, 1 GB RAM) for low cost.
7. **Storage:** e.g. 20 GB gp2, enable autoscaling if desired.
8. **Connectivity:**
   - **VPC:** Same as above.
   - **Subnet group:** The one you created (e.g. `reland-db-subnet-group`).
   - **Public access:** **No** (keep RDS private).
   - **VPC security group:** Select the security group you created (e.g. `reland-rds-sg`).
9. **Database name:** e.g. `reland_db`.
10. **Backup, encryption, logging:** Configure as required (e.g. 7-day backup, encryption enabled).
11. Click **Create database**. Wait until status is **Available**; note the **Endpoint** (e.g. `reland-db.xxxxx.us-east-1.rds.amazonaws.com`).

### Step 2.4: Store the database URL in Parameter Store

1. In the Console, open **Systems Manager** (search “Systems Manager”).
2. Left sidebar: **Application Management** → **Parameter Store**.
3. Click **Create parameter**.
4. **Name:** `/reland/database/url`.
5. **Type:** **SecureString**.
6. **Value:**  
   `postgresql://reland_admin:YOUR_PASSWORD@reland-db.xxxxx.us-east-1.rds.amazonaws.com:5432/reland_db`  
   Replace `YOUR_PASSWORD` and the host with your RDS endpoint. For RDS, add `?sslmode=require` at the end so the URL looks like:  
   `postgresql://reland_admin:YOUR_PASSWORD@reland-db.xxxxx.us-east-1.rds.amazonaws.com:5432/reland_db?sslmode=require`
7. Click **Create parameter**.

Optional: create a non-secret parameter for the models bucket:

- **Name:** `/reland/s3/models-bucket`
- **Type:** String
- **Value:** Your S3 models bucket name (e.g. `reland-models-123456789012`)

---

## 3. Database — Seed Data (From Your Computer)

RDS is created in the Console; **loading schema and seed data** is done from your machine so the app has tables and initial data.

1. **Get the RDS URL:** From Parameter Store (Console or CLI) or build it from the RDS endpoint, database name, and credentials.
2. **From your project root** (with `reland-backend` containing `risk_map_predictions.csv` and `EO_events_2510.csv`):

   ```bash
   cd reland-backend
   python3 setup_rds_database.py --rds-url "postgresql://reland_admin:YOUR_PASSWORD@reland-db.xxxxx.us-east-1.rds.amazonaws.com:5432/reland_db?sslmode=require"
   ```

   Or use the deploy script (after setting `DATABASE_URL` or `RDS_URL`):

   ```bash
   ./scripts/deploy_reland.sh --database
   ```

3. The script creates tables and loads locations and confirmed events from the CSVs. After this, the database is ready for the backend.

---

## 4. Frontend — Manual Deploy via Console

You will: (1) create an S3 bucket and configure it for static website hosting in the Console, (2) create a CloudFront distribution in the Console, (3) build the frontend on your machine and upload files (upload can be done in the Console or via CLI).

### Step 4.1: Create S3 bucket for the frontend

1. In the AWS Console, open **S3**.
2. Click **Create bucket**.
3. **Bucket name:** e.g. `reland-frontend-ACCOUNT_ID` (replace `ACCOUNT_ID` with your 12-digit AWS account ID; must be globally unique).
4. **Region:** e.g. `us-east-1`.
5. **Block Public Access:** Uncheck **Block all public access** (required for public website hosting). Confirm the warning.
6. Leave other defaults and click **Create bucket**.

### Step 4.2: Enable static website hosting on the bucket

1. Open the bucket you just created.
2. Go to the **Properties** tab.
3. Scroll to **Static website hosting** → **Edit**.
4. **Enable** static website hosting.
5. **Hosting type:** Host a static website.
6. **Index document:** `index.html`.
7. **Error document:** `index.html` (so React Router works for client-side routes).
8. Save changes.
9. Note the **Bucket website endpoint** (e.g. `http://reland-frontend-xxxxx.s3-website-us-east-1.amazonaws.com`).

### Step 4.3: Attach a bucket policy (public read)

1. In the same bucket, go to the **Permissions** tab.
2. **Bucket policy** → **Edit**.
3. Use a policy that allows public read for website access, for example (replace `BUCKET_NAME`):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "PublicReadGetObject",
         "Effect": "Allow",
         "Principal": "*",
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::BUCKET_NAME/*"
       }
     ]
   }
   ```

4. Save changes.

### Step 4.4: Create CloudFront distribution

1. In the Console, open **CloudFront**.
2. Click **Create distribution**.
3. **Origin domain:** Choose the **S3 website endpoint** (e.g. `reland-frontend-xxxxx.s3-website-us-east-1.amazonaws.com`), **not** the REST endpoint. If you only see the bucket name, type the full website endpoint manually.
4. **Origin path:** Leave blank.
5. **Name:** Auto-filled from origin; you can leave it or rename (e.g. `reland-frontend`).
6. **Viewer protocol policy:** Redirect HTTP to HTTPS.
7. **Allowed HTTP methods:** GET, HEAD, OPTIONS.
8. **Cache policy:** e.g. CachingOptimized or a custom policy.
9. **Default root object:** `index.html`.
10. **Error pages:** Add custom error response:
    - **HTTP error code:** 403 and 404 (or add two rules: 403, 404).
    - **Response page path:** `/index.html`.
    - **HTTP response code:** 200.
    This enables React Router to work.
11. Click **Create distribution**. Wait until **Status** is **Deployed**; note the **Distribution domain name** (e.g. `d1234abcd.cloudfront.net`) and **Distribution ID** (e.g. `E3MS1AYMUSBSAQ`).

### Step 4.5: Build the frontend (from your computer)

1. On your machine, in the repo:

   ```bash
   cd reland-frontend
   ```

2. Create a `.env` with your backend URL and Mapbox token (use your App Runner URL once the backend is deployed):

   ```bash
   echo "REACT_APP_API_URL=https://your-app-runner-url.us-east-1.awsapprunner.com" > .env
   echo "REACT_APP_MAPBOX_TOKEN=pk.your_mapbox_token" >> .env
   ```

3. Build:

   ```bash
   npm install
   npm run build
   ```

4. You should have a `build/` folder with `index.html` and `static/`.

### Step 4.6: Upload build files to S3 (via Console or CLI)

**Option A — AWS Console:**

1. Open your **frontend S3 bucket** in the Console.
2. Go to the **Objects** tab.
3. Click **Upload**.
4. **Add files** → select **all** files and folders inside `reland-frontend/build/` (drag and drop or Choose files). Ensure `index.html` is at the root of the bucket and `static/` (with js, css, etc.) is uploaded.
5. Under **Permissions**, you can leave “Grant public-read” if the bucket policy already allows public read.
6. Click **Upload**.

**Option B — AWS CLI (from your computer):**

```bash
aws s3 sync reland-frontend/build/ s3://YOUR_FRONTEND_BUCKET_NAME/ --delete \
  --cache-control "public, max-age=31536000, immutable" --exclude "index.html" --exclude "service-worker.js"
aws s3 cp reland-frontend/build/index.html s3://YOUR_FRONTEND_BUCKET_NAME/index.html \
  --cache-control "no-cache, no-store, must-revalidate"
```

Replace `YOUR_FRONTEND_BUCKET_NAME` with your bucket name.

### Step 4.7: Invalidate CloudFront cache (so users see the new frontend)

1. In **CloudFront**, open your distribution (click its ID).
2. Go to the **Invalidations** tab.
3. Click **Create invalidation**.
4. **Object paths:** `/*`.
5. Click **Create invalidation**. Wait until the invalidation status is **Completed** (often 5–15 minutes).

Your frontend is now served at `https://YOUR_DISTRIBUTION_DOMAIN` (e.g. `https://d1234abcd.cloudfront.net`).

---

## 5. Backend — Manual Deploy via Console

You will: (1) create an ECR repository in the Console, (2) build and push the Docker image from your computer, (3) create or update the App Runner service in the Console.

### Step 5.1: Create ECR repository

1. In the AWS Console, open **ECR** (Elastic Container Registry).
2. Make sure the region is correct (e.g. `us-east-1`).
3. Click **Create repository**.
4. **Visibility:** Private.
5. **Repository name:** e.g. `reland-backend`.
6. Leave other defaults and click **Create repository**.
7. Note the **Repository URI** (e.g. `123456789012.dkr.ecr.us-east-1.amazonaws.com/reland-backend`).

### Step 5.2: Build and push the Docker image (from your computer)

1. Authenticate Docker to ECR (replace region and account if needed):

   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
   ```

2. Build the image for linux/amd64 (required for App Runner):

   ```bash
   cd reland-backend
   docker buildx build --platform linux/amd64 -t reland-backend:latest --load .
   ```

3. Tag and push (replace `ACCOUNT_ID` and `REGION`):

   ```bash
   docker tag reland-backend:latest ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/reland-backend:latest
   docker push ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/reland-backend:latest
   ```

After this, the **latest** image is in ECR and you can use it in App Runner.

### Step 5.3: Create IAM role for App Runner (if not already created)

App Runner needs a role that can pull from ECR and (for this app) access S3 and EC2. If an admin has already created `reland-apprunner-role`, skip to Step 5.4.

1. Open **IAM** → **Roles** → **Create role**.
2. **Trusted entity type:** AWS service.
3. **Use case:** App Runner.
4. Click **Next**.
5. **Permissions:** Attach policies such as `AmazonEC2ContainerRegistryReadOnly`, and custom or managed policies for S3 (models bucket) and EC2 (launch workers). For a minimal start you may need at least ECR read and S3 access.
6. **Role name:** e.g. `reland-apprunner-role`.
7. Create the role.

### Step 5.4: Create App Runner service (first time)

1. In the AWS Console, open **App Runner**.
2. Click **Create service**.
3. **Repository type:** Container registry.
4. **Provider:** Amazon ECR.
5. **Container image URI:** Click **Browse** and select your ECR repository and image tag (e.g. `reland-backend:latest`), or paste the full URI (e.g. `123456789012.dkr.ecr.us-east-1.amazonaws.com/reland-backend:latest`).
6. **Deployment trigger:** Manual (or Automatic if you prefer).
7. **ECR access role:** If prompted, use the role that allows App Runner to pull from ECR (often created automatically; otherwise select an existing one).
8. **Service name:** e.g. `reland-backend`.
9. **CPU:** 1 vCPU. **Memory:** 2 GB.
10. **Port:** **8080** (the container listens on 8080).
11. **Environment variables:** Add the following (replace values as needed):
    - `FLASK_ENV` = `production`
    - `ENVIRONMENT` = `production`
    - `DATABASE_URL` = (paste the full PostgreSQL URL, or reference Parameter Store if your account supports it)
    - `AWS_REGION` = `us-east-1`
    - `S3_MODELS_BUCKET` = your models bucket name
    - `EC2_LAUNCH_TEMPLATE_NAME` = `reland-worker-template` (if you use EC2 for training)
    - `PORT` = `8080`
    - `USE_REDIS` = `false`
    - `DEBUG` = `False`
    Optionally: `SECRET_KEY`, `GOOGLE_GEOCODING_API_KEY`.
12. **Health check:**  
    **Path:** `/health`  
    **Protocol:** HTTP  
    **Interval:** 10 seconds  
    **Timeout:** 10 seconds  
    **Healthy threshold:** 1  
    **Unhealthy threshold:** 10  
13. **Networking:** If your RDS is in a VPC, configure **Custom VPC** so App Runner runs in the same VPC and can reach RDS. Otherwise use default (public).
14. **Service role:** Select the App Runner instance role (e.g. `reland-apprunner-role`) that has ECR, S3, and EC2 permissions.
15. Click **Create & deploy**. Wait until **Status** is **Running**.
16. Copy the **Service URL** (e.g. `https://xxxxx.us-east-1.awsapprunner.com`). Use this as `REACT_APP_API_URL` when rebuilding the frontend.

### Step 5.5: Redeploy backend (after code changes) via Console

When you have a new Docker image in ECR:

1. Open **App Runner** → your service (e.g. `reland-backend`).
2. Go to the **Configuration** tab (or **Deploy** tab, depending on console layout).
3. Click **Edit** (or **Deploy new version**).
4. **Container image:** Update to the new image tag (e.g. `latest` or a new tag you pushed).
5. Save and **Start deployment**. Wait until the deployment finishes and status is **Running**.

You can also trigger a new deployment from the **Deployments** tab by starting a new deployment for the current configuration.

---

## 6. After Deployment

- **Frontend URL:** `https://YOUR_CLOUDFRONT_DOMAIN` (from Step 4.4).
- **Backend URL:** App Runner service URL (from Step 5.4). Use it as `REACT_APP_API_URL` when building the frontend.
- **Database:** No direct URL for users; the backend connects using `DATABASE_URL` (stored in Parameter Store or in App Runner environment variables).

**Optional:** Use the unified script for future updates: copy `deploy.env.example` to `deploy.env`, fill in the values (bucket, distribution ID, App Runner URL, etc.), then run:

- `./scripts/deploy_reland.sh --frontend` — build and upload frontend, invalidate CloudFront.
- `./scripts/deploy_reland.sh --backend` — build Docker image, push to ECR, update App Runner (or do the App Runner update manually in the Console as in Step 5.5).
- `./scripts/deploy_reland.sh --database` — run RDS seed again (with confirmation).

For more on automation and architecture, see [HANDOVER_GUIDE.md](HANDOVER_GUIDE.md), [DEPLOY_AFTER_CHANGE.md](DEPLOY_AFTER_CHANGE.md), and [AWS_ARCHITECTURE_EXPLAINED.md](AWS_ARCHITECTURE_EXPLAINED.md).
