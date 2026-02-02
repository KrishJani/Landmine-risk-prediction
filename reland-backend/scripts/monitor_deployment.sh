#!/bin/bash
# Monitor App Runner deployment in real-time
# Usage: ./monitor_deployment.sh

AWS_REGION="${AWS_REGION:-us-east-1}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"

echo "======================================================================"
echo "📊 Monitoring App Runner Deployment"
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

SERVICE_ID=$(echo $SERVICE_ARN | awk -F'/' '{print $NF}')
LOG_GROUP="/aws/apprunner/reland-backend/${SERVICE_ID}/service"

echo "Service ARN: $SERVICE_ARN"
echo "Service ID: $SERVICE_ID"
echo ""

# Get latest deployment
LATEST_DEPLOYMENT=$(aws apprunner list-operations \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --max-results 1 \
    --query 'OperationSummaryList[0].Id' \
    --output text)

echo "Latest Deployment: $LATEST_DEPLOYMENT"
echo ""

# Get service status
echo "======================================================================"
echo "📋 Service Status"
echo "======================================================================"
aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.{Status:Status,ServiceUrl:ServiceUrl,HealthCheck:HealthCheckConfiguration}' \
    --output json | jq '.'

echo ""
echo "======================================================================"
echo "📋 Recent Logs (Last 30 lines)"
echo "======================================================================"
aws logs tail "$LOG_GROUP" \
    --since 5m \
    --region ${AWS_REGION} \
    --format short | tail -30

echo ""
echo "======================================================================"
echo "🔄 Following logs (Ctrl+C to stop)..."
echo "======================================================================"
echo ""

# Follow logs
aws logs tail "$LOG_GROUP" \
    --log-stream-names "deployment/${LATEST_DEPLOYMENT}" "events" \
    --follow \
    --region ${AWS_REGION} \
    --format short
