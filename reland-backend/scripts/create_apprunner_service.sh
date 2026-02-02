#!/bin/bash
set -e

# Script to create a new AWS App Runner service with proper health check configuration
# Usage: ./create_apprunner_service.sh
# 
# This script creates a new App Runner service with:
# - Proper health check configuration (/health endpoint)
# - Lenient health check settings for startup
# - All required environment variables
#
# IMPORTANT: This should only be run once to create the service.
# After creation, use manual_deploy.sh or GitHub Actions for updates.

echo "======================================================================"
echo "🚀 Creating New AWS App Runner Service"
echo "======================================================================"

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-reland-backend}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "Configuration:"
echo "  AWS Region: $AWS_REGION"
echo "  ECR Repository: $ECR_REPOSITORY"
echo "  App Runner Service: $APP_RUNNER_SERVICE"
echo "  Image Tag: $IMAGE_TAG"
echo ""

# Check if service already exists
SERVICE_ARN=$(aws apprunner list-services \
    --region ${AWS_REGION} \
    --query "ServiceSummaryList[?ServiceName=='${APP_RUNNER_SERVICE}'].ServiceArn" \
    --output text 2>/dev/null || echo "")

if [ -n "$SERVICE_ARN" ] && [ "$SERVICE_ARN" != "None" ]; then
    echo "⚠️  WARNING: App Runner service '${APP_RUNNER_SERVICE}' already exists!"
    echo "   Service ARN: $SERVICE_ARN"
    echo ""
    echo "   If you want to recreate it:"
    echo "   1. Delete the existing service first:"
    echo "      aws apprunner delete-service --service-arn $SERVICE_ARN --region $AWS_REGION"
    echo "   2. Wait for deletion to complete"
    echo "   3. Run this script again"
    echo ""
    echo "   Or use manual_deploy.sh to update the existing service"
    exit 1
fi

# Get AWS account ID and ECR registry
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

# Verify image exists in ECR
echo "======================================================================"
echo "1️⃣  Verifying ECR Image"
echo "======================================================================"

if ! aws ecr describe-images \
    --repository-name ${ECR_REPOSITORY} \
    --image-ids imageTag=${IMAGE_TAG} \
    --region ${AWS_REGION} &>/dev/null; then
    echo "❌ Error: Image ${IMAGE_URI} not found in ECR"
    echo "   Please build and push the image first:"
    echo "   cd reland-backend"
    echo "   docker build -t ${ECR_REPOSITORY}:${IMAGE_TAG} ."
    echo "   aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}"
    echo "   docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${IMAGE_URI}"
    echo "   docker push ${IMAGE_URI}"
    exit 1
fi

echo "✅ Image found: ${IMAGE_URI}"

# Get environment variables
echo ""
echo "======================================================================"
echo "2️⃣  Getting Environment Variables"
echo "======================================================================"

