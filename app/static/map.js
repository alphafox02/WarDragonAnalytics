// WarDragon Analytics - Tactical Operations JavaScript

// Global variables
let map;
let markers = [];
let lines = [];
let currentData = [];
let patternData = {
    repeated: [],
    coordinated: [],
    pilotReuse: [],
    anomalies: [],
    multiKit: []
};
let refreshTimer;
let alertRefreshTimer;
let kits = [];
let watchlist = [];
let alerts = [];
let activeFilters = {
    showUnusual: false,
    showRepeated: false,
    showCoordinated: false,
    showMultikit: false,
    geoPolygon: null
};
let drawnItems;

// Flight path tracking
let flightPaths = {};  // Map of drone_id -> { polyline, markers }
let activeFlightPath = null;  // Currently displayed flight path drone_id

// Map view state - prevent auto-zoom after initial load
let initialLoadComplete = false;

// Pilot/Home location tracking
let pilotMarkers = [];  // Pilot location markers
let homeMarkers = [];   // Home location markers
let pilotLines = [];    // Lines from drone to pilot
let homeLines = [];     // Lines from drone to home
let showPilotLocations = true;  // Toggle for pilot locations
let showHomeLocations = true;   // Toggle for home locations

// RSSI Location estimation tracking
let estimationMarker = null;  // Estimated location marker
let estimationCircle = null;  // Confidence radius circle
let estimationErrorLine = null;  // Line from estimated to actual
let estimationOverlay = null;  // Info overlay element
let activeEstimation = null;  // Currently displayed estimation drone_id

// Kit color mapping
const KIT_COLORS = [
    '#ff4444', '#4444ff', '#44ff44', '#ffff44', '#ff44ff', '#44ffff',
    '#ff8844', '#8844ff', '#44ff88', '#ff4488', '#88ff44', '#4488ff'
];

// Get consistent color for a kit_id using hash
// This ensures the same kit always gets the same color, even before it's in the kits list
function getKitColor(kitId) {
    if (!kitId) return KIT_COLORS[0];

    // Simple hash function for string -> number
    let hash = 0;
    for (let i = 0; i < kitId.length; i++) {
        const char = kitId.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32-bit integer
    }

    // Use absolute value and mod to get color index
    const index = Math.abs(hash) % KIT_COLORS.length;
    return KIT_COLORS[index];
}

// Get kit name from kit_id, with fallback to kit_id if not found
function getKitName(kitId) {
    if (!kitId) return 'Unknown';
    const kit = kits.find(k => k.kit_id === kitId);
    return kit ? (kit.name || kitId) : kitId;
}

// Get signal strength bar visualization
function getSignalBar(rssi) {
    if (rssi == null || isNaN(rssi)) return '';
    // Map RSSI to 0-5 bars: -40 to -55 = 5 bars, -56 to -70 = 4, -71 to -80 = 3, -81 to -90 = 2, -91+ = 1
    let bars = 1;
    let color = '#ff4444';  // Red (weak)
    if (rssi >= -55) { bars = 5; color = '#44ff44'; }       // Green (excellent)
    else if (rssi >= -65) { bars = 4; color = '#88ff44'; }  // Yellow-green (good)
    else if (rssi >= -75) { bars = 3; color = '#ffff44'; }  // Yellow (fair)
    else if (rssi >= -85) { bars = 2; color = '#ffaa44'; }  // Orange (weak)
    // else 1 bar, red (very weak)

    const filled = '▓'.repeat(bars);
    const empty = '░'.repeat(5 - bars);
    return `<span style="color: ${color}; font-family: monospace;">${filled}</span><span style="color: #444;">${empty}</span>`;
}

// Pattern colors
const PATTERN_COLORS = {
    coordinated: '#ffaa00',
    pilotReuse: '#4444ff',
    normal: '#4444ff',
    unusual: '#ff4444'
};

// Initialize map
function initMap() {
    try {
        map = L.map('map').setView([34.05, -118.24], 12);

        // Use OpenStreetMap tiles with offline fallback
        // When offline, map will show gray but markers still work
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19,
            errorTileUrl: ''  // Don't show broken tile images when offline
        }).addTo(map);
    } catch (e) {
        console.error('Failed to initialize map:', e);
        // Create a basic map container message
        const mapDiv = document.getElementById('map');
        if (mapDiv) {
            mapDiv.innerHTML = '<div style="padding: 20px; color: #ff4444;">Map failed to load. Check console for errors.</div>';
        }
        return;
    }

    // Initialize drawn items layer for geographic filtering
    drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    // Add drawing controls
    const drawControl = new L.Control.Draw({
        position: 'topright',
        draw: {
            polygon: {
                allowIntersection: false,
                showArea: true,
                shapeOptions: {
                    color: '#00ff00'
                }
            },
            polyline: false,
            rectangle: true,
            circle: false,
            marker: false,
            circlemarker: false
        },
        edit: {
            featureGroup: drawnItems,
            remove: true
        }
    });
    map.addControl(drawControl);

    // Handle drawn shapes
    map.on(L.Draw.Event.CREATED, function (event) {
        const layer = event.layer;
        drawnItems.clearLayers();
        drawnItems.addLayer(layer);

        // Store polygon for filtering
        if (event.layerType === 'polygon' || event.layerType === 'rectangle') {
            activeFilters.geoPolygon = layer.toGeoJSON().geometry.coordinates[0];
            applyFilters();
        }
    });

    map.on(L.Draw.Event.DELETED, function () {
        activeFilters.geoPolygon = null;
        applyFilters();
    });
}

// Create custom marker icon
function createMarkerIcon(color, trackType, options = {}) {
    const { isWatchlist = false, isAnomaly = false, multiKitCount = 0, isCoordinated = false } = options;

    let iconHtml = trackType === 'aircraft'
        ? `<svg width="30" height="30" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" fill="${color}"/></svg>`
        : `<svg width="30" height="30" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="8" fill="${color}" stroke="#000" stroke-width="1"/></svg>`;

    // Add badges for special markers
    let badges = '';
    if (isWatchlist) {
        badges += '<div class="marker-badge watchlist">⭐</div>';
    }
    if (isAnomaly) {
        badges += '<div class="marker-badge anomaly">⚠</div>';
    }
    if (multiKitCount > 1) {
        badges += `<div class="marker-badge multi-kit">${multiKitCount}</div>`;
    }
    if (isCoordinated) {
        badges += '<div class="marker-badge coordinated">↔</div>';
    }

    const fullHtml = `
        <div class="marker-wrapper">
            ${iconHtml}
            ${badges}
        </div>
    `;

    return L.divIcon({
        html: fullHtml,
        className: 'marker-icon',
        iconSize: [30, 30],
        iconAnchor: [15, 15],
        popupAnchor: [0, -15]
    });
}

// Add CSS for marker badges and flight path UI
const style = document.createElement('style');
style.textContent = `
    .marker-wrapper { position: relative; }
    .marker-badge {
        position: absolute;
        top: -5px;
        right: -5px;
        background: #ff4444;
        color: white;
        border-radius: 50%;
        width: 16px;
        height: 16px;
        font-size: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        border: 2px solid #1a1a1a;
    }
    .marker-badge.watchlist { background: #00ff00; color: #1a1a1a; }
    .marker-badge.multi-kit { background: #4444ff; }
    .marker-badge.coordinated { background: #ffaa00; }

    /* Flight path button styles */
    .popup-actions {
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px solid #444;
    }
    .popup-btn {
        padding: 6px 12px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 500;
        transition: all 0.2s;
    }
    .flight-path-btn {
        background: #4488ff;
        color: white;
        width: 100%;
    }
    .flight-path-btn:hover {
        background: #3377ee;
    }
    .flight-path-btn.active {
        background: #ff4444;
    }
    .flight-path-btn.active:hover {
        background: #ee3333;
    }
    .flight-path-btn.loading {
        background: #666;
        cursor: wait;
    }

    /* Flight path breadcrumb markers */
    .breadcrumb-marker {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        border: 1px solid rgba(255,255,255,0.5);
    }

    /* Flight path polyline styling - make it pop! */
    .flight-path-line {
        filter: drop-shadow(0 0 3px rgba(0,0,0,0.5));
    }

    /* RSSI Location estimation button and overlay */
    .estimate-btn {
        background: #aa88ff;
        color: white;
        width: 100%;
        margin-top: 6px;
    }
    .estimate-btn:hover {
        background: #9977ee;
    }
    .estimate-btn.active {
        background: #ff8844;
    }
    .estimate-btn.active:hover {
        background: #ee7733;
    }
    .estimate-btn:disabled {
        background: #555;
        cursor: not-allowed;
        color: #888;
    }

    /* Estimation result overlay */
    .estimate-overlay {
        position: absolute;
        bottom: 10px;
        left: 10px;
        background: rgba(26, 26, 26, 0.95);
        border: 1px solid #aa88ff;
        border-radius: 8px;
        padding: 12px 16px;
        z-index: 1000;
        max-width: 320px;
        font-size: 12px;
    }
    .estimate-overlay h4 {
        margin: 0 0 8px 0;
        color: #aa88ff;
        font-size: 13px;
    }
    .estimate-overlay .close-btn {
        position: absolute;
        top: 8px;
        right: 10px;
        background: none;
        border: none;
        color: #888;
        cursor: pointer;
        font-size: 16px;
    }
    .estimate-overlay .close-btn:hover {
        color: #fff;
    }
    .estimate-overlay .stat-row {
        display: flex;
        justify-content: space-between;
        margin: 4px 0;
    }
    .estimate-overlay .stat-label {
        color: #888;
    }
    .estimate-overlay .stat-value {
        color: #fff;
        font-family: monospace;
    }
    .estimate-overlay .error-good { color: #44ff44; }
    .estimate-overlay .error-fair { color: #ffff44; }
    .estimate-overlay .error-poor { color: #ff8844; }
    .estimate-overlay .error-bad { color: #ff4444; }
    /* Spoofing detection classes */
    .estimate-overlay .spoof-normal { color: #44ff44; }
    .estimate-overlay .spoof-monitor { color: #ffff44; }
    .estimate-overlay .spoof-suspicious { color: #ff8844; }
    .estimate-overlay .spoof-likely { color: #ff4444; font-weight: bold; }
`;
document.head.appendChild(style);

// Format time - with defensive checks
function formatTime(isoString) {
    if (!isoString) return 'N/A';
    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return 'N/A';
        return date.toLocaleTimeString();
    } catch (e) {
        return 'N/A';
    }
}

// Format coordinate - with defensive checks
function formatCoord(value, decimals = 6) {
    if (value == null || value === undefined || isNaN(value)) return 'N/A';
    try {
        return Number(value).toFixed(decimals);
    } catch (e) {
        return 'N/A';
    }
}

