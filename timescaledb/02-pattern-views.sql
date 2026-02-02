-- WarDragon Analytics - Pattern Detection Views and Functions
-- This script creates database views and functions for pattern detection
-- and intelligence analysis of drone activity.
--
-- Database: wardragon
-- PostgreSQL Version: 15+
-- TimescaleDB Extension: Required
--
-- Views:
--   - active_threats: Pre-joined view with anomaly detection
--   - multi_kit_detections: Drones seen by multiple kits
--
-- Functions:
--   - detect_coordinated_activity(): Clustering function for grouped drones
--   - calculate_distance_m(): Calculate distance between two lat/lon points

-- =============================================================================
-- UTILITY FUNCTIONS
-- =============================================================================

-- Calculate distance between two lat/lon points in meters using Haversine formula
CREATE OR REPLACE FUNCTION calculate_distance_m(
    lat1 DOUBLE PRECISION,
    lon1 DOUBLE PRECISION,
    lat2 DOUBLE PRECISION,
    lon2 DOUBLE PRECISION
) RETURNS DOUBLE PRECISION AS $$
DECLARE
    earth_radius DOUBLE PRECISION := 6371000; -- Earth radius in meters
    dlat DOUBLE PRECISION;
    dlon DOUBLE PRECISION;
    a DOUBLE PRECISION;
    c DOUBLE PRECISION;
BEGIN
    -- Handle NULL inputs
    IF lat1 IS NULL OR lon1 IS NULL OR lat2 IS NULL OR lon2 IS NULL THEN
        RETURN NULL;
    END IF;

    -- Convert to radians
    dlat := radians(lat2 - lat1);
    dlon := radians(lon2 - lon1);

    -- Haversine formula
    a := sin(dlat/2) * sin(dlat/2) +
         cos(radians(lat1)) * cos(radians(lat2)) *
         sin(dlon/2) * sin(dlon/2);
    c := 2 * atan2(sqrt(a), sqrt(1-a));

    RETURN earth_radius * c;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE;

COMMENT ON FUNCTION calculate_distance_m IS 'Calculate distance in meters between two lat/lon points using Haversine formula';

-- =============================================================================
-- VIEW: active_threats
-- =============================================================================
-- Pre-joined view with anomaly detection logic.
-- This view identifies drones with unusual behavior patterns including:
-- - High speed (>30 m/s)
-- - High altitude (>400m for drones)
-- - Repeated appearances (same drone_id seen multiple times)
-- - Multi-kit detections (seen by 2+ kits)

CREATE OR REPLACE VIEW active_threats AS
WITH recent_activity AS (
    -- Get all drone activity from last hour
    SELECT
        time,
        kit_id,
        drone_id,
        lat,
        lon,
        alt,
        speed,
        heading,
        pilot_lat,
        pilot_lon,
        operator_id,
        freq,
        rssi,
        rid_make,
        rid_model,
        track_type
    FROM drones
    WHERE time >= NOW() - INTERVAL '1 hour'
),
drone_stats AS (
    -- Calculate statistics per drone
    SELECT
        drone_id,
        COUNT(*) AS appearance_count,
        COUNT(DISTINCT kit_id) AS kit_count,
        MIN(time) AS first_seen,
        MAX(time) AS last_seen,
        MAX(speed) AS max_speed,
        MAX(alt) AS max_altitude,
        AVG(speed) AS avg_speed,
        ARRAY_AGG(DISTINCT kit_id) AS detecting_kits
    FROM recent_activity
    WHERE lat IS NOT NULL AND lon IS NOT NULL
    GROUP BY drone_id
)
SELECT
    ra.time,
    ra.kit_id,
    ra.drone_id,
    ra.lat,
    ra.lon,
    ra.alt,
    ra.speed,
    ra.heading,
    ra.pilot_lat,
    ra.pilot_lon,
    ra.operator_id,
    ra.freq,
    ra.rssi,
    ra.rid_make,
    ra.rid_model,
    ra.track_type,
    -- Pattern flags
    (ds.appearance_count >= 2) AS is_repeated,
    (ds.kit_count >= 2) AS is_multi_kit,
    (ra.speed > 30) AS is_high_speed,
    (ra.alt > 400 AND ra.track_type = 'drone') AS is_high_altitude,
    -- Anomaly score (0-4 based on number of flags)
    (
        (CASE WHEN ra.speed > 30 THEN 1 ELSE 0 END) +
        (CASE WHEN ra.alt > 400 AND ra.track_type = 'drone' THEN 1 ELSE 0 END) +
        (CASE WHEN ds.appearance_count >= 3 THEN 1 ELSE 0 END) +
        (CASE WHEN ds.kit_count >= 3 THEN 1 ELSE 0 END)
    ) AS anomaly_score,
    -- Stats from drone_stats
    ds.appearance_count,
    ds.kit_count,
    ds.first_seen,
    ds.last_seen,
    ds.max_speed,
    ds.max_altitude,
    ds.detecting_kits
