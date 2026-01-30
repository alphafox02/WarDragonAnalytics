# WarDragon Analytics - Dashboard Query Reference

This document provides a reference for all SQL queries used in the Grafana dashboards, organized by dashboard and panel.

## Dashboard 1: Tactical Overview

### Panel: Active Drones (Last 5 Min)
```sql
SELECT COUNT(DISTINCT drone_id) AS "Active Drones"
FROM drones
WHERE time >= NOW() - INTERVAL '5 minutes'
  AND ($kit_filter = 'All' OR kit_id = $kit_filter);
```

### Panel: Active Alerts
```sql
-- Count anomalies: altitude > 400m, speed > 30 m/s, or unusual timing
SELECT COUNT(*) AS "Alerts"
FROM (
  SELECT DISTINCT drone_id
  FROM drones
  WHERE time >= NOW() - INTERVAL '1 hour'
    AND ($kit_filter = 'All' OR kit_id = $kit_filter)
    AND (
      alt > 400 OR
      speed > 30 OR
      EXTRACT(HOUR FROM time) BETWEEN 22 AND 5  -- Night flights
    )
) AS anomalies;
```

### Panel: Kit Status Grid
```sql
SELECT
  k.kit_id AS "Kit ID",
  k.name AS "Name",
  k.location AS "Location",
  CASE
    WHEN k.last_seen >= NOW() - INTERVAL '1 minute' THEN 'online'
    WHEN k.last_seen >= NOW() - INTERVAL '5 minutes' THEN 'stale'
    ELSE 'offline'
  END AS "Status",
  COALESCE(EXTRACT(EPOCH FROM (NOW() - k.last_seen))::INTEGER, 0) AS "Last Seen (sec)",
  COALESCE(recent.drone_count, 0) AS "Drones (5m)"
FROM kits k
LEFT JOIN (
  SELECT kit_id, COUNT(DISTINCT drone_id) AS drone_count
  FROM drones
  WHERE time >= NOW() - INTERVAL '5 minutes'
  GROUP BY kit_id
) recent ON k.kit_id = recent.kit_id
WHERE $kit_filter = 'All' OR k.kit_id = $kit_filter
ORDER BY "Status", k.kit_id;
```

### Panel: Drone Count Timeline (Last Hour)
```sql
SELECT
  time_bucket('5 minutes', time) AS time,
  kit_id,
  COUNT(DISTINCT drone_id) AS value
FROM drones
WHERE time >= NOW() - INTERVAL '1 hour'
  AND ($kit_filter = 'All' OR kit_id = $kit_filter)
GROUP BY time_bucket('5 minutes', time), kit_id
ORDER BY time;
```

### Panel: Top RID Makes
```sql
SELECT
  COALESCE(rid_make, 'Unknown') AS "Manufacturer",
  COUNT(DISTINCT drone_id) AS "Unique Drones"
FROM drones
WHERE time >= $__timeFrom()
  AND time <= $__timeTo()
  AND ($kit_filter = 'All' OR kit_id = $kit_filter)
  AND track_type = 'drone'
GROUP BY rid_make
ORDER BY COUNT(DISTINCT drone_id) DESC
LIMIT 10;
```

---

## Dashboard 2: Pattern Analysis

### Panel: Repeated Drone IDs
```sql
WITH drone_appearances AS (
  SELECT
    drone_id,
    MIN(time) AS first_seen,
    MAX(time) AS last_seen,
    COUNT(DISTINCT time_bucket('5 minutes', time)) AS appearances,
    ARRAY_AGG(DISTINCT kit_id) AS kits,
    ARRAY_AGG(DISTINCT COALESCE(rid_make, 'Unknown')) AS makes
  FROM drones
  WHERE time >= $__timeFrom()
    AND time <= $__timeTo()
    AND ($kit_filter = 'All' OR kit_id = $kit_filter)
  GROUP BY drone_id
  HAVING COUNT(DISTINCT time_bucket('5 minutes', time)) > 1
)
SELECT
  drone_id AS "Drone ID",
  appearances AS "Appearances",
  first_seen AS "First Seen",
  last_seen AS "Last Seen",
  EXTRACT(EPOCH FROM (last_seen - first_seen))/60 AS "Duration (min)",
  ARRAY_TO_STRING(kits, ', ') AS "Kits",
  ARRAY_TO_STRING(makes, ', ') AS "Make"
FROM drone_appearances
ORDER BY appearances DESC, last_seen DESC
LIMIT 50;
```

