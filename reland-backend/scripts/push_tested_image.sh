#!/bin/bash
# Push the tested local image to ECR
# Usage: ./push_tested_image.sh

set -e

echo "======================================================================"
echo "📤 Pushing Tested Image to ECR"
echo "======================================================================"
echo ""

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-reland-backend}"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPO_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}"

echo "Configuration:"
echo "  ECR Repository: $ECR_REPOSITORY"
echo "  ECR Registry: $ECR_REGISTRY"
echo "  Target URI: $ECR_REPO_URI:latest"
echo ""

# Check if local test image exists
if ! docker images | grep -q "reland-backend-test.*latest"; then
    echo "❌ Local test image 'reland-backend-test:latest' not found"
    echo ""
    echo "Please test the image first:"
    echo "  ./test_before_deploy.sh"
    exit 1
fi

echo "✅ Found local test image: reland-backend-test:latest"
echo ""

# Step 1: Login to ECR
echo "======================================================================"
echo "1️⃣  Logging in to ECR"
echo "======================================================================"

aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $ECR_REGISTRY

if [ $? -eq 0 ]; then
    echo "✅ Logged in to ECR"
else
    echo "❌ Failed to login to ECR"
    exit 1
fi

echo ""

# Step 2: Tag the tested image
echo "======================================================================"
echo "2️⃣  Tagging Tested Image"
echo "======================================================================"

docker tag reland-backend-test:latest $ECR_REPO_URI:latest

if [ $? -eq 0 ]; then
    echo "✅ Image tagged: $ECR_REPO_URI:latest"
else
    echo "❌ Failed to tag image"
    exit 1
fi

echo ""

# Step 3: Push to ECR
echo "======================================================================"
echo "3️⃣  Pushing to ECR"
echo "======================================================================"

echo "Pushing image (this may take a few minutes)..."
docker push $ECR_REPO_URI:latest

if [ $? -eq 0 ]; then
    echo "✅ Image pushed successfully!"
else
    echo "❌ Failed to push image"
    exit 1
fi

echo ""

# Step 4: Verify
echo "======================================================================"
echo "4️⃣  Verifying Push"
echo "======================================================================"

LATEST_IMAGE=$(aws ecr describe-images \
    --repository-name $ECR_REPOSITORY \
    --region $AWS_REGION \
    --image-ids imageTag=latest \
    --query 'imageDetails[0].imagePushedAt' \
    --output text 2>/dev/null)

if [ -n "$LATEST_IMAGE" ]; then
    echo "✅ Verified: Latest image in ECR pushed at: $LATEST_IMAGE"
else
    echo "⚠️  Could not verify push (but it may have succeeded)"
fi

echo ""
echo "======================================================================"
echo "✅ Complete!"
echo "======================================================================"
echo ""
echo "Your tested image is now in ECR:"
echo "  $ECR_REPO_URI:latest"
echo ""
echo "You can now use this image URI in App Runner service configuration."
echo ""
