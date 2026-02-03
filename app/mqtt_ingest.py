#!/usr/bin/env python3
"""
WarDragon Analytics MQTT Ingest Service

Receives drone, aircraft, signal, and system data from WarDragon kits via MQTT.
Alternative to HTTP polling - kits push data directly to the Analytics stack.

Features:
- Subscribes to DragonSync MQTT topics
- Auto-registers kits when they first publish (no manual config needed)
- Handles aggregate and per-drone topics
- Normalizes data and writes to TimescaleDB
- Tracks kit health from MQTT heartbeats
- Graceful shutdown on SIGTERM/SIGINT

DragonSync MQTT Topics:
- wardragon/drones      - Aggregate drone list (JSON array)
- wardragon/drone/{id}  - Individual drone updates
- wardragon/aircraft    - ADS-B aircraft data
- wardragon/signals     - FPV signal detections
- wardragon/system      - System status/health
"""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import aiomqtt
    MQTT_AVAILABLE = True
except ImportError:
    try:
        import asyncio_mqtt as aiomqtt
        MQTT_AVAILABLE = True
    except ImportError:
        MQTT_AVAILABLE = False

from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://wardragon:wardragon@localhost:5432/wardragon')
MQTT_BROKER_HOST = os.getenv('MQTT_BROKER_HOST', 'localhost')
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', '1883'))
MQTT_USERNAME = os.getenv('MQTT_USERNAME', '')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')
MQTT_USE_TLS = os.getenv('MQTT_USE_TLS', 'false').lower() == 'true'

# Topic configuration (matches DragonSync defaults)
MQTT_TOPIC_DRONES = os.getenv('MQTT_TOPIC_DRONES', 'wardragon/drones')
MQTT_TOPIC_DRONE_PREFIX = os.getenv('MQTT_TOPIC_DRONE_PREFIX', 'wardragon/drone/')
MQTT_TOPIC_AIRCRAFT = os.getenv('MQTT_TOPIC_AIRCRAFT', 'wardragon/aircraft')
MQTT_TOPIC_SIGNALS = os.getenv('MQTT_TOPIC_SIGNALS', 'wardragon/signals')
MQTT_TOPIC_SYSTEM = os.getenv('MQTT_TOPIC_SYSTEM', 'wardragon/system')

# Global shutdown event
shutdown_event = asyncio.Event()


