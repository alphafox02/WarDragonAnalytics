-- WarDragon Analytics - MQTT Support Migration
-- This script adds support for MQTT-based data ingest from WarDragon kits.
--
-- Changes:
--   - Add 'source' column to kits table (http, mqtt, both)
--   - Make api_url nullable (MQTT-only kits don't need it)
--
-- Run this migration on existing databases:
--   docker exec -i wardragon-timescaledb psql -U wardragon -d wardragon < timescaledb/04-mqtt-support.sql

-- =============================================================================
-- MIGRATION: Add source column to kits table
-- =============================================================================

-- Add source column to track how kit sends data (default 'http' for existing kits)
ALTER TABLE kits ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'http'
    CHECK (source IN ('http', 'mqtt', 'both'));

-- Make api_url nullable (MQTT-only kits don't have an HTTP API URL)
-- Note: We can't directly change NOT NULL to nullable, so we recreate the constraint
ALTER TABLE kits ALTER COLUMN api_url DROP NOT NULL;

-- Create index for filtering by source
CREATE INDEX IF NOT EXISTS idx_kits_source ON kits(source);

-- Add comments
COMMENT ON COLUMN kits.source IS 'Data source type: http (polled), mqtt (pushed), or both';

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
-- Kits table now supports:
--   - HTTP-polled kits (api_url required, source='http')
--   - MQTT-pushed kits (api_url optional, source='mqtt')
--   - Hybrid kits (both api_url and MQTT, source='both')
