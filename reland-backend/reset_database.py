"""
Reset database to original state
- Deletes all user labels
- Deletes all confirmed events  
- Resets dist_old_mine and risk_score to original values from CSV
"""
import os
import sys
import pandas as pd
from datetime import datetime

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(__file__))
from models import db, Location, UserLabel, ConfirmedEvent

# Import app - need to handle the hyphen in filename
import importlib.util
spec = importlib.util.spec_from_file_location("backend_app", os.path.join(os.path.dirname(__file__), "backend-app.py"))
backend_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_app)
app = backend_app.app

def reset_database():
    """Reset database to original state"""
    print("="*50)
    print("🔄 Resetting Database to Original State")
    print("="*50)
    print("\n⚠️  WARNING: This will:")
    print("   - Delete ALL user labels")
    print("   - Delete ALL confirmed events")
    print("   - Reset dist_old_mine and risk_score to original CSV values")
    print("\nThis action cannot be undone!")
    
    confirm = input("\nType 'RESET' to confirm: ").strip()
    if confirm != 'RESET':
        print("Reset cancelled.")
        return
    
    with app.app_context():
        # Step 1: Delete all user labels
        print("\n1. Deleting all user labels...")
        labels_deleted = UserLabel.query.delete()
        print(f"   ✓ Deleted {labels_deleted} user labels")
        
        # Step 2: Delete all confirmed events
        print("\n2. Deleting all confirmed events...")
        events_deleted = ConfirmedEvent.query.delete()
        print(f"   ✓ Deleted {events_deleted} confirmed events")
        
        # Step 3: Reset locations from CSV
        print("\n3. Resetting locations from CSV...")
        risk_file = os.path.join(os.path.dirname(__file__), 'risk_map_predictions.csv')
        
        if not os.path.exists(risk_file):
            print(f"   ⚠️  Warning: {risk_file} not found.")
            print("   Skipping location reset. Only clearing labels and events.")
            db.session.commit()
            print("\n✓ Reset complete (partial - locations not reset)")
            return
        
        # Load original CSV data
        df = pd.read_csv(risk_file)
        print(f"   Loaded {len(df)} rows from CSV")
        
        # Create a mapping of coordinates to original values
        csv_map = {}
        for _, row in df.iterrows():
            key = (float(row['LONGITUD_X']), float(row['LATITUD_Y']))
            csv_map[key] = {
                'risk_score': float(row.get('risk_score', 0)) if not pd.isna(row.get('risk_score')) else None,
                'risk_score_lr': float(row.get('risk_score_lr', 0)) if not pd.isna(row.get('risk_score_lr')) else None,
                'risk_level': 'Low' if pd.isna(row.get('risk_score')) or float(row.get('risk_score', 0)) < 1e-30 
                              else ('Medium' if float(row.get('risk_score', 0)) < 1e-20 else 'High')
            }
        
        # Update all locations
        all_locations = Location.query.all()
        updated_count = 0
        not_found_count = 0
        
        for location in all_locations:
            key = (location.lon, location.lat)
            if key in csv_map:
                original = csv_map[key]
                location.risk_score = original['risk_score']
                location.risk_score_lr = original['risk_score_lr']
                location.risk_level = original['risk_level']
                location.dist_old_mine = None  # Reset to None (will be recalculated)
                updated_count += 1
            else:
                not_found_count += 1
                # If not in CSV, reset to None/defaults
                location.risk_score = None
                location.risk_score_lr = None
                location.risk_level = 'Unknown'
                location.dist_old_mine = None
        
        db.session.commit()
        
        print(f"   ✓ Updated {updated_count} locations from CSV")
        if not_found_count > 0:
            print(f"   ⚠️  {not_found_count} locations not found in CSV (reset to defaults)")
        
        print("\n" + "="*50)
        print("✓ Database reset complete!")
        print(f"   - Deleted {labels_deleted} user labels")
        print(f"   - Deleted {events_deleted} confirmed events")
        print(f"   - Reset {updated_count} locations to original values")
        print("="*50)
        print("\nNote: dist_old_mine has been reset to NULL.")
        print("      It will be recalculated when you click 'Recalculate and Predict'.")


if __name__ == '__main__':
    reset_database()


