#!/usr/bin/env python3
"""
Script to set up RDS database with the same schema and data as local database
This script will:
1. Create tables in RDS (if they don't exist)
2. Load data from CSV files (same as init_database.py but for RDS)
"""
import os
import sys
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(__file__))
from models import db, Location, ConfirmedEvent

def ensure_ssl_in_url(url):
    """Ensure SSL is enabled in database URL"""
    if 'sslmode' in url:
        return url  # Already has SSL configured
    if '?' not in url:
        return url + '?sslmode=require'
    else:
        return url + '&sslmode=require'

def setup_rds_database(rds_url):
    """Set up RDS database with schema and data"""
    from flask import Flask
    from app import create_app
    
    # Ensure SSL is enabled for RDS
    rds_url = ensure_ssl_in_url(rds_url)
    
    # Create app with RDS URL
    os.environ['DATABASE_URL'] = rds_url
    os.environ['FLASK_ENV'] = 'production'
    
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = rds_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    
    with app.app_context():
        print("="*50)
        print("🗄️  Setting up RDS Database")
        print("="*50)
        
        # Create tables
        print("Creating database tables...")
        db.create_all()
        print("✓ Database tables created")
        
        # Load data from CSV files
        locations_count = load_risk_predictions()
        events_count = load_eo_events()
        
        print("="*50)
        print(f"✓ RDS database setup complete!")
        print(f"   Locations: {locations_count}")
        print(f"   Confirmed Events: {events_count}")
        print("="*50)


def load_risk_predictions():
    """Load risk_map_predictions.csv into Location table"""
    risk_file = os.path.join(os.path.dirname(__file__), 'risk_map_predictions.csv')
    
    if not os.path.exists(risk_file):
        print(f"⚠️  Warning: {risk_file} not found. Skipping risk predictions import.")
        return 0
    
    print(f"Loading risk predictions from {risk_file}...")
    df = pd.read_csv(risk_file)
    
    # Check if data already exists
    existing_count = Location.query.count()
    if existing_count > 0:
        print(f"⚠️  Database already has {existing_count} locations. Skipping import.")
        print("   To reload, delete the data and restart.")
        return existing_count
    
    locations_added = 0
    for _, row in df.iterrows():
        try:
            # Determine risk level
            risk_score = row.get('risk_score', 0)
            if pd.isna(risk_score):
                risk_level = 'Low'
            else:
                if risk_score < 1e-30:
                    risk_level = 'Low'
                elif risk_score < 1e-20:
                    risk_level = 'Medium'
                else:
                    risk_level = 'High'
            
            location = Location(
                lat=float(row['LATITUD_Y']),
                lon=float(row['LONGITUD_X']),
                municipio=str(row['Municipio']),
                risk_score=float(row.get('risk_score', 0)) if not pd.isna(row.get('risk_score')) else None,
                risk_score_lr=float(row.get('risk_score_lr', 0)) if not pd.isna(row.get('risk_score_lr')) else None,
                risk_level=risk_level,
                elevation=float(row.get('elevation', 0)) if not pd.isna(row.get('elevation')) else None,
                rainfall=float(row.get('rainfall', 0)) if not pd.isna(row.get('rainfall')) else None,
                temperature=float(row.get('temperature', 0)) if not pd.isna(row.get('temperature')) else None,
                population_2012=float(row.get('population_2012', 0)) if not pd.isna(row.get('population_2012')) else None,
                hist_mines=float(row.get('hist_mines', 0)) if not pd.isna(row.get('hist_mines')) else None
            )
            db.session.add(location)
            locations_added += 1
            
            if locations_added % 1000 == 0:
                print(f"  Processed {locations_added} locations...")
                db.session.commit()
                
        except Exception as e:
            print(f"  Error processing row: {e}")
            continue
    
    db.session.commit()
    print(f"✓ Loaded {locations_added} locations from risk_map_predictions.csv")
    return locations_added


def load_eo_events():
    """Load EO_events_2510.csv into ConfirmedEvent table"""
    eo_file = os.path.join(os.path.dirname(__file__), 'EO_events_2510.csv')
    
    if not os.path.exists(eo_file):
        print(f"⚠️  Warning: {eo_file} not found. Skipping EO events import.")
        return 0
    
    print(f"Loading EO events from {eo_file}...")
    df = pd.read_csv(eo_file)
    
    # Check if data already exists
    existing_count = ConfirmedEvent.query.filter_by(source='EO_events').count()
    if existing_count > 0:
        print(f"⚠️  Database already has {existing_count} EO events. Skipping import.")
        return existing_count
    
    events_added = 0
    for idx, row in df.iterrows():
        try:
            # Parse date
            event_date = None
            if 'date' in row and pd.notna(row['date']):
                try:
                    event_date = pd.to_datetime(row['date'])
                except:
                    pass
            
            # Handle column name variations
            lat_col = 'LATITUDE_Y' if 'LATITUDE_Y' in row else 'LATITUD_Y'
            lon_col = 'LONGITUDE_X' if 'LONGITUDE_X' in row else 'LONGITUD_X'
            
            event = ConfirmedEvent(
                lat=float(row[lat_col]),
                lon=float(row[lon_col]),
                municipio=str(row.get('municipio', 'Unknown')),
                departamento=str(row.get('departamento', '')),
                event_date=event_date,
                source='EO_events',
                eo_event_id=f"eo_{idx}"
            )
            db.session.add(event)
            events_added += 1
            
            if events_added % 100 == 0:
                print(f"  Processed {events_added} events...")
                db.session.commit()
                
        except Exception as e:
            print(f"  Error processing row {idx}: {e}")
            continue
    
    db.session.commit()
    print(f"✓ Loaded {events_added} confirmed events from EO_events_2510.csv")
    return events_added


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Set up RDS database with schema and data')
    parser.add_argument('--rds-url', type=str, help='RDS database URL (postgresql://user:pass@host:port/db)', required=True)
    args = parser.parse_args()
    
    setup_rds_database(args.rds_url)
