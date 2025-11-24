"""
Migration script to add dist_old_mine column to locations table

Run this script to add the dist_old_mine column to your database.
You can also run the SQL directly:
    ALTER TABLE locations ADD COLUMN IF NOT EXISTS dist_old_mine FLOAT;
"""
import os
import sys

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(__file__))

# Import app
import importlib.util
spec = importlib.util.spec_from_file_location("backend_app", os.path.join(os.path.dirname(__file__), "backend-app.py"))
backend_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_app)
app = backend_app.app

if __name__ == '__main__':
    with app.app_context():
        print("="*50)
        print("🔄 Adding dist_old_mine column to locations table")
        print("="*50)
        
        try:
            from sqlalchemy import text
            from models import db
            
            # Check if column already exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='locations' AND column_name='dist_old_mine'
            """))
            
            if result.fetchone():
                print("✓ Column 'dist_old_mine' already exists. No migration needed.")
            else:
                # Add the column
                print("Adding dist_old_mine column...")
                db.session.execute(text("""
                    ALTER TABLE locations 
                    ADD COLUMN dist_old_mine FLOAT
                """))
                db.session.commit()
                print("✓ Column 'dist_old_mine' added successfully!")
                
        except ImportError as e:
            print(f"❌ Missing dependency: {str(e)}")
            print("\nYou can run this SQL directly in your PostgreSQL database:")
            print("  ALTER TABLE locations ADD COLUMN IF NOT EXISTS dist_old_mine FLOAT;")
            sys.exit(1)
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error: {str(e)}")
            print("\nYou can run this SQL directly in your PostgreSQL database:")
            print("  ALTER TABLE locations ADD COLUMN IF NOT EXISTS dist_old_mine FLOAT;")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        print("="*50)
        print("✓ Migration complete!")
        print("="*50)

