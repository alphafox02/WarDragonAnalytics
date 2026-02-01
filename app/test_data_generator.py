#!/usr/bin/env python3
"""
Test Data Generator for WarDragon Analytics

Generates realistic fake drone tracks, FPV signals, and system health data
for testing the Analytics UI and database.

Usage:
    python app/test_data_generator.py --mode=db --duration=2h --kits=3 --drones=15
    python app/test_data_generator.py --mode=sql --duration=1h --kits=1 --drones=5
"""

import argparse
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple
import math

# Database imports (optional, only needed for --mode=db)
try:
    import psycopg2
    from psycopg2.extras import execute_batch
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("Warning: psycopg2 not installed. Use --mode=sql or install: pip install psycopg2-binary", file=sys.stderr)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Realistic drone makes and models (DJI, Autel, etc.)
DRONE_MAKES_MODELS = [
    ("DJI", "Mini 3 Pro"),
    ("DJI", "Air 3"),
    ("DJI", "Mavic 3"),
    ("DJI", "Mavic 3 Pro"),
    ("DJI", "Inspire 3"),
    ("DJI", "Phantom 4 Pro"),
    ("DJI", "Matrice 30"),
    ("DJI", "Avata 2"),
    ("Autel", "EVO II Pro"),
    ("Autel", "EVO Nano+"),
    ("Autel", "EVO Lite+"),
    ("Skydio", "X2"),
    ("Parrot", "ANAFI USA"),
    ("DJI", "FPV"),
]

# FPV frequency bands (5.8 GHz analog + DJI)
FPV_FREQUENCIES = {
    "analog": [
        5740, 5760, 5780, 5800, 5820, 5840, 5860, 5880,  # Band A
        5733, 5752, 5771, 5790, 5809, 5828, 5847, 5866,  # Band B
        5705, 5685, 5665, 5645, 5885, 5905, 5925, 5945,  # Band E
        5658, 5695, 5732, 5769, 5806, 5843, 5880, 5917,  # Band F
        5362, 5399, 5436, 5473, 5510, 5547, 5584, 5621,  # Band R
    ],
    "dji": [5725, 5760, 5795, 5830, 5865],  # DJI Digital FPV
}

# UA types (Remote ID)
UA_TYPES = {
    1: "Aeroplane",
    2: "Helicopter/Multirotor",
    3: "Gyroplane",
    4: "VTOL",
    6: "Glider",
}

# Kit locations (example GPS coordinates) - spread across US
# Used when --clustered is NOT set
KIT_BASE_LOCATIONS_SPREAD = [
    (37.7749, -122.4194, "San Francisco, CA"),    # SF
    (34.0522, -118.2437, "Los Angeles, CA"),      # LA
    (40.7128, -74.0060, "New York, NY"),          # NYC
    (41.8781, -87.6298, "Chicago, IL"),           # Chicago
    (29.7604, -95.3698, "Houston, TX"),           # Houston
    (33.4484, -112.0740, "Phoenix, AZ"),          # Phoenix
    (39.7392, -104.9903, "Denver, CO"),           # Denver
    (47.6062, -122.3321, "Seattle, WA"),          # Seattle
]

# Clustered kit locations - all within ~5km of each other
# Used for multi-kit detection testing (same drone seen by multiple kits)
KIT_BASE_LOCATIONS_CLUSTERED = [
    (37.7749, -122.4194, "Site Alpha"),     # Center point
    (37.7820, -122.4100, "Site Bravo"),     # ~1km NE
    (37.7680, -122.4280, "Site Charlie"),   # ~1km SW
    (37.7800, -122.4300, "Site Delta"),     # ~1km NW
    (37.7700, -122.4100, "Site Echo"),      # ~1km SE
]

# Default to spread locations (backwards compatible)
KIT_BASE_LOCATIONS = KIT_BASE_LOCATIONS_SPREAD


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def random_walk_gps(center_lat: float, center_lon: float, max_distance_km: float = 2.0) -> Tuple[float, float]:
    """
    Generate a random GPS coordinate within max_distance_km of center point.
    Returns (lat, lon).
    """
    # Convert km to degrees (rough approximation)
    lat_offset = (random.random() - 0.5) * 2 * (max_distance_km / 111.0)
    lon_offset = (random.random() - 0.5) * 2 * (max_distance_km / (111.0 * math.cos(math.radians(center_lat))))
    return (center_lat + lat_offset, center_lon + lon_offset)


