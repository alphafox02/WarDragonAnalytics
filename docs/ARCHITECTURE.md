# WarDragon Analytics Architecture

## Overview

Multi-kit drone surveillance aggregation and visualization platform.

**Purpose:** Centralized logging, analysis, and visualization of data from one or more WarDragon kits running DragonSync.

**Deployment Options:**
- Centralized server (aggregates multiple kits)
- Per-kit local instance (single kit, pointed at localhost)
- Hybrid (some kits report to central, some run local)

---

## Data Sources

### DragonSync API Endpoints

Each WarDragon kit exposes these endpoints (default port 8088):

```
GET /status          -> System health, GPS, CPU, memory, disk, temps
GET /drones          -> Drone/aircraft tracks (Remote ID + ADS-B)
GET /signals         -> FPV signal detections (suscli)
GET /config          -> Sanitized config (no secrets)
GET /update/check    -> Git update availability
```

**Data Collected:**
- **Drones:** Remote ID (DJI, BLE, Wi-Fi), pilot location, home point, FAA RID enrichment
- **Aircraft:** ADS-B tracks (ICAO, callsign, altitude, speed)
- **Signals:** FPV frequency detections (5.8GHz analog, DJI)
- **System:** Kit GPS, health metrics, uptime

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    WarDragon Kits (Field)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  Kit A   │  │  Kit B   │  │  Kit C   │  │  Kit D   │       │
│  │DragonSync│  │DragonSync│  │DragonSync│  │DragonSync│       │
│  │ :8088    │  │ :8088    │  │ :8088    │  │ :8088    │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼────────────┼────────────┼────────────┼────────────────┘
        │            │            │            │
        │ HTTP Poll every 5s     │            │
        └────────────┴────────────┴────────────┘
                     │
          ┌──────────▼──────────────────────────────────┐
          │    WarDragon Analytics (Docker)             │
          │                                              │
          │  ┌─────────────────────────────────────┐    │
          │  │  Collector Service (Python)         │    │
          │  │  - Polls /drones, /signals, /status │    │
          │  │  - Writes to TimescaleDB            │    │
          │  │  - Tracks kit health/availability   │    │
          │  └──────────────┬──────────────────────┘    │
          │                 │                            │
          │  ┌──────────────▼──────────────────────┐    │
          │  │  TimescaleDB (PostgreSQL)          │    │
          │  │  - Time-series optimized           │    │
          │  │  - Automatic partitioning          │    │
          │  │  - Data retention policies         │    │
          │  └──────────────┬──────────────────────┘    │
          │                 │                            │
          │  ┌──────────────┴──────────────────────┐    │
          │  │         Grafana :3000               │    │
          │  │  - Pre-built dashboards             │    │
          │  │  - Real-time maps                   │    │
          │  │  - Time-series graphs               │    │
          │  └─────────────────────────────────────┘    │
          │                                              │
          │  ┌─────────────────────────────────────┐    │
          │  │   Web UI :8080 (FastAPI/Flask)      │    │
          │  │  - Leaflet map (all kits combined)  │    │
          │  │  - Kit management                   │    │
          │  │  - CSV/KML export                   │    │
          │  │  - Alert configuration              │    │
          │  └─────────────────────────────────────┘    │
          └──────────────────────────────────────────────┘
