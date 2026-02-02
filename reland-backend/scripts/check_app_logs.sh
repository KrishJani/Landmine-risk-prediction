#!/bin/bash
# Check application logs for App Runner service
# Usage: ./check_app_logs.sh

set -e

AWS_REGION="${AWS_REGION:-us-east-1}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"

echo "======================================================================"
echo "📋 Checking Application Logs"
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

# Get service ID
SERVICE_ID=$(echo $SERVICE_ARN | awk -F'/' '{print $NF}' | awk -F':' '{print $NF}')

echo "Service ID: $SERVICE_ID"
echo ""

# Get latest deployment
echo "======================================================================"
echo "1️⃣  Latest Deployment"
echo "======================================================================"

LATEST_DEPLOYMENT=$(aws apprunner list-operations \
    --service-arn $SERVICE_ARN \
    --region $AWS_REGION \
    --max-results 1 \
    --query 'OperationSummaryList[0].Id' \
    --output text)

echo "Latest Deployment ID: $LATEST_DEPLOYMENT"
echo ""

# Get log group
LOG_GROUP="/aws/apprunner/${APP_RUNNER_SERVICE}/${SERVICE_ID}/application"

echo "======================================================================"
echo "2️⃣  Application Logs (Last 50 lines)"
echo "======================================================================"
echo "Log Group: $LOG_GROUP"
echo ""

# Try to get logs
if aws logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --region $AWS_REGION \
    --order-by LastEventTime \
    --descending \
    --max-items 1 &>/dev/null; then
    
    LOG_STREAM=$(aws logs describe-log-streams \
        --log-group-name "$LOG_GROUP" \
        --region $AWS_REGION \
        --order-by LastEventTime \
        --descending \
        --max-items 1 \
        --query 'logStreams[0].logStreamName' \
        --output text)
    
    if [ -n "$LOG_STREAM" ] && [ "$LOG_STREAM" != "None" ]; then
        echo "Log Stream: $LOG_STREAM"
        echo ""
        echo "--- Application Logs ---"
        aws logs get-log-events \
            --log-group-name "$LOG_GROUP" \
            --log-stream-name "$LOG_STREAM" \
            --region $AWS_REGION \
            --limit 50 \
            --query 'events[*].message' \
            --output text | tail -50
    else
        echo "⚠️  No log streams found yet (app might still be starting)"
    fi
else
    echo "⚠️  Log group not found or not accessible yet"
    echo "   This is normal if the service just started"
fi

echo ""
echo "======================================================================"
echo "3️⃣  Service Status"
echo "======================================================================"

STATUS=$(aws apprunner describe-service \
    --service-arn $SERVICE_ARN \
    --region $AWS_REGION \
    --query 'Service.Status' \
    --output text)

HEALTH_CONFIG=$(aws apprunner describe-service \
    --service-arn $SERVICE_ARN \
    --region $AWS_REGION \
    --query 'Service.HealthCheckConfiguration' \
    --output json)

echo "Status: $STATUS"
echo ""
echo "Health Check Configuration:"
echo "$HEALTH_CONFIG" | jq '.'

echo ""
echo "======================================================================"
echo "4️⃣  Recent Operations"
echo "======================================================================"

aws apprunner list-operations \
    --service-arn $SERVICE_ARN \
    --region $AWS_REGION \
    --max-results 3 \
    --query 'OperationSummaryList[].[Id,Type,Status,StartedAt]' \
    --output table

echo ""
echo "======================================================================"
echo "💡 Tips"
echo "======================================================================"
echo ""
echo "If health checks are failing, check:"
echo "  1. Application logs above for errors"
echo "  2. Start command is set: python3 /app/run.py"
echo "  3. Port matches: 8080"
echo "  4. Health endpoint exists: /health"
echo ""
echo "To watch logs in real-time:"
echo "  aws logs tail $LOG_GROUP --follow --region $AWS_REGION"
echo ""
