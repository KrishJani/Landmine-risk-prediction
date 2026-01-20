# RELand Deployment Steps - Quick Reference

## Prerequisites Checklist

**On your local machine (where you'll run deployment commands):**
- [ ] AWS Account with appropriate permissions
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] Docker installed and running (for building backend Docker image)
- [ ] Node.js and npm installed (for frontend build)
- [ ] PostgreSQL client tools installed (optional, for database access)

**Note:** Docker is needed on your local machine to build the Docker image before pushing to ECR. AWS App Runner will pull the image from ECR, so Docker doesn't need to be installed in AWS.

---

## Step-by-Step Deployment

### Step 1: Database Setup (RDS PostgreSQL)

1. **Create RDS Subnet Group**
   - AWS Console → RDS → Subnet groups → Create DB subnet group
   - Name: `reland-db-subnet-group`
   - VPC: Select your default VPC
   - Availability Zones: Select 2+ AZs
   - Subnets: Select subnets in chosen AZs

2. **Create Security Group**
   - EC2 Console → Security Groups → Create security group
   - Name: `reland-rds-sg`
   - Inbound rule: PostgreSQL (port 5432) from VPC CIDR (e.g., `10.0.0.0/16`)

3. **Create RDS Instance**
   - RDS Console → Databases → Create database
   - Engine: PostgreSQL 15.4
   - Template: Production (or Free tier for testing)
   - DB identifier: `reland-db`
   - Master username: `reland_admin`
   - Master password: [Generate strong password - SAVE THIS]
   - Instance: `db.t3.micro`
   - Storage: 20 GB (gp2)
   - VPC: Default VPC
   - Subnet group: `reland-db-subnet-group`
   - Public access: **No**
   - Security group: `reland-rds-sg`
   - Database name: `reland_db`
   - Enable automated backups (7 days retention)
   - Click **Create database**

**SAVE:** Database endpoint, username, password

---

### Step 2: S3 Buckets

1. **Create Frontend Bucket**
   ```bash
   aws s3 mb s3://reland-frontend-$(aws sts get-caller-identity --query Account --output text)
   ```

2. **Configure Frontend Bucket for Static Website**
   - Create `website-config.json`:
     ```json
     {
       "IndexDocument": {"Suffix": "index.html"},
       "ErrorDocument": {"Key": "index.html"}
     }
     ```
   - Apply configuration:
     ```bash
     aws s3api put-bucket-website \
       --bucket reland-frontend-$(aws sts get-caller-identity --query Account --output text) \
       --website-configuration file://website-config.json
     ```

3. **Create Models Bucket**
   ```bash
   aws s3 mb s3://reland-models-$(aws sts get-caller-identity --query Account --output text)
   ```

---

### Step 3: ECR Repository

```bash
aws ecr create-repository --repository-name reland-backend --region us-east-1
```

**SAVE:** ECR repository URI (format: `ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/reland-backend`)

---

### Step 4: IAM Roles

1. **App Runner Service Role**
   - IAM Console → Roles → Create role
   - Trusted entity: App Runner
   - Permissions:
     - `AmazonEC2FullAccess` (to launch EC2 workers)
     - `AmazonS3FullAccess` (to access models bucket)
     - `AmazonEC2ContainerRegistryReadOnly` (to pull images)
   - Role name: `reland-apprunner-role`

2. **EC2 Worker Role**
   - IAM Console → Roles → Create role
   - Trusted entity: EC2
   - Permissions:
     - `AmazonS3FullAccess` (to save models)
     - `AmazonEC2FullAccess` (for self-termination)
   - Role name: `reland-ec2-worker-role`

---

### Step 5: Systems Manager Parameter Store

Store sensitive configuration:

```bash
# Get your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Database URL (replace with your actual RDS endpoint and password)
aws ssm put-parameter \
  --name "/reland/database/url" \
  --value "postgresql://reland_admin:YOUR_PASSWORD@YOUR_RDS_ENDPOINT:5432/reland_db" \
  --type "SecureString" \
  --region us-east-1

# S3 Models Bucket
aws ssm put-parameter \
  --name "/reland/s3/models-bucket" \
  --value "reland-models-${ACCOUNT_ID}" \
  --type "String" \
  --region us-east-1
```

---

### Step 6: EC2 Launch Template

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

### Step 7: Build and Push Docker Image

