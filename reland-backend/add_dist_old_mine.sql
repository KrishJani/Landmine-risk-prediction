-- Migration script to add dist_old_mine column to locations table
-- Run this SQL in your PostgreSQL database

ALTER TABLE locations ADD COLUMN IF NOT EXISTS dist_old_mine FLOAT;

-- Verify the column was added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'locations' AND column_name = 'dist_old_mine';











