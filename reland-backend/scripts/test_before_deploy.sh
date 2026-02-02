#!/bin/bash
# Comprehensive test script to verify Docker image works before deploying to App Runner
# Usage: ./test_before_deploy.sh

set -e

echo "======================================================================"
echo "🧪 Testing Docker Image Before Deployment"
echo "======================================================================"
echo ""

cd "$(dirname "$0")"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="reland-backend-test"
CONTAINER_NAME="reland-backend-test-container"

# Find available port (start from 8001, try up to 8010)
PORT=8001
for p in {8001..8010}; do
    if ! lsof -Pi :$p -sTCP:LISTEN -t >/dev/null 2>&1; then
        PORT=$p
        break
    fi
done

echo "Using port: $PORT"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up..."
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    
    # Also cleanup any existing containers with same name
    docker ps -a --filter "name=$CONTAINER_NAME" --format "{{.ID}}" | xargs -r docker rm -f 2>/dev/null || true
    
    echo "✅ Cleanup complete"
}

# Set trap to cleanup on exit
trap cleanup EXIT

echo "======================================================================"
echo "1️⃣  Building Docker Image"
echo "======================================================================"

# Build for linux/amd64 (x86_64) to match AWS App Runner platform
echo "Building for linux/amd64 platform (AWS App Runner compatible)..."
docker buildx build \
  --platform linux/amd64 \
  --tag $IMAGE_NAME:latest \
  --load \
  .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Docker image built successfully (linux/amd64)${NC}"
else
    echo -e "${RED}❌ Docker build failed${NC}"
    echo -e "${YELLOW}Note: If buildx is not set up, run: docker buildx create --use${NC}"
    exit 1
fi

echo ""
echo "======================================================================"
echo "2️⃣  Starting Container"
echo "======================================================================"

# Cleanup any existing container first
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Check if port is available
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Port $PORT is already in use. Trying to find available port...${NC}"
    for p in {8001..8010}; do
        if ! lsof -Pi :$p -sTCP:LISTEN -t >/dev/null 2>&1; then
            PORT=$p
            echo -e "${GREEN}✅ Found available port: $PORT${NC}"
            break
        fi
    done
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${RED}❌ Could not find available port in range 8001-8010${NC}"
        echo "   Please free up a port or modify the script"
        exit 1
    fi
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo -e "${YELLOW}⚠️  DATABASE_URL not set. Using placeholder for testing.${NC}"
    echo "   Health endpoint should still work without database."
    DATABASE_URL="postgresql://test:test@localhost:5432/test"
fi

# Start container
echo "Starting container on port $PORT..."
docker run -d \
    --name $CONTAINER_NAME \
    -p $PORT:8080 \
    -e FLASK_ENV=production \
    -e ENVIRONMENT=production \
    -e DATABASE_URL="$DATABASE_URL" \
    -e PORT=8080 \
    -e DEBUG=False \
    $IMAGE_NAME:latest

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Container started${NC}"
else
    echo -e "${RED}❌ Container failed to start${NC}"
    exit 1
fi

echo ""
echo "======================================================================"
echo "3️⃣  Waiting for Application to Start"
echo "======================================================================"

echo "Waiting 15 seconds for application to initialize..."
sleep 15

# Check if container is still running
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo -e "${RED}❌ Container stopped unexpectedly${NC}"
    echo ""
    echo "Container logs:"
    docker logs $CONTAINER_NAME
    exit 1
fi

echo -e "${GREEN}✅ Container is running${NC}"

echo ""
echo "======================================================================"
echo "4️⃣  Checking Container Logs"
echo "======================================================================"

echo "Recent logs:"
docker logs --tail 20 $CONTAINER_NAME

echo ""
echo "======================================================================"
echo "5️⃣  Testing Health Endpoint"
echo "======================================================================"

# Test health endpoint with retries
MAX_RETRIES=5
RETRY_COUNT=0
HEALTH_CHECK_PASSED=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Attempt $RETRY_COUNT/$MAX_RETRIES: Testing http://localhost:$PORT/health"
    
    HTTP_CODE=$(curl -s -o /tmp/health_response.txt -w "%{http_code}" --max-time 5 http://localhost:$PORT/health 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✅ Health check passed!${NC}"
        echo "Response:"
        cat /tmp/health_response.txt
        echo ""
        HEALTH_CHECK_PASSED=true
        break
    else
        echo -e "${YELLOW}⚠️  Health check returned HTTP $HTTP_CODE${NC}"
        if [ -f /tmp/health_response.txt ]; then
            echo "Response:"
            cat /tmp/health_response.txt
            echo ""
        fi
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo "Waiting 5 seconds before retry..."
            sleep 5
        fi
    fi
done

if [ "$HEALTH_CHECK_PASSED" = false ]; then
    echo -e "${RED}❌ Health check failed after $MAX_RETRIES attempts${NC}"
    echo ""
    echo "Container logs:"
    docker logs $CONTAINER_NAME
    exit 1
fi

echo ""
echo "======================================================================"
echo "6️⃣  Testing Root Endpoint"
echo "======================================================================"

ROOT_CODE=$(curl -s -o /tmp/root_response.txt -w "%{http_code}" --max-time 5 http://localhost:$PORT/ 2>/dev/null || echo "000")

if [ "$ROOT_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Root endpoint works${NC}"
    echo "Response preview:"
    head -5 /tmp/root_response.txt
    echo ""
else
    echo -e "${YELLOW}⚠️  Root endpoint returned HTTP $ROOT_CODE${NC}"
fi

echo ""
echo "======================================================================"
echo "7️⃣  Verifying Port Binding"
echo "======================================================================"

if docker port $CONTAINER_NAME | grep -q "8080"; then
    echo -e "${GREEN}✅ Port 8080 is properly exposed${NC}"
    docker port $CONTAINER_NAME
else
    echo -e "${RED}❌ Port 8080 not found in port mapping${NC}"
    exit 1
fi

echo ""
echo "======================================================================"
echo "✅ All Tests Passed!"
echo "======================================================================"
echo ""
echo "Summary:"
echo "  ✅ Docker image builds successfully"
echo "  ✅ Container starts and stays running"
echo "  ✅ Health endpoint (/health) responds with 200 OK"
echo "  ✅ Port 8080 is properly exposed"
echo ""
echo "Your Docker image is ready for deployment to AWS App Runner!"
echo ""
echo "Next steps:"
echo "  1. Push image to ECR (if not already done)"
echo "  2. Create App Runner service in AWS Console with proper health check config"
echo "  3. See MANUAL_APP_RUNNER_SETUP.md for step-by-step instructions"
echo ""