### Panel: Operator Reuse Detection
```sql
-- Find operators controlling multiple drones via operator_id match
WITH operator_matches AS (
  SELECT
    operator_id AS identifier,
    'operator_id' AS method,
    COUNT(DISTINCT drone_id) AS drone_count,
    ARRAY_AGG(DISTINCT drone_id) AS drones,
    MIN(time) AS first_seen,
    MAX(time) AS last_seen
  FROM drones
  WHERE time >= $__timeFrom()
    AND time <= $__timeTo()
    AND ($kit_filter = 'All' OR kit_id = $kit_filter)
    AND operator_id IS NOT NULL
    AND operator_id != ''
  GROUP BY operator_id
  HAVING COUNT(DISTINCT drone_id) > 1
),
-- Find pilots in close proximity with different drones
pilot_proximity AS (
  SELECT
    CONCAT('Pilot@', ROUND(d1.pilot_lat::NUMERIC, 4), ',', ROUND(d1.pilot_lon::NUMERIC, 4)) AS identifier,
    'proximity' AS method,
    COUNT(DISTINCT d1.drone_id) AS drone_count,
    ARRAY_AGG(DISTINCT d1.drone_id) AS drones,
    MIN(d1.time) AS first_seen,
    MAX(d1.time) AS last_seen
  FROM drones d1
  WHERE d1.time >= $__timeFrom()
    AND d1.time <= $__timeTo()
    AND ($kit_filter = 'All' OR d1.kit_id = $kit_filter)
    AND d1.pilot_lat IS NOT NULL
    AND d1.pilot_lon IS NOT NULL
  GROUP BY ROUND(d1.pilot_lat::NUMERIC, 4), ROUND(d1.pilot_lon::NUMERIC, 4)
  HAVING COUNT(DISTINCT d1.drone_id) > 1
)
SELECT
  identifier AS "Operator/Location",
  method AS "Detection Method",
  drone_count AS "Drones",
  ARRAY_TO_STRING(drones, ', ') AS "Drone IDs",
  first_seen AS "First Seen",
  last_seen AS "Last Seen"
FROM (
  SELECT * FROM operator_matches
  UNION ALL
  SELECT * FROM pilot_proximity
) combined
ORDER BY drone_count DESC, last_seen DESC
LIMIT 50;
```

### Panel: Frequency Reuse Patterns
```sql
SELECT
  CONCAT(freq_mhz::INTEGER, ' MHz') AS "Frequency",
  detection_type AS "Type",
  COUNT(*) AS "Detections",
  COUNT(DISTINCT kit_id) AS "Kits"
FROM signals
WHERE time >= $__timeFrom()
  AND time <= $__timeTo()
  AND ($kit_filter = 'All' OR kit_id = $kit_filter)
GROUP BY freq_mhz, detection_type
ORDER BY COUNT(*) DESC
LIMIT 15;
```

### Panel: Coordinated Activity Detection
```sql
-- Detect coordinated activity: multiple drones in same time window
WITH time_windows AS (
  SELECT
    time_bucket('5 minutes', time) AS window,
    COUNT(DISTINCT drone_id) AS drone_count,
    ARRAY_AGG(DISTINCT drone_id) AS drones,
    ARRAY_AGG(DISTINCT kit_id) AS kits,
    MIN(time) AS start_time,
    MAX(time) AS end_time
  FROM drones
  WHERE time >= $__timeFrom()
    AND time <= $__timeTo()
    AND ($kit_filter = 'All' OR kit_id = $kit_filter)
  GROUP BY time_bucket('5 minutes', time)
  HAVING COUNT(DISTINCT drone_id) >= 2
)
SELECT
  CONCAT('Group-', ROW_NUMBER() OVER (ORDER BY start_time DESC)) AS "Group ID",
  drone_count AS "Group Size",
  ARRAY_TO_STRING(drones, ', ') AS "Drone IDs",
  ARRAY_TO_STRING(kits, ', ') AS "Detected By",
  start_time AS "Start Time",
  end_time AS "End Time"
FROM time_windows
ORDER BY drone_count DESC, start_time DESC
LIMIT 50;
```

