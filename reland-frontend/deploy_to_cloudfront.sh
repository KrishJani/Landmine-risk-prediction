#!/bin/bash
# Deploy frontend to S3 and CloudFront
# Usage: ./deploy_to_cloudfront.sh

set -e

AWS_REGION="us-east-1"
S3_BUCKET="reland-frontend-348170387270"
CLOUDFRONT_DISTRIBUTION_ID="E3MS1AYMUSBSAQ"
BACKEND_URL="https://fdfj6f9e5g.us-east-1.awsapprunner.com"

echo "======================================================================"
echo "🚀 Deploying Frontend to S3 and CloudFront"
echo "======================================================================"

cd "$(dirname "$0")"

# Step 1: Create .env file with backend URL
echo "1️⃣  Creating .env file with backend URL..."
cat > .env <<EOF
REACT_APP_API_URL=${BACKEND_URL}
REACT_APP_MAPBOX_TOKEN=pk.eyJ1Ijoia3JyaXNoMjUiLCJhIjoiY21oamRmbnptMWNhdjJrcHFqaXoybWo0cSJ9.-fbOe_Xt-AJvinYHStN0ew
EOF

echo "✅ .env file created"
echo "   REACT_APP_API_URL=${BACKEND_URL}"
echo ""

# Step 2: Install dependencies (if needed)
if [ ! -d "node_modules" ]; then
    echo "2️⃣  Installing dependencies..."
    npm install
    echo "✅ Dependencies installed"
    echo ""
else
    echo "2️⃣  Dependencies already installed, skipping..."
    echo ""
fi

# Step 3: Build frontend
echo "3️⃣  Building frontend with new backend URL..."
npm run build

if [ ! -d "build" ]; then
    echo "❌ Build failed - build directory not found"
    exit 1
fi

echo "✅ Frontend built successfully"
echo ""

# Step 4: Upload to S3
echo "4️⃣  Uploading to S3..."
echo "   Bucket: ${S3_BUCKET}"

# Upload all files except index.html with long cache
aws s3 sync build/ s3://${S3_BUCKET}/ \
  --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "index.html" \
  --exclude "service-worker.js" \
  --region ${AWS_REGION}

# Upload index.html with no cache
aws s3 cp build/index.html s3://${S3_BUCKET}/index.html \
  --cache-control "no-cache, no-store, must-revalidate" \
  --region ${AWS_REGION}

echo "✅ Files uploaded to S3"
echo ""

# Step 5: Invalidate CloudFront cache
echo "5️⃣  Invalidating CloudFront cache..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id ${CLOUDFRONT_DISTRIBUTION_ID} \
  --paths "/*" \
  --region ${AWS_REGION} \
  --query 'Invalidation.Id' \
  --output text)

echo "✅ CloudFront invalidation created: ${INVALIDATION_ID}"
echo "   This may take 5-15 minutes to complete"
echo ""

# Step 6: Summary
echo "======================================================================"
echo "✅ Deployment Complete!"
echo "======================================================================"
echo ""
echo "Frontend URL: https://d2vctqilbgf3ka.cloudfront.net"
echo "Backend URL: ${BACKEND_URL}"
echo ""
echo "Note: CloudFront cache invalidation is in progress."
echo "      Changes may take 5-15 minutes to appear."
echo ""
echo "Check invalidation status:"
echo "  aws cloudfront get-invalidation --distribution-id ${CLOUDFRONT_DISTRIBUTION_ID} --id ${INVALIDATION_ID} --region ${AWS_REGION}"
echo ""
