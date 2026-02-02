#!/bin/bash
set -e

# Script to diagnose and fix health check and WAF issues
# Usage: ./fix_healthcheck.sh

echo "======================================================================"
echo "🔧 Fixing Health Check and WAF Issues"
echo "======================================================================"

AWS_REGION="${AWS_REGION:-us-east-1}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"

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

# Get service details
echo "======================================================================"
echo "1️⃣  Checking Current Service Configuration"
echo "======================================================================"

aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.{Status:Status,HealthCheck:HealthCheckConfiguration,NetworkConfig:NetworkConfiguration}' \
    --output json | jq '.'

echo ""
echo "======================================================================"
echo "2️⃣  Updating Health Check Configuration"
echo "======================================================================"

# Update health check with faster, more lenient settings
aws apprunner update-service \
    --service-arn ${SERVICE_ARN} \
    --health-check-configuration \
        Protocol=HTTP,Path=/health,Interval=10,Timeout=3,HealthyThreshold=1,UnhealthyThreshold=5 \
    --region ${AWS_REGION}

echo "✅ Health check configuration updated"
echo "   - Interval: 10 seconds"
echo "   - Timeout: 3 seconds"
echo "   - Healthy Threshold: 1"
echo "   - Unhealthy Threshold: 5"

echo ""
echo "======================================================================"
echo "3️⃣  Checking Network Configuration (WAF)"
echo "======================================================================"

NETWORK_CONFIG=$(aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.NetworkConfiguration' \
    --output json)

echo "$NETWORK_CONFIG" | jq '.'

# Check if WAF is configured
WAF_ARN=$(echo "$NETWORK_CONFIG" | jq -r '.IngressConfiguration.AssociatedWafWebAclArn // empty')

if [ -n "$WAF_ARN" ] && [ "$WAF_ARN" != "null" ]; then
    echo ""
    echo "⚠️  WAF is associated: $WAF_ARN"
    echo "   This might be blocking health checks."
    echo ""
    echo "   To fix:"
    echo "   1. Go to AWS Console → App Runner → ${APP_RUNNER_SERVICE}"
    echo "   2. Configuration → Security"
    echo "   3. Check WAF rules allow /health path"
    echo "   4. Or remove WAF association if not needed"
else
    echo "✅ No WAF association found (this is fine)"
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

if [ -n "$SERVICE_URL" ]; then
    echo "Service URL: $SERVICE_URL"
    echo ""
    echo "Testing /health endpoint..."
    
    for i in {1..3}; do
        echo "Attempt $i/3:"
        RESPONSE=$(curl -s -o /tmp/health_response.txt -w "%{http_code}" --max-time 5 ${SERVICE_URL}/health || echo "000")
        
        if [ "$RESPONSE" = "200" ]; then
            echo "✅ Health check passed! Response:"
            cat /tmp/health_response.txt
            echo ""
            break
        else
            echo "❌ Health check failed: HTTP $RESPONSE"
            if [ -f /tmp/health_response.txt ]; then
                echo "Response:"
                cat /tmp/health_response.txt
                echo ""
            fi
        fi
        
        if [ $i -lt 3 ]; then
            sleep 2
        fi
    done
else
    echo "⚠️  Service URL not available yet (service may still be starting)"
fi

echo ""
echo "======================================================================"
echo "5️⃣  Starting Deployment"
echo "======================================================================"

aws apprunner start-deployment \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION}

echo "✅ Deployment started"

echo ""
echo "======================================================================"
echo "6️⃣  Monitoring Deployment"
echo "======================================================================"

echo "Waiting for service to be RUNNING..."
echo "This may take 5-10 minutes..."
echo ""

for i in {1..30}; do
    STATUS=$(aws apprunner describe-service \
        --service-arn ${SERVICE_ARN} \
        --region ${AWS_REGION} \
        --query 'Service.Status' \
        --output text)
    
    HEALTH_STATUS=$(aws apprunner describe-service \
        --service-arn ${SERVICE_ARN} \
        --region ${AWS_REGION} \
        --query 'Service.HealthCheckConfiguration' \
        --output json 2>/dev/null || echo '{}')
    
    echo "Attempt $i/30: Status=$STATUS"
    
    if [ "$STATUS" = "RUNNING" ]; then
        echo "✅ Service is RUNNING!"
        break
    fi
    
    if [ "$i" -eq 30 ]; then
        echo "⚠️  Timeout waiting for service to be running"
        echo "   Check CloudWatch logs for details"
        exit 1
    fi
    
    sleep 30
done

echo ""
echo "======================================================================"
echo "✅ Fix Complete!"
echo "======================================================================"
echo ""
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "View logs:"
echo "  aws logs tail /aws/apprunner/${APP_RUNNER_SERVICE}/${APP_RUNNER_SERVICE}/application --follow --region ${AWS_REGION}"
echo ""
echo "If health checks still fail:"
echo "  1. Check CloudWatch logs for errors"
echo "  2. Verify WAF rules allow /health path"
echo "  3. Check security groups allow App Runner → RDS traffic"
echo ""
