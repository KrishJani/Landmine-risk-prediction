# RELand Production Deployment Guide

## Overview

This guide provides essential steps to deploy the RELand application to AWS production.

**Architecture:**
- Frontend: S3 + CloudFront (CDN)
- Backend API: AWS App Runner (Flask)
- Database: RDS PostgreSQL (with PostGIS)
- ML Training: EC2 Spot Instances (g4dn.xlarge GPU)
- Storage: S3 (models), ECR (Docker images)

**Monthly Cost:** ~$38.95/month

---

## Prerequisites

1. AWS Account with appropriate permissions
2. AWS CLI installed and configured
3. Docker installed (for building images)
4. GitHub repository with code

---

## Step 1: Database Setup (RDS PostgreSQL)

### 1.1 Create RDS Subnet Group

1. AWS Console → RDS → Subnet groups → Create DB subnet group
2. Name: `reland-db-subnet-group`
3. VPC: Select your default VPC
4. Availability Zones: Select 2+ AZs
5. Subnets: Select subnets in chosen AZs

### 1.2 Create Security Group

1. EC2 Console → Security Groups → Create security group
2. Name: `reland-rds-sg`
3. Inbound rule: PostgreSQL (port 5432) from VPC CIDR (e.g., `10.0.0.0/16`)

### 1.3 Create RDS Instance

1. RDS Console → Databases → Create database
2. Engine: PostgreSQL 15.4
3. Template: Production (or Free tier for testing)
4. Settings:
   - DB identifier: `reland-db`
   - Master username: `reland_admin`
   - Master password: [Generate strong password]
5. Instance: `db.t3.micro`
6. Storage: 20 GB (gp2)
7. Connectivity:
   - VPC: Default VPC
   - Subnet group: `reland-db-subnet-group`
   - Public access: **No**
   - Security group: `reland-rds-sg`
8. Database name: `reland_db`
9. Enable automated backups (7 days retention)
10. Click **Create database**

**Save:** Database endpoint, username, password

---

## Step 2: S3 Buckets

### 2.1 Frontend Bucket

```bash
aws s3 mb s3://reland-frontend-$(aws sts get-caller-identity --query Account --output text)
aws s3api put-bucket-website \
  --bucket reland-frontend-$(aws sts get-caller-identity --query Account --output text) \
  --website-configuration file://website-config.json
```

Create `website-config.json`:
```json
{
  "IndexDocument": {"Suffix": "index.html"},
  "ErrorDocument": {"Key": "index.html"}
}
```

### 2.2 Models Bucket

```bash
aws s3 mb s3://reland-models-$(aws sts get-caller-identity --query Account --output text)
```

---

## Step 3: ECR Repository

```bash
aws ecr create-repository --repository-name reland-backend --region us-east-1
```

**Save:** ECR repository URI

---

## Step 4: IAM Roles

### 4.1 App Runner Service Role

1. IAM Console → Roles → Create role
2. Trusted entity: App Runner
3. Permissions:
   - `AmazonEC2FullAccess` (to launch EC2 workers)
   - `AmazonS3FullAccess` (to access models bucket)
   - `AmazonEC2ContainerRegistryReadOnly` (to pull images)
4. Role name: `reland-apprunner-role`

### 4.2 EC2 Worker Role

1. IAM Console → Roles → Create role
2. Trusted entity: EC2
3. Permissions:
   - `AmazonS3FullAccess` (to save models)
   - `AmazonEC2FullAccess` (for self-termination)
4. Role name: `reland-ec2-worker-role`

---

## Step 5: Systems Manager Parameter Store

Store sensitive configuration:

```bash
# Database URL
aws ssm put-parameter \
  --name "/reland/database/url" \
  --value "postgresql://reland_admin:PASSWORD@RDS_ENDPOINT:5432/reland_db" \
  --type "SecureString" \
  --region us-east-1

# S3 Models Bucket
aws ssm put-parameter \
  --name "/reland/s3/models-bucket" \
  --value "reland-models-$(aws sts get-caller-identity --query Account --output text)" \
  --type "String" \
  --region us-east-1
```

---

## Step 6: EC2 Launch Template

### 6.1 Create Launch Template

1. EC2 Console → Launch Templates → Create launch template
2. Name: `reland-worker-template`
3. AMI: Deep Learning AMI (Ubuntu) with GPU support
4. Instance type: `g4dn.xlarge`
5. Key pair: [Your key pair]
6. Security group: [Allow SSH and database access]
7. IAM role: `reland-ec2-worker-role`
8. User data: Copy contents of `reland-backend/ec2-user-data.sh`
9. Storage: 50 GB gp3

---

## Step 7: App Runner Service

### 7.1 Build and Push Docker Image