FROM recent_activity ra
JOIN drone_stats ds ON ra.drone_id = ds.drone_id
ORDER BY anomaly_score DESC, ra.time DESC;

COMMENT ON VIEW active_threats IS 'Active drone threats with anomaly detection and pattern flags (last 1 hour)';

-- =============================================================================
-- VIEW: multi_kit_detections
-- =============================================================================
-- Drones detected by 2+ kits within time windows.
-- Useful for triangulation and correlation analysis.
-- Uses time_bucket for efficient queries.

CREATE OR REPLACE VIEW multi_kit_detections AS
WITH bucketed_detections AS (
    -- Bucket detections into 1-minute intervals for correlation
    SELECT
        time_bucket('1 minute', time) AS bucket,
        drone_id,
        kit_id,
        lat,
        lon,
        alt,
        freq,
        rssi,
        time,
        rid_make,
        rid_model
    FROM drones
    WHERE time >= NOW() - INTERVAL '24 hours'
        AND lat IS NOT NULL
        AND lon IS NOT NULL
),
multi_kit_groups AS (
    -- Find drones seen by multiple kits in same time bucket
    SELECT
        bucket,
        drone_id,
        COUNT(DISTINCT kit_id) AS kit_count,
        ARRAY_AGG(DISTINCT kit_id ORDER BY kit_id) AS kit_ids,
        ARRAY_AGG(
            json_build_object(
                'kit_id', kit_id,
                'lat', lat,
                'lon', lon,
                'rssi', rssi,
                'freq', freq,
                'timestamp', time
            ) ORDER BY rssi DESC
        ) AS detections,
        MAX(rssi) AS max_rssi,
        MIN(rssi) AS min_rssi,
        AVG(rssi) AS avg_rssi,
        MAX(time) AS latest_detection
    FROM bucketed_detections
    GROUP BY bucket, drone_id
    HAVING COUNT(DISTINCT kit_id) >= 2
)
SELECT
    bucket AS time_bucket,
    drone_id,
    kit_count,
    kit_ids,
    detections,
    max_rssi,
    min_rssi,
    avg_rssi,
    latest_detection,
    (kit_count >= 3) AS triangulation_possible
FROM multi_kit_groups
ORDER BY bucket DESC, kit_count DESC;

COMMENT ON VIEW multi_kit_detections IS 'Drones detected by 2+ kits with RSSI comparison (last 24 hours)';

-- =============================================================================
-- FUNCTION: detect_coordinated_activity
-- =============================================================================
-- Clustering algorithm to find groups of drones appearing together.
-- Uses time and location proximity to identify coordinated activity.
--
-- Parameters:
--   p_time_window_minutes: Time window in minutes (default 60)
--   p_distance_threshold_m: Distance threshold in meters (default 500)
--
-- Returns: JSON array of coordinated groups

