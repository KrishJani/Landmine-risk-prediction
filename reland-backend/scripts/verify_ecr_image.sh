#!/bin/bash
# Script to verify ECR has the latest tested Docker image
# Usage: ./verify_ecr_image.sh

set -e

echo "======================================================================"
echo "🔍 Verifying ECR Image"
echo "======================================================================"
echo ""

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-reland-backend}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}❌ Failed to get AWS account ID. Are you logged in?${NC}"
    exit 1
fi

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPO_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}"

echo "Configuration:"
echo "  AWS Account ID: $AWS_ACCOUNT_ID"
echo "  AWS Region: $AWS_REGION"
echo "  ECR Repository: $ECR_REPOSITORY"
echo "  ECR Registry: $ECR_REGISTRY"
echo ""

# Check if repository exists
echo "======================================================================"
echo "1️⃣  Checking ECR Repository"
echo "======================================================================"

if ! aws ecr describe-repositories \
    --repository-names $ECR_REPOSITORY \
    --region $AWS_REGION &>/dev/null; then
    echo -e "${RED}❌ Repository '$ECR_REPOSITORY' not found in ECR${NC}"
    echo ""
    echo "Create it with:"
    echo "  aws ecr create-repository --repository-name $ECR_REPOSITORY --region $AWS_REGION"
    exit 1
fi

echo -e "${GREEN}✅ Repository exists${NC}"
echo ""

# Get latest image tags
echo "======================================================================"
echo "2️⃣  Checking Available Images in ECR"
echo "======================================================================"

IMAGES=$(aws ecr describe-images \
    --repository-name $ECR_REPOSITORY \
    --region $AWS_REGION \
    --query 'sort_by(imageDetails,&imagePushedAt)[-5:].[imageTags[0],imagePushedAt,imageDigest]' \
    --output text 2>/dev/null)

if [ -z "$IMAGES" ]; then
    echo -e "${RED}❌ No images found in ECR repository${NC}"
    echo ""
    echo "You need to push an image first:"
    echo "  1. Build: docker build -t $ECR_REPOSITORY:latest ."
    echo "  2. Tag: docker tag $ECR_REPOSITORY:latest $ECR_REPO_URI:latest"
    echo "  3. Login: aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY"
    echo "  4. Push: docker push $ECR_REPO_URI:latest"
    exit 1
fi

echo "Recent images in ECR:"
echo ""
printf "%-20s %-30s %s\n" "TAG" "PUSHED AT" "DIGEST"
echo "─────────────────────────────────────────────────────────────────────────"
echo "$IMAGES" | while read tag pushed_at digest; do
    printf "%-20s %-30s %s\n" "${tag:-<untagged>}" "$pushed_at" "${digest:0:20}..."
done
echo ""

# Check for 'latest' tag specifically
echo "======================================================================"
echo "3️⃣  Checking 'latest' Tag"
echo "======================================================================"

LATEST_IMAGE=$(aws ecr describe-images \
    --repository-name $ECR_REPOSITORY \
    --region $AWS_REGION \
    --image-ids imageTag=latest \
    --query 'imageDetails[0].[imagePushedAt,imageDigest,imageSizeInBytes]' \
    --output text 2>/dev/null)

if [ -z "$LATEST_IMAGE" ] || [ "$LATEST_IMAGE" == "None" ]; then
    echo -e "${YELLOW}⚠️  No 'latest' tag found in ECR${NC}"
    echo ""
    echo "Available tags:"
    aws ecr describe-images \
        --repository-name $ECR_REPOSITORY \
        --region $AWS_REGION \
        --query 'imageDetails[*].imageTags[0]' \
        --output text | tr '\t' '\n' | grep -v '^$'
    echo ""
    echo "You should push with 'latest' tag:"
    echo "  docker tag $ECR_REPOSITORY:test $ECR_REPO_URI:latest"
    echo "  docker push $ECR_REPO_URI:latest"
