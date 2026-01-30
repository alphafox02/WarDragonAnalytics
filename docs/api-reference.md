# WarDragon Analytics - API Reference

Complete reference documentation for all WarDragon Analytics REST API endpoints.

**Base URL:** `http://localhost:8090` (default)

**Format:** JSON

**Authentication:** None (add authentication in production - see [SECURITY.md](../SECURITY.md))

---

## Table of Contents

- [Overview](#overview)
- [Core Endpoints (Phase 1)](#core-endpoints-phase-1)
  - [Health Check](#health-check)
  - [Kit Management](#kit-management)
  - [Drone Tracks](#drone-tracks)
  - [Signal Detections](#signal-detections)
  - [CSV Export](#csv-export)
- [Pattern Detection Endpoints (Phase 2)](#pattern-detection-endpoints-phase-2)
  - [Repeated Drones](#repeated-drones)
  - [Coordinated Activity](#coordinated-activity)
  - [Pilot Reuse](#pilot-reuse)
  - [Anomalies](#anomalies)
  - [Multi-Kit Detections](#multi-kit-detections)
- [Error Codes](#error-codes)
- [Data Models](#data-models)
- [Integration Examples](#integration-examples)

---

## Overview

WarDragon Analytics provides a REST API for querying drone surveillance data aggregated from multiple WarDragon kits. The API is built with FastAPI and returns JSON responses.

**API Version:** 1.0.0

**Key Features:**
- Real-time drone track queries
- FPV signal detection data
- Multi-kit aggregation
- Pattern detection and anomaly identification
- CSV export for offline analysis
- Kit health monitoring

---

## Core Endpoints (Phase 1)

### Health Check

Check if the API and database are available.

**Endpoint:** `GET /health`

**Use Case:** Container healthcheck, monitoring, uptime checks

**Parameters:** None

**Response:**
```json
{
  "status": "healthy"
}
```

**Status Codes:**
- `200 OK` - Service is healthy
- `503 Service Unavailable` - Database connection failed

**Example:**
```bash
curl http://localhost:8090/health
```

---

### Kit Management

Query information about configured WarDragon kits.

**Endpoint:** `GET /api/kits`

**Use Case:** Get kit status, monitor kit health, list available kits

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kit_id` | string | No | Filter by specific kit ID |

**Response:**
```json
{
  "kits": [
    {
      "kit_id": "kit-alpha",
      "name": "Alpha Kit",
      "location": "Building A - Rooftop",
      "api_url": "http://192.168.1.100:8088",
      "last_seen": "2026-01-20T15:30:00Z",
      "status": "online",
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "count": 1
}
```

**Kit Status Values:**
- `online` - Last seen < 30 seconds ago
- `stale` - Last seen 30-120 seconds ago
- `offline` - Last seen > 120 seconds ago
- `unknown` - Never seen or no data

**Status Codes:**
- `200 OK` - Success
- `500 Internal Server Error` - Database error

**Example:**
```bash
# List all kits
curl http://localhost:8090/api/kits

# Get specific kit
curl "http://localhost:8090/api/kits?kit_id=kit-alpha"
```

---

### Drone Tracks

Query drone and aircraft detections with time-based and attribute filters.

**Endpoint:** `GET /api/drones`

**Use Case:** Retrieve drone tracks for visualization, analysis, or export

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `time_range` | string | No | `1h` | Time range: `1h`, `24h`, `7d`, or `custom:START,END` |
| `kit_id` | string | No | - | Filter by kit ID (comma-separated for multiple) |
| `rid_make` | string | No | - | Filter by manufacturer (e.g., `DJI`, `Autel`) |
| `track_type` | string | No | - | Filter by type: `drone` or `aircraft` |
| `limit` | integer | No | `1000` | Maximum results (max 10,000) |

**Time Range Formats:**
- `1h` - Last 1 hour
- `24h` - Last 24 hours
- `7d` - Last 7 days
- `custom:2026-01-20T10:00:00,2026-01-20T12:00:00` - Custom ISO timestamps

**Response:**
```json
{
  "drones": [
    {
      "time": "2026-01-20T15:30:00Z",
      "kit_id": "kit-alpha",
      "drone_id": "DJI-1234567890ABCDEF",
      "lat": 37.7749,
      "lon": -122.4194,
      "alt": 120.5,
      "speed": 15.2,
      "heading": 180.0,
      "pilot_lat": 37.7750,
      "pilot_lon": -122.4190,
      "home_lat": 37.7751,
      "home_lon": -122.4191,
      "mac": "AA:BB:CC:DD:EE:FF",
      "rssi": -65,
      "freq": 2412.0,
      "ua_type": "multirotor",
      "operator_id": "OP12345678",
      "caa_id": null,
      "rid_make": "DJI",
      "rid_model": "Mavic 3",
      "rid_source": "BLE",
      "track_type": "drone"
    }
  ],
  "count": 1,
  "time_range": "1h"
}
```

**Status Codes:**
- `200 OK` - Success
- `500 Internal Server Error` - Database error

**Example:**
```bash
# Last hour of all drones
curl http://localhost:8090/api/drones

# DJI drones only, last 24 hours
curl "http://localhost:8090/api/drones?time_range=24h&rid_make=DJI"

# Specific kit, last 7 days
curl "http://localhost:8090/api/drones?time_range=7d&kit_id=kit-alpha"

# Multiple kits
curl "http://localhost:8090/api/drones?kit_id=kit-alpha,kit-bravo"

# Custom time range
curl "http://localhost:8090/api/drones?time_range=custom:2026-01-20T10:00:00,2026-01-20T12:00:00"
```

---

### Signal Detections

Query FPV and RF signal detections (5.8GHz analog, DJI, etc.).

**Endpoint:** `GET /api/signals`

**Use Case:** Analyze FPV signal activity, frequency usage, signal strength

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `time_range` | string | No | `1h` | Time range: `1h`, `24h`, `7d`, or `custom:START,END` |
| `kit_id` | string | No | - | Filter by kit ID (comma-separated) |
| `detection_type` | string | No | - | Filter by type: `analog_fpv`, `dji_fpv`, etc. |
| `min_freq_mhz` | float | No | - | Minimum frequency (MHz) |
| `max_freq_mhz` | float | No | - | Maximum frequency (MHz) |
| `limit` | integer | No | `1000` | Maximum results (max 10,000) |

**Response:**
```json
{
  "signals": [
    {
      "time": "2026-01-20T15:30:00Z",
      "kit_id": "kit-alpha",
      "freq_mhz": 5800.0,
      "power_dbm": -45.0,
      "bandwidth_mhz": 10.0,
      "lat": 37.7749,
      "lon": -122.4194,
      "alt": 10.0,
      "detection_type": "analog_fpv"
    }
  ],
  "count": 1,
  "time_range": "1h"
}
```

**Detection Types:**
- `analog_fpv` - 5.8GHz analog FPV video
- `dji_fpv` - DJI digital FPV (OcuSync)
- `rc_control` - RC control signals
- `wifi` - WiFi signals
- `unknown` - Unidentified RF signals

**Status Codes:**
- `200 OK` - Success
- `500 Internal Server Error` - Database error

**Example:**
```bash
# All signals, last hour
curl http://localhost:8090/api/signals

# 5.8GHz FPV signals only
curl "http://localhost:8090/api/signals?min_freq_mhz=5600&max_freq_mhz=6000"

# Analog FPV detections, last 24 hours
curl "http://localhost:8090/api/signals?time_range=24h&detection_type=analog_fpv"
```

---

### CSV Export

Export drone tracks to CSV format for offline analysis.

**Endpoint:** `GET /api/export/csv`

**Use Case:** Download data for Excel, spreadsheet analysis, or archival

**Parameters:**

Same as `/api/drones` endpoint (see [Drone Tracks](#drone-tracks))

**Response:** CSV file download

**Content-Type:** `text/csv`

**Filename:** `wardragon_analytics_YYYYMMDD_HHMMSS.csv`

**CSV Columns:**
```
time,kit_id,drone_id,lat,lon,alt,speed,heading,pilot_lat,pilot_lon,home_lat,home_lon,mac,rssi,freq,ua_type,operator_id,caa_id,rid_make,rid_model,rid_source,track_type
```

**Status Codes:**
- `200 OK` - Success (returns CSV)
- `500 Internal Server Error` - Database or export error

**Example:**
```bash
# Export last 24 hours to CSV
curl -o drones.csv "http://localhost:8090/api/export/csv?time_range=24h"

# Export specific kit, last 7 days
curl -o alpha_7d.csv "http://localhost:8090/api/export/csv?time_range=7d&kit_id=kit-alpha"

# Export DJI drones only
curl -o dji_drones.csv "http://localhost:8090/api/export/csv?rid_make=DJI"
```

---

## Pattern Detection Endpoints (Phase 2)

Advanced intelligence endpoints for tactical operations and threat detection.

### Repeated Drones

Find drones that have been detected multiple times (surveillance pattern detection).

**Endpoint:** `GET /api/patterns/repeated-drones`

**Use Case:** Identify drones repeatedly visiting an area (surveillance, stalking, reconnaissance)

**Parameters:**

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `time_window_hours` | integer | No | `24` | 1-168 | Time window for analysis (hours) |
| `min_appearances` | integer | No | `2` | ≥2 | Minimum number of appearances |

**Response:**
```json
{
  "repeated_drones": [
    {
      "drone_id": "DJI-ABCD1234",
      "first_seen": "2026-01-19T10:00:00Z",
      "last_seen": "2026-01-20T15:30:00Z",
      "appearance_count": 5,
      "locations": [
        {
          "lat": 37.7749,
          "lon": -122.4194,
          "kit_id": "kit-alpha",
          "timestamp": "2026-01-19T10:00:00Z"
        },
        {
          "lat": 37.7750,
          "lon": -122.4195,
          "kit_id": "kit-alpha",
          "timestamp": "2026-01-19T14:30:00Z"
        }
      ]
    }
  ],
  "count": 1,
  "time_window_hours": 24,
  "min_appearances": 2
}
```

**Status Codes:**
- `200 OK` - Success
- `422 Unprocessable Entity` - Invalid parameters
- `500 Internal Server Error` - Database error
- `503 Service Unavailable` - Database unavailable

**Example:**
```bash
# Last 24 hours, 2+ appearances
curl http://localhost:8090/api/patterns/repeated-drones

# Last 48 hours, 3+ appearances
curl "http://localhost:8090/api/patterns/repeated-drones?time_window_hours=48&min_appearances=3"

# Last week
curl "http://localhost:8090/api/patterns/repeated-drones?time_window_hours=168"
```

---

### Coordinated Activity

Detect groups of drones flying together (swarm detection, coordinated operations).

**Endpoint:** `GET /api/patterns/coordinated`

**Use Case:** Identify drone swarms, coordinated attacks, or synchronized operations

**Parameters:**

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `time_window_minutes` | integer | No | `60` | 1-1440 | Time window for grouping (minutes) |
| `distance_threshold_m` | integer | No | `500` | ≥10 | Maximum distance between drones (meters) |

**Response:**
```json
{
  "coordinated_groups": [
    {
      "group_id": 1,
      "drone_count": 4,
      "drones": [
        {
          "drone_id": "DJI-DRONE1",
          "lat": 37.7749,
          "lon": -122.4194,
          "timestamp": "2026-01-20T15:30:00Z",
          "kit_id": "kit-alpha",
          "rid_make": "DJI"
        },
        {
          "drone_id": "DJI-DRONE2",
          "lat": 37.7750,
          "lon": -122.4195,
          "timestamp": "2026-01-20T15:30:05Z",
          "kit_id": "kit-alpha",
          "rid_make": "DJI"
        }
      ],
      "correlation_score": "high"
    }
  ],
  "count": 1,
  "time_window_minutes": 60,
  "distance_threshold_m": 500
}
```

**Correlation Score:**
- `high` - 5+ drones in group
- `medium` - 3-4 drones in group
- `low` - 2 drones in group

**Algorithm:** DBSCAN-style clustering using time and spatial proximity

**Status Codes:**
- `200 OK` - Success
- `422 Unprocessable Entity` - Invalid parameters
- `500 Internal Server Error` - Database error
- `503 Service Unavailable` - Database unavailable

**Example:**
```bash
# Last hour, 500m grouping
curl http://localhost:8090/api/patterns/coordinated

# Last 30 minutes, tight grouping (200m)
curl "http://localhost:8090/api/patterns/coordinated?time_window_minutes=30&distance_threshold_m=200"

# Last 6 hours
curl "http://localhost:8090/api/patterns/coordinated?time_window_minutes=360"
```

---

### Pilot Reuse

Detect operators flying multiple different drones (operator tracking, persistent surveillance).

**Endpoint:** `GET /api/patterns/pilot-reuse`

**Use Case:** Track operators across drone changes, identify professional operators

**Parameters:**

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `time_window_hours` | integer | No | `24` | 1-168 | Time window for analysis (hours) |
| `proximity_threshold_m` | integer | No | `50` | ≥10 | Pilot location proximity (meters) |

**Response:**
```json
{
  "pilot_reuse_patterns": [
    {
      "pilot_identifier": "OP12345678",
      "correlation_method": "operator_id",
      "drones": [
        {
          "drone_id": "DJI-DRONE1",
          "rid_make": "DJI",
          "rid_model": "Mavic 3",
          "first_seen": "2026-01-20T10:00:00Z",
          "last_seen": "2026-01-20T12:00:00Z"
        },
        {
          "drone_id": "DJI-DRONE2",
          "rid_make": "DJI",
          "rid_model": "Mini 3 Pro",
          "first_seen": "2026-01-20T13:00:00Z",
          "last_seen": "2026-01-20T15:00:00Z"
        }
      ]
    }
  ],
  "count": 1,
  "time_window_hours": 24,
  "proximity_threshold_m": 50
}
```

**Correlation Methods:**
- `operator_id` - Matched by Remote ID operator field
- `proximity` - Matched by pilot location clustering

**Status Codes:**
- `200 OK` - Success
- `422 Unprocessable Entity` - Invalid parameters
- `500 Internal Server Error` - Database error
- `503 Service Unavailable` - Database unavailable

**Example:**
```bash
# Last 24 hours
curl http://localhost:8090/api/patterns/pilot-reuse

# Last 12 hours, 100m proximity
curl "http://localhost:8090/api/patterns/pilot-reuse?time_window_hours=12&proximity_threshold_m=100"
```

---

### Anomalies

Detect unusual or dangerous drone behavior (altitude, speed, or flight pattern anomalies).

**Endpoint:** `GET /api/patterns/anomalies`

**Use Case:** Identify dangerous drones, reckless pilots, or unusual behavior

**Parameters:**

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `time_window_hours` | integer | No | `1` | 1-24 | Time window for analysis (hours) |

**Response:**
```json
{
  "anomalies": [
    {
      "anomaly_type": "speed",
      "severity": "high",
      "drone_id": "DJI-FAST1234",
      "details": {
        "speed_mps": 45.5,
        "threshold": 40.0,
        "rid_make": "DJI",
        "rid_model": "FPV Drone"
      },
      "timestamp": "2026-01-20T15:30:00Z"
    },
    {
      "anomaly_type": "altitude",
      "severity": "critical",
      "drone_id": "DJI-HIGH5678",
      "details": {
        "altitude_m": 520.0,
        "threshold": 500.0,
        "rid_make": "DJI"
      },
      "timestamp": "2026-01-20T15:25:00Z"
    },
    {
      "anomaly_type": "rapid_altitude_change",
      "severity": "medium",
      "drone_id": "DJI-CLIMB9999",
      "details": {
        "altitude_change_m": 85.0,
        "time_window_s": 10,
        "threshold": 75.0
      },
      "timestamp": "2026-01-20T15:20:00Z"
    }
  ],
  "count": 3,
  "time_window_hours": 1
}
```

**Anomaly Types:**

1. **Speed Anomalies**
   - `critical`: > 50 m/s (~180 km/h)
   - `high`: > 40 m/s (~144 km/h)
   - `medium`: > 30 m/s (~108 km/h)

2. **Altitude Anomalies**
   - `critical`: > 500m (above legal limit in most jurisdictions)
   - `high`: > 450m
   - `medium`: > 400m (FAA limit)

3. **Rapid Altitude Change**
   - `critical`: > 100m in 10 seconds
   - `high`: > 75m in 10 seconds
   - `medium`: > 50m in 10 seconds

**Status Codes:**
- `200 OK` - Success
- `422 Unprocessable Entity` - Invalid parameters
- `500 Internal Server Error` - Database error
- `503 Service Unavailable` - Database unavailable

**Example:**
```bash
# Last hour
curl http://localhost:8090/api/patterns/anomalies

# Last 6 hours
curl "http://localhost:8090/api/patterns/anomalies?time_window_hours=6"

# Last 24 hours
curl "http://localhost:8090/api/patterns/anomalies?time_window_hours=24"
```

---

### Multi-Kit Detections

Find drones detected by multiple kits simultaneously (triangulation opportunities).

**Endpoint:** `GET /api/patterns/multi-kit`

**Use Case:** Identify triangulation opportunities, signal strength comparison, coverage analysis

**Parameters:**

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `time_window_minutes` | integer | No | `15` | 1-1440 | Time window for correlation (minutes) |

**Response:**
```json
{
  "multi_kit_detections": [
    {
      "drone_id": "DJI-TRIANGLE",
      "kits": [
        {
          "kit_id": "kit-alpha",
          "rssi": -65,
          "lat": 37.7749,
          "lon": -122.4194,
          "timestamp": "2026-01-20T15:30:00Z"
        },
        {
          "kit_id": "kit-bravo",
          "rssi": -72,
          "lat": 37.7760,
          "lon": -122.4200,
          "timestamp": "2026-01-20T15:30:05Z"
        },
        {
          "kit_id": "kit-charlie",
          "rssi": -68,
          "lat": 37.7755,
          "lon": -122.4185,
          "timestamp": "2026-01-20T15:30:03Z"
        }
      ],
      "triangulation_possible": true
    }
  ],
  "count": 1,
  "time_window_minutes": 15
}
```

**Triangulation Possible:** `true` if detected by 3+ kits (enables geometric position estimation)

**Use Cases:**
1. **Triangulation** - Calculate precise drone position from RSSI
2. **Signal Comparison** - Analyze relative signal strengths
3. **Coverage Analysis** - Understand kit detection overlap
4. **Quality Validation** - Verify detection accuracy across kits

**Status Codes:**
- `200 OK` - Success
- `422 Unprocessable Entity` - Invalid parameters
- `500 Internal Server Error` - Database error
- `503 Service Unavailable` - Database unavailable

**Example:**
```bash
# Last 15 minutes
curl http://localhost:8090/api/patterns/multi-kit

# Last 30 minutes
curl "http://localhost:8090/api/patterns/multi-kit?time_window_minutes=30"

# Last hour
curl "http://localhost:8090/api/patterns/multi-kit?time_window_minutes=60"
```

---

## Error Codes

All endpoints follow standard HTTP status codes.

| Code | Meaning | Common Causes |
|------|---------|---------------|
| `200 OK` | Success | Request completed successfully |
| `422 Unprocessable Entity` | Invalid parameters | Parameter out of range, wrong type |
| `500 Internal Server Error` | Server error | Database query error, internal exception |
| `503 Service Unavailable` | Service unavailable | Database connection failed, pool unavailable |

**Error Response Format:**
```json
{
  "detail": "Error description here"
}
```

---

## Data Models

### DroneTrack

```typescript
{
  time: string,              // ISO 8601 timestamp
  kit_id: string,
  drone_id: string,
  lat?: number,              // WGS84 latitude
  lon?: number,              // WGS84 longitude
  alt?: number,              // Altitude in meters (AGL)
  speed?: number,            // Ground speed in m/s
  heading?: number,          // Heading in degrees (0-360)
  pilot_lat?: number,        // Pilot/operator latitude
  pilot_lon?: number,        // Pilot/operator longitude
  home_lat?: number,         // Home point latitude
  home_lon?: number,         // Home point longitude
  mac?: string,              // MAC address (if available)
  rssi?: number,             // Signal strength in dBm
  freq?: number,             // Frequency in MHz
  ua_type?: string,          // UA type (multirotor, fixed-wing, etc.)
  operator_id?: string,      // Remote ID operator identifier
  caa_id?: string,           // CAA registration ID
  rid_make?: string,         // Manufacturer (DJI, Autel, etc.)
  rid_model?: string,        // Model (Mavic 3, etc.)
  rid_source?: string,       // RID source (BLE, WiFi, etc.)
  track_type?: string        // "drone" or "aircraft"
}
```

### SignalDetection

```typescript
{
  time: string,              // ISO 8601 timestamp
  kit_id: string,
  freq_mhz: number,          // Frequency in MHz
  power_dbm?: number,        // Signal power in dBm
  bandwidth_mhz?: number,    // Bandwidth in MHz
  lat?: number,              // Detection location latitude
  lon?: number,              // Detection location longitude
  alt?: number,              // Detection altitude in meters
  detection_type?: string    // analog_fpv, dji_fpv, etc.
}
```

### KitStatus

```typescript
{
  kit_id: string,
  name: string,
  location?: string,
  api_url: string,
  last_seen?: string,        // ISO 8601 timestamp
  status: string,            // online, stale, offline, unknown
  created_at: string         // ISO 8601 timestamp
}
```

---

## Integration Examples

### JavaScript (Fetch API)

```javascript
// Get drones from last hour
async function getDrones() {
  const response = await fetch('http://localhost:8090/api/drones?time_range=1h');
  const data = await response.json();
  return data.drones;
}

// Get repeated drones
async function getRepeatedDrones(hours = 24) {
  const response = await fetch(
    `http://localhost:8090/api/patterns/repeated-drones?time_window_hours=${hours}`
  );
  const data = await response.json();
  return data.repeated_drones;
}

// Display on map
async function updateMap() {
  const drones = await getDrones();
  drones.forEach(drone => {
    if (drone.lat && drone.lon) {
      addMarker(drone.lat, drone.lon, drone.drone_id);
    }
  });
}
```

### Python (Requests)

```python
import requests

BASE_URL = "http://localhost:8090"

# Get all kits
def get_kits():
    response = requests.get(f"{BASE_URL}/api/kits")
    response.raise_for_status()
    return response.json()["kits"]

# Get anomalies
def get_anomalies(hours=1):
    params = {"time_window_hours": hours}
    response = requests.get(f"{BASE_URL}/api/patterns/anomalies", params=params)
    response.raise_for_status()
    return response.json()["anomalies"]

# Export to CSV
def export_csv(filename="drones.csv", time_range="24h"):
    params = {"time_range": time_range}
    response = requests.get(f"{BASE_URL}/api/export/csv", params=params)
    response.raise_for_status()
    with open(filename, "wb") as f:
        f.write(response.content)
```

### cURL

```bash
# Get health status
curl http://localhost:8090/health

# Get all kits
curl http://localhost:8090/api/kits

# Get drones from last 24 hours (pretty print with jq)
curl http://localhost:8090/api/drones?time_range=24h | jq

# Get coordinated activity
curl "http://localhost:8090/api/patterns/coordinated?time_window_minutes=30" | jq

# Export CSV
curl -o drones.csv "http://localhost:8090/api/export/csv?time_range=7d"

# Get all pattern metrics
curl -s http://localhost:8090/api/patterns/repeated-drones | jq '.count'
curl -s http://localhost:8090/api/patterns/coordinated | jq '.count'
curl -s http://localhost:8090/api/patterns/pilot-reuse | jq '.count'
curl -s http://localhost:8090/api/patterns/anomalies | jq '.count'
curl -s http://localhost:8090/api/patterns/multi-kit | jq '.count'
```

### Grafana (JSON API Datasource)

```json
{
  "datasource": "WarDragon Analytics",
  "url": "http://wardragon-api:8090/api/drones",
  "params": {
    "time_range": "1h",
    "limit": 1000
  },
  "jsonPath": "$.drones[*]"
}
```

---

## Performance Considerations

### Response Times (Target)

| Endpoint | Time Window | Target Response Time |
|----------|-------------|----------------------|
| `/health` | N/A | < 50ms |
| `/api/kits` | N/A | < 100ms |
| `/api/drones` | 1 hour | < 200ms |
| `/api/drones` | 24 hours | < 500ms |
| `/api/signals` | 1 hour | < 200ms |
| `/api/patterns/repeated-drones` | 24 hours | < 300ms |
| `/api/patterns/coordinated` | 1 hour | < 400ms |
| `/api/patterns/pilot-reuse` | 24 hours | < 450ms |
| `/api/patterns/anomalies` | 1 hour | < 200ms |
| `/api/patterns/multi-kit` | 15 minutes | < 250ms |

### Optimization Tips

1. **Use smaller time windows** for real-time queries
2. **Limit results** to what you actually need
3. **Filter early** - use kit_id, rid_make, etc. to reduce data
4. **Cache results** when appropriate
5. **Use multi-kit endpoint** for triangulation (pre-aggregated)

### Database Indexes

All endpoints are optimized with TimescaleDB indexes on:
- `time` (hypertable partitioning)
- `kit_id`
- `drone_id`
- `rid_make`
- `track_type`
- Pattern-specific indexes (pilot coordinates, RSSI, etc.)

---

## Security Considerations

**WARNING:** The default deployment has **NO AUTHENTICATION**.

For production deployments:

1. **Add authentication** - Use API keys, OAuth2, or JWT tokens
2. **Use HTTPS** - Always encrypt API traffic in production
3. **Rate limiting** - Prevent abuse with rate limits
4. **Network isolation** - Restrict API access to trusted networks
5. **Input validation** - All parameters are validated, but review security settings

See [SECURITY.md](../SECURITY.md) for complete security hardening guide.

---

## Version History

### v1.0.0 (2026-01-20)
- Phase 1: Core endpoints (health, kits, drones, signals, CSV export)
- Phase 2: Pattern detection endpoints (5 new endpoints)
- Database views and functions for pattern analysis
- Comprehensive error handling and validation

---

## Support

- **Documentation:** [README.md](../README.md), [operator-guide.md](operator-guide.md)
- **Architecture:** [architecture.md](architecture.md)
- **Testing:** [testing.md](testing.md)
- **Deployment:** [deployment.md](deployment.md)
- **Troubleshooting:** [troubleshooting.md](troubleshooting.md)

---

**Last Updated:** 2026-01-20
**API Version:** 1.0.0
**WarDragon Analytics** - Multi-kit drone surveillance platform