def generate_mac() -> str:
    """Generate a random MAC address."""
    return ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])


def generate_drone_id() -> str:
    """Generate a realistic drone serial number."""
    prefix = random.choice(["DJI", "AUT", "SKY", "PAR"])
    return f"{prefix}{random.randint(100000, 999999)}"


def generate_operator_id() -> str:
    """Generate a realistic operator ID (FAA format)."""
    return f"FAA{random.randint(1000000000000, 9999999999999)}"


def interpolate_position(start: Tuple[float, float], end: Tuple[float, float], fraction: float) -> Tuple[float, float]:
    """Linear interpolation between two GPS points."""
    lat = start[0] + (end[0] - start[0]) * fraction
    lon = start[1] + (end[1] - start[1]) * fraction
    return (lat, lon)


def calculate_heading(start: Tuple[float, float], end: Tuple[float, float]) -> float:
    """Calculate heading (degrees) from start to end point."""
    lat1, lon1 = math.radians(start[0]), math.radians(start[1])
    lat2, lon2 = math.radians(end[0]), math.radians(end[1])

    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)

    heading = math.degrees(math.atan2(x, y))
    return (heading + 360) % 360


# ============================================================================
# DATA GENERATORS
# ============================================================================

class DroneTrack:
    """Represents a simulated drone track over time."""

    def __init__(self, kit_id: str, kit_location: Tuple[float, float], start_time: datetime):
        self.kit_id = kit_id
        self.drone_id = generate_drone_id()
        self.mac = generate_mac()
        self.operator_id = generate_operator_id()
        self.make, self.model = random.choice(DRONE_MAKES_MODELS)
        self.ua_type = random.choice(list(UA_TYPES.keys()))

        # Flight parameters
        self.start_time = start_time
        self.duration_minutes = random.randint(5, 45)
        self.end_time = start_time + timedelta(minutes=self.duration_minutes)

        # Initial position (within 5km of kit)
        self.pilot_lat, self.pilot_lon = random_walk_gps(kit_location[0], kit_location[1], 5.0)
        self.home_lat, self.home_lon = self.pilot_lat, self.pilot_lon

        # Flight characteristics (must be set before _generate_waypoints)
        self.max_speed = random.uniform(5, 20)  # m/s
        self.max_altitude = random.uniform(30, 120)  # meters

        # Generate flight waypoints
        self.waypoints = self._generate_waypoints(kit_location)
        self.current_waypoint_idx = 0

    def _generate_waypoints(self, kit_location: Tuple[float, float]) -> List[Tuple[float, float, float]]:
        """Generate 3-8 waypoints for the drone flight.

        First waypoint starts at home/pilot location (takeoff).
        Last waypoint returns near home location (landing).
        """
        num_waypoints = random.randint(3, 8)
        waypoints = []

        # First waypoint: start at home/pilot location (takeoff)
        takeoff_alt = random.uniform(5, 20)  # Low altitude at takeoff
        waypoints.append((self.home_lat, self.home_lon, takeoff_alt))

        # Middle waypoints: random positions within 2km of kit
        for _ in range(num_waypoints - 2):
            lat, lon = random_walk_gps(kit_location[0], kit_location[1], 2.0)
            alt = random.uniform(20, self.max_altitude)
            waypoints.append((lat, lon, alt))

        # Last waypoint: return near home (landing approach)
        # Add small offset for realism
        land_lat, land_lon = random_walk_gps(self.home_lat, self.home_lon, 0.05)
        land_alt = random.uniform(5, 15)
        waypoints.append((land_lat, land_lon, land_alt))

        return waypoints

    def get_position_at_time(self, current_time: datetime) -> Dict[str, Any]:
        """Get drone position and telemetry at specific time."""
        if current_time < self.start_time or current_time > self.end_time:
            return None

        # Calculate progress through flight (0.0 to 1.0)
        total_seconds = (self.end_time - self.start_time).total_seconds()
        elapsed_seconds = (current_time - self.start_time).total_seconds()
        progress = elapsed_seconds / total_seconds

        # Determine current waypoint
        waypoint_progress = progress * len(self.waypoints)
        current_wp_idx = min(int(waypoint_progress), len(self.waypoints) - 2)
        wp_fraction = waypoint_progress - current_wp_idx

        # Interpolate between waypoints
        start_wp = self.waypoints[current_wp_idx]
        end_wp = self.waypoints[current_wp_idx + 1]

        lat, lon = interpolate_position(
            (start_wp[0], start_wp[1]),
            (end_wp[0], end_wp[1]),
            wp_fraction
        )
        alt = start_wp[2] + (end_wp[2] - start_wp[2]) * wp_fraction

        # Calculate heading
        heading = calculate_heading((start_wp[0], start_wp[1]), (end_wp[0], end_wp[1]))

        # Add some noise to speed and altitude
        speed = self.max_speed * (0.5 + random.random() * 0.5)
        vspeed = random.uniform(-2, 2)

        return {
            "time": current_time,
            "kit_id": self.kit_id,
            "drone_id": self.drone_id,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "alt": round(alt, 1),
            "speed": round(speed, 1),
            "heading": round(heading, 1),
            "vspeed": round(vspeed, 1),
            "pilot_lat": round(self.pilot_lat, 6),
            "pilot_lon": round(self.pilot_lon, 6),
            "home_lat": round(self.home_lat, 6),
            "home_lon": round(self.home_lon, 6),
            "mac": self.mac,
            "rssi": random.randint(-90, -40),
            "freq": round(random.choice([2400.0, 2450.0, 5800.0]), 1),
            "ua_type": UA_TYPES[self.ua_type],
            "operator_id": self.operator_id,
            "caa_id": "",
            "rid_make": self.make,
            "rid_model": self.model,
            "rid_source": random.choice(["wifi", "ble", "dji"]),
            "track_type": "drone",
        }


