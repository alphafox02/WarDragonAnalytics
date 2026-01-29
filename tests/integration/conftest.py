#!/usr/bin/env python3
"""
Integration Test Fixtures for WarDragon Analytics

Provides Docker-based test fixtures for full-stack integration testing.
Tests use a real TimescaleDB instance via Docker Compose.

Requirements:
- Docker and Docker Compose must be installed and running
- Run tests with: pytest -m integration
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Generator, AsyncGenerator
import subprocess
import pytest
import asyncpg
import httpx
from sqlalchemy import create_engine, text


# Test database configuration
TEST_DB_HOST = os.getenv("TEST_DB_HOST", "localhost")
TEST_DB_PORT = os.getenv("TEST_DB_PORT", "5432")
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "wardragon")
TEST_DB_USER = os.getenv("TEST_DB_USER", "wardragon")
TEST_DB_PASSWORD = os.getenv("TEST_DB_PASSWORD", "test_password")
TEST_DATABASE_URL = f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"

# Test API configuration
TEST_API_HOST = os.getenv("TEST_API_HOST", "localhost")
TEST_API_PORT = os.getenv("TEST_API_PORT", "8090")
TEST_API_URL = f"http://{TEST_API_HOST}:{TEST_API_PORT}"


@pytest.fixture(scope="session")
def docker_compose_file():
    """Path to the test docker-compose file."""
    return "docker-compose.test.yml"


@pytest.fixture(scope="session")
def docker_services():
    """
    Ensure Docker Compose services are running for the test session.

    This fixture starts the test stack (TimescaleDB, API, Collector) and
    ensures they are healthy before running tests.
    """
    compose_file = "docker-compose.test.yml"
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    compose_path = os.path.join(project_dir, compose_file)

    if not os.path.exists(compose_path):
        pytest.skip(f"Docker Compose file not found: {compose_path}")

    # Start services
    print("\n🐳 Starting Docker Compose services...")
    try:
        subprocess.run(
            ["docker-compose", "-f", compose_file, "up", "-d"],
            cwd=project_dir,
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to start Docker services: {e.stderr}")

    # Wait for services to be healthy
    print("⏳ Waiting for services to become healthy...")
    max_wait = 60  # seconds
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            # Check database
            engine = create_engine(TEST_DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()

            # Check API
            response = httpx.get(f"{TEST_API_URL}/health", timeout=5)
            if response.status_code == 200:
                print("PASS All services are healthy!")
                break
        except Exception:
            time.sleep(2)
    else:
        # Cleanup on failure
        subprocess.run(
            ["docker-compose", "-f", compose_file, "down", "-v"],
            cwd=project_dir,
            capture_output=True
        )
        pytest.fail("Services failed to become healthy within timeout")

    yield

    # Teardown: stop and remove containers
    print("\n🧹 Stopping Docker Compose services...")
    subprocess.run(
        ["docker-compose", "-f", compose_file, "down", "-v"],
        cwd=project_dir,
        capture_output=True
    )


@pytest.fixture
async def db_pool(docker_services) -> AsyncGenerator[asyncpg.Pool, None]:
    """
    Async database connection pool for tests.

    Provides a connection pool to TimescaleDB for direct database operations.
    """
    pool = await asyncpg.create_pool(
        TEST_DATABASE_URL,
        min_size=2,
        max_size=5,
        command_timeout=30
    )

    yield pool

    await pool.close()


@pytest.fixture
async def db_conn(db_pool) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Single database connection for tests.

    Acquires a connection from the pool for test operations.
    """
    async with db_pool.acquire() as conn:
        yield conn


@pytest.fixture
async def clean_database(db_conn):
    """
    Clean all data from test database tables before each test.

    This fixture ensures each test starts with a clean slate.
    Runs before each test that uses it.
    """
    # Delete data from all tables
    await db_conn.execute("DELETE FROM system_health")
    await db_conn.execute("DELETE FROM signals")
    await db_conn.execute("DELETE FROM drones")
    await db_conn.execute("DELETE FROM kits")

    # Reset sequences if any
    # Note: Our tables don't use sequences, but keeping this for future-proofing

    yield

    # Optional: cleanup after test (can be used for debugging)
    # Comment out the deletes below to preserve data for debugging failed tests


@pytest.fixture
def api_client(docker_services) -> Generator[httpx.Client, None, None]:
    """
    Synchronous HTTP client for API testing.

    Provides a configured HTTP client for making requests to the test API.
    """
    with httpx.Client(base_url=TEST_API_URL, timeout=30.0) as client:
        yield client