// Create popup content - with defensive checks for all properties
function createPopup(track, options = {}) {
    // Defensive: ensure track is an object
    if (!track || typeof track !== 'object') {
        return '<div class="popup-title">No data available</div>';
    }

    const ridMake = track.rid_make || 'Unknown';
    const ridModel = track.rid_model || 'Unknown';
    const trackType = track.track_type || 'drone';
    const droneId = track.drone_id || 'Unknown';
    const kitId = track.kit_id || 'Unknown';
    const { isWatchlist = false, isAnomaly = false, anomalyTypes = [], multiKitCount = 0, multiKitData = [] } = options || {};

    let badges = '';
    if (isWatchlist) badges += '<span class="popup-badge watchlist">Watchlist</span> ';
    if (isAnomaly) badges += '<span class="popup-badge anomaly">Anomaly</span> ';
    // Show triangulation indicator for 3+ kits
    if (multiKitCount >= 3) {
        badges += `<span class="popup-badge multi-kit triangulation">◎ ${multiKitCount} kits</span> `;
    } else if (multiKitCount > 1) {
        badges += `<span class="popup-badge multi-kit">${multiKitCount} kits</span> `;
    }

    let anomalyInfo = '';
    if (anomalyTypes.length > 0) {
        anomalyInfo = `
            <div class="popup-row">
                <span class="popup-label">Anomalies:</span>
                <span class="popup-value">${anomalyTypes.join(', ')}</span>
            </div>
        `;
    }

    // Build multi-kit details section
    let multiKitInfo = '';
    if (multiKitCount > 1 && Array.isArray(multiKitData) && multiKitData.length > 0) {
        // Sort by RSSI (strongest first - less negative is stronger)
        const sortedKits = [...multiKitData].sort((a, b) => (b.rssi || -999) - (a.rssi || -999));
        const strongestRssi = sortedKits[0]?.rssi;

        const kitRows = sortedKits.map((kit, idx) => {
            const kitName = getKitName(kit.kit_id);
            const rssi = kit.rssi != null ? kit.rssi : 'N/A';
            const isStrongest = idx === 0 && rssi !== 'N/A';
            const signalBar = rssi !== 'N/A' ? getSignalBar(rssi) : '';
            const strongestTag = isStrongest ? ' <span style="color: #00ff00; font-size: 10px;">(strongest)</span>' : '';
            return `<div class="multi-kit-row" style="margin-left: 10px; font-size: 11px;">
                <span style="color: ${getKitColor(kit.kit_id)};">●</span> ${kitName}: ${rssi} dBm ${signalBar}${strongestTag}
            </div>`;
        }).join('');

        const triangulationNote = multiKitCount >= 3
            ? '<div style="font-size: 10px; color: #aa88ff; margin-top: 3px;">◎ Triangulation possible</div>'
            : '';

        multiKitInfo = `
            <div class="popup-section multi-kit-section" style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #444;">
                <div class="popup-label" style="margin-bottom: 4px;">Detected by ${multiKitCount} kits:</div>
                ${kitRows}
                ${triangulationNote}
            </div>
        `;
    }

    // Show MAC address if it's different from drone_id (indicates drone_id is a serial number)
    // or always show if available for additional identification
    let macInfo = '';
    if (track.mac) {
        macInfo = `
            <div class="popup-row">
                <span class="popup-label">MAC:</span>
                <span class="popup-value" style="font-family: monospace; font-size: 11px;">${track.mac}</span>
            </div>
        `;
    }

    // Show operator ID if available
    let operatorInfo = '';
    if (track.operator_id) {
        operatorInfo = `
            <div class="popup-row">
                <span class="popup-label">Operator ID:</span>
                <span class="popup-value">${track.operator_id}</span>
            </div>
        `;
    }

    // Show pilot location if available (must be non-zero - 0,0 means not provided)
    let pilotInfo = '';
    if (track.pilot_lat != null && track.pilot_lon != null && (track.pilot_lat !== 0 || track.pilot_lon !== 0)) {
        pilotInfo = `
            <div class="popup-row popup-pilot">
                <span class="popup-label">Pilot:</span>
                <span class="popup-value">${formatCoord(track.pilot_lat)}, ${formatCoord(track.pilot_lon)}</span>
            </div>
        `;
    }

    // Show home location if available (must be non-null AND non-zero - 0,0 means not provided)
    let homeInfo = '';
    if (track.home_lat != null && track.home_lon != null && (track.home_lat !== 0 || track.home_lon !== 0)) {
        homeInfo = `
            <div class="popup-row popup-home">
                <span class="popup-label">Home:</span>
                <span class="popup-value">${formatCoord(track.home_lat)}, ${formatCoord(track.home_lon)}</span>
            </div>
        `;
    }

    // Check if flight path is currently shown for this drone
    const hasFlightPath = activeFlightPath === droneId;
    const escapedDroneId = droneId.replace(/'/g, "\\'");  // Escape quotes for onclick
    const flightPathBtn = hasFlightPath
        ? `<button class="popup-btn flight-path-btn active" onclick="hideFlightPath('${escapedDroneId}')">Hide Flight Path</button>`
        : `<button class="popup-btn flight-path-btn" onclick="showFlightPath('${escapedDroneId}')">Show Flight Path</button>`;

    // Check if estimation is currently shown for this drone
    const hasEstimation = activeEstimation === droneId;
    const escapedTimestamp = track.time ? track.time.replace(/'/g, "\\'") : '';
    // Only show estimate button if there's multi-kit data (2+ kits)
    let estimateBtn = '';
    if (multiKitCount >= 2) {
        estimateBtn = hasEstimation
            ? `<button class="popup-btn estimate-btn active" onclick="clearEstimation()">Hide Estimation</button>`
            : `<button class="popup-btn estimate-btn" data-drone-id="${escapedDroneId}" data-timestamp="${escapedTimestamp}" onclick="estimateLocation('${escapedDroneId}', '${escapedTimestamp}')">Estimate Location</button>`;
    }

    // Safe formatting for numeric values
    const safeAlt = (track.alt != null && !isNaN(track.alt)) ? Number(track.alt).toFixed(1) : 'N/A';
    const safeSpeed = (track.speed != null && !isNaN(track.speed)) ? Number(track.speed).toFixed(1) : 'N/A';
    const safeRssi = track.rssi || 'N/A';

    // Look up kit name from kits array
    const kitName = getKitName(kitId);
    const kitDisplay = kitName !== kitId ? `${kitName}` : kitId;
    const kitTooltip = kitName !== kitId ? `ID: ${kitId}` : '';

    return `
        <div class="popup-title">${droneId} ${badges}</div>
        <div class="popup-row">
            <span class="popup-label">Kit:</span>
            <span class="popup-value" ${kitTooltip ? `title="${kitTooltip}"` : ''}>${kitDisplay}</span>
        </div>
        <div class="popup-row">
            <span class="popup-label">Type:</span>
            <span class="popup-value">${trackType}</span>
        </div>
        <div class="popup-row">
            <span class="popup-label">RID:</span>
            <span class="popup-value">${ridMake} ${ridModel}</span>
        </div>
        ${macInfo}
        ${operatorInfo}
        <div class="popup-row">
            <span class="popup-label">Position:</span>
            <span class="popup-value">${formatCoord(track.lat)}, ${formatCoord(track.lon)}</span>
        </div>
        ${pilotInfo}
        ${homeInfo}
        <div class="popup-row">
            <span class="popup-label">Altitude:</span>
            <span class="popup-value">${safeAlt} m</span>
        </div>
        <div class="popup-row">
            <span class="popup-label">Speed:</span>
            <span class="popup-value">${safeSpeed} m/s</span>
        </div>
        <div class="popup-row">
            <span class="popup-label">RSSI:</span>
            <span class="popup-value">${safeRssi} dBm</span>
        </div>
        <div class="popup-row">
            <span class="popup-label">Time:</span>
            <span class="popup-value">${formatTime(track.time)}</span>
        </div>
        ${anomalyInfo}
        ${multiKitInfo}
        <div class="popup-actions">
            ${flightPathBtn}
            ${estimateBtn}
        </div>
    `;
}

// Track if a popup is currently open to avoid closing it during refresh
let openPopupDroneId = null;

// Update map markers - with comprehensive defensive checks
function updateMap(data) {
    // Defensive: check if map is initialized
    if (!map) {
        console.warn('Map not initialized, skipping updateMap');
        return;
    }

    // Defensive: ensure data is an array
    if (!Array.isArray(data)) {
        console.warn('updateMap received non-array data:', typeof data);
        data = [];
    }

    // Check if a popup is open and remember which drone it belongs to
    let reopenPopupForDrone = null;
    markers.forEach(marker => {
        if (marker.isPopupOpen && marker.isPopupOpen()) {
            // Find the drone_id for this marker
            const pos = marker.getLatLng();
            const drone = currentData.find(d =>
                d && Math.abs(d.lat - pos.lat) < 0.00001 && Math.abs(d.lon - pos.lng) < 0.00001
            );
            if (drone) {
                reopenPopupForDrone = drone.drone_id;
            }
        }
    });

    // Clear existing markers and lines safely
    try {
        markers.forEach(marker => { try { map.removeLayer(marker); } catch(e) {} });
        lines.forEach(line => { try { map.removeLayer(line); } catch(e) {} });
        pilotMarkers.forEach(marker => { try { map.removeLayer(marker); } catch(e) {} });
        homeMarkers.forEach(marker => { try { map.removeLayer(marker); } catch(e) {} });
        pilotLines.forEach(line => { try { map.removeLayer(line); } catch(e) {} });
        homeLines.forEach(line => { try { map.removeLayer(line); } catch(e) {} });
    } catch (e) {
        console.warn('Error clearing map layers:', e);
    }
    markers = [];
    lines = [];
    pilotMarkers = [];
    homeMarkers = [];
    pilotLines = [];
    homeLines = [];

    // Draw pattern connections first (so they're behind markers)
    try {
        drawPatternConnections();
    } catch (e) {
        console.warn('Error drawing pattern connections:', e);
    }

    // Add markers for each track
    data.forEach((track, index) => {
        try {
            // Defensive: skip invalid tracks
            if (!track || typeof track !== 'object') return;
            if (track.lat == null || track.lon == null || isNaN(track.lat) || isNaN(track.lon)) return;

            // Use hash-based color for consistent kit coloring
            const color = getKitColor(track.kit_id);

            // Check for special statuses - with defensive checks
            const droneId = track.drone_id || 'unknown';
            const isWatchlist = Array.isArray(watchlist) && watchlist.includes(droneId);
            const anomaly = Array.isArray(patternData.anomalies) ? patternData.anomalies.find(a => a && a.drone_id === droneId) : null;
            const isAnomaly = !!anomaly;
            const anomalyTypes = (anomaly && Array.isArray(anomaly.anomaly_types)) ? anomaly.anomaly_types : [];
            const multiKit = Array.isArray(patternData.multiKit) ? patternData.multiKit.find(m => m && m.drone_id === droneId) : null;
            const multiKitCount = (multiKit && Array.isArray(multiKit.kits)) ? multiKit.kits.length : 0;
            const multiKitData = multiKit?.kits || [];  // Per-kit observation data
            const isCoordinated = Array.isArray(patternData.coordinated) && patternData.coordinated.some(g =>
                g && Array.isArray(g.drone_ids) && g.drone_ids.includes(droneId)
            );

            const icon = createMarkerIcon(color, track.track_type, {
                isWatchlist,
                isAnomaly,
                multiKitCount,
                isCoordinated
            });

            const marker = L.marker([track.lat, track.lon], { icon })
                .bindPopup(createPopup(track, { isWatchlist, isAnomaly, anomalyTypes, multiKitCount, multiKitData }))
                .addTo(map);

            markers.push(marker);

            // Add pilot location marker and line if available (must be non-zero - 0,0 means not provided)
            if (showPilotLocations && track.pilot_lat != null && track.pilot_lon != null && (track.pilot_lat !== 0 || track.pilot_lon !== 0)) {
                // Create pilot marker (person icon)
                const pilotIcon = L.divIcon({
                    className: 'pilot-marker',
                    html: `<div style="
                        background-color: #ff9900;
                        border: 2px solid #cc7700;
                        border-radius: 50%;
                        width: 12px;
                        height: 12px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    "><span style="font-size: 8px;">P</span></div>`,
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                });

                const pilotMarker = L.marker([track.pilot_lat, track.pilot_lon], { icon: pilotIcon })
                    .bindPopup(`
                        <div class="popup-title">Pilot: ${track.drone_id}</div>
                        <div class="popup-row">
                            <span class="popup-label">Position:</span>
                            <span class="popup-value">${formatCoord(track.pilot_lat)}, ${formatCoord(track.pilot_lon)}</span>
                        </div>
                    `)
                    .addTo(map);
                pilotMarkers.push(pilotMarker);

                // Draw line from drone to pilot
                const pilotLine = L.polyline(
                    [[track.lat, track.lon], [track.pilot_lat, track.pilot_lon]],
                    {
                        color: '#ff9900',
                        weight: 2,
                        dashArray: '5, 5',
                        opacity: 0.7
                    }
                ).addTo(map);
                pilotLines.push(pilotLine);
            }

            // Add home location marker and line if available (must be non-zero - 0,0 means not provided)
            if (showHomeLocations && track.home_lat != null && track.home_lon != null && (track.home_lat !== 0 || track.home_lon !== 0)) {
                // Create home marker (house icon)
                const homeIcon = L.divIcon({
                    className: 'home-marker',
                    html: `<div style="
                        background-color: #00cc00;
                        border: 2px solid #009900;
                        border-radius: 50%;
                        width: 12px;
                        height: 12px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    "><span style="font-size: 8px;">H</span></div>`,
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                });

                const homeMarker = L.marker([track.home_lat, track.home_lon], { icon: homeIcon })
                    .bindPopup(`
                        <div class="popup-title">Home: ${track.drone_id}</div>
                        <div class="popup-row">
                            <span class="popup-label">Position:</span>
                            <span class="popup-value">${formatCoord(track.home_lat)}, ${formatCoord(track.home_lon)}</span>
                        </div>
                    `)
                    .addTo(map);
                homeMarkers.push(homeMarker);

                // Draw line from drone to home
                const homeLine = L.polyline(
                    [[track.lat, track.lon], [track.home_lat, track.home_lon]],
                    {
                        color: '#00cc00',
                        weight: 2,
                        dashArray: '3, 3',
                        opacity: 0.7
                    }
                ).addTo(map);
                homeLines.push(homeLine);
            }
        } catch (e) {
            console.warn('Error adding marker for track:', track, e);
        }
    });

    // Auto-fit bounds only on first load - preserve user's zoom/pan during refresh
    try {
        if (markers.length > 0 && !initialLoadComplete) {
            const group = L.featureGroup(markers);
            map.fitBounds(group.getBounds().pad(0.1));
            initialLoadComplete = true;  // Only fit bounds once
        }
    } catch (e) {
        console.warn('Error fitting map bounds:', e);
    }

    // Reopen popup if one was open before refresh
    if (reopenPopupForDrone) {
        const droneData = data.find(d => d && d.drone_id === reopenPopupForDrone);
        if (droneData) {
            markers.forEach(marker => {
                const pos = marker.getLatLng();
                if (Math.abs(droneData.lat - pos.lat) < 0.00001 && Math.abs(droneData.lon - pos.lng) < 0.00001) {
                    marker.openPopup();
                }
            });
        }
    }
}

// Draw pattern connections on map
function drawPatternConnections() {
    // Draw coordinated drone connections
    patternData.coordinated.forEach(group => {
        if (group.drone_ids && group.drone_ids.length > 1) {
            const drones = currentData.filter(d => group.drone_ids.includes(d.drone_id));
            if (drones.length > 1) {
                for (let i = 0; i < drones.length - 1; i++) {
                    for (let j = i + 1; j < drones.length; j++) {
                        if (drones[i].lat && drones[j].lat) {
                            const line = L.polyline(
                                [[drones[i].lat, drones[i].lon], [drones[j].lat, drones[j].lon]],
                                {
                                    color: PATTERN_COLORS.coordinated,
                                    weight: 2,
                                    dashArray: '5, 5',
                                    opacity: 0.7
                                }
                            ).addTo(map);
                            lines.push(line);
                        }
                    }
                }
            }
        }
    });

    // Draw pilot reuse connections
    patternData.pilotReuse.forEach(pilot => {
        if (pilot.pilot_lat && pilot.pilot_lon && pilot.drone_ids) {
            pilot.drone_ids.forEach(droneId => {
                const drone = currentData.find(d => d.drone_id === droneId);
                if (drone && drone.lat) {
                    const line = L.polyline(
                        [[pilot.pilot_lat, pilot.pilot_lon], [drone.lat, drone.lon]],
                        {
                            color: PATTERN_COLORS.pilotReuse,
                            weight: 2,
                            opacity: 0.6
                        }
                    ).addTo(map);
                    lines.push(line);
                }
            });
        }
    });
}

// =============================================================================
// Pilot/Home Location Toggle Functions
// =============================================================================

// Toggle pilot location visibility
function togglePilotLocations(show) {
    showPilotLocations = show;
    updateMap(currentData);
}

// Toggle home location visibility
function toggleHomeLocations(show) {
    showHomeLocations = show;
    updateMap(currentData);
}

// Fit map bounds to show all drones (manual trigger)
function fitToAllDrones() {
    if (markers.length === 0) {
        console.log('No drones to fit to');
        return;
    }
    try {
        const group = L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.1));
    } catch (e) {
        console.warn('Error fitting map bounds:', e);
    }
}

