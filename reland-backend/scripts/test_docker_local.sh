#!/bin/bash
# Test Docker image locally to diagnose App Runner issues
# Usage: ./test_docker_local.sh

set -e

echo "======================================================================"
echo "🧪 Testing Docker Image Locally"
echo "======================================================================"

cd "$(dirname "$0")"

# Build image for linux/amd64 (x86_64) to match AWS App Runner platform
echo "1. Building Docker image for linux/amd64 (AWS App Runner compatible)..."
docker buildx build \
  --platform linux/amd64 \
  --tag reland-backend-test \
  --load \
  . || {
    echo "❌ Docker build failed"
    echo "Note: If buildx is not set up, run: docker buildx create --use"
    exit 1
}

echo "✅ Image built successfully"
echo ""

# Run container in background (use port 8081 to avoid conflicts)
echo "2. Starting container..."
CONTAINER_ID=$(docker run -d -p 8081:8080 \
  -e FLASK_ENV=production \
  -e ENVIRONMENT=production \
  -e DATABASE_URL="postgresql://test:test@localhost:5432/test" \
  -e PORT=8080 \
  reland-backend-test)

echo "Container ID: $CONTAINER_ID"
echo ""

# Wait a bit for startup
echo "3. Waiting for app to start (10 seconds)..."
sleep 10

# Check logs
echo ""
echo "======================================================================"
echo "📋 Container Logs"
echo "======================================================================"
docker logs $CONTAINER_ID

echo ""
echo "======================================================================"
echo "🧪 Testing Health Endpoint"
echo "======================================================================"

# Test health endpoint
for i in {1..5}; do
    echo "Attempt $i/5:"
    RESPONSE=$(curl -s -o /tmp/health_test.txt -w "%{http_code}" --max-time 5 http://localhost:8081/health || echo "000")
    
    if [ "$RESPONSE" = "200" ]; then
        echo "✅ Health check passed! Response:"
        cat /tmp/health_test.txt
        echo ""
        break
    else
        echo "❌ Health check failed: HTTP $RESPONSE"
        if [ -f /tmp/health_test.txt ]; then
            echo "Response:"
            cat /tmp/health_test.txt
        fi
        echo ""
    fi
    
    if [ $i -lt 5 ]; then
        sleep 5
    fi
done

echo ""
echo "======================================================================"
echo "📊 Container Status"
echo "======================================================================"
docker ps -a --filter "id=$CONTAINER_ID" --format "table {{.ID}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "======================================================================"
echo "✅ Test Complete"
echo "======================================================================"
echo ""
echo "To view logs: docker logs -f $CONTAINER_ID"
echo "To stop container: docker stop $CONTAINER_ID"
echo "To remove container: docker rm $CONTAINER_ID"
echo ""