@pytest.fixture
async def async_api_client(docker_services) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Async HTTP client for API testing.

    Provides an async HTTP client for concurrent API testing.
    """
    async with httpx.AsyncClient(base_url=TEST_API_URL, timeout=30.0) as client:
        yield client


@pytest.fixture
async def sample_kits(db_conn) -> list[dict]:
    """
    Insert sample kit configurations into the database.

    Returns:
        List of kit dictionaries with their configuration.
    """
    kits = [
        {
            "kit_id": "test-kit-001",
            "name": "Test Kit Alpha",
            "location": "Test Site A",
            "api_url": "http://test-kit-001:8088",
            "status": "online",
            "last_seen": datetime.now(timezone.utc)
        },
        {
            "kit_id": "test-kit-002",
            "name": "Test Kit Bravo",
            "location": "Test Site B",
            "api_url": "http://test-kit-002:8088",
            "status": "online",
            "last_seen": datetime.now(timezone.utc)
        },
        {
            "kit_id": "test-kit-003",
            "name": "Test Kit Charlie",
            "location": "Test Site C",
            "api_url": "http://test-kit-003:8088",
            "status": "offline",
            "last_seen": datetime.now(timezone.utc)
        }
    ]

    for kit in kits:
        await db_conn.execute(
            """
            INSERT INTO kits (kit_id, name, location, api_url, status, last_seen)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            kit["kit_id"], kit["name"], kit["location"],
            kit["api_url"], kit["status"], kit["last_seen"]
        )

    return kits


@pytest.fixture
async def sample_drones(db_conn, sample_kits) -> list[dict]:
    """
    Insert sample drone tracks into the database.

    Creates diverse drone data including:
    - DJI drones (DroneID) and Remote ID drones
    - Generic drones
    - Aircraft (ADS-B)
    - Various locations and timestamps

    Returns:
        List of drone dictionaries with their data.
    """
    now = datetime.now(timezone.utc)

    drones = [
        # DJI Mavic 3 from test-kit-001
        {
            "time": now,
            "kit_id": "test-kit-001",
            "drone_id": "DJI-001",
            "lat": 37.7749,
            "lon": -122.4194,
            "alt": 120.5,
            "speed": 15.2,
            "heading": 180.0,
            "pilot_lat": 37.7740,
            "pilot_lon": -122.4180,
            "home_lat": 37.7740,
            "home_lon": -122.4180,
            "mac": "AA:BB:CC:DD:EE:01",
            "rssi": -65,
            "freq": 2437.0,
            "ua_type": "Quadcopter",
            "operator_id": "OP-12345",
            "rid_make": "DJI",
            "rid_model": "Mavic 3",
            "rid_source": "ble",
            "track_type": "drone"
        },
        # DJI Mini 4 Pro from test-kit-002
        {
            "time": now,
            "kit_id": "test-kit-002",
            "drone_id": "DJI-002",
            "lat": 37.7850,
            "lon": -122.4100,
            "alt": 85.0,
            "speed": 8.5,
            "heading": 90.0,
            "pilot_lat": 37.7845,
            "pilot_lon": -122.4090,
            "mac": "AA:BB:CC:DD:EE:02",
            "rssi": -70,
            "rid_make": "DJI",
            "rid_model": "Mini 4 Pro",
            "rid_source": "wifi",
            "track_type": "drone"
        },
        # Autel EVO II from test-kit-001
        {
            "time": now,
            "kit_id": "test-kit-001",
            "drone_id": "AUTEL-001",
            "lat": 37.7650,
            "lon": -122.4300,
            "alt": 150.0,
            "speed": 12.0,
            "heading": 270.0,
            "rid_make": "Autel",
            "rid_model": "EVO II",
            "track_type": "drone"
        },
        # Aircraft (ADS-B) from test-kit-002
        {
            "time": now,
            "kit_id": "test-kit-002",
            "drone_id": "A1B2C3",
            "lat": 37.8000,
            "lon": -122.4000,
            "alt": 3000.0,
            "speed": 150.0,
            "heading": 45.0,
            "track_type": "aircraft"
        },
        # Same DJI-001 detected by test-kit-002 (multi-kit tracking)
        {
            "time": now,
            "kit_id": "test-kit-002",
            "drone_id": "DJI-001",
            "lat": 37.7749,
            "lon": -122.4194,
            "alt": 120.5,
            "speed": 15.2,
            "heading": 180.0,
            "mac": "AA:BB:CC:DD:EE:01",
            "rssi": -75,  # Weaker signal from farther kit
            "rid_make": "DJI",
            "rid_model": "Mavic 3",
            "track_type": "drone"
        }
    ]

    for drone in drones:
        await db_conn.execute(
            """
            INSERT INTO drones (
                time, kit_id, drone_id, lat, lon, alt, speed, heading,
                pilot_lat, pilot_lon, home_lat, home_lon,
                mac, rssi, freq, ua_type, operator_id, caa_id,
                rid_make, rid_model, rid_source, track_type
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12,
                $13, $14, $15, $16, $17, $18,
                $19, $20, $21, $22
            )
            """,
            drone["time"], drone["kit_id"], drone["drone_id"],
            drone.get("lat"), drone.get("lon"), drone.get("alt"),
            drone.get("speed"), drone.get("heading"),
            drone.get("pilot_lat"), drone.get("pilot_lon"),
            drone.get("home_lat"), drone.get("home_lon"),
            drone.get("mac"), drone.get("rssi"), drone.get("freq"),
            drone.get("ua_type"), drone.get("operator_id"), drone.get("caa_id"),
            drone.get("rid_make"), drone.get("rid_model"),
            drone.get("rid_source"), drone["track_type"]
        )

    return drones


