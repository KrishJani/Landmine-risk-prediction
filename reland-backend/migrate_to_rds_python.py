#!/usr/bin/env python3
"""
Python-based migration script to migrate data from local PostgreSQL to RDS.
This avoids pg_dump version mismatch issues by using Python/SQLAlchemy directly.
"""
import os
import sys

# Load dotenv if available (from script directory)
try:
    from dotenv import load_dotenv
    import os as os_module
    # Load .env from the script's directory
    script_dir = os_module.path.dirname(os_module.path.abspath(__file__))
    env_path = os_module.path.join(script_dir, '.env')
    load_dotenv(env_path)  # Try script directory first
    load_dotenv()  # Also try current directory
except ImportError:
    pass  # dotenv not required

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError
from urllib.parse import quote_plus, urlparse, urlunparse

def ensure_ssl_in_url(url):
    """Ensure SSL is enabled in database URL"""
    if 'sslmode' in url:
        return url  # Already has SSL configured
    if '?' not in url:
        return url + '?sslmode=require'
    else:
        return url + '&sslmode=require'

def get_local_connection(local_url=None):
    """Get connection to local database"""
    if local_url:
        local_db_url = local_url
        source = "command line argument"
    else:
        # Prioritize LOCAL_DATABASE_URL to avoid using RDS URL
        local_db_url = os.getenv('LOCAL_DATABASE_URL')
        if local_db_url:
            source = "LOCAL_DATABASE_URL env var"
        else:
            local_db_url = os.getenv('DATABASE_URL')
            if local_db_url:
                source = "DATABASE_URL env var"
            else:
                source = "default"
        
        # If DATABASE_URL points to RDS (contains .rds.amazonaws.com), use default local
        if local_db_url and '.rds.amazonaws.com' in local_db_url:
            print("⚠️  Warning: DATABASE_URL points to RDS. Using default local database.")
            local_db_url = None
            source = "default (RDS detected in DATABASE_URL)"
        
        # Default local database connection
        if not local_db_url:
            local_db_url = 'postgresql://reland_user:reland_password123@localhost:5432/reland_db'
    
    # Mask password in display
    display_url = local_db_url
    if '@' in display_url:
        parts = display_url.split('@')
        if ':' in parts[0]:
            user_pass = parts[0].split(':', 1)
            display_url = f"{user_pass[0]}:***@{parts[1]}"
    print(f"🔗 Local DB ({source}): {display_url}")
    return create_engine(local_db_url)

def get_rds_connection(rds_url):
    """Get connection to RDS database with SSL and optimized pool settings"""
    rds_url = ensure_ssl_in_url(rds_url)
    # Configure connection pool for better reliability with RDS over SSL
    return create_engine(
        rds_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
        connect_args={
            'connect_timeout': 30,  # 30 second connection timeout
            'sslmode': 'require'
        }
    )

def create_tables_in_rds(rds_url_str):
    """Create tables in RDS using SQLAlchemy models"""
    print("="*50)
    print("📋 Creating tables in RDS...")
    print("="*50)
    
    # Ensure SSL is enabled
    rds_url_str = ensure_ssl_in_url(rds_url_str)
    # Debug: show URL (mask password)
    debug_url = rds_url_str
    if '@' in debug_url and ':' in debug_url.split('@')[0]:
        user_pass = debug_url.split('@')[0].split(':', 1)
        debug_url = f"{user_pass[0]}:***@{debug_url.split('@')[1]}"
    print(f"🔗 Using connection: {debug_url}")
    original_db_url = os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL'] = rds_url_str
    os.environ['FLASK_ENV'] = 'production'
    
    try:
        # Import models directly (avoid importing app.py which creates app at module level)
        sys.path.insert(0, os.path.dirname(__file__))
        from flask import Flask
        from models import db
        
        # Create Flask app with RDS URL
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = rds_url_str
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db.init_app(app)
        
        with app.app_context():
            db.create_all()
            print("✅ Tables created in RDS")
            return True
    finally:
        # Restore original DATABASE_URL if it existed
        if original_db_url:
            os.environ['DATABASE_URL'] = original_db_url
        elif 'DATABASE_URL' in os.environ:
            del os.environ['DATABASE_URL']

