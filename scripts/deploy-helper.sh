#!/bin/bash
# Helper script for AWS deployment
# This script helps automate some common deployment tasks

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="${PROJECT_NAME:-reland}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo -e "${GREEN}RELand AWS Deployment Helper${NC}"
echo "Project: $PROJECT_NAME"
echo "Region: $AWS_REGION"
echo "Account: $AWS_ACCOUNT_ID"
echo ""

# Function to check if resource exists
check_resource() {
    local resource_type=$1
    local resource_name=$2
    local check_cmd=$3
    
    if eval "$check_cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $resource_type '$resource_name' exists"
        return 0
    else
        echo -e "${RED}✗${NC} $resource_type '$resource_name' not found"
        return 1
    fi
}

# Function to setup AWS Systems Manager Parameter Store
setup_parameters() {
    echo -e "${YELLOW}Setting up AWS Systems Manager Parameter Store...${NC}"
    
    read -sp "Enter RDS Database URL (postgresql://user:pass@host:port/db): " DATABASE_URL
    echo ""
    
    read -sp "Enter Redis URL (redis://host:port/0): " REDIS_URL
    echo ""
    
    # Store parameters (encrypted)
    aws ssm put-parameter \
        --name "/reland/database/url" \
        --value "$DATABASE_URL" \
        --type "SecureString" \
        --overwrite \
        --region $AWS_REGION
    
    aws ssm put-parameter \
        --name "/reland/redis/url" \
        --value "$REDIS_URL" \
        --type "SecureString" \
        --overwrite \
        --region $AWS_REGION
    
    echo -e "${GREEN}✓ Parameters stored in Systems Manager${NC}"
}

# Function to check all resources
check_all_resources() {
    echo -e "${YELLOW}Checking AWS resources...${NC}"
    
    # Check RDS
    check_resource "RDS Instance" "${PROJECT_NAME}-db" \
        "aws rds describe-db-instances --db-instance-identifier ${PROJECT_NAME}-db --region $AWS_REGION"
    
    # Check S3 buckets
    check_resource "S3 Bucket" "${PROJECT_NAME}-web-${AWS_ACCOUNT_ID}" \
        "aws s3 ls s3://${PROJECT_NAME}-web-${AWS_ACCOUNT_ID} --region $AWS_REGION"
    
    check_resource "S3 Bucket" "${PROJECT_NAME}-models-${AWS_ACCOUNT_ID}" \
        "aws s3 ls s3://${PROJECT_NAME}-models-${AWS_ACCOUNT_ID} --region $AWS_REGION"
    
    # Check ECR
    check_resource "ECR Repository" "${PROJECT_NAME}-backend" \
        "aws ecr describe-repositories --repository-names ${PROJECT_NAME}-backend --region $AWS_REGION"
    
    # Check ElastiCache
    check_resource "ElastiCache Cluster" "${PROJECT_NAME}-redis" \
        "aws elasticache describe-cache-clusters --cache-cluster-id ${PROJECT_NAME}-redis --region $AWS_REGION"
    
    # Check App Runner
    check_resource "App Runner Service" "${PROJECT_NAME}-backend" \
        "aws apprunner list-services --region $AWS_REGION --query \"ServiceSummaryList[?ServiceName=='${PROJECT_NAME}-backend']\""
    
    # Check IAM roles
    check_resource "IAM Role" "${PROJECT_NAME}-apprunner-role" \
        "aws iam get-role --role-name ${PROJECT_NAME}-apprunner-role"
    
    check_resource "IAM Role" "${PROJECT_NAME}-ec2-worker-role" \
        "aws iam get-role --role-name ${PROJECT_NAME}-ec2-worker-role"
    
    echo ""
    echo -e "${GREEN}Resource check complete${NC}"
}

