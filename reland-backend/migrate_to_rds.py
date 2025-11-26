"""
Script to migrate data from local PostgreSQL to RDS.
This preserves all existing data including user labels and confirmed events.
"""
import os
import sys
import subprocess
from dotenv import load_dotenv

load_dotenv()

def export_local_database():
    """Export local database to SQL file"""
    local_db_url = os.getenv('LOCAL_DATABASE_URL', 'postgresql://reland_user:reland_password123@localhost:5432/reland_db')
    backup_file = 'local_db_backup.sql'
    
    print("="*50)
    print("📤 Exporting local database...")
    print("="*50)
    
    try:
        # Use pg_dump to export
        cmd = [
            'pg_dump',
            '--no-owner',
            '--no-acl',
            '--clean',
            '--if-exists',
            local_db_url,
            '-f', backup_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Error exporting database:")
            print(result.stderr)
            return None
        
        print(f"✓ Database exported to {backup_file}")
        return backup_file
        
    except FileNotFoundError:
        print("❌ pg_dump not found. Please install PostgreSQL client tools.")
        print("   Windows: Download from https://www.postgresql.org/download/windows/")
        print("   macOS: brew install postgresql")
        print("   Linux: sudo apt-get install postgresql-client")
        return None
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None

def import_to_rds(backup_file, rds_url):
    """Import SQL file to RDS"""
    print("="*50)
    print("📥 Importing to RDS...")
    print("="*50)
    
    try:
        cmd = ['psql', rds_url, '-f', backup_file]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Error importing to RDS:")
            print(result.stderr)
            return False
        
        print("✓ Database imported to RDS successfully!")
        return True
        
    except FileNotFoundError:
        print("❌ psql not found. Please install PostgreSQL client tools.")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def verify_rds_data(rds_url):
    """Verify data was imported correctly"""
    print("="*50)
    print("🔍 Verifying RDS data...")
    print("="*50)
    
    try:
        import psycopg2
        from urllib.parse import urlparse
        
        # Parse connection string
        parsed = urlparse(rds_url)
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path[1:],  # Remove leading /
            user=parsed.username,
            password=parsed.password
        )
        
        cur = conn.cursor()
        
        # Check counts
        cur.execute("SELECT COUNT(*) FROM locations;")
        locations_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM confirmed_events;")
        events_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM user_labels;")
        labels_count = cur.fetchone()[0]
        
        conn.close()
        
        print(f"✓ Locations: {locations_count}")
        print(f"✓ Confirmed Events: {events_count}")
        print(f"✓ User Labels: {labels_count}")
        print("="*50)
        
        return True
        
    except Exception as e:
        print(f"⚠️  Could not verify (this is okay): {str(e)}")
        return False

if __name__ == '__main__':
    # Get RDS URL from environment or prompt
    rds_url = os.getenv('RDS_DATABASE_URL')
    
    if not rds_url:
        print("Enter your RDS database URL:")
        print("Format: postgresql://username:password@host:port/database")
        rds_url = input("RDS URL: ").strip()
        
        if not rds_url:
            print("❌ RDS URL is required")
            sys.exit(1)
    
    # Export local database
    backup_file = export_local_database()
    if not backup_file:
        sys.exit(1)
    
    # Confirm before importing
    print("\n⚠️  This will overwrite any existing data in RDS!")
    confirm = input("Continue? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("Cancelled.")
        sys.exit(0)
    
    # Import to RDS
    if import_to_rds(backup_file, rds_url):
        # Verify
        verify_rds_data(rds_url)
        print("\n✅ Migration complete!")
    else:
        print("\n❌ Migration failed. Check errors above.")
        sys.exit(1)