class FPVSignalGenerator:
    """Generates FPV signal detections."""

    def __init__(self, kit_id: str, kit_location: Tuple[float, float]):
        self.kit_id = kit_id
        self.kit_lat, self.kit_lon, self.kit_alt = kit_location[0], kit_location[1], random.uniform(5, 50)

    def generate_signal(self, current_time: datetime) -> Dict[str, Any]:
        """Generate a random FPV signal detection."""
        # Randomly choose analog or DJI
        signal_type = random.choice(["analog", "dji"])
        freq_mhz = random.choice(FPV_FREQUENCIES[signal_type])

        return {
            "time": current_time,
            "kit_id": self.kit_id,
            "freq_mhz": round(freq_mhz, 1),
            "power_dbm": round(random.uniform(-85, -45), 1),
            "bandwidth_mhz": 20.0 if signal_type == "dji" else 8.0,
            "lat": round(self.kit_lat, 6),
            "lon": round(self.kit_lon, 6),
            "alt": round(self.kit_alt, 1),
            "detection_type": signal_type,
        }


class SystemHealthGenerator:
    """Generates system health data for a kit."""

    def __init__(self, kit_id: str, kit_location: Tuple[float, float]):
        self.kit_id = kit_id
        self.kit_lat, self.kit_lon = kit_location[0], kit_location[1]
        self.kit_alt = random.uniform(5, 50)
        self.start_time = None

        # Baseline values
        self.base_cpu = random.uniform(20, 40)
        self.base_memory = random.uniform(40, 60)
        self.base_disk = random.uniform(30, 50)
        self.base_temp_cpu = random.uniform(45, 55)
        self.base_temp_gpu = random.uniform(40, 50)

    def generate_health(self, current_time: datetime) -> Dict[str, Any]:
        """Generate system health snapshot."""
        if self.start_time is None:
            self.start_time = current_time

        uptime_hours = (current_time - self.start_time).total_seconds() / 3600.0

        # Add some realistic variation
        cpu = self.base_cpu + random.uniform(-10, 20)
        memory = self.base_memory + random.uniform(-5, 10)
        disk = self.base_disk + random.uniform(0, 2)
        temp_cpu = self.base_temp_cpu + random.uniform(-5, 15)
        temp_gpu = self.base_temp_gpu + random.uniform(-5, 10)

        # GPS jitter (simulate stationary kit with GPS drift)
        lat = self.kit_lat + random.uniform(-0.00001, 0.00001)
        lon = self.kit_lon + random.uniform(-0.00001, 0.00001)

        return {
            "time": current_time,
            "kit_id": self.kit_id,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "alt": round(self.kit_alt, 1),
            "cpu_percent": round(min(100, max(0, cpu)), 1),
            "memory_percent": round(min(100, max(0, memory)), 1),
            "disk_percent": round(min(100, max(0, disk)), 1),
            "uptime_hours": round(uptime_hours, 2),
            "temp_cpu": round(temp_cpu, 1),
            "temp_gpu": round(temp_gpu, 1),
        }


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def get_db_connection(db_url: str):
    """Create database connection."""
    if not DB_AVAILABLE:
        raise RuntimeError("psycopg2 not available. Install with: pip install psycopg2-binary")

    return psycopg2.connect(db_url)