**Note:** This step is performed on your local machine (where Docker is installed). The Docker image is built locally, then pushed to AWS ECR, where App Runner will pull it from.

```bash
cd reland-backend

# Build Docker image (runs on your local machine)
docker build -t reland-backend .

# Get ECR login
ECR_URI=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com/reland-backend
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URI

# Tag and push to ECR
docker tag reland-backend:latest $ECR_URI:latest
docker push $ECR_URI:latest

cd ..
```

---

### Step 8: Create App Runner Service

1. App Runner Console → Services → Create service
2. Source: Container registry → ECR
3. Container image: Select your ECR image (`reland-backend:latest`)
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

**SAVE:** Service URL (e.g., `https://xxxxx.us-east-1.awsapprunner.com`)

---

### Step 9: CloudFront Distribution

1. CloudFront Console → Distributions → Create distribution
2. Origin: S3 bucket (reland-frontend-ACCOUNT_ID)
3. Viewer protocol policy: Redirect HTTP to HTTPS
4. Default root object: `index.html`
5. Error pages: 404 → `/index.html` (200)
6. Comment: `RELand Frontend Distribution`
7. Click **Create distribution**

**SAVE:** Distribution ID and domain name

---

### Step 10: Deploy Frontend

1. **Build React App**
   ```bash
   cd reland-frontend
   npm install
   REACT_APP_API_URL=https://YOUR_APP_RUNNER_URL npm run build
   ```

2. **Upload to S3**
   ```bash
   ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
   aws s3 sync build/ s3://reland-frontend-${ACCOUNT_ID} --delete
   ```

3. **Invalidate CloudFront**
   ```bash
   DISTRIBUTION_ID=$(aws cloudfront list-distributions \
     --query "DistributionList.Items[?Comment=='RELand Frontend Distribution'].Id" \
     --output text)
   aws cloudfront create-invalidation \
     --distribution-id $DISTRIBUTION_ID \
     --paths "/*"
   ```

---

### Step 11: Initialize Database

```bash
cd reland-backend

# Set DATABASE_URL environment variable
export DATABASE_URL="postgresql://reland_admin:PASSWORD@RDS_ENDPOINT:5432/reland_db"

# Run initialization script
python init_database.py
```

---

### Step 12: Verify Deployment

1. **Health Check**
   ```bash
   curl https://YOUR_APP_RUNNER_URL/health
   ```

2. **Test API**
   ```bash
   curl https://YOUR_APP_RUNNER_URL/api/initial_data
   ```

3. **Test Frontend**
   - Open CloudFront distribution URL
   - Verify map loads
   - Test label creation
   - Test retrain model functionality

---

## Using the Deployment Helper Script

For easier deployment, use the helper script:

```bash
chmod +x deploy-helper.sh
./deploy-helper.sh
```

The script provides options to:
- Check all resources
- Get service URLs
- Setup AWS Systems Manager parameters
- Deploy backend
- Deploy frontend
- Update backend environment

---

## Quick Deployment Commands

### Deploy Backend Only
```bash
./deploy-helper.sh
# Select option 4: Deploy backend
```

### Deploy Frontend Only
```bash
./deploy-helper.sh
# Select option 5: Deploy frontend
```

### Check All Resources
```bash
./deploy-helper.sh
# Select option 1: Check all resources
```

---

## Important Notes

- **Database Password**: Store securely, you'll need it for Parameter Store and App Runner
- **RDS Endpoint**: Takes 5-10 minutes to create, wait before proceeding
- **App Runner**: First deployment takes 5-10 minutes
- **CloudFront**: Distribution takes 15-20 minutes to deploy
- **Cost**: Expected ~$38.95/month

---

## Troubleshooting

### Database Connection Issues
- Verify security group allows App Runner subnet
- Check DATABASE_URL is correct in App Runner environment variables
- Ensure RDS is in same VPC as App Runner

### EC2 Worker Not Launching
- Verify IAM role has EC2 permissions
- Check launch template is correct
- Verify user data script is valid

### App Runner Deployment Fails
- Check Docker image builds successfully locally
- Verify ECR repository exists
- Check environment variables are set correctly

---

## Next Steps After Deployment

1. Set up CloudWatch monitoring and alerts
2. Configure automated backups
3. Set up GitHub Actions for CI/CD (optional)
4. Document runbooks for common issues
5. Set up cost monitoring in AWS Cost Explorer
