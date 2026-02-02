#!/bin/bash
# Clean up old ECR images and push new build
# Usage: ./cleanup_and_push.sh

set -e

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-reland-backend}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"

echo "======================================================================"
echo "🧹 Cleaning Up Old ECR Images and Pushing New Build"
echo "======================================================================"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

echo "Configuration:"
echo "  AWS Region: $AWS_REGION"
echo "  ECR Repository: $ECR_REPOSITORY"
echo "  Image Tag: $IMAGE_TAG"
echo "  Image URI: $IMAGE_URI"
echo ""

# Step 1: Delete all old images
echo "======================================================================"
echo "1️⃣  Deleting Old Images from ECR"
echo "======================================================================"

# Get all image digests
IMAGE_DIGESTS=$(aws ecr list-images \
    --repository-name ${ECR_REPOSITORY} \
    --region ${AWS_REGION} \
    --query 'imageIds[*].imageDigest' \
    --output text 2>/dev/null || echo "")

if [ -n "$IMAGE_DIGESTS" ] && [ "$IMAGE_DIGESTS" != "None" ]; then
    echo "Found images to delete. Deleting all images..."
    
    # Convert to array and delete each
    for digest in $IMAGE_DIGESTS; do
        if [ -n "$digest" ]; then
            echo "Deleting image: $digest"
            aws ecr batch-delete-image \
                --repository-name ${ECR_REPOSITORY} \
                --region ${AWS_REGION} \
                --image-ids imageDigest=$digest 2>/dev/null || true
        fi
    done
    
    echo "✅ Old images deleted"
else
    echo "ℹ️  No existing images found (repository may be empty)"
fi

echo ""

# Step 2: Build new image
echo "======================================================================"
echo "2️⃣  Building Docker Image for linux/amd64"
echo "======================================================================"

cd "$(dirname "$0")"

docker buildx build \
  --platform linux/amd64 \
  --tag ${ECR_REPOSITORY}:${IMAGE_TAG} \
  --tag ${ECR_REPOSITORY}:latest \
  --load \
  .

echo "✅ Docker image built: ${ECR_REPOSITORY}:${IMAGE_TAG} (linux/amd64)"
echo ""

# Step 3: Login to ECR
echo "======================================================================"
echo "3️⃣  Logging in to Amazon ECR"
echo "======================================================================"

aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REGISTRY}

echo "✅ Logged in to ECR"
echo ""

# Step 4: Tag for ECR
echo "======================================================================"
echo "4️⃣  Tagging Image for ECR"
echo "======================================================================"

docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${IMAGE_URI}
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest

echo "✅ Image tagged: ${IMAGE_URI}"
echo "✅ Image tagged: ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest"
echo ""

# Step 5: Push to ECR
echo "======================================================================"
echo "5️⃣  Pushing Image to ECR"
echo "======================================================================"

echo "Pushing ${IMAGE_URI}..."
docker push ${IMAGE_URI}

echo "Pushing latest tag..."
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest

echo "✅ Image pushed to ECR"
echo ""

# Step 6: Verify
echo "======================================================================"
echo "6️⃣  Verifying Push"
echo "======================================================================"

LATEST_IMAGE=$(aws ecr describe-images \
    --repository-name ${ECR_REPOSITORY} \
    --region ${AWS_REGION} \
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
echo "Image URI: ${IMAGE_URI}"
echo "Latest URI: ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest"
echo ""
echo "You can now create a new App Runner service with this image."
echo ""
