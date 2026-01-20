#!/usr/bin/env python3
import os
import sys
import subprocess

print("=" * 70, flush=True)
print("RELand Backend Starting", flush=True)
print("=" * 70, flush=True)

port = os.environ.get('PORT', '8000')
print(f"PORT: {port}", flush=True)
print(f"DATABASE_URL set: {'Yes' if os.environ.get('DATABASE_URL') else 'No'}", flush=True)
print("=" * 70, flush=True)

cmd = [
    'gunicorn',
    f'--bind=0.0.0.0:{port}',
    '--workers=1',
    '--timeout=300',
    '--access-logfile=-',
    '--error-logfile=-',
    'wsgi:application'
]

print(f"Executing: {' '.join(cmd)}", flush=True)
sys.stdout.flush()
os.execvp(cmd[0], cmd)
