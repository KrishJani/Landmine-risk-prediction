#!/usr/bin/env python3
"""
Create RDS tables using raw SQL (avoids Flask app import issues)
"""
from sqlalchemy import create_engine, text

CREATE_TABLES_SQL = """
-- Create locations table
CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    municipio VARCHAR(100) NOT NULL,
    risk_score DOUBLE PRECISION,
    risk_score_lr DOUBLE PRECISION,
    risk_level VARCHAR(20),
    elevation DOUBLE PRECISION,
    rainfall DOUBLE PRECISION,
    temperature DOUBLE PRECISION,
    population_2012 DOUBLE PRECISION,
    hist_mines DOUBLE PRECISION,
    dist_old_mine DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_locations_lat ON locations(lat);
CREATE INDEX IF NOT EXISTS idx_locations_lon ON locations(lon);
CREATE INDEX IF NOT EXISTS idx_locations_municipio ON locations(municipio);

-- Create user_labels table
CREATE TABLE IF NOT EXISTS user_labels (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
    label INTEGER NOT NULL CHECK (label IN (0, 1)),
    notes TEXT,
    user_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_labels_location_id ON user_labels(location_id);

-- Create confirmed_events table
CREATE TABLE IF NOT EXISTS confirmed_events (
    id SERIAL PRIMARY KEY,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    municipio VARCHAR(100),
    departamento VARCHAR(100),
    event_date DATE,
    description TEXT,
    source VARCHAR(50),
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    eo_event_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_confirmed_events_location_id ON confirmed_events(location_id);
CREATE INDEX IF NOT EXISTS idx_confirmed_events_municipio ON confirmed_events(municipio);

-- Create training_jobs table
CREATE TABLE IF NOT EXISTS training_jobs (
    id VARCHAR(255) PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    municipio VARCHAR(100),
    subset VARCHAR(50),
    model_name VARCHAR(100),
    objective VARCHAR(50),
    n_step INTEGER,
    progress DOUBLE PRECISION DEFAULT 0.0,
    progress_message TEXT,
    result TEXT,
    error_message TEXT,
    ec2_instance_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_training_jobs_status ON training_jobs(status);
CREATE INDEX IF NOT EXISTS idx_training_jobs_created_at ON training_jobs(created_at);
"""

def ensure_ssl_in_url(url):
    """Ensure SSL is enabled in database URL"""
    if 'sslmode' in url:
        return url  # Already has SSL configured
    if '?' not in url:
        return url + '?sslmode=require'
    else:
        return url + '&sslmode=require'

def create_tables(rds_url):
    """Create tables in RDS using raw SQL"""
    rds_url = ensure_ssl_in_url(rds_url)
    engine = create_engine(rds_url)
    
    print("Creating tables in RDS...")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLES_SQL))
    print("✅ Tables created successfully!")

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python create_rds_tables_sql.py <RDS_URL>")
        sys.exit(1)
    
    create_tables(sys.argv[1])
