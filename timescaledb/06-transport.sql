-- WarDragon Analytics - Transport Field Migration
-- Adds RF transport type from droneid-go (WiFi-Beacon, WiFi-NAN, BT5-LR-Extended, etc.)
--
-- Run this migration on existing databases:
--   docker exec -i wardragon-timescaledb psql -U wardragon -d wardragon < timescaledb/06-transport.sql

-- =============================================================================
-- MIGRATION: Add transport column to drones table
-- =============================================================================

ALTER TABLE drones ADD COLUMN IF NOT EXISTS transport TEXT;

COMMENT ON COLUMN drones.transport IS 'RF transport type: WiFi-Beacon, WiFi-NAN, BT5-LR-Extended';

CREATE INDEX IF NOT EXISTS idx_drones_transport ON drones(transport);

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
