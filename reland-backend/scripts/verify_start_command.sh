#!/bin/bash
# Verify start command configuration and check for common issues
# Usage: ./verify_start_command.sh

set -e

SERVICE_ARN="arn:aws:apprunner:us-east-1:348170387270:service/reland-backend/53628a1012fc4076be1c3f2b9818315d"

echo "======================================================================"
echo "🔍 Verifying Start Command Configuration"
echo "======================================================================"
echo ""

# Get full service configuration
CONFIG=$(aws apprunner describe-service \
    --service-arn $SERVICE_ARN \
    --region us-east-1 \
    --output json)

echo "1️⃣  Start Command Check"
echo "======================================================================"

START_CMD=$(echo "$CONFIG" | jq -r '.Service.SourceConfiguration.ImageRepository.ImageConfiguration.StartCommand // "NOT SET"')

if [ "$START_CMD" == "NOT SET" ] || [ -z "$START_CMD" ] || [ "$START_CMD" == "null" ]; then
    echo "❌ CRITICAL: Start command is NOT SET!"
    echo ""
    echo "This means App Runner won't execute your application."
    exit 1
else
    echo "✅ Start command is set: $START_CMD"
fi

echo ""
echo "2️⃣  Start Command Format Check"
echo "======================================================================"

# Check for common issues
if [[ "$START_CMD" == *"python "* ]]; then
    echo "⚠️  WARNING: Using 'python' instead of 'python3'"
    echo "   Recommendation: Use 'python3' for explicit Python 3"
fi

if [[ "$START_CMD" != *"/app/"* ]]; then
    echo "⚠️  WARNING: Path doesn't start with /app/"
    echo "   Make sure the path is correct (should be /app/...)"
fi

if [[ "$START_CMD" == *"python3"* ]] && [[ "$START_CMD" == *"/app/"* ]]; then
    echo "✅ Format looks correct"
fi

echo ""
echo "3️⃣  Port Configuration"
echo "======================================================================"

PORT=$(echo "$CONFIG" | jq -r '.Service.SourceConfiguration.ImageRepository.ImageConfiguration.Port // "NOT SET"')
PORT_ENV=$(echo "$CONFIG" | jq -r '.Service.SourceConfiguration.ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables.PORT // "NOT SET"')

echo "Port (App Runner): $PORT"
echo "PORT (Environment Variable): $PORT_ENV"

if [ "$PORT" == "$PORT_ENV" ] && [ "$PORT" == "8080" ]; then
    echo "✅ Port configuration matches"
else
    echo "⚠️  Port mismatch or incorrect value"
fi

echo ""
echo "4️⃣  Service Status"
echo "======================================================================"

STATUS=$(echo "$CONFIG" | jq -r '.Service.Status')
echo "Current Status: $STATUS"

if [ "$STATUS" == "CREATE_FAILED" ] || [ "$STATUS" == "UPDATE_FAILED" ]; then
    echo ""
    echo "⚠️  Service has failed. Checking latest operation..."
    
    LATEST_OP=$(aws apprunner list-operations \
        --service-arn $SERVICE_ARN \
        --region us-east-1 \
        --max-results 1 \
        --query 'OperationSummaryList[0]' \
        --output json)
    
    OP_STATUS=$(echo "$LATEST_OP" | jq -r '.Status')
    OP_TYPE=$(echo "$LATEST_OP" | jq -r '.Type')
    
    echo "   Latest Operation: $OP_TYPE"
    echo "   Operation Status: $OP_STATUS"
fi

echo ""
echo "5️⃣  Image Configuration"
echo "======================================================================"

IMAGE_URI=$(echo "$CONFIG" | jq -r '.Service.SourceConfiguration.ImageRepository.ImageIdentifier')
echo "Image URI: $IMAGE_URI"

# Check if image exists in ECR
if [[ "$IMAGE_URI" == *".dkr.ecr."* ]]; then
    REPO_NAME=$(echo "$IMAGE_URI" | sed 's/.*\///' | cut -d: -f1)
    IMAGE_TAG=$(echo "$IMAGE_URI" | cut -d: -f2)
    
    echo "Repository: $REPO_NAME"
    echo "Tag: $IMAGE_TAG"
    
    # Verify image exists
    if aws ecr describe-images \
        --repository-name "$REPO_NAME" \
        --image-ids "imageTag=$IMAGE_TAG" \
        --region us-east-1 &>/dev/null; then
        echo "✅ Image exists in ECR"
    else
        echo "❌ Image not found in ECR!"
    fi
fi

echo ""
echo "======================================================================"
echo "📋 Summary"
echo "======================================================================"

if [ "$START_CMD" != "NOT SET" ] && [ -n "$START_CMD" ] && [ "$START_CMD" != "null" ]; then
    echo "✅ Start command is configured: $START_CMD"
    echo ""
    echo "If you're still not seeing logs:"
    echo "  1. Check that the file exists in Docker image: /app/minimal_health.py"
    echo "  2. Verify the file is executable"
    echo "  3. Check CloudWatch logs for application output"
    echo "  4. Verify Python3 is available in the container"
else
    echo "❌ Start command is NOT SET!"
    echo ""
    echo "ACTION REQUIRED:"
    echo "  1. Go to App Runner → Configuration → Edit"
    echo "  2. Set Start command to: python3 /app/minimal_health.py"
    echo "  3. Save and redeploy"
fi

echo ""
