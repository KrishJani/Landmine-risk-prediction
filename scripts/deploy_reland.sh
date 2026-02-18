#!/bin/bash
#
# RELand unified deploy script: frontend, backend, and/or database seed.
# Run from repository root: ./scripts/deploy_reland.sh [options]
#
# Usage:
#   --frontend         Build frontend, upload to S3, invalidate CloudFront
#   --backend          Build Docker image, push to ECR, update App Runner
#   --database         Run RDS seed (setup_rds_database.py); requires DATABASE_URL or RDS_URL
#   --database --local Run local DB init (init_database.py); uses LOCAL_DATABASE_URL
#   --all              Run --frontend and --backend (not database unless --with-db-seed)
#   --with-db-seed     With --all, also run --database after backend
#   --help             Show this help
#
# Configuration: set environment variables (or source a deploy.env file, do not commit secrets).
#
# Frontend:
#   S3_BUCKET                    S3 bucket for frontend (e.g. reland-frontend-348170387270)
#   CLOUDFRONT_DISTRIBUTION_ID   CloudFront distribution ID
#   REACT_APP_API_URL            Backend API URL (build-time)
#   REACT_APP_MAPBOX_TOKEN       Mapbox token (build-time, optional)
#   AWS_REGION                   AWS region (default: us-east-1)
#
# Backend:
#   AWS_REGION                   AWS region (default: us-east-1)
#   ECR_REPOSITORY               ECR repository name (default: reland-backend)
#   APP_RUNNER_SERVICE           App Runner service name (default: reland-backend)
#   DATABASE_URL                 PostgreSQL URL for RDS (or from Parameter Store /reland/database/url)
#   S3_MODELS_BUCKET             S3 models bucket (or from Parameter Store /reland/s3/models-bucket)
#   EC2_LAUNCH_TEMPLATE_NAME     Optional (default: reland-worker-template)
#   SECRET_KEY                   Optional
#   GOOGLE_GEOCODING_API_KEY     Optional
#
# Database (for --database):
#   DATABASE_URL or RDS_URL      RDS connection string for setup_rds_database.py
#   LOCAL_DATABASE_URL           For --database --local (optional; default localhost)
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load optional config (do not commit deploy.env if it contains secrets)
if [ -f "$PROJECT_ROOT/deploy.env" ]; then
  set -a
  source "$PROJECT_ROOT/deploy.env"
  set +a
fi
if [ -f "$SCRIPT_DIR/deploy.env" ]; then
  set -a
  source "$SCRIPT_DIR/deploy.env"
  set +a
fi

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-reland-backend}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-reland-backend}"

DEPLOY_FRONTEND=false
DEPLOY_BACKEND=false
DEPLOY_DATABASE=false
DATABASE_LOCAL=false
WITH_DB_SEED=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --frontend)
      DEPLOY_FRONTEND=true
      shift
      ;;
    --backend)
      DEPLOY_BACKEND=true
      shift
      ;;
    --database)
      DEPLOY_DATABASE=true
      shift
      ;;
    --local)
      DATABASE_LOCAL=true
      shift
      ;;
    --all)
      DEPLOY_FRONTEND=true
      DEPLOY_BACKEND=true
      shift
      ;;
    --with-db-seed)
      WITH_DB_SEED=true
      shift
      ;;
    --help|-h)
      head -50 "$SCRIPT_DIR/$(basename "$0")" | grep -E '^#(\s|$)'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [ "$WITH_DB_SEED" = true ]; then
  DEPLOY_DATABASE=true
fi

if [ "$DEPLOY_FRONTEND" != true ] && [ "$DEPLOY_BACKEND" != true ] && [ "$DEPLOY_DATABASE" != true ]; then
  echo "Usage: $0 --frontend | --backend | --database [--local] | --all [--with-db-seed]"
  echo "Run with --help for full help."
  exit 1
fi

# ----- Checks -----
if ! command -v aws &>/dev/null; then
  echo "❌ AWS CLI is not installed or not in PATH."
  exit 1
fi

