# GitHub Actions Workflows

This directory contains GitHub Actions workflows for automated deployment of the RELand application.

## Workflows

### 1. `deploy-backend.yml`
Deploys the backend Flask application to AWS App Runner.

**Triggers:**
- Push to `main` or `production` branch
- Changes in `reland-backend/**` directory
- Manual trigger via GitHub UI

**Steps:**
1. Checkout code
2. Configure AWS credentials (using OIDC)
3. Login to Amazon ECR
4. Build Docker image
5. Push image to ECR
6. Deploy to App Runner
7. Wait for deployment
8. Health check

### 2. `deploy-frontend.yml`
Deploys the frontend React application to S3 and invalidates CloudFront cache.

**Triggers:**
- Push to `main` or `production` branch
- Changes in `reland-frontend/**` directory
- Manual trigger via GitHub UI

**Steps:**
1. Checkout code
2. Configure AWS credentials (using OIDC)
3. Setup Node.js
4. Install dependencies
5. Build React app
6. Upload to S3
7. Invalidate CloudFront cache

## Required GitHub Secrets

Configure these in: **Settings** → **Secrets and variables** → **Actions**

| Secret | Description |
|--------|-------------|
| `AWS_ROLE_ARN` | IAM role ARN for GitHub Actions (OIDC) |
| `REACT_APP_API_URL` | Backend API URL for frontend build |
| `REACT_APP_MAPBOX_TOKEN` | Mapbox API token |
| `CLOUDFRONT_DISTRIBUTION_ID` | CloudFront distribution ID |

## Setup Instructions

See [PRODUCTION_DEPLOYMENT_GUIDE.md](../PRODUCTION_DEPLOYMENT_GUIDE.md) for complete setup instructions.

## Manual Trigger

You can manually trigger workflows:
1. Go to **Actions** tab
2. Select workflow
3. Click **Run workflow**
4. Select branch and run

## Monitoring

- View workflow runs in **Actions** tab
- Check logs for each step
- Set up notifications for failures

