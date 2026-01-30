#!/bin/bash
# Script to start the RELand backend server

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Start the Flask server
echo "Starting RELand Backend Server..."
python app.py

