#!/bin/bash
# Script to run predictions with database integration
# This script recalculates features and runs the model, saving results to database

# Get timestamp
TIMESTAMP=$(date +"%m%d%Y%H%M%S")

# Default values (can be overridden with environment variables)
MUNICIPIO=${MUNICIPIO:-blockCV}
SUBSET=${SUBSET:-full}
MODEL=${MODEL:-TabCmpt}
OBJECTIVE=${OBJECTIVE:-irm}
N_STEP=${N_STEP:-2}

# Database URL (should be set in environment)
if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL environment variable not set"
    echo "Please set it to your PostgreSQL connection string"
    exit 1
fi

echo "=========================================="
echo "Running Predictions with Database Integration"
echo "=========================================="
echo "Timestamp: $TIMESTAMP"
echo "Municipio: $MUNICIPIO"
echo "Subset: $SUBSET"
echo "Model: $MODEL"
echo "Objective: $OBJECTIVE"
echo "=========================================="
echo ""

# Create experiments directory
mkdir -p "./experiments/$TIMESTAMP"

# Run the model with database integration
python main.py \
    --timestamp "$TIMESTAMP" \
    --municipio "$MUNICIPIO" \
    --subset "$SUBSET" \
    --model "$MODEL" \
    --objective "$OBJECTIVE" \
    --n_step "$N_STEP" \
    --use_db \
    --save_to_db \
    --db_url "$DATABASE_URL" \
    2>&1 | tee "./experiments/$TIMESTAMP/log.txt"

echo ""
echo "=========================================="
echo "Prediction run completed!"
echo "Results saved to: ./experiments/$TIMESTAMP/"
echo "Predictions saved to database"
echo "=========================================="


