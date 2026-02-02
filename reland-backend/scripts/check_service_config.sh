#!/bin/bash
# Check App Runner service configuration - especially start command
# Usage: ./check_service_config.sh

set -e

AWS_REGION="${AWS_REGION:-us-east-1}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"

echo "======================================================================"
echo "🔍 Checking App Runner Service Configuration"
echo "======================================================================"
echo ""

# Get service ARN
SERVICE_ARN=$(aws apprunner list-services \
    --region ${AWS_REGION} \
    --query "ServiceSummaryList[?ServiceName=='${APP_RUNNER_SERVICE}'].ServiceArn" \
    --output text 2>/dev/null || echo "")

if [ -z "$SERVICE_ARN" ] || [ "$SERVICE_ARN" == "None" ]; then
    echo "❌ Error: App Runner service '${APP_RUNNER_SERVICE}' not found"
    exit 1
fi

echo "Service ARN: $SERVICE_ARN"
echo ""

# Get full service configuration
echo "======================================================================"
echo "1️⃣  Service Configuration"
echo "======================================================================"

SERVICE_CONFIG=$(aws apprunner describe-service \
    --service-arn $SERVICE_ARN \
    --region $AWS_REGION)

# Extract critical configuration
echo "Service Status:"
echo "$SERVICE_CONFIG" | jq -r '.Service.Status'

echo ""
echo "======================================================================"
echo "2️⃣  Source Configuration (CRITICAL)"
echo "======================================================================"

SOURCE_CONFIG=$(echo "$SERVICE_CONFIG" | jq '.Service.SourceConfiguration')

echo "Image Configuration:"
echo "$SOURCE_CONFIG" | jq '.ImageRepository.ImageConfiguration'

echo ""
echo "======================================================================"
echo "3️⃣  Start Command Check ⚠️"
echo "======================================================================"

START_CMD=$(echo "$SOURCE_CONFIG" | jq -r '.ImageRepository.ImageConfiguration.StartCommand // "NOT SET"')

if [ "$START_CMD" == "NOT SET" ] || [ -z "$START_CMD" ] || [ "$START_CMD" == "null" ]; then
    echo "❌ CRITICAL: Start command is NOT SET!"
    echo ""
    echo "This is why there are no application logs - the app never starts!"
    echo ""
    echo "Fix: Set Start command to: python3 /app/run.py"
else
    echo "✅ Start command: $START_CMD"
fi

echo ""
echo "======================================================================"
echo "4️⃣  Port Configuration"
echo "======================================================================"

PORT=$(echo "$SOURCE_CONFIG" | jq -r '.ImageRepository.ImageConfiguration.Port // "NOT SET"')
PORT_ENV=$(echo "$SOURCE_CONFIG" | jq -r '.ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables.PORT // "NOT SET"')

echo "Port (App Runner): $PORT"
echo "PORT (Environment Variable): $PORT_ENV"

if [ "$PORT" != "$PORT_ENV" ]; then
    echo "⚠️  WARNING: Port mismatch!"
fi

echo ""
echo "======================================================================"
echo "5️⃣  Environment Variables"
echo "======================================================================"

ENV_VARS=$(echo "$SOURCE_CONFIG" | jq '.ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables')

echo "Environment Variables:"
echo "$ENV_VARS" | jq '.'

echo ""
echo "======================================================================"
echo "6️⃣  Health Check Configuration"
echo "======================================================================"

HEALTH_CONFIG=$(echo "$SERVICE_CONFIG" | jq '.Service.HealthCheckConfiguration')

echo "$HEALTH_CONFIG" | jq '.'

echo ""
echo "======================================================================"
echo "📋 Summary"
echo "======================================================================"

if [ "$START_CMD" == "NOT SET" ] || [ -z "$START_CMD" ] || [ "$START_CMD" == "null" ]; then
    echo "❌ CRITICAL ISSUE FOUND: Start command is not set!"
    echo ""
    echo "This is why:"
    echo "  - No application logs appear"
    echo "  - Health checks fail"
    echo "  - Service never becomes RUNNING"
    echo ""
    echo "ACTION REQUIRED:"
    echo "  1. Go to App Runner → Your service → Configuration"
    echo "  2. Click 'Edit'"
    echo "  3. Find 'Start command' field"
    echo "  4. Set it to: python3 /app/run.py"
    echo "  5. Save and redeploy"
else
    echo "✅ Start command is set: $START_CMD"
    echo ""
    echo "If there are still no logs, check:"
    echo "  1. Application might be crashing immediately"
    echo "  2. Check CloudWatch logs for errors"
    echo "  3. Verify DATABASE_URL is complete"
fi

echo ""
