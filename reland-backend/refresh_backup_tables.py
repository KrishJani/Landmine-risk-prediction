#!/usr/bin/env python3
"""
Refresh backup tables in the database
This script recreates the backup tables with current data from original tables
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def refresh_backup_tables():
    """Refresh backup tables with current data"""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("Error: DATABASE_URL not found in .env file")
        sys.exit(1)
    
    engine = create_engine(db_url)
    
    print("Refreshing backup tables...")
    
    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()
        
        try:
            # Drop existing backup tables
            print("  Dropping existing backup tables...")
            conn.execute(text("DROP TABLE IF EXISTS locations_backup CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS user_labels_backup CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS confirmed_events_backup CASCADE"))
            
            # Recreate backup tables with current data
            print("  Creating locations_backup...")
            conn.execute(text("""
                CREATE TABLE locations_backup AS 
                SELECT * FROM locations
            """))
            
            print("  Creating user_labels_backup...")
            conn.execute(text("""
                CREATE TABLE user_labels_backup AS 
                SELECT * FROM user_labels
            """))
            
            print("  Creating confirmed_events_backup...")
            conn.execute(text("""
                CREATE TABLE confirmed_events_backup AS 
                SELECT * FROM confirmed_events
            """))
            
            # Commit transaction
            trans.commit()
            
            # Verify
            print("\nVerifying backup tables...")
            result = conn.execute(text("""
                SELECT 
                    'locations_backup' as table_name, COUNT(*) as row_count FROM locations_backup
                UNION ALL
                SELECT 
                    'user_labels_backup', COUNT(*) FROM user_labels_backup
                UNION ALL
                SELECT 
                    'confirmed_events_backup', COUNT(*) FROM confirmed_events_backup
            """))
            
            print("\n✓ Backup tables refreshed successfully!")
            print("\nBackup table row counts:")
            for row in result:
                print(f"  {row[0]}: {row[1]:,} rows")
                
        except Exception as e:
            trans.rollback()
            print(f"✗ Error refreshing backup tables: {e}")
            sys.exit(1)

if __name__ == '__main__':
    refresh_backup_tables()

