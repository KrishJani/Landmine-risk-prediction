# Project Handover Guide

This guide explains how to set up and deploy the RELand Landmine Risk Prediction application for a new team member.

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Landmine-risk-prediction
   ```

2. **Set up AWS Access**
   - Ensure you have AWS account access (Account ID: `348170387270`, Region: `us-east-1`)
   - Configure AWS CLI credentials
   - Request IAM permissions for deployment

3. **Configure GitHub Secrets**
   - Add required secrets to GitHub repository settings
   - Set up OIDC for GitHub Actions

4. **Deploy**
   - Push to `main` or `production` branch
   - GitHub Actions will automatically deploy

---

## AWS Infrastructure Overview

### Services Used

- **RDS (PostgreSQL with PostGIS)**: Database for application data
- **S3**: Static frontend files and trained ML models
- **ECR**: Docker image registry for backend
- **App Runner**: Hosts Flask backend API
- **CloudFront**: CDN for frontend delivery
- **EC2**: ML model training (g4dn.xlarge Spot instances)
- **Systems Manager Parameter Store**: Secure credential storage
- **IAM**: Access control and service roles

### Current Endpoints

- **Frontend**: CloudFront distribution (check AWS Console)
- **Backend API**: App Runner service URL (check AWS Console)
- **Database**: RDS endpoint (stored in Parameter Store: `/reland/database/url`)
- **ECR Repository**: `reland-backend`
- **S3 Buckets**: 
  - Frontend: `reland-web-<account-id>`
  - Models: `reland-models-<account-id>`

---

## Required AWS Setup

### 1. IAM Roles (Must be created by AWS Admin)

#### `reland-apprunner-role`
- **Trust Policy**: App Runner service
- **Permissions**:
  - `AmazonEC2FullAccess`
  - `AmazonS3FullAccess`
  - `AmazonECRReadOnly`

#### `reland-ec2-worker-role`
- **Trust Policy**: EC2 service
- **Permissions**:
  - `AmazonS3FullAccess`
  - `AmazonEC2FullAccess` (for self-termination)

#### GitHub Actions OIDC Role
- **Trust Policy**: GitHub OIDC provider
- **Permissions**: 
  - ECR push/pull
  - App Runner update
  - S3 upload
  - CloudFront invalidation
  - Parameter Store read

### 2. Systems Manager Parameter Store

Ensure these parameters exist:
- `/reland/database/url` (SecureString): RDS connection string
- `/reland/s3/models-bucket` (String): S3 bucket name for models

### 3. EC2 Launch Template

Template name: `reland-worker-template`
- Instance type: `g4dn.xlarge` (Spot)
- IAM role: `reland-ec2-worker-role`
- User data: Script to pull code, train model, upload to S3

---

## GitHub Secrets Configuration

Add these secrets in GitHub repository settings (`Settings > Secrets and variables > Actions`):

### Required Secrets

1. **`AWS_ROLE_ARN`**
   - ARN of the IAM role for GitHub Actions OIDC
   - Format: `arn:aws:iam::348170387270:role/github-actions-role`

2. **`DATABASE_URL`**
   - RDS PostgreSQL connection string
   - Format: `postgresql://user:password@host:5432/database`
   - Can also be read from Parameter Store: `/reland/database/url`

3. **`REACT_APP_API_URL`**
   - Backend API URL (App Runner service URL)
   - Example: `https://xxxxx.us-east-1.awsapprunner.com`

4. **`REACT_APP_MAPBOX_TOKEN`**
   - Mapbox API token for map rendering

5. **`CLOUDFRONT_DISTRIBUTION_ID`**
   - CloudFront distribution ID for cache invalidation

6. **`S3_MODELS_BUCKET`**
   - S3 bucket name for ML models
   - Can also be read from Parameter Store: `/reland/s3/models-bucket`

### Optional Secrets

- **`EC2_LAUNCH_TEMPLATE_NAME`**: Defaults to `reland-worker-template`
- **`SECRET_KEY`**: Flask secret key (defaults to `change-me-in-production`)
- **`GOOGLE_GEOCODING_API_KEY`**: For geocoding features

---

## CI/CD Workflow

### Backend Deployment (`.github/workflows/deploy-backend.yml`)

**Triggers:**
- Push to `main` or `production` branch
- Changes in `reland-backend/**` or workflow file
- Manual trigger via `workflow_dispatch`

**Steps:**
1. Configure AWS credentials via OIDC
2. Build Docker image for `linux/amd64`
3. Push to ECR with tags: `latest` and `{git-sha}`
4. Update App Runner service with new image
5. Wait for deployment and health check