class MQTTDatabaseWriter:
    """Database interface for MQTT ingest - reuses logic from collector.py"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self._connect()

    def _connect(self):
        """Create database engine with connection pooling"""
        try:
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False
            )
            logger.info("MQTT Ingest: Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            raise

    def test_connection(self) -> bool:
        """Test database connectivity"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def insert_drone(self, kit_id: str, drone: Dict) -> bool:
        """Insert a single drone record"""
        try:
            with self.engine.connect() as conn:
                query = text("""
                    INSERT INTO drones (
                        time, kit_id, drone_id, lat, lon, alt, speed, heading,
                        vspeed, height, direction, op_status, runtime, id_type,
                        pilot_lat, pilot_lon, home_lat, home_lon,
                        mac, rssi, freq, ua_type, operator_id, caa_id,
                        rid_make, rid_model, rid_source, track_type
                    ) VALUES (
                        :time, :kit_id, :drone_id, :lat, :lon, :alt, :speed, :heading,
                        :vspeed, :height, :direction, :op_status, :runtime, :id_type,
                        :pilot_lat, :pilot_lon, :home_lat, :home_lon,
                        :mac, :rssi, :freq, :ua_type, :operator_id, :caa_id,
                        :rid_make, :rid_model, :rid_source, :track_type
                    )
                    ON CONFLICT (time, kit_id, drone_id) DO UPDATE SET
                        lat = EXCLUDED.lat,
                        lon = EXCLUDED.lon,
                        alt = EXCLUDED.alt,
                        speed = EXCLUDED.speed,
                        heading = EXCLUDED.heading,
                        vspeed = EXCLUDED.vspeed,
                        height = EXCLUDED.height
                """)

                timestamp = self._parse_timestamp(drone.get('timestamp'))
                track_type = drone.get('track_type', 'drone')

                conn.execute(query, {
                    'time': timestamp,
                    'kit_id': kit_id,
                    'drone_id': drone.get('id') or drone.get('drone_id') or drone.get('mac', 'unknown'),
                    'lat': self._safe_float(drone.get('lat')),
                    'lon': self._safe_float(drone.get('lon')),
                    'alt': self._safe_float(drone.get('alt')),
                    'speed': self._safe_float(drone.get('speed')),
                    'heading': self._safe_float(drone.get('heading') or drone.get('direction')),
                    'vspeed': self._safe_float(drone.get('vspeed')),
                    'height': self._safe_float(drone.get('height')),
                    'direction': self._safe_float(drone.get('direction')),
                    'op_status': drone.get('op_status'),
                    'runtime': self._safe_int(drone.get('runtime')),
                    'id_type': drone.get('id_type'),
                    'pilot_lat': self._safe_float(drone.get('pilot_lat')),
                    'pilot_lon': self._safe_float(drone.get('pilot_lon')),
                    'home_lat': self._safe_float(drone.get('home_lat')),
                    'home_lon': self._safe_float(drone.get('home_lon')),
                    'mac': drone.get('mac'),
                    'rssi': self._safe_int(drone.get('rssi')),
                    'freq': self._safe_float(drone.get('freq')),
                    'ua_type': drone.get('ua_type'),
                    'operator_id': drone.get('operator_id'),
                    'caa_id': drone.get('caa_id'),
                    'rid_make': drone.get('rid_make') or drone.get('make'),
                    'rid_model': drone.get('rid_model') or drone.get('model'),
                    'rid_source': drone.get('rid_source') or drone.get('source'),
                    'track_type': track_type
                })
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert drone: {e}")
            return False

    def insert_aircraft(self, kit_id: str, aircraft: Dict) -> bool:
        """Insert an aircraft record (from ADS-B)"""
        try:
            with self.engine.connect() as conn:
                query = text("""
                    INSERT INTO drones (
                        time, kit_id, drone_id, lat, lon, alt, speed, heading,
                        vspeed, track_type, mac, rssi
                    ) VALUES (
                        :time, :kit_id, :drone_id, :lat, :lon, :alt, :speed, :heading,
                        :vspeed, 'aircraft', :mac, :rssi
                    )
                    ON CONFLICT (time, kit_id, drone_id) DO UPDATE SET
                        lat = EXCLUDED.lat,
                        lon = EXCLUDED.lon,
                        alt = EXCLUDED.alt,
                        speed = EXCLUDED.speed,
                        heading = EXCLUDED.heading,
                        vspeed = EXCLUDED.vspeed
                """)

                timestamp = self._parse_timestamp(aircraft.get('timestamp'))

                # ICAO hex is the unique identifier for ADS-B aircraft
                icao = aircraft.get('icao') or aircraft.get('hex') or 'unknown'
                callsign = aircraft.get('callsign') or aircraft.get('flight', '').strip()

                conn.execute(query, {
                    'time': timestamp,
                    'kit_id': kit_id,
                    'drone_id': icao,
                    'lat': self._safe_float(aircraft.get('lat')),
                    'lon': self._safe_float(aircraft.get('lon')),
                    'alt': self._safe_float(aircraft.get('alt') or aircraft.get('alt_baro')),
                    'speed': self._safe_float(aircraft.get('speed') or aircraft.get('gs')),
                    'heading': self._safe_float(aircraft.get('track') or aircraft.get('heading')),
                    'vspeed': self._safe_float(aircraft.get('baro_rate')),
                    'mac': callsign if callsign else None,  # Store callsign in mac field
                    'rssi': self._safe_int(aircraft.get('rssi'))
                })
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert aircraft: {e}")
            return False

    def insert_signal(self, kit_id: str, signal: Dict) -> bool:
        """Insert an FPV signal record"""
        try:
            with self.engine.connect() as conn:
                query = text("""
                    INSERT INTO signals (
                        time, kit_id, freq_mhz, power_dbm, bandwidth_mhz,
                        lat, lon, alt, detection_type, pal_conf, ntsc_conf,
                        source, signal_type
                    ) VALUES (
                        :time, :kit_id, :freq_mhz, :power_dbm, :bandwidth_mhz,
                        :lat, :lon, :alt, :detection_type, :pal_conf, :ntsc_conf,
                        :source, :signal_type
                    )
                    ON CONFLICT (time, kit_id, freq_mhz) DO UPDATE SET
                        power_dbm = EXCLUDED.power_dbm,
                        pal_conf = EXCLUDED.pal_conf,
                        ntsc_conf = EXCLUDED.ntsc_conf
                """)

                # Handle timestamp: 'timestamp' or 'observed_at'
                timestamp = self._parse_timestamp(signal.get('timestamp') or signal.get('observed_at'))

                # Handle frequency: 'freq_mhz' or 'center_hz' (convert Hz to MHz)
                freq = self._safe_float(signal.get('freq_mhz'))
                if not freq:
                    center_hz = self._safe_float(signal.get('center_hz'))
                    if center_hz:
                        freq = center_hz / 1e6

                bandwidth_hz = signal.get('bandwidth_hz', 0)
                bandwidth_mhz = bandwidth_hz / 1e6 if bandwidth_hz else self._safe_float(signal.get('bandwidth_mhz'))

                conn.execute(query, {
                    'time': timestamp,
                    'kit_id': kit_id,
                    'freq_mhz': freq,
                    'power_dbm': self._safe_float(signal.get('power_dbm')),
                    'bandwidth_mhz': bandwidth_mhz,
                    'lat': self._safe_float(signal.get('sensor_lat') or signal.get('lat')),
                    'lon': self._safe_float(signal.get('sensor_lon') or signal.get('lon')),
                    'alt': self._safe_float(signal.get('sensor_alt') or signal.get('alt')),
                    'detection_type': signal.get('detection_type', 'analog'),
                    'pal_conf': self._safe_float(signal.get('pal_conf') or signal.get('pal')),
                    'ntsc_conf': self._safe_float(signal.get('ntsc_conf') or signal.get('ntsc')),
                    'source': signal.get('source'),
                    'signal_type': signal.get('signal_type')
                })
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert signal: {e}")
            return False

    def insert_system_health(self, kit_id: str, status: Dict) -> bool:
        """Insert system health record"""
        try:
            with self.engine.connect() as conn:
                query = text("""
                    INSERT INTO system_health (
                        time, kit_id, lat, lon, alt,
                        cpu_percent, memory_percent, disk_percent,
                        uptime_hours, temp_cpu, temp_gpu,
                        pluto_temp, zynq_temp, speed, track, gps_fix
                    ) VALUES (
                        :time, :kit_id, :lat, :lon, :alt,
                        :cpu_percent, :memory_percent, :disk_percent,
                        :uptime_hours, :temp_cpu, :temp_gpu,
                        :pluto_temp, :zynq_temp, :speed, :track, :gps_fix
                    )
                    ON CONFLICT (time, kit_id) DO UPDATE SET
                        cpu_percent = EXCLUDED.cpu_percent,
                        memory_percent = EXCLUDED.memory_percent,
                        disk_percent = EXCLUDED.disk_percent
                """)

                timestamp = self._parse_timestamp(status.get('timestamp'))

                # Calculate memory percent from total/available if not provided directly
                # DragonSync sends memory_total_mb and memory_available_mb
                memory_percent = status.get('memory_percent')
                if memory_percent is None:
                    mem_total = self._safe_float(
                        status.get('memory_total_mb') or status.get('memory_total')
                    )
                    mem_avail = self._safe_float(
                        status.get('memory_available_mb') or status.get('memory_available')
                    )
                    if mem_total and mem_total > 0:
                        memory_percent = ((mem_total - mem_avail) / mem_total) * 100

                # Calculate disk percent from total/used if not provided directly
                # DragonSync sends disk_total_mb and disk_used_mb
                disk_percent = status.get('disk_percent')
                if disk_percent is None:
                    disk_total = self._safe_float(
                        status.get('disk_total_mb') or status.get('disk_total')
                    )
                    disk_used = self._safe_float(
                        status.get('disk_used_mb') or status.get('disk_used')
                    )
                    if disk_total and disk_total > 0:
                        disk_percent = (disk_used / disk_total) * 100

                # Convert uptime from seconds to hours if needed
                # DragonSync sends uptime_s
                uptime_hours = status.get('uptime_hours')
                if uptime_hours is None:
                    uptime_secs = self._safe_float(
                        status.get('uptime_s') or status.get('uptime')
                    )
                    if uptime_secs is not None:
                        uptime_hours = uptime_secs / 3600.0

                conn.execute(query, {
                    'time': timestamp,
                    'kit_id': kit_id,
                    # DragonSync sends latitude/longitude/hae, also accept lat/lon/alt
                    'lat': self._safe_float(status.get('latitude') or status.get('lat')),
                    'lon': self._safe_float(status.get('longitude') or status.get('lon')),
                    'alt': self._safe_float(status.get('hae') or status.get('alt')),
                    'cpu_percent': self._safe_float(status.get('cpu_usage') or status.get('cpu_percent')),
                    'memory_percent': self._safe_float(memory_percent),
                    'disk_percent': self._safe_float(disk_percent),
                    'uptime_hours': self._safe_float(uptime_hours),
                    # DragonSync sends temperature_c, pluto_temp_c, zynq_temp_c
                    'temp_cpu': self._safe_float(status.get('temperature_c') or status.get('temperature') or status.get('temp_cpu')),
                    'temp_gpu': self._safe_float(status.get('temp_gpu')),
                    'pluto_temp': self._safe_float(status.get('pluto_temp_c') or status.get('pluto_temp')),
                    'zynq_temp': self._safe_float(status.get('zynq_temp_c') or status.get('zynq_temp')),
                    'speed': self._safe_float(status.get('speed')),
                    'track': self._safe_float(status.get('track')),
                    'gps_fix': status.get('gps_fix')
                })
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert system health: {e}")
            return False

    def update_kit_last_seen(self, kit_id: str) -> bool:
        """Update kit's last_seen timestamp to keep it online"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("""
                    UPDATE kits SET
                        last_seen = NOW(),
                        status = 'online'
                    WHERE kit_id = :kit_id
                """), {'kit_id': kit_id})
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to update kit last_seen for {kit_id}: {e}")
            return False

    def register_mqtt_kit(self, kit_id: str, name: str = None) -> bool:
        """Auto-register a kit that sends data via MQTT"""
        try:
            with self.engine.connect() as conn:
                # Check if kit already exists and get current source
                result = conn.execute(text("""
                    SELECT source FROM kits WHERE kit_id = :kit_id
                """), {'kit_id': kit_id})
                row = result.fetchone()

                if row:
                    current_source = row[0]
                    # If kit exists with 'http', upgrade to 'both'
                    if current_source == 'http':
                        conn.execute(text("""
                            UPDATE kits SET
                                source = 'both',
                                last_seen = NOW(),
                                status = 'online'
                            WHERE kit_id = :kit_id
                        """), {'kit_id': kit_id})
                        conn.commit()
                        logger.info(f"Kit {kit_id} upgraded from HTTP to hybrid (HTTP + MQTT)")
                    else:
                        # Just update last_seen
                        conn.execute(text("""
                            UPDATE kits SET
                                last_seen = NOW(),
                                status = 'online'
                            WHERE kit_id = :kit_id
                        """), {'kit_id': kit_id})
                        conn.commit()
                else:
                    # New kit, register as MQTT source
                    conn.execute(text("""
                        INSERT INTO kits (kit_id, name, api_url, source, status, enabled, created_at, last_seen)
                        VALUES (:kit_id, :name, NULL, 'mqtt', 'online', TRUE, NOW(), NOW())
                        ON CONFLICT (kit_id) DO UPDATE SET
                            last_seen = NOW(),
                            status = 'online'
                    """), {
                        'kit_id': kit_id,
                        # Just use kit_id as name - it's already descriptive (e.g., "wardragon-SERIAL")
                        # and the [M] badge in the UI shows it's MQTT
                        'name': name or kit_id
                    })
                    conn.commit()
                    logger.info(f"Auto-registered new MQTT kit: {kit_id}")

                return True
        except Exception as e:
            logger.error(f"Failed to register MQTT kit {kit_id}: {e}")
            return False

    def _parse_timestamp(self, ts: Any) -> datetime:
        """Parse timestamp from various formats"""
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                pass
        if isinstance(ts, (int, float)):
            try:
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except:
                pass
        return datetime.now(timezone.utc)

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert value to int"""
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def close(self):
        """Close database connection pool"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection pool closed")


class MQTTIngestService:
    """MQTT subscriber service for WarDragon data ingest"""

    def __init__(self):
        self.db = None
        self.client = None
        self.known_kits = set()  # Track kits we've seen
        self.stats = {
            'drones_received': 0,
            'aircraft_received': 0,
            'signals_received': 0,
            'system_received': 0,
            'errors': 0
        }

    async def start(self):
        """Start the MQTT ingest service"""
        if not MQTT_AVAILABLE:
            logger.error("MQTT library not available. Install with: pip install aiomqtt")
            logger.error("The service requires aiomqtt (or asyncio-mqtt) for MQTT support.")
            sys.exit(1)

        logger.info("Starting WarDragon Analytics MQTT Ingest Service")
        logger.info(f"MQTT Broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        logger.info(f"TLS: {'enabled' if MQTT_USE_TLS else 'disabled'}")

        # Initialize database
        logger.info("Initializing database connection...")
        self.db = MQTTDatabaseWriter(DATABASE_URL)

        if not self.db.test_connection():
            logger.error("Database connection test failed. Exiting.")
            sys.exit(1)

        # Ensure source column exists in kits table
        self._ensure_source_column()

        # Connect to MQTT broker and subscribe
        await self._connect_and_subscribe()

    def _ensure_source_column(self):
        """Ensure the source column exists in the kits table"""
        try:
            with self.db.engine.connect() as conn:
                # Check if source column exists
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'kits' AND column_name = 'source'
                    )
                """))
                has_source = result.scalar()

                if not has_source:
                    # Add source column
                    conn.execute(text("""
                        ALTER TABLE kits ADD COLUMN source TEXT DEFAULT 'http'
                            CHECK (source IN ('http', 'mqtt', 'both'))
                    """))
                    conn.commit()
                    logger.info("Added 'source' column to kits table")

                    # Create index
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kits_source ON kits(source)"))
                    conn.commit()
                else:
                    logger.debug("Source column already exists in kits table")
        except Exception as e:
            logger.warning(f"Could not check/add source column: {e}")

    async def _connect_and_subscribe(self):
        """Connect to MQTT broker and subscribe to topics"""
        # Build connection parameters
        connect_kwargs = {
            'hostname': MQTT_BROKER_HOST,
            'port': MQTT_BROKER_PORT,
        }

        if MQTT_USERNAME:
            connect_kwargs['username'] = MQTT_USERNAME
        if MQTT_PASSWORD:
            connect_kwargs['password'] = MQTT_PASSWORD

        reconnect_interval = 5  # seconds
        max_reconnect_interval = 60  # seconds

        while not shutdown_event.is_set():
            try:
                logger.info(f"Connecting to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}...")

                async with aiomqtt.Client(**connect_kwargs) as client:
                    logger.info("Connected to MQTT broker")
                    reconnect_interval = 5  # Reset on successful connection

                    # Subscribe to all DragonSync topics
                    # Note: Only subscribe to /attrs for system - /availability sends plain strings, not JSON
                    topics = [
                        (MQTT_TOPIC_DRONES, 0),       # Aggregate drones
                        (f"{MQTT_TOPIC_DRONE_PREFIX}#", 0),  # Per-drone topics (includes /attrs but filters by JSON)
                        (MQTT_TOPIC_AIRCRAFT, 0),    # ADS-B aircraft
                        (MQTT_TOPIC_SIGNALS, 0),     # FPV signals
                        (f"{MQTT_TOPIC_SYSTEM}/attrs", 0),  # System status JSON only
                    ]

                    for topic, qos in topics:
                        await client.subscribe(topic, qos=qos)
                        logger.info(f"Subscribed to: {topic}")

                    # Start stats logging task
                    stats_task = asyncio.create_task(self._log_stats())

                    try:
                        # Process messages
                        async for message in client.messages:
                            if shutdown_event.is_set():
                                break
                            await self._handle_message(message)
                    finally:
                        stats_task.cancel()
                        try:
                            await stats_task
                        except asyncio.CancelledError:
                            pass

            except aiomqtt.MqttError as e:
                if shutdown_event.is_set():
                    break
                logger.error(f"MQTT error: {e}")
                logger.info(f"Reconnecting in {reconnect_interval} seconds...")
                await asyncio.sleep(reconnect_interval)
                reconnect_interval = min(reconnect_interval * 2, max_reconnect_interval)

            except Exception as e:
                if shutdown_event.is_set():
                    break
                logger.error(f"Unexpected error: {e}", exc_info=True)
                await asyncio.sleep(reconnect_interval)

        logger.info("MQTT ingest service stopped")

    async def _handle_message(self, message):
        """Handle incoming MQTT message"""
        try:
            topic = str(message.topic)
            payload = message.payload.decode('utf-8')

            # Skip non-JSON topics (Home Assistant state/availability send plain strings)
            # Includes: /availability, /state, /pilot_availability, /home_availability
            if 'availability' in topic or topic.endswith('/state'):
                return

            data = json.loads(payload)

            # Extract kit_id from payload (DragonSync uses different fields per message type)
            # - Drone/aircraft/signal messages use 'seen_by'
            # - System attrs use 'id' (e.g., "wardragon-SERIAL")
            kit_id = data.get('seen_by') or data.get('kit_id') or data.get('id') or data.get('uid')

            if not kit_id:
                # Try to extract from topic for per-drone messages
                if topic.startswith(MQTT_TOPIC_DRONE_PREFIX):
                    # Can't determine kit_id from per-drone topic alone
                    logger.debug(f"No kit_id in per-drone message, skipping: {topic}")
                    return
                else:
                    logger.warning(f"No kit_id in message on topic {topic}")
                    return

            # Auto-register kit if first time seeing it
            if kit_id not in self.known_kits:
                self.db.register_mqtt_kit(kit_id)
                self.known_kits.add(kit_id)

            # Route message to appropriate handler
            if topic == MQTT_TOPIC_DRONES:
                await self._handle_drones(kit_id, data)
            elif topic.startswith(MQTT_TOPIC_DRONE_PREFIX):
                await self._handle_drone(kit_id, data)
            elif topic == MQTT_TOPIC_AIRCRAFT:
                await self._handle_aircraft(kit_id, data)
            elif topic == MQTT_TOPIC_SIGNALS:
                await self._handle_signal(kit_id, data)
            elif topic == f"{MQTT_TOPIC_SYSTEM}/attrs":
                # DragonSync system health (JSON)
                await self._handle_system(kit_id, data)
            else:
                logger.debug(f"Unhandled topic: {topic}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON on topic {topic}: {payload[:100]!r}")
            self.stats['errors'] += 1
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            self.stats['errors'] += 1

    async def _handle_drones(self, kit_id: str, data: Dict):
        """Handle aggregate drones message - can be single drone dict, list, or wrapped"""
        # DragonSync publishes individual drone dicts to aggregate topic
        # Handle: single dict, list of dicts, or {"drones": [...]}
        if isinstance(data, list):
            drones = data
        elif 'drones' in data:
            drones = data.get('drones', [])
        else:
            # Single drone dict (this is what DragonSync sends)
            drones = [data]

        for drone in drones:
            if self.db.insert_drone(kit_id, drone):
                self.stats['drones_received'] += 1

        if drones:
            logger.debug(f"Kit {kit_id}: Received {len(drones)} drones via MQTT")

    async def _handle_drone(self, kit_id: str, data: Dict):
        """Handle per-drone message"""
        if self.db.insert_drone(kit_id, data):
            self.stats['drones_received'] += 1
            logger.debug(f"Kit {kit_id}: Received drone {data.get('id')} via MQTT")

    async def _handle_aircraft(self, kit_id: str, data: Dict):
        """Handle aircraft message"""
        # Handle both single aircraft and list
        aircraft_list = data.get('aircraft', [data])
        if isinstance(data, list):
            aircraft_list = data

        for aircraft in aircraft_list:
            if self.db.insert_aircraft(kit_id, aircraft):
                self.stats['aircraft_received'] += 1

        if aircraft_list:
            logger.debug(f"Kit {kit_id}: Received {len(aircraft_list)} aircraft via MQTT")

    async def _handle_signal(self, kit_id: str, data: Dict):
        """Handle FPV signal message"""
        # Handle both single signal and list
        signals = data.get('signals', [data])
        if isinstance(data, list):
            signals = data

        for signal in signals:
            if self.db.insert_signal(kit_id, signal):
                self.stats['signals_received'] += 1

        if signals:
            logger.debug(f"Kit {kit_id}: Received {len(signals)} signals via MQTT")

    async def _handle_system(self, kit_id: str, data: Dict):
        """Handle system status message"""
        if self.db.insert_system_health(kit_id, data):
            self.stats['system_received'] += 1
            # Update kit's last_seen timestamp to keep it 'online'
            self.db.update_kit_last_seen(kit_id)
            logger.debug(f"Kit {kit_id}: Received system status via MQTT")

    async def _log_stats(self):
        """Periodically log statistics"""
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(60)  # Log every minute

                total = sum(self.stats.values())
                logger.info(
                    f"MQTT Ingest Stats: "
                    f"Drones: {self.stats['drones_received']}, "
                    f"Aircraft: {self.stats['aircraft_received']}, "
                    f"Signals: {self.stats['signals_received']}, "
                    f"System: {self.stats['system_received']}, "
                    f"Errors: {self.stats['errors']}, "
                    f"Known Kits: {len(self.known_kits)}"
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error logging stats: {e}")

    async def shutdown(self):
        """Gracefully shutdown the service"""
        logger.info("Initiating graceful shutdown...")
        shutdown_event.set()

        # Close database connection
        if self.db:
            self.db.close()

        logger.info("Shutdown complete")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received signal {sig_name}, initiating shutdown...")
    shutdown_event.set()


def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Create and run service
    service = MQTTIngestService()

    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("MQTT ingest service stopped")


if __name__ == '__main__':
    main()