def migrate_table_data(local_engine, rds_engine, table_name, batch_size=100):
    """Migrate data from local to RDS table"""
    print(f"\n📦 Migrating {table_name}...")
    
    try:
        with local_engine.connect() as local_conn:
            # Check if table exists locally
            inspector = inspect(local_engine)
            if table_name not in inspector.get_table_names():
                print(f"   ⚠️  Table {table_name} not found locally, skipping")
                return 0
            
            # Get row count
            result = local_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            total_rows = result.fetchone()[0]
            
            if total_rows == 0:
                print(f"   ℹ️  Table {table_name} is empty, skipping")
                return 0
            
            print(f"   Found {total_rows:,} rows")
            
            # Check if data already exists in RDS
            with rds_engine.connect() as rds_conn:
                result = rds_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                existing_rows = result.fetchone()[0]
                
                if existing_rows > 0:
                    print(f"   ⚠️  RDS already has {existing_rows:,} rows")
                    # Auto-delete if migrating - use DELETE instead of TRUNCATE for faster execution
                    print(f"   Clearing existing data (this may take a moment)...")
                    import time
                    start_time = time.time()
                    with rds_engine.begin() as trans_conn:
                        # DELETE is faster than TRUNCATE for smaller amounts and doesn't require CASCADE
                        trans_conn.execute(text(f"DELETE FROM {table_name}"))
                    elapsed = time.time() - start_time
                    print(f"   ✓ Cleared {existing_rows:,} rows in {elapsed:.1f}s")
                    # Re-check count after clearing
                    result = rds_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    existing_rows = result.fetchone()[0]
            
            # Get column names
            result = local_conn.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                ORDER BY ordinal_position
            """))
            columns = [row[0] for row in result]
            columns_str = ', '.join(columns)
            
            # Migrate in batches with retry logic and batched transactions
            migrated = 0
            offset = 0
            max_retries = 3
            batches_per_transaction = 10  # Commit every 10 batches (1000 rows with batch_size=100)
            import time
            start_time = time.time()
            
            # Prepare INSERT statement once
            placeholders = ', '.join([f':{col}' for col in columns])
            quoted_table = f'"{table_name}"'
            quoted_columns = ', '.join([f'"{col}"' for col in columns])
            insert_sql = f'INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})'
            
            # Migrate with batched transactions (commit every N batches for better performance)
            batch_num = 0
            pending_batches = []
            
            while offset < total_rows:
                # Fetch batch from local
                result = local_conn.execute(text(f"""
                    SELECT {columns_str} 
                    FROM {table_name} 
                    ORDER BY {columns[0]}
                    LIMIT {batch_size} OFFSET {offset}
                """))
                
                rows = result.fetchall()
                if not rows:
                    break
                
                # Prepare data
                data = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i]
                    data.append(row_dict)
                
                pending_batches.append(data)
                batch_num += 1
                
                # Commit every N batches or at the end
                if batch_num % batches_per_transaction == 0 or offset + batch_size >= total_rows:
                    # Insert all pending batches in a single transaction
                    retry_count = 0
                    success = False
                    
                    while retry_count < max_retries and not success:
                        try:
                            with rds_engine.begin() as trans:
                                for batch_data in pending_batches:
                                    trans.execute(text(insert_sql), batch_data)
                            success = True
                            migrated += sum(len(b) for b in pending_batches)
                            pending_batches = []
                        except Exception as e:
                            retry_count += 1
                            if retry_count < max_retries:
                                wait_time = retry_count * 2
                                print(f"   ⚠️  Transaction failed (attempt {retry_count}/{max_retries}), retrying in {wait_time}s...")
                                time.sleep(wait_time)
                                rds_engine.dispose()  # Reset connection pool
                            else:
                                raise
                
                offset += batch_size
                
                # Progress updates with time estimates
                if migrated % 1000 == 0 or offset >= total_rows:
                    elapsed = time.time() - start_time
                    rate = migrated / elapsed if elapsed > 0 else 0
                    remaining = total_rows - migrated
                    eta = remaining / rate if rate > 0 else 0
                    pct = 100 * migrated // total_rows if total_rows > 0 else 0
                    print(f"   Migrated {migrated:,}/{total_rows:,} rows ({pct}%) | Rate: {rate:.0f} rows/s | ETA: {eta:.0f}s")
            
            print(f"   ✅ Migrated {migrated:,} rows")
            return migrated
            
    except Exception as e:
        print(f"   ❌ Error migrating {table_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return 0

def verify_migration(local_engine, rds_engine):
    """Verify data was migrated correctly"""
    print("\n" + "="*50)
    print("🔍 Verifying migration...")
    print("="*50)
    
    tables = ['locations', 'user_labels', 'confirmed_events', 'training_jobs']
    
    for table in tables:
        try:
            with local_engine.connect() as local_conn:
                result = local_conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                local_count = result.fetchone()[0]
            
            with rds_engine.connect() as rds_conn:
                result = rds_conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                rds_count = result.fetchone()[0]
            
            status = "✅" if local_count == rds_count else "⚠️"
            print(f"{status} {table}: Local={local_count:,}, RDS={rds_count:,}")
            
        except Exception as e:
            print(f"⚠️  {table}: Could not verify - {str(e)}")

if __name__ == '__main__':
    import argparse
    import getpass
    parser = argparse.ArgumentParser(description='Migrate local database to RDS using Python')
    parser.add_argument('--rds-url', type=str, required=False,
                       help='RDS database URL (postgresql://user:pass@host:port/db)')
    parser.add_argument('--rds-host', type=str,
                       help='RDS host (e.g., reland-db.cyt6ces8iruu.us-east-1.rds.amazonaws.com)')
    parser.add_argument('--rds-user', type=str, default='reland_admin',
                       help='RDS username (default: reland_admin)')
    parser.add_argument('--rds-db', type=str, default='reland_db',
                       help='RDS database name (default: reland_db)')
    parser.add_argument('--rds-port', type=int, default=5432,
                       help='RDS port (default: 5432)')
    parser.add_argument('--local-url', type=str,
                       help='Local database URL (default: from LOCAL_DATABASE_URL or DATABASE_URL env var)')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Batch size for migration (default: 100, reduce if timeouts occur)')
    parser.add_argument('--yes', action='store_true',
                       help='Skip confirmation prompts')
    args = parser.parse_args()
    
    # Build RDS URL from components or use provided URL
    if args.rds_url:
        rds_url = args.rds_url
    elif args.rds_host:
        # Prompt for password if not in URL
        password = getpass.getpass(f"Enter password for {args.rds_user}@{args.rds_host}: ")
        # URL-encode password to handle special characters
        encoded_password = quote_plus(password)
        rds_url = f"postgresql://{args.rds_user}:{encoded_password}@{args.rds_host}:{args.rds_port}/{args.rds_db}"
    else:
        print("❌ Error: Either --rds-url or --rds-host must be provided")
        parser.print_help()
        sys.exit(1)
    
    print("="*70)
    print("🚀 Python-based Database Migration")
    print("="*70)
    # Mask password in display
    display_url = rds_url
    if '@' in display_url:
        parts = display_url.split('@')
        if ':' in parts[0]:
            user_pass = parts[0].split(':', 1)
            display_url = f"{user_pass[0]}:***@{parts[1]}"
    print(f"\nRDS URL: {display_url}")
    
    if not args.yes:
        print("\n⚠️  This will:")
        print("   1. Create tables in RDS (if they don't exist)")
        print("   2. Migrate data from local database to RDS")
        print("   3. Verify the migration")
        confirm = input("\nContinue? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Cancelled.")
            sys.exit(0)
    
    try:
        # Ensure RDS URL has SSL enabled
        rds_url = ensure_ssl_in_url(args.rds_url)
        
        # Get connections
        print("\n" + "="*70)
        print("1️⃣  Connecting to databases...")
        print("="*70)
        
        local_engine = get_local_connection(args.local_url)
        rds_engine = get_rds_connection(rds_url)
        
        # Test connections
        with local_engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"✅ Local database connected (PostgreSQL {version.split()[1]})")
            
            # Check if local database has data
            try:
                result = conn.execute(text("SELECT COUNT(*) FROM locations"))
                local_count = result.fetchone()[0]
                if local_count == 0:
                    print(f"⚠️  Warning: Local database is empty ({local_count} locations)")
                    print("   💡 To populate local database, run: python init_database.py")
                    print("   💡 Or load directly into RDS: python setup_rds_database.py --rds-url <RDS_URL>")
                else:
                    print(f"   ✅ Found {local_count:,} locations in local database")
                    # Check other tables too
                    for table in ['user_labels', 'confirmed_events', 'training_jobs']:
                        try:
                            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                            count = result.fetchone()[0]
                            if count > 0:
                                print(f"   ✅ Found {count:,} rows in {table}")
                        except Exception:
                            pass
            except Exception as e:
                print(f"   ℹ️  Could not check local data: {e}")
        
        # Test RDS connection with SSL
        try:
            with rds_engine.connect() as conn:
                result = conn.execute(text("SELECT version();"))
                version = result.fetchone()[0]
                print(f"✅ RDS database connected (PostgreSQL {version.split()[1]})")
        except Exception as e:
            print(f"❌ RDS connection failed: {e}")
            print("\n💡 Troubleshooting:")
            print("   1. Verify the password is correct")
            print("   2. Check if SSL is required (RDS usually requires SSL)")
            print("   3. Verify security group allows your IP")
            print("\n💡 You can provide password interactively:")
            print("   python migrate_to_rds_python.py --rds-host <host> --rds-user <user> --rds-db <db>")
            sys.exit(1)
        
        # Create tables
        print("\n" + "="*70)
        print("2️⃣  Creating tables in RDS...")
        print("="*70)
        
        # Try using Flask models first, fallback to raw SQL if that fails
        try:
            create_tables_in_rds(rds_url)
        except Exception as e:
            print(f"⚠️  Flask-based table creation failed: {e}")
            print("   Trying raw SQL approach...")
            # Fallback: create tables using raw SQL
            from create_rds_tables_sql import create_tables
            create_tables(rds_url)
        
        # Migrate data
        print("\n" + "="*70)
        print("3️⃣  Migrating data...")
        print("="*70)
        
        tables = ['locations', 'user_labels', 'confirmed_events', 'training_jobs']
        total_migrated = 0
        
        print(f"\n📊 Using batch size: {args.batch_size} rows per batch")
        print("   (Reduce with --batch-size if you encounter timeouts)\n")
        
        for table in tables:
            try:
                count = migrate_table_data(local_engine, rds_engine, table, batch_size=args.batch_size)
                total_migrated += count
            except Exception as e:
                print(f"\n❌ Failed to migrate {table}: {e}")
                print(f"   💡 Try reducing batch size: --batch-size 50")
                print(f"   💡 Check RDS connectivity and network settings")
                raise
        
        # Verify
        verify_migration(local_engine, rds_engine)
        
        print("\n" + "="*70)
        print("✅ Migration complete!")
        print("="*70)
        print(f"\nTotal rows migrated: {total_migrated:,}")
        print("\n💡 Migration complete! Your RDS database is ready to use.")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