CREATE OR REPLACE FUNCTION detect_coordinated_activity(
    p_time_window_minutes INTEGER DEFAULT 60,
    p_distance_threshold_m DOUBLE PRECISION DEFAULT 500
) RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    WITH recent_drones AS (
        -- Get recent drone positions
        SELECT DISTINCT ON (drone_id)
            drone_id,
            time,
            lat,
            lon,
            alt,
            kit_id,
            rid_make,
            rid_model
        FROM drones
        WHERE time >= NOW() - make_interval(mins => p_time_window_minutes)
            AND lat IS NOT NULL
            AND lon IS NOT NULL
            AND track_type = 'drone'
        ORDER BY drone_id, time DESC
    ),
    drone_pairs AS (
        -- Find all drone pairs within distance threshold
        SELECT
            d1.drone_id AS drone1_id,
            d2.drone_id AS drone2_id,
            d1.time AS time1,
            d2.time AS time2,
            calculate_distance_m(d1.lat, d1.lon, d2.lat, d2.lon) AS distance_m,
            ABS(EXTRACT(EPOCH FROM (d1.time - d2.time))) AS time_diff_seconds
        FROM recent_drones d1
        CROSS JOIN recent_drones d2
        WHERE d1.drone_id < d2.drone_id  -- Avoid duplicates
            AND calculate_distance_m(d1.lat, d1.lon, d2.lat, d2.lon) <= p_distance_threshold_m
            AND ABS(EXTRACT(EPOCH FROM (d1.time - d2.time))) <= p_time_window_minutes * 60
    ),
    coordinated_groups AS (
        -- Group drones that are close together
        SELECT
            dp.drone1_id,
            COUNT(DISTINCT dp.drone2_id) AS pair_count,
            AVG(dp.distance_m) AS avg_distance_m,
            MAX(dp.time_diff_seconds) AS max_time_diff_seconds
        FROM drone_pairs dp
        GROUP BY dp.drone1_id
        HAVING COUNT(DISTINCT dp.drone2_id) >= 1
    ),
    group_details AS (
        SELECT
            cg.drone1_id,
            cg.pair_count,
            cg.avg_distance_m,
            cg.max_time_diff_seconds,
            json_agg(
                json_build_object(
                    'drone_id', rd.drone_id,
                    'lat', rd.lat,
                    'lon', rd.lon,
                    'alt', rd.alt,
                    'timestamp', rd.time,
                    'kit_id', rd.kit_id,
                    'rid_make', rd.rid_make
                )
            ) AS drones
        FROM coordinated_groups cg
        JOIN drone_pairs dp ON dp.drone1_id = cg.drone1_id
        JOIN recent_drones rd ON rd.drone_id = dp.drone1_id OR rd.drone_id = dp.drone2_id
        GROUP BY cg.drone1_id, cg.pair_count, cg.avg_distance_m, cg.max_time_diff_seconds
    ),
    numbered_groups AS (
        SELECT
            ROW_NUMBER() OVER (ORDER BY pair_count DESC) AS group_id,
            pair_count + 1 AS drone_count,
            drones,
            ROUND(avg_distance_m::numeric, 1) AS avg_distance_m,
            ROUND(max_time_diff_seconds::numeric, 1) AS max_time_diff_seconds,
            CASE
                WHEN pair_count >= 4 THEN 'high'
                WHEN pair_count >= 2 THEN 'medium'
                ELSE 'low'
            END AS correlation_score
        FROM group_details
    )
    SELECT json_agg(
        json_build_object(
            'group_id', group_id,
            'drone_count', drone_count,
            'drones', drones,
            'avg_distance_m', avg_distance_m,
            'max_time_diff_seconds', max_time_diff_seconds,
            'correlation_score', correlation_score
        )
    )
    INTO result
    FROM numbered_groups;

    RETURN COALESCE(result, '[]'::json);
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION detect_coordinated_activity IS 'Detect groups of drones appearing together in time and space';

-- =============================================================================
-- FUNCTION: detect_loitering
-- =============================================================================
-- Detect drones that remain in a geographic area for extended periods.
-- Useful for security monitoring of facilities (prisons, warehouses, etc.)
--
-- Parameters:
--   p_lat: Center latitude of monitored area
--   p_lon: Center longitude of monitored area
--   p_radius_m: Radius in meters to monitor (default 500m)
--   p_min_duration_minutes: Minimum time in area to be considered loitering (default 5)
--   p_time_window_hours: Time window to search (default 24 hours)
--
-- Returns: JSON array of loitering drones with duration and positions