```bash
cd reland-backend
docker build -t reland-backend .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ECR_URI
docker tag reland-backend:latest ECR_URI:latest
docker push ECR_URI:latest
```

### 7.2 Create App Runner Service

1. App Runner Console → Services → Create service
2. Source: Container registry → ECR
3. Container image: Select your ECR image
4. Service name: `reland-backend`
5. Port: `5001`
6. Environment variables:
   ```
   DATABASE_URL=postgresql://reland_admin:PASSWORD@RDS_ENDPOINT:5432/reland_db
   AWS_REGION=us-east-1
   S3_MODELS_BUCKET=reland-models-ACCOUNT_ID
   EC2_LAUNCH_TEMPLATE_NAME=reland-worker-template
   ```
7. Auto-scaling: Min 1, Max 1, Auto-pause enabled
8. Service role: `reland-apprunner-role`
9. Click **Create & deploy**

**Save:** Service URL

---

## Step 8: CloudFront Distribution

1. CloudFront Console → Distributions → Create distribution
2. Origin: S3 bucket (reland-frontend-ACCOUNT_ID)
3. Viewer protocol policy: Redirect HTTP to HTTPS
4. Default root object: `index.html`
5. Error pages: 404 → `/index.html` (200)
6. Click **Create distribution**

**Save:** Distribution ID and domain name

---

## Step 9: Deploy Frontend

### 9.1 Build React App

```bash
cd reland-frontend
npm install
REACT_APP_API_URL=https://YOUR_APP_RUNNER_URL npm run build
```

### 9.2 Upload to S3

```bash
aws s3 sync build/ s3://reland-frontend-ACCOUNT_ID --delete
```

### 9.3 Invalidate CloudFront

```bash
aws cloudfront create-invalidation \
  --distribution-id DISTRIBUTION_ID \
  --paths "/*"
```

---

## Step 10: Initialize Database

```bash
# Connect to RDS and run initialization
psql -h RDS_ENDPOINT -U reland_admin -d reland_db -f reland-backend/init_database.py
```

Or use the Python script:
```bash
cd reland-backend
python init_database.py
```

---

## Step 11: GitHub Actions (Optional - Automated Deployment)

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
      - name: Build and push Docker image
        run: |
          docker build -t reland-backend ./reland-backend
          aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_URI
          docker tag reland-backend:latest $ECR_URI:latest
          docker push $ECR_URI:latest
      - name: Deploy to App Runner
        run: |
          aws apprunner start-deployment --service-arn $APP_RUNNER_SERVICE_ARN

  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Build React app
        run: |
          cd reland-frontend
          npm install
          REACT_APP_API_URL=${{ secrets.API_URL }} npm run build
      - name: Deploy to S3
        run: |
          aws s3 sync reland-frontend/build/ s3://${{ secrets.S3_FRONTEND_BUCKET }} --delete
      - name: Invalidate CloudFront
        run: |
          aws cloudfront create-invalidation --distribution-id ${{ secrets.CLOUDFRONT_DIST_ID }} --paths "/*"
```

---

## Step 12: Testing

1. **Health Check:**
   ```bash
   curl https://YOUR_APP_RUNNER_URL/health
   ```

2. **Test API:**
   ```bash
   curl https://YOUR_APP_RUNNER_URL/api/initial_data
   ```

3. **Test Frontend:**
   - Open CloudFront distribution URL
   - Verify map loads
   - Test label creation
   - Test retrain model (creates job, polls status)

---

## Troubleshooting

### Database Connection Issues
- Check security group allows App Runner subnet
- Verify DATABASE_URL is correct
- Check RDS is in same VPC

### EC2 Worker Not Launching
- Verify IAM role has EC2 permissions
- Check launch template is correct
- Verify user data script is valid

### App Runner Deployment Fails
- Check Docker image builds successfully
- Verify ECR repository exists
- Check environment variables are set

---

## Cost Monitoring

Set up AWS Cost Explorer to monitor:
- RDS instance hours
- App Runner compute hours
- EC2 Spot instance usage
- S3 storage and requests
- CloudFront data transfer

Expected: ~$38.95/month

---

## Security Checklist

- [ ] RDS has public access disabled
- [ ] Security groups restrict access appropriately
- [ ] IAM roles follow least privilege
- [ ] S3 buckets have proper access policies
- [ ] CloudFront uses HTTPS
- [ ] Database credentials in Parameter Store (encrypted)

---

## Next Steps

1. Set up monitoring (CloudWatch)
2. Configure alerts for errors
3. Set up automated backups
4. Document runbooks for common issues

---

**For detailed AWS Console steps, see:** `AWS_CONSOLE_GUIDE_OPTIMIZED.md`

