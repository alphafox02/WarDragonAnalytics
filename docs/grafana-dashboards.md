# WarDragon Analytics - Grafana Dashboards Guide

Comprehensive guide to using the pre-built Grafana dashboards for tactical drone surveillance operations.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Dashboard Overview](#dashboard-overview)
- [Dashboard 1: Tactical Overview](#dashboard-1-tactical-overview)
- [Dashboard 2: Pattern Analysis](#dashboard-2-pattern-analysis)
- [Dashboard 3: Multi-Kit Correlation](#dashboard-3-multi-kit-correlation)
- [Dashboard 4: Anomaly Detection](#dashboard-4-anomaly-detection)
- [Common Features](#common-features)
- [Filters and Variables](#filters-and-variables)
- [Alerts and Notifications](#alerts-and-notifications)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Quick Start

### Accessing Grafana

**URL:** `http://localhost:3000` (or your server IP)

**Default Credentials:**
- Username: `admin`
- Password: Set in `.env` file as `GRAFANA_PASSWORD`

**First Login:**
1. Navigate to http://localhost:3000
2. Login with admin credentials
3. You'll see 4 pre-installed dashboards in the "WarDragon Analytics" folder

### Dashboard Access

1. Click **Dashboards** (menu icon) on left sidebar
2. Navigate to **WarDragon Analytics** folder
3. Select a dashboard:
   - **Tactical Overview** - Real-time operations dashboard
   - **Pattern Analysis** - Surveillance and behavior patterns
   - **Multi-Kit Correlation** - Multi-kit detection analysis
   - **Anomaly Detection** - Unusual behavior alerts

---

## Dashboard Overview

WarDragon Analytics includes 4 purpose-built Grafana dashboards for tactical drone surveillance.

### Dashboard Summary

| Dashboard | Purpose | Best For | Refresh Rate |
|-----------|---------|----------|--------------|
| **Tactical Overview** | Real-time situational awareness | Live operations, command centers | 5 seconds |
| **Pattern Analysis** | Surveillance pattern detection | Intelligence analysis, investigations | 30 seconds |
| **Multi-Kit Correlation** | Triangulation and coverage | Multi-kit deployments, signal analysis | 30 seconds |
| **Anomaly Detection** | Threat identification | Security operations, airspace monitoring | 30 seconds |

### Data Source

All dashboards use the **TimescaleDB** datasource, auto-provisioned during deployment.

**Connection Details:**
- Name: `TimescaleDB`
- Type: PostgreSQL
- Host: `timescaledb:5432`
- Database: `wardragon`
- User: `wardragon`

---

## Dashboard 1: Tactical Overview

**Purpose:** Real-time operational awareness for command and control.

**Use Case:** Monitor active drone activity, kit health, and immediate threats during live operations.

### Panels

#### 1. Active Drones (Last 5 Min)
**Type:** Stat panel

**What it shows:** Count of unique drones detected in the last 5 minutes

**Interpretation:**
- **0-5 drones:** Normal baseline
- **5-10 drones:** Elevated activity
- **10+ drones:** High activity or event

**Color Coding:**
- Green: 0-5 drones
- Yellow: 6-10 drones
- Red: 11+ drones

#### 2. Active Alerts
**Type:** Stat panel

**What it shows:** Count of anomalies in the last hour (altitude >400m, speed >30 m/s, night flights)

**Interpretation:**
- **0 alerts:** Normal operations
- **1-3 alerts:** Monitor situation
- **4+ alerts:** Investigate immediately

**Color Coding:**
- Green: 0 alerts
- Yellow: 1-3 alerts
- Red: 4+ alerts

#### 3. Kit Status Grid
**Type:** Table panel

**Columns:**
- Kit ID
- Name
- Location
- Status (online/stale/offline)
- Last Seen (seconds ago)
- Drones (5m) - Drone count in last 5 minutes

**Status Meanings:**
- **Online** (green): Last seen < 1 minute ago
- **Stale** (yellow): Last seen 1-5 minutes ago
- **Offline** (red): Last seen > 5 minutes ago

**Actions:**
- Check connectivity if offline
- Verify DragonSync API if stale
- Monitor deployment status

#### 4. Drone Count Timeline
**Type:** Time series graph

**What it shows:** Number of unique drones over time, grouped by kit (5-minute buckets)

**Interpretation:**
- Spikes indicate burst activity
- Flat lines indicate steady surveillance
- Gaps indicate no detections

**Use Cases:**
- Identify peak activity times
- Correlate events with timestamps
- Assess kit detection patterns

#### 5. Top RID Makes
**Type:** Bar chart

**What it shows:** Most detected drone manufacturers in current time range

**Interpretation:**
- **DJI dominance:** Consumer/prosumer drones
- **Autel presence:** Professional operators
- **Unknown/Other:** Possible custom builds or spoofed IDs

**Use Cases:**
- Threat profiling
- Operator sophistication assessment
- Equipment trends

### Operational Workflows

**Scenario 1: Live Event Monitoring**
1. Set time range to "Last 5 minutes"
2. Enable auto-refresh (5 seconds)
3. Monitor Active Drones stat
4. Watch Kit Status Grid for offline kits
5. Check Drone Count Timeline for activity spikes

**Scenario 2: Post-Event Analysis**
1. Set time range to event duration (custom range)
2. Review Drone Count Timeline for patterns
3. Check Top RID Makes for threat profile
4. Export data if needed (Grafana export feature)

---

## Dashboard 2: Pattern Analysis

**Purpose:** Detect surveillance patterns, operator reuse, and coordinated activity.

**Use Case:** Intelligence gathering, investigation support, threat hunting.

### Panels

#### 1. Repeated Drone IDs
**Type:** Table panel

**What it shows:** Drones detected multiple times in the time range

**Columns:**
- Drone ID
- Appearances (count of 5-minute buckets)
- First Seen
- Last Seen
- Duration (minutes)
- Kits (which kits detected it)
- Make

**Interpretation:**
- **2-3 appearances:** Possible return trip
- **4-10 appearances:** Surveillance pattern
- **10+ appearances:** Persistent surveillance or training

**Red Flags:**
- Same drone, different times of day
- Same drone over multiple days
- Multiple kits detecting same ID

**Actions:**
- Flag for watchlist
- Correlate with pilot reuse
- Export for investigation

#### 2. Operator Reuse Detection
**Type:** Table panel

**What it shows:** Operators controlling multiple different drones

**Columns:**
- Operator/Location (ID or coordinates)
- Detection Method (operator_id or proximity)
- Drones (count)
- Drone IDs (list)
- First Seen
- Last Seen

**Detection Methods:**
- **operator_id:** Exact match on Remote ID operator field
- **proximity:** Pilots within 50m with different drones

**Interpretation:**
- **2-3 drones:** Hobbyist with multiple aircraft
- **4-6 drones:** Professional operator or commercial use
- **7+ drones:** Fleet operator, training, or coordinated operation

**Red Flags:**
- Rapid drone swaps (< 1 hour between different drones)
- Same operator, different locations
- Professional-grade equipment (Matrice, Autel EVO)

#### 3. Coordinated Activity Detection
**Type:** Table panel

**What it shows:** Groups of drones flying together (within same 5-minute window)

**Columns:**
- Group ID
- Group Size (number of drones)
- Drone IDs
- Detected By (kits)
- Start Time
- End Time

**Interpretation:**
- **2 drones:** Possible coincidence or paired operation
- **3-4 drones:** Coordinated activity (photography, surveying)
- **5+ drones:** Swarm operation or training exercise

**Red Flags:**
- Military-style formations
- Synchronized timing
- Uniform equipment (all same make/model)

#### 4. Flight Pattern Map
**Type:** Geomap panel

**What it shows:** Drone tracks plotted on map with track type color coding

**Map Features:**
- Blue markers: Normal drones
- Red markers: Anomalies
- Lines: Flight paths (if available)
- Clusters: Coordinated activity

**Use Cases:**
- Visualize surveillance routes
- Identify perimeter monitoring
- Detect grid search patterns

#### 5. Frequency Reuse Patterns
**Type:** Table panel

**What it shows:** Most used FPV frequencies and signal types

**Columns:**
- Frequency (MHz)
- Type (analog_fpv, dji_fpv, etc.)
- Detections (count)
- Kits (how many kits detected)

**Interpretation:**
- **5800-5900 MHz:** Analog FPV video
- **5725-5850 MHz:** Racing drones, custom builds
- **2400 MHz:** WiFi, DJI OcuSync, RC control

**Red Flags:**
- Non-standard frequencies
- Military bands
- Encrypted signals

### Operational Workflows

**Scenario 1: Surveillance Investigation**
1. Set time range to 24 hours (or investigation period)
2. Check Repeated Drone IDs table
3. Export drone IDs with 3+ appearances
4. Cross-reference with Operator Reuse Detection
5. Plot on Flight Pattern Map
6. Build timeline of activity

**Scenario 2: Swarm Detection**
1. Monitor Coordinated Activity Detection
2. Filter for groups of 3+ drones
3. Check Flight Pattern Map for formation
4. Review Frequency Reuse for coordination channel
5. Alert security if military-style swarm detected

---

## Dashboard 3: Multi-Kit Correlation

**Purpose:** Triangulation analysis and multi-kit detection correlation.

**Use Case:** Precision tracking, signal strength analysis, coverage optimization.

### Panels

#### 1. Multi-Kit Detections (Triangulation Opportunities)
**Type:** Table panel

**What it shows:** Drones detected by 2+ kits simultaneously

**Columns:**
- Drone ID
- Kits (count)
- Kit IDs
- RSSI Comparison (kit:rssi pairs)
- RSSI Spread (dBm difference)
- Avg Lat/Lon (centroid)
- Time Window
- Make

**Interpretation:**
- **2 kits:** Basic correlation, rough location estimate
- **3 kits:** Triangulation possible, precise location
- **4+ kits:** High-precision tracking

**Triangulation Quality:**
- **RSSI Spread < 10 dBm:** Drone equidistant from kits
- **RSSI Spread 10-30 dBm:** Good triangulation geometry
- **RSSI Spread > 30 dBm:** Drone much closer to one kit

**Use Cases:**
- Calculate precise drone position from RSSI
- Verify Remote ID location accuracy
- Detect spoofed locations

#### 2. Kit Coverage Overlap Map
**Type:** Geomap panel

**What it shows:** Kit positions with detection counts

**Map Features:**
- Kit markers sized by detection count
- Coverage circles (approximate range)
- Overlap zones highlighted

**Interpretation:**
- Large overlaps: Good for triangulation
- Gaps: Coverage holes
- Asymmetric: Obstructions or antenna issues

**Use Cases:**
- Optimize kit placement
- Identify coverage gaps
- Plan additional kit deployments

#### 3. Kit Handoff Tracking
**Type:** Time series graph

**What it shows:** RSSI over time for drones detected by multiple kits

**Interpretation:**
- **Rising RSSI on Kit A, Falling on Kit B:** Drone moving toward Kit A
- **Crossover points:** Drone passing midpoint between kits
- **Sudden drops:** Line-of-sight obstruction

**Use Cases:**
- Track drone movement
- Identify flight corridors
- Detect pattern of life

#### 4. Detection Density Heatmap
**Type:** Heatmap panel

**What it shows:** Grid-based detection density (0.01° lat/lon squares)

**Interpretation:**
- **Hot spots:** High-traffic areas
- **Cold zones:** Low activity or coverage gaps
- **Corridors:** Flight paths

**Use Cases:**
- Identify surveillance targets (hot spots)
- Optimize sensor placement
- Plan countermeasures

### Operational Workflows

**Scenario 1: Precision Tracking**
1. Monitor Multi-Kit Detections table
2. Filter for triangulation_possible = true (3+ kits)
3. Note RSSI values from each kit
4. Calculate position using trilateration
5. Compare with Remote ID broadcast location
6. Flag discrepancies > 50m

**Scenario 2: Coverage Optimization**
1. Review Kit Coverage Overlap Map
2. Identify coverage gaps
3. Check Detection Density Heatmap for activity
4. Plan additional kit deployment to fill gaps
5. Test with temporary kit placement

---

## Dashboard 4: Anomaly Detection

**Purpose:** Identify dangerous, unusual, or illegal drone behavior.

**Use Case:** Airspace security, threat detection, regulatory compliance monitoring.

### Panels

#### 1. Altitude Changes with Thresholds
**Type:** Time series graph with thresholds

**What it shows:** Drone altitude over time with FAA/regulatory limits

**Threshold Lines:**
- 400m (red line): FAA recreational limit (USA)
- 120m (yellow line): Typical commercial limit
- 500m (critical line): Extreme altitude

**Interpretation:**
- **Below 120m:** Normal operations
- **120-400m:** Commercial or professional (requires authorization)
- **Above 400m:** Recreational limit violation
- **Above 500m:** Extreme violation or manned aircraft

**Actions:**
- Log violations
- Alert authorities if persistent
- Track operator for enforcement

#### 2. Speed Anomalies
**Type:** Time series graph with thresholds

**What it shows:** Drone ground speed over time

**Threshold Lines:**
- 30 m/s (yellow): Fast for consumer drones (~108 km/h)
- 40 m/s (orange): Very fast, likely racing drone (~144 km/h)
- 50 m/s (red): Extreme speed, possible aircraft (~180 km/h)

**Interpretation:**
- **0-15 m/s:** Normal consumer drone (Mavic, Mini)
- **15-30 m/s:** Fast drone (FPV, racing)
- **30-50 m/s:** Racing drone or professional FPV
- **> 50 m/s:** Possible manned aircraft or misidentified

**Red Flags:**
- Sudden acceleration
- Speeds inconsistent with drone type (Mavic at 40 m/s = spoofed ID)

#### 3. Out-of-Pattern Behavior Detection
**Type:** Table panel

**What it shows:** Comprehensive anomaly summary

**Columns:**
- Drone ID
- Make / Model
- Anomaly Count (total violations)
- Altitude Issues
- Speed Issues
- Timing Issues (night flights: 22:00-05:00)
- Max Alt (m)
- Max Speed (m/s)
- First Seen / Last Seen
- Kits

**Anomaly Categories:**

1. **Altitude Issues:**
   - "Excessive Altitude (>400m)"
   - "High Altitude (>120m)"

2. **Speed Issues:**
   - "Very High Speed (>30 m/s)"
   - "High Speed (>20 m/s)"

3. **Timing Issues:**
   - "Night Flight" (22:00-05:00 local time)

**Interpretation:**
- **1-2 anomalies:** Possible violation or operator error
- **3-5 anomalies:** Pattern of violations
- **6+ anomalies:** Professional operator or intentional violations

**Priority Actions:**
- Critical: Altitude >500m or Speed >50 m/s
- High: Multiple simultaneous violations
- Medium: Single violation, first offense

#### 4. Signal Strength Anomalies (RSSI)
**Type:** Time series graph

**What it shows:** RSSI over time for detected drones

**Interpretation:**
- **RSSI > -50 dBm:** Very close (< 100m)
- **RSSI -50 to -70 dBm:** Close (100-500m)
- **RSSI -70 to -90 dBm:** Medium range (500m-2km)
- **RSSI < -90 dBm:** Long range (> 2km) or weak signal

**Anomalies:**
- Sudden RSSI drops: Obstruction or antenna failure
- RSSI spikes: Drone very close to kit
- Fluctuating RSSI: Multipath interference

#### 5. Rapid Altitude Changes (Climb/Descent Rate)
**Type:** Time series graph

**What it shows:** Rate of altitude change (m/s)

**Interpretation:**
- **+5 to +10 m/s:** Normal climb
- **+10 to +20 m/s:** Fast climb (racing, aggressive)
- **> +20 m/s:** Extreme climb
- **-10 to -20 m/s:** Fast descent
- **< -20 m/s:** Emergency descent or crash

**Red Flags:**
- Sustained high climb rates (> 15 m/s for > 10 seconds)
- Rapid descent followed by stop (possible crash)
- Oscillating altitude (unstable flight)

### Operational Workflows

**Scenario 1: Airspace Violation Response**
1. Monitor Out-of-Pattern Behavior Detection
2. Filter for altitude >400m
3. Note Drone ID, Make, Timestamp
4. Check if persistent (multiple detections)
5. Log violation
6. Contact authorities if warranted

**Scenario 2: Threat Assessment**
1. Check all anomaly panels
2. Identify drones with multiple violations
3. Cross-reference with Pattern Analysis (repeated?)
4. Assess intent (commercial, hobbyist, malicious)
5. Escalate if threat indicators present:
   - Night operations
   - Altitude violations
   - Speed inconsistent with type
   - Repeated surveillance pattern

---

## Common Features

### Time Range Selection

All dashboards support flexible time ranges:

**Quick Ranges:**
- Last 5 minutes (live ops)
- Last 15 minutes
- Last 30 minutes
- Last 1 hour
- Last 3 hours
- Last 6 hours
- Last 12 hours
- Last 24 hours
- Last 7 days

**Custom Range:**
- Click time range selector (top right)
- Choose "Absolute time range"
- Select start and end times

**Best Practices:**
- **Live ops:** 5-15 minutes with 5-second refresh
- **Shift analysis:** 6-12 hours
- **Investigation:** Custom range for incident window
- **Trend analysis:** 7 days

### Auto-Refresh

Enable automatic dashboard refresh for live monitoring:

1. Click refresh icon (top right)
2. Select interval:
   - 5s (live ops, high activity)
   - 10s (live ops, moderate activity)
   - 30s (monitoring)
   - 1m (background monitoring)
   - 5m (low-priority monitoring)

**Recommendations:**
- **Tactical Overview:** 5-10 seconds
- **Pattern Analysis:** 30 seconds to 1 minute
- **Multi-Kit Correlation:** 30 seconds
- **Anomaly Detection:** 30 seconds

### Exporting Data

Export data from any panel:

1. Click panel title
2. Select "Inspect" → "Data"
3. Click "Download CSV" or "Download Excel"

**Use Cases:**
- Offline analysis
- Evidence collection
- Report generation
- Backup/archival

### Sharing Dashboards

Share dashboard snapshots or links:

1. Click share icon (top right)
2. Options:
   - **Link:** Share URL with current time range and filters
   - **Snapshot:** Create public snapshot (careful with sensitive data!)
   - **Export JSON:** Download dashboard definition

---

## Filters and Variables

### Kit Filter

All dashboards include a `$kit_filter` variable to filter by kit.

**Location:** Top of dashboard

**Options:**
- "All" - Show data from all kits (default)
- Individual kit IDs (kit-alpha, kit-bravo, etc.)

**Use Cases:**
- Focus on single kit for troubleshooting
- Compare specific kit performance
- Isolate coverage area

**How to Use:**
1. Click `kit_filter` dropdown (top of dashboard)
2. Select kit or "All"
3. Dashboard updates automatically

### Time Range Variable

Some dashboards support custom time variables for panel-specific ranges.

**Use Cases:**
- Compare different time windows on same dashboard
- Zoom into specific incident while keeping overview

---

## Alerts and Notifications

### Configuring Grafana Alerts

Set up alerts for critical conditions:

1. Navigate to **Alerting** → **Alert rules**
2. Click **New alert rule**
3. Configure:
   - **Query:** Select metric (e.g., drone count > 10)
   - **Condition:** Define threshold
   - **Evaluation:** How often to check
   - **Notification:** Email, webhook, Slack, etc.

### Recommended Alerts

**1. Kit Offline Alert**
- **Condition:** Kit status = "offline" for > 5 minutes
- **Action:** Notify operations team
- **Priority:** High

**2. Altitude Violation Alert**
- **Condition:** Drone altitude > 400m
- **Action:** Log violation, notify security
- **Priority:** Medium

**3. Swarm Detection Alert**
- **Condition:** Coordinated group size ≥ 5 drones
- **Action:** Immediate notification
- **Priority:** Critical

**4. Repeated Surveillance Alert**
- **Condition:** Same drone detected 5+ times in 24 hours
- **Action:** Add to watchlist, notify intelligence
- **Priority:** Medium

---

## Troubleshooting

### Dashboard Not Loading

**Symptoms:** Blank dashboard, "No data" message

**Causes & Solutions:**

1. **Database not connected:**
   - Check: `docker ps` - is `wardragon-timescaledb` running?
   - Fix: `docker restart wardragon-timescaledb`

2. **No data in time range:**
   - Check: Expand time range to 24 hours or 7 days
   - Verify: DragonSync kits are sending data

3. **Datasource misconfigured:**
   - Check: Grafana → Configuration → Data Sources → TimescaleDB
   - Verify: Host = `timescaledb`, Port = `5432`, Database = `wardragon`

### Panels Show Errors

**Symptoms:** Red error boxes, "Query error" messages

**Common Errors:**

1. **"relation does not exist"**
   - Cause: Database views not created
   - Fix: Apply `timescaledb/02-pattern-views.sql` (see [deployment.md](deployment.md))

2. **"column does not exist"**
   - Cause: Schema mismatch
   - Fix: Verify database schema with `\d drones` in psql

3. **"syntax error"**
   - Cause: SQL query issue
   - Fix: Check Grafana query editor, review [dashboard-queries.md](dashboard-queries.md)

### Slow Dashboard Performance

**Symptoms:** Long load times, timeouts

**Solutions:**

1. **Reduce time range:**
   - Use smaller windows (1 hour instead of 7 days)

2. **Check database performance:**
   ```bash
   docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "SELECT * FROM pg_stat_activity;"
   ```

3. **Verify indexes:**
   ```bash
   docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "\di"
   ```

4. **Check Docker resources:**
   - Increase memory allocation for TimescaleDB container (see [docs/development/DOCKER_SETUP.md](docs/development/DOCKER_SETUP.md))

### Dashboards Disappeared

**Symptoms:** Dashboards missing from Grafana

**Causes & Solutions:**

1. **Provisioning issue:**
   - Check: `grafana/dashboards/dashboard-provider.yaml` exists
   - Check: Dashboard JSON files in `grafana/dashboards-json/`
   - Fix: Restart Grafana: `docker restart wardragon-grafana`

2. **Permissions issue:**
   - Check: File permissions on `grafana/dashboards-json/*.json`
   - Fix: `chmod 644 grafana/dashboards-json/*.json`

3. **Grafana reset:**
   - Cause: Grafana volume deleted
   - Fix: Dashboards will auto-provision on next startup

---

## Advanced Usage

### Creating Custom Dashboards

Build your own dashboards for specific use cases:

1. Navigate to **Dashboards** → **New Dashboard**
2. Add panel → Select visualization
3. Configure query using TimescaleDB datasource
4. Use queries from [dashboard-queries.md](dashboard-queries.md) as templates
5. Save dashboard

**Example: Custom Watchlist Dashboard**
```sql
SELECT time, drone_id, lat, lon, alt, speed, kit_id
FROM drones
WHERE time >= NOW() - INTERVAL '24 hours'
  AND drone_id IN ('DJI-WATCHLIST1', 'DJI-WATCHLIST2')
ORDER BY time DESC;
```

### Panel Customization

Modify existing panels:

1. Click panel title → Edit
2. Modify query, visualization, or settings
3. Save dashboard (requires permissions)

**Recommended Customizations:**
- Adjust threshold lines for local regulations
- Add specific watchlist drones to queries
- Change color schemes for team preferences
- Add annotations for notable events

### Embedding Dashboards

Embed dashboards in external applications:

1. Enable anonymous access (development only!):
   - Edit `grafana/grafana.ini`
   - Set `[auth.anonymous] enabled = true`

2. Get panel embed URL:
   - Click panel → Share → Embed
   - Copy iframe code

**Security Warning:** Do not enable anonymous access in production without proper network isolation!

### Templating and Variables

Create dynamic dashboards with variables:

**Example: Multi-Kit Comparison**
1. Dashboard Settings → Variables → Add variable
2. Name: `kit_a`, Type: Query
3. Query: `SELECT DISTINCT kit_id FROM kits`
4. Repeat for `kit_b`
5. Use in panel queries: `WHERE kit_id IN ('$kit_a', '$kit_b')`

---

## Best Practices

### Operational Use

1. **Use multiple monitors:**
   - Monitor 1: Tactical Overview (live)
   - Monitor 2: Pattern Analysis or Anomaly Detection
   - Monitor 3: Web UI map (http://localhost:8090)

2. **Set appropriate refresh rates:**
   - Live ops: 5-10 seconds
   - Background monitoring: 30-60 seconds
   - Investigation: Disable auto-refresh

3. **Document incidents:**
   - Export CSV for evidence
   - Take dashboard screenshots
   - Note exact time ranges

### Performance Optimization

1. **Limit time ranges** to what you need
2. **Disable unused panels** (edit dashboard, delete panel)
3. **Use kit filter** to reduce data volume
4. **Schedule maintenance** during low-activity periods

### Security

1. **Change default password** immediately
2. **Use HTTPS** in production (reverse proxy)
3. **Restrict network access** to trusted users
4. **Enable authentication** for all users
5. **Audit access logs** regularly

---

## Quick Reference

### Dashboard URLs

- Tactical Overview: `http://localhost:3000/d/tactical-overview`
- Pattern Analysis: `http://localhost:3000/d/pattern-analysis`
- Multi-Kit Correlation: `http://localhost:3000/d/multi-kit-correlation`
- Anomaly Detection: `http://localhost:3000/d/anomaly-detection`

### Key Shortcuts

- `Ctrl + S` (Windows/Linux) or `Cmd + S` (Mac): Save dashboard
- `d + k`: Toggle kiosk mode (fullscreen)
- `Ctrl + H` (Windows/Linux) or `Cmd + H` (Mac): Toggle row collapse
- `Esc`: Exit panel edit mode

### Metric Thresholds

| Metric | Normal | Elevated | Critical |
|--------|--------|----------|----------|
| Drone altitude | < 120m | 120-400m | > 400m |
| Drone speed | < 20 m/s | 20-30 m/s | > 30 m/s |
| Active drones | 0-5 | 6-10 | 11+ |
| Kit offline time | < 1 min | 1-5 min | > 5 min |
| Coordinated group | 1 drone | 2-4 drones | 5+ drones |

---

## Support

- **Deployment Issues:** See [deployment.md](deployment.md)
- **Query Reference:** See [dashboard-queries.md](dashboard-queries.md)
- **API Documentation:** See [api-reference.md](api-reference.md)
- **Troubleshooting:** See [troubleshooting.md](troubleshooting.md)
- **Operator Workflows:** See [operator-guide.md](operator-guide.md)

---

**Last Updated:** 2026-01-20
**Grafana Version:** Latest (auto-updated via Docker)
**WarDragon Analytics** - Multi-kit drone surveillance platform