@pytest.fixture
async def sample_signals(db_conn, sample_kits) -> list[dict]:
    """
    Insert sample FPV signal detections into the database.

    Creates diverse signal data including:
    - 5.8GHz analog FPV signals
    - DJI digital video signals
    - Various power levels and bandwidths

    Returns:
        List of signal dictionaries with their data.
    """
    now = datetime.now(timezone.utc)

    signals = [
        # Analog FPV on Race Band 1 from test-kit-001
        {
            "time": now,
            "kit_id": "test-kit-001",
            "freq_mhz": 5658.0,
            "power_dbm": -45.5,
            "bandwidth_mhz": 10.0,
            "lat": 37.7749,
            "lon": -122.4194,
            "alt": 50.0,
            "detection_type": "analog"
        },
        # Analog FPV on Race Band 8 from test-kit-001
        {
            "time": now,
            "kit_id": "test-kit-001",
            "freq_mhz": 5917.0,
            "power_dbm": -52.0,
            "bandwidth_mhz": 10.0,
            "lat": 37.7749,
            "lon": -122.4194,
            "detection_type": "analog"
        },
        # DJI digital FPV from test-kit-002
        {
            "time": now,
            "kit_id": "test-kit-002",
            "freq_mhz": 5745.0,
            "power_dbm": -38.0,
            "bandwidth_mhz": 20.0,
            "lat": 37.7850,
            "lon": -122.4100,
            "detection_type": "dji"
        },
        # Weak analog signal from test-kit-002
        {
            "time": now,
            "kit_id": "test-kit-002",
            "freq_mhz": 5800.0,
            "power_dbm": -78.5,
            "bandwidth_mhz": 10.0,
            "detection_type": "analog"
        }
    ]

    for signal in signals:
        await db_conn.execute(
            """
            INSERT INTO signals (
                time, kit_id, freq_mhz, power_dbm, bandwidth_mhz,
                lat, lon, alt, detection_type
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            signal["time"], signal["kit_id"], signal["freq_mhz"],
            signal["power_dbm"], signal["bandwidth_mhz"],
            signal.get("lat"), signal.get("lon"), signal.get("alt"),
            signal["detection_type"]
        )

    return signals


@pytest.fixture
async def sample_health(db_conn, sample_kits) -> list[dict]:
    """
    Insert sample system health metrics into the database.

    Returns:
        List of health metric dictionaries.
    """
    now = datetime.now(timezone.utc)

    health_records = [
        {
            "time": now,
            "kit_id": "test-kit-001",
            "lat": 37.7749,
            "lon": -122.4194,
            "alt": 10.0,
            "cpu_percent": 45.5,
            "memory_percent": 62.3,
            "disk_percent": 38.7,
            "uptime_hours": 72.5,
            "temp_cpu": 55.0,
            "temp_gpu": 48.0
        },
        {
            "time": now,
            "kit_id": "test-kit-002",
            "lat": 37.7850,
            "lon": -122.4100,
            "alt": 15.0,
            "cpu_percent": 38.2,
            "memory_percent": 55.1,
            "disk_percent": 42.0,
            "uptime_hours": 120.0,
            "temp_cpu": 52.0,
            "temp_gpu": 45.0
        }
    ]

    for health in health_records:
        await db_conn.execute(
            """
            INSERT INTO system_health (
                time, kit_id, lat, lon, alt,
                cpu_percent, memory_percent, disk_percent,
                uptime_hours, temp_cpu, temp_gpu
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            health["time"], health["kit_id"],
            health["lat"], health["lon"], health["alt"],
            health["cpu_percent"], health["memory_percent"], health["disk_percent"],
            health["uptime_hours"], health["temp_cpu"], health["temp_gpu"]
        )

    return health_records
