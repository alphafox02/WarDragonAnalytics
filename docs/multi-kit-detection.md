# Multi-Kit Detection Guide

## Overview

When a drone is detected by multiple WarDragon kits simultaneously or over a time period, the Analytics platform provides enhanced visualization and analysis capabilities. This enables:

- **Cross-validation**: Confirm drone presence with multiple independent sensors
- **Triangulation**: With 3+ kits, position accuracy improves significantly
- **Coverage analysis**: Understand which kits have overlapping detection areas
- **Signal comparison**: Compare RSSI from each kit to estimate proximity

---

## Visual Indicators

### Map Markers

Drones detected by multiple kits display a blue badge showing the kit count:

| Kits | Badge | Meaning |
|------|-------|---------|
| 1 | (none) | Standard single-kit detection |
| 2 | "2 kits" | Seen by 2 kits - cross-validated |
| 3+ | "3 kits" with triangulation symbol | Triangulation possible |

### Popup Details

When you click on a multi-kit drone, the popup shows:

1. **Kit list**: All kits that detected this drone
2. **Signal strength (RSSI)**: Per-kit signal strength with visual bar
3. **Strongest signal**: The kit with the best signal is highlighted
4. **Triangulation indicator**: Shows when 3+ kits enable position triangulation

Example popup content:
```
Detected by 3 kits:
  Test Kit Alpha: -65 dBm (strongest)
  Mobile Unit Bravo: -72 dBm
  Fixed Site Charlie: -78 dBm
Triangulation possible
```

### Table View

The drone table shows multi-kit detections with:
- Kit name with "+N" suffix (e.g., "Test Kit Alpha +2")
- Blue highlight on multi-kit rows
- Tooltip showing all kits when hovering

---

## Flight Path Visualization

For drones observed by multiple kits, the flight path is color-coded:

1. **Color segments**: Each kit's observations are shown in that kit's color
2. **Handoff markers**: White circles indicate where detection passed between kits
3. **Legend**: A floating legend shows which color corresponds to which kit
4. **Breadcrumb tooltips**: Hovering shows which kit observed that position

This visualization helps understand:
- Which kit has coverage in different areas
- Where detection gaps or overlaps exist
- How a drone's path crosses kit coverage zones

---

## Signal Strength Interpretation

RSSI (Received Signal Strength Indicator) helps estimate proximity:

| RSSI Range | Strength | Visual |
|------------|----------|--------|
| -40 to -55 dBm | Excellent | Green bars |
| -56 to -65 dBm | Good | Yellow-green bars |
| -66 to -75 dBm | Fair | Yellow bars |
| -76 to -85 dBm | Weak | Orange bars |
| -86+ dBm | Very weak | Red bars |

**Note**: The kit with the strongest (least negative) RSSI is typically closest to the drone.

---

## Kit Filtering Behavior

When filtering by specific kits:

- **All Kits selected**: Shows all drones, multi-kit badges visible
- **Specific kits selected**: Shows drones seen by ANY selected kit
- **Multi-kit drones**: Display all observing kits, not just selected ones

This allows you to:
1. Filter to a specific kit's coverage area
2. Still see multi-kit context for drones that kit detected
3. Understand cross-kit detection patterns

---

## Triangulation

When 3 or more kits detect the same drone:

1. **Visual indicator**: Purple triangulation symbol appears
2. **Accuracy**: Position confidence increases significantly
3. **Use case**: Critical for high-priority drone tracking

For effective triangulation:
- Kits should be geographically separated
- All kits should have clear line-of-sight to the detection area
- Time synchronization between kits improves accuracy

---

## RSSI Location Estimation

For drones observed by 2+ kits, you can estimate the drone's location using RSSI-based trilateration. This is particularly useful for **encrypted drones** (like DJI encrypted DroneID) where the drone broadcasts a unique identifier but no GPS position.

### How It Works

1. **Click on a drone** that shows a multi-kit badge (2+ kits)
2. **Click "Estimate Location"** button in the popup
3. The system:
   - Retrieves RSSI values from each observing kit
   - Gets kit GPS positions from system health data
   - **Converts RSSI to estimated distance** using log-distance path loss model
   - **Trilaterates** to find the position that best fits all distance estimates
   - Displays estimated location with confidence radius
   - If drone has reported GPS, calculates spoofing score by comparing positions

### The Algorithm

**RSSI to Distance Conversion:**

