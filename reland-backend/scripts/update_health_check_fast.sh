#!/bin/bash
# Update health check to fail faster
# Usage: ./update_health_check_fast.sh

SERVICE_ARN="arn:aws:apprunner:us-east-1:348170387270:service/reland-backend/53628a1012fc4076be1c3f2b9818315d"

echo "Updating health check to fail faster..."
echo "New settings: Interval=10s, UnhealthyThreshold=6"
echo "Will fail after: 6 × 10 = 60 seconds"

aws apprunner update-service \
  --service-arn $SERVICE_ARN \
  --health-check-configuration \
    Protocol=HTTP,Path=/health,Interval=10,Timeout=10,HealthyThreshold=1,UnhealthyThreshold=6 \
  --region us-east-1

echo ""
echo "✅ Health check updated!"
echo "Next deployment will fail after ~60 seconds if app crashes"
