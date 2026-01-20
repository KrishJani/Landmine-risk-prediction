#!/bin/bash
set -e

# Log everything
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting RELand EC2 Worker setup at $(date)"

# Update system
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y

# Install system dependencies
apt-get install -y \
    python3.11 \
    python3-pip \
    python3-venv \
    git \
    postgresql-client \
    curl \
    wget \
    unzip \
    build-essential \
    libpq-dev

# Install AWS CLI v2
cd /tmp
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
./aws/install
rm -rf aws awscliv2.zip

# Install NVIDIA drivers and CUDA (for GPU support)
# Note: This is for g4dn instances which have NVIDIA T4 GPUs
apt-get install -y linux-headers-$(uname -r)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/cuda-keyring_1.0-1_all.deb
dpkg -i cuda-keyring_1.0-1_all.deb
apt-get update
apt-get install -y cuda-toolkit-11-8

# Set up project directory
mkdir -p /opt/reland
cd /opt/reland

# Get AWS region and account ID from instance metadata
AWS_REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Download code from S3 (assuming code is uploaded there) or clone from git
# For now, we'll assume the code is available via git or S3
# Option 1: Clone from git (if repository is public or using deploy keys)
# git clone https://github.com/your-org/reland.git /opt/reland

# Option 2: Download from S3 (recommended for private repos)
# aws s3 sync s3://reland-code-bucket/ /opt/reland/ --region $AWS_REGION

# For this setup, we'll create a minimal structure and download dependencies
# The actual code should be uploaded to S3 or available via git

# Create virtual environment
python3.11 -m venv ml_venv
source ml_venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install ML and data science libraries
pip install numpy pandas scikit-learn scipy

# Install project dependencies (these should match requirements.txt)
# Note: rq and redis are optional (only if USE_REDIS=true)
pip install Flask Flask-SQLAlchemy Flask-CORS \
    psycopg2-binary \
    geopandas shapely fiona \
    python-dotenv \
    gunicorn \
    requests

# Optionally install rq/redis if Redis is enabled
# pip install rq redis

# Install project-specific modules (if using custom modules)
# These should be in the code repository
# pip install -e /opt/reland

# Set up environment variables
# These will be retrieved from Systems Manager Parameter Store or Secrets Manager
# For now, we'll create a template that will be populated

cat > /opt/reland/.env.template <<EOF
# Database connection
DATABASE_URL=postgresql://reland_admin:PASSWORD@RDS_ENDPOINT:5432/reland_db

# AWS configuration
AWS_REGION=${AWS_REGION}
S3_MODELS_BUCKET=reland-models-${ACCOUNT_ID}
S3_CODE_BUCKET=reland-code-${ACCOUNT_ID}

# Worker configuration (no Redis needed - synchronous training)
USE_REDIS=false
WORKER_NAME=reland-worker-${INSTANCE_ID}
EOF

# Create script to fetch secrets from AWS Systems Manager Parameter Store
cat > /opt/reland/fetch-secrets.sh <<'FETCH_SCRIPT'
#!/bin/bash
# Fetch secrets from AWS Systems Manager Parameter Store
# This script should be run before starting the worker

AWS_REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)

# Fetch database URL
DATABASE_URL=$(aws ssm get-parameter \
    --name "/reland/database/url" \
    --with-decryption \
    --region $AWS_REGION \
    --query 'Parameter.Value' \
    --output text)

# Create .env file (no Redis needed - cost optimization)
cat > /opt/reland/.env <<EOF
DATABASE_URL=${DATABASE_URL}
AWS_REGION=${AWS_REGION}
S3_MODELS_BUCKET=reland-models-$(aws sts get-caller-identity --query Account --output text)
USE_REDIS=false
WORKER_NAME=reland-worker-$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
EOF
FETCH_SCRIPT

chmod +x /opt/reland/fetch-secrets.sh

# Create worker startup script
# This worker reads jobs from the database (no Redis needed)
cat > /opt/reland/start-worker.sh <<'WORKER_SCRIPT'
#!/bin/bash
set -e

cd /opt/reland
source ml_venv/bin/activate

# Fetch secrets
./fetch-secrets.sh

# Load environment variables
source .env

# Set macOS fork safety (for compatibility)
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Set CUDA device
export CUDA_VISIBLE_DEVICES=0

# Start database-based worker (no Redis needed)
echo "Starting RELand EC2 Worker at $(date)"
echo "Reading jobs from database..."
python3 ec2_worker_main.py
WORKER_SCRIPT

chmod +x /opt/reland/start-worker.sh

# Create systemd service for worker
cat > /etc/systemd/system/reland-worker.service <<EOF
[Unit]
Description=RELand Background Worker
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/reland
EnvironmentFile=/opt/reland/.env
ExecStart=/opt/reland/start-worker.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
systemctl daemon-reload
systemctl enable reland-worker

# Note: In cost-optimized mode (no Redis), EC2 instances are launched on-demand
# when training is triggered and self-terminate after completion.
# The termination logic is handled by the training script itself or App Runner.

# For synchronous training mode (no Redis), the EC2 instance can be used for
# direct GPU training when triggered from App Runner. The instance should
# terminate itself after training completes.

# Create a simple termination script that can be called after training
cat > /opt/reland/self-terminate.sh <<'TERMINATE_SCRIPT'
#!/bin/bash
# Self-terminate this EC2 instance
AWS_REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)

echo "Terminating instance $INSTANCE_ID after training completion..."
aws ec2 terminate-instances \
    --instance-ids $INSTANCE_ID \
    --region $AWS_REGION
TERMINATE_SCRIPT

chmod +x /opt/reland/self-terminate.sh

# Always start the worker service (for database-based jobs)
# The worker reads jobs from the database and processes them asynchronously
systemctl start reland-worker
echo "Worker service started for database-based job processing"

echo "RELand EC2 Worker setup completed at $(date)"
echo "Worker service status:"
systemctl status reland-worker --no-pager