### Panel: Flight Pattern Map
```sql
SELECT
  time,
  drone_id,
  lat,
  lon,
  alt,
  speed,
  heading,
  track_type,
  COALESCE(rid_make, 'Unknown') AS make
FROM drones
WHERE time >= $__timeFrom()
  AND time <= $__timeTo()
  AND ($kit_filter = 'All' OR kit_id = $kit_filter)
  AND lat IS NOT NULL
  AND lon IS NOT NULL
ORDER BY time DESC
LIMIT 5000;
```

---

## Dashboard 3: Multi-Kit Correlation

### Panel: Multi-Kit Detections (Triangulation Opportunities)
```sql
-- Find drones detected by multiple kits within 1-minute windows
WITH multi_kit_detections AS (
  SELECT
    drone_id,
    time_bucket('1 minute', time) AS time_window,
    COUNT(DISTINCT kit_id) AS kit_count,
    ARRAY_AGG(DISTINCT kit_id) AS kits,
    ARRAY_AGG(DISTINCT CONCAT(kit_id, ':', rssi, 'dBm')) AS rssi_by_kit,
    MAX(rssi) - MIN(rssi) AS rssi_spread,
    AVG(lat) AS avg_lat,
    AVG(lon) AS avg_lon,
    ARRAY_AGG(DISTINCT COALESCE(rid_make, 'Unknown')) AS makes
  FROM drones
  WHERE time >= $__timeFrom()
    AND time <= $__timeTo()
    AND rssi IS NOT NULL
  GROUP BY drone_id, time_bucket('1 minute', time)
  HAVING COUNT(DISTINCT kit_id) >= 2
)
SELECT
  drone_id AS "Drone ID",
  kit_count AS "Kits",
  ARRAY_TO_STRING(kits, ', ') AS "Kit IDs",
  ARRAY_TO_STRING(rssi_by_kit, ', ') AS "RSSI Comparison",
  rssi_spread AS "RSSI Spread",
  ROUND(avg_lat::NUMERIC, 5) AS "Avg Lat",
  ROUND(avg_lon::NUMERIC, 5) AS "Avg Lon",
  time_window AS "Time Window",
  ARRAY_TO_STRING(makes, ', ') AS "Make"
FROM multi_kit_detections
ORDER BY kit_count DESC, time_window DESC
LIMIT 100;
```

### Panel: Kit Coverage Overlap Map
```sql
-- Show kit positions and detection coverage
WITH kit_coverage AS (
  SELECT
    sh.kit_id,
    sh.lat,
    sh.lon,
    sh.alt,
    COUNT(DISTINCT d.drone_id) AS detections
  FROM system_health sh
  LEFT JOIN drones d ON sh.kit_id = d.kit_id
    AND d.time >= $__timeFrom()
    AND d.time <= $__timeTo()
  WHERE sh.time >= $__timeFrom()
    AND sh.time <= $__timeTo()
    AND sh.lat IS NOT NULL
    AND sh.lon IS NOT NULL
  GROUP BY sh.kit_id, sh.lat, sh.lon, sh.alt
)
SELECT
  kit_id,
  AVG(lat) AS lat,
  AVG(lon) AS lon,
  AVG(alt) AS alt,
  SUM(detections) AS detections
FROM kit_coverage
GROUP BY kit_id;
```

