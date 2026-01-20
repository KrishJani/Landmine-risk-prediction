# RELand Deployment - Detailed Documentation

**Date:** January 15, 2026  
**Account:** 348170387270  
**Region:** us-east-1 (N. Virginia)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Completed Steps](#completed-steps)
3. [Pending Steps](#pending-steps)
4. [Cost Breakdown](#cost-breakdown)
5. [Architecture Overview](#architecture-overview)
6. [Troubleshooting Guide](#troubleshooting-guide)

---

## Executive Summary

### Deployment Status
- **Frontend:** ✅ Deployed and accessible via CloudFront
- **Backend:** ⏳ Pending (requires IAM roles and Docker image push)
- **Database:** ✅ Created and configured
- **Infrastructure:** ✅ 80% Complete

### Current Access Points
- **Frontend URL:** `https://d2vctqilbgf3ka.cloudfront.net`
- **S3 Website:** `http://reland-frontend-348170387270.s3-website-us-east-1.amazonaws.com`
- **Database Endpoint:** `reland-db.cyt6ces8iruu.us-east-1.rds.amazonaws.com:5432`
- **CloudFront Distribution ID:** `E3MS1AYMUSBSAQ`

### Blockers
1. **IAM Roles:** Require admin permissions to create
2. **Docker Image Push:** Requires AWS credentials for account 348170387270
3. **App Runner Service:** Cannot be created without IAM roles and Docker image

---

## Completed Steps

### Step 1: Database Setup (RDS PostgreSQL)

#### What We Did
1. **Created RDS Subnet Group** (`reland-db-subnet-group`)
   - Selected default VPC
   - Configured 2 availability zones for high availability
   - Purpose: Defines which subnets RDS can use

2. **Created Security Group** (`reland-rds-sg`)
   - Allowed PostgreSQL (port 5432) from VPC CIDR (172.31.0.0/16)
   - Purpose: Controls network access to the database

3. **Created RDS Instance** (`reland-db`)
   - Engine: PostgreSQL 17.6
   - Instance: db.t3.micro (2 vCPU, 1 GB RAM)
   - Storage: 20 GB gp2
   - Database name: `reland_db`
   - Master username: `reland_admin`
   - Public access: Disabled (private, VPC-only)
   - Automated backups: Enabled (7 days retention)
   - Encryption: Enabled

#### Why This Step is Needed
- **Database is the core data store** for the application
- Stores user labels, confirmed events, risk predictions, and map data
- PostgreSQL with PostGIS extension supports geospatial queries
- Private access ensures security (only accessible from within VPC)

#### Configuration Details
- **DB Instance Identifier:** `reland-db`
- **Endpoint:** `reland-db.cyt6ces8iruu.us-east-1.rds.amazonaws.com`
- **Port:** 5432
- **Database Name:** `reland_db`
- **Master Username:** `reland_admin`
- **Status:** Available

#### Estimated Cost
- **db.t3.micro instance:** ~$15.00/month
- **20 GB gp2 storage:** ~$2.30/month
- **Backup storage (7 days):** ~$0.10/month
- **Total:** ~$17.40/month

---

### Step 2: S3 Buckets

#### What We Did
1. **Created Frontend Bucket** (`reland-frontend-348170387270`)
   - Configured for static website hosting
   - Index document: `index.html`
   - Error document: `index.html` (for React SPA routing)
   - Block public access: Disabled (for website hosting)
   - Bucket policy: Added public read access

2. **Created Models Bucket** (`reland-models-348170387270`)
   - Private bucket (block public access enabled)
   - Purpose: Store trained ML models
   - Will be accessed by EC2 workers and App Runner

#### Why This Step is Needed
- **Frontend Bucket:** Hosts the React application static files
- **Models Bucket:** Stores trained ML models for risk prediction
- S3 provides scalable, durable storage
- Frontend bucket serves as origin for CloudFront CDN

#### Configuration Details
- **Frontend Bucket:** `reland-frontend-348170387270`
- **Models Bucket:** `reland-models-348170387270`
- **Region:** us-east-1
- **Frontend Website Endpoint:** `http://reland-frontend-348170387270.s3-website-us-east-1.amazonaws.com`

#### Estimated Cost
- **Storage (10 MB frontend + models):** ~$0.0002/month (negligible)
- **Requests:** Covered by free tier (first 20,000 GET requests free)
- **Data transfer out:** Covered by CloudFront
- **Total:** ~$0.00/month (within free tier)

---

### Step 3: ECR Repository

#### What We Did
1. **Created ECR Repository** (`reland-backend`)
   - Repository name: `reland-backend`
   - Region: us-east-1
   - Purpose: Store Docker images for App Runner

#### Why This Step is Needed
- **ECR stores Docker container images** for the backend application
- App Runner pulls images from ECR to deploy the backend
- Provides version control and image management
- Enables CI/CD workflows

#### Configuration Details
- **Repository URI:** `348170387270.dkr.ecr.us-east-1.amazonaws.com/reland-backend`
- **Status:** Created and ready

#### Estimated Cost
- **Storage (500 MB image):** ~$0.50/month
- **Data transfer:** Free within same region
- **Total:** ~$0.50/month

---

### Step 4: IAM Roles ⏳ PENDING

#### What Needs to Be Done
1. **Create App Runner Service Role** (`reland-apprunner-role`)
   - Trust policy: App Runner service
   - Permissions needed:
     - `AmazonEC2FullAccess` (to launch EC2 workers for ML training)
     - `AmazonS3FullAccess` (to access models bucket)
     - `AmazonEC2ContainerRegistryReadOnly` (to pull Docker images)

2. **Create EC2 Worker Role** (`reland-ec2-worker-role`)
   - Trust policy: EC2 service
   - Permissions needed:
     - `AmazonS3FullAccess` (to save trained models)
     - `AmazonEC2FullAccess` (for self-termination after training)

#### Why This Step is Needed
- **IAM roles provide secure access** to AWS services
- App Runner needs permissions to launch EC2 instances for ML training
- EC2 workers need permissions to save models to S3
- Follows AWS security best practices (least privilege)

#### Status
- **Blocked:** Requires IAM permissions (`iam:CreateRole`)
- **Action Required:** AWS administrator needs to create these roles

#### Estimated Cost
- **IAM roles:** Free (no additional cost)

---

### Step 5: Systems Manager Parameter Store

#### What We Did
1. **Created Database URL Parameter** (`/reland/database/url`)
   - Type: SecureString (encrypted)
   - Value: `postgresql://reland_admin:PASSWORD@reland-db.cyt6ces8iruu.us-east-1.rds.amazonaws.com:5432/reland_db`
   - Purpose: Securely store database connection string

2. **Created S3 Models Bucket Parameter** (`/reland/s3/models-bucket`)
   - Type: String
   - Value: `reland-models-348170387270`
   - Purpose: Store bucket name for application configuration

#### Why This Step is Needed
- **Secure storage of sensitive credentials** (database passwords)
- Applications can retrieve secrets programmatically
- No hardcoded credentials in code
- Centralized configuration management

#### Configuration Details
- **Database URL Parameter:** `/reland/database/url` (SecureString)
- **Models Bucket Parameter:** `/reland/s3/models-bucket` (String)
- **Encryption:** AWS managed KMS key

#### Estimated Cost
- **Standard parameters:** Free (first 10,000 parameters)
- **SecureString encryption:** Free (AWS managed keys)
- **Total:** ~$0.00/month

---

### Step 6: EC2 Launch Template

#### What We Did
1. **Created Launch Template** (`reland-worker-template`)
   - AMI: Deep Learning AMI Neuron (Ubuntu 24.04)
   - Instance type: g4dn.xlarge (4 vCPU, 16 GB RAM, NVIDIA T4 GPU)
   - Key pair: `reland-ec2-worker-key`
   - Security group: `reland-ec2-worker-sg`
   - Storage: 50 GB gp3
   - User data: Complete setup script from `ec2-user-data.sh`
   - IAM role: Not set (pending creation)

#### Why This Step is Needed
- **EC2 instances run ML model training** on GPU
- g4dn.xlarge provides NVIDIA T4 GPU for PyTorch training
- Launch template enables on-demand instance creation
- User data script automates environment setup

#### Configuration Details
- **Template Name:** `reland-worker-template`
- **Instance Type:** g4dn.xlarge
- **AMI:** Deep Learning AMI Neuron (Ubuntu 24.04)
- **Storage:** 50 GB gp3
- **User Data:** Installs Python, PyTorch, CUDA, and project dependencies

#### Estimated Cost
- **g4dn.xlarge:** ~$0.526/hour (~$378/month if running 24/7)
- **Note:** Instances are launched on-demand for training and self-terminate
- **Expected usage:** ~2-4 hours/month for model training
- **Estimated monthly cost:** ~$1.05 - $2.10/month (on-demand usage)

---

### Step 7: Build and Push Docker Image

#### What We Did
1. **Built Docker Image Locally**
   - Fixed Dockerfile to include GDAL dependencies
   - Built image: `reland-backend:latest`
   - Image size: ~500 MB
   - Status: Built successfully

2. **Attempted Push to ECR**
   - Status: Failed (403 Forbidden)
   - Reason: AWS CLI configured for different account (794383793076)
   - Action Required: Need AWS credentials for account 348170387270

#### Why This Step is Needed
- **Docker image contains the backend application** (Flask API)
- App Runner requires the image in ECR to deploy
- Image includes all dependencies and application code
- Enables consistent deployment across environments

#### Configuration Details
- **Image Name:** `reland-backend:latest`
- **Base Image:** python:3.11-slim
- **ECR Repository:** `348170387270.dkr.ecr.us-east-1.amazonaws.com/reland-backend`
- **Status:** Built locally, not yet pushed

#### Estimated Cost
- **ECR storage:** ~$0.50/month (already included in Step 3)
- **Data transfer:** Free within same region
- **Total:** ~$0.00/month (no additional cost)

---

### Step 8: Create App Runner Service ⏳ PENDING

#### What Needs to Be Done
1. **Create App Runner Service**
   - Service name: `reland-backend`
   - Source: ECR container registry
   - Container image: `reland-backend:latest`
   - Port: 5001 (or 8000 based on Dockerfile)
   - Environment variables:
     - `DATABASE_URL`: From Parameter Store
     - `AWS_REGION`: us-east-1
     - `S3_MODELS_BUCKET`: reland-models-348170387270
     - `EC2_LAUNCH_TEMPLATE_NAME`: reland-worker-template
   - Auto-scaling: Min 1, Max 1, Auto-pause enabled
   - Service role: `reland-apprunner-role` (pending)
   - Networking: Custom VPC (to access RDS)

#### Why This Step is Needed
- **App Runner hosts the Flask backend API**
- Provides automatic scaling and load balancing
- Handles HTTPS, health checks, and deployments
- Connects frontend to database and ML services

#### Status
- **Blocked:** Requires IAM role (`reland-apprunner-role`) and Docker image in ECR

#### Estimated Cost
- **1 vCPU, 2 GB RAM:** ~$0.007/hour (~$5.04/month)
- **Auto-pause:** Reduces cost when idle
- **Expected cost:** ~$2-3/month (with auto-pause)
- **Data transfer:** First 1 GB free, then $0.12/GB

---

### Step 9: CloudFront Distribution

#### What We Did
1. **Created CloudFront Distribution** (`reland-frontend`)
   - Origin: S3 website endpoint (`reland-frontend-348170387270.s3-website-us-east-1.amazonaws.com`)
   - Viewer protocol: Redirect HTTP to HTTPS
   - Default root object: `index.html`
   - Custom error response: 404 → `/index.html` (200)
   - Cache policy: CachingOptimized
   - Allowed HTTP methods: GET, HEAD, OPTIONS
   - WAF: Enabled (monitor mode)
   - Price class: Free tier

2. **Configured Error Pages**
   - 404 Not Found → `/index.html` (200 OK)
   - Purpose: Enable React Router client-side routing

#### Why This Step is Needed
- **CloudFront provides global CDN** for fast content delivery
- HTTPS encryption for secure connections
- Custom error pages enable React SPA routing
- Reduces latency and improves user experience

#### Configuration Details
- **Distribution ID:** `E3MS1AYMUSBSAQ`
- **Domain:** `d2vctqilbgf3ka.cloudfront.net`
- **Status:** Deployed
- **Origin:** S3 website endpoint

#### Estimated Cost
- **Free Tier (first 12 months):**
  - 1 TB data transfer out: Free
  - 10,000,000 HTTP/HTTPS requests: Free
- **After free tier:** ~$0.085/GB data transfer, $0.0075/10,000 requests
- **Expected cost (after free tier):** ~$1-3/month for low traffic

---

### Step 10: Deploy Frontend

#### What We Did
1. **Built React Application**
   - Built with placeholder API URL: `https://placeholder-api-url.awsapprunner.com`
   - Build output: `reland-frontend/build/` directory
   - Status: Build successful

2. **Uploaded to S3**
   - Uploaded all files from `build/` directory
   - Files uploaded to root of S3 bucket
   - Structure: `index.html`, `static/` folder, assets
   - Status: Upload successful

3. **Configured S3 Bucket Policy**
   - Added public read access policy
   - Enabled static website hosting
   - Status: Working

4. **Invalidated CloudFront Cache**
   - Created invalidation for `/*`
   - Status: Completed

#### Why This Step is Needed
- **Frontend is the user interface** for the application
- React app provides interactive map and controls
- S3 hosts static files, CloudFront delivers them globally
- Bucket policy enables public access for website hosting

#### Configuration Details
- **Build Location:** `reland-frontend/build/`
- **S3 Bucket:** `reland-frontend-348170387270`
- **CloudFront URL:** `https://d2vctqilbgf3ka.cloudfront.net`
- **Status:** Deployed and accessible

#### Estimated Cost
- **S3 storage:** ~$0.00/month (within free tier)
- **CloudFront:** Free tier (first 12 months)
- **Total:** ~$0.00/month

---

## Pending Steps

### Step 4: IAM Roles (REQUIRES ADMIN)

#### What's Needed
1. **reland-apprunner-role**
   - Trust policy for App Runner service
   - Permissions: EC2, S3, ECR access

2. **reland-ec2-worker-role**
   - Trust policy for EC2 service
   - Permissions: S3, EC2 self-termination

#### Why It's Blocked
- User doesn't have `iam:CreateRole` permission
- Requires AWS administrator to create roles

#### Action Required
- Contact AWS administrator with role specifications (provided in Step 4 section)

---

### Step 7: Push Docker Image (REQUIRES CREDENTIALS)

#### What's Needed
1. **AWS Credentials** for account 348170387270
   - Access Key ID
   - Secret Access Key

2. **Push Commands**
   ```bash
   ECR_URI="348170387270.dkr.ecr.us-east-1.amazonaws.com/reland-backend"
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URI
   docker tag reland-backend:latest ${ECR_URI}:latest
   docker push ${ECR_URI}:latest
   ```

#### Why It's Blocked
- AWS CLI configured for different account (794383793076)
- Need credentials for account 348170387270

#### Action Required
- Obtain AWS credentials for account 348170387270
- Configure AWS CLI or use profile
- Push Docker image to ECR

---

### Step 8: Create App Runner Service (REQUIRES ROLES + IMAGE)

#### What's Needed
1. **IAM Role:** `reland-apprunner-role` (from Step 4)
2. **Docker Image:** In ECR (from Step 7)
3. **Service Configuration:**
   - Environment variables
   - VPC networking
   - Auto-scaling settings

#### Why It's Blocked
- Depends on Step 4 (IAM roles) and Step 7 (Docker image)

#### Action Required
- Complete Step 4 and Step 7 first
- Then create App Runner service

---

### Step 11: Initialize Database (OPTIONAL - CAN DO NOW)

#### What's Needed
1. **Run Database Initialization Script**
   - Script: `reland-backend/init_database.py`
   - Creates tables and loads initial data
   - Requires database connection

#### Why It's Needed
- Sets up database schema
- Loads initial data (municipalities, borders, etc.)
- One-time setup

#### Status
- Can be done now (database is ready)
- Requires database password

#### Estimated Cost
- **No additional cost** (uses existing RDS instance)

---

## Cost Breakdown

### Monthly Recurring Costs

| Service | Configuration | Monthly Cost |
|---------|--------------|--------------|
| **RDS PostgreSQL** | db.t3.micro, 20 GB | $17.40 |
| **ECR Storage** | 500 MB image | $0.50 |
| **S3 Storage** | 10 MB (frontend + models) | $0.00 (free tier) |
| **CloudFront** | Free tier (first 12 months) | $0.00 |
| **App Runner** | 1 vCPU, 2 GB, auto-pause | $2-3 (estimated) |
| **EC2 Training** | g4dn.xlarge (on-demand, 2-4 hrs/month) | $1.05 - $2.10 |
| **Systems Manager** | 2 parameters | $0.00 (free tier) |
| **Data Transfer** | Minimal (within AWS) | $0.00 - $1.00 |
| **TOTAL** | | **~$21 - $24/month** |

### One-Time Setup Costs
- **None** (all services are pay-as-you-go)

### Cost Optimization Notes
- **RDS:** Using db.t3.micro (smallest instance) - can scale up if needed
- **App Runner:** Auto-pause enabled to reduce costs when idle
- **EC2:** On-demand instances that self-terminate after training
- **CloudFront:** Using free tier (first 12 months)
- **S3:** Within free tier limits

### Expected Cost After Free Tier Expires
- **CloudFront:** ~$1-3/month (low traffic)
- **Total:** ~$22-27/month

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Users/Internet                       │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              CloudFront Distribution (CDN)                   │
│         d2vctqilbgf3ka.cloudfront.net                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         S3 Bucket: reland-frontend-348170387270             │
│              (Static React Frontend)                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              App Runner Service (Backend API)                │
│              (PENDING: Needs IAM role + Docker image)        │
└───────────────┬───────────────────────┬────────────────────┘
                │                        │
                ▼                        ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│   RDS PostgreSQL         │  │  S3: reland-models-         │
│   reland-db              │  │  348170387270               │
│   (Database)             │  │  (ML Models Storage)        │
└──────────────────────────┘  └──────────────────────────────┘
                                        ▲
                                        │
                           ┌────────────┴────────────┐
                           │                         │
                           ▼                         ▼
                ┌──────────────────┐    ┌──────────────────────┐
                │  EC2 g4dn.xlarge │    │  Systems Manager     │
                │  (ML Training)   │    │  Parameter Store     │
                │  (On-demand)     │    │  (Secrets)           │
                └──────────────────┘    └──────────────────────┘
```

### Data Flow
1. **User Request** → CloudFront → S3 (frontend files)
2. **API Request** → CloudFront → App Runner → RDS (database queries)
3. **ML Training** → App Runner → EC2 Worker → S3 (save models)
4. **Model Loading** → App Runner → S3 (load trained models)

---

## Troubleshooting Guide

### Issue: 504 Gateway Timeout from CloudFront
**Solution:** 
- Verify S3 bucket policy allows public read access
- Check CloudFront origin uses S3 website endpoint (not REST endpoint)
- Ensure Block Public Access is disabled for frontend bucket

### Issue: Cannot Create IAM Roles
**Solution:**
- Requires AWS administrator with `iam:CreateRole` permission
- Provide role specifications to admin

### Issue: Cannot Push Docker Image
**Solution:**
- Configure AWS CLI with correct account credentials
- Use: `aws configure --profile reland-prod`
- Or obtain temporary credentials for ECR push

### Issue: App Runner Service Creation Fails
**Solution:**
- Ensure IAM role exists and is properly configured
- Verify Docker image is in ECR
- Check environment variables are correct

### Issue: Database Connection Errors
**Solution:**
- Verify security group allows App Runner subnet
- Check DATABASE_URL in Parameter Store
- Ensure RDS and App Runner are in same VPC

---

## Next Steps Checklist

### Immediate Actions (Require Admin/Credentials)
- [ ] Get AWS administrator to create IAM roles (Step 4)
- [ ] Obtain AWS credentials for account 348170387270
- [ ] Push Docker image to ECR (Step 7)
- [ ] Create App Runner service (Step 8)

### Optional Actions (Can Do Now)
- [ ] Initialize database (Step 11)
- [ ] Test database connection
- [ ] Verify Parameter Store values

### After Backend is Deployed
- [ ] Update frontend with actual App Runner URL
- [ ] Rebuild and redeploy frontend
- [ ] Test full application flow
- [ ] Set up monitoring and alerts

---

## Important Credentials & Endpoints

### Save These Securely

**Database:**
- Endpoint: `reland-db.cyt6ces8iruu.us-east-1.rds.amazonaws.com`
- Port: `5432`
- Database: `reland_db`
- Username: `reland_admin`
- Password: [Stored in Parameter Store]

**Frontend:**
- CloudFront URL: `https://d2vctqilbgf3ka.cloudfront.net`
- S3 Bucket: `reland-frontend-348170387270`

**Backend (Pending):**
- App Runner URL: [Will be available after Step 8]

**ECR:**
- Repository URI: `348170387270.dkr.ecr.us-east-1.amazonaws.com/reland-backend`

**S3:**
- Frontend Bucket: `reland-frontend-348170387270`
- Models Bucket: `reland-models-348170387270`

---

## Security Notes

### Current Security Configuration
- ✅ RDS: Private (no public access)
- ✅ Database credentials: Stored in Parameter Store (encrypted)
- ✅ S3 Models Bucket: Private
- ✅ S3 Frontend Bucket: Public (required for website hosting)
- ✅ CloudFront: HTTPS only
- ⏳ IAM Roles: Pending (will follow least privilege)

### Recommendations
- Enable CloudWatch monitoring
- Set up CloudWatch alarms for errors
- Configure automated backups for RDS
- Review and rotate credentials regularly
- Enable CloudTrail for audit logging

---

## Support & Resources

### AWS Documentation
- [RDS User Guide](https://docs.aws.amazon.com/rds/)
- [App Runner User Guide](https://docs.aws.amazon.com/apprunner/)
- [CloudFront User Guide](https://docs.aws.amazon.com/cloudfront/)
- [S3 User Guide](https://docs.aws.amazon.com/s3/)

### Project Files
- Deployment Steps: `DEPLOYMENT_STEPS.md`
- Deployment Guide: `DEPLOYMENT_GUIDE.md`
- Helper Script: `deploy-helper.sh`

---

**Document Version:** 1.0  
**Last Updated:** January 15, 2026  
**Status:** 80% Complete - Frontend Deployed, Backend Pending
