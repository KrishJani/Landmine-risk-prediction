#!/usr/bin/env python3
"""
Fix sequences for locations, confirmed_events, and user_labels tables
to ensure auto-increment works properly
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

def fix_sequence(table_name, sequence_name):
    """Fix sequence for a given table"""
    print(f"\n{'='*60}")
    print(f"🔧 Fixing {table_name} table sequence")
    print(f"{'='*60}")
    
    try:
        # Check if sequence exists
        result = db.session.execute(text(f"""
            SELECT sequence_name 
            FROM information_schema.sequences 
            WHERE sequence_name = '{sequence_name}'
        """))
        sequence_exists = result.fetchone() is not None
        
        if not sequence_exists:
            print(f"1️⃣  Creating sequence '{sequence_name}'...")
            # Get max id to set sequence start value
            max_id_result = db.session.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}"))
            max_id = max_id_result.scalar() or 0
            
            db.session.execute(text(f"""
                CREATE SEQUENCE {sequence_name}
                START WITH {max_id + 1}
                INCREMENT BY 1
                NO MINVALUE
                NO MAXVALUE
                CACHE 1
            """))
            db.session.commit()
            print(f"   ✓ Sequence created starting at {max_id + 1}")
        else:
            print(f"1️⃣  Sequence '{sequence_name}' already exists.")
        
        # Set the default value for the id column
        print(f"\n2️⃣  Setting default value for {table_name}.id column...")
        db.session.execute(text(f"""
            ALTER TABLE {table_name} 
            ALTER COLUMN id SET DEFAULT nextval('{sequence_name}'::regclass)
        """))
        db.session.commit()
        print("   ✓ Default value set")
        
        # Make sure the sequence is owned by the column
        print(f"\n3️⃣  Setting sequence ownership...")
        db.session.execute(text(f"""
            ALTER SEQUENCE {sequence_name} OWNED BY {table_name}.id
        """))
        db.session.commit()
        print("   ✓ Sequence ownership set")
        
        print(f"\n✅ {table_name} table sequence fixed!")
        
    except Exception as e:
        db.session.rollback()
        print(f"\n❌ Error fixing {table_name}: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise

if __name__ == '__main__':
    with app.app_context():
        print("="*60)
        print("🔧 Fixing all table sequences")
        print("="*60)
        print(f"💾 Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
        
        try:
            # Fix sequences for all three tables
            fix_sequence('locations', 'locations_id_seq')
            fix_sequence('confirmed_events', 'confirmed_events_id_seq')
            fix_sequence('user_labels', 'user_labels_id_seq')
            
            print("\n" + "="*60)
            print("✅ All sequences fixed! Tables should now auto-increment properly.")
            print("="*60)
            
        except Exception as e:
            print(f"\n❌ Fatal error: {str(e)}")
            import traceback
            print(traceback.format_exc())
            sys.exit(1)