def insert_drones_batch(conn, drones: List[Dict[str, Any]]) -> int:
    """Batch insert drone records."""
    if not drones:
        return 0

    query = """
        INSERT INTO drones (
            time, kit_id, drone_id, lat, lon, alt, speed, heading,
            pilot_lat, pilot_lon, home_lat, home_lon, mac, rssi, freq,
            ua_type, operator_id, caa_id, rid_make, rid_model, rid_source, track_type
        ) VALUES (
            %(time)s, %(kit_id)s, %(drone_id)s, %(lat)s, %(lon)s, %(alt)s, %(speed)s, %(heading)s,
            %(pilot_lat)s, %(pilot_lon)s, %(home_lat)s, %(home_lon)s, %(mac)s, %(rssi)s, %(freq)s,
            %(ua_type)s, %(operator_id)s, %(caa_id)s, %(rid_make)s, %(rid_model)s, %(rid_source)s, %(track_type)s
        )
        ON CONFLICT (time, kit_id, drone_id) DO NOTHING
    """

    with conn.cursor() as cur:
        execute_batch(cur, query, drones, page_size=1000)
    conn.commit()
    return len(drones)


def insert_signals_batch(conn, signals: List[Dict[str, Any]]) -> int:
    """Batch insert signal records."""
    if not signals:
        return 0

    query = """
        INSERT INTO signals (
            time, kit_id, freq_mhz, power_dbm, bandwidth_mhz,
            lat, lon, alt, detection_type
        ) VALUES (
            %(time)s, %(kit_id)s, %(freq_mhz)s, %(power_dbm)s, %(bandwidth_mhz)s,
            %(lat)s, %(lon)s, %(alt)s, %(detection_type)s
        )
        ON CONFLICT (time, kit_id, freq_mhz) DO NOTHING
    """

    with conn.cursor() as cur:
        execute_batch(cur, query, signals, page_size=1000)
    conn.commit()
    return len(signals)


def insert_health_batch(conn, health_records: List[Dict[str, Any]]) -> int:
    """Batch insert system health records."""
    if not health_records:
        return 0

    query = """
        INSERT INTO system_health (
            time, kit_id, lat, lon, alt, cpu_percent, memory_percent,
            disk_percent, uptime_hours, temp_cpu, temp_gpu
        ) VALUES (
            %(time)s, %(kit_id)s, %(lat)s, %(lon)s, %(alt)s, %(cpu_percent)s, %(memory_percent)s,
            %(disk_percent)s, %(uptime_hours)s, %(temp_cpu)s, %(temp_gpu)s
        )
        ON CONFLICT (time, kit_id) DO NOTHING
    """

    with conn.cursor() as cur:
        execute_batch(cur, query, health_records, page_size=1000)
    conn.commit()
    return len(health_records)


def upsert_kits(conn, kits: List[Dict[str, Any]]) -> int:
    """Insert or update kit records."""
    if not kits:
        return 0

    query = """
        INSERT INTO kits (kit_id, name, location, api_url, last_seen, status, created_at)
        VALUES (%(kit_id)s, %(name)s, %(location)s, %(api_url)s, %(last_seen)s, %(status)s, %(created_at)s)
        ON CONFLICT (kit_id) DO UPDATE SET
            last_seen = EXCLUDED.last_seen,
            status = EXCLUDED.status
    """

    with conn.cursor() as cur:
        execute_batch(cur, query, kits, page_size=100)
    conn.commit()
    return len(kits)


# ============================================================================
# SQL GENERATION
# ============================================================================