CREATE OR REPLACE FUNCTION detect_loitering(
    p_lat DOUBLE PRECISION,
    p_lon DOUBLE PRECISION,
    p_radius_m DOUBLE PRECISION DEFAULT 500,
    p_min_duration_minutes INTEGER DEFAULT 5,
    p_time_window_hours INTEGER DEFAULT 24
) RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    WITH drones_in_area AS (
        -- Find all drone detections within the radius
        SELECT
            drone_id,
            time,
            lat,
            lon,
            alt,
            speed,
            kit_id,
            rid_make,
            rid_model,
            calculate_distance_m(p_lat, p_lon, lat, lon) AS distance_from_center
        FROM drones
        WHERE time >= NOW() - make_interval(hours => p_time_window_hours)
            AND lat IS NOT NULL
            AND lon IS NOT NULL
            AND track_type = 'drone'
            AND calculate_distance_m(p_lat, p_lon, lat, lon) <= p_radius_m
    ),
    loitering_stats AS (
        -- Calculate time spent in area per drone
        SELECT
            drone_id,
            COUNT(*) AS detection_count,
            MIN(time) AS first_seen,
            MAX(time) AS last_seen,
            EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 60 AS duration_minutes,
            AVG(distance_from_center) AS avg_distance_from_center,
            MIN(distance_from_center) AS min_distance_from_center,
            AVG(speed) AS avg_speed,
            AVG(alt) AS avg_altitude,
            ARRAY_AGG(DISTINCT kit_id) AS detecting_kits,
            MAX(rid_make) AS rid_make,
            MAX(rid_model) AS rid_model
        FROM drones_in_area
        GROUP BY drone_id
        HAVING EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 60 >= p_min_duration_minutes
    )
    SELECT json_agg(
        json_build_object(
            'drone_id', drone_id,
            'duration_minutes', ROUND(duration_minutes::numeric, 1),
            'detection_count', detection_count,
            'first_seen', first_seen,
            'last_seen', last_seen,
            'avg_distance_from_center_m', ROUND(avg_distance_from_center::numeric, 1),
            'min_distance_from_center_m', ROUND(min_distance_from_center::numeric, 1),
            'avg_speed_ms', ROUND(avg_speed::numeric, 1),
            'avg_altitude_m', ROUND(avg_altitude::numeric, 1),
            'detecting_kits', detecting_kits,
            'rid_make', rid_make,
            'rid_model', rid_model,
            'threat_level',
                CASE
                    WHEN duration_minutes > 30 THEN 'critical'
                    WHEN duration_minutes > 15 THEN 'high'
                    WHEN duration_minutes > 10 THEN 'medium'
                    ELSE 'low'
                END
        )
        ORDER BY duration_minutes DESC
    )
    INTO result
    FROM loitering_stats;

    RETURN COALESCE(result, '[]'::json);
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION detect_loitering IS 'Detect drones loitering in a specific geographic area (for facility security monitoring)';


-- =============================================================================
-- FUNCTION: detect_rapid_descent
-- =============================================================================
-- Detect drones with rapid altitude changes that could indicate payload drops.
-- Common pattern for contraband delivery to prisons or secure facilities.
--
-- Parameters:
--   p_time_window_minutes: Time window to search (default 60 minutes)
--   p_min_descent_rate_mps: Minimum descent rate in m/s to flag (default 5 m/s)
--   p_min_descent_m: Minimum total descent in meters (default 30m)
--
-- Returns: JSON array of descent events with details