Uses the standard [log-distance path loss model](https://en.wikipedia.org/wiki/Log-distance_path_loss_model) from RF engineering (Rappaport, "Wireless Communications: Principles and Practice"):

```
distance = 10^((TxPower - RSSI) / (10 * n))
```

Where:
- `TxPower`: Transmitter power (default: 0 dBm)
- `RSSI`: Received signal strength (e.g., -65 dBm)
- `n`: Path loss exponent (default: 2.5 for outdoor line-of-sight)

| Environment | Path Loss Exponent (n) |
|-------------|------------------------|
| Free space | 2.0 |
| Outdoor (clear) | 2.0-2.5 |
| Suburban | 2.5-3.0 |
| Urban/obstructed | 3.0-4.0 |

**Trilateration:**

| Kits | Method | Description |
|------|--------|-------------|
| 1 kit | Single point | Returns kit position with distance as confidence radius |
| 2 kits | Weighted line | Position along line between kits, weighted by inverse distance |
| 3+ kits | Iterative trilateration | Gradient descent to find best-fit position |

With 3+ kits, the algorithm iteratively adjusts the estimated position to minimize the error between calculated distances (from the estimate to each kit) and expected distances (from RSSI).

### Visualization

- **Yellow dashed marker**: Estimated drone position
- **Yellow dashed circle**: Confidence radius (estimated accuracy)
- **Red dashed line**: Error line to actual position (for validation)
- **Info overlay**: Shows algorithm details, kit data, error metrics, and spoofing score

### Use Cases

1. **Algorithm validation**: Test estimation accuracy against drones with known GPS
2. **Encrypted drone location**: Future support for drones without GPS data (e.g., encrypted DJI drones that only have RSSI/frequency)
3. **Spoofing detection**: Detect when a drone is reporting false GPS coordinates

### Spoofing Detection

The estimation API includes automatic spoofing detection that compares the drone's reported GPS position against the RSSI-estimated position:

| Spoofing Score | Interpretation |
|----------------|----------------|
| 0.0 - 0.29 | Normal - position matches RSSI estimate |
| 0.30 - 0.49 | Warrants monitoring - some deviation |
| 0.50 - 0.69 | Suspicious - significant deviation |
| 0.70 - 1.0 | Likely spoofing - extreme deviation |

The response includes:
- `spoofing_score`: 0.0-1.0 indicating likelihood of GPS spoofing
- `spoofing_suspected`: True if score >= 0.5
- `spoofing_reason`: Explanation when spoofing is suspected

Example spoofing scenario:
```
Drone reports: 37.7749, -122.4194
RSSI estimate: 37.7820, -122.4300 (based on signal strengths)
Error: 1,250 meters (expected accuracy: 180m)
Spoofing score: 0.72 (likely spoofing)
Reason: "Position error (1251m) is 6.9x the expected accuracy (180m)"
```

### API Endpoint

```
GET /api/analysis/estimate-location/{drone_id}?timestamp=2026-01-20T12:34:56Z
```

See [API Reference](api-reference.md#rssi-location-estimation) for full documentation.

---

## API Reference

### Multi-Kit Detection Endpoint

```
GET /api/patterns/multi-kit?time_window_minutes=15
```

Returns:
```json
{
  "multi_kit_detections": [
    {
      "drone_id": "ABC123",
      "kits": [
        {"kit_id": "kit-001", "rssi": -65, "lat": 34.05, "lon": -118.24, "timestamp": "..."},
        {"kit_id": "kit-002", "rssi": -72, "lat": 34.06, "lon": -118.25, "timestamp": "..."}
      ],
      "triangulation_possible": true,
      "rid_make": "DJI",
      "rid_model": "Mini 3 Pro",
      "latest_detection": "2026-01-20T12:34:56Z"
    }
  ],
  "count": 5,
  "time_window_minutes": 15
}
```

### Track Endpoint with Kit Data

```
GET /api/drones/{drone_id}/track?time_range=1h
```

Each track point includes `kit_id` for multi-kit path visualization:
```json
{
  "track": [
    {"time": "...", "kit_id": "kit-001", "lat": 34.05, "lon": -118.24, "alt": 50},
    {"time": "...", "kit_id": "kit-002", "lat": 34.06, "lon": -118.25, "alt": 55}
  ]
}
```

---

## Best Practices

1. **Kit placement**: Position kits to maximize overlapping coverage for critical areas
2. **Naming conventions**: Use clear kit names to quickly identify observations
3. **Time synchronization**: Ensure all kits have accurate time (NTP recommended)
4. **Signal analysis**: Use RSSI comparison to estimate drone-to-kit distance
5. **Triangulation zones**: Plan kit placement to enable 3+ kit coverage where needed

---

## Troubleshooting

### Multi-kit badges not appearing

1. Check that drones have different `kit_id` values in the database
2. Verify the time window is sufficient (default: 15 minutes)
3. Ensure the multi-kit pattern endpoint is responding: `/api/patterns/multi-kit`

### Flight path shows single color

1. The drone may have only been observed by one kit
2. Check track data: `GET /api/drones/{id}/track` - verify `kit_id` varies
3. Extend the time range to capture more observations

### RSSI values missing

1. Some kits may not report signal strength
2. Check kit configuration and DragonSync settings
3. RSSI is optional - displays as "N/A" when unavailable
