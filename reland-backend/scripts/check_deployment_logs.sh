#!/bin/bash
# Script to check App Runner deployment logs
# Usage: ./check_deployment_logs.sh

AWS_REGION="${AWS_REGION:-us-east-1}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"

echo "======================================================================"
echo "📋 Checking App Runner Deployment Logs"
echo "======================================================================"

# Get service ARN
SERVICE_ARN=$(aws apprunner list-services \
    --region ${AWS_REGION} \
    --query "ServiceSummaryList[?ServiceName=='${APP_RUNNER_SERVICE}'].ServiceArn" \
    --output text)

if [ -z "$SERVICE_ARN" ] || [ "$SERVICE_ARN" == "None" ]; then
    echo "❌ Error: App Runner service '${APP_RUNNER_SERVICE}' not found"
    exit 1
fi

echo "Service ARN: $SERVICE_ARN"
echo ""

# Get service status
echo "======================================================================"
echo "1️⃣  Service Status"
echo "======================================================================"

aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.{Status:Status,ServiceUrl:ServiceUrl,HealthCheck:HealthCheckConfiguration}' \
    --output json | jq '.'

echo ""
echo "======================================================================"
echo "2️⃣  Recent Deployment Events"
echo "======================================================================"

aws apprunner list-operations \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --max-results 5 \
    --query 'OperationSummaryList[*].{Id:Id,Type:Type,Status:Status,StartedAt:StartedAt,EndedAt:EndedAt}' \
    --output table

echo ""
echo "======================================================================"
echo "3️⃣  CloudWatch Logs (Last 50 lines)"
echo "======================================================================"

LOG_GROUP="/aws/apprunner/${APP_RUNNER_SERVICE}/${APP_RUNNER_SERVICE}/application"

# Check if log group exists
if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region ${AWS_REGION} --query "logGroups[?logGroupName=='$LOG_GROUP'].logGroupName" --output text | grep -q "$LOG_GROUP"; then
    echo "Fetching logs from: $LOG_GROUP"
    echo ""
    aws logs tail "$LOG_GROUP" --since 10m --region ${AWS_REGION} --format short || echo "No logs found or log group doesn't exist yet"
else
    echo "⚠️  Log group not found: $LOG_GROUP"
    echo "   This might mean the app hasn't started yet or logs aren't being written"
fi

echo ""
echo "======================================================================"
echo "4️⃣  Testing Health Endpoint"
echo "======================================================================"

SERVICE_URL=$(aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.ServiceUrl' \
    --output text)

if [ -n "$SERVICE_URL" ] && [ "$SERVICE_URL" != "None" ]; then
    echo "Service URL: $SERVICE_URL"
    echo ""
    echo "Testing /health endpoint..."
    curl -v --max-time 10 ${SERVICE_URL}/health 2>&1 || echo "❌ Health check failed"
else
    echo "⚠️  Service URL not available (service may still be starting)"
fi

echo ""
echo "======================================================================"
echo "5️⃣  Recent Error Logs"
echo "======================================================================"

if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region ${AWS_REGION} --query "logGroups[?logGroupName=='$LOG_GROUP'].logGroupName" --output text | grep -q "$LOG_GROUP"; then
    echo "Searching for errors in logs..."
    aws logs filter-log-events \
        --log-group-name "$LOG_GROUP" \
        --region ${AWS_REGION} \
        --filter-pattern "ERROR error Error Exception exception" \
        --start-time $(($(date +%s) - 600))000 \
        --max-items 20 \
        --query 'events[*].message' \
        --output text | head -20 || echo "No errors found"
else
    echo "Log group not found"
fi

echo ""
echo "======================================================================"
echo "✅ Log Check Complete"
echo "======================================================================"
echo ""
echo "To view logs in real-time:"
echo "  aws logs tail $LOG_GROUP --follow --region ${AWS_REGION}"
echo ""