### Panel: Detection Density Heatmap
```sql
-- Create heatmap grid of detection density
WITH grid AS (
  SELECT
    time_bucket('10 minutes', time) AS time,
    ROUND(lat::NUMERIC, 2) AS lat_grid,
    ROUND(lon::NUMERIC, 2) AS lon_grid,
    COUNT(*) AS detections
  FROM drones
  WHERE time >= $__timeFrom()
    AND time <= $__timeTo()
    AND lat IS NOT NULL
    AND lon IS NOT NULL
  GROUP BY time_bucket('10 minutes', time), ROUND(lat::NUMERIC, 2), ROUND(lon::NUMERIC, 2)
)
SELECT
  time,
  CONCAT(lat_grid, ',', lon_grid) AS location,
  detections
FROM grid
ORDER BY time;
```

### Panel: Kit Handoff Tracking (RSSI over Time)
```sql
-- Track kit handoffs: show RSSI over time for drones detected by multiple kits
WITH multi_kit_drones AS (
  SELECT DISTINCT drone_id
  FROM drones
  WHERE time >= $__timeFrom()
    AND time <= $__timeTo()
  GROUP BY drone_id
  HAVING COUNT(DISTINCT kit_id) >= 2
  LIMIT 10  -- Limit to top 10 for readability
)
SELECT
  time_bucket('30 seconds', d.time) AS time,
  CONCAT(d.drone_id, ' @ ', d.kit_id) AS metric,
  AVG(d.rssi) AS value
FROM drones d
INNER JOIN multi_kit_drones mkd ON d.drone_id = mkd.drone_id
WHERE d.time >= $__timeFrom()
  AND d.time <= $__timeTo()
  AND d.rssi IS NOT NULL
GROUP BY time_bucket('30 seconds', d.time), d.drone_id, d.kit_id
ORDER BY time;
```

---

## Dashboard 4: Anomaly Detection

### Panel: Altitude Changes with Thresholds
```sql
SELECT
  time_bucket('30 seconds', time) AS time,
  drone_id,
  AVG(alt) AS value
FROM drones
WHERE time >= $__timeFrom()
  AND time <= $__timeTo()
  AND ($kit_filter = 'All' OR kit_id = $kit_filter)
  AND alt IS NOT NULL
  AND alt > 0
GROUP BY time_bucket('30 seconds', time), drone_id
ORDER BY time;
```

### Panel: Speed Anomalies
```sql
SELECT
  time_bucket('30 seconds', time) AS time,
  drone_id,
  AVG(speed) AS value
FROM drones
WHERE time >= $__timeFrom()
  AND time <= $__timeTo()
  AND ($kit_filter = 'All' OR kit_id = $kit_filter)
  AND speed IS NOT NULL
  AND speed > 0
GROUP BY time_bucket('30 seconds', time), drone_id
ORDER BY time;
```

### Panel: Out-of-Pattern Behavior Detection
```sql
WITH anomaly_detection AS (
  SELECT
    drone_id,
    kit_id,
    time,
    alt,
    speed,
    EXTRACT(HOUR FROM time) AS hour,
    CASE
      WHEN alt > 400 THEN 'Excessive Altitude (>400m)'
      WHEN alt > 120 THEN 'High Altitude (>120m)'
      ELSE NULL
    END AS altitude_anomaly,
    CASE
      WHEN speed > 30 THEN 'Very High Speed (>30 m/s)'
      WHEN speed > 20 THEN 'High Speed (>20 m/s)'
      ELSE NULL
    END AS speed_anomaly,
    CASE
      WHEN EXTRACT(HOUR FROM time) BETWEEN 22 AND 23 OR EXTRACT(HOUR FROM time) BETWEEN 0 AND 5 THEN 'Night Flight'
      ELSE NULL
    END AS time_anomaly,
    COALESCE(rid_make, 'Unknown') AS make,
    COALESCE(rid_model, 'Unknown') AS model
  FROM drones
  WHERE time >= $__timeFrom()
    AND time <= $__timeTo()
    AND ($kit_filter = 'All' OR kit_id = $kit_filter)
)
SELECT
  drone_id AS "Drone ID",
  make AS "Make",
  model AS "Model",
  COUNT(*) FILTER (WHERE altitude_anomaly IS NOT NULL OR speed_anomaly IS NOT NULL OR time_anomaly IS NOT NULL) AS "Anomaly Count",
  STRING_AGG(DISTINCT altitude_anomaly, ', ') AS "Altitude Issues",
  STRING_AGG(DISTINCT speed_anomaly, ', ') AS "Speed Issues",
  STRING_AGG(DISTINCT time_anomaly, ', ') AS "Timing Issues",
  MAX(alt) AS "Max Alt (m)",
  MAX(speed) AS "Max Speed (m/s)",
  MIN(time) AS "First Seen",
  MAX(time) AS "Last Seen",
  STRING_AGG(DISTINCT kit_id, ', ') AS "Kits"
FROM anomaly_detection
WHERE altitude_anomaly IS NOT NULL OR speed_anomaly IS NOT NULL OR time_anomaly IS NOT NULL
GROUP BY drone_id, make, model
ORDER BY "Anomaly Count" DESC, "Last Seen" DESC
LIMIT 100;
```