**Environment Variables Set:**
- `FLASK_ENV=production`
- `ENVIRONMENT=production`
- `DATABASE_URL` (from secret)
- `AWS_REGION=us-east-1`
- `S3_MODELS_BUCKET` (from secret)
- `EC2_LAUNCH_TEMPLATE_NAME` (from secret or default)
- `SECRET_KEY` (from secret or default)
- `GOOGLE_GEOCODING_API_KEY` (from secret or empty)
- `USE_REDIS=false`
- `PORT=8000`
- `DEBUG=False`

### Frontend Deployment (`.github/workflows/deploy-frontend.yml`)

**Triggers:**
- Push to `main` or `production` branch
- Changes in `reland-frontend/**` or workflow file
- Manual trigger via `workflow_dispatch`

**Steps:**
1. Configure AWS credentials via OIDC
2. Build React app with environment variables
3. Upload `build/` to S3 bucket
4. Invalidate CloudFront cache

---

## Local Development Setup

### Backend

1. **Install dependencies**
   ```bash
   cd reland-backend
   pip install -r requirements.txt
   ```

2. **Configure environment**
   - Copy `.env.example` to `.env` (if exists)
   - Set `DATABASE_URL` for local PostgreSQL
   - Set other required variables

3. **Run locally**
   ```bash
   python app.py
   # or
   flask run
   ```

### Frontend

1. **Install dependencies**
   ```bash
   cd reland-frontend
   npm install
   ```

2. **Configure environment**
   - Copy `.env.example` to `.env`
   - Set `REACT_APP_API_URL` (local backend: `http://localhost:5000`)
   - Set `REACT_APP_MAPBOX_TOKEN`

3. **Run locally**
   ```bash
   npm start
   ```

---

## Deployment Checklist for New Team Member

### Initial Setup

- [ ] AWS account access granted
- [ ] AWS CLI configured (`aws configure`)
- [ ] GitHub repository access
- [ ] IAM roles created (or access to create them)
- [ ] GitHub secrets configured
- [ ] OIDC provider configured for GitHub Actions

### First Deployment

- [ ] Verify RDS database is accessible
- [ ] Verify S3 buckets exist and are accessible
- [ ] Verify ECR repository exists
- [ ] Build and push Docker image to ECR manually (if needed)
- [ ] Create App Runner service (if not exists)
- [ ] Test backend health endpoint
- [ ] Deploy frontend to S3
- [ ] Verify CloudFront distribution

### Ongoing Development

- [ ] Push changes to `main` or `production` branch
- [ ] Monitor GitHub Actions workflows
- [ ] Verify deployments in AWS Console
- [ ] Test application endpoints

---

## Troubleshooting

### Backend Not Deploying

1. Check GitHub Actions logs
2. Verify `AWS_ROLE_ARN` secret is correct
3. Verify ECR push succeeded
4. Check App Runner service logs
5. Verify environment variables in App Runner

### Frontend Not Updating

1. Check GitHub Actions logs
2. Verify S3 upload succeeded
3. Check CloudFront invalidation
4. Clear browser cache

### Database Connection Issues

1. Verify RDS security group allows App Runner
2. Check `DATABASE_URL` in Parameter Store or secret
3. Verify database is running
4. Check network connectivity

### CI/CD Not Triggering

1. Verify branch name (`main` or `production`)
2. Check file paths in workflow triggers
3. Verify workflow file syntax
4. Check GitHub Actions permissions

---

## Important Files

- **`.github/workflows/deploy-backend.yml`**: Backend CI/CD
- **`.github/workflows/deploy-frontend.yml`**: Frontend CI/CD
- **`reland-backend/Dockerfile`**: Backend container definition
- **`reland-backend/app.py`**: Flask application entry point
- **`reland-frontend/package.json`**: Frontend dependencies
- **`DEPLOYMENT_DETAILED_DOCUMENTATION.md`**: Detailed AWS setup

---

## Cost Estimate

Approximate monthly costs:
- RDS: ~$15/month
- S3: ~$1/month
- CloudFront: ~$1/month
- App Runner: ~$20/month (with traffic)
- EC2: On-demand (Spot instances for training)
- **Total: ~$38.95/month**

---

## Security Notes

- Database credentials stored in Parameter Store (SecureString)
- HTTPS enforced via CloudFront
- Private RDS subnet (not publicly accessible)
- IAM roles follow least privilege principle
- OIDC for GitHub Actions (no long-lived credentials)

---

## Support

For detailed deployment information, see:
- `DEPLOYMENT_DETAILED_DOCUMENTATION.md`
- `reland-backend/README.md`
- `reland-frontend/README.md`
- `.github/workflows/README.md`
