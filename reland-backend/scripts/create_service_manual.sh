#!/bin/bash
# Manual App Runner service creation script
# Usage: ./create_service_manual.sh

set -e

AWS_REGION="us-east-1"
ECR_REPOSITORY="reland-backend"
APP_RUNNER_SERVICE="reland-backend"
IMAGE_TAG="latest"

echo "======================================================================"
echo "🚀 Creating App Runner Service Manually"
echo "======================================================================"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

echo "Configuration:"
echo "  AWS Region: $AWS_REGION"
echo "  ECR Repository: $ECR_REPOSITORY"
echo "  Image URI: $IMAGE_URI"
echo "  Service Name: $APP_RUNNER_SERVICE"
echo ""

# Get DATABASE_URL from Parameter Store
echo "Getting DATABASE_URL from Parameter Store..."
DATABASE_URL=$(aws ssm get-parameter \
    --name "/reland/database/url" \
    --region ${AWS_REGION} \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text)

if [ -z "$DATABASE_URL" ]; then
    echo "❌ Error: Could not retrieve DATABASE_URL from Parameter Store"
    exit 1
fi

echo "✅ DATABASE_URL retrieved"
echo ""

# Get S3_MODELS_BUCKET
S3_MODELS_BUCKET="${S3_MODELS_BUCKET:-reland-models-348170387270}"

# Create service configuration
echo "Creating service configuration..."
cat > /tmp/apprunner-service-config.json <<EOF
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
          "EC2_LAUNCH_TEMPLATE_NAME": "reland-worker-template",
          "SECRET_KEY": "change-me-in-production",
          "GOOGLE_GEOCODING_API_KEY": "",
          "USE_REDIS": "false",
          "PORT": "8080",
          "DEBUG": "False"
        },
        "StartCommand": "python3 /app/run.py"
      },
      "ImageRepositoryType": "ECR",
      "ImageRepositoryAccessRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/reland-apprunner-ecr-role"
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
  }
}
EOF

echo "✅ Configuration file created: /tmp/apprunner-service-config.json"
echo ""

# Show configuration summary
echo "Configuration Summary:"
echo "  Port: 8080"
echo "  Health Check Path: /health"
echo "  Health Check Interval: 10 seconds"
echo "  Health Check Timeout: 10 seconds"
echo "  Start Command: python3 /app/run.py"
echo "  Image: ${IMAGE_URI}"
echo "  IAM Role: arn:aws:iam::${AWS_ACCOUNT_ID}:role/reland-apprunner-ecr-role"
echo ""

# Create the service
echo "======================================================================"
echo "Creating App Runner Service..."
echo "======================================================================"

SERVICE_OUTPUT=$(aws apprunner create-service \
    --region ${AWS_REGION} \
    --cli-input-json file:///tmp/apprunner-service-config.json \
    --output json)

SERVICE_ARN=$(echo "$SERVICE_OUTPUT" | jq -r '.Service.ServiceArn')
OPERATION_ID=$(echo "$SERVICE_OUTPUT" | jq -r '.OperationId')

if [ -n "$SERVICE_ARN" ] && [ "$SERVICE_ARN" != "null" ]; then
    echo "✅ Service creation initiated!"
    echo ""
    echo "Service ARN: ${SERVICE_ARN}"
    echo "Operation ID: ${OPERATION_ID}"
    echo ""
    echo "The service is being created. This may take 5-10 minutes."
    echo ""
    echo "Monitor status with:"
    echo "  aws apprunner describe-service --service-arn ${SERVICE_ARN} --region ${AWS_REGION} --query 'Service.Status'"
    echo ""
    echo "View logs with:"
    echo "  aws logs tail /aws/apprunner/${APP_RUNNER_SERVICE}/${APP_RUNNER_SERVICE}/application --follow --region ${AWS_REGION}"
    echo ""
    echo "Once RUNNING, get service URL with:"
    echo "  aws apprunner describe-service --service-arn ${SERVICE_ARN} --region ${AWS_REGION} --query 'Service.ServiceUrl' --output text"
    echo ""
    echo "Test health endpoint:"
    echo "  curl \$(aws apprunner describe-service --service-arn ${SERVICE_ARN} --region ${AWS_REGION} --query 'Service.ServiceUrl' --output text)/health"
else
    echo "❌ Failed to create service"
    echo "$SERVICE_OUTPUT" | jq '.'
    exit 1
fi
