#!/bin/bash
# Watch logs for current App Runner deployment
# Usage: ./watch_current_deployment.sh

AWS_REGION="${AWS_REGION:-us-east-1}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"

echo "======================================================================"
echo "📋 Watching Current Deployment Logs"
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

# Extract service ID from ARN
SERVICE_ID=$(echo $SERVICE_ARN | awk -F'/' '{print $NF}')

# Get latest deployment
LATEST_DEPLOYMENT=$(aws apprunner list-operations \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --max-results 1 \
    --query 'OperationSummaryList[0].Id' \
    --output text)

if [ -z "$LATEST_DEPLOYMENT" ] || [ "$LATEST_DEPLOYMENT" == "None" ]; then
    echo "❌ No deployment found"
    exit 1
fi

echo "Service ARN: $SERVICE_ARN"
echo "Service ID: $SERVICE_ID"
echo "Latest Deployment ID: $LATEST_DEPLOYMENT"
echo ""

LOG_GROUP="/aws/apprunner/reland-backend/${SERVICE_ID}/service"
DEPLOYMENT_STREAM="deployment/${LATEST_DEPLOYMENT}"

echo "======================================================================"
echo "📊 Deployment Logs"
echo "======================================================================"
echo "Log Group: $LOG_GROUP"
echo "Log Stream: $DEPLOYMENT_STREAM"
echo ""

# Check if log stream exists
STREAM_EXISTS=$(aws logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name-prefix "$DEPLOYMENT_STREAM" \
    --region ${AWS_REGION} \
    --query "logStreams[?logStreamName=='$DEPLOYMENT_STREAM'].logStreamName" \
    --output text)

if [ -z "$STREAM_EXISTS" ]; then
    echo "⚠️  Deployment log stream not found yet"
    echo "   Checking events stream..."
    echo ""
    
    # Check events stream
    aws logs tail "$LOG_GROUP" \
        --log-stream-names "events" \
        --since 30m \
        --region ${AWS_REGION} \
        --format short
else
    echo "✅ Found deployment log stream"
    echo ""
    echo "Recent logs:"
    echo "---"
    
    # Get all logs from deployment stream
    aws logs get-log-events \
        --log-group-name "$LOG_GROUP" \
        --log-stream-name "$DEPLOYMENT_STREAM" \
        --region ${AWS_REGION} \
        --start-from-head \
        --limit 500 \
        --query "events[*].[timestamp,message]" \
        --output text | while IFS=$'\t' read -r timestamp message; do
            if [ -n "$timestamp" ]; then
                date_str=$(date -r $((timestamp / 1000)) '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d @$((timestamp / 1000)) '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "$timestamp")
                echo "[$date_str] $message"
            else
                echo "$message"
            fi
        done
fi

echo ""
echo "======================================================================"
echo "🔄 Following logs (Ctrl+C to stop)..."
echo "======================================================================"
echo ""

# Follow logs
aws logs tail "$LOG_GROUP" \
    --log-stream-names "$DEPLOYMENT_STREAM" "events" \
    --follow \
    --region ${AWS_REGION} \
    --format short
