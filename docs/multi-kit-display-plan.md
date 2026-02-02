# Multi-Kit Drone Display - Implementation Plan

**Status: IMPLEMENTED** (January 2026)

## Problem Statement

When a drone is detected by multiple WarDragon kits simultaneously or over a time period, users need to understand:
1. **Which kits** saw the drone (not just a count)
2. **What data** each kit captured (RSSI, position, timing differences)
3. **How to filter** when viewing data from specific kits
4. **What it means** for localization/triangulation

Currently, the UI shows "Seen by 2 kits" but doesn't reveal which kits or their individual observations.

---

## Current State

### Data Available (API already provides this)
```json
{
  "drone_id": "ABC123",
  "kits": [
    {"kit_id": "kit-001", "rssi": -65, "lat": 34.05, "lon": -118.24, "timestamp": "..."},
    {"kit_id": "kit-002", "rssi": -72, "lat": 34.06, "lon": -118.25, "timestamp": "..."}
  ],
  "triangulation_possible": true,
  "rid_make": "DJI",
  "rid_model": "Mini 3 Pro"
}
```

### Current Issues
1. **Bug**: UI expects `.drones` but API returns `.multi_kit_detections` - data not loading
2. **Missing info**: Only shows count, not kit names
3. **No per-kit details**: RSSI from each kit is valuable for localization
4. **Filtering confusion**: Unclear what happens when filtering by specific kits

---

## User Experience Goals

### Primary Goals
1. **At a glance**: User sees drone was detected by multiple kits (current badge)
2. **On click**: User sees which kits and key per-kit data
3. **For filtering**: Clear behavior when specific kits are selected

### Secondary Goals
1. **Triangulation hint**: When 3+ kits see a drone, indicate triangulation is possible
2. **Signal strength comparison**: Help user understand relative proximity
3. **Timing analysis**: Show if kits saw the drone at the same time or different times

---

## Technical Implementation Plan

### Phase 1: Fix Data Loading (Bug Fix) - DONE
**File**: `app/static/map.js`
**Issue**: Line 1310 uses `.drones` but API returns `.multi_kit_detections`

```javascript
// Fixed:
patternData.multiKit = results[4]?.multi_kit_detections || [];
```

Also fixed access pattern: uses `multiKit.kits.length` instead of `multiKit.kit_count`.

---

### Phase 2: Enhanced Popup Display - DONE
**File**: `app/static/map.js` - `createPopup()` function

**Current**:
```
Seen by 2 kits
```

**Proposed**:
```
Seen by 2 kits: Test Kit Alpha, Mobile Unit Bravo
```

For 3+ kits with triangulation:
```
Seen by 3 kits (triangulation possible)
├─ Test Kit Alpha: -65 dBm
├─ Mobile Unit Bravo: -72 dBm
└─ Fixed Site Charlie: -58 dBm (strongest)
```

**Implementation**:
1. Pass `kits` array to popup (currently only passing `kit_count`)
2. Look up kit names using `getKitName()` helper
3. Format RSSI with signal strength indicator
4. Highlight strongest signal (closest kit)

---

### Phase 3: Kit Filtering Behavior - DONE

**Current Ambiguity**: When user selects "Kit A" and "Kit B", and a drone was seen by both:
- Does it show? (Yes - drone matches filter)
- Which kit's data is shown? (Currently: most recent)

**Proposed Behavior**:
1. **All Kits selected**: Show all drones, indicate multi-kit in badge
2. **Specific kits selected**: Show drones seen by ANY selected kit
3. **Multi-kit drones**: In popup, indicate which of the selected kits saw it

**Visual Indicator Options**:
- Option A: Show all observing kits, highlight selected ones
- Option B: Only show data from selected kits
- Option C: Primary kit data shown, expandable section for others

**Recommendation**: Option A - show all, highlight selected. This gives full context while making filter selection clear.

---

### Phase 4: Table View Enhancement - DONE
**File**: `app/static/map.js` - `updateTable()` function

**Current columns**: Time, Kit, Drone ID, Type, RID Make, RID Model, Lat, Lon, Alt, Speed

**Options for multi-kit display**:
1. **Multi-Kit badge in Kit column**: "Test Kit Alpha +1" with tooltip
2. **Expandable rows**: Click to see per-kit breakdown
3. **Separate Multi-Kit column**: Show count or checkmarks

**Recommendation**: Option 1 - concise, non-intrusive, tooltip provides details

---

### Phase 5: Flight Path Multi-Kit Visualization - DONE
When showing flight path for a drone seen by multiple kits:
- Color-code path segments by which kit observed them
- Show coverage overlap areas
- Indicate handoff points between kits

**Complexity**: High - defer to future enhancement

---

## UI/UX Design Decisions