# Try to get DATABASE_URL from Parameter Store if not set
DATABASE_URL_SOURCE="shell"
if [ -z "$DATABASE_URL" ]; then
    echo "⚠️  DATABASE_URL not set. Attempting to retrieve from Parameter Store..."
    DATABASE_URL=$(aws ssm get-parameter \
        --name "/reland/database/url" \
        --region ${AWS_REGION} \
        --with-decryption \
        --query 'Parameter.Value' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$DATABASE_URL" ]; then
        echo "❌ DATABASE_URL not found in Parameter Store either."
        echo "   Please set it:"
        echo "   export DATABASE_URL='postgresql://user:pass@host:5432/db'"
        echo "   Or set it in Parameter Store: /reland/database/url"
        exit 1
    else
        DATABASE_URL_SOURCE="Parameter Store"
        echo "✅ Retrieved DATABASE_URL from Parameter Store"
    fi
fi

# Try to get S3_MODELS_BUCKET from Parameter Store if not set
if [ -z "$S3_MODELS_BUCKET" ]; then
    S3_MODELS_BUCKET=$(aws ssm get-parameter \
        --name "/reland/s3/models-bucket" \
        --region ${AWS_REGION} \
        --query 'Parameter.Value' \
        --output text 2>/dev/null || echo "")
fi

# Try to get SECRET_KEY from Parameter Store if not set
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(aws ssm get-parameter \
        --name "/reland/app/secret-key" \
        --region ${AWS_REGION} \
        --with-decryption \
        --query 'Parameter.Value' \
        --output text 2>/dev/null || echo "")
fi

# Try to get GOOGLE_GEOCODING_API_KEY from Parameter Store if not set
if [ -z "$GOOGLE_GEOCODING_API_KEY" ]; then
    GOOGLE_GEOCODING_API_KEY=$(aws ssm get-parameter \
        --name "/reland/app/google-geocoding-api-key" \
        --region ${AWS_REGION} \
        --with-decryption \
        --query 'Parameter.Value' \
        --output text 2>/dev/null || echo "")
fi

echo "Environment variables:"
echo "  DATABASE_URL: ${DATABASE_URL:0:50}*** (from ${DATABASE_URL_SOURCE})"
echo "  S3_MODELS_BUCKET: ${S3_MODELS_BUCKET:-Not set}"
echo "  SECRET_KEY: ${SECRET_KEY:+Set (hidden)}${SECRET_KEY:-Not set}"
echo "  GOOGLE_GEOCODING_API_KEY: ${GOOGLE_GEOCODING_API_KEY:+Set (hidden)}${GOOGLE_GEOCODING_API_KEY:-Not set}"

# Create service configuration JSON
echo ""
echo "======================================================================"
echo "3️⃣  Creating Service Configuration"
echo "======================================================================"

cat > /tmp/service-config.json <<EOF
{
  "ServiceName": "${APP_RUNNER_SERVICE}",
  "SourceConfiguration": {
    "ImageRepository": {
      "ImageIdentifier": "${IMAGE_URI}",
      "ImageConfiguration": {
        "Port": "8080",
        "RuntimeEnvironmentVariables": {
          "FLASK_ENV": "production",
          "ENVIRONMENT": "production",
          "DATABASE_URL": "${DATABASE_URL}",
          "AWS_REGION": "${AWS_REGION}",
          "S3_MODELS_BUCKET": "${S3_MODELS_BUCKET}",
          "EC2_LAUNCH_TEMPLATE_NAME": "${EC2_LAUNCH_TEMPLATE_NAME:-reland-worker-template}",
          "SECRET_KEY": "${SECRET_KEY:-change-me-in-production}",
          "GOOGLE_GEOCODING_API_KEY": "${GOOGLE_GEOCODING_API_KEY:-}",
          "USE_REDIS": "false",
          "PORT": "8080",
          "DEBUG": "False"
        },
        "StartCommand": "python3 /app/run.py"
      },
      "ImageRepositoryType": "ECR",
      "ImageRepositoryAccessRoleArn": ""
    },
    "AutoDeploymentsEnabled": false
  },
  "InstanceConfiguration": {
    "Cpu": "1 vCPU",
    "Memory": "2 GB"
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP",
    "Path": "/health",
    "Interval": 10,
    "Timeout": 10,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 10
  },
  "AutoScalingConfigurationArn": ""
}
EOF

echo "✅ Service configuration created"
echo ""
echo "Health Check Configuration:"
echo "  Protocol: HTTP"
echo "  Path: /health"
echo "  Interval: 10 seconds"
echo "  Timeout: 10 seconds"
echo "  Healthy Threshold: 1 (pass after 1 successful check)"
echo "  Unhealthy Threshold: 10 (allow 10 failures before marking unhealthy)"

# Create IAM role for App Runner to access ECR (if needed)
echo ""
echo "======================================================================"
echo "4️⃣  Checking IAM Role for ECR Access"
echo "======================================================================"

# App Runner needs a role to access ECR
# Check if a role exists, if not, we'll need to create one
ECR_ACCESS_ROLE_NAME="reland-apprunner-ecr-role"
ECR_ACCESS_ROLE_ARN=$(aws iam get-role \
    --role-name ${ECR_ACCESS_ROLE_NAME} \
    --query 'Role.Arn' \
    --output text 2>/dev/null || echo "")

if [ -z "$ECR_ACCESS_ROLE_ARN" ] || [ "$ECR_ACCESS_ROLE_ARN" == "None" ]; then
    echo "⚠️  IAM role '${ECR_ACCESS_ROLE_NAME}' not found"
    echo "   Creating IAM role for ECR access..."
    
    # Create trust policy for App Runner
    cat > /tmp/trust-policy.json <<'TRUSTEOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "build.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
TRUSTEOF

    # Create the role
    ECR_ACCESS_ROLE_ARN=$(aws iam create-role \
        --role-name ${ECR_ACCESS_ROLE_NAME} \
        --assume-role-policy-document file:///tmp/trust-policy.json \
        --query 'Role.Arn' \
        --output text)
    
    # Attach ECR read-only policy
    aws iam attach-role-policy \
        --role-name ${ECR_ACCESS_ROLE_NAME} \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
    
    echo "✅ Created IAM role: ${ECR_ACCESS_ROLE_ARN}"
else
    echo "✅ Found existing IAM role: ${ECR_ACCESS_ROLE_ARN}"
fi

# Update service config with role ARN
jq ".SourceConfiguration.ImageRepository.ImageRepositoryAccessRoleArn = \"${ECR_ACCESS_ROLE_ARN}\"" /tmp/service-config.json > /tmp/service-config-updated.json
mv /tmp/service-config-updated.json /tmp/service-config.json

# Create the service
echo ""
echo "======================================================================"
echo "5️⃣  Creating App Runner Service"
echo "======================================================================"

echo "Creating service (this may take a few minutes)..."
SERVICE_ARN=$(aws apprunner create-service \
    --cli-input-json file:///tmp/service-config.json \
    --region ${AWS_REGION} \
    --query 'Service.ServiceArn' \
    --output text)

if [ -z "$SERVICE_ARN" ] || [ "$SERVICE_ARN" == "None" ]; then
    echo "❌ Failed to create service"
    echo "   Check the error message above"
    exit 1
fi

echo "✅ Service created successfully!"
echo "   Service ARN: $SERVICE_ARN"

# Wait for service to be created
echo ""
echo "======================================================================"
echo "6️⃣  Waiting for Service to Start"
echo "======================================================================"

echo "Waiting for service to be created and start deployment..."
echo "This may take 5-10 minutes..."
echo ""

for i in {1..30}; do
    STATUS=$(aws apprunner describe-service \
        --service-arn ${SERVICE_ARN} \
        --region ${AWS_REGION} \
        --query 'Service.Status' \
        --output text)
    
    HEALTH_CONFIG=$(aws apprunner describe-service \
        --service-arn ${SERVICE_ARN} \
        --region ${AWS_REGION} \
        --query 'Service.HealthCheckConfiguration' \
        --output json 2>/dev/null || echo '{}')
    
    echo "Attempt $i/30: Status=$STATUS"
    
    if [ "$STATUS" = "RUNNING" ]; then
        echo "✅ Service is RUNNING!"
        break
    fi
    
    if [ "$STATUS" = "CREATE_FAILED" ] || [ "$STATUS" = "OPERATION_IN_PROGRESS" ]; then
        if [ "$STATUS" = "CREATE_FAILED" ]; then
            echo "❌ Service creation failed"
            echo "   Check CloudWatch logs for details"
            exit 1
        fi
    fi
    
    if [ "$i" -eq 30 ]; then
        echo "⚠️  Timeout waiting for service to be running"
        echo "   Service may still be starting. Check AWS Console for details."
        echo "   Service ARN: $SERVICE_ARN"
        exit 1
    fi
    
    sleep 30
done

# Get service URL
SERVICE_URL=$(aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.ServiceUrl' \
    --output text)

# Verify health check configuration
HEALTH_CONFIG=$(aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.HealthCheckConfiguration' \
    --output json)

echo ""
echo "======================================================================"
echo "✅ Service Creation Complete!"
echo "======================================================================"
echo ""
echo "Service Details:"
echo "  Service Name: ${APP_RUNNER_SERVICE}"
echo "  Service ARN: ${SERVICE_ARN}"
echo "  Service URL: ${SERVICE_URL}"
echo ""
echo "Health Check Configuration:"
echo "$HEALTH_CONFIG" | jq '.'
echo ""
echo "Test health endpoint:"
echo "  curl ${SERVICE_URL}/health"
echo ""
echo "View logs:"
echo "  aws logs tail /aws/apprunner/${APP_RUNNER_SERVICE}/${APP_RUNNER_SERVICE}/application --follow --region ${AWS_REGION}"
echo ""
echo "Monitor service:"
echo "  aws apprunner describe-service --service-arn ${SERVICE_ARN} --region ${AWS_REGION}"
echo ""