def generate_drone_insert_sql(drone: Dict[str, Any]) -> str:
    """Generate SQL INSERT statement for a drone record."""
    return f"""INSERT INTO drones (time, kit_id, drone_id, lat, lon, alt, speed, heading, pilot_lat, pilot_lon, home_lat, home_lon, mac, rssi, freq, ua_type, operator_id, caa_id, rid_make, rid_model, rid_source, track_type)
VALUES ('{drone['time'].isoformat()}', '{drone['kit_id']}', '{drone['drone_id']}', {drone['lat']}, {drone['lon']}, {drone['alt']}, {drone['speed']}, {drone['heading']}, {drone['pilot_lat']}, {drone['pilot_lon']}, {drone['home_lat']}, {drone['home_lon']}, '{drone['mac']}', {drone['rssi']}, {drone['freq']}, '{drone['ua_type']}', '{drone['operator_id']}', '{drone['caa_id']}', '{drone['rid_make']}', '{drone['rid_model']}', '{drone['rid_source']}', '{drone['track_type']}')
ON CONFLICT (time, kit_id, drone_id) DO NOTHING;"""


def generate_signal_insert_sql(signal: Dict[str, Any]) -> str:
    """Generate SQL INSERT statement for a signal record."""
    return f"""INSERT INTO signals (time, kit_id, freq_mhz, power_dbm, bandwidth_mhz, lat, lon, alt, detection_type)
VALUES ('{signal['time'].isoformat()}', '{signal['kit_id']}', {signal['freq_mhz']}, {signal['power_dbm']}, {signal['bandwidth_mhz']}, {signal['lat']}, {signal['lon']}, {signal['alt']}, '{signal['detection_type']}')
ON CONFLICT (time, kit_id, freq_mhz) DO NOTHING;"""


def generate_health_insert_sql(health: Dict[str, Any]) -> str:
    """Generate SQL INSERT statement for a health record."""
    return f"""INSERT INTO system_health (time, kit_id, lat, lon, alt, cpu_percent, memory_percent, disk_percent, uptime_hours, temp_cpu, temp_gpu)
VALUES ('{health['time'].isoformat()}', '{health['kit_id']}', {health['lat']}, {health['lon']}, {health['alt']}, {health['cpu_percent']}, {health['memory_percent']}, {health['disk_percent']}, {health['uptime_hours']}, {health['temp_cpu']}, {health['temp_gpu']})
ON CONFLICT (time, kit_id) DO NOTHING;"""


def generate_kit_insert_sql(kit: Dict[str, Any]) -> str:
    """Generate SQL INSERT statement for a kit record."""
    return f"""INSERT INTO kits (kit_id, name, location, api_url, last_seen, status, created_at)
VALUES ('{kit['kit_id']}', '{kit['name']}', '{kit['location']}', '{kit['api_url']}', '{kit['last_seen'].isoformat()}', '{kit['status']}', '{kit['created_at'].isoformat()}')
ON CONFLICT (kit_id) DO UPDATE SET last_seen = EXCLUDED.last_seen, status = EXCLUDED.status;"""


# ============================================================================
# MAIN SIMULATION
# ============================================================================

def parse_duration(duration_str: str) -> timedelta:
    """Parse duration string like '2h', '30m', '1h30m' to timedelta."""
    total_minutes = 0

    if 'h' in duration_str:
        parts = duration_str.split('h')
        total_minutes += int(parts[0]) * 60
        duration_str = parts[1] if len(parts) > 1 else ""

    if 'm' in duration_str:
        total_minutes += int(duration_str.replace('m', ''))

    return timedelta(minutes=total_minutes)


