#!/bin/bash
# Script to start the RELand backend server

cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate

# Start the Flask server
echo "Starting RELand Backend Server..."
python backend-app.py