// =============================================================================
// Flight Path (Breadcrumb Trail) Functions
// =============================================================================

// Show flight path for a drone
async function showFlightPath(droneId) {
    // Hide any existing flight path first
    if (activeFlightPath && activeFlightPath !== droneId) {
        hideFlightPath(activeFlightPath);
    }

    // Get the time range from the current filter
    const timeRange = document.getElementById('time-range').value;

    try {
        // Fetch track history from API
        const response = await fetch(`/api/drones/${encodeURIComponent(droneId)}/track?time_range=${timeRange}&limit=500`);
        const data = await response.json();

        if (!data.track || data.track.length < 2) {
            console.log(`Not enough track points for ${droneId}`);
            return;
        }

        // Analyze which kits observed this drone
        const uniqueKits = [...new Set(data.track.map(p => p.kit_id).filter(k => k))];
        const isMultiKit = uniqueKits.length > 1;

        // Storage for polylines and markers
        const polylines = [];
        const outlinePolylines = [];
        const breadcrumbMarkers = [];

        if (isMultiKit) {
            // Multi-kit: Create segments color-coded by kit
            let currentKit = null;
            let segmentPoints = [];

            // First create a full outline for the entire path
            const allPoints = data.track.map(p => [p.lat, p.lon]);
            const fullOutline = L.polyline(allPoints, {
                color: '#000000',
                weight: 7,
                opacity: 0.6,
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(map);
            outlinePolylines.push(fullOutline);

            // Create color-coded segments by kit
            data.track.forEach((point, index) => {
                const kitId = point.kit_id || 'unknown';

                if (currentKit !== kitId && segmentPoints.length > 0) {
                    // Kit changed - draw the previous segment
                    const segmentColor = getKitColor(currentKit);
                    const segment = L.polyline(segmentPoints, {
                        color: segmentColor,
                        weight: 4,
                        opacity: 0.9,
                        lineCap: 'round',
                        lineJoin: 'round',
                        className: 'flight-path-line'
                    }).addTo(map);
                    segment.bindTooltip(`Observed by: ${getKitName(currentKit)}`, { sticky: true });
                    polylines.push(segment);

                    // Start new segment with overlap point for continuity
                    segmentPoints = [segmentPoints[segmentPoints.length - 1]];
                }

                currentKit = kitId;
                segmentPoints.push([point.lat, point.lon]);
            });

            // Draw final segment
            if (segmentPoints.length > 1) {
                const segmentColor = getKitColor(currentKit);
                const segment = L.polyline(segmentPoints, {
                    color: segmentColor,
                    weight: 4,
                    opacity: 0.9,
                    lineCap: 'round',
                    lineJoin: 'round',
                    className: 'flight-path-line'
                }).addTo(map);
                segment.bindTooltip(`Observed by: ${getKitName(currentKit)}`, { sticky: true });
                polylines.push(segment);
            }

            // Add kit handoff markers (where kit changes)
            let prevKit = data.track[0]?.kit_id;
            data.track.forEach((point, index) => {
                if (index > 0 && point.kit_id !== prevKit) {
                    const handoffMarker = L.circleMarker([point.lat, point.lon], {
                        radius: 8,
                        fillColor: '#ffffff',
                        fillOpacity: 0.9,
                        color: '#000',
                        weight: 2
                    }).addTo(map);
                    handoffMarker.bindTooltip(
                        `Kit handoff: ${getKitName(prevKit)} → ${getKitName(point.kit_id)}<br>${formatTime(point.time)}`,
                        { permanent: false, direction: 'top' }
                    );
                    breadcrumbMarkers.push(handoffMarker);
                    prevKit = point.kit_id;
                }
            });
        } else {
            // Single-kit: Original behavior
            const drone = currentData.find(d => d.drone_id === droneId);
            const baseColor = getKitColor(drone?.kit_id);
            const trackPoints = data.track.map(p => [p.lat, p.lon]);

            // Dark outline underneath
            const outlinePolyline = L.polyline(trackPoints, {
                color: '#000000',
                weight: 7,
                opacity: 0.6,
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(map);
            outlinePolylines.push(outlinePolyline);

            // Main colored line
            const polyline = L.polyline(trackPoints, {
                color: baseColor,
                weight: 4,
                opacity: 0.9,
                lineCap: 'round',
                lineJoin: 'round',
                className: 'flight-path-line'
            }).addTo(map);
            polylines.push(polyline);
        }

        // Add breadcrumb markers (every Nth point)
        const step = Math.max(1, Math.floor(data.track.length / 20));

        data.track.forEach((point, index) => {
            if (index === 0 || index === data.track.length - 1) return;
            if (index % step !== 0) return;

            const opacity = 0.3 + (0.5 * (index / data.track.length));
            const pointColor = getKitColor(point.kit_id);

            const breadcrumb = L.circleMarker([point.lat, point.lon], {
                radius: 6,
                fillColor: pointColor,
                fillOpacity: opacity,
                color: '#000',
                weight: 2,
                opacity: 0.8
            }).addTo(map);

            const kitInfo = isMultiKit ? `<br>Kit: ${getKitName(point.kit_id)}` : '';
            breadcrumb.bindTooltip(`${formatTime(point.time)}<br>Alt: ${point.alt?.toFixed(0) || 'N/A'}m${kitInfo}`, {
                permanent: false,
                direction: 'top'
            });

            breadcrumbMarkers.push(breadcrumb);
        });

        // Add start point marker (green)
        const startPoint = data.track[0];
        const startMarker = L.circleMarker([startPoint.lat, startPoint.lon], {
            radius: 8,
            fillColor: '#00ff00',
            fillOpacity: 0.9,
            color: '#000',
            weight: 2
        }).addTo(map);
        const startKitInfo = isMultiKit ? `<br>Kit: ${getKitName(startPoint.kit_id)}` : '';
        startMarker.bindTooltip(`Start: ${formatTime(startPoint.time)}${startKitInfo}`, {
            permanent: false,
            direction: 'top'
        });
        breadcrumbMarkers.push(startMarker);

        // Add legend for multi-kit paths
        if (isMultiKit) {
            const legendHtml = uniqueKits.map(kitId =>
                `<span style="color: ${getKitColor(kitId)};">●</span> ${getKitName(kitId)}`
            ).join('<br>');
            const legendMarker = L.marker([startPoint.lat, startPoint.lon], {
                icon: L.divIcon({
                    className: 'flight-path-legend',
                    html: `<div style="background: rgba(0,0,0,0.8); padding: 5px 8px; border-radius: 4px; font-size: 11px; white-space: nowrap;">
                        <strong style="color: #fff;">Kits (${uniqueKits.length}):</strong><br>${legendHtml}
                    </div>`,
                    iconAnchor: [-10, 0]
                })
            }).addTo(map);
            breadcrumbMarkers.push(legendMarker);
        }

        // Store flight path data
        flightPaths[droneId] = {
            polylines: polylines,
            outlinePolylines: outlinePolylines,
            markers: breadcrumbMarkers,
            pointCount: data.track.length,
            isMultiKit: isMultiKit,
            kits: uniqueKits
        };
        activeFlightPath = droneId;

        // Update popup to show "Hide" button
        updatePopupForDrone(droneId);

        console.log(`Showing flight path for ${droneId}: ${data.track.length} points`);

    } catch (error) {
        console.error(`Failed to fetch flight path for ${droneId}:`, error);
    }
}

// Hide flight path for a drone
function hideFlightPath(droneId) {
    const pathData = flightPaths[droneId];
    if (pathData) {
        // Remove polylines (may be array for multi-kit or single for legacy)
        if (Array.isArray(pathData.polylines)) {
            pathData.polylines.forEach(p => map.removeLayer(p));
        } else if (pathData.polyline) {
            map.removeLayer(pathData.polyline);
        }
        // Remove outline polylines
        if (Array.isArray(pathData.outlinePolylines)) {
            pathData.outlinePolylines.forEach(p => map.removeLayer(p));
        } else if (pathData.outlinePolyline) {
            map.removeLayer(pathData.outlinePolyline);
        }
        // Remove breadcrumb markers
        if (pathData.markers) {
            pathData.markers.forEach(marker => map.removeLayer(marker));
        }
        delete flightPaths[droneId];
    }

    if (activeFlightPath === droneId) {
        activeFlightPath = null;
    }

    // Update popup to show "Show" button
    updatePopupForDrone(droneId);

    console.log(`Hidden flight path for ${droneId}`);
}

// Clear all flight paths
function clearAllFlightPaths() {
    Object.keys(flightPaths).forEach(droneId => {
        hideFlightPath(droneId);
    });
    activeFlightPath = null;
}

// Update popup content for a specific drone (after showing/hiding flight path)
function updatePopupForDrone(droneId) {
    // Find the marker for this drone and update its popup
    const drone = currentData.find(d => d.drone_id === droneId);
    if (!drone) return;

    markers.forEach(marker => {
        const pos = marker.getLatLng();
        if (Math.abs(pos.lat - drone.lat) < 0.00001 && Math.abs(pos.lng - drone.lon) < 0.00001) {
            // Check for special statuses
            const isWatchlist = watchlist.includes(drone.drone_id);
            const anomaly = patternData.anomalies.find(a => a.drone_id === drone.drone_id);
            const isAnomaly = !!anomaly;
            const anomalyTypes = anomaly ? anomaly.anomaly_types || [] : [];
            const multiKit = patternData.multiKit.find(m => m.drone_id === drone.drone_id);
            const multiKitCount = (multiKit && Array.isArray(multiKit.kits)) ? multiKit.kits.length : 0;
            const multiKitData = multiKit?.kits || [];

            // Update popup content
            marker.setPopupContent(createPopup(drone, {
                isWatchlist, isAnomaly, anomalyTypes, multiKitCount, multiKitData
            }));
        }
    });
}

// =============================================================================
// RSSI-Based Location Estimation
// =============================================================================

// Request location estimation from API
async function estimateLocation(droneId, timestamp) {
    // Clear any existing estimation
    clearEstimation();

    // Update button to loading state
    const btn = document.querySelector('.estimate-btn');
    if (btn) {
        btn.classList.add('loading');
        btn.textContent = 'Estimating...';
        btn.disabled = true;
    }

    try {
        let url = `/api/analysis/estimate-location/${encodeURIComponent(droneId)}`;
        if (timestamp) {
            url += `?timestamp=${encodeURIComponent(timestamp)}`;
        }

        const response = await fetch(url);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Estimation failed');
        }

        const result = await response.json();
        displayEstimation(result);
        activeEstimation = droneId;

        // Update button state
        if (btn) {
            btn.classList.remove('loading');
            btn.classList.add('active');
            btn.textContent = 'Hide Estimation';
            btn.disabled = false;
            btn.onclick = () => clearEstimation();
        }

        console.log(`Estimated location for ${droneId}:`, result);
    } catch (error) {
        console.error('Estimation error:', error);
        alert('Location estimation failed: ' + error.message);

        // Reset button
        if (btn) {
            btn.classList.remove('loading');
            btn.textContent = 'Estimate Location';
            btn.disabled = false;
        }
    }
}

// Display estimation result on map
function displayEstimation(result) {
    const estimated = result.estimated;
    const actual = result.actual;
    const confidence = result.confidence_radius_m;
    const errorMeters = result.error_meters;

    // Create estimated location marker (dashed yellow circle)
    const estimateIcon = L.divIcon({
        className: 'estimate-marker',
        html: `<div style="
            width: 20px;
            height: 20px;
            background: rgba(255, 200, 0, 0.3);
            border: 3px dashed #ffcc00;
            border-radius: 50%;
            box-shadow: 0 0 10px rgba(255, 200, 0, 0.5);
        "></div>`,
        iconSize: [26, 26],
        iconAnchor: [13, 13]
    });

    estimationMarker = L.marker([estimated.lat, estimated.lon], { icon: estimateIcon })
        .bindPopup(`
            <div class="popup-title">Estimated Location</div>
            <div class="popup-row">
                <span class="popup-label">Position:</span>
                <span class="popup-value">${estimated.lat.toFixed(6)}, ${estimated.lon.toFixed(6)}</span>
            </div>
            <div class="popup-row">
                <span class="popup-label">Confidence:</span>
                <span class="popup-value">${confidence.toFixed(0)}m radius</span>
            </div>
            ${errorMeters != null ? `
            <div class="popup-row">
                <span class="popup-label">Error:</span>
                <span class="popup-value">${errorMeters.toFixed(1)}m from actual</span>
            </div>
            ` : ''}
        `)
        .addTo(map);

    // Create confidence radius circle
    estimationCircle = L.circle([estimated.lat, estimated.lon], {
        radius: confidence,
        color: '#ffcc00',
        fillColor: '#ffcc00',
        fillOpacity: 0.1,
        weight: 2,
        dashArray: '5, 5'
    }).addTo(map);

    // If we have actual position, draw error line
    if (actual && actual.lat && actual.lon) {
        estimationErrorLine = L.polyline([
            [estimated.lat, estimated.lon],
            [actual.lat, actual.lon]
        ], {
            color: '#ff4444',
            weight: 2,
            dashArray: '10, 5',
            opacity: 0.8
        }).addTo(map);
    }

    // Create info overlay
    showEstimationOverlay(result);

    // Zoom to show the estimation
    const bounds = L.latLngBounds([
        [estimated.lat, estimated.lon]
    ]);
    if (actual && actual.lat && actual.lon) {
        bounds.extend([actual.lat, actual.lon]);
    }
    // Pad bounds to show confidence radius
    map.fitBounds(bounds.pad(0.5));
}

// Show estimation info overlay
function showEstimationOverlay(result) {
    // Remove existing overlay
    if (estimationOverlay) {
        estimationOverlay.remove();
    }

    const errorMeters = result.error_meters;
    let errorClass = 'error-good';
    if (errorMeters != null) {
        if (errorMeters > 500) errorClass = 'error-bad';
        else if (errorMeters > 200) errorClass = 'error-poor';
        else if (errorMeters > 100) errorClass = 'error-fair';
    }

    // Spoofing detection display
    const spoofingScore = result.spoofing_score;
    const spoofingSuspected = result.spoofing_suspected;
    const spoofingReason = result.spoofing_reason;
    let spoofingClass = 'spoof-normal';
    let spoofingLabel = 'Normal';
    if (spoofingScore != null) {
        if (spoofingScore >= 0.7) {
            spoofingClass = 'spoof-likely';
            spoofingLabel = 'Likely Spoofing';
        } else if (spoofingScore >= 0.5) {
            spoofingClass = 'spoof-suspicious';
            spoofingLabel = 'Suspicious';
        } else if (spoofingScore >= 0.3) {
            spoofingClass = 'spoof-monitor';
            spoofingLabel = 'Monitor';
        }
    }

    const overlay = document.createElement('div');
    overlay.className = 'estimate-overlay';
    overlay.innerHTML = `
        <button class="close-btn" onclick="clearEstimation()">&times;</button>
        <h4>Location Estimation</h4>
        <div class="stat-row">
            <span class="stat-label">Drone:</span>
            <span class="stat-value">${result.drone_id}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Algorithm:</span>
            <span class="stat-value">${result.algorithm}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Kits used:</span>
            <span class="stat-value">${result.observations.length}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Confidence:</span>
            <span class="stat-value">${result.confidence_radius_m.toFixed(0)}m</span>
        </div>
        ${errorMeters != null ? `
        <div class="stat-row">
            <span class="stat-label">Error:</span>
            <span class="stat-value ${errorClass}">${errorMeters.toFixed(1)}m</span>
        </div>
        ` : `
        <div class="stat-row">
            <span class="stat-label">Error:</span>
            <span class="stat-value">N/A (no actual position)</span>
        </div>
        `}
        ${spoofingScore != null ? `
        <div class="stat-row" style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #444;">
            <span class="stat-label">Spoofing:</span>
            <span class="stat-value ${spoofingClass}">${spoofingLabel} (${(spoofingScore * 100).toFixed(0)}%)</span>
        </div>
        ${spoofingReason ? `
        <div style="font-size: 10px; color: #ff8800; margin-top: 4px;">
            ${spoofingReason}
        </div>
        ` : ''}
        ` : ''}
        <div style="margin-top: 8px; font-size: 10px; color: #888;">
            ${result.observations.map(o => `${getKitName(o.kit_id)}: ${o.rssi || 'N/A'} dBm`).join('<br>')}
        </div>
    `;

    document.getElementById('map').appendChild(overlay);
    estimationOverlay = overlay;
}

// Clear estimation display
function clearEstimation() {
    if (estimationMarker) {
        map.removeLayer(estimationMarker);
        estimationMarker = null;
    }
    if (estimationCircle) {
        map.removeLayer(estimationCircle);
        estimationCircle = null;
    }
    if (estimationErrorLine) {
        map.removeLayer(estimationErrorLine);
        estimationErrorLine = null;
    }
    if (estimationOverlay) {
        estimationOverlay.remove();
        estimationOverlay = null;
    }

    // Update button if it exists
    const btn = document.querySelector('.estimate-btn');
    if (btn) {
        btn.classList.remove('active');
        btn.textContent = 'Estimate Location';
        const droneId = btn.getAttribute('data-drone-id');
        const timestamp = btn.getAttribute('data-timestamp');
        if (droneId) {
            btn.onclick = () => estimateLocation(droneId, timestamp);
        }
    }

    activeEstimation = null;
}

// =============================================================================

// Update table
function updateTable(data) {
    const tbody = document.getElementById('tracks-table');
    tbody.innerHTML = '';

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #aaa;">No data available</td></tr>';
        return;
    }

    data.slice(0, 100).forEach(track => {
        const row = document.createElement('tr');
        row.className = 'track-row';

        // Add special row classes
        if (watchlist.includes(track.drone_id)) {
            row.classList.add('watchlist');
        }
        if (patternData.anomalies.some(a => a.drone_id === track.drone_id)) {
            row.classList.add('anomaly');
        }
        // Check for multi-kit detection
        const multiKitCheck = patternData.multiKit.find(m => m.drone_id === track.drone_id);
        if (multiKitCheck && Array.isArray(multiKitCheck.kits) && multiKitCheck.kits.length > 1) {
            row.classList.add('multi-kit');
        }

        row.onclick = () => {
            if (track.lat != null && track.lon != null) {
                map.setView([track.lat, track.lon], 15);
                markers.forEach(marker => {
                    const pos = marker.getLatLng();
                    if (pos.lat === track.lat && pos.lng === track.lon) {
                        marker.openPopup();
                    }
                });
            }
        };

        // Look up kit name and check for multi-kit
        const kitName = getKitName(track.kit_id);
        const multiKit = patternData.multiKit.find(m => m.drone_id === track.drone_id);
        const multiKitCount = (multiKit && Array.isArray(multiKit.kits)) ? multiKit.kits.length : 0;

        let kitDisplay = kitName !== track.kit_id ? kitName : track.kit_id;
        let kitTooltip = kitName !== track.kit_id ? `ID: ${track.kit_id}` : '';

        // Add multi-kit indicator
        if (multiKitCount > 1) {
            const otherKits = multiKit.kits
                .filter(k => k.kit_id !== track.kit_id)
                .map(k => getKitName(k.kit_id))
                .join(', ');
            kitDisplay += ` <span style="color: #4488ff; font-size: 10px;">+${multiKitCount - 1}</span>`;
            kitTooltip = `Also seen by: ${otherKits}${kitTooltip ? '\n' + kitTooltip : ''}`;
            if (multiKitCount >= 3) {
                kitDisplay += ' <span style="color: #aa88ff; font-size: 10px;">◎</span>';
                kitTooltip = '◎ Triangulation possible\n' + kitTooltip;
            }
        }

        row.innerHTML = `
            <td>${formatTime(track.time)}</td>
            <td ${kitTooltip ? `title="${kitTooltip}"` : ''}>${kitDisplay}</td>
            <td>${track.drone_id}</td>
            <td>${track.track_type || 'drone'}</td>
            <td>${track.rid_make || 'N/A'}</td>
            <td>${track.rid_model || 'N/A'}</td>
            <td>${formatCoord(track.lat)}</td>
            <td>${formatCoord(track.lon)}</td>
            <td>${track.alt != null ? track.alt.toFixed(1) : 'N/A'}</td>
            <td>${track.speed != null ? track.speed.toFixed(1) : 'N/A'}</td>
        `;
        tbody.appendChild(row);
    });
}

// Update stats - accepts optional API response with pre-computed counts
function updateStats(data, apiResponse = null) {
    // Use API counts if available (already deduplicated by drone_id)
    // Otherwise count unique drone_ids from the data
    const uniqueDroneIds = new Set(data.map(d => d.drone_id));
    const drones = data.filter(d => d.track_type === 'drone' || !d.track_type);
    const aircraft = data.filter(d => d.track_type === 'aircraft');
    const uniqueKits = new Set(data.map(d => d.kit_id));

    // Count unique drone_ids within each track type
    const uniqueDroneOnlyIds = new Set(drones.map(d => d.drone_id));
    const uniqueAircraftIds = new Set(aircraft.map(d => d.drone_id));

    // total-tracks shows total unique targets (drones + aircraft)
    document.getElementById('total-tracks').textContent = uniqueDroneIds.size;
    document.getElementById('total-drones').textContent = uniqueDroneOnlyIds.size;
    document.getElementById('total-aircraft').textContent = uniqueAircraftIds.size;
    document.getElementById('active-kits').textContent = uniqueKits.size;
}

// Update threat summary cards
function updateThreatCards() {
    // Active threats (anomalies in last hour)
    const activeThreatsCount = patternData.anomalies.length;
    document.getElementById('active-threats').textContent = activeThreatsCount;

    // Repeated contacts
    const repeatedCount = patternData.repeated.length;
    document.getElementById('repeated-contacts').textContent = repeatedCount;

    // Multi-kit detections
    const multiKitCount = patternData.multiKit.length;
    document.getElementById('multi-kit-detections').textContent = multiKitCount;

    // Total anomalies by type
    const anomalyCount = patternData.anomalies.reduce((sum, a) =>
        sum + (a.anomaly_types ? a.anomaly_types.length : 0), 0
    );
    document.getElementById('anomalies-count').textContent = anomalyCount;

    // Update quick filter counts
    document.getElementById('unusual-count').textContent = activeThreatsCount;
    document.getElementById('repeated-count').textContent = repeatedCount;
    document.getElementById('multikit-count').textContent = multiKitCount;
    document.getElementById('coordinated-count').textContent = patternData.coordinated.length;
}

// Alert Management
function addAlert(type, title, message) {
    const alert = {
        id: Date.now(),
        type, // 'info', 'warning', 'critical'
        title,
        message,
        time: new Date().toISOString()
    };

    alerts.push(alert);
    saveAlerts();
    renderAlerts();
}

function dismissAlert(alertId) {
    alerts = alerts.filter(a => a.id !== alertId);
    saveAlerts();
    renderAlerts();
}

function clearAllAlerts() {
    alerts = [];
    saveAlerts();
    renderAlerts();
}

function renderAlerts() {
    const panel = document.getElementById('alert-panel');
    const list = document.getElementById('alerts-list');

    if (alerts.length === 0) {
        panel.classList.remove('has-alerts');
        return;
    }

    panel.classList.add('has-alerts');
    list.innerHTML = '';

    alerts.forEach(alert => {
        const alertEl = document.createElement('div');
        alertEl.className = `alert-item ${alert.type}`;
        alertEl.innerHTML = `
            <div class="alert-content">
                <div class="alert-title">${alert.title}</div>
                <div class="alert-message">${alert.message}</div>
            </div>
            <span class="alert-time">${formatTime(alert.time)}</span>
            <button class="alert-dismiss" onclick="dismissAlert(${alert.id})">×</button>
        `;
        list.appendChild(alertEl);
    });
}

function saveAlerts() {
    localStorage.setItem('wardragon_alerts', JSON.stringify(alerts));
}

function loadAlerts() {
    const saved = localStorage.getItem('wardragon_alerts');
    if (saved) {
        alerts = JSON.parse(saved);
        renderAlerts();
    }
}

// Check for new alerts based on pattern data
function checkForAlerts() {
    const now = new Date();

    // Check for new anomalies
    patternData.anomalies.forEach(anomaly => {
        const existingAlert = alerts.find(a =>
            a.message.includes(anomaly.drone_id) && a.type === 'critical'
        );
        if (!existingAlert) {
            const anomalyTypes = anomaly.anomaly_types ? anomaly.anomaly_types.join(', ') : 'Unknown';
            addAlert('critical', 'Anomaly Detected',
                `Drone ${anomaly.drone_id}: ${anomalyTypes}`);
        }
    });

    // Check for coordinated activity
    patternData.coordinated.forEach(group => {
        if (group.drone_ids && group.drone_ids.length > 2) {
            const existingAlert = alerts.find(a =>
                a.message.includes('coordinated') && a.message.includes(group.drone_ids[0])
            );
            if (!existingAlert) {
                addAlert('warning', 'Coordinated Activity',
                    `${group.drone_ids.length} drones detected in close proximity`);
            }
        }
    });

    // Check for watchlist matches
    const watchlistMatches = currentData.filter(d => watchlist.includes(d.drone_id));
    watchlistMatches.forEach(drone => {
        const existingAlert = alerts.find(a =>
            a.message.includes(drone.drone_id) && a.type === 'info'
        );
        if (!existingAlert) {
            addAlert('info', 'Watchlist Match',
                `Drone ${drone.drone_id} detected`);
        }
    });
}

// Watchlist Management
function addToWatchlist(droneId) {
    droneId = droneId.trim();
    if (droneId && !watchlist.includes(droneId)) {
        watchlist.push(droneId);
        saveWatchlist();
        renderWatchlist();
        applyFilters();
    }
}

function removeFromWatchlist(droneId) {
    watchlist = watchlist.filter(id => id !== droneId);
    saveWatchlist();
    renderWatchlist();
    applyFilters();
}

function renderWatchlist() {
    const container = document.getElementById('watchlist-items');
    container.innerHTML = '';

    watchlist.forEach(droneId => {
        const tag = document.createElement('div');
        tag.className = 'watchlist-tag';
        tag.innerHTML = `
            ${droneId}
            <span class="remove" onclick="removeFromWatchlist('${droneId}')">×</span>
        `;
        container.appendChild(tag);
    });
}

function saveWatchlist() {
    localStorage.setItem('wardragon_watchlist', JSON.stringify(watchlist));
}

function loadWatchlist() {
    const saved = localStorage.getItem('wardragon_watchlist');
    if (saved) {
        watchlist = JSON.parse(saved);
        renderWatchlist();
    }
}

// Fetch kits with timeout
async function fetchKits() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

        const response = await fetch('/api/kits', { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        kits = data.kits || [];
        updateKitCheckboxes();
    } catch (error) {
        if (error.name === 'AbortError') {
            console.warn('Kit fetch timed out - database may be slow');
        } else {
            console.error('Failed to fetch kits:', error);
        }
        // Keep existing kits data if we have it
    }
}

// Update kit checkboxes - preserves user's checkbox selections
function updateKitCheckboxes() {
    const container = document.getElementById('kit-checkboxes');

    // Save current checkbox states before rebuilding
    const previousStates = new Map();
    const existingCheckboxes = container.querySelectorAll('input[type="checkbox"]');
    existingCheckboxes.forEach(cb => {
        if (cb.value !== 'all') {
            previousStates.set(cb.value, cb.checked);
        }
    });
    const hadPreviousKits = previousStates.size > 0;

    container.innerHTML = '<label><input type="checkbox" value="all" checked> All Kits</label>';

    if (!kits || kits.length === 0) {
        const noKitsMsg = document.createElement('div');
        noKitsMsg.className = 'no-kits-message';
        noKitsMsg.style.cssText = 'font-size: 11px; color: #888; margin-top: 5px; font-style: italic;';
        noKitsMsg.textContent = 'No kits registered yet. Add kits via Kits button or wait for MQTT data.';
        container.appendChild(noKitsMsg);
        return;
    }

    kits.forEach(kit => {
        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = kit.kit_id;

        // Preserve previous state if it existed, otherwise default to checked
        if (hadPreviousKits && previousStates.has(kit.kit_id)) {
            checkbox.checked = previousStates.get(kit.kit_id);
        } else {
            checkbox.checked = true;  // New kits default to checked
        }

        // Status indicator: online=green, stale=yellow, offline=red
        const statusDot = kit.status === 'online' ? '🟢' : kit.status === 'stale' ? '🟡' : '🔴';
        // Source indicator: M=MQTT, H=Hybrid, D=Discovered from drone data
        const sourceTag = kit.source === 'mqtt' ? ' [M]' :
                         kit.source === 'hybrid' ? ' [H]' :
                         kit.source === 'discovered' ? ' [D]' : '';

        label.appendChild(checkbox);
        label.appendChild(document.createTextNode(` ${statusDot} ${kit.name || kit.kit_id}${sourceTag}`));
        label.title = `Status: ${kit.status || 'unknown'}, Source: ${kit.source || 'http'}\n[M]=MQTT, [H]=Hybrid, [D]=Discovered from data`;
        container.appendChild(label);
    });
}

// Get selected filters
function getFilters() {
    const timeRange = document.getElementById('time-range').value;
    const ridMake = document.getElementById('rid-make').value;
    const showDrones = document.getElementById('show-drones').checked;
    const showAircraft = document.getElementById('show-aircraft').checked;

    const kitCheckboxes = document.querySelectorAll('#kit-checkboxes input[type="checkbox"]:checked');
    const selectedKits = Array.from(kitCheckboxes)
        .map(cb => cb.value)
        .filter(v => v !== 'all');

    const filters = { time_range: timeRange };
    if (selectedKits.length > 0) {
        filters.kit_id = selectedKits.join(',');
    }
    if (ridMake) {
        filters.rid_make = ridMake;
    }

    return { filters, showDrones, showAircraft };
}

// Apply active filters to data
function applyActiveFilters(data) {
    let filtered = [...data];

    // Show unusual filter
    if (activeFilters.showUnusual) {
        filtered = filtered.filter(d =>
            patternData.anomalies.some(a => a.drone_id === d.drone_id)
        );
    }

    // Show repeated filter
    if (activeFilters.showRepeated) {
        filtered = filtered.filter(d =>
            patternData.repeated.some(r => r.drone_id === d.drone_id)
        );
    }

    // Show coordinated filter
    if (activeFilters.showCoordinated) {
        const coordinatedDrones = patternData.coordinated.flatMap(g => g.drone_ids || []);
        filtered = filtered.filter(d => coordinatedDrones.includes(d.drone_id));
    }

    // Show multi-kit filter (drones seen by 2+ kits)
    if (activeFilters.showMultikit) {
        const multikitDrones = patternData.multiKit.map(m => m.drone_id);
        filtered = filtered.filter(d => multikitDrones.includes(d.drone_id));
    }

    // Geographic polygon filter
    if (activeFilters.geoPolygon) {
        filtered = filtered.filter(d => {
            if (!d.lat || !d.lon) return false;
            return isPointInPolygon([d.lon, d.lat], activeFilters.geoPolygon);
        });
    }

    return filtered;
}

// Point in polygon check
function isPointInPolygon(point, polygon) {
    const [x, y] = point;
    let inside = false;

    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        const [xi, yi] = polygon[i];
        const [xj, yj] = polygon[j];

        const intersect = ((yi > y) !== (yj > y)) &&
            (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
    }

    return inside;
}

// Convert time_range to minutes for pattern APIs
function timeRangeToMinutes(timeRange) {
    const match = timeRange.match(/^(\d+)([mhd])$/);
    if (!match) return 60;  // Default to 60 minutes
    const value = parseInt(match[1]);
    const unit = match[2];
    switch (unit) {
        case 'm': return value;
        case 'h': return value * 60;
        case 'd': return value * 24 * 60;
        default: return 60;
    }
}

// Fetch pattern data
async function fetchPatterns() {
    const { filters } = getFilters();
    const timeWindowMinutes = timeRangeToMinutes(filters.time_range || '1h');

    try {
        // Fetch all pattern endpoints
        const endpoints = [
            'repeated-drones',
            'coordinated',
            'pilot-reuse',
            'anomalies',
            'multi-kit'
        ];

        const promises = endpoints.map(async (endpoint) => {
            try {
                const params = new URLSearchParams(filters);
                // Add time_window_minutes for endpoints that need it
                if (endpoint === 'multi-kit') {
                    params.set('time_window_minutes', Math.min(timeWindowMinutes, 10080));  // Max 7 days
                }
                if (endpoint === 'anomalies') {
                    params.set('time_window_hours', Math.max(1, Math.ceil(timeWindowMinutes / 60)));
                }
                const response = await fetch(`/api/patterns/${endpoint}?${params}`);
                if (response.ok) {
                    return await response.json();
                }
                return null;
            } catch (error) {
                console.log(`Pattern API ${endpoint} not yet available`);
                return null;
            }
        });

        const results = await Promise.all(promises);

        // Update pattern data
        patternData.repeated = results[0]?.drones || [];
        patternData.coordinated = results[1]?.groups || [];
        patternData.pilotReuse = results[2]?.pilots || [];
        patternData.anomalies = results[3]?.anomalies || [];
        patternData.multiKit = results[4]?.multi_kit_detections || [];

        updateThreatCards();
        checkForAlerts();
    } catch (error) {
        console.error('Failed to fetch patterns:', error);
    }
}

// Fetch and update data - with offline/error handling
// Makes separate API calls for drones and aircraft to ensure drones are never
// crowded out by high-volume ADS-B aircraft data
async function fetchData() {
    try {
        // Only show loading overlay on first load to reduce visual flash
        if (currentData.length === 0) {
            showLoading(true);
        }

        const { filters, showDrones, showAircraft } = getFilters();

        let allData = [];

        // Fetch drones and aircraft separately with their own limits
        // This ensures drones are never crowded out by aircraft volume
        const fetchPromises = [];

        if (showDrones) {
            const droneParams = new URLSearchParams(filters);
            droneParams.set('track_type', 'drone');
            droneParams.set('limit', '2000');
            fetchPromises.push(
                fetch(`/api/drones?${droneParams}`)
                    .then(r => r.ok ? r.json() : { drones: [] })
                    .then(data => ({ type: 'drone', data }))
                    .catch(() => ({ type: 'drone', data: { drones: [] } }))
            );
        }

        if (showAircraft) {
            const aircraftParams = new URLSearchParams(filters);
            aircraftParams.set('track_type', 'aircraft');
            aircraftParams.set('limit', '2000');
            fetchPromises.push(
                fetch(`/api/drones?${aircraftParams}`)
                    .then(r => r.ok ? r.json() : { drones: [] })
                    .then(data => ({ type: 'aircraft', data }))
                    .catch(() => ({ type: 'aircraft', data: { drones: [] } }))
            );
        }

        if (fetchPromises.length === 0) {
            currentData = [];
        } else {
            try {
                const results = await Promise.all(fetchPromises);
                for (const result of results) {
                    if (Array.isArray(result.data.drones)) {
                        allData = allData.concat(result.data.drones);
                    }
                }
            } catch (fetchError) {
                console.warn('API fetch failed (may be offline):', fetchError.message);
                const lastUpdate = document.getElementById('last-update');
                if (lastUpdate) {
                    lastUpdate.textContent = `Offline - Last update: ${new Date().toLocaleTimeString()}`;
                    lastUpdate.style.color = '#ff4444';
                }
                // Keep showing existing data if available
                if (currentData.length > 0) {
                    return;
                }
            }
        }

        currentData = allData;

        // Fetch pattern data (don't fail if this errors)
        try {
            await fetchPatterns();
        } catch (patternError) {
            console.warn('Pattern fetch failed:', patternError.message);
        }

        // Apply active filters
        const displayData = applyActiveFilters(currentData);

        updateMap(displayData);
        updateTable(displayData);
        updateStats(currentData);

        const lastUpdate = document.getElementById('last-update');
        if (lastUpdate) {
            lastUpdate.textContent = `Last update: ${new Date().toLocaleTimeString()}`;
            lastUpdate.style.color = '';  // Reset color
        }
    } catch (error) {
        console.error('Failed to fetch data:', error);
        // Only show alert for unexpected errors, not network failures
        if (error.name !== 'TypeError' && !error.message.includes('fetch')) {
            addAlert('critical', 'Data Fetch Error', 'Failed to process drone data');
        }
    } finally {
        showLoading(false);
    }
}

// Show/hide loading indicator
function showLoading(show) {
    let overlay = document.getElementById('loading-overlay');
    if (show && !overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="loading-spinner">
                <div class="spinner"></div>
                <div>Loading data...</div>
            </div>
        `;
        document.querySelector('.map-container').appendChild(overlay);
    } else if (!show && overlay) {
        overlay.remove();
    }
}

// Apply filters
function applyFilters() {
    fetchData();
}

// Toggle quick filter
function toggleQuickFilter(filterName) {
    const btn = document.getElementById(`filter-${filterName}`);
    activeFilters[filterName] = !activeFilters[filterName];

    if (activeFilters[filterName]) {
        btn.classList.add('active');
    } else {
        btn.classList.remove('active');
    }

    const displayData = applyActiveFilters(currentData);
    updateMap(displayData);
    updateTable(displayData);
}

// Filter by threat card
function filterByThreatCard(cardType) {
    // Reset all quick filters
    activeFilters.showUnusual = false;
    activeFilters.showRepeated = false;
    activeFilters.showCoordinated = false;
    activeFilters.showMultikit = false;

    document.getElementById('filter-showUnusual').classList.remove('active');
    document.getElementById('filter-showRepeated').classList.remove('active');
    document.getElementById('filter-showCoordinated').classList.remove('active');
    document.getElementById('filter-showMultikit').classList.remove('active');

    // Activate the selected filter
    if (cardType === 'unusual') {
        activeFilters.showUnusual = true;
        document.getElementById('filter-showUnusual').classList.add('active');
    } else if (cardType === 'repeated') {
        activeFilters.showRepeated = true;
        document.getElementById('filter-showRepeated').classList.add('active');
    } else if (cardType === 'coordinated') {
        activeFilters.showCoordinated = true;
        document.getElementById('filter-showCoordinated').classList.add('active');
    } else if (cardType === 'multikit') {
        activeFilters.showMultikit = true;
        document.getElementById('filter-showMultikit').classList.add('active');
    }

    const displayData = applyActiveFilters(currentData);
    updateMap(displayData);
    updateTable(displayData);
}

// Export CSV
function exportCSV() {
    const { filters } = getFilters();
    const params = new URLSearchParams(filters);
    window.location.href = `/api/export/csv?${params}`;
}

// Toggle theme
function toggleTheme() {
    document.body.classList.toggle('light-theme');
    const theme = document.body.classList.contains('light-theme') ? 'light' : 'dark';
    localStorage.setItem('wardragon_theme', theme);
}

function loadTheme() {
    const theme = localStorage.getItem('wardragon_theme');
    if (theme === 'light') {
        document.body.classList.add('light-theme');
    }
}

// Setup auto-refresh
function setupAutoRefresh() {
    const select = document.getElementById('refresh-interval');
    select.addEventListener('change', () => {
        const interval = parseInt(select.value);

        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }

        if (interval > 0) {
            refreshTimer = setInterval(fetchData, interval * 1000);
            document.getElementById('refresh-status').textContent = `Auto-refresh: ${interval}s`;
        } else {
            document.getElementById('refresh-status').textContent = 'Auto-refresh: Disabled';
        }
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    loadTheme();
    loadWatchlist();
    loadAlerts();

    initMap();
    setupAutoRefresh();
    initAIChat();

    await fetchKits();
    await fetchData();

    // Start auto-refresh (default 5s)
    refreshTimer = setInterval(fetchData, 5000);

    // Start alert check (every 5s)
    alertRefreshTimer = setInterval(checkForAlerts, 5000);

    // Refresh kit list every 30s to pick up new MQTT kits
    setInterval(fetchKits, 30000);
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (refreshTimer) clearInterval(refreshTimer);
    if (alertRefreshTimer) clearInterval(alertRefreshTimer);
});


// =============================================================================
// Kit Manager Functions
// =============================================================================

function openKitManager() {
    document.getElementById('kit-manager-modal').classList.add('active');
    loadKitList();
}

function closeKitManager() {
    document.getElementById('kit-manager-modal').classList.remove('active');
    clearKitTestResult();
}

// Close modal when clicking outside
document.addEventListener('click', (e) => {
    const modal = document.getElementById('kit-manager-modal');
    if (e.target === modal) {
        closeKitManager();
    }
});

// Close modal on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeKitManager();
    }
});

function clearKitTestResult() {
    const resultEl = document.getElementById('kit-test-result');
    resultEl.className = 'kit-test-result';
    resultEl.textContent = '';
}

function showKitTestResult(message, type) {
    const resultEl = document.getElementById('kit-test-result');
    resultEl.className = `kit-test-result ${type}`;
    resultEl.textContent = message;
}

async function testNewKit() {
    const urlInput = document.getElementById('new-kit-url');
    const apiUrl = urlInput.value.trim();

    if (!apiUrl) {
        showKitTestResult('Please enter an API URL', 'error');
        return;
    }

    showKitTestResult('Testing connection...', 'loading');

    try {
        const response = await fetch(`/api/admin/kits/test?api_url=${encodeURIComponent(apiUrl)}`, {
            method: 'POST'
        });
        const result = await response.json();

        if (result.success) {
            let message = `Connection successful!`;
            if (result.kit_id) {
                message += ` Kit ID: ${result.kit_id}`;
            }
            if (result.response_time_ms) {
                message += ` (${result.response_time_ms}ms)`;
            }
            showKitTestResult(message, 'success');
        } else {
            showKitTestResult(`Connection failed: ${result.message}`, 'error');
        }
    } catch (error) {
        showKitTestResult(`Test failed: ${error.message}`, 'error');
    }
}

async function addNewKit() {
    const apiUrl = document.getElementById('new-kit-url').value.trim();
    const name = document.getElementById('new-kit-name').value.trim();
    const location = document.getElementById('new-kit-location').value.trim();

    if (!apiUrl) {
        showKitTestResult('Please enter an API URL', 'error');
        return;
    }

    showKitTestResult('Adding kit...', 'loading');

    try {
        const response = await fetch('/api/admin/kits', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                api_url: apiUrl,
                name: name || null,
                location: location || null,
                enabled: true
            })
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showKitTestResult(`Kit added successfully! ID: ${result.kit_id}`, 'success');
            // Clear form
            document.getElementById('new-kit-url').value = '';
            document.getElementById('new-kit-name').value = '';
            document.getElementById('new-kit-location').value = '';
            // Reload kit list
            loadKitList();
            // Refresh main kits display
            fetchKits();
        } else {
            showKitTestResult(`Failed to add kit: ${result.detail || result.message || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showKitTestResult(`Failed to add kit: ${error.message}`, 'error');
    }
}

async function loadKitList() {
    const listEl = document.getElementById('kit-list');
    listEl.innerHTML = '<div class="loading">Loading kits...</div>';

    try {
        // Add timeout to prevent hanging indefinitely
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

        const response = await fetch('/api/kits', { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.kits || data.kits.length === 0) {
            listEl.innerHTML = `
                <div class="kit-list-empty">
                    <span style="font-size: 48px;">📡</span>
                    <p>No kits configured yet. Add your first WarDragon kit above.</p>
                </div>
            `;
            return;
        }

        listEl.innerHTML = '';
        data.kits.forEach(kit => {
            const card = createKitCard(kit);
            listEl.appendChild(card);
        });

    } catch (error) {
        let errorMsg = error.message;
        if (error.name === 'AbortError') {
            errorMsg = 'Request timed out - database may be unavailable';
        }
        listEl.innerHTML = `
            <div class="kit-list-empty" style="color: #ff4444;">
                <p>Failed to load kits: ${errorMsg}</p>
                <button class="btn btn-secondary" onclick="loadKitList()" style="margin-top: 10px;">Retry</button>
            </div>
        `;
    }
}

function createKitCard(kit) {
    const card = document.createElement('div');
    card.className = `kit-card ${kit.status || 'unknown'}`;

    const lastSeen = kit.last_seen ? formatTime(kit.last_seen) : 'Never';

    // Source type indicator
    const source = kit.source || 'http';
    let sourceIcon, sourceLabel;
    switch (source) {
        case 'mqtt':
            sourceIcon = '📡';
            sourceLabel = 'MQTT Push';
            break;
        case 'both':
            sourceIcon = '🔄';
            sourceLabel = 'HTTP + MQTT';
            break;
        default:
            sourceIcon = '🌐';
            sourceLabel = 'HTTP Poll';
    }

    // For MQTT-only kits, URL may be null
    const urlDisplay = kit.api_url ? kit.api_url : '<em>MQTT only</em>';
    const showTestBtn = kit.api_url && kit.source !== 'mqtt'; // Only show test for HTTP kits

    card.innerHTML = `
        <div class="kit-info">
            <h4>
                ${kit.name || kit.kit_id}
                <span class="status-badge ${kit.status || 'unknown'}">${kit.status || 'unknown'}</span>
                <span class="source-badge source-${source}" title="${sourceLabel}">${sourceIcon} ${source.toUpperCase()}</span>
            </h4>
            <div class="kit-details">
                <span><strong>ID:</strong> ${kit.kit_id}</span>
                <span><strong>URL:</strong> ${urlDisplay}</span>
                ${kit.location ? `<span><strong>Location:</strong> ${kit.location}</span>` : ''}
                <span><strong>Last Seen:</strong> ${lastSeen}</span>
            </div>
        </div>
        <div class="kit-actions">
            ${showTestBtn ? `<button class="btn-test" onclick="testExistingKit('${kit.kit_id}')">Test</button>` : ''}
            <button class="btn-delete" onclick="deleteKit('${kit.kit_id}', '${kit.name || kit.kit_id}')">Delete</button>
        </div>
    `;

    return card;
}

async function testExistingKit(kitId) {
    try {
        const response = await fetch(`/api/admin/kits/${encodeURIComponent(kitId)}/test`, {
            method: 'POST'
        });
        const result = await response.json();

        if (result.success) {
            alert(`Connection to ${kitId} successful! (${result.response_time_ms}ms)`);
        } else {
            alert(`Connection to ${kitId} failed: ${result.message}`);
        }
    } catch (error) {
        alert(`Test failed: ${error.message}`);
    }
}

async function deleteKit(kitId, kitName) {
    if (!confirm(`Are you sure you want to delete kit "${kitName}"?\n\nThis will stop collecting data from this kit. Historical data will be preserved.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/admin/kits/${encodeURIComponent(kitId)}`, {
            method: 'DELETE'
        });
        const result = await response.json();

        if (response.ok && result.success) {
            alert(`Kit "${kitName}" deleted successfully.`);
            loadKitList();
            fetchKits();
        } else {
            alert(`Failed to delete kit: ${result.detail || result.message || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`Failed to delete kit: ${error.message}`);
    }
}


// =============================================================================
// AI Assistant Chat Functions
// =============================================================================

let aiSessionId = null;
let aiChatOpen = false;

// Toggle AI chat panel visibility
function toggleAIChat() {
    const panel = document.getElementById('ai-chat-panel');
    const btn = document.getElementById('ai-chat-btn');

    aiChatOpen = !aiChatOpen;

    if (aiChatOpen) {
        panel.classList.add('open');
        if (btn) btn.classList.add('active');
        // Check AI status when opening
        checkAIStatus();
        // Focus the input
        setTimeout(() => {
            const input = document.getElementById('ai-input');
            if (input && !input.disabled) input.focus();
        }, 300);
    } else {
        panel.classList.remove('open');
        if (btn) btn.classList.remove('active');
    }
}

// Check if AI/Ollama is available
async function checkAIStatus() {
    const statusEl = document.getElementById('ai-status');
    const statusTextEl = document.getElementById('ai-status-text');
    const modelEl = document.getElementById('ai-model-info');
    const inputEl = document.getElementById('ai-input');
    const sendBtn = document.getElementById('ai-send-btn');

    statusEl.className = 'ai-chat-status checking';
    statusTextEl.textContent = 'Checking...';

    try {
        const response = await fetch('/api/llm/status');
        const data = await response.json();

        if (data.available) {
            statusEl.className = 'ai-chat-status online';
            statusTextEl.textContent = 'Online';
            modelEl.textContent = `Model: ${data.model || 'Unknown'}`;
            inputEl.disabled = false;
            sendBtn.disabled = false;
            inputEl.placeholder = 'Ask about your drone data...';
        } else {
            statusEl.className = 'ai-chat-status offline';
            statusTextEl.textContent = 'Offline';
            modelEl.textContent = data.message || 'Ollama not available';
            inputEl.disabled = true;
            sendBtn.disabled = true;
            inputEl.placeholder = 'AI assistant unavailable - check Ollama';
        }
    } catch (error) {
        console.error('Failed to check AI status:', error);
        statusEl.className = 'ai-chat-status offline';
        statusTextEl.textContent = 'Error';
        modelEl.textContent = 'Connection failed';
        inputEl.disabled = true;
        sendBtn.disabled = true;
        inputEl.placeholder = 'AI assistant unavailable';
    }
}

// Send AI query from a quick button
async function sendAIQuery(question) {
    const messagesContainer = document.getElementById('ai-messages');

    // Add user message to chat
    addAIChatMessage(question, 'user');

    // Show loading indicator
    const loadingId = addAILoadingMessage();

    try {
        const response = await fetch('/api/llm/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: question,
                session_id: aiSessionId
            })
        });

        const data = await response.json();

        // Remove loading indicator
        removeAILoadingMessage(loadingId);

        if (data.success) {
            // Store session ID for conversation context
            if (data.session_id) {
                aiSessionId = data.session_id;
            }

            // Add assistant response
            addAIChatMessage(data.response, 'assistant', data.results, data.query_executed);
        } else {
            addAIChatMessage(`Sorry, I couldn't process that request: ${data.error || 'Unknown error'}`, 'assistant', null, null, true);
        }
    } catch (error) {
        removeAILoadingMessage(loadingId);
        console.error('AI query failed:', error);
        addAIChatMessage('Sorry, there was an error connecting to the AI assistant. Please check that Ollama is running.', 'assistant', null, null, true);
    }

    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Send AI query from the input field
function sendAIQueryFromInput() {
    const inputEl = document.getElementById('ai-input');
    const question = inputEl.value.trim();

    if (question) {
        inputEl.value = '';
        sendAIQuery(question);
    }
}

// Handle keydown in AI input (Enter to send)
function handleAIInputKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendAIQueryFromInput();
    }
}

// Add a message to the AI chat
function addAIChatMessage(text, role, results = null, queryExecuted = null, isError = false) {
    const messagesContainer = document.getElementById('ai-messages');

    const messageEl = document.createElement('div');
    // Use CSS class pattern: ai-message ai-message-{role}
    const roleClass = role === 'user' ? 'ai-message-user' : 'ai-message-assistant';
    messageEl.className = `ai-message ${roleClass}${isError ? ' ai-message-error' : ''}`;

    let content = `<div class="ai-message-content">${escapeHtml(text)}`;

    // Add query info if available (for transparency)
    if (queryExecuted && role === 'assistant') {
        content += `<div class="ai-query-info" title="SQL query executed">
            <span class="ai-query-toggle" onclick="toggleQueryDetails(this)">Show query</span>
            <pre class="ai-query-details" style="display: none;">${escapeHtml(queryExecuted)}</pre>
        </div>`;
    }

    // Add results table if available
    if (results && results.length > 0) {
        content += formatAIResults(results);
    }

    content += '</div>';
    messageEl.innerHTML = content;

    messagesContainer.appendChild(messageEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Add loading message
function addAILoadingMessage() {
    const messagesContainer = document.getElementById('ai-messages');
    const loadingId = 'ai-loading-' + Date.now();

    const loadingEl = document.createElement('div');
    loadingEl.id = loadingId;
    loadingEl.className = 'ai-message ai-message-assistant';
    loadingEl.innerHTML = `
        <div class="ai-message-content">
            <div class="ai-message-loading">
                <span></span><span></span><span></span>
            </div>
            <span style="margin-left: 8px;">Analyzing your data...</span>
        </div>
    `;

    messagesContainer.appendChild(loadingEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    return loadingId;
}

// Remove loading message
function removeAILoadingMessage(loadingId) {
    const loadingEl = document.getElementById(loadingId);
    if (loadingEl) {
        loadingEl.remove();
    }
}

// Format AI results as a table
function formatAIResults(results) {
    if (!results || results.length === 0) return '';

    // Get columns from first result
    const columns = Object.keys(results[0]);

    let html = '<div class="ai-results-table-wrapper"><table class="ai-results-table"><thead><tr>';

    // Header row
    columns.forEach(col => {
        html += `<th>${escapeHtml(formatColumnName(col))}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Data rows (limit to 20 for display)
    const displayResults = results.slice(0, 20);
    displayResults.forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
            const value = row[col];
            html += `<td>${formatCellValue(value, col)}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table></div>';

    // Show count if more results
    if (results.length > 20) {
        html += `<div class="ai-results-more">Showing 20 of ${results.length} results</div>`;
    }

    return html;
}

// Format column name for display
function formatColumnName(col) {
    return col
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

// Format cell value based on column type
function formatCellValue(value, column) {
    if (value === null || value === undefined) {
        return '<span class="null-value">-</span>';
    }

    // Format timestamps
    if (column.includes('time') || column.includes('date') || column.includes('seen')) {
        try {
            const date = new Date(value);
            if (!isNaN(date.getTime())) {
                return date.toLocaleString();
            }
        } catch (e) {}
    }

    // Format numbers
    if (typeof value === 'number') {
        // Coordinates
        if (column === 'lat' || column === 'lon' || column.includes('_lat') || column.includes('_lon')) {
            return value.toFixed(6);
        }
        // Altitude, speed
        if (column === 'alt' || column === 'speed' || column === 'height') {
            return value.toFixed(1);
        }
        // Counts and integers
        if (Number.isInteger(value)) {
            return value.toLocaleString();
        }
        // Other floats
        return value.toFixed(2);
    }

    return escapeHtml(String(value));
}

// Toggle query details visibility
function toggleQueryDetails(toggleEl) {
    const detailsEl = toggleEl.nextElementSibling;
    if (detailsEl.style.display === 'none') {
        detailsEl.style.display = 'block';
        toggleEl.textContent = 'Hide query';
    } else {
        detailsEl.style.display = 'none';
        toggleEl.textContent = 'Show query';
    }
}

// Clear AI chat conversation
function clearAIChat() {
    const messagesContainer = document.getElementById('ai-messages');

    // Clear session on server if we have one
    if (aiSessionId) {
        fetch(`/api/llm/session/${aiSessionId}`, { method: 'DELETE' })
            .catch(err => console.warn('Failed to clear session:', err));
    }

    // Generate new session ID
    aiSessionId = 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

    // Reset to welcome message (matching the HTML structure)
    messagesContainer.innerHTML = `
        <div class="ai-message ai-message-assistant">
            <div class="ai-message-content">
                <p><strong>Welcome!</strong> I can help you explore your drone detection data.</p>
                <p>Try asking questions like:</p>
                <ul>
                    <li>"What drones were seen in the last hour?"</li>
                    <li>"Show me DJI drones above 100 meters"</li>
                    <li>"How many unique drones today?"</li>
                    <li>"Any FPV signals detected?"</li>
                </ul>
            </div>
        </div>
    `;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize AI chat on page load
function initAIChat() {
    // Generate a session ID
    aiSessionId = 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

    // Check status periodically (every 30 seconds)
    setInterval(() => {
        if (aiChatOpen) {
            checkAIStatus();
        }
    }, 30000);
}
