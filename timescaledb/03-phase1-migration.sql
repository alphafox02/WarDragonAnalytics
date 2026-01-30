-- WarDragon Analytics - Phase 1 Schema Migration
-- Adds additional fields available from DragonSync API
-- Safe to run multiple times (uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS)

-- =============================================================================
-- DRONES TABLE: Additional fields from DragonSync API
-- =============================================================================

-- Vertical speed in m/s (climb/descend rate)
ALTER TABLE drones ADD COLUMN IF NOT EXISTS vspeed DOUBLE PRECISION;
COMMENT ON COLUMN drones.vspeed IS 'Vertical speed in m/s (positive=climbing, negative=descending)';

-- Height above ground level (AGL) vs alt which is MSL
ALTER TABLE drones ADD COLUMN IF NOT EXISTS height DOUBLE PRECISION;
COMMENT ON COLUMN drones.height IS 'Height above ground level (AGL) in meters';

-- Direction/heading from Remote ID (may differ from calculated heading)
ALTER TABLE drones ADD COLUMN IF NOT EXISTS direction DOUBLE PRECISION;
COMMENT ON COLUMN drones.direction IS 'Direction from Remote ID broadcast in degrees (0-359)';

-- Operational status from Remote ID
ALTER TABLE drones ADD COLUMN IF NOT EXISTS op_status TEXT;
COMMENT ON COLUMN drones.op_status IS 'Operational status from Remote ID (ground, airborne, emergency, etc.)';

-- Flight runtime in seconds
ALTER TABLE drones ADD COLUMN IF NOT EXISTS runtime INTEGER;
COMMENT ON COLUMN drones.runtime IS 'Flight runtime in seconds since takeoff';

-- ID type (detection method)
ALTER TABLE drones ADD COLUMN IF NOT EXISTS id_type TEXT;
COMMENT ON COLUMN drones.id_type IS 'Detection method: ble, wifi, dji (OcuSync)';

-- =============================================================================
-- SYSTEM_HEALTH TABLE: Additional fields from DragonSync API
-- =============================================================================

-- SDR temperatures (Pluto SDR / AntSDR)
ALTER TABLE system_health ADD COLUMN IF NOT EXISTS pluto_temp DOUBLE PRECISION;
COMMENT ON COLUMN system_health.pluto_temp IS 'Pluto SDR temperature in Celsius';

ALTER TABLE system_health ADD COLUMN IF NOT EXISTS zynq_temp DOUBLE PRECISION;
COMMENT ON COLUMN system_health.zynq_temp IS 'Zynq FPGA temperature in Celsius';

-- Kit GPS movement data
ALTER TABLE system_health ADD COLUMN IF NOT EXISTS speed DOUBLE PRECISION;
COMMENT ON COLUMN system_health.speed IS 'Kit GPS ground speed in m/s';

ALTER TABLE system_health ADD COLUMN IF NOT EXISTS track DOUBLE PRECISION;
COMMENT ON COLUMN system_health.track IS 'Kit GPS heading/track in degrees (0-359)';

-- GPS fix quality
ALTER TABLE system_health ADD COLUMN IF NOT EXISTS gps_fix BOOLEAN;
COMMENT ON COLUMN system_health.gps_fix IS 'Whether kit has valid GPS fix';

-- =============================================================================
-- SIGNALS TABLE: Additional fields from DragonSync API
-- =============================================================================

-- FPV video standard confidence scores (0.0 - 1.0)
ALTER TABLE signals ADD COLUMN IF NOT EXISTS pal_conf DOUBLE PRECISION;
COMMENT ON COLUMN signals.pal_conf IS 'PAL video standard confidence score (0.0-1.0)';

ALTER TABLE signals ADD COLUMN IF NOT EXISTS ntsc_conf DOUBLE PRECISION;
COMMENT ON COLUMN signals.ntsc_conf IS 'NTSC video standard confidence score (0.0-1.0)';

-- Detection source (which stage detected the signal)
ALTER TABLE signals ADD COLUMN IF NOT EXISTS source TEXT;
COMMENT ON COLUMN signals.source IS 'Detection source: guard (energy), confirm (fpvdet)';

-- Signal type
ALTER TABLE signals ADD COLUMN IF NOT EXISTS signal_type TEXT;
COMMENT ON COLUMN signals.signal_type IS 'Signal type: fpv, dji, etc.';

-- =============================================================================
-- INDEX UPDATES
-- =============================================================================

-- Index for vertical speed queries (detecting rapid climbs/descents)
CREATE INDEX IF NOT EXISTS idx_drones_vspeed ON drones(vspeed, time DESC)
WHERE vspeed IS NOT NULL AND (vspeed > 5 OR vspeed < -5);

-- Index for operational status filtering
CREATE INDEX IF NOT EXISTS idx_drones_op_status ON drones(op_status, time DESC)
WHERE op_status IS NOT NULL;

-- Index for id_type filtering
CREATE INDEX IF NOT EXISTS idx_drones_id_type ON drones(id_type, time DESC)
WHERE id_type IS NOT NULL;

-- Index for SDR temperature monitoring (overheating detection)
CREATE INDEX IF NOT EXISTS idx_system_health_sdr_temp ON system_health(pluto_temp, zynq_temp, time DESC)
WHERE pluto_temp IS NOT NULL OR zynq_temp IS NOT NULL;

-- Index for mobile kit tracking
CREATE INDEX IF NOT EXISTS idx_system_health_mobile ON system_health(speed, time DESC)
WHERE speed IS NOT NULL AND speed > 0;

-- Index for signal source filtering
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source, time DESC)
WHERE source IS NOT NULL;

-- Index for confidence score queries
CREATE INDEX IF NOT EXISTS idx_signals_confidence ON signals(pal_conf, ntsc_conf, time DESC)
WHERE pal_conf IS NOT NULL OR ntsc_conf IS NOT NULL;

-- =============================================================================
-- VERIFICATION
-- =============================================================================

\echo 'Phase 1 migration complete. New columns added:'
\echo '  drones: vspeed, height, direction, op_status, runtime, id_type'
\echo '  system_health: pluto_temp, zynq_temp, speed, track, gps_fix'
\echo '  signals: pal_conf, ntsc_conf, source, signal_type'
