#!/usr/bin/env python3
"""
Restore original tables from backup tables
WARNING: This will overwrite current data!
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def restore_from_backup():
    """Restore original tables from backup tables"""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("Error: DATABASE_URL not found in .env file")
        sys.exit(1)
    
    print("⚠️  WARNING: This will overwrite all current data in original tables!")
    confirm = input("Type 'RESTORE' to confirm: ").strip()
    if confirm != 'RESTORE':
        print("Restore cancelled.")
        return
    
    engine = create_engine(db_url)
    
    print("\nRestoring from backup tables...")
    
    with engine.connect() as conn:
        trans = conn.begin()
        
        try:
            # Restore locations
            print("  Restoring locations...")
            conn.execute(text("TRUNCATE TABLE locations"))
            conn.execute(text("INSERT INTO locations SELECT * FROM locations_backup"))
            
            # Restore user_labels
            print("  Restoring user_labels...")
            conn.execute(text("TRUNCATE TABLE user_labels"))
            conn.execute(text("INSERT INTO user_labels SELECT * FROM user_labels_backup"))
            
            # Restore confirmed_events
            print("  Restoring confirmed_events...")
            conn.execute(text("TRUNCATE TABLE confirmed_events"))
            conn.execute(text("INSERT INTO confirmed_events SELECT * FROM confirmed_events_backup"))
            
            trans.commit()
            
            # Verify
            result = conn.execute(text("""
                SELECT 
                    'locations' as table_name, COUNT(*) as row_count FROM locations
                UNION ALL
                SELECT 
                    'user_labels', COUNT(*) FROM user_labels
                UNION ALL
                SELECT 
                    'confirmed_events', COUNT(*) FROM confirmed_events
            """))
            
            print("\n✓ Tables restored successfully!")
            print("\nRestored table row counts:")
            for row in result:
                print(f"  {row[0]}: {row[1]:,} rows")
                
        except Exception as e:
            trans.rollback()
            print(f"✗ Error restoring tables: {e}")
            sys.exit(1)

if __name__ == '__main__':
    restore_from_backup()

