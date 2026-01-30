"""
Script to remove all entries with municipio='Unknown' from the database
"""
import os
from app import create_app
from models import db, Location, ConfirmedEvent, UserLabel

# Create Flask app using refactored structure
app = create_app()

def cleanup_unknown():
    """Remove all entries with municipio='Unknown'"""
    with app.app_context():
        # Count before deletion
        unknown_locations = Location.query.filter_by(municipio='Unknown').all()
        unknown_events = ConfirmedEvent.query.filter_by(municipio='Unknown').all()
        unknown_labels = UserLabel.query.join(Location).filter(Location.municipio == 'Unknown').all()
        
        print(f"Found:")
        print(f"  - {len(unknown_locations)} locations with municipio='Unknown'")
        print(f"  - {len(unknown_events)} confirmed events with municipio='Unknown'")
        print(f"  - {len(unknown_labels)} user labels associated with Unknown locations")
        
        if len(unknown_locations) == 0 and len(unknown_events) == 0:
            print("\n✓ No 'Unknown' entries found. Database is clean.")
            return
        
        # Delete user labels first (they reference locations)
        for label in unknown_labels:
            db.session.delete(label)
        print(f"\n✓ Deleted {len(unknown_labels)} user labels")
        
        # Delete confirmed events
        for event in unknown_events:
            db.session.delete(event)
        print(f"✓ Deleted {len(unknown_events)} confirmed events")
        
        # Delete locations (this will cascade delete any remaining labels)
        for location in unknown_locations:
            db.session.delete(location)
        print(f"✓ Deleted {len(unknown_locations)} locations")
        
        # Commit all changes
        db.session.commit()
        print("\n✓ Cleanup complete! All 'Unknown' entries have been removed.")

if __name__ == '__main__':
    cleanup_unknown()