CREATE OR REPLACE FUNCTION detect_rapid_descent(
    p_time_window_minutes INTEGER DEFAULT 60,
    p_min_descent_rate_mps DOUBLE PRECISION DEFAULT 5.0,
    p_min_descent_m DOUBLE PRECISION DEFAULT 30.0
) RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    WITH ordered_positions AS (
        -- Get all drone positions with previous altitude
        SELECT
            drone_id,
            time,
            lat,
            lon,
            alt,
            speed,
            kit_id,
            rid_make,
            rid_model,
            LAG(alt) OVER (PARTITION BY drone_id ORDER BY time) AS prev_alt,
            LAG(time) OVER (PARTITION BY drone_id ORDER BY time) AS prev_time,
            LAG(lat) OVER (PARTITION BY drone_id ORDER BY time) AS prev_lat,
            LAG(lon) OVER (PARTITION BY drone_id ORDER BY time) AS prev_lon
        FROM drones
        WHERE time >= NOW() - make_interval(mins => p_time_window_minutes)
            AND alt IS NOT NULL
            AND lat IS NOT NULL
            AND lon IS NOT NULL
            AND track_type = 'drone'
    ),
    descent_events AS (
        -- Calculate descent rate and filter for rapid descents
        SELECT
            drone_id,
            time,
            lat,
            lon,
            alt,
            prev_alt,
            prev_time,
            prev_lat,
            prev_lon,
            speed,
            kit_id,
            rid_make,
            rid_model,
            (prev_alt - alt) AS descent_m,
            EXTRACT(EPOCH FROM (time - prev_time)) AS time_diff_seconds,
            (prev_alt - alt) / NULLIF(EXTRACT(EPOCH FROM (time - prev_time)), 0) AS descent_rate_mps
        FROM ordered_positions
        WHERE prev_alt IS NOT NULL
            AND prev_time IS NOT NULL
            AND (prev_alt - alt) >= p_min_descent_m
            AND (prev_alt - alt) / NULLIF(EXTRACT(EPOCH FROM (time - prev_time)), 0) >= p_min_descent_rate_mps
    )
    SELECT json_agg(
        json_build_object(
            'drone_id', drone_id,
            'timestamp', time,
            'lat', lat,
            'lon', lon,
            'start_altitude_m', ROUND(prev_alt::numeric, 1),
            'end_altitude_m', ROUND(alt::numeric, 1),
            'descent_m', ROUND(descent_m::numeric, 1),
            'descent_rate_mps', ROUND(descent_rate_mps::numeric, 1),
            'time_diff_seconds', ROUND(time_diff_seconds::numeric, 1),
            'horizontal_speed_ms', ROUND(speed::numeric, 1),
            'kit_id', kit_id,
            'rid_make', rid_make,
            'rid_model', rid_model,
            'threat_level',
                CASE
                    WHEN descent_rate_mps > 15 THEN 'critical'
                    WHEN descent_rate_mps > 10 THEN 'high'
                    WHEN descent_rate_mps > 7 THEN 'medium'
                    ELSE 'low'
                END,
            'possible_payload_drop', (descent_rate_mps > 8 AND speed < 5)
        )
        ORDER BY time DESC
    )
    INTO result
    FROM descent_events;

    RETURN COALESCE(result, '[]'::json);
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION detect_rapid_descent IS 'Detect rapid altitude descents that may indicate payload drops (for facility security)';


-- =============================================================================
-- FUNCTION: detect_night_activity
-- =============================================================================
-- Detect drone activity during night hours (high suspicion indicator).
-- Night flights near secure facilities are often unauthorized.
--
-- Parameters:
--   p_time_window_hours: Time window to search (default 24 hours)
--   p_night_start_hour: Hour when night begins (default 22 = 10 PM local)
--   p_night_end_hour: Hour when night ends (default 5 = 5 AM local)
--
-- Returns: JSON array of night activity with risk assessment

CREATE OR REPLACE FUNCTION detect_night_activity(
    p_time_window_hours INTEGER DEFAULT 24,
    p_night_start_hour INTEGER DEFAULT 22,
    p_night_end_hour INTEGER DEFAULT 5
) RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    WITH night_activity AS (
        SELECT
            drone_id,
            time,
            lat,
            lon,
            alt,
            speed,
            kit_id,
            rid_make,
            rid_model,
            EXTRACT(HOUR FROM time) AS detection_hour
        FROM drones
        WHERE time >= NOW() - make_interval(hours => p_time_window_hours)
            AND lat IS NOT NULL
            AND lon IS NOT NULL
            AND track_type = 'drone'
            AND (
                EXTRACT(HOUR FROM time) >= p_night_start_hour
                OR EXTRACT(HOUR FROM time) <= p_night_end_hour
            )
    ),
    night_stats AS (
        SELECT
            drone_id,
            COUNT(*) AS detection_count,
            MIN(time) AS first_seen,
            MAX(time) AS last_seen,
            AVG(alt) AS avg_altitude,
            AVG(speed) AS avg_speed,
            ARRAY_AGG(DISTINCT kit_id) AS detecting_kits,
            MAX(rid_make) AS rid_make,
            MAX(rid_model) AS rid_model,
            json_agg(
                json_build_object(
                    'time', time,
                    'lat', lat,
                    'lon', lon,
                    'alt', alt,
                    'speed', speed
                )
                ORDER BY time
            ) AS positions
        FROM night_activity
        GROUP BY drone_id
    )
    SELECT json_agg(
        json_build_object(
            'drone_id', drone_id,
            'detection_count', detection_count,
            'first_seen', first_seen,
            'last_seen', last_seen,
            'avg_altitude_m', ROUND(avg_altitude::numeric, 1),
            'avg_speed_ms', ROUND(avg_speed::numeric, 1),
            'detecting_kits', detecting_kits,
            'rid_make', rid_make,
            'rid_model', rid_model,
            'positions', positions,
            'risk_level',
                CASE
                    WHEN detection_count > 10 THEN 'critical'
                    WHEN detection_count > 5 THEN 'high'
                    WHEN detection_count > 2 THEN 'medium'
                    ELSE 'low'
                END
        )
        ORDER BY detection_count DESC
    )
    INTO result
    FROM night_stats;

    RETURN COALESCE(result, '[]'::json);
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION detect_night_activity IS 'Detect drone activity during night hours (high suspicion indicator)';


