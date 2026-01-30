#!/bin/sh
set -e

echo "Starting RELand Backend"
echo "PORT: ${PORT:-not-set}"

# Use PORT from environment, default to 8080
PORT=${PORT:-8080}

echo "Starting gunicorn on port $PORT"
exec gunicorn --bind "0.0.0.0:$PORT" --workers 1 --timeout 300 --log-level debug --access-logfile - --error-logfile - wsgi:application