else
    PUSHED_AT=$(echo $LATEST_IMAGE | awk '{print $1}')
    DIGEST=$(echo $LATEST_IMAGE | awk '{print $2}')
    SIZE=$(echo $LATEST_IMAGE | awk '{print $3}')
    SIZE_MB=$((SIZE / 1024 / 1024))
    
    echo -e "${GREEN}✅ 'latest' tag found${NC}"
    echo "  Pushed at: $PUSHED_AT"
    echo "  Digest: ${DIGEST:0:20}..."
    echo "  Size: ${SIZE_MB} MB"
    echo ""
fi

# Compare local image with ECR
echo "======================================================================"
echo "4️⃣  Comparing Local Test Image with ECR"
echo "======================================================================"

# Check if local test image exists
if ! docker images | grep -q "reland-backend-test.*latest"; then
    echo -e "${YELLOW}⚠️  Local test image 'reland-backend-test:latest' not found${NC}"
    echo "  (This is okay if you cleaned it up)"
else
    LOCAL_IMAGE_ID=$(docker images --format "{{.ID}}" reland-backend-test:latest | head -1)
    echo "Local test image ID: $LOCAL_IMAGE_ID"
    echo ""
    echo "To push this image to ECR:"
    echo "  1. Tag it: docker tag reland-backend-test:latest $ECR_REPO_URI:latest"
    echo "  2. Login: aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY"
    echo "  3. Push: docker push $ECR_REPO_URI:latest"
    echo ""
fi

# Check image age
if [ -n "$LATEST_IMAGE" ] && [ "$LATEST_IMAGE" != "None" ]; then
    PUSHED_AT=$(echo $LATEST_IMAGE | awk '{print $1}')
    PUSHED_TIMESTAMP=$(date -j -f "%Y-%m-%dT%H:%M:%S" "${PUSHED_AT%.*}" "+%s" 2>/dev/null || date -d "$PUSHED_AT" "+%s" 2>/dev/null)
    CURRENT_TIMESTAMP=$(date +%s)
    AGE_HOURS=$(( (CURRENT_TIMESTAMP - PUSHED_TIMESTAMP) / 3600 ))
    
    echo "======================================================================"
    echo "5️⃣  Image Age Check"
    echo "======================================================================"
    
    if [ $AGE_HOURS -lt 24 ]; then
        echo -e "${GREEN}✅ Image is recent (pushed ${AGE_HOURS} hour(s) ago)${NC}"
    else
        echo -e "${YELLOW}⚠️  Image is ${AGE_HOURS} hours old${NC}"
        echo "  Consider pushing a fresh image if you made recent changes"
    fi
    echo ""
fi

# Summary and recommendations
echo "======================================================================"
echo "📋 Summary & Recommendations"
echo "======================================================================"

if [ -z "$LATEST_IMAGE" ] || [ "$LATEST_IMAGE" == "None" ]; then
    echo -e "${RED}❌ No 'latest' tag in ECR${NC}"
    echo ""
    echo "ACTION REQUIRED:"
    echo "  1. Build and test locally: ./test_before_deploy.sh"
    echo "  2. Tag the tested image: docker tag reland-backend-test:latest $ECR_REPO_URI:latest"
    echo "  3. Login to ECR: aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY"
    echo "  4. Push to ECR: docker push $ECR_REPO_URI:latest"
else
    echo -e "${GREEN}✅ ECR repository has images${NC}"
    echo ""
    echo "To ensure you have the latest tested image:"
    echo "  1. If you just tested locally, push it:"
    echo "     docker tag reland-backend-test:latest $ECR_REPO_URI:latest"
    echo "     docker push $ECR_REPO_URI:latest"
    echo ""
    echo "  2. Or rebuild and push fresh:"
    echo "     docker build -t $ECR_REPO_URI:latest ."
    echo "     docker push $ECR_REPO_URI:latest"
fi

echo ""
echo "ECR Image URI for App Runner:"
echo "  $ECR_REPO_URI:latest"
echo ""