def generate_test_data(
    num_kits: int = 3,
    drones_per_kit: int = 15,
    duration: timedelta = timedelta(hours=2),
    output_mode: str = "sql",
    db_url: str = None,
    signal_probability: float = 0.3,
    multi_kit_probability: float = 0.3,
    clustered: bool = None,
) -> Dict[str, int]:
    """
    Generate test data for WarDragon Analytics.

    Args:
        num_kits: Number of kits to simulate
        drones_per_kit: Average number of drones per kit
        duration: Time period to simulate (back from now)
        output_mode: 'sql' (print SQL) or 'db' (write to database)
        db_url: Database URL (required for db mode)
        signal_probability: Probability of FPV signal detection per interval
        multi_kit_probability: Probability of a drone being seen by multiple kits (for RSSI triangulation testing)
        clustered: If True, place kits close together (~1km apart) for multi-kit testing.
                   If None (default), auto-enable when multi_kit_probability > 0

    Returns:
        Dict with counts of generated records
    """
    stats = {
        "kits": 0,
        "drones": 0,
        "signals": 0,
        "health": 0,
        "multi_kit_drones": 0,
    }

    # Database connection (if needed)
    conn = None
    if output_mode == "db":
        if not db_url:
            raise ValueError("Database URL required for --mode=db")
        conn = get_db_connection(db_url)
        print(f"Connected to database: {db_url.split('@')[1] if '@' in db_url else db_url}")

    # Time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - duration

    # Determine if we should use clustered kit locations
    # Auto-enable clustering when multi-kit testing is requested
    use_clustered = clustered if clustered is not None else (multi_kit_probability > 0)
    kit_locations = KIT_BASE_LOCATIONS_CLUSTERED if use_clustered else KIT_BASE_LOCATIONS_SPREAD

    print(f"\nGenerating test data:")
    print(f"  Time range: {start_time.isoformat()} to {end_time.isoformat()}")
    print(f"  Duration: {duration}")
    print(f"  Kits: {num_kits}")
    print(f"  Kit placement: {'CLUSTERED (~1km apart)' if use_clustered else 'SPREAD (different cities)'}")
    print(f"  Drones per kit: ~{drones_per_kit}")
    print(f"  Output mode: {output_mode}\n")

    # Generate kits
    kits = []
    kit_data = []

    for i in range(num_kits):
        kit_id = f"kit-{i+1:03d}"
        location_info = kit_locations[i % len(kit_locations)]

        kit = {
            "kit_id": kit_id,
            "name": f"Test Kit {i+1}",
            "location": location_info[2],
            "api_url": f"http://192.168.1.{100+i}:8088",
            "last_seen": end_time,
            "status": "online",
            "created_at": start_time,
        }
        kits.append(kit)
        kit_data.append({
            "kit_id": kit_id,
            "location": (location_info[0], location_info[1]),
        })
        stats["kits"] += 1

    # Insert/print kits
    if output_mode == "db":
        upsert_kits(conn, kits)
        print(f"✓ Inserted {stats['kits']} kits")
    else:
        print("-- Kits")
        for kit in kits:
            print(generate_kit_insert_sql(kit))
        print()

    # Generate drone tracks
    all_drone_tracks = []
    # Shared drones for multi-kit detection (same drone seen by multiple kits)
    shared_drone_tracks = []  # List of (base_track, [kit_ids])

    for kit in kit_data:
        num_drones = random.randint(int(drones_per_kit * 0.7), int(drones_per_kit * 1.3))

        for _ in range(num_drones):
            # Random start time within the duration
            flight_start = start_time + timedelta(
                seconds=random.randint(0, int(duration.total_seconds() * 0.8))
            )

            track = DroneTrack(kit["kit_id"], kit["location"], flight_start)
            all_drone_tracks.append(track)

    # Create multi-kit shared drones (for RSSI triangulation and spoofing detection testing)
    # These drones fly in overlapping coverage areas and are seen by 2+ kits
    if num_kits >= 2 and multi_kit_probability > 0:
        num_shared_drones = max(1, int(drones_per_kit * multi_kit_probability))
        print(f"Creating {num_shared_drones} shared drones for multi-kit detection testing...")

        for i in range(num_shared_drones):
            # Pick 2-3 kits that will see this drone
            num_observing_kits = random.randint(2, min(3, num_kits))
            observing_kits = random.sample(kit_data, num_observing_kits)

            # Create the base drone track (using first kit's location as reference)
            flight_start = start_time + timedelta(
                seconds=random.randint(0, int(duration.total_seconds() * 0.6))
            )
            base_track = DroneTrack(observing_kits[0]["kit_id"], observing_kits[0]["location"], flight_start)

            # Store shared drone info
            shared_drone_tracks.append({
                "base_track": base_track,
                "observing_kits": observing_kits,
                "drone_id": base_track.drone_id,
            })
            stats["multi_kit_drones"] += 1

    print(f"Generated {len(all_drone_tracks)} single-kit drone tracks")
    if shared_drone_tracks:
        print(f"Generated {len(shared_drone_tracks)} multi-kit shared drones (for RSSI triangulation testing)")

    # Generate FPV signal generators
    fpv_generators = [
        FPVSignalGenerator(kit["kit_id"], kit["location"])
        for kit in kit_data
    ]

    # Generate health data generators
    health_generators = [
        SystemHealthGenerator(kit["kit_id"], kit["location"])
        for kit in kit_data
    ]

    # Simulate time progression
    current_time = start_time
    interval = timedelta(seconds=5)  # 5-second intervals (matching collector poll rate)
    health_interval = timedelta(seconds=30)  # Health updates every 30s
    last_health_time = start_time

    drone_batch = []
    signal_batch = []
    health_batch = []

    batch_size = 1000

    if output_mode == "sql":
        print("-- Drone tracks")

    iteration = 0
    while current_time <= end_time:
        iteration += 1

        # Generate drone positions (single-kit)
        for track in all_drone_tracks:
            position = track.get_position_at_time(current_time)
            if position:
                drone_batch.append(position)
                stats["drones"] += 1

        # Generate multi-kit shared drone observations
        # Same drone seen by multiple kits with different RSSI values
        for shared in shared_drone_tracks:
            base_track = shared["base_track"]
            position = base_track.get_position_at_time(current_time)
            if position:
                # Create observation from each observing kit
                for kit in shared["observing_kits"]:
                    # Calculate distance-based RSSI (closer kits get stronger signal)
                    kit_lat, kit_lon = kit["location"]
                    drone_lat, drone_lon = position["lat"], position["lon"]

                    # Rough distance calculation (degrees to ~km)
                    dist_km = math.sqrt(
                        (kit_lat - drone_lat)**2 + (kit_lon - drone_lon)**2
                    ) * 111.0  # ~111 km per degree

                    # RSSI decreases with distance (free-space path loss approximation)
                    # Base RSSI at 100m: -50dBm, decreases ~6dB per doubling of distance
                    base_rssi = -50
                    if dist_km > 0.1:
                        rssi = base_rssi - 20 * math.log10(dist_km / 0.1)
                    else:
                        rssi = base_rssi + random.randint(-5, 5)

                    # Clamp to realistic range and add noise
                    rssi = max(-95, min(-35, rssi + random.uniform(-5, 5)))

                    # Create observation record for this kit
                    kit_observation = position.copy()
                    kit_observation["kit_id"] = kit["kit_id"]
                    kit_observation["rssi"] = round(rssi)
                    kit_observation["drone_id"] = shared["drone_id"]  # Same drone ID across kits
                    drone_batch.append(kit_observation)
                    stats["drones"] += 1

        # Generate FPV signals (probabilistically)
        for fpv_gen in fpv_generators:
            if random.random() < signal_probability:
                signal = fpv_gen.generate_signal(current_time)
                signal_batch.append(signal)
                stats["signals"] += 1

        # Generate health data (every 30s)
        if current_time >= last_health_time + health_interval:
            for health_gen in health_generators:
                health = health_gen.generate_health(current_time)
                health_batch.append(health)
                stats["health"] += 1
            last_health_time = current_time

        # Batch insert/print
        if len(drone_batch) >= batch_size or current_time >= end_time:
            if output_mode == "db":
                if drone_batch:
                    insert_drones_batch(conn, drone_batch)
                if signal_batch:
                    insert_signals_batch(conn, signal_batch)
                if health_batch:
                    insert_health_batch(conn, health_batch)

                if iteration % 20 == 0:
                    print(f"  Progress: {current_time.isoformat()} | Drones: {stats['drones']}, Signals: {stats['signals']}, Health: {stats['health']}")
            else:
                for drone in drone_batch:
                    print(generate_drone_insert_sql(drone))
                for signal in signal_batch:
                    print(generate_signal_insert_sql(signal))
                for health in health_batch:
                    print(generate_health_insert_sql(health))

            drone_batch = []
            signal_batch = []
            health_batch = []

        current_time += interval

    # Final batch
    if drone_batch or signal_batch or health_batch:
        if output_mode == "db":
            if drone_batch:
                insert_drones_batch(conn, drone_batch)
            if signal_batch:
                insert_signals_batch(conn, signal_batch)
            if health_batch:
                insert_health_batch(conn, health_batch)
        else:
            for drone in drone_batch:
                print(generate_drone_insert_sql(drone))
            for signal in signal_batch:
                print(generate_signal_insert_sql(signal))
            for health in health_batch:
                print(generate_health_insert_sql(health))

    if conn:
        conn.close()

    return stats


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate test data for WarDragon Analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 2 hours of data for 3 kits, write to database
  python app/test_data_generator.py --mode=db --duration=2h --kits=3 --drones=15

  # Generate 1 hour of SQL statements (for manual import)
  python app/test_data_generator.py --mode=sql --duration=1h --kits=1 --drones=5 > test_data.sql

  # Generate 30 minutes of data with custom database URL
  python app/test_data_generator.py --mode=db --duration=30m --kits=2 --db-url="postgresql://user:pass@localhost:5432/wardragon"
        """
    )

    parser.add_argument(
        "--mode",
        choices=["sql", "db"],
        default="sql",
        help="Output mode: 'sql' (print SQL) or 'db' (write to database)"
    )

    parser.add_argument(
        "--duration",
        type=str,
        default="2h",
        help="Duration of data to generate (e.g., '2h', '30m', '1h30m')"
    )

    parser.add_argument(
        "--kits",
        type=int,
        default=3,
        help="Number of kits to simulate"
    )

    parser.add_argument(
        "--drones",
        type=int,
        default=15,
        help="Average number of drones per kit"
    )

    parser.add_argument(
        "--db-url",
        type=str,
        default="postgresql://wardragon:wardragon@localhost:5432/wardragon",
        help="Database URL (for --mode=db)"
    )

    parser.add_argument(
        "--signal-probability",
        type=float,
        default=0.3,
        help="Probability of FPV signal detection per 5s interval (0.0-1.0)"
    )

    parser.add_argument(
        "--multi-kit-probability",
        type=float,
        default=0.3,
        help="Probability of drones being shared across multiple kits (for RSSI triangulation testing, 0.0-1.0)"
    )

    parser.add_argument(
        "--clustered",
        action="store_true",
        default=None,
        help="Place all kits close together (~1km apart) for realistic multi-kit testing. Auto-enabled when --multi-kit-probability > 0"
    )

    parser.add_argument(
        "--spread",
        action="store_true",
        help="Place kits in different cities (spread across US). Overrides auto-clustering."
    )

    args = parser.parse_args()

    # Parse duration
    duration = parse_duration(args.duration)

    # Validate
    if args.mode == "db" and not DB_AVAILABLE:
        print("Error: psycopg2 not installed. Install with: pip install psycopg2-binary", file=sys.stderr)
        print("Or use --mode=sql to generate SQL statements instead.", file=sys.stderr)
        sys.exit(1)

    # Generate data
    try:
        # Determine clustering: --spread overrides, --clustered forces, otherwise auto
        clustered = None  # Auto-detect based on multi_kit_probability
        if args.spread:
            clustered = False
        elif args.clustered:
            clustered = True

        stats = generate_test_data(
            num_kits=args.kits,
            drones_per_kit=args.drones,
            duration=duration,
            output_mode=args.mode,
            db_url=args.db_url if args.mode == "db" else None,
            signal_probability=args.signal_probability,
            multi_kit_probability=args.multi_kit_probability,
            clustered=clustered,
        )

        print("\n" + "="*60)
        print("GENERATION COMPLETE")
        print("="*60)
        print(f"Kits:                 {stats['kits']}")
        print(f"Drone records:        {stats['drones']}")
        print(f"Multi-kit drones:     {stats['multi_kit_drones']} (same drone seen by 2+ kits)")
        print(f"Signal records:       {stats['signals']}")
        print(f"Health records:       {stats['health']}")
        print(f"Total records:        {stats['drones'] + stats['signals'] + stats['health']}")
        print("="*60)
        if stats['multi_kit_drones'] > 0:
            print("\nMulti-kit drones enable RSSI location estimation testing:")
            print("  1. Open Web UI at http://localhost:8090")
            print("  2. Click on a drone with '2 kits' or '3 kits' badge")
            print("  3. Click 'Estimate Location' to test RSSI triangulation")
            print("  4. Review spoofing score in the estimation overlay")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