deploy_frontend() {
  echo "======================================================================"
  echo "🚀 Deploying Frontend"
  echo "======================================================================"
  if [ -z "$S3_BUCKET" ]; then
    echo "❌ S3_BUCKET is not set. Set it or add to deploy.env."
    exit 1
  fi
  if [ -z "$CLOUDFRONT_DISTRIBUTION_ID" ]; then
    echo "❌ CLOUDFRONT_DISTRIBUTION_ID is not set."
    exit 1
  fi
  if [ -z "$REACT_APP_API_URL" ]; then
    echo "❌ REACT_APP_API_URL is not set (needed at build time)."
    exit 1
  fi
  if ! command -v npm &>/dev/null; then
    echo "❌ npm is not installed or not in PATH."
    exit 1
  fi

  cd "$PROJECT_ROOT/reland-frontend"
  if [ ! -f "package.json" ]; then
    echo "❌ reland-frontend/package.json not found."
    exit 1
  fi

  echo "Creating .env for build..."
  cat > .env <<EOF
REACT_APP_API_URL=${REACT_APP_API_URL}
REACT_APP_MAPBOX_TOKEN=${REACT_APP_MAPBOX_TOKEN:-}
EOF

  if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  echo "Building frontend..."
  npm run build
  if [ ! -d "build" ]; then
    echo "❌ Build failed - build directory not found"
    exit 1
  fi

  echo "Uploading to S3 (bucket: $S3_BUCKET)..."
  aws s3 sync build/ "s3://${S3_BUCKET}/" \
    --delete \
    --cache-control "public, max-age=31536000, immutable" \
    --exclude "index.html" \
    --exclude "service-worker.js" \
    --region "$AWS_REGION"
  aws s3 cp build/index.html "s3://${S3_BUCKET}/index.html" \
    --cache-control "no-cache, no-store, must-revalidate" \
    --region "$AWS_REGION"

  echo "Invalidating CloudFront..."
  INVALIDATION_ID=$(aws cloudfront create-invalidation \
    --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
    --paths "/*" \
    --region "$AWS_REGION" \
    --query 'Invalidation.Id' \
    --output text)
  echo "✅ Frontend deployed. CloudFront invalidation: $INVALIDATION_ID (may take 5-15 min)"
}