-- =============================================================================
-- VIEW: security_alerts
-- =============================================================================
-- Consolidated view of all security-relevant drone activity.
-- Combines loitering, rapid descent, night activity, and other patterns.

CREATE OR REPLACE VIEW security_alerts AS
WITH recent_activity AS (
    SELECT
        time,
        kit_id,
        drone_id,
        lat,
        lon,
        alt,
        speed,
        rid_make,
        rid_model,
        track_type,
        LAG(alt) OVER (PARTITION BY drone_id ORDER BY time) AS prev_alt,
        LAG(time) OVER (PARTITION BY drone_id ORDER BY time) AS prev_time,
        EXTRACT(HOUR FROM time) AS detection_hour
    FROM drones
    WHERE time >= NOW() - INTERVAL '4 hours'
        AND lat IS NOT NULL
        AND lon IS NOT NULL
        AND track_type = 'drone'
),
flagged_activity AS (
    SELECT
        time,
        kit_id,
        drone_id,
        lat,
        lon,
        alt,
        speed,
        rid_make,
        rid_model,
        -- Flag: Rapid descent (possible payload drop)
        CASE
            WHEN prev_alt IS NOT NULL
                AND (prev_alt - alt) > 30
                AND (prev_alt - alt) / NULLIF(EXTRACT(EPOCH FROM (time - prev_time)), 0) > 5
            THEN TRUE
            ELSE FALSE
        END AS is_rapid_descent,
        -- Flag: Night activity
        CASE
            WHEN detection_hour >= 22 OR detection_hour <= 5
            THEN TRUE
            ELSE FALSE
        END AS is_night_activity,
        -- Flag: Low and slow (typical surveillance pattern)
        CASE
            WHEN alt < 50 AND speed < 5 AND speed > 0
            THEN TRUE
            ELSE FALSE
        END AS is_low_slow,
        -- Flag: High speed approach
        CASE
            WHEN speed > 25
            THEN TRUE
            ELSE FALSE
        END AS is_high_speed
    FROM recent_activity
)
SELECT
    time,
    kit_id,
    drone_id,
    lat,
    lon,
    alt,
    speed,
    rid_make,
    rid_model,
    is_rapid_descent,
    is_night_activity,
    is_low_slow,
    is_high_speed,
    -- Calculate overall threat score
    (
        (CASE WHEN is_rapid_descent THEN 3 ELSE 0 END) +
        (CASE WHEN is_night_activity THEN 2 ELSE 0 END) +
        (CASE WHEN is_low_slow THEN 2 ELSE 0 END) +
        (CASE WHEN is_high_speed THEN 1 ELSE 0 END)
    ) AS threat_score,
    -- Threat level based on score
    CASE
        WHEN (
            (CASE WHEN is_rapid_descent THEN 3 ELSE 0 END) +
            (CASE WHEN is_night_activity THEN 2 ELSE 0 END) +
            (CASE WHEN is_low_slow THEN 2 ELSE 0 END) +
            (CASE WHEN is_high_speed THEN 1 ELSE 0 END)
        ) >= 5 THEN 'critical'
        WHEN (
            (CASE WHEN is_rapid_descent THEN 3 ELSE 0 END) +
            (CASE WHEN is_night_activity THEN 2 ELSE 0 END) +
            (CASE WHEN is_low_slow THEN 2 ELSE 0 END) +
            (CASE WHEN is_high_speed THEN 1 ELSE 0 END)
        ) >= 3 THEN 'high'
        WHEN (
            (CASE WHEN is_rapid_descent THEN 3 ELSE 0 END) +
            (CASE WHEN is_night_activity THEN 2 ELSE 0 END) +
            (CASE WHEN is_low_slow THEN 2 ELSE 0 END) +
            (CASE WHEN is_high_speed THEN 1 ELSE 0 END)
        ) >= 1 THEN 'medium'
        ELSE 'low'
    END AS threat_level
