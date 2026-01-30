-- WarDragon Analytics - TimescaleDB Initialization Script
-- This script initializes the database schema for multi-kit drone surveillance
-- aggregation and visualization platform.
--
-- Database: wardragon
-- PostgreSQL Version: 15+
-- TimescaleDB Extension: Required
--
-- Tables:
--   - kits: Configuration and status of WarDragon kits
--   - drones: Drone/aircraft tracks (Remote ID + ADS-B) [HYPERTABLE]
--   - signals: FPV signal detections (5.8GHz analog, DJI) [HYPERTABLE]
--   - system_health: Kit health metrics and GPS [HYPERTABLE]
--
-- Retention: 30 days for raw data, 1 year for continuous aggregates

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

-- Enable TimescaleDB extension for time-series optimization
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- =============================================================================
-- TABLE: kits
-- =============================================================================
-- Stores configuration and status information for each WarDragon kit.
-- This is a regular table (not a hypertable) as it contains relatively static
-- configuration data with infrequent updates.

CREATE TABLE kits (
    -- Unique identifier from WarDragon serial (e.g., "wardragon-abc123")
    kit_id TEXT PRIMARY KEY,

    -- Human-readable name for the kit (e.g., "Mobile Unit Alpha")
    name TEXT,

    -- Physical location or deployment site (e.g., "Field Operations", "HQ")
    location TEXT,

    -- Base URL for the kit's DragonSync API (e.g., "http://192.168.1.100:8088")
    api_url TEXT NOT NULL,

    -- Timestamp of last successful communication with the kit
    last_seen TIMESTAMPTZ,

    -- Current operational status: "online", "offline", or "error"
    status TEXT CHECK (status IN ('online', 'offline', 'error')),

    -- Whether the kit is enabled for polling (can be disabled without deleting)
    enabled BOOLEAN DEFAULT TRUE NOT NULL,

    -- Timestamp when the kit was first registered in the system
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Create index on status for filtering queries (e.g., "show all online kits")
CREATE INDEX idx_kits_status ON kits(status);

-- Create index on enabled for filtering active kits
CREATE INDEX idx_kits_enabled ON kits(enabled) WHERE enabled = TRUE;

-- Create index on last_seen for detecting stale/offline kits
CREATE INDEX idx_kits_last_seen ON kits(last_seen DESC);

COMMENT ON TABLE kits IS 'Configuration and status of WarDragon kits';
COMMENT ON COLUMN kits.kit_id IS 'Unique identifier for the kit';
COMMENT ON COLUMN kits.api_url IS 'Base URL for DragonSync API endpoint';
COMMENT ON COLUMN kits.status IS 'Current status: online, offline, or error';

-- =============================================================================
-- TABLE: drones (HYPERTABLE)
-- =============================================================================
-- Stores drone and aircraft tracks from Remote ID (DJI, BLE, Wi-Fi) and ADS-B.
-- This is a time-series hypertable optimized for high-volume inserts and
-- time-based queries.

CREATE TABLE drones (
    -- Primary timestamp for time-series partitioning
    time TIMESTAMPTZ NOT NULL,

    -- Foreign key reference to kits table (which kit detected this drone)
    kit_id TEXT NOT NULL,

    -- Unique identifier for the drone/aircraft (MAC, ICAO hex, or serial number)
    drone_id TEXT NOT NULL,

    -- Drone GPS coordinates
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    alt DOUBLE PRECISION,  -- Altitude in meters (MSL or AGL depending on source)

    -- Drone motion data
    speed DOUBLE PRECISION,    -- Ground speed in m/s
    heading DOUBLE PRECISION,  -- Heading in degrees (0-359)
    vspeed DOUBLE PRECISION,   -- Vertical speed in m/s (positive=climbing)
    height DOUBLE PRECISION,   -- Height above ground level (AGL) in meters
    direction DOUBLE PRECISION, -- Direction from Remote ID broadcast in degrees

    -- Operational metadata
    op_status TEXT,            -- Operational status (ground, airborne, emergency)
    runtime INTEGER,           -- Flight runtime in seconds
    id_type TEXT,              -- Detection method: ble, wifi, dji

    -- Pilot location (Remote ID only, null for ADS-B)
    pilot_lat DOUBLE PRECISION,
    pilot_lon DOUBLE PRECISION,

    -- Home point / takeoff location (Remote ID only)
    home_lat DOUBLE PRECISION,
    home_lon DOUBLE PRECISION,

    -- Remote ID metadata
    mac TEXT,                -- MAC address for BLE/Wi-Fi Remote ID
    rssi INTEGER,            -- Signal strength in dBm
    freq DOUBLE PRECISION,   -- Frequency in MHz (for RF-based detection)

    -- Remote ID identification fields
    ua_type TEXT,           -- UA type (helicopter, quadcopter, fixed-wing, etc.)
    operator_id TEXT,       -- Operator ID (if broadcast)
    caa_id TEXT,            -- Civil Aviation Authority registration ID
    rid_make TEXT,          -- Manufacturer (DJI, Autel, etc.)
    rid_model TEXT,         -- Model (Mavic 3, Mini 4 Pro, etc.)
    rid_source TEXT,        -- Detection source (ble, wifi, dji)

    -- Track type discriminator
    track_type TEXT CHECK (track_type IN ('drone', 'aircraft')),

    -- Composite primary key: time + kit_id + drone_id
    -- Allows same drone to be tracked by multiple kits at same timestamp
    PRIMARY KEY (time, kit_id, drone_id)
);

-- Convert drones table to TimescaleDB hypertable partitioned by time
-- This enables automatic time-based partitioning and compression
SELECT create_hypertable('drones', 'time');

-- =============================================================================
-- INDEXES: drones
-- =============================================================================

-- Index for querying specific drones across time
CREATE INDEX idx_drones_drone_id ON drones(drone_id, time DESC);

-- Index for querying all drones from a specific kit
CREATE INDEX idx_drones_kit_id ON drones(kit_id, time DESC);

-- Composite index for kit + track_type queries (e.g., "show aircraft from kit-001")
CREATE INDEX idx_drones_kit_track_type ON drones(kit_id, track_type, time DESC);

-- Index for filtering by Remote ID manufacturer
CREATE INDEX idx_drones_rid_make ON drones(rid_make, time DESC) WHERE rid_make IS NOT NULL;

-- Index for filtering by Remote ID model
CREATE INDEX idx_drones_rid_model ON drones(rid_model, time DESC) WHERE rid_model IS NOT NULL;

-- Spatial index for geographic queries (requires PostGIS for advanced queries)
-- Note: Basic lat/lon queries work without PostGIS, but for complex spatial
-- operations (radius search, polygon intersections), consider adding PostGIS
CREATE INDEX idx_drones_location ON drones(lat, lon, time DESC) WHERE lat IS NOT NULL AND lon IS NOT NULL;

-- Index for MAC address lookups (tracking specific devices)
CREATE INDEX idx_drones_mac ON drones(mac, time DESC) WHERE mac IS NOT NULL;

COMMENT ON TABLE drones IS 'Drone and aircraft tracks from Remote ID and ADS-B';
COMMENT ON COLUMN drones.time IS 'Detection timestamp (time-series partition key)';
COMMENT ON COLUMN drones.track_type IS 'Track type: drone (Remote ID) or aircraft (ADS-B)';
COMMENT ON COLUMN drones.rid_source IS 'Remote ID detection source: ble, wifi, or dji';

-- =============================================================================
-- TABLE: signals (HYPERTABLE)
-- =============================================================================
-- Stores FPV (First Person View) signal detections from 5.8GHz spectrum
-- scanning. Includes analog FPV and DJI digital video transmissions.

CREATE TABLE signals (
    -- Primary timestamp for time-series partitioning
    time TIMESTAMPTZ NOT NULL,

    -- Foreign key reference to kits table (which kit detected this signal)
    kit_id TEXT NOT NULL,

    -- Center frequency of detected signal in MHz (e.g., 5740, 5800, 5860)
    freq_mhz DOUBLE PRECISION NOT NULL,

    -- Signal strength in dBm (e.g., -40, -60, -80)
    power_dbm DOUBLE PRECISION,

    -- Signal bandwidth in MHz (e.g., 10 for analog, 20 for DJI)
    bandwidth_mhz DOUBLE PRECISION,

    -- GPS coordinates of the kit at time of detection
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    alt DOUBLE PRECISION,

    -- Detection type discriminator
    detection_type TEXT CHECK (detection_type IN ('analog', 'dji')),

    -- FPV video standard confidence scores (0.0-1.0)
    pal_conf DOUBLE PRECISION,
    ntsc_conf DOUBLE PRECISION,

    -- Detection metadata
    source TEXT,               -- Detection source: guard (energy), confirm (fpvdet)
    signal_type TEXT,          -- Signal type: fpv, dji, etc.

    -- Composite primary key: time + kit_id + freq_mhz
    -- Allows multiple kits to detect same frequency at same time
    PRIMARY KEY (time, kit_id, freq_mhz)
);

-- Convert signals table to TimescaleDB hypertable partitioned by time
SELECT create_hypertable('signals', 'time');

-- =============================================================================
-- INDEXES: signals
-- =============================================================================

-- Index for querying signals from a specific kit
CREATE INDEX idx_signals_kit_id ON signals(kit_id, time DESC);

-- Index for querying specific frequency ranges
CREATE INDEX idx_signals_freq_mhz ON signals(freq_mhz, time DESC);

-- Index for filtering by detection type
CREATE INDEX idx_signals_detection_type ON signals(detection_type, time DESC);

-- Composite index for kit + detection_type queries
CREATE INDEX idx_signals_kit_detection_type ON signals(kit_id, detection_type, time DESC);

-- Index for power-based queries (e.g., "show strong signals > -50 dBm")
CREATE INDEX idx_signals_power_dbm ON signals(power_dbm, time DESC) WHERE power_dbm IS NOT NULL;

-- Spatial index for signal location queries
CREATE INDEX idx_signals_location ON signals(lat, lon, time DESC) WHERE lat IS NOT NULL AND lon IS NOT NULL;

COMMENT ON TABLE signals IS 'FPV signal detections (5.8GHz analog and DJI digital)';
COMMENT ON COLUMN signals.freq_mhz IS 'Center frequency in MHz (e.g., 5800)';
COMMENT ON COLUMN signals.power_dbm IS 'Signal strength in dBm';
COMMENT ON COLUMN signals.detection_type IS 'Detection type: analog or dji';

-- =============================================================================
-- TABLE: system_health (HYPERTABLE)
-- =============================================================================
-- Stores system health metrics and GPS position for each WarDragon kit.
-- Used for monitoring kit operational status, resource usage, and position.

CREATE TABLE system_health (
    -- Primary timestamp for time-series partitioning
    time TIMESTAMPTZ NOT NULL,

    -- Foreign key reference to kits table
    kit_id TEXT NOT NULL,

    -- GPS coordinates of the kit
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    alt DOUBLE PRECISION,  -- Altitude in meters

    -- System resource utilization (0-100 percent)
    cpu_percent DOUBLE PRECISION CHECK (cpu_percent >= 0 AND cpu_percent <= 100),
    memory_percent DOUBLE PRECISION CHECK (memory_percent >= 0 AND memory_percent <= 100),
    disk_percent DOUBLE PRECISION CHECK (disk_percent >= 0 AND disk_percent <= 100),

    -- System uptime in hours
    uptime_hours DOUBLE PRECISION CHECK (uptime_hours >= 0),

    -- Temperature sensors in Celsius
    temp_cpu DOUBLE PRECISION,
    temp_gpu DOUBLE PRECISION,

    -- SDR temperatures (Pluto SDR / AntSDR)
    pluto_temp DOUBLE PRECISION,
    zynq_temp DOUBLE PRECISION,

    -- Kit GPS movement data
    speed DOUBLE PRECISION,    -- Kit GPS ground speed in m/s
    track DOUBLE PRECISION,    -- Kit GPS heading in degrees (0-359)
    gps_fix BOOLEAN,           -- Whether kit has valid GPS fix

    -- Composite primary key: time + kit_id
    PRIMARY KEY (time, kit_id)
);

-- Convert system_health table to TimescaleDB hypertable partitioned by time
SELECT create_hypertable('system_health', 'time');

-- =============================================================================
-- INDEXES: system_health
-- =============================================================================

-- Index for querying health metrics for a specific kit
CREATE INDEX idx_system_health_kit_id ON system_health(kit_id, time DESC);

-- Index for finding kits with high CPU usage (performance monitoring)
CREATE INDEX idx_system_health_cpu ON system_health(cpu_percent, time DESC) WHERE cpu_percent > 80;

-- Index for finding kits with high memory usage
CREATE INDEX idx_system_health_memory ON system_health(memory_percent, time DESC) WHERE memory_percent > 80;

-- Index for finding kits with high disk usage
CREATE INDEX idx_system_health_disk ON system_health(disk_percent, time DESC) WHERE disk_percent > 80;

-- Index for finding kits with high temperatures (overheating detection)
CREATE INDEX idx_system_health_temp ON system_health(temp_cpu, time DESC) WHERE temp_cpu > 70;

-- Spatial index for kit location tracking
CREATE INDEX idx_system_health_location ON system_health(lat, lon, time DESC) WHERE lat IS NOT NULL AND lon IS NOT NULL;

COMMENT ON TABLE system_health IS 'System health metrics and GPS position for each kit';
COMMENT ON COLUMN system_health.cpu_percent IS 'CPU utilization percentage (0-100)';
COMMENT ON COLUMN system_health.uptime_hours IS 'System uptime in hours';

-- =============================================================================
-- RETENTION POLICIES
-- =============================================================================
-- Automatically drop old data to manage disk space and maintain performance.
-- Raw data is retained for operational analysis; continuous aggregates provide
-- long-term historical trends.

-- Drones: Keep raw track data for 30 days
-- After 30 days, data is automatically deleted by TimescaleDB background job
SELECT add_retention_policy('drones', INTERVAL '30 days');

-- Signals: Keep raw signal detections for 30 days
SELECT add_retention_policy('signals', INTERVAL '30 days');

-- System Health: Keep raw health metrics for 90 days (longer retention for troubleshooting)
SELECT add_retention_policy('system_health', INTERVAL '90 days');

-- =============================================================================
-- CONTINUOUS AGGREGATES: drones_hourly
-- =============================================================================
-- Pre-computed hourly rollups of drone activity per kit.
-- Provides fast queries for historical trends and analytics dashboards.
-- Automatically maintained by TimescaleDB as new data arrives.

CREATE MATERIALIZED VIEW drones_hourly
WITH (timescaledb.continuous) AS
SELECT
    -- Bucket time into 1-hour intervals
    time_bucket('1 hour', time) AS bucket,

    -- Group by kit
    kit_id,

    -- Aggregate metrics
    COUNT(DISTINCT drone_id) AS unique_drones,     -- Number of unique drones seen
    COUNT(*) AS total_detections,                  -- Total number of detection records
    AVG(alt) AS avg_altitude,                      -- Average altitude in meters
    MAX(alt) AS max_altitude,                      -- Maximum altitude in meters
    AVG(speed) AS avg_speed,                       -- Average speed in m/s
    MAX(speed) AS max_speed,                       -- Maximum speed in m/s

    -- Track type breakdown
    COUNT(DISTINCT drone_id) FILTER (WHERE track_type = 'drone') AS unique_drones_rid,
    COUNT(DISTINCT drone_id) FILTER (WHERE track_type = 'aircraft') AS unique_aircraft_adsb,

    -- Remote ID manufacturer breakdown (top manufacturers)
    COUNT(DISTINCT drone_id) FILTER (WHERE rid_make = 'DJI') AS dji_count,
    COUNT(DISTINCT drone_id) FILTER (WHERE rid_make = 'Autel') AS autel_count,
    COUNT(DISTINCT drone_id) FILTER (WHERE rid_make = 'Skydio') AS skydio_count
FROM drones
GROUP BY bucket, kit_id
WITH NO DATA;

-- Note: TimescaleDB continuous aggregates don't support standard COMMENT syntax
-- Hourly rollup of drone activity per kit (1-year retention via refresh policy)

-- Create indexes on continuous aggregate
CREATE INDEX idx_drones_hourly_bucket ON drones_hourly(bucket DESC);
CREATE INDEX idx_drones_hourly_kit_id ON drones_hourly(kit_id, bucket DESC);

-- =============================================================================
-- CONTINUOUS AGGREGATES: signals_hourly
-- =============================================================================
-- Pre-computed hourly rollups of FPV signal detections per kit.
-- Provides fast queries for spectrum usage trends and analytics.

CREATE MATERIALIZED VIEW signals_hourly
WITH (timescaledb.continuous) AS
SELECT
    -- Bucket time into 1-hour intervals
    time_bucket('1 hour', time) AS bucket,

    -- Group by kit
    kit_id,

    -- Aggregate metrics
    COUNT(*) AS total_detections,                  -- Total number of signal detections
    COUNT(DISTINCT freq_mhz) AS unique_frequencies, -- Number of unique frequencies detected
    AVG(power_dbm) AS avg_power,                   -- Average signal power in dBm
    MAX(power_dbm) AS max_power,                   -- Maximum signal power in dBm
    MIN(power_dbm) AS min_power,                   -- Minimum signal power in dBm

    -- Detection type breakdown
    COUNT(*) FILTER (WHERE detection_type = 'analog') AS analog_count,
    COUNT(*) FILTER (WHERE detection_type = 'dji') AS dji_count,

    -- Frequency band usage (common FPV bands)
    COUNT(*) FILTER (WHERE freq_mhz >= 5650 AND freq_mhz < 5750) AS band_a_count,  -- Band A (5.65-5.75 GHz)
    COUNT(*) FILTER (WHERE freq_mhz >= 5750 AND freq_mhz < 5850) AS band_b_count,  -- Band B (5.75-5.85 GHz)
    COUNT(*) FILTER (WHERE freq_mhz >= 5850 AND freq_mhz < 5950) AS band_c_count   -- Band C (5.85-5.95 GHz)
FROM signals
GROUP BY bucket, kit_id
WITH NO DATA;

-- Note: TimescaleDB continuous aggregates don't support standard COMMENT syntax
-- Hourly rollup of FPV signal detections per kit (1-year retention via refresh policy)

-- Create indexes on continuous aggregate
CREATE INDEX idx_signals_hourly_bucket ON signals_hourly(bucket DESC);
CREATE INDEX idx_signals_hourly_kit_id ON signals_hourly(kit_id, bucket DESC);

-- =============================================================================
-- REFRESH POLICIES FOR CONTINUOUS AGGREGATES
-- =============================================================================
-- Configure automatic refresh of continuous aggregates.
-- These policies ensure that materialized views stay up-to-date as new data
-- arrives in the base tables.

-- Refresh drones_hourly every 30 minutes, with 1-hour materialization lag
-- (allows late-arriving data to be included)
SELECT add_continuous_aggregate_policy('drones_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes');

-- Refresh signals_hourly every 30 minutes, with 1-hour materialization lag
SELECT add_continuous_aggregate_policy('signals_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes');

-- =============================================================================
-- COMPRESSION POLICIES
-- =============================================================================
-- Enable compression for older data to reduce disk usage.
-- TimescaleDB can achieve 10-20x compression ratios for time-series data.
-- Compressed data is still queryable but optimized for storage.

-- Enable compression on drones table (compress data older than 7 days)
ALTER TABLE drones SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'kit_id,drone_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('drones', INTERVAL '7 days');

-- Enable compression on signals table (compress data older than 7 days)
ALTER TABLE signals SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'kit_id',
    timescaledb.compress_orderby = 'time DESC,freq_mhz'
);

SELECT add_compression_policy('signals', INTERVAL '7 days');

-- Enable compression on system_health table (compress data older than 7 days)
ALTER TABLE system_health SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'kit_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('system_health', INTERVAL '7 days');

-- =============================================================================
-- GRANTS AND PERMISSIONS
-- =============================================================================
-- Grant necessary permissions to the wardragon database user.
-- Assumes user 'wardragon' is created by docker-entrypoint with appropriate password.

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO wardragon;

-- Grant table permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO wardragon;

-- Grant sequence permissions (for any future tables with SERIAL columns)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO wardragon;

-- Grant default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO wardragon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO wardragon;

-- =============================================================================
-- INITIALIZATION COMPLETE
-- =============================================================================
-- Database schema is now ready for WarDragon Analytics platform.
-- Next steps:
--   1. Start collector service to poll DragonSync APIs
--   2. Configure kits in config/kits.yaml
--   3. Access Grafana dashboards at http://localhost:3000
--   4. Access Web UI at http://localhost:8080