### Badge Design
| Scenario | Badge Text | Color |
|----------|-----------|-------|
| 2 kits | "2 kits" | Blue |
| 3+ kits (triangulation) | "3 kits ◎" | Purple |
| Anomaly + multi-kit | Both badges shown | Red + Blue |

### Popup Layout for Multi-Kit
```
┌─────────────────────────────────────────┐
│ DRONE-12345                     [Badge] │
├─────────────────────────────────────────┤
│ Type: drone                             │
│ RID: DJI Mini 3 Pro                     │
│ Position: 34.0522, -118.2437            │
│ Altitude: 85.2m                         │
│ Speed: 12.5 m/s                         │
├─────────────────────────────────────────┤
│ ▼ Detected by 2 kits                    │
│   ├─ Test Kit Alpha      -65 dBm ████▓░│
│   └─ Mobile Unit Bravo   -72 dBm ███▓░░│
├─────────────────────────────────────────┤
│ [Show Flight Path] [Add to Watchlist]   │
└─────────────────────────────────────────┘
```

### Signal Strength Indicator
Visual bar or color coding:
- Excellent (-40 to -55 dBm): Green
- Good (-56 to -70 dBm): Yellow-Green
- Fair (-71 to -85 dBm): Yellow
- Weak (-86+ dBm): Red

---

## Documentation Updates Needed

### 1. User Guide Updates
**File**: `docs/user-guide.md` (create if doesn't exist)

Add section:
```markdown
## Multi-Kit Detection

When a drone is detected by multiple WarDragon kits, the system provides:

### Visual Indicators
- Blue badge on map marker showing kit count
- Purple badge with triangulation icon when 3+ kits see the drone

### Popup Details
Click on a multi-kit drone to see:
- List of kits that detected it
- Signal strength (RSSI) from each kit
- Relative timing of detections

### Filtering Behavior
When filtering by specific kits:
- Drones seen by ANY selected kit will appear
- Multi-kit drones show which selected kits observed them
- Non-selected kits are shown in gray in the popup
```

### 2. Architecture Doc Update
**File**: `docs/architecture.md`

Add to Data Flow section:
```markdown
### Multi-Kit Correlation
The `/api/patterns/multi-kit` endpoint correlates detections across kits:
- Groups drone observations by drone_id within a time window
- Returns per-kit observation details (RSSI, position, timestamp)
- Indicates when triangulation is possible (3+ kits)
```

### 3. API Documentation
**File**: `docs/api.md` (or inline in api.py docstrings)

Document the multi-kit response format:
```markdown
### GET /api/patterns/multi-kit

Returns drones detected by 2+ kits within the time window.

Response:
```json
{
  "multi_kit_detections": [
    {
      "drone_id": "ABC123",
      "kits": [
        {"kit_id": "...", "rssi": -65, "lat": ..., "lon": ..., "timestamp": "..."}
      ],
      "triangulation_possible": true,
      "rid_make": "DJI",
      "rid_model": "Mini 3 Pro",
      "latest_detection": "2024-01-20T12:34:56Z"
    }
  ],
  "count": 5,
  "time_window_minutes": 15
}
```
```

---

## Implementation Order

1. **Phase 1**: Fix data loading bug (5 min)
2. **Phase 2**: Enhanced popup with kit names (30 min)
3. **Phase 3**: Filtering behavior clarification (20 min)
4. **Phase 4**: Table view enhancement (20 min)
5. **Documentation**: User guide + architecture updates (30 min)

**Total estimated effort**: ~2 hours

---

## Testing Plan

### Unit Tests
- Verify `getKitName()` returns correct names
- Verify popup formatting with 0, 1, 2, 3+ kits

### Integration Tests
- Generate test data with multi-kit detections
- Verify badges appear correctly
- Verify popup shows all kits
- Verify filtering works as expected

### Manual Testing
1. Generate test data with overlapping kit coverage
2. Verify map shows multi-kit badges
3. Click drone, verify kit list in popup
4. Filter by one kit, verify behavior
5. Filter by two kits, verify multi-kit drones appear
6. Check table view for multi-kit indication

---

## Questions to Consider

1. **Time window**: How long should a drone be considered "multi-kit"? Current: 15 min window
2. **Stale data**: If Kit A saw drone 10 min ago and Kit B sees it now, is that multi-kit?
3. **Position discrepancy**: If kits report significantly different positions, flag as anomaly?
4. **Primary kit**: Should one kit be considered "primary" (strongest signal, most recent)?

---

## Summary

This plan addresses the user's question about multi-kit drone handling with:
- **Clear visual indicators** showing which kits saw a drone
- **Per-kit details** in the popup (RSSI, timing)
- **Logical filtering behavior** when specific kits are selected
- **Documentation** explaining the feature to users

The implementation is incremental - each phase can be tested independently before moving to the next.