### Panel: Signal Strength Anomalies (RSSI)
```sql
SELECT
  time_bucket('30 seconds', time) AS time,
  CONCAT(drone_id, ' @ ', kit_id) AS metric,
  AVG(rssi) AS value
FROM drones
WHERE time >= $__timeFrom()
  AND time <= $__timeTo()
  AND ($kit_filter = 'All' OR kit_id = $kit_filter)
  AND rssi IS NOT NULL
GROUP BY time_bucket('30 seconds', time), drone_id, kit_id
ORDER BY time;
```

### Panel: Rapid Altitude Changes (Climb/Descent Rate)
```sql
-- Calculate altitude change rate (climb/descent)
WITH altitude_deltas AS (
  SELECT
    time,
    drone_id,
    alt,
    LAG(alt) OVER (PARTITION BY drone_id ORDER BY time) AS prev_alt,
    EXTRACT(EPOCH FROM (time - LAG(time) OVER (PARTITION BY drone_id ORDER BY time))) AS time_diff
  FROM drones
  WHERE time >= $__timeFrom()
    AND time <= $__timeTo()
    AND ($kit_filter = 'All' OR kit_id = $kit_filter)
    AND alt IS NOT NULL
)
SELECT
  time_bucket('1 minute', time) AS time,
  drone_id,
  AVG((alt - prev_alt) / NULLIF(time_diff, 0)) AS value
FROM altitude_deltas
WHERE prev_alt IS NOT NULL
  AND time_diff IS NOT NULL
  AND time_diff > 0
  AND time_diff < 60  -- Ignore gaps > 60 seconds
GROUP BY time_bucket('1 minute', time), drone_id
ORDER BY time;
```

---

## Query Optimization Notes

### TimescaleDB Functions Used
- `time_bucket()`: Aggregates time-series data into fixed intervals
- `LAG()`: Window function for calculating deltas between rows
- `ARRAY_AGG()`: Collects multiple values into PostgreSQL arrays

### Performance Considerations
- All queries use indexed columns (time, kit_id, drone_id)
- LIMIT clauses prevent excessive data transfer
- time_bucket intervals balance detail vs. performance
- WHERE clauses always include time range filters
- HAVING clauses reduce result sets early in aggregation

### Variable Usage
- `$kit_filter`: User-selected kit or 'All'
- `$__timeFrom()`: Grafana start time
- `$__timeTo()`: Grafana end time

### Common Patterns
1. **Recent Activity**: `WHERE time >= NOW() - INTERVAL 'X minutes'`
2. **Aggregation**: `GROUP BY time_bucket('X minutes', time), ...`
3. **Counting Uniques**: `COUNT(DISTINCT column)`
4. **Array Aggregation**: `ARRAY_AGG(DISTINCT column)`
5. **Conditional Counting**: `COUNT(*) FILTER (WHERE condition)`