FROM flagged_activity
WHERE is_rapid_descent OR is_night_activity OR is_low_slow OR is_high_speed
ORDER BY threat_score DESC, time DESC;

COMMENT ON VIEW security_alerts IS 'Consolidated security alerts with threat scoring (last 4 hours)';


-- =============================================================================
-- INDEXES FOR PATTERN DETECTION
-- =============================================================================
-- Additional indexes to optimize pattern detection queries

-- Index for operator_id lookups (pilot reuse detection)
CREATE INDEX IF NOT EXISTS idx_drones_operator_id ON drones(operator_id, time DESC)
    WHERE operator_id IS NOT NULL;

-- Index for pilot location clustering (pilot reuse by proximity)
CREATE INDEX IF NOT EXISTS idx_drones_pilot_location ON drones(pilot_lat, pilot_lon, time DESC)
    WHERE pilot_lat IS NOT NULL AND pilot_lon IS NOT NULL;

-- Composite index for multi-kit detection queries
CREATE INDEX IF NOT EXISTS idx_drones_id_kit_time ON drones(drone_id, kit_id, time DESC)
    WHERE lat IS NOT NULL AND lon IS NOT NULL;

-- Index for speed-based anomaly queries
CREATE INDEX IF NOT EXISTS idx_drones_speed_anomaly ON drones(speed, time DESC)
    WHERE speed > 30;

-- Index for altitude-based anomaly queries
CREATE INDEX IF NOT EXISTS idx_drones_altitude_anomaly ON drones(alt, time DESC)
    WHERE alt > 400;

-- Index for track_type drone filtering (used by most pattern detection queries)
CREATE INDEX IF NOT EXISTS idx_drones_track_type_drone ON drones(time DESC)
    WHERE track_type = 'drone' AND lat IS NOT NULL AND lon IS NOT NULL;

-- Index for night activity detection (hour extraction)
CREATE INDEX IF NOT EXISTS idx_drones_night_hours ON drones(time DESC)
    WHERE track_type = 'drone'
    AND lat IS NOT NULL
    AND lon IS NOT NULL
    AND (EXTRACT(HOUR FROM time) >= 22 OR EXTRACT(HOUR FROM time) <= 5);

-- =============================================================================
-- GRANTS AND PERMISSIONS
-- =============================================================================
-- Grant necessary permissions to the wardragon database user

-- Grant execute on functions
GRANT EXECUTE ON FUNCTION calculate_distance_m TO wardragon;
GRANT EXECUTE ON FUNCTION detect_coordinated_activity TO wardragon;
GRANT EXECUTE ON FUNCTION detect_loitering TO wardragon;
GRANT EXECUTE ON FUNCTION detect_rapid_descent TO wardragon;
GRANT EXECUTE ON FUNCTION detect_night_activity TO wardragon;

-- Grant select on views
GRANT SELECT ON active_threats TO wardragon;
GRANT SELECT ON multi_kit_detections TO wardragon;
GRANT SELECT ON security_alerts TO wardragon;

-- =============================================================================
-- INITIALIZATION COMPLETE
-- =============================================================================
-- Pattern detection views and functions are now ready.
-- These views and functions support the following pattern detection APIs:
--   - /api/patterns/repeated-drones
--   - /api/patterns/coordinated
--   - /api/patterns/pilot-reuse
--   - /api/patterns/anomalies
--   - /api/patterns/multi-kit
--   - /api/patterns/security-alerts (new: consolidated threat view)
--   - /api/patterns/loitering (new: facility security monitoring)
--   - /api/patterns/rapid-descent (new: payload drop detection)
--   - /api/patterns/night-activity (new: unauthorized night flights)
