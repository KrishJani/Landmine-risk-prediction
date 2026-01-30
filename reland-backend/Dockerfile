# Build for linux/amd64 (x86_64) to match AWS App Runner platform
# Note: Platform is specified in buildx command, not in FROM
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    libpq-dev \
    curl \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL version for fiona/geopandas
ENV GDAL_VERSION=3.8.0

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/experiments

# Make startup scripts executable
RUN chmod +x /app/run.py && \
    chmod +x /app/minimal_health.py

# Expose port (App Runner will set PORT env var)
EXPOSE 8080

# Health check (more lenient for startup)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# CMD removed - App Runner uses Start command from service configuration
# CMD ["python3", "/app/run.py"]

