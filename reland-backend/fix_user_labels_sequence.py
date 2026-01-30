#!/usr/bin/env python3
"""
Fix the user_labels table sequence to ensure auto-increment works properly
"""
import os
import sys

os.environ.setdefault('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', 'YES')

from dotenv import load_dotenv
load_dotenv(override=False)

from flask import Flask
from flask_cors import CORS
from models import db
from sqlalchemy import text

# Database configuration
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
        print("🔧 Fixing user_labels table sequence")
        print("="*60)
        print(f"💾 Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
        print()
        
        try:
            # Check if sequence exists
            result = db.session.execute(text("""
                SELECT sequence_name 
                FROM information_schema.sequences 
                WHERE sequence_name = 'user_labels_id_seq'
            """))
            sequence_exists = result.fetchone() is not None
            
            if not sequence_exists:
                print("1️⃣  Creating sequence 'user_labels_id_seq'...")
                # Get max id to set sequence start value
                max_id_result = db.session.execute(text("SELECT COALESCE(MAX(id), 0) FROM user_labels"))
                max_id = max_id_result.scalar() or 0
                
                db.session.execute(text(f"""
                    CREATE SEQUENCE user_labels_id_seq
                    START WITH {max_id + 1}
                    INCREMENT BY 1
                    NO MINVALUE
                    NO MAXVALUE
                    CACHE 1
                """))
                db.session.commit()
                print(f"   ✓ Sequence created starting at {max_id + 1}")
            else:
                print("1️⃣  Sequence 'user_labels_id_seq' already exists.")
            
            # Set the default value for the id column
            print("\n2️⃣  Setting default value for id column...")
            db.session.execute(text("""
                ALTER TABLE user_labels 
                ALTER COLUMN id SET DEFAULT nextval('user_labels_id_seq'::regclass)
            """))
            db.session.commit()
            print("   ✓ Default value set")
            
            # Make sure the sequence is owned by the column
            print("\n3️⃣  Setting sequence ownership...")
            db.session.execute(text("""
                ALTER SEQUENCE user_labels_id_seq OWNED BY user_labels.id
            """))
            db.session.commit()
            print("   ✓ Sequence ownership set")
            
            print("\n" + "="*60)
            print("✅ Fix complete! The user_labels table should now auto-increment properly.")
            print("="*60)
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error: {str(e)}")
            import traceback
            print(traceback.format_exc())
            sys.exit(1)
