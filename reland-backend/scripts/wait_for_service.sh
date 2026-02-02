#!/bin/bash
# Wait for App Runner service to be in RUNNING state
# Usage: ./wait_for_service.sh

set -e

SERVICE_ARN="arn:aws:apprunner:us-east-1:348170387270:service/reland-backend/53628a1012fc4076be1c3f2b9818315d"
AWS_REGION="us-east-1"

echo "======================================================================"
echo "⏳ Waiting for App Runner Service to be Ready"
echo "======================================================================"
echo ""
echo "Service ARN: $SERVICE_ARN"
echo ""

for i in {1..60}; do
    STATUS=$(aws apprunner describe-service \
        --service-arn ${SERVICE_ARN} \
        --region ${AWS_REGION} \
        --query 'Service.Status' \
        --output text)
    
    echo "Attempt $i/60: Service status: $STATUS"
    
    if [ "$STATUS" = "RUNNING" ]; then
        echo ""
        echo "✅ Service is now RUNNING!"
        echo ""
        
        # Get service URL
        SERVICE_URL=$(aws apprunner describe-service \
            --service-arn ${SERVICE_ARN} \
            --region ${AWS_REGION} \
            --query 'Service.ServiceUrl' \
            --output text)
        
        echo "Service URL: ${SERVICE_URL}"
        echo ""
        echo "You can now start a deployment or test the service:"
        echo "  curl ${SERVICE_URL}/health"
        echo ""
        exit 0
    fi
    
    if [ "$STATUS" = "CREATE_FAILED" ] || [ "$STATUS" = "DELETE_FAILED" ]; then
        echo ""
        echo "❌ Service is in failed state: $STATUS"
        echo "   Check CloudWatch logs for details"
        exit 1
    fi
    
    if [ "$i" -eq 60 ]; then
        echo ""
        echo "⚠️  Timeout waiting for service to be RUNNING"
        echo "   Current status: $STATUS"
        echo "   Check AWS Console for details"
        exit 1
    fi
    
    sleep 10
done