deploy_backend() {
  echo "======================================================================"
  echo "🚀 Deploying Backend"
  echo "======================================================================"
  if ! docker info &>/dev/null; then
    echo "❌ Docker is not running or not in PATH."
    exit 1
  fi

  if [ -z "$DATABASE_URL" ]; then
    echo "Attempting to get DATABASE_URL from Parameter Store..."
    DATABASE_URL=$(aws ssm get-parameter --name "/reland/database/url" --region "$AWS_REGION" --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || true)
  fi
  if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL is not set and could not be read from Parameter Store."
    exit 1
  fi

  if [ -z "$S3_MODELS_BUCKET" ]; then
    S3_MODELS_BUCKET=$(aws ssm get-parameter --name "/reland/s3/models-bucket" --region "$AWS_REGION" --query 'Parameter.Value' --output text 2>/dev/null || true)
  fi

  AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"
  IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

  cd "$PROJECT_ROOT/reland-backend"
  if [ ! -f "Dockerfile" ]; then
    echo "❌ reland-backend/Dockerfile not found."
    exit 1
  fi

  echo "Building Docker image (linux/amd64)..."
  docker buildx build \
    --platform linux/amd64 \
    --tag "${ECR_REPOSITORY}:${IMAGE_TAG}" \
    --tag "${ECR_REPOSITORY}:latest" \
    --load \
    .

  echo "Logging in to ECR..."
  aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

  echo "Tagging and pushing to ECR..."
  docker tag "${ECR_REPOSITORY}:${IMAGE_TAG}" "$IMAGE_URI"
  docker tag "${ECR_REPOSITORY}:${IMAGE_TAG}" "${ECR_REGISTRY}/${ECR_REPOSITORY}:latest"
  docker push "$IMAGE_URI"
  docker push "${ECR_REGISTRY}/${ECR_REPOSITORY}:latest"

  SERVICE_ARN=$(aws apprunner list-services --region "$AWS_REGION" --query "ServiceSummaryList[?ServiceName=='${APP_RUNNER_SERVICE}'].ServiceArn" --output text)
  if [ -z "$SERVICE_ARN" ] || [ "$SERVICE_ARN" = "None" ]; then
    echo "❌ App Runner service '$APP_RUNNER_SERVICE' not found."
    exit 1
  fi

  echo "Updating App Runner service..."
  cat > /tmp/reland-source.json <<EOF
{
  "ImageRepository": {
    "ImageIdentifier": "${IMAGE_URI}",
    "ImageConfiguration": {
      "Port": "8080",
      "RuntimeEnvironmentVariables": {
        "FLASK_ENV": "production",
        "ENVIRONMENT": "production",
        "DATABASE_URL": "${DATABASE_URL}",
        "AWS_REGION": "${AWS_REGION}",
        "S3_MODELS_BUCKET": "${S3_MODELS_BUCKET:-}",
        "EC2_LAUNCH_TEMPLATE_NAME": "${EC2_LAUNCH_TEMPLATE_NAME:-reland-worker-template}",
        "SECRET_KEY": "${SECRET_KEY:-change-me-in-production}",
        "GOOGLE_GEOCODING_API_KEY": "${GOOGLE_GEOCODING_API_KEY:-}",
        "USE_REDIS": "false",
        "PORT": "8080",
        "DEBUG": "False"
      },
      "StartCommand": "python3 /app/run.py"
    },
    "ImageRepositoryType": "ECR"
  },
  "AutoDeploymentsEnabled": false
}
EOF
  aws apprunner update-service --service-arn "$SERVICE_ARN" --source-configuration file:///tmp/reland-source.json --region "$AWS_REGION" >/dev/null
  aws apprunner update-service --service-arn "$SERVICE_ARN" --health-check-configuration Protocol=HTTP,Path=/health,Interval=10,Timeout=10,HealthyThreshold=1,UnhealthyThreshold=10 --region "$AWS_REGION" 2>/dev/null || true

  echo "Starting deployment..."
  aws apprunner start-deployment --service-arn "$SERVICE_ARN" --region "$AWS_REGION"
  echo "Waiting for RUNNING (may take 5-10 min)..."
  for i in $(seq 1 30); do
    STATUS=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$AWS_REGION" --query 'Service.Status' --output text)
    echo "  Attempt $i/30: $STATUS"
    if [ "$STATUS" = "RUNNING" ]; then
      break
    fi
    [ "$i" -eq 30 ] && echo "⚠️ Timeout waiting for RUNNING" && exit 1
    sleep 30
  done
  SERVICE_URL=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$AWS_REGION" --query 'Service.ServiceUrl' --output text)
  echo "✅ Backend deployed. Service URL: $SERVICE_URL"
}

deploy_database() {
  echo "======================================================================"
  echo "🗄️  Database seed (setup or re-seed)"
  echo "======================================================================"
  if [ "$DATABASE_LOCAL" = true ]; then
    cd "$PROJECT_ROOT/reland-backend"
    export LOCAL_DATABASE_URL="${LOCAL_DATABASE_URL:-postgresql://reland_user:reland_password123@localhost:5432/reland_db}"
    echo "Running init_database.py (local)..."
    python3 init_database.py
    echo "✅ Local database init done."
    return
  fi

  RDS_URL="${DATABASE_URL:-$RDS_URL}"
  if [ -z "$RDS_URL" ]; then
    RDS_URL=$(aws ssm get-parameter --name "/reland/database/url" --region "$AWS_REGION" --with-decryption --query 'Parameter.Value' --output text 2>/dev/null || true)
  fi
  if [ -z "$RDS_URL" ]; then
    echo "❌ DATABASE_URL or RDS_URL not set and not in Parameter Store."
    exit 1
  fi

  echo "This will run setup_rds_database.py and may overwrite/append data in RDS."
  read -p "Continue? [y/N] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[yY]$ ]]; then
    echo "Aborted."
    exit 0
  fi

  cd "$PROJECT_ROOT/reland-backend"
  if [ ! -f "setup_rds_database.py" ]; then
    echo "❌ setup_rds_database.py not found."
    exit 1
  fi
  python3 setup_rds_database.py --rds-url "$RDS_URL"
  echo "✅ RDS database seed done."
}

# ----- Run -----
if [ "$DEPLOY_FRONTEND" = true ]; then
  deploy_frontend
fi
if [ "$DEPLOY_BACKEND" = true ]; then
  deploy_backend
fi
if [ "$DEPLOY_DATABASE" = true ]; then
  deploy_database
fi

echo ""
echo "======================================================================"
echo "✅ Deploy complete"
echo "======================================================================"