```

---

## Database Schema (TimescaleDB)

### kits table
```sql
CREATE TABLE kits (
    kit_id TEXT PRIMARY KEY,
    name TEXT,
    location TEXT,
    api_url TEXT NOT NULL,
    last_seen TIMESTAMPTZ,
    status TEXT,  -- online, offline, error
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### drones table (hypertable)
```sql
CREATE TABLE drones (
    time TIMESTAMPTZ NOT NULL,
    kit_id TEXT NOT NULL,
    drone_id TEXT NOT NULL,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    alt DOUBLE PRECISION,
    speed DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    pilot_lat DOUBLE PRECISION,
    pilot_lon DOUBLE PRECISION,
    home_lat DOUBLE PRECISION,
    home_lon DOUBLE PRECISION,
    mac TEXT,
    rssi INTEGER,
    freq DOUBLE PRECISION,
    ua_type TEXT,
    operator_id TEXT,
    caa_id TEXT,
    rid_make TEXT,
    rid_model TEXT,
    rid_source TEXT,
    track_type TEXT,  -- drone, aircraft
    PRIMARY KEY (time, kit_id, drone_id)
);

SELECT create_hypertable('drones', 'time');
```

### signals table (hypertable)
```sql
CREATE TABLE signals (
    time TIMESTAMPTZ NOT NULL,
    kit_id TEXT NOT NULL,
    freq_mhz DOUBLE PRECISION NOT NULL,
    power_dbm DOUBLE PRECISION,
    bandwidth_mhz DOUBLE PRECISION,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    alt DOUBLE PRECISION,
    detection_type TEXT,  -- analog, dji
    PRIMARY KEY (time, kit_id, freq_mhz)
);

SELECT create_hypertable('signals', 'time');
```

### system_health table (hypertable)
```sql
CREATE TABLE system_health (
    time TIMESTAMPTZ NOT NULL,
    kit_id TEXT NOT NULL,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    alt DOUBLE PRECISION,
    cpu_percent DOUBLE PRECISION,
    memory_percent DOUBLE PRECISION,
    disk_percent DOUBLE PRECISION,
    uptime_hours DOUBLE PRECISION,
    temp_cpu DOUBLE PRECISION,
    temp_gpu DOUBLE PRECISION,
    PRIMARY KEY (time, kit_id)
);

SELECT create_hypertable('system_health', 'time');
```

### Retention Policies
```sql
-- Keep raw data for 30 days
SELECT add_retention_policy('drones', INTERVAL '30 days');
SELECT add_retention_policy('signals', INTERVAL '30 days');
SELECT add_retention_policy('system_health', INTERVAL '90 days');

-- Continuous aggregates (1-hour rollups, keep for 1 year)
CREATE MATERIALIZED VIEW drones_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', time) AS bucket,
       kit_id,
       COUNT(DISTINCT drone_id) AS unique_drones,
       AVG(alt) AS avg_altitude,
       AVG(speed) AS avg_speed
FROM drones
GROUP BY bucket, kit_id;

SELECT add_retention_policy('drones_hourly', INTERVAL '1 year');
```

---

## Components

### 1. Collector Service (app/collector.py)

**Responsibilities:**
- Poll DragonSync APIs from configured kits
- Normalize data format
- Write to TimescaleDB
- Track kit health/availability
- Retry logic for offline kits

**Pseudo-code:**
```python
async def poll_kit(kit: Kit):
    while True:
        try:
            # Fetch drones
            drones = await fetch_json(f"{kit.api_url}/drones")
            for drone in drones:
                await db.insert_drone(kit.id, drone)

            # Fetch signals
            signals = await fetch_json(f"{kit.api_url}/signals")
            for signal in signals:
                await db.insert_signal(kit.id, signal)

            # Fetch status
            status = await fetch_json(f"{kit.api_url}/status")
            await db.insert_health(kit.id, status)

            await kit.mark_online()
        except Exception as e:
            logger.error(f"Kit {kit.id} error: {e}")
            await kit.mark_offline()

        await asyncio.sleep(5)  # Poll every 5 seconds
```

### 2. Web UI (app/api.py + templates/)

**Framework:** FastAPI (Python) or Flask

**Features:**
- Leaflet map showing all drones from all kits
- Kit management (add/remove/configure)
- Filters (time range, kit, RID make/model)
- CSV/KML export
- Alert configuration (geofences, RID watchlist)

**Endpoints:**
```
GET  /                        -> Main map UI
GET  /api/kits                -> List configured kits
POST /api/kits                -> Add new kit
GET  /api/drones              -> Query drones (filters: time, kit, etc.)
GET  /api/signals             -> Query signals
GET  /api/export/csv          -> Export CSV
GET  /api/export/kml          -> Export KML for Google Earth
```

### 3. Grafana Dashboards

**Pre-built dashboards:**
1. **Operations Overview:** All kits, drone count, signal count, map
2. **Kit Health:** CPU, memory, disk, temps, GPS quality
3. **Drone Analysis:** RID make/model breakdown, altitude distribution, speed distribution
4. **Signal Analysis:** Frequency spectrum, power levels over time
5. **Historical Trends:** Daily/weekly drone counts, geographic heatmaps

---

## Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_DB: wardragon
      POSTGRES_USER: wardragon
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - ./timescaledb/init.sql:/docker-entrypoint-initdb.d/init.sql
      - timescale-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  collector:
    build: ./app
    environment:
      DATABASE_URL: postgresql://wardragon:${DB_PASSWORD}@timescaledb:5432/wardragon
      KITS_CONFIG: /config/kits.yaml
    volumes:
      - ./config:/config
    depends_on:
      - timescaledb
    restart: always

  web:
    build: ./app
    command: uvicorn api:app --host 0.0.0.0 --port 8080
    environment:
      DATABASE_URL: postgresql://wardragon:${DB_PASSWORD}@timescaledb:5432/wardragon
    ports:
      - "8080:8080"
    depends_on:
      - timescaledb
    restart: always

  grafana:
    image: grafana/grafana:latest
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
      GF_INSTALL_PLUGINS: grafana-worldmap-panel
    volumes:
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - grafana-data:/var/lib/grafana
    ports:
      - "3000:3000"
    depends_on:
      - timescaledb
    restart: always

volumes:
  timescale-data:
  grafana-data:
```

### Configuration (config/kits.yaml)

```yaml
kits:
  - id: kit-001
    name: "Mobile Unit Alpha"
    api_url: "http://192.168.1.100:8088"
    location: "Field Operations"
    enabled: true

  - id: kit-002
    name: "Mobile Unit Bravo"
    api_url: "http://192.168.1.101:8088"
    location: "Field Operations"
    enabled: true

  - id: kit-003
    name: "Fixed Site Charlie"
    api_url: "http://10.0.0.50:8088"
    location: "Headquarters"
    enabled: true

# For single-kit local deployment:
  - id: local-kit
    api_url: "http://127.0.0.1:8088"
    name: "Local WarDragon Kit"
    enabled: true
```

---

## Features Roadmap

### Phase 1: MVP (Core Functionality)
- [x] Architecture design
- [ ] TimescaleDB schema
- [ ] Basic collector (polls /drones, /status)
- [ ] Simple web UI (map + table)
- [ ] Docker Compose deployment
- [ ] Single-kit support

### Phase 2: Multi-Kit Aggregation
- [ ] Kit management UI
- [ ] Health monitoring
- [ ] Offline kit detection
- [ ] Basic Grafana dashboards
- [ ] CSV export

### Phase 3: Advanced Analytics
- [ ] Signal collection (/signals endpoint)
- [ ] Geofencing alerts
- [ ] RID watchlist
- [ ] KML export (Google Earth)
- [ ] Continuous aggregates (hourly/daily rollups)
- [ ] Data retention policies

### Phase 4: Production Features
- [ ] Authentication (user accounts)
- [ ] RBAC (role-based access control)
- [ ] API keys for kits
- [ ] Encrypted kit-to-analytics communication
- [ ] Alert webhooks (Slack, email, PagerDuty)
- [ ] Mobile-responsive UI

---

## API Compatibility

**DragonSync API Version:** Assumes DragonSync API as of 2026-01-19

**Consumed Endpoints:**
- `/status` - System health and GPS
- `/drones` - Drone/aircraft tracks
- `/signals` - FPV signal detections

**Data Format:** JSON responses from DragonSync API

**Polling Strategy:**
- Drones/signals: Every 5 seconds (configurable)
- Status: Every 30 seconds (configurable)
- Exponential backoff on errors

---

## Security Considerations

1. **Network Isolation:** Analytics should run on trusted network
2. **API Authentication:** Future: add API keys to DragonSync → Analytics communication
3. **Database Encryption:** TimescaleDB with encrypted volumes
4. **Web UI Auth:** Login required for web UI (Phase 4)
5. **Rate Limiting:** Respect DragonSync API rate limits (100 req/60s per IP)

---

## Performance Targets

- **Latency:** < 10s from drone detection to display in Analytics
- **Scale:** Support 10+ kits simultaneously
- **Data Retention:** 30 days raw, 1 year aggregates
- **Query Speed:** < 1s for time-range queries (1 hour of data)
- **Resource Usage:** < 2GB RAM, < 50GB disk for 30 days of 5-kit data

---

## Development Plan

1. **Now:** Architecture design (this document)
2. **Next:** Implement TimescaleDB schema + init scripts
3. **Then:** Build collector service (basic polling)
4. **Then:** Build web UI (Leaflet map + table)
5. **Then:** Create Grafana dashboards
6. **Finally:** Package as Docker Compose, test with real kit

**Estimated effort:** 2-3 weeks for MVP (single-kit, basic UI)
**Estimated effort:** +1 week for multi-kit support
**Estimated effort:** +1 week for advanced analytics features
