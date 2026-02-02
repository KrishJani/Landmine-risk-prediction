#!/bin/bash
set -e

# Manual deployment script for RELand Backend to AWS App Runner
# Usage: ./manual_deploy.sh

echo "======================================================================"
echo "🚀 Manual Deployment to AWS App Runner"
echo "======================================================================"

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-reland-backend}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"

echo "Configuration:"
echo "  AWS Region: $AWS_REGION"
echo "  ECR Repository: $ECR_REPOSITORY"
echo "  App Runner Service: $APP_RUNNER_SERVICE"
echo "  Image Tag: $IMAGE_TAG"
echo ""

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

echo ""

# Check AWS CLI is installed and configured
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

echo "======================================================================"
echo "1️⃣  Building Docker Image"
echo "======================================================================"

cd "$(dirname "$0")"

# Build for linux/amd64 (x86_64) to match AWS App Runner platform
# Use buildx for cross-platform builds
echo "Building Docker image for linux/amd64 platform (AWS App Runner compatible)..."
docker buildx build \
  --platform linux/amd64 \
  --tag ${ECR_REPOSITORY}:${IMAGE_TAG} \
  --tag ${ECR_REPOSITORY}:latest \
  --load \
  .

echo "✅ Docker image built: ${ECR_REPOSITORY}:${IMAGE_TAG} (linux/amd64)"

echo ""
echo "======================================================================"
echo "2️⃣  Logging in to Amazon ECR"
echo "======================================================================"

aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}
echo "✅ Logged in to ECR"

echo ""
echo "======================================================================"
echo "3️⃣  Tagging Image for ECR"
echo "======================================================================"

docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${IMAGE_URI}
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest
echo "✅ Image tagged: ${IMAGE_URI}"

echo ""
echo "======================================================================"
echo "4️⃣  Pushing Image to ECR"
echo "======================================================================"

echo "Pushing ${IMAGE_URI}..."
docker push ${IMAGE_URI}
echo "Pushing latest tag..."
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest
echo "✅ Image pushed to ECR"

echo ""
echo "======================================================================"
echo "5️⃣  Getting App Runner Service ARN"
echo "======================================================================"

SERVICE_ARN=$(aws apprunner list-services \
    --region ${AWS_REGION} \
    --query "ServiceSummaryList[?ServiceName=='${APP_RUNNER_SERVICE}'].ServiceArn" \
    --output text)

if [ -z "$SERVICE_ARN" ] || [ "$SERVICE_ARN" == "None" ]; then
    echo "❌ Error: App Runner service '${APP_RUNNER_SERVICE}' not found"
    echo "   Available services:"
    aws apprunner list-services --region ${AWS_REGION} --query "ServiceSummaryList[].ServiceName" --output table
    exit 1
fi

echo "✅ Found service: $SERVICE_ARN"

echo ""
echo "======================================================================"
echo "6️⃣  Getting Current Service Configuration"
echo "======================================================================"

aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.SourceConfiguration' > /tmp/current-source.json

echo "✅ Current configuration saved"

echo ""
echo "======================================================================"
echo "7️⃣  Updating Service with New Image"
echo "======================================================================"

# Create new source configuration with health check
cat > /tmp/new-source.json <<EOF
{
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
    "ImageRepositoryType": "ECR"
  },
  "AutoDeploymentsEnabled": false
}
EOF

echo "Using environment variables:"
echo "  DATABASE_URL: ${DATABASE_URL:0:50}*** (from ${DATABASE_URL_SOURCE:-shell/Parameter Store})"
echo "  S3_MODELS_BUCKET: ${S3_MODELS_BUCKET:-Not set}"
echo "  SECRET_KEY: ${SECRET_KEY:+Set (hidden)}${SECRET_KEY:-Not set}"
echo ""

# Update service with source configuration
aws apprunner update-service \
    --service-arn ${SERVICE_ARN} \
    --source-configuration file:///tmp/new-source.json \
    --region ${AWS_REGION}

# Update health check configuration separately (more lenient for startup)
echo "Configuring health check with startup-friendly settings..."
aws apprunner update-service \
    --service-arn ${SERVICE_ARN} \
    --health-check-configuration Protocol=HTTP,Path=/health,Interval=10,Timeout=10,HealthyThreshold=1,UnhealthyThreshold=10 \
    --region ${AWS_REGION} 2>/dev/null || echo "⚠️  Note: Health check configuration may need to be set via AWS Console"

echo "✅ Service update initiated"

echo ""
echo "======================================================================"
echo "8️⃣  Starting Deployment"
echo "======================================================================"

aws apprunner start-deployment \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION}

echo "✅ Deployment started"

echo ""
echo "======================================================================"
echo "9️⃣  Monitoring Deployment"
echo "======================================================================"

echo "Waiting for deployment to complete..."
echo "This may take 5-10 minutes..."
echo ""

for i in {1..30}; do
    STATUS=$(aws apprunner describe-service \
        --service-arn ${SERVICE_ARN} \
        --region ${AWS_REGION} \
        --query 'Service.Status' \
        --output text)
    
    echo "Attempt $i/30: Service status: $STATUS"
    
    if [ "$STATUS" = "RUNNING" ]; then
        echo "✅ Service is running!"
        break
    fi
    
    if [ "$i" -eq 30 ]; then
        echo "⚠️  Timeout waiting for service to be running"
        echo "   Check AWS Console for details"
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

echo ""
echo "======================================================================"
echo "✅ Deployment Complete!"
echo "======================================================================"
echo ""
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "Test health endpoint:"
echo "  curl ${SERVICE_URL}/health"
echo ""
echo "View logs:"
echo "  aws apprunner describe-service --service-arn ${SERVICE_ARN} --region ${AWS_REGION}"
echo "  Or check CloudWatch Logs in AWS Console"
echo ""