# Function to get service URLs
get_urls() {
    echo -e "${YELLOW}Getting service URLs...${NC}"
    
    # App Runner URL
    APP_RUNNER_ARN=$(aws apprunner list-services \
        --region $AWS_REGION \
        --query "ServiceSummaryList[?ServiceName=='${PROJECT_NAME}-backend'].ServiceArn" \
        --output text 2>/dev/null)
    
    if [ ! -z "$APP_RUNNER_ARN" ] && [ "$APP_RUNNER_ARN" != "None" ]; then
        APP_RUNNER_URL=$(aws apprunner describe-service \
            --service-arn $APP_RUNNER_ARN \
            --region $AWS_REGION \
            --query 'Service.ServiceUrl' \
            --output text)
        echo -e "${GREEN}Backend API:${NC} $APP_RUNNER_URL"
    else
        echo -e "${RED}App Runner service not found${NC}"
    fi
    
    # CloudFront URL
    DISTRIBUTION_ID=$(aws cloudfront list-distributions \
        --query "DistributionList.Items[?Comment=='RELand Frontend Distribution'].Id" \
        --output text 2>/dev/null)
    
    if [ ! -z "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "None" ]; then
        CLOUDFRONT_URL=$(aws cloudfront get-distribution \
            --id $DISTRIBUTION_ID \
            --query 'Distribution.DomainName' \
            --output text)
        echo -e "${GREEN}Frontend (CloudFront):${NC} https://$CLOUDFRONT_URL"
    else
        echo -e "${RED}CloudFront distribution not found${NC}"
    fi
    
    # RDS Endpoint
    RDS_ENDPOINT=$(aws rds describe-db-instances \
        --db-instance-identifier ${PROJECT_NAME}-db \
        --region $AWS_REGION \
        --query 'DBInstances[0].Endpoint.Address' \
        --output text 2>/dev/null)
    
    if [ ! -z "$RDS_ENDPOINT" ] && [ "$RDS_ENDPOINT" != "None" ]; then
        echo -e "${GREEN}RDS Endpoint:${NC} $RDS_ENDPOINT:5432"
    else
        echo -e "${RED}RDS instance not found${NC}"
    fi
    
    # Redis Endpoint
    REDIS_ENDPOINT=$(aws elasticache describe-cache-clusters \
        --cache-cluster-id ${PROJECT_NAME}-redis \
        --show-cache-node-info \
        --region $AWS_REGION \
        --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
        --output text 2>/dev/null)
    
    REDIS_PORT=$(aws elasticache describe-cache-clusters \
        --cache-cluster-id ${PROJECT_NAME}-redis \
        --show-cache-node-info \
        --region $AWS_REGION \
        --query 'CacheClusters[0].CacheNodes[0].Endpoint.Port' \
        --output text 2>/dev/null)
    
    if [ ! -z "$REDIS_ENDPOINT" ] && [ "$REDIS_ENDPOINT" != "None" ]; then
        echo -e "${GREEN}Redis Endpoint:${NC} $REDIS_ENDPOINT:$REDIS_PORT"
    else
        echo -e "${RED}Redis cluster not found${NC}"
    fi
}

# Function to update backend environment
update_backend_env() {
    echo -e "${YELLOW}Updating backend environment...${NC}"
    
    # Get current values
    APP_RUNNER_ARN=$(aws apprunner list-services \
        --region $AWS_REGION \
        --query "ServiceSummaryList[?ServiceName=='${PROJECT_NAME}-backend'].ServiceArn" \
        --output text 2>/dev/null)
    
    if [ -z "$APP_RUNNER_ARN" ] || [ "$APP_RUNNER_ARN" == "None" ]; then
        echo -e "${RED}App Runner service not found${NC}"
        return 1
    fi
    
    # Get current service configuration
    aws apprunner describe-service \
        --service-arn $APP_RUNNER_ARN \
        --region $AWS_REGION \
        > /tmp/apprunner-config.json
    
    echo "Current App Runner configuration saved to /tmp/apprunner-config.json"
    echo "Edit this file and update the service with:"
    echo "  aws apprunner update-service --service-arn $APP_RUNNER_ARN --source-configuration file:///tmp/apprunner-config.json"
}

# Function to deploy backend
deploy_backend() {
    echo -e "${YELLOW}Deploying backend...${NC}"
    
    cd reland-backend
    
    # Build Docker image
    echo "Building Docker image..."
    docker build -t ${PROJECT_NAME}-backend:latest .
    
    # Tag for ECR
    ECR_REPO_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-backend"
    docker tag ${PROJECT_NAME}-backend:latest ${ECR_REPO_URI}:latest
    
    # Login to ECR
    aws ecr get-login-password --region $AWS_REGION | \
        docker login --username AWS --password-stdin $ECR_REPO_URI
    
    # Push to ECR
    echo "Pushing to ECR..."
    docker push ${ECR_REPO_URI}:latest
    
    # Trigger App Runner deployment
    APP_RUNNER_ARN=$(aws apprunner list-services \
        --region $AWS_REGION \
        --query "ServiceSummaryList[?ServiceName=='${PROJECT_NAME}-backend'].ServiceArn" \
        --output text)
    
    if [ ! -z "$APP_RUNNER_ARN" ] && [ "$APP_RUNNER_ARN" != "None" ]; then
        echo "Triggering App Runner deployment..."
        aws apprunner start-deployment \
            --service-arn $APP_RUNNER_ARN \
            --region $AWS_REGION
        echo -e "${GREEN}✓ Deployment triggered${NC}"
    else
        echo -e "${RED}App Runner service not found${NC}"
    fi
    
    cd ..
}

# Function to deploy frontend
deploy_frontend() {
    echo -e "${YELLOW}Deploying frontend...${NC}"
    
    cd reland-frontend
    
    # Build frontend
    echo "Building frontend..."
    npm run build
    
    # Upload to S3
    echo "Uploading to S3..."
    aws s3 sync build/ s3://${PROJECT_NAME}-web-${AWS_ACCOUNT_ID}/ \
        --delete \
        --cache-control "public, max-age=31536000, immutable" \
        --exclude "index.html" \
        --exclude "service-worker.js"
    
    aws s3 cp build/index.html s3://${PROJECT_NAME}-web-${AWS_ACCOUNT_ID}/index.html \
        --cache-control "no-cache, no-store, must-revalidate"
    
    # Invalidate CloudFront
    DISTRIBUTION_ID=$(aws cloudfront list-distributions \
        --query "DistributionList.Items[?Comment=='RELand Frontend Distribution'].Id" \
        --output text)
    
    if [ ! -z "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "None" ]; then
        echo "Invalidating CloudFront cache..."
        aws cloudfront create-invalidation \
            --distribution-id $DISTRIBUTION_ID \
            --paths "/*"
        echo -e "${GREEN}✓ Frontend deployed and cache invalidated${NC}"
    else
        echo -e "${YELLOW}CloudFront distribution not found, skipping invalidation${NC}"
    fi
    
    cd ..
}

# Main menu
show_menu() {
    echo ""
    echo "Select an option:"
    echo "1) Check all resources"
    echo "2) Get service URLs"
    echo "3) Setup AWS Systems Manager parameters"
    echo "4) Deploy backend"
    echo "5) Deploy frontend"
    echo "6) Update backend environment"
    echo "7) Exit"
    echo ""
    read -p "Enter choice [1-7]: " choice
    
    case $choice in
        1) check_all_resources ;;
        2) get_urls ;;
        3) setup_parameters ;;
        4) deploy_backend ;;
        5) deploy_frontend ;;
        6) update_backend_env ;;
        7) exit 0 ;;
        *) echo -e "${RED}Invalid option${NC}" ;;
    esac
    
    show_menu
}

# Run menu
show_menu

