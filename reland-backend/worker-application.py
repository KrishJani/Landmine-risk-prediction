"""
Elastic Beanstalk Worker entry point.
EB Worker expects 'application' variable to be the worker app.
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from worker import *

# EB Worker will run this file
# The worker.py script will be executed when this module is imported
if __name__ == '__main__':
    # This will be called by EB Worker
    pass

