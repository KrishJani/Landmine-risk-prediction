#!/bin/bash
# Diagnostic script to check App Runner service health check configuration
# Usage: ./diagnose_apprunner.sh

echo "======================================================================"
echo "🔍 App Runner Service Diagnostic"
echo "======================================================================"

AWS_REGION="${AWS_REGION:-us-east-1}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"

# Get service ARN
SERVICE_ARN=$(aws apprunner list-services \
    --region ${AWS_REGION} \
    --query "ServiceSummaryList[?ServiceName=='${APP_RUNNER_SERVICE}'].ServiceArn" \
    --output text 2>/dev/null || echo "")

if [ -z "$SERVICE_ARN" ] || [ "$SERVICE_ARN" == "None" ]; then
    echo "❌ Error: App Runner service '${APP_RUNNER_SERVICE}' not found"
    echo ""
    echo "Available services:"
    aws apprunner list-services --region ${AWS_REGION} --query "ServiceSummaryList[].ServiceName" --output table
    exit 1
fi

echo "Service ARN: $SERVICE_ARN"
echo ""

# Get service details
echo "======================================================================"
echo "1️⃣  Service Status"
echo "======================================================================"

SERVICE_STATUS=$(aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.Status' \
    --output text)

SERVICE_URL=$(aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.ServiceUrl' \
    --output text)

echo "Status: $SERVICE_STATUS"
echo "URL: $SERVICE_URL"
echo ""

# Check health check configuration
echo "======================================================================"
echo "2️⃣  Health Check Configuration"
echo "======================================================================"

HEALTH_CONFIG=$(aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.HealthCheckConfiguration' \
    --output json)

if [ -z "$HEALTH_CONFIG" ] || [ "$HEALTH_CONFIG" == "null" ] || [ "$HEALTH_CONFIG" == "{}" ]; then
    echo "❌ CRITICAL: Health check configuration is missing or not set!"
    echo "   This is likely why service creation is failing."
    echo ""
    echo "   Fix: Run fix_healthcheck.sh or manually set health check:"
    echo "   aws apprunner update-service \\"
    echo "     --service-arn $SERVICE_ARN \\"
    echo "     --health-check-configuration \\"
    echo "       Protocol=HTTP,Path=/health,Interval=10,Timeout=10,HealthyThreshold=1,UnhealthyThreshold=10 \\"
    echo "     --region $AWS_REGION"
else
    echo "$HEALTH_CONFIG" | jq '.'
    echo ""
    
    # Check if path is correct
    HEALTH_PATH=$(echo "$HEALTH_CONFIG" | jq -r '.Path // empty')
    if [ "$HEALTH_PATH" != "/health" ]; then
        echo "⚠️  WARNING: Health check path is '$HEALTH_PATH', should be '/health'"
    else
        echo "✅ Health check path is correct: /health"
    fi
    
    # Check thresholds
    UNHEALTHY_THRESHOLD=$(echo "$HEALTH_CONFIG" | jq -r '.UnhealthyThreshold // 0')
    if [ "$UNHEALTHY_THRESHOLD" -lt 5 ]; then
        echo "⚠️  WARNING: Unhealthy threshold is $UNHEALTHY_THRESHOLD, should be at least 5-10 for startup"
    else
        echo "✅ Unhealthy threshold is appropriate: $UNHEALTHY_THRESHOLD"
    fi
fi

echo ""

# Check network configuration
echo "======================================================================"
echo "3️⃣  Network Configuration (WAF)"
echo "======================================================================"

NETWORK_CONFIG=$(aws apprunner describe-service \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --query 'Service.NetworkConfiguration' \
    --output json)

WAF_ARN=$(echo "$NETWORK_CONFIG" | jq -r '.IngressConfiguration.AssociatedWafWebAclArn // empty')

if [ -n "$WAF_ARN" ] && [ "$WAF_ARN" != "null" ]; then
    echo "⚠️  WAF is associated: $WAF_ARN"
    echo "   This might be blocking health checks if rules are too restrictive"
    echo "   Ensure WAF allows /health path"
else
    echo "✅ No WAF association (this is fine)"
fi

echo ""

# Check recent operations
echo "======================================================================"
echo "4️⃣  Recent Operations"
echo "======================================================================"

OPERATIONS=$(aws apprunner list-operations \
    --service-arn ${SERVICE_ARN} \
    --region ${AWS_REGION} \
    --max-results 5 \
    --query 'OperationSummaryList[].[Id,Type,Status,StartedAt]' \
    --output table)

if [ -n "$OPERATIONS" ]; then
    echo "$OPERATIONS"
else
    echo "No recent operations found"
fi

echo ""

# Test health endpoint if service is running
if [ "$SERVICE_STATUS" = "RUNNING" ] && [ -n "$SERVICE_URL" ]; then
    echo "======================================================================"
    echo "5️⃣  Testing Health Endpoint"
    echo "======================================================================"
    
    echo "Testing: $SERVICE_URL/health"
    echo ""
    
    for i in {1..3}; do
        RESPONSE=$(curl -s -o /tmp/health_response.txt -w "%{http_code}" --max-time 10 ${SERVICE_URL}/health 2>&1 || echo "000")
        
        if [ "$RESPONSE" = "200" ]; then
            echo "✅ Health check passed! Response:"
            cat /tmp/health_response.txt
            echo ""
            break
        else
            echo "Attempt $i/3: HTTP $RESPONSE"
            if [ -f /tmp/health_response.txt ]; then
                echo "Response body:"
                cat /tmp/health_response.txt
                echo ""
            fi
        fi
        
        if [ $i -lt 3 ]; then
            sleep 2
        fi
    done
else
    echo "======================================================================"
    echo "5️⃣  Health Endpoint Test"
    echo "======================================================================"
    echo "⚠️  Service is not RUNNING (status: $SERVICE_STATUS)"
    echo "   Cannot test health endpoint"
fi

echo ""
echo "======================================================================"
echo "📋 Summary & Recommendations"
echo "======================================================================"

if [ -z "$HEALTH_CONFIG" ] || [ "$HEALTH_CONFIG" == "null" ] || [ "$HEALTH_CONFIG" == "{}" ]; then
    echo "❌ CRITICAL ISSUE: Health check configuration is missing!"
    echo ""
    echo "   ACTION REQUIRED:"
    echo "   1. Run: ./fix_healthcheck.sh"
    echo "   OR"
    echo "   2. Delete and recreate the service:"
    echo "      - Delete: aws apprunner delete-service --service-arn $SERVICE_ARN --region $AWS_REGION"
    echo "      - Create: ./create_apprunner_service.sh"
elif [ "$SERVICE_STATUS" != "RUNNING" ]; then
    echo "⚠️  Service is not running (status: $SERVICE_STATUS)"
    echo ""
    echo "   Check CloudWatch logs:"
    echo "   aws logs tail /aws/apprunner/${APP_RUNNER_SERVICE}/${APP_RUNNER_SERVICE}/application --follow --region $AWS_REGION"
    echo ""
    echo "   If health checks are failing, ensure:"
    echo "   1. Health check path is /health"
    echo "   2. Unhealthy threshold is at least 5-10"
    echo "   3. Application starts successfully (check logs)"
    echo "   4. Port 8080 is exposed and listening"
else
    echo "✅ Service appears to be configured correctly"
    echo ""
    echo "   If you're still experiencing issues:"
    echo "   1. Check CloudWatch logs for application errors"
    echo "   2. Verify database connectivity"
    echo "   3. Ensure all environment variables are set correctly"
fi

echo ""
