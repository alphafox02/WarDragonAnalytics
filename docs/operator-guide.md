# WarDragon Analytics Operator Guide

**Tactical Dashboards and Threat Hunting Workflows for Phase 2**

This guide covers operational use of WarDragon Analytics tactical dashboards, pattern detection capabilities, and intelligence workflows for identifying threats and anomalous drone activity.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Accessing Dashboards](#accessing-dashboards)
3. [Tactical Overview Dashboard](#tactical-overview-dashboard)
4. [Pattern Analysis Dashboard](#pattern-analysis-dashboard)
5. [Multi-Kit Correlation Dashboard](#multi-kit-correlation-dashboard)
6. [Anomaly Detection Dashboard](#anomaly-detection-dashboard)
7. [Web UI Tactical Interface](#web-ui-tactical-interface)
8. [Pattern Detection Workflows](#pattern-detection-workflows)
9. [Alert Interpretation](#alert-interpretation)
10. [Threat Hunting Quick Reference](#threat-hunting-quick-reference)

---

## Quick Start

### Access Points

- **Web UI**: http://localhost:8090 - Real-time map and tactical interface
- **Grafana**: http://localhost:3000 - Operational dashboards and analytics
  - Username: `admin`
  - Password: (set in `.env` file as `GRAFANA_PASSWORD`)

### First-Time Setup

1. **Generate Test Data** (recommended for training):
   ```bash
   python tests/generate_test_data.py --scenario all
   ```

2. **Access Grafana**:
   - Navigate to http://localhost:3000
   - Login with admin credentials
   - Dashboards are pre-provisioned in "WarDragon Analytics" folder

3. **Verify Data Flow**:
   - Check "Tactical Overview" dashboard
   - Confirm kits show as "online"
   - Verify drone detections appear

---

## Accessing Dashboards

### Dashboard Organization

All pre-built dashboards are located in Grafana under:
**Dashboards → Browse → WarDragon Analytics**

Available dashboards:
- Tactical Overview
- Pattern Analysis
- Multi-Kit Correlation
- Anomaly Detection

### Time Range Selection

Most dashboards default to "Last 6 hours" but can be adjusted:
- Click the time picker (top right)
- Select from presets: Last 5m, 15m, 1h, 6h, 24h, 7d
- Or set custom absolute time range

### Auto-Refresh

Enable auto-refresh for live operations:
- Click refresh dropdown (top right)
- Select interval: 5s, 10s, 30s, 1m, 5m
- Dashboard will auto-update without manual refresh

---

## Tactical Overview Dashboard

**Purpose**: Real-time operational awareness and kit health monitoring

### Key Panels

#### 1. Active Drones (Last 5 Minutes)
- **What it shows**: Count of unique drones detected in last 5 minutes
- **Normal range**: 0-10 drones (depends on operational area)
- **Alert threshold**: Sudden spike (10+ drones) may indicate swarm activity
- **Action**: If count spikes, switch to Pattern Analysis dashboard to check for coordination

#### 2. Kit Status Grid
- **What it shows**: Online/offline status of all kits
- **Status indicators**:
  - Green: Online (last seen < 2 minutes ago)
  - Yellow: Stale (last seen 2-10 minutes ago)
  - Red: Offline (last seen > 10 minutes ago)
- **Action**: Investigate red/yellow kits for connectivity issues

#### 3. Active Alerts/Anomalies
- **What it shows**: Count of detected patterns and anomalies
- **Alert types**:
  - Repeated drones (surveillance pattern)
  - Coordinated activity (swarms)
  - Speed/altitude anomalies
  - Multi-kit detections
- **Action**: Click panel to drill down to specific alerts

#### 4. Drone Count Timeline (Last Hour)
- **What it shows**: Number of unique drones per 5-minute bucket
- **Pattern recognition**:
  - Flat line: Normal baseline activity
  - Gradual increase: Normal operational tempo
  - Sudden spike: Potential swarm or coordinated event
- **Action**: Hover over spikes to see exact count and time

#### 5. Top Remote ID Manufacturers
- **What it shows**: Most detected drone makes (DJI, Autel, Skydio, etc.)
- **Intelligence value**:
  - Identify common platforms in area
  - Detect unusual manufacturers (may indicate sophisticated operator)
- **Action**: Note any non-consumer brands (Autel EVO, Skydio X2) - may indicate professional/government use

### Tactical Workflow

**Scenario: Starting Your Shift**

1. Check Kit Status Grid - all kits online?
2. Review Active Drones count - baseline activity level
3. Check Active Alerts - any outstanding patterns?
4. Review Drone Count Timeline - any unusual spikes in last hour?
5. Note Top Manufacturers - know what's normal in your area

---

## Pattern Analysis Dashboard

**Purpose**: Detect surveillance patterns, operator reuse, and coordinated activity

### Key Panels

#### 1. Repeated Drone IDs
- **What it shows**: Drones appearing multiple times over time window
- **Columns**:
  - `drone_id`: Unique drone identifier
  - `appearances`: Number of separate flight sessions
  - `first_seen`: First detection timestamp
  - `last_seen`: Most recent detection timestamp
  - `time_span`: Duration between first and last appearance
- **Threat indicator**: 3+ appearances over 24 hours suggests surveillance or persistent monitoring
- **Action**: Click drone ID to see all locations on map

#### 2. Operator Reuse Detection
- **What it shows**: Same `operator_id` used across different drones, OR pilots in close proximity (<50m) with different drones
- **Columns**:
  - `operator_id` or `pilot_location`: Shared operator or pilot cluster
  - `drone_count`: Number of different drones
  - `drones`: List of drone IDs associated with operator
  - `correlation_method`: "operator_id_match" or "pilot_proximity"
- **Threat indicator**: Professional operators may use multiple drones for extended operations
- **Action**: Investigate pilot locations - are they co-located or distributed?

#### 3. Coordinated Activity (Swarms)
- **What it shows**: Groups of drones appearing together in time and space
- **Columns**:
  - `group_id`: Unique identifier for swarm group
  - `drone_count`: Number of drones in group
  - `center_lat/lon`: Geographic center of group
  - `time_window`: Time span of coordinated activity
  - `avg_altitude`: Average altitude of group
- **Threat indicator**: 4+ drones within 500m appearing within 5 minutes
- **Action**: High-priority alert - potential swarm attack or coordinated surveillance

#### 4. Frequency Reuse Patterns
- **What it shows**: FPV frequencies used repeatedly (may indicate favorite channels)
- **Intelligence value**: Helps predict which frequencies to monitor
- **Action**: Configure SDR to prioritize frequently-used channels

### Tactical Workflow

**Scenario: Detecting Surveillance Pattern**

1. **Check Repeated Drone IDs panel**:
   - Look for drones with 3+ appearances
   - Note time span (surveillance often spans hours/days)
   - Click drone ID to view flight paths

2. **Correlate with Operator Reuse**:
   - Does repeated drone share operator ID with other drones?
   - Are pilot locations clustered (same launch point)?

3. **Cross-reference with Coordinated Activity**:
   - Is repeated drone part of larger swarm?
   - Are other drones from same operator appearing together?

4. **Document in RID Watchlist**:
   - Add drone ID to watchlist in Web UI
   - Configure alerts for future detections

**Scenario: Identifying Swarm Activity**

1. **Check Coordinated Activity panel**:
   - Look for groups with 4+ drones
   - Note geographic center and time window

2. **Assess Threat Level**:
   - High altitude (>100m) + high speed = reconnaissance
   - Low altitude (<50m) + slow speed = payload delivery
   - Tight formation = trained operators

3. **Alert Team**:
   - Use tactical comms to notify response team
   - Provide group_id, location, and drone count

4. **Monitor for Escalation**:
   - Track if more drones join swarm
   - Watch for changes in altitude/speed patterns

---

## Multi-Kit Correlation Dashboard

**Purpose**: Leverage multiple kits for triangulation and tracking handoffs

### Key Panels

#### 1. Multi-Kit Detections Table
- **What it shows**: Drones simultaneously detected by 2+ kits
- **Columns**:
  - `drone_id`: Unique drone identifier
  - `kit_count`: Number of kits detecting drone
  - `kits`: List of detecting kits
  - `rssi_values`: Signal strength from each kit (dBm)
  - `time_window`: Duration of multi-kit visibility
- **Triangulation opportunity**: Use RSSI differences to estimate drone location
- **Action**: Higher kit count = better triangulation accuracy

#### 2. Coverage Overlap Heatmap
- **What it shows**: Geographic areas covered by multiple kits
- **Color coding**:
  - Dark blue: Single kit coverage
  - Green: 2-kit overlap
  - Yellow: 3-kit overlap
  - Red: 4+ kit overlap (best triangulation)
- **Intelligence value**: Identify coverage gaps and optimal sensor placement
- **Action**: Position additional kits to eliminate gaps

#### 3. Kit-to-Kit Handoff Tracking
- **What it shows**: Drones transitioning between kit coverage areas
- **Columns**:
  - `drone_id`: Unique drone identifier
  - `handoff_sequence`: Order of kits detecting drone (e.g., kit-001 → kit-002 → kit-003)
  - `flight_path`: Estimated flight direction
  - `velocity`: Speed during handoff
- **Intelligence value**: Track drone movement across large areas
- **Action**: Predict next coverage area based on flight path

#### 4. Detection Density Map
- **What it shows**: Hotspots of drone activity across all kits
- **Interpretation**:
  - High density = frequent activity area (launch point, target, loiter area)
  - Low density = transit corridor
- **Action**: Focus collection assets on high-density areas

### Tactical Workflow

**Scenario: Triangulating Drone Location**

1. **Identify Multi-Kit Detection**:
   - Look for drone detected by 3+ kits
   - Note RSSI values from each kit

2. **Calculate Approximate Distance**:
   - Higher RSSI (less negative) = closer to kit
   - Example: Kit-001 (-50 dBm), Kit-002 (-70 dBm), Kit-003 (-85 dBm)
   - Drone is closest to Kit-001

3. **Plot on Map**:
   - Use Web UI to visualize drone position
   - Compare with kit locations
   - Estimate distance based on RSSI gradient

4. **Refine with Handoff Data**:
   - If drone is moving, track handoff sequence
   - Predict future position based on velocity

**Scenario: Optimizing Kit Placement**

1. **Review Coverage Overlap Heatmap**:
   - Identify areas with single-kit coverage (blue zones)
   - Look for gaps between kits (white zones)

2. **Analyze Detection Density**:
   - Where is most drone activity?
   - Are high-density areas adequately covered?

3. **Plan Kit Relocation**:
   - Move kits to eliminate coverage gaps
   - Ensure high-density areas have 3+ kit coverage

---

## Anomaly Detection Dashboard

**Purpose**: Identify unusual flight behavior and potential threats

### Key Panels

#### 1. Altitude Anomalies
- **What it shows**: Drones with rapid altitude changes
- **Thresholds**:
  - Rapid climb: >50m in <30 seconds
  - Rapid descent: >50m in <30 seconds
  - Extreme altitude: >150m or <10m
- **Threat indicators**:
  - Rapid climb: Evading detection or gaining observation altitude
  - Rapid descent: Approaching target or malfunction
  - Very low altitude: Attempting to avoid radar/detection
- **Action**: Investigate rapidly descending drones immediately (potential crash or attack)

#### 2. Speed Anomalies
- **What it shows**: Drones with unusual speed patterns
- **Thresholds**:
  - Speed spike: 0 to >30m/s in <10 seconds
  - Hovering after high speed: >20m/s to <2m/s in <10 seconds
  - Sustained high speed: >25m/s for >60 seconds
- **Threat indicators**:
  - Speed spike: Racing drones or evasive maneuvers
  - Sudden stop: Payload delivery or target acquisition
  - Sustained high speed: Long-range reconnaissance
- **Action**: High-speed drones may indicate skilled operators or FPV racing platforms

#### 3. Erratic Flight Patterns
- **What it shows**: Drones with unusual heading changes
- **Thresholds**:
  - Heading variance: >180° change in <5 seconds
  - Random walk: >5 heading changes >90° in 30 seconds
  - Loitering: Circular pattern in <100m radius for >5 minutes
- **Threat indicators**:
  - Random walk: Operator confusion, GPS jamming, or autonomous failure
  - Tight loitering: Target surveillance or awaiting command
- **Action**: Loitering drones warrant immediate investigation

#### 4. Signal Strength Anomalies
- **What it shows**: Unusual RSSI patterns
- **Thresholds**:
  - Sudden signal loss: RSSI drop >30 dBm in <10 seconds
  - Intermittent signal: On/off pattern with <50% duty cycle
  - Unexpectedly strong signal: RSSI > -40 dBm
- **Threat indicators**:
  - Sudden loss: Drone crashed, landed, or jammed
  - Intermittent: Terrain masking or intentional signal management
  - Very strong: Drone very close to kit (<50m)
- **Action**: Very strong signals may indicate perimeter breach

### Tactical Workflow

**Scenario: Rapid Altitude Drop Alert**

1. **Review Altitude Anomalies panel**:
   - Identify drone with rapid descent (>50m in <30s)
   - Note current altitude and descent rate

2. **Assess Intent**:
   - Is drone descending to ground level? (Possible landing/crash)
   - Is descent stopping at low altitude? (Possible low-level approach)

3. **Check Location**:
   - Use Web UI to view drone position on map
   - Is drone near critical infrastructure or populated area?

4. **Immediate Actions**:
   - Alert security team if near protected area
   - Prepare to deploy counter-UAS if threat confirmed
   - Document incident timeline

**Scenario: Loitering Drone Detection**

1. **Review Erratic Flight Patterns panel**:
   - Look for circular/loitering pattern
   - Note duration of loiter (>5 min = high priority)

2. **Analyze Location**:
   - What is drone observing?
   - Is it directly over critical asset or perimeter?

3. **Check for Additional Drones**:
   - Switch to Pattern Analysis dashboard
   - Look for coordinated activity (loiter may be scout for swarm)

4. **Response Options**:
   - Visual observation (if safe)
   - RF jamming (if authorized and legal)
   - Law enforcement notification
   - Document operator_id for future reference

---

## Web UI Tactical Interface

**URL**: http://localhost:8090

### Key Features

#### 1. Live Alert Panel (Top of Page)
- **Real-time alerts**: New drones, pattern matches, anomalies
- **Severity levels**:
  - INFO (blue): New drone detected
  - WARNING (yellow): Pattern detected (repeated, operator reuse)
  - CRITICAL (red): Anomaly or swarm detected
- **Actions**:
  - Dismiss: Remove from view
  - Acknowledge: Mark as reviewed
  - View Details: Jump to drone on map

#### 2. Quick Filters
- **"Show Unusual"**: Filter to only anomalous drones (speed/altitude anomalies)
- **"Show Repeated"**: Filter to drones with multiple appearances
- **"Show Coordinated"**: Filter to drones in swarm groups
- **RID Watchlist**: Show only drones on watchlist
- **Geographic Filter**: Draw polygon on map to filter by area

#### 3. Pattern Highlighting
- **Coordinated drones**: Same color/icon grouping
- **Repeated drones**: Numbered markers showing appearance sequence
- **Operator reuse**: Drones from same operator linked with lines
- **Multi-kit detections**: Drone markers show kit count badge

#### 4. Threat Summary Cards (Left Panel)
- **Active Threats**: Count of current high-priority drones
- **Repeated Contacts**: Count of drones with 3+ appearances
- **Multi-Kit Detections**: Count of triangulation opportunities
- **Anomalies Detected**: Count of unusual behaviors in last hour

### Tactical Workflow

**Scenario: Managing Live Operations**

1. **Monitor Alert Panel**:
   - Watch for new drone alerts (blue)
   - Immediately investigate critical alerts (red)

2. **Use Quick Filters**:
   - Start with "Show Unusual" to prioritize threats
   - Switch to "Show Coordinated" if swarm detected

3. **Track Patterns on Map**:
   - Click drone marker to see details
   - Use flight path lines to assess direction
   - Note pilot location (if available from Remote ID)

4. **Update Watchlist**:
   - Right-click drone marker → "Add to Watchlist"
   - Configure alert preferences (SMS, email, webhook)

5. **Export Intelligence**:
   - Click "Export CSV" to save current drone data
   - Share with team or upload to intelligence database

---

## Pattern Detection Workflows

### Workflow 1: Daily Threat Hunting

**Time Required**: 15-20 minutes
**Frequency**: Once per shift

1. **Open Tactical Overview Dashboard**:
   - Check for any active alerts
   - Review drone count timeline for anomalies

2. **Switch to Pattern Analysis Dashboard**:
   - Check Repeated Drone IDs table
   - Note any new entries since last shift
   - Add persistent drones to watchlist

3. **Review Anomaly Detection Dashboard**:
   - Scan for altitude/speed anomalies
   - Investigate any loitering patterns

4. **Check Multi-Kit Correlation Dashboard**:
   - Identify triangulation opportunities
   - Note coverage gaps for kit repositioning

5. **Document Findings**:
   - Export significant detections to CSV
   - Update threat assessment log
   - Brief incoming shift operator

### Workflow 2: Investigating Suspected Surveillance

**Trigger**: Drone appears 3+ times in 24 hours
**Time Required**: 10-15 minutes

1. **Identify Repeated Drone**:
   - Pattern Analysis Dashboard → Repeated Drone IDs
   - Click drone ID to view all detections

2. **Analyze Flight Patterns**:
   - Web UI → Search for drone ID
   - Review all flight paths
   - Note if paths cover same area (perimeter sweep, grid pattern)

3. **Check Operator Information**:
   - Review operator_id field
   - Check for pilot location data
   - Cross-reference with Operator Reuse panel

4. **Assess Threat Level**:
   - Consistent flight paths = HIGH (surveillance)
   - Random patterns = MEDIUM (hobbyist)
   - Single-pass patterns = LOW (transit)

5. **Take Action**:
   - HIGH: Alert security team, add to watchlist with SMS alerts
   - MEDIUM: Add to watchlist with email alerts, monitor
   - LOW: Document and continue monitoring

### Workflow 3: Responding to Swarm Detection

**Trigger**: Coordinated Activity alert (4+ drones together)
**Time Required**: 5-10 minutes (immediate response)

1. **Confirm Swarm**:
   - Pattern Analysis Dashboard → Coordinated Activity
   - Verify drone count, location, and time window

2. **Assess Threat**:
   - Check altitude (high = recon, low = attack)
   - Check speed (fast = racing/training, slow = deliberate)
   - Check formation (tight = trained, loose = amateur)

3. **Alert Team**:
   - Use emergency notification system
   - Provide: group_id, location, drone count, altitude, heading

4. **Monitor in Real-Time**:
   - Web UI → Enable auto-refresh (5 seconds)
   - Use "Show Coordinated" filter
   - Track swarm movement and changes in count

5. **Deploy Response** (if authorized):
   - RF jamming (legal considerations apply)
   - Visual observation team
   - Law enforcement notification
   - Counter-UAS systems (if available and legal)

6. **Document Incident**:
   - Export all detections to CSV
   - Screenshot dashboard states
   - Write incident report with timestamps

---

## Alert Interpretation

### Alert Priority Levels

#### Critical (Immediate Response Required)
- Swarm detected (4+ drones coordinated)
- Drone loitering over critical infrastructure (>5 min)
- Rapid altitude drop near populated area
- Very low altitude approach (<10m)

#### High (Investigate Within 5 Minutes)
- Repeated drone (3+ appearances in 24h)
- Speed anomaly (>30m/s)
- Altitude anomaly (rapid climb/descent)
- Multi-kit detection near perimeter

#### Medium (Investigate Within 30 Minutes)
- Operator reuse (same operator, multiple drones)
- Intermittent signal pattern
- Unusual manufacturer (non-consumer brand)

#### Low (Monitor and Document)
- New drone detected (first appearance)
- Normal flight pattern
- Single-kit detection at distance

### Pattern Interpretation Guide

| Pattern | What It Means | Likely Intent | Response |
|---------|---------------|---------------|----------|
| **Repeated Drone (Same Location)** | Drone returns to same area multiple times | Surveillance, monitoring, hobbyist favorite spot | Add to watchlist, identify operator |
| **Repeated Drone (Different Locations)** | Drone covers multiple areas | Area reconnaissance, mapping | High priority - assess pattern |
| **Coordinated Swarm (Tight Formation)** | Drones moving together in sync | Trained operators, demonstration, attack | Immediate alert, deploy response |
| **Coordinated Swarm (Loose Formation)** | Drones in general proximity | Racing event, multiple hobbyists | Monitor, verify not a threat |
| **Operator Reuse (Same operator_id)** | Professional with multiple platforms | Commercial operator, government, or sophisticated threat actor | Investigate credentials, monitor closely |
| **Pilot Proximity (<50m)** | Multiple operators in same location | Training event, group flight, or coordinated operation | Assess context, monitor for patterns |
| **Multi-Kit Detection (Strong RSSI)** | Drone close to multiple kits | Drone in center of coverage area, good triangulation | Track with precision, priority target |
| **Speed Spike** | Sudden acceleration | FPV racer, evasive maneuver, malfunction | Assess altitude and direction |
| **Altitude Drop** | Rapid descent | Landing, crash, attack approach | Immediate investigation if near critical asset |
| **Loitering (Circular Pattern)** | Hovering/circling in small area | Target surveillance, awaiting command | High priority - identify target of interest |
| **Erratic Heading** | Random direction changes | GPS jamming, operator confusion, autonomous failure | Monitor for crash or further anomalies |

---

## Threat Hunting Quick Reference

### Quick Checks (30 Seconds)

**Grafana Tactical Overview Dashboard**:
- Active Drones count (any spike from baseline?)
- Kit Status Grid (all kits online?)
- Active Alerts count (any new patterns?)

### Detailed Investigation (5 Minutes)

**Grafana Pattern Analysis Dashboard**:
- Repeated Drone IDs (any 3+ appearances?)
- Operator Reuse (any shared operators across drones?)
- Coordinated Activity (any swarms detected?)

**Grafana Anomaly Detection Dashboard**:
- Altitude Anomalies (any rapid changes?)
- Speed Anomalies (any spikes or unusual patterns?)
- Erratic Flight Patterns (any loitering?)

### Common Threat Scenarios

**Scenario**: Single drone, multiple appearances, same flight path
- **Likely**: Surveillance or monitoring
- **Action**: Add to watchlist, identify operator, assess target

**Scenario**: 5+ drones appearing simultaneously, tight formation
- **Likely**: Swarm attack or coordinated operation
- **Action**: Immediate alert, deploy response, track movement

**Scenario**: Drone with rapid altitude drop near critical asset
- **Likely**: Attack approach or malfunction
- **Action**: Immediate security alert, visual confirmation

**Scenario**: Same operator_id across 4+ different drones
- **Likely**: Professional operator (commercial, government, or threat)
- **Action**: Investigate credentials, monitor all associated drones

**Scenario**: Drone loitering at low altitude over perimeter
- **Likely**: Reconnaissance for future breach
- **Action**: Document location, increase patrols, consider counter-UAS

### API Quick Reference

All APIs support `hours` parameter to set time window (default: 6 hours).

```bash
# Find repeated drones (surveillance)
curl http://localhost:8090/api/patterns/repeated-drones?hours=24

# Detect swarms
curl http://localhost:8090/api/patterns/coordinated?hours=6

# Find operator reuse
curl http://localhost:8090/api/patterns/pilot-reuse?hours=12

# Detect anomalies
curl http://localhost:8090/api/patterns/anomalies?hours=6

# Find multi-kit detections (triangulation)
curl http://localhost:8090/api/patterns/multi-kit?hours=6
```

### Dashboard Shortcuts

- **Grafana**: http://localhost:3000/d/tactical-overview
- **Web UI**: http://localhost:8090
- **API Docs**: http://localhost:8090/docs (Swagger UI)

### Common Grafana Queries

**Find all drones from specific kit**:
```sql
SELECT * FROM drones WHERE kit_id = 'kit-001' AND time > NOW() - INTERVAL '6 hours'
```

**Count unique drones per hour**:
```sql
SELECT time_bucket('1 hour', time) AS hour, COUNT(DISTINCT drone_id) AS unique_drones
FROM drones WHERE time > NOW() - INTERVAL '24 hours' GROUP BY hour ORDER BY hour DESC
```

**Find drones with high speed**:
```sql
SELECT DISTINCT drone_id, MAX(speed) as max_speed FROM drones
WHERE time > NOW() - INTERVAL '6 hours' GROUP BY drone_id HAVING MAX(speed) > 25
```

---

## Troubleshooting

### No Drones Showing in Dashboards

**Check**:
1. Kits are online (Kit Status Grid shows green)
2. Collector service is running (`docker-compose ps collector`)
3. Database has data (`docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "SELECT COUNT(*) FROM drones;"`)

**Solution**:
- Generate test data: `python tests/generate_test_data.py --scenario normal`
- Verify kits.yaml configuration is correct
- Check collector logs: `docker-compose logs collector`

### Pattern Detection Not Working

**Check**:
1. Sufficient data exists (patterns require multiple detections over time)
2. Time range is appropriate (try increasing `hours` parameter)
3. API is responding (`curl http://localhost:8090/health`)

**Solution**:
- Generate pattern test data: `python tests/generate_test_data.py --scenario all`
- Verify database views exist (check `init.sql`)
- Restart web service: `docker-compose restart web`

### Grafana Dashboards Not Loading

**Check**:
1. Grafana is running (`docker-compose ps grafana`)
2. TimescaleDB datasource is configured
3. Dashboards are provisioned (check `/grafana/provisioning/`)

**Solution**:
- Restart Grafana: `docker-compose restart grafana`
- Check Grafana logs: `docker-compose logs grafana`
- Verify datasource at http://localhost:3000/datasources

---

## Additional Resources

- **README.md**: Overview and setup instructions
- **PHASE2_PLAN.md**: Detailed Phase 2 feature specifications
- **testing.md**: Testing procedures and test data generator usage
- **tests/README.md**: Test suite documentation

For questions or issues, consult project documentation or open a GitHub issue.

---

**Remember**: WarDragon Analytics is a passive monitoring tool. Always comply with local laws and regulations regarding drone detection and counter-UAS operations. Consult legal counsel before deploying any active countermeasures.
