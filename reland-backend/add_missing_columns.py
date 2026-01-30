#!/usr/bin/env python3
"""
Migration script to add missing columns to database tables
This ensures the database schema matches the models.

Currently adds:
- dist_old_mine column to locations table
"""
import os
import sys

# Set macOS fork safety BEFORE any imports
os.environ.setdefault('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', 'YES')

from dotenv import load_dotenv
load_dotenv(override=False)

# Import Flask app setup (same as backend-app.py)
from flask import Flask
from flask_cors import CORS
from models import db

# Database configuration (same as backend-app.py)
env = os.getenv('FLASK_ENV', os.getenv('ENVIRONMENT', 'local')).lower()
if env in ['production', 'prod']:
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required in production.")
else:
    DATABASE_URL = os.getenv('LOCAL_DATABASE_URL') or os.getenv(
        'DATABASE_URL',
        'postgresql://reland_user:reland_password123@localhost:5432/reland_db'
    )

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

if __name__ == '__main__':
    with app.app_context():
        print("="*60)
        print("🔄 Database Migration: Adding Missing Columns")
        print("="*60)
        print(f"💾 Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
        print()
        
        from sqlalchemy import text, inspect
        
        # Check current schema
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('locations')]
        print(f"📋 Current columns in 'locations' table: {', '.join(columns)}")
        print()
        
        migrations_applied = []
        
        # Migration 1: Add dist_old_mine column
        if 'dist_old_mine' not in columns:
            print("1️⃣  Adding 'dist_old_mine' column to locations table...")
            try:
                db.session.execute(text("""
                    ALTER TABLE locations 
                    ADD COLUMN dist_old_mine FLOAT
                """))
                db.session.commit()
                print("   ✓ Column 'dist_old_mine' added successfully!")
                migrations_applied.append('dist_old_mine')
            except Exception as e:
                db.session.rollback()
                print(f"   ❌ Error adding column: {str(e)}")
                sys.exit(1)
        else:
            print("1️⃣  Column 'dist_old_mine' already exists. Skipping.")
        
        print()
        print("="*60)
        if migrations_applied:
            print(f"✅ Migration complete! Added columns: {', '.join(migrations_applied)}")
        else:
            print("✅ No migrations needed. Database schema is up to date.")
        print("="*60)
