#!/usr/bin/env python3
"""
WarDragon Analytics Collector Service

Polls DragonSync APIs from configured WarDragon kits and stores data in TimescaleDB.

Features:
- Async polling of multiple kits every 5 seconds
- Fetches /drones, /signals, /status endpoints
- Normalizes data and writes to TimescaleDB
- Tracks kit health (online/offline/stale)
- Exponential backoff for offline kits
- Connection pooling and retry logic
- Graceful shutdown on SIGTERM/SIGINT
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import os

import httpx
import yaml
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
KITS_CONFIG = os.getenv('KITS_CONFIG', '/config/kits.yaml')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '5'))  # seconds
STATUS_POLL_INTERVAL = int(os.getenv('STATUS_POLL_INTERVAL', '30'))  # seconds
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '10'))  # seconds
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
INITIAL_BACKOFF = float(os.getenv('INITIAL_BACKOFF', '5.0'))  # seconds
MAX_BACKOFF = float(os.getenv('MAX_BACKOFF', '300.0'))  # 5 minutes
STALE_THRESHOLD = int(os.getenv('STALE_THRESHOLD', '60'))  # seconds
KIT_RELOAD_INTERVAL = int(os.getenv('KIT_RELOAD_INTERVAL', '30'))  # seconds - how often to check for new kits
USE_DB_KITS = os.getenv('USE_DB_KITS', 'true').lower() == 'true'  # Use database for kit config instead of YAML

# Global shutdown event
shutdown_event = asyncio.Event()


class KitHealth:
    """Tracks health status and backoff for a kit"""

    def __init__(self, kit_id: str):
        self.kit_id = kit_id
        self.status = 'unknown'  # unknown, online, offline, stale, error
        self.last_seen: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.consecutive_failures = 0
        self.backoff_delay = INITIAL_BACKOFF
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0

    def mark_success(self):
        """Mark successful poll"""
        self.status = 'online'
        self.last_seen = datetime.now(timezone.utc)
        self.consecutive_failures = 0
        self.backoff_delay = INITIAL_BACKOFF
        self.total_requests += 1
        self.successful_requests += 1
        self.last_error = None

    def mark_failure(self, error: str):
        """Mark failed poll and calculate backoff"""
        self.status = 'offline'
        self.last_error = error
        self.consecutive_failures += 1
        self.total_requests += 1
        self.failed_requests += 1

        # Exponential backoff: delay = min(initial * 2^failures, max)
        self.backoff_delay = min(
            INITIAL_BACKOFF * (2 ** self.consecutive_failures),
            MAX_BACKOFF
        )
        logger.warning(
            f"Kit {self.kit_id} failed (attempt {self.consecutive_failures}). "
            f"Next retry in {self.backoff_delay:.1f}s. Error: {error}"
        )

    def mark_stale(self):
        """Mark as stale if no data received recently"""
        if self.last_seen:
            age = (datetime.now(timezone.utc) - self.last_seen).total_seconds()
            if age > STALE_THRESHOLD:
                self.status = 'stale'
                logger.warning(f"Kit {self.kit_id} marked stale (last seen {age:.0f}s ago)")

    def get_next_poll_delay(self) -> float:
        """Get delay until next poll attempt"""
        if self.status == 'online':
            return 0.0  # Poll immediately
        return self.backoff_delay

    def get_stats(self) -> Dict[str, Any]:
        """Get health statistics"""
        success_rate = (
            (self.successful_requests / self.total_requests * 100)
            if self.total_requests > 0 else 0.0
        )
        return {
            'status': self.status,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'consecutive_failures': self.consecutive_failures,
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': f"{success_rate:.1f}%",
            'next_retry_delay': self.backoff_delay,
            'last_error': self.last_error
        }


class DatabaseWriter:
    """Handles database connections and writes"""

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
                pool_pre_ping=True,  # Verify connections before using
                pool_recycle=3600,   # Recycle connections after 1 hour
                echo=False
            )
            logger.info("Database connection pool created")
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

    async def insert_drones(self, kit_id: str, drones: List[Dict]) -> int:
        """Insert drone records into database"""
        if not drones:
            return 0

        inserted = 0
        try:
            with self.engine.connect() as conn:
                for drone in drones:
                    try:
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

                        # Normalize timestamp
                        timestamp = self._parse_timestamp(drone.get('timestamp'))

                        # Determine track type
                        track_type = drone.get('track_type', 'drone')
                        if drone.get('icao'):
                            track_type = 'aircraft'

                        conn.execute(query, {
                            'time': timestamp,
                            'kit_id': kit_id,
                            # Priority: drone_id (explicit), id (serial from DragonSync), icao (aircraft), mac (fallback)
                            'drone_id': drone.get('drone_id') or drone.get('id') or drone.get('icao') or drone.get('mac', 'unknown'),
                            'lat': self._safe_float(drone.get('lat')),
                            'lon': self._safe_float(drone.get('lon')),
                            'alt': self._safe_float(drone.get('alt') or drone.get('altitude')),
                            'speed': self._safe_float(drone.get('speed')),
                            'heading': self._safe_float(drone.get('heading') or drone.get('direction')),
                            # Phase 1: New drone fields from DragonSync API
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
                            'rid_make': drone.get('rid', {}).get('make') or drone.get('rid_make') or drone.get('make'),
                            'rid_model': drone.get('rid', {}).get('model') or drone.get('rid_model') or drone.get('model'),
                            'rid_source': drone.get('rid', {}).get('source') or drone.get('rid_source') or drone.get('source'),
                            'track_type': track_type
                        })
                        conn.commit()
                        inserted += 1
                    except SQLAlchemyError as e:
                        logger.error(f"Failed to insert drone record: {e}")
                        conn.rollback()
                        continue

            if inserted > 0:
                logger.debug(f"Inserted {inserted} drone records for kit {kit_id}")
            return inserted
        except Exception as e:
            logger.error(f"Failed to insert drones for kit {kit_id}: {e}")
            return 0

    async def insert_signals(self, kit_id: str, signals: List[Dict]) -> int:
        """Insert signal records into database"""
        if not signals:
            return 0

        inserted = 0
        try:
            with self.engine.connect() as conn:
                for signal in signals:
                    try:
                        query = text("""
                            INSERT INTO signals (
                                time, kit_id, freq_mhz, power_dbm, bandwidth_mhz,
                                lat, lon, alt, detection_type,
                                pal_conf, ntsc_conf, source, signal_type
                            ) VALUES (
                                :time, :kit_id, :freq_mhz, :power_dbm, :bandwidth_mhz,
                                :lat, :lon, :alt, :detection_type,
                                :pal_conf, :ntsc_conf, :source, :signal_type
                            )
                            ON CONFLICT (time, kit_id, freq_mhz) DO UPDATE SET
                                power_dbm = EXCLUDED.power_dbm,
                                pal_conf = EXCLUDED.pal_conf,
                                ntsc_conf = EXCLUDED.ntsc_conf
                        """)

                        timestamp = self._parse_timestamp(signal.get('timestamp'))

                        # Determine detection type
                        freq = self._safe_float(signal.get('freq_mhz') or signal.get('freq'))
                        detection_type = signal.get('type', 'analog')
                        if freq and 5600 <= freq <= 5900:
                            detection_type = signal.get('type', 'analog')

                        conn.execute(query, {
                            'time': timestamp,
                            'kit_id': kit_id,
                            'freq_mhz': freq,
                            'power_dbm': self._safe_float(signal.get('power_dbm') or signal.get('power')),
                            'bandwidth_mhz': self._safe_float(signal.get('bandwidth_mhz') or signal.get('bandwidth') or signal.get('bandwidth_hz', 0) / 1e6),
                            'lat': self._safe_float(signal.get('lat') or signal.get('sensor_lat')),
                            'lon': self._safe_float(signal.get('lon') or signal.get('sensor_lon')),
                            'alt': self._safe_float(signal.get('alt') or signal.get('sensor_alt')),
                            'detection_type': detection_type,
                            # Phase 1: New signal fields from DragonSync API
                            'pal_conf': self._safe_float(signal.get('pal_conf')),
                            'ntsc_conf': self._safe_float(signal.get('ntsc_conf')),
                            'source': signal.get('source'),  # guard, confirm
                            'signal_type': signal.get('signal_type')  # fpv
                        })
                        conn.commit()
                        inserted += 1
                    except SQLAlchemyError as e:
                        logger.error(f"Failed to insert signal record: {e}")
                        conn.rollback()
                        continue

            if inserted > 0:
                logger.debug(f"Inserted {inserted} signal records for kit {kit_id}")
            return inserted
        except Exception as e:
            logger.error(f"Failed to insert signals for kit {kit_id}: {e}")
            return 0

    async def insert_health(self, kit_id: str, status: Dict) -> bool:
        """Insert system health record into database"""
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
                        disk_percent = EXCLUDED.disk_percent,
                        pluto_temp = EXCLUDED.pluto_temp,
                        zynq_temp = EXCLUDED.zynq_temp
                """)

                timestamp = self._parse_timestamp(status.get('timestamp') or status.get('last_update_time'))

                # Handle both nested format (legacy) and flat format (DragonSync API)
                gps = status.get('gps', {})
                cpu = status.get('cpu', {})
                memory = status.get('memory', {})
                disk = status.get('disk', {})
                temps = status.get('temps', {})

                # Calculate memory/disk percentages from totals if not provided directly
                mem_percent = self._safe_float(memory.get('percent') or status.get('memory_percent'))
                if mem_percent is None and status.get('memory_total') and status.get('memory_available'):
                    total = self._safe_float(status.get('memory_total'))
                    avail = self._safe_float(status.get('memory_available'))
                    if total and total > 0:
                        mem_percent = ((total - avail) / total) * 100

                disk_percent = self._safe_float(disk.get('percent') or status.get('disk_percent'))
                if disk_percent is None and status.get('disk_total') and status.get('disk_used'):
                    total = self._safe_float(status.get('disk_total'))
                    used = self._safe_float(status.get('disk_used'))
                    if total and total > 0:
                        disk_percent = (used / total) * 100

                conn.execute(query, {
                    'time': timestamp,
                    'kit_id': kit_id,
                    # GPS - handle both nested and flat format
                    'lat': self._safe_float(gps.get('lat') or status.get('lat')),
                    'lon': self._safe_float(gps.get('lon') or status.get('lon')),
                    'alt': self._safe_float(gps.get('alt') or status.get('alt')),
                    # CPU - handle both nested and flat format
                    'cpu_percent': self._safe_float(cpu.get('percent') or status.get('cpu_usage') or status.get('cpu_percent')),
                    'memory_percent': mem_percent,
                    'disk_percent': disk_percent,
                    'uptime_hours': self._safe_float(status.get('uptime_hours') or (status.get('uptime', 0) / 3600 if status.get('uptime') else None)),
                    'temp_cpu': self._safe_float(temps.get('cpu') or status.get('temperature') or status.get('temp_cpu')),
                    'temp_gpu': self._safe_float(temps.get('gpu') or status.get('temp_gpu')),
                    # Phase 1: New system_health fields from DragonSync API
                    'pluto_temp': self._safe_float(status.get('pluto_temp')),
                    'zynq_temp': self._safe_float(status.get('zynq_temp')),
                    'speed': self._safe_float(status.get('speed')),
                    'track': self._safe_float(status.get('track')),
                    'gps_fix': status.get('gps_fix')
                })
                conn.commit()

                logger.debug(f"Inserted health record for kit {kit_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to insert health for kit {kit_id}: {e}")
            return False

    async def update_kit_status(self, kit_id: str, status: str, last_seen: datetime,
                                  name: str = None, api_url: str = None, location: str = None):
        """Update kit status in kits table"""
        try:
            with self.engine.connect() as conn:
                query = text("""
                    INSERT INTO kits (kit_id, name, api_url, location, status, last_seen)
                    VALUES (:kit_id, :name, :api_url, :location, :status, :last_seen)
                    ON CONFLICT (kit_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        last_seen = EXCLUDED.last_seen,
                        name = COALESCE(EXCLUDED.name, kits.name),
                        api_url = COALESCE(EXCLUDED.api_url, kits.api_url),
                        location = COALESCE(EXCLUDED.location, kits.location)
                """)
                conn.execute(query, {
                    'kit_id': kit_id,
                    'name': name or kit_id,
                    'api_url': api_url or 'unknown',
                    'location': location,
                    'status': status,
                    'last_seen': last_seen
                })
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update kit status: {e}")

    def _parse_timestamp(self, ts: Any) -> datetime:
        """Parse timestamp from various formats"""
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                pass
        # Default to current time
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

    def fetch_kits_from_db(self) -> List[Dict]:
        """Fetch kit configurations from the database"""
        try:
            with self.engine.connect() as conn:
                # First, ensure the enabled column exists
                try:
                    result = conn.execute(text("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'kits' AND column_name = 'enabled'
                        )
                    """))
                    has_enabled = result.scalar()

                    if not has_enabled:
                        conn.execute(text("ALTER TABLE kits ADD COLUMN enabled BOOLEAN DEFAULT TRUE"))
                        conn.commit()
                        logger.info("Added 'enabled' column to kits table")
                except Exception as e:
                    logger.warning(f"Could not check/add enabled column: {e}")
                    has_enabled = False

                # Fetch kits
                if has_enabled:
                    result = conn.execute(text("""
                        SELECT kit_id, name, api_url, location, status, enabled
                        FROM kits
                        WHERE enabled = TRUE OR enabled IS NULL
                        ORDER BY name
                    """))
                else:
                    result = conn.execute(text("""
                        SELECT kit_id, name, api_url, location, status
                        FROM kits
                        ORDER BY name
                    """))

                kits = []
                for row in result:
                    kit = {
                        'id': row[0],  # kit_id
                        'name': row[1],
                        'api_url': row[2],
                        'location': row[3],
                        'status': row[4],
                        'enabled': row[5] if has_enabled and len(row) > 5 else True
                    }
                    kits.append(kit)

                logger.info(f"Fetched {len(kits)} enabled kits from database")
                return kits
        except Exception as e:
            logger.error(f"Failed to fetch kits from database: {e}")
            return []


class KitCollector:
    """Handles polling and data collection for a single kit"""

    def __init__(self, kit_config: Dict, db: DatabaseWriter, client: httpx.AsyncClient):
        # Config ID is used as fallback if API doesn't provide kit_id
        self.config_id = kit_config.get('id', 'unknown')
        self.kit_id = None  # Will be set from API /status response
        self.name = kit_config.get('name')  # Optional friendly name
        self.api_url = kit_config['api_url'].rstrip('/')
        self.location = kit_config.get('location')
        self.enabled = kit_config.get('enabled', True)

        self.db = db
        self.client = client
        self.health = None  # Created after we know the kit_id
        self._initialized = False

        logger.info(f"Initialized collector for {self.api_url} (config_id: {self.config_id})")

    async def fetch_json(self, endpoint: str, retry: int = 0) -> Optional[Dict]:
        """Fetch JSON data from kit endpoint with retry logic"""
        url = f"{self.api_url}{endpoint}"

        try:
            response = await self.client.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            error = f"Timeout fetching {endpoint}"
            if retry < MAX_RETRIES:
                logger.debug(f"Kit {self.kit_id}: {error}, retrying ({retry + 1}/{MAX_RETRIES})")
                await asyncio.sleep(1 * (retry + 1))  # Linear backoff for retries
                return await self.fetch_json(endpoint, retry + 1)
            logger.error(f"Kit {self.kit_id}: {error} after {MAX_RETRIES} retries")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"Kit {self.kit_id}: HTTP {e.response.status_code} fetching {endpoint}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Kit {self.kit_id}: Request error fetching {endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"Kit {self.kit_id}: Unexpected error fetching {endpoint}: {e}")
            return None

    async def poll_drones(self) -> bool:
        """Poll /drones endpoint and store data"""
        data = await self.fetch_json('/drones')
        if data is None:
            return False

        # Handle both {drones: [...]} and [...] formats
        drones = data if isinstance(data, list) else data.get('drones', [])

        if drones:
            kit_id = self._get_kit_id()
            inserted = await self.db.insert_drones(kit_id, drones)
            logger.info(f"Kit {kit_id}: Collected {len(drones)} drones, inserted {inserted}")

        return True

    async def poll_signals(self) -> bool:
        """Poll /signals endpoint and store data"""
        data = await self.fetch_json('/signals')
        if data is None:
            return False

        # Handle both {signals: [...]} and [...] formats
        signals = data if isinstance(data, list) else data.get('signals', [])

        if signals:
            kit_id = self._get_kit_id()
            inserted = await self.db.insert_signals(kit_id, signals)
            logger.info(f"Kit {kit_id}: Collected {len(signals)} signals, inserted {inserted}")

        return True

    async def poll_status(self) -> bool:
        """Poll /status endpoint and store data, also extracts kit_id"""
        data = await self.fetch_json('/status')
        if data is None:
            return False

        # Extract kit_id from API response (e.g., "wardragon-abc123")
        # Check both 'kit_id' and 'uid' fields - DragonSync returns 'uid' in status response
        api_kit_id = data.get('kit_id') or data.get('uid')
        if api_kit_id and api_kit_id != self.kit_id:
            old_id = self.kit_id
            self.kit_id = api_kit_id
            if old_id:
                logger.info(f"Kit ID updated: {old_id} -> {self.kit_id}")
            else:
                logger.info(f"Kit ID discovered from API: {self.kit_id}")
            # Update health tracker with new kit_id
            if self.health:
                self.health.kit_id = self.kit_id

        success = await self.db.insert_health(self._get_kit_id(), data)
        if success:
            logger.info(f"Kit {self._get_kit_id()}: Collected system status")

        return True

    def _get_kit_id(self) -> str:
        """Get the kit_id, falling back to config_id if not yet discovered"""
        return self.kit_id or self.config_id

    async def poll_all_endpoints(self) -> bool:
        """Poll all endpoints for this kit"""
        # Poll drones and signals endpoints
        results = await asyncio.gather(
            self.poll_drones(),
            self.poll_signals(),
            return_exceptions=True
        )

        # Check if any succeeded
        success = any(r is True for r in results)

        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                endpoint = ['/drones', '/signals'][i]
                logger.error(f"Kit {self.kit_id}: Exception polling {endpoint}: {result}")

        return success

    async def _initialize(self) -> bool:
        """Initialize by fetching /status to discover kit_id"""
        logger.info(f"Discovering kit_id from {self.api_url}/status...")

        # Try to get kit_id from /status endpoint
        # Check both 'kit_id' and 'uid' - DragonSync returns 'uid' in status response
        data = await self.fetch_json('/status')
        if data:
            api_kit_id = data.get('kit_id') or data.get('uid')
            if api_kit_id:
                self.kit_id = api_kit_id
                logger.info(f"Discovered kit_id from API: {self.kit_id}")
            else:
                self.kit_id = self.config_id
                logger.warning(f"API did not provide kit_id, using config_id: {self.kit_id}")

            # Store initial health data
            await self.db.insert_health(self._get_kit_id(), data)
        else:
            self.kit_id = self.config_id
            logger.warning(f"Could not reach {self.api_url}/status, using config_id: {self.kit_id}")

        # Now create health tracker with the discovered kit_id
        self.health = KitHealth(self._get_kit_id())
        self._initialized = True
        return True

    async def run(self):
        """Main polling loop for this kit"""
        # First, initialize to discover kit_id
        if not self._initialized:
            await self._initialize()

        kit_id = self._get_kit_id()
        logger.info(f"Starting collector for kit {kit_id}")

        status_poll_counter = 0
        status_interval_cycles = STATUS_POLL_INTERVAL // POLL_INTERVAL

        while not shutdown_event.is_set():
            if not self.enabled:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            try:
                kit_id = self._get_kit_id()

                # Poll drones and signals
                success = await self.poll_all_endpoints()

                # Poll status less frequently
                status_poll_counter += 1
                if status_poll_counter >= status_interval_cycles:
                    status_success = await self.poll_status()
                    success = success or status_success
                    status_poll_counter = 0
                    # kit_id may have been updated by poll_status
                    kit_id = self._get_kit_id()

                # Update health status
                if success:
                    self.health.mark_success()
                    await self.db.update_kit_status(
                        kit_id,
                        self.health.status,
                        self.health.last_seen,
                        name=self.name or kit_id,
                        api_url=self.api_url,
                        location=self.location
                    )
                else:
                    self.health.mark_failure("Failed to fetch data from any endpoint")
                    await self.db.update_kit_status(
                        kit_id,
                        self.health.status,
                        datetime.now(timezone.utc),
                        name=self.name or kit_id,
                        api_url=self.api_url,
                        location=self.location
                    )

                # Calculate next poll delay
                if success:
                    delay = POLL_INTERVAL
                else:
                    # Use exponential backoff for failed kits
                    delay = self.health.get_next_poll_delay()
                    logger.info(f"Kit {kit_id}: Backing off for {delay:.1f}s")

                # Wait for next poll or shutdown
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(),
                        timeout=delay
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Normal timeout, continue polling

            except Exception as e:
                logger.error(f"Kit {kit_id}: Unexpected error in polling loop: {e}", exc_info=True)
                self.health.mark_failure(str(e))
                await asyncio.sleep(POLL_INTERVAL)

        logger.info(f"Stopped collector for kit {kit_id}")


class CollectorService:
    """Main collector service that manages all kit collectors"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.kits = []
        self.kit_configs = {}  # Track kit configs by api_url for change detection
        self.db = None
        self.client = None
        self.tasks = []
        self.health_stats = {}
        self._kit_lock = asyncio.Lock()  # Protect concurrent kit modifications

    def load_config(self) -> List[Dict]:
        """Load kits configuration from YAML file and/or database.

        When USE_DB_KITS is enabled (default):
        1. Load kits from database
        2. Also load from YAML and sync any new kits to database
        3. Database is the source of truth for enabled/disabled state

        When USE_DB_KITS is disabled:
        1. Only use YAML file
        """
        yaml_kits = self._load_yaml_kits()

        if not USE_DB_KITS:
            # YAML-only mode
            logger.info(f"Database kit management disabled, using YAML only ({len(yaml_kits)} kits)")
            return yaml_kits

        if not self.db:
            logger.warning("Database not initialized, using YAML configuration")
            return yaml_kits

        # Database mode: sync YAML kits to database, then load from database
        db_kits = self.db.fetch_kits_from_db()

        # Sync YAML kits to database (add any that don't exist)
        if yaml_kits:
            self._sync_yaml_to_database(yaml_kits, db_kits)
            # Re-fetch after sync
            db_kits = self.db.fetch_kits_from_db()

        if db_kits:
            logger.info(f"Loaded {len(db_kits)} kits from database")
            return db_kits
        elif yaml_kits:
            logger.info(f"No kits in database yet, using {len(yaml_kits)} kits from YAML")
            return yaml_kits
        else:
            logger.warning("No kits configured in database or YAML. Add kits via web UI or kits.yaml")
            return []

    def _load_yaml_kits(self) -> List[Dict]:
        """Load kits from YAML configuration file"""
        config_file = Path(self.config_path)

        if not config_file.exists():
            logger.debug(f"YAML config file not found: {self.config_path}")
            return []

        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            kits = config.get('kits', [])

            # Validate and normalize configuration
            for i, kit in enumerate(kits):
                if 'api_url' not in kit:
                    logger.warning(f"Kit #{i+1} in YAML missing 'api_url' field, skipping")
                    continue
                # 'id' is now optional - will be discovered from API
                if 'id' not in kit:
                    kit['id'] = f"kit-{i+1}"

            return [k for k in kits if 'api_url' in k]
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML configuration: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to load YAML configuration: {e}")
            return []

    def _sync_yaml_to_database(self, yaml_kits: List[Dict], db_kits: List[Dict]):
        """Sync YAML kits to database (add new ones, don't modify existing)"""
        db_urls = {k['api_url'] for k in db_kits}

        for kit in yaml_kits:
            api_url = kit['api_url'].rstrip('/')
            if api_url not in db_urls and f"{api_url}/" not in db_urls:
                # Kit not in database, add it
                try:
                    with self.db.engine.connect() as conn:
                        from sqlalchemy import text
                        conn.execute(text("""
                            INSERT INTO kits (kit_id, name, api_url, location, status, enabled, created_at)
                            VALUES (:kit_id, :name, :api_url, :location, 'unknown', TRUE, NOW())
                            ON CONFLICT (kit_id) DO NOTHING
                        """), {
                            'kit_id': kit.get('id', f"kit-yaml-{hash(api_url) % 10000}"),
                            'name': kit.get('name', kit.get('id', api_url)),
                            'api_url': api_url,
                            'location': kit.get('location')
                        })
                        conn.commit()
                    logger.info(f"Synced YAML kit to database: {api_url}")
                except Exception as e:
                    logger.error(f"Failed to sync YAML kit to database: {e}")

    async def reload_kits(self) -> Dict[str, int]:
        """
        Reload kit configuration from database and update collectors.

        Returns:
            Dict with counts of added, removed, and unchanged kits
        """
        if not USE_DB_KITS or not self.db:
            return {'added': 0, 'removed': 0, 'unchanged': len(self.kits)}

        async with self._kit_lock:
            try:
                # Fetch current kits from database
                db_kits = self.db.fetch_kits_from_db()

                # Build sets for comparison
                current_urls = {k.api_url for k in self.kits}
                new_urls = {k['api_url'] for k in db_kits}

                # Find kits to add
                to_add = [k for k in db_kits if k['api_url'] not in current_urls]

                # Find kits to remove
                to_remove = [k for k in self.kits if k.api_url not in new_urls]

                stats = {'added': 0, 'removed': 0, 'unchanged': 0}

                # Remove old collectors
                for collector in to_remove:
                    logger.info(f"Removing collector for kit {collector._get_kit_id()} ({collector.api_url})")
                    collector.enabled = False
                    self.kits.remove(collector)
                    stats['removed'] += 1

                # Add new collectors
                for kit_config in to_add:
                    kit_config['enabled'] = kit_config.get('enabled', True)
                    if kit_config['enabled']:
                        logger.info(f"Adding new collector for kit {kit_config.get('id', 'unknown')} ({kit_config['api_url']})")
                        collector = KitCollector(kit_config, self.db, self.client)
                        self.kits.append(collector)
                        # Start the collector task
                        task = asyncio.create_task(collector.run())
                        self.tasks.append(task)
                        stats['added'] += 1

                stats['unchanged'] = len(self.kits) - stats['added']

                if stats['added'] > 0 or stats['removed'] > 0:
                    logger.info(f"Kit reload complete: {stats['added']} added, {stats['removed']} removed, {stats['unchanged']} unchanged")

                return stats

            except Exception as e:
                logger.error(f"Failed to reload kits: {e}")
                return {'added': 0, 'removed': 0, 'unchanged': len(self.kits), 'error': str(e)}

    async def start(self):
        """Start the collector service"""
        logger.info("Starting WarDragon Analytics Collector Service")
        logger.info(f"Poll interval: {POLL_INTERVAL}s")
        logger.info(f"Status poll interval: {STATUS_POLL_INTERVAL}s")
        logger.info(f"Request timeout: {REQUEST_TIMEOUT}s")
        logger.info(f"Dynamic kit reload: {'enabled' if USE_DB_KITS else 'disabled'} (interval: {KIT_RELOAD_INTERVAL}s)")

        # Initialize database
        logger.info("Initializing database connection...")
        self.db = DatabaseWriter(DATABASE_URL)

        if not self.db.test_connection():
            logger.error("Database connection test failed. Exiting.")
            sys.exit(1)

        # Load configuration (now that db is initialized, can read from db)
        kit_configs = self.load_config()

        # Initialize HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0
            ),
            timeout=httpx.Timeout(REQUEST_TIMEOUT),
            follow_redirects=True
        )
        logger.info("HTTP client initialized with connection pooling")

        # Create kit collectors
        enabled_kits = [k for k in kit_configs if k.get('enabled', True)]
        logger.info(f"Starting collectors for {len(enabled_kits)} enabled kits")

        if not enabled_kits:
            logger.warning("No kits configured. Waiting for kits to be added via API...")

        for kit_config in enabled_kits:
            collector = KitCollector(kit_config, self.db, self.client)
            self.kits.append(collector)

        # Start collector tasks
        for kit in self.kits:
            task = asyncio.create_task(kit.run())
            self.tasks.append(task)

        logger.info(f"Collector service started with {len(self.tasks)} active collectors")

        # Start health monitoring task
        health_task = asyncio.create_task(self.monitor_health())
        self.tasks.append(health_task)

        # Start kit reload task (for dynamic kit management)
        if USE_DB_KITS:
            reload_task = asyncio.create_task(self.kit_reload_loop())
            self.tasks.append(reload_task)

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Wait for all tasks to complete
        logger.info("Waiting for collector tasks to complete...")
        await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("All collector tasks completed")

    async def kit_reload_loop(self):
        """Periodically check for kit configuration changes in the database"""
        logger.info(f"Kit reload loop started (interval: {KIT_RELOAD_INTERVAL}s)")

        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(KIT_RELOAD_INTERVAL)

                if shutdown_event.is_set():
                    break

                # Reload kits from database
                stats = await self.reload_kits()

                # Log only if there were changes
                if stats.get('added', 0) > 0 or stats.get('removed', 0) > 0:
                    logger.info(f"Kit configuration updated: +{stats['added']}/-{stats['removed']}")

            except Exception as e:
                logger.error(f"Error in kit reload loop: {e}")
                await asyncio.sleep(10)  # Wait before retrying

        logger.info("Kit reload loop stopped")

    async def monitor_health(self):
        """Periodically log health statistics for all kits"""
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(60)  # Log every minute

                if shutdown_event.is_set():
                    break

                logger.info("=== Kit Health Status ===")
                for collector in self.kits:
                    if collector.health:
                        kit_id = collector._get_kit_id()
                        collector.health.mark_stale()
                        stats = collector.health.get_stats()
                        logger.info(
                            f"Kit {kit_id}: {stats['status']} | "
                            f"Success rate: {stats['success_rate']} | "
                            f"Requests: {stats['total_requests']} "
                            f"(OK: {stats['successful_requests']}, Failed: {stats['failed_requests']})"
                        )
                        if stats['last_error']:
                            logger.info(f"  Last error: {stats['last_error']}")
                logger.info("=" * 40)

            except Exception as e:
                logger.error(f"Error in health monitoring: {e}")

    async def shutdown(self):
        """Gracefully shutdown the service"""
        logger.info("Initiating graceful shutdown...")
        shutdown_event.set()

        # Close HTTP client
        if self.client:
            await self.client.aclose()
            logger.info("HTTP client closed")

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
    service = CollectorService(KITS_CONFIG)

    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Collector service stopped")


if __name__ == '__main__':
    main()
