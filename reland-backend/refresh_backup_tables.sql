-- Script to refresh backup tables with current data
-- Run this whenever you want to update the backup tables
-- Usage: psql -U reland_user -d reland_db -f refresh_backup_tables.sql

-- Drop existing backup tables
DROP TABLE IF EXISTS locations_backup CASCADE;
DROP TABLE IF EXISTS user_labels_backup CASCADE;
DROP TABLE IF EXISTS confirmed_events_backup CASCADE;

-- Recreate backup tables with current data
CREATE TABLE locations_backup AS 
SELECT * FROM locations;

CREATE TABLE user_labels_backup AS 
SELECT * FROM user_labels;

CREATE TABLE confirmed_events_backup AS 
SELECT * FROM confirmed_events;

-- Verify
SELECT 
    'locations_backup' as table_name, COUNT(*) as row_count FROM locations_backup
UNION ALL
SELECT 
    'user_labels_backup', COUNT(*) FROM user_labels_backup
UNION ALL
SELECT 
    'confirmed_events_backup', COUNT(*) FROM confirmed_events_backup;

