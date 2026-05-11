-- 07-extended-fields-v2.sql
--
-- Extended field coverage for DragonSync v2.0+ schema.
--
-- DragonSync v2.0 introduced kit-scoped MQTT topics and expanded several
-- payload fields. This migration adds columns to capture the fields that
-- were previously dropped on the floor by insert_drone() and
-- insert_system_health() because no DB column existed for them.
--
-- All ADD COLUMN statements use IF NOT EXISTS so this is safe to re-run.
-- Defaults are NULL — existing rows are unaffected. New rows populate as
-- the updated ingest code fills them in.
--
-- High-value additions:
--   drones.description        Carries DJI O2/O3/O4 protocol markers,
--                             OcuSync labels, operator self-ID text.
--                             Currently the single best signal for
--                             distinguishing drone radio protocols.
--   drones.freq_mhz           Frequency normalized to MHz.
--   drones.rid_status, .rid_tracking, .rid_lookup_*
--                             FAA Remote ID database lookup outcomes.
--   drones.ua_type_name       Human-readable UA category (e.g.
--                             "Helicopter or Multirotor").
--   system_health.time_source The kit's time source (gpsd / static / system),
--                             useful for filtering out kits with no real GPS.
--   system_health.gpsd_time_utc / .kit_updated_epoch
--                             Detect clock drift between kit and analytics.

-- ---- drones table ----

ALTER TABLE drones ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS freq_mhz DOUBLE PRECISION;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS rid_status TEXT;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS rid_tracking TEXT;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS rid_lookup_attempted BOOLEAN;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS rid_lookup_success BOOLEAN;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS ua_type_name TEXT;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS operator_id_type TEXT;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS height_type TEXT;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS ew_dir TEXT;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS pressure_altitude DOUBLE PRECISION;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS gps_accuracy DOUBLE PRECISION;
ALTER TABLE drones ADD COLUMN IF NOT EXISTS observed_at DOUBLE PRECISION;

-- Indexes for fields likely to be filtered / grouped by in dashboards.
-- description is the highest-value new filter (protocol family lookups).
CREATE INDEX IF NOT EXISTS idx_drones_description ON drones (description) WHERE description IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drones_ua_type_name ON drones (ua_type_name) WHERE ua_type_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drones_rid_lookup_success ON drones (rid_lookup_success) WHERE rid_lookup_success IS NOT NULL;

-- ---- system_health table ----

ALTER TABLE system_health ADD COLUMN IF NOT EXISTS time_source TEXT;
ALTER TABLE system_health ADD COLUMN IF NOT EXISTS gpsd_time_utc TEXT;
ALTER TABLE system_health ADD COLUMN IF NOT EXISTS kit_updated_epoch BIGINT;

-- ---- Comments to document field provenance ----

COMMENT ON COLUMN drones.description IS
  'Self-reported drone description from RID Self-ID Message or DragonSync protocol-detection label. '
  'Examples: "DJI O4 (Decrypted)", "DJI Mini 2 (O2)", "DJI Encrypted (O4)", operator self-ID text.';
COMMENT ON COLUMN drones.freq_mhz IS
  'Detection frequency normalized to MHz. Set by droneid-go from RID Frequency Message.';
COMMENT ON COLUMN drones.rid_status IS
  'FAA Remote ID database lookup: registration status (e.g. accepted, expired, denied).';
COMMENT ON COLUMN drones.rid_tracking IS
  'FAA Remote ID database lookup: tracking ID.';
COMMENT ON COLUMN drones.rid_lookup_attempted IS
  'Whether DragonSync attempted an FAA RID lookup for this serial.';
COMMENT ON COLUMN drones.rid_lookup_success IS
  'Whether the FAA RID lookup returned a match.';
COMMENT ON COLUMN drones.ua_type_name IS
  'Human-readable Unmanned Aircraft category from RID Basic ID (e.g. "Helicopter or Multirotor", '
  '"Aeroplane/Airplane (Fixed wing)"). See ASTM F3411 UA Type table.';
COMMENT ON COLUMN drones.operator_id_type IS 'Operator ID type from RID Operator ID Message.';
COMMENT ON COLUMN drones.height_type IS 'Height reference type from RID Location/Vector Message.';
COMMENT ON COLUMN drones.ew_dir IS 'East/West direction segment flag from RID Location/Vector Message.';
COMMENT ON COLUMN drones.pressure_altitude IS 'Pressure altitude when present in RID payload.';
COMMENT ON COLUMN drones.gps_accuracy IS 'HA-style numeric accuracy in meters, sourced from horizontal_accuracy.';
COMMENT ON COLUMN drones.observed_at IS 'Unix epoch seconds when DragonSync first received this update.';

COMMENT ON COLUMN system_health.time_source IS
  'Kit time source: gpsd, static, or system. Useful for filtering kits without a real GPS fix.';
COMMENT ON COLUMN system_health.gpsd_time_utc IS
  'GPS-derived UTC time string from gpsd (ISO 8601).';
COMMENT ON COLUMN system_health.kit_updated_epoch IS
  'Unix epoch seconds when the kit published this status. Compare against time column to detect clock drift.';
