#!/usr/bin/env python3
"""
RQ Worker script for processing background jobs.
Run this script to start a worker that processes model training jobs.

Usage:
    python worker.py

Or with custom Redis URL:
    REDIS_URL=redis://localhost:6379/0 python worker.py
"""
import os
from dotenv import load_dotenv
from rq import Worker, Queue, Connection
from redis import Redis

# Load environment variables
load_dotenv()

# Get Redis URL from environment
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

if __name__ == '__main__':
    # Connect to Redis
    redis_conn = Redis.from_url(REDIS_URL)
    
    # Create queue
    queue = Queue('model_training', connection=redis_conn)
    
    print("="*50)
    print("🚀 RELand Background Worker")
    print("="*50)
    print(f"Redis URL: {REDIS_URL}")
    print(f"Queue: model_training")
    print("="*50)
    print("Waiting for jobs...")
    print("Press Ctrl+C to stop")
    print("="*50 + "\n")
    
    # Start worker
    with Connection(redis_conn):
        worker = Worker([queue])
        worker.work()

