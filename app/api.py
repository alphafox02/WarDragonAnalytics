#!/usr/bin/env python3
"""
WarDragon Analytics FastAPI Web Application

Provides REST API and web UI for multi-kit drone surveillance visualization.

Enterprise Features (Optional):
- Authentication: Set AUTH_ENABLED=true in .env
- Alerting: Configure SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL
- Audit Logging: Always enabled for admin actions
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, Body, Request, Depends, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
import asyncpg
import csv
import io
import re
import math

# Import optional enterprise modules
try:
    from auth import (
        is_auth_enabled, get_auth_status, authenticate_user,
        create_access_token, require_auth, get_current_user,
        set_auth_cookie, clear_auth_cookie, check_rate_limit,
        record_login_attempt, COOKIE_NAME
    )
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    def is_auth_enabled(): return False
    def get_auth_status(): return {"auth_enabled": False}
    async def require_auth(request: Request): return "anonymous"
    async def get_current_user(request: Request): return "anonymous"

try:
    from alerting import alert_manager, AlertSeverity, alert_kit_status
    ALERTING_AVAILABLE = True
except ImportError:
    ALERTING_AVAILABLE = False
    alert_manager = None

try:
    from audit import (
        audit_log, audit_login, audit_logout, audit_kit_action,
        audit_data_export, audit_system_startup, AuditAction
    )
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False
    audit_log = None

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Environment variables
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://wardragon:wardragon@timescaledb:5432/wardragon"
)
API_TITLE = os.environ.get("API_TITLE", "WarDragon Analytics API")
API_VERSION = os.environ.get("API_VERSION", "1.0.0")
MAX_QUERY_RANGE_HOURS = int(os.environ.get("MAX_QUERY_RANGE_HOURS", "168"))  # 7 days default

# Initialize FastAPI app
app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="Multi-kit drone surveillance aggregation and visualization"
)

# Mount static files directory
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Mounted static files from {static_dir}")

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None


# Pydantic models
class KitStatus(BaseModel):
    kit_id: str
    name: str
    location: Optional[str]
    api_url: Optional[str]  # Optional for MQTT-only kits
    last_seen: Optional[datetime]
    status: str  # online, offline, stale
    source: Optional[str] = "http"  # http, mqtt, both


class DroneTrack(BaseModel):
    time: datetime
    kit_id: str
    drone_id: str
    lat: Optional[float]
    lon: Optional[float]
    alt: Optional[float]
    speed: Optional[float]
    heading: Optional[float]
    pilot_lat: Optional[float]
    pilot_lon: Optional[float]
    home_lat: Optional[float]
    home_lon: Optional[float]
    mac: Optional[str]
    rssi: Optional[int]
    freq: Optional[float]
    ua_type: Optional[str]
    operator_id: Optional[str]
    caa_id: Optional[str]
    rid_make: Optional[str]
    rid_model: Optional[str]
    rid_source: Optional[str]
    track_type: Optional[str]


class SignalDetection(BaseModel):
    time: datetime
    kit_id: str
    freq_mhz: float
    power_dbm: Optional[float]
    bandwidth_mhz: Optional[float]
    lat: Optional[float]
    lon: Optional[float]
    alt: Optional[float]
    detection_type: Optional[str]


# Pattern detection models
class DroneLocation(BaseModel):
    lat: float
    lon: float
    kit_id: str
    timestamp: datetime


class RepeatedDrone(BaseModel):
    drone_id: str
    first_seen: datetime
    last_seen: datetime
    appearance_count: int
    locations: List[DroneLocation]


class CoordinatedDrone(BaseModel):
    drone_id: str
    lat: float
    lon: float
    timestamp: datetime
    kit_id: Optional[str]
    rid_make: Optional[str]


class CoordinatedGroup(BaseModel):
    group_id: int
    drone_count: int
    drones: List[dict]
    correlation_score: str


class PilotReuse(BaseModel):
    pilot_identifier: str
    drones: List[dict]
    correlation_method: str


class Anomaly(BaseModel):
    anomaly_type: str
    severity: str
    drone_id: str
    details: dict
    timestamp: datetime


class MultiKitDetection(BaseModel):
    drone_id: str
    kits: List[dict]
    triangulation_possible: bool


class LocationEstimate(BaseModel):
    """Model for RSSI-based location estimation response."""
    drone_id: str
    timestamp: datetime
    actual: Optional[dict] = None  # {"lat": float, "lon": float} if known
    estimated: dict  # {"lat": float, "lon": float}
    error_meters: Optional[float] = None  # Distance from actual if known
    confidence_radius_m: float  # Estimated accuracy radius
    observations: List[dict]  # Kit observations used
    algorithm: str  # "single_kit", "two_kit_weighted", or "trilateration"
    estimated_distances: Optional[List[dict]] = None  # [{"kit_id": str, "distance_m": float}, ...]
    # Spoofing detection fields
    spoofing_score: Optional[float] = None  # 0.0-1.0, higher = more suspicious
    spoofing_suspected: Optional[bool] = None  # True if score > threshold
    spoofing_reason: Optional[str] = None  # Explanation if suspected


# Kit Management Models
class KitCreate(BaseModel):
    """Model for creating a new kit"""
    api_url: str = Field(..., description="Base URL for the kit's DragonSync API (e.g., http://192.168.1.100:8088)")
    name: Optional[str] = Field(None, description="Human-readable name for the kit")
    location: Optional[str] = Field(None, description="Physical location or deployment site")
    enabled: bool = Field(True, description="Whether the kit should be actively polled")


class KitUpdate(BaseModel):
    """Model for updating an existing kit"""
    api_url: Optional[str] = Field(None, description="Base URL for the kit's DragonSync API")
    name: Optional[str] = Field(None, description="Human-readable name for the kit")
    location: Optional[str] = Field(None, description="Physical location or deployment site")
    enabled: Optional[bool] = Field(None, description="Whether the kit should be actively polled")


class KitResponse(BaseModel):
    """Model for kit response"""
    kit_id: str
    name: Optional[str]
    location: Optional[str]
    api_url: str
    last_seen: Optional[datetime]
    status: str
    enabled: bool = True
    created_at: Optional[datetime]


class KitTestResult(BaseModel):
    """Model for kit connection test result"""
    success: bool
    kit_id: Optional[str] = None
    message: str
    response_time_ms: Optional[float] = None


# Startup/Shutdown events
@app.on_event("startup")
async def startup():
    """Initialize database connection pool on startup."""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool on shutdown."""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connection pool closed")


# Helper functions
def parse_time_range(time_range: str) -> tuple[datetime, datetime]:
    """Parse time_range parameter into start and end datetimes."""
    now = datetime.utcnow()

    if time_range == "1h":
        start_time = now - timedelta(hours=1)
    elif time_range == "24h":
        start_time = now - timedelta(hours=24)
    elif time_range == "7d":
        start_time = now - timedelta(days=7)
    elif time_range.startswith("custom:"):
        # Format: custom:YYYY-MM-DDTHH:MM:SS,YYYY-MM-DDTHH:MM:SS
        try:
            _, times = time_range.split(":", 1)
            start_str, end_str = times.split(",", 1)
            start_time = datetime.fromisoformat(start_str)
            end_time = datetime.fromisoformat(end_str)
            return start_time, end_time
        except Exception as e:
            logger.warning(f"Invalid custom time range format: {time_range}, error: {e}")
            start_time = now - timedelta(hours=1)
    else:
        start_time = now - timedelta(hours=1)

    # Enforce max query range
    max_range = timedelta(hours=MAX_QUERY_RANGE_HOURS)
    if now - start_time > max_range:
        start_time = now - max_range

    return start_time, now


async def get_kit_status(kit_id: Optional[str] = None) -> List[dict]:
    """Get status of configured kits, including kits discovered from drone data."""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with db_pool.acquire() as conn:
        # Check if source column exists (for backwards compatibility)
        source_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'kits' AND column_name = 'source'
            )
        """)

        # Get registered kits from kits table
        if kit_id:
            if source_exists:
                query = """
                    SELECT kit_id, name, location, api_url, last_seen, status, created_at,
                           COALESCE(source, 'http') as source
                    FROM kits
                    WHERE kit_id = $1
                """
            else:
                query = """
                    SELECT kit_id, name, location, api_url, last_seen, status, created_at,
                           'http' as source
                    FROM kits
                    WHERE kit_id = $1
                """
            rows = await conn.fetch(query, kit_id)
        else:
            if source_exists:
                query = """
                    SELECT kit_id, name, location, api_url, last_seen, status, created_at,
                           COALESCE(source, 'http') as source
                    FROM kits
                    ORDER BY name
                """
            else:
                query = """
                    SELECT kit_id, name, location, api_url, last_seen, status, created_at,
                           'http' as source
                    FROM kits
                    ORDER BY name
                """
            rows = await conn.fetch(query)

        # Build dict of registered kits
        kits_dict = {}
        now = datetime.now(timezone.utc)
        for row in rows:
            kit = dict(row)
            if kit["last_seen"]:
                # Handle both timezone-aware and naive datetimes from DB
                last_seen = kit["last_seen"]
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                time_since_seen = (now - last_seen).total_seconds()
                if time_since_seen < 30:
                    kit["status"] = "online"
                elif time_since_seen < 120:
                    kit["status"] = "stale"
                else:
                    kit["status"] = "offline"
            else:
                kit["status"] = "unknown"
            kits_dict[kit["kit_id"]] = kit

        # Also discover kits from drone data (last 7 days) that aren't registered
        # This catches kits that have data but weren't formally registered
        if not kit_id:
            discovered_query = """
                SELECT DISTINCT kit_id, MAX(time) as last_seen
                FROM drones
                WHERE time > NOW() - INTERVAL '7 days'
                  AND kit_id IS NOT NULL
                GROUP BY kit_id
            """
            discovered_rows = await conn.fetch(discovered_query)

            for row in discovered_rows:
                discovered_kit_id = row["kit_id"]
                if discovered_kit_id and discovered_kit_id not in kits_dict:
                    # Create a discovered kit entry
                    last_seen = row["last_seen"]
                    if last_seen:
                        if last_seen.tzinfo is None:
                            last_seen = last_seen.replace(tzinfo=timezone.utc)
                        time_since_seen = (now - last_seen).total_seconds()
                    else:
                        time_since_seen = float('inf')

                    if time_since_seen < 30:
                        status = "online"
                    elif time_since_seen < 120:
                        status = "stale"
                    else:
                        status = "offline"

                    kits_dict[discovered_kit_id] = {
                        "kit_id": discovered_kit_id,
                        "name": f"Discovered: {discovered_kit_id}",
                        "location": None,
                        "api_url": None,
                        "last_seen": last_seen,
                        "status": status,
                        "created_at": None,
                        "source": "discovered"  # Special source indicating auto-discovered from data
                    }

        # Sort by name and return as list
        kits = sorted(kits_dict.values(), key=lambda k: k.get("name") or k.get("kit_id") or "")
        return kits


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint for Docker healthcheck."""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database pool not initialized")

    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection failed: {e}")


@app.get("/api/kits")
async def list_kits(kit_id: Optional[str] = Query(None, description="Filter by specific kit ID")):
    """
    List all configured kits with their status.

    Returns:
        List of kit objects with status, last seen time, etc.
    """
    try:
        kits = await get_kit_status(kit_id)
        return {"kits": kits, "count": len(kits)}
    except Exception as e:
        logger.error(f"Failed to list kits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Kit Management Admin Endpoints
# =============================================================================

async def _ensure_enabled_column():
    """Ensure the 'enabled' column exists in the kits table (migration-safe)."""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            # Check if column exists
            exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'kits' AND column_name = 'enabled'
                )
            """)
            if not exists:
                await conn.execute("""
                    ALTER TABLE kits ADD COLUMN enabled BOOLEAN DEFAULT TRUE
                """)
                logger.info("Added 'enabled' column to kits table")
    except Exception as e:
        logger.warning(f"Could not add enabled column (may already exist): {e}")


async def _test_kit_connection(api_url: str) -> KitTestResult:
    """Test connection to a kit's API and retrieve its kit_id."""
    import httpx
    import time

    api_url = api_url.rstrip('/')
    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{api_url}/status")
            response_time = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                kit_id = data.get('kit_id') or data.get('uid')
                return KitTestResult(
                    success=True,
                    kit_id=kit_id,
                    message=f"Successfully connected to kit",
                    response_time_ms=round(response_time, 2)
                )
            else:
                return KitTestResult(
                    success=False,
                    message=f"Kit returned HTTP {response.status_code}",
                    response_time_ms=round(response_time, 2)
                )
    except httpx.TimeoutException:
        return KitTestResult(
            success=False,
            message="Connection timed out after 10 seconds"
        )
    except httpx.ConnectError as e:
        return KitTestResult(
            success=False,
            message=f"Connection refused or unreachable: {str(e)}"
        )
    except Exception as e:
        return KitTestResult(
            success=False,
            message=f"Connection failed: {str(e)}"
        )


def _generate_kit_id(api_url: str) -> str:
    """Generate a temporary kit_id from the API URL."""
    # Extract host from URL
    match = re.search(r'://([^:/]+)', api_url)
    if match:
        host = match.group(1)
        # Replace dots with dashes for cleaner ID
        return f"kit-{host.replace('.', '-')}"
    return f"kit-{hash(api_url) % 10000}"


@app.post("/api/admin/kits", response_model=dict)
async def create_kit(request: Request, kit: KitCreate, user: str = Depends(require_auth)):
    """
    Add a new kit to the system.

    The kit will be tested for connectivity, and if successful, will be added
    to the database. The collector will automatically start polling this kit.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    client_ip = request.client.host if request.client else None

    await _ensure_enabled_column()

    # Normalize URL
    api_url = kit.api_url.rstrip('/')
    if not api_url.startswith('http'):
        api_url = f"http://{api_url}"

    # Test connection to the kit
    test_result = await _test_kit_connection(api_url)

    # Use discovered kit_id or generate one
    kit_id = test_result.kit_id or _generate_kit_id(api_url)

    try:
        async with db_pool.acquire() as conn:
            # Check if kit already exists
            existing = await conn.fetchval(
                "SELECT kit_id FROM kits WHERE kit_id = $1 OR api_url = $2",
                kit_id, api_url
            )
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Kit already exists with ID: {existing}"
                )

            # Insert the new kit
            await conn.execute("""
                INSERT INTO kits (kit_id, name, api_url, location, status, enabled, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
            """, kit_id, kit.name or kit_id, api_url, kit.location,
                'online' if test_result.success else 'offline', kit.enabled)

        logger.info(f"Created new kit: {kit_id} ({api_url})")

        # Audit log
        if AUDIT_AVAILABLE:
            await audit_kit_action(
                AuditAction.KIT_CREATED, kit_id, user, success=True,
                details={"api_url": api_url, "name": kit.name},
                client_ip=client_ip
            )

        return {
            "success": True,
            "kit_id": kit_id,
            "message": f"Kit created successfully. {'Connection test passed.' if test_result.success else 'Warning: Initial connection test failed.'}",
            "connection_test": test_result.dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create kit: {e}")
        if AUDIT_AVAILABLE:
            await audit_kit_action(
                AuditAction.KIT_CREATED, kit.api_url, user, success=False,
                details={"error": str(e)},
                client_ip=client_ip
            )
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/kits/{kit_id}", response_model=dict)
async def update_kit(request: Request, kit_id: str, kit: KitUpdate, user: str = Depends(require_auth)):
    """
    Update an existing kit's configuration.

    Only provided fields will be updated; null fields are ignored.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    client_ip = request.client.host if request.client else None

    await _ensure_enabled_column()

    try:
        async with db_pool.acquire() as conn:
            # Check if kit exists
            existing = await conn.fetchrow(
                "SELECT * FROM kits WHERE kit_id = $1", kit_id
            )
            if not existing:
                raise HTTPException(status_code=404, detail=f"Kit not found: {kit_id}")

            # Build update query dynamically
            updates = []
            params = []
            param_idx = 1

            if kit.api_url is not None:
                api_url = kit.api_url.rstrip('/')
                if not api_url.startswith('http'):
                    api_url = f"http://{api_url}"
                updates.append(f"api_url = ${param_idx}")
                params.append(api_url)
                param_idx += 1

            if kit.name is not None:
                updates.append(f"name = ${param_idx}")
                params.append(kit.name)
                param_idx += 1

            if kit.location is not None:
                updates.append(f"location = ${param_idx}")
                params.append(kit.location)
                param_idx += 1

            if kit.enabled is not None:
                updates.append(f"enabled = ${param_idx}")
                params.append(kit.enabled)
                param_idx += 1

            if not updates:
                return {"success": True, "message": "No changes requested", "kit_id": kit_id}

            # Add kit_id as last parameter
            params.append(kit_id)

            query = f"UPDATE kits SET {', '.join(updates)} WHERE kit_id = ${param_idx}"
            await conn.execute(query, *params)

        logger.info(f"Updated kit: {kit_id}")

        # Audit log
        if AUDIT_AVAILABLE:
            await audit_kit_action(
                AuditAction.KIT_UPDATED, kit_id, user, success=True,
                details={"updates": kit.dict(exclude_none=True)},
                client_ip=client_ip
            )

        return {"success": True, "message": "Kit updated successfully", "kit_id": kit_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update kit: {e}")
        if AUDIT_AVAILABLE:
            await audit_kit_action(
                AuditAction.KIT_UPDATED, kit_id, user, success=False,
                details={"error": str(e)},
                client_ip=client_ip
            )
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/kits/{kit_id}", response_model=dict)
async def delete_kit(
    request: Request,
    kit_id: str,
    delete_data: bool = Query(False, description="Also delete all drone/signal data from this kit"),
    user: str = Depends(require_auth)
):
    """
    Remove a kit from the system.

    By default, only removes the kit configuration. Use delete_data=true to
    also remove all drone tracks and signal detections from this kit.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    client_ip = request.client.host if request.client else None

    try:
        async with db_pool.acquire() as conn:
            # Check if kit exists
            existing = await conn.fetchval(
                "SELECT kit_id FROM kits WHERE kit_id = $1", kit_id
            )
            if not existing:
                raise HTTPException(status_code=404, detail=f"Kit not found: {kit_id}")

            # Optionally delete associated data
            deleted_data = {}
            if delete_data:
                # Delete from drones table
                drone_result = await conn.execute(
                    "DELETE FROM drones WHERE kit_id = $1", kit_id
                )
                deleted_data['drones'] = int(drone_result.split()[-1]) if drone_result else 0

                # Delete from signals table
                signal_result = await conn.execute(
                    "DELETE FROM signals WHERE kit_id = $1", kit_id
                )
                deleted_data['signals'] = int(signal_result.split()[-1]) if signal_result else 0

                # Delete from system_health table
                health_result = await conn.execute(
                    "DELETE FROM system_health WHERE kit_id = $1", kit_id
                )
                deleted_data['health_records'] = int(health_result.split()[-1]) if health_result else 0

            # Delete the kit
            await conn.execute("DELETE FROM kits WHERE kit_id = $1", kit_id)

        logger.info(f"Deleted kit: {kit_id} (delete_data={delete_data})")

        # Audit log
        if AUDIT_AVAILABLE:
            await audit_kit_action(
                AuditAction.KIT_DELETED, kit_id, user, success=True,
                details={"delete_data": delete_data, "deleted_data": deleted_data if delete_data else None},
                client_ip=client_ip
            )

        response = {
            "success": True,
            "message": f"Kit {kit_id} deleted successfully",
            "kit_id": kit_id
        }
        if delete_data:
            response["deleted_data"] = deleted_data

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete kit: {e}")
        if AUDIT_AVAILABLE:
            await audit_kit_action(
                AuditAction.KIT_DELETED, kit_id, user, success=False,
                details={"error": str(e)},
                client_ip=client_ip
            )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/kits/test", response_model=KitTestResult)
async def test_kit_connection(api_url: str = Query(..., description="API URL to test")):
    """
    Test connectivity to a kit's API without adding it.

    Useful for verifying the URL before adding a new kit.
    """
    # Normalize URL
    api_url = api_url.rstrip('/')
    if not api_url.startswith('http'):
        api_url = f"http://{api_url}"

    return await _test_kit_connection(api_url)


@app.post("/api/admin/kits/{kit_id}/test", response_model=KitTestResult)
async def test_existing_kit(kit_id: str):
    """
    Test connectivity to an existing kit.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT api_url FROM kits WHERE kit_id = $1", kit_id
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Kit not found: {kit_id}")

    return await _test_kit_connection(row['api_url'])


@app.get("/api/admin/kits/reload-status")
async def get_reload_status():
    """
    Check the status of kit configuration reload.

    Returns information about which kits are configured and their polling status.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT kit_id, name, api_url, status, enabled, last_seen
                FROM kits
                ORDER BY name
            """)

        kits = []
        for row in rows:
            kit = dict(row)
            kit['enabled'] = kit.get('enabled', True)
            kits.append(kit)

        return {
            "total_kits": len(kits),
            "enabled_kits": sum(1 for k in kits if k.get('enabled', True)),
            "online_kits": sum(1 for k in kits if k['status'] == 'online'),
            "kits": kits
        }
    except Exception as e:
        logger.error(f"Failed to get reload status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/drones")
async def query_drones(
    time_range: str = Query("1h", description="Time range: 1h, 24h, 7d, or custom:START,END"),
    kit_id: Optional[str] = Query(None, description="Filter by kit ID (comma-separated for multiple)"),
    rid_make: Optional[str] = Query(None, description="Filter by RID make (e.g., DJI, Autel)"),
    track_type: Optional[str] = Query(None, description="Filter by track type: drone or aircraft"),
    limit: int = Query(1000, description="Maximum number of results", le=10000),
    deduplicate: bool = Query(True, description="Return only latest detection per drone_id (default: true)")
):
    """
    Query drone/aircraft tracks with filters.

    By default, returns only the latest detection per drone_id to avoid
    showing the same drone multiple times. Set deduplicate=false to get
    all raw detections.

    Returns:
        List of drone tracks matching the filter criteria.
        - drones: List of track records (deduplicated by default)
        - count: Number of unique drones
        - total_detections: Total number of raw detections in time range
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        start_time, end_time = parse_time_range(time_range)

        # Build base WHERE clause
        where_clauses = ["time >= $1 AND time <= $2"]
        params = [start_time, end_time]
        param_counter = 3

        # Add kit_id filter
        if kit_id:
            kit_ids = [k.strip() for k in kit_id.split(",")]
            where_clauses.append(f"kit_id = ANY(${param_counter})")
            params.append(kit_ids)
            param_counter += 1

        # Add rid_make filter
        if rid_make:
            where_clauses.append(f"rid_make = ${param_counter}")
            params.append(rid_make)
            param_counter += 1

        # Add track_type filter
        if track_type:
            where_clauses.append(f"track_type = ${param_counter}")
            params.append(track_type)
            param_counter += 1

        where_clause = " AND ".join(where_clauses)

        if deduplicate:
            # Return only the latest detection per drone_id
            # This prevents showing the same drone 13 times
            query = f"""
                SELECT DISTINCT ON (drone_id)
                    time, kit_id, drone_id, lat, lon, alt, speed, heading,
                    pilot_lat, pilot_lon, home_lat, home_lon, mac, rssi, freq,
                    ua_type, operator_id, caa_id, rid_make, rid_model, rid_source, track_type
                FROM drones
                WHERE {where_clause}
                ORDER BY drone_id, time DESC
                LIMIT ${param_counter}
            """
        else:
            # Return all raw detections (original behavior)
            query = f"""
                SELECT
                    time, kit_id, drone_id, lat, lon, alt, speed, heading,
                    pilot_lat, pilot_lon, home_lat, home_lon, mac, rssi, freq,
                    ua_type, operator_id, caa_id, rid_make, rid_model, rid_source, track_type
                FROM drones
                WHERE {where_clause}
                ORDER BY time DESC
                LIMIT ${param_counter}
            """
        params.append(limit)

        # Also get total detection count for the time range
        count_query = f"""
            SELECT
                COUNT(*) AS total_detections,
                COUNT(DISTINCT drone_id) AS unique_drones
            FROM drones
            WHERE {where_clause}
        """
        count_params = params[:-1]  # Exclude limit

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            count_row = await conn.fetchrow(count_query, *count_params)

        drones = [dict(row) for row in rows]

        return {
            "drones": drones,
            "count": count_row['unique_drones'],  # Number of unique drones
            "total_detections": count_row['total_detections'],  # Total raw detections
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Failed to query drones: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/drones/{drone_id}/track")
async def get_drone_track(
    drone_id: str,
    time_range: str = Query("1h", description="Time range: 1h, 24h, 7d, or custom:START,END"),
    limit: int = Query(500, description="Maximum number of track points", le=2000)
):
    """
    Get track history (flight path) for a specific drone.

    Returns all position records for the drone within the time range,
    ordered chronologically for drawing a flight path polyline.

    Returns:
        - track: List of position records with time, lat, lon, alt, speed
        - drone_id: The requested drone ID
        - point_count: Number of track points returned
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        start_time, end_time = parse_time_range(time_range)

        query = """
            SELECT
                time, kit_id, lat, lon, alt, speed, heading, rssi
            FROM drones
            WHERE drone_id = $1
              AND time >= $2 AND time <= $3
              AND lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY time ASC
            LIMIT $4
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, drone_id, start_time, end_time, limit)

        track = [dict(row) for row in rows]

        return {
            "drone_id": drone_id,
            "track": track,
            "point_count": len(track),
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Failed to get drone track for {drone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/signals")
async def query_signals(
    time_range: str = Query("1h", description="Time range: 1h, 24h, 7d, or custom:START,END"),
    kit_id: Optional[str] = Query(None, description="Filter by kit ID (comma-separated for multiple)"),
    detection_type: Optional[str] = Query(None, description="Filter by detection type: analog or dji"),
    limit: int = Query(1000, description="Maximum number of results", le=10000)
):
    """
    Query FPV signal detections with filters.

    Returns:
        List of signal detections matching the filter criteria.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        start_time, end_time = parse_time_range(time_range)

        # Build query
        query = """
            SELECT
                time, kit_id, freq_mhz, power_dbm, bandwidth_mhz,
                lat, lon, alt, detection_type
            FROM signals
            WHERE time >= $1 AND time <= $2
        """
        params = [start_time, end_time]
        param_counter = 3

        # Add kit_id filter
        if kit_id:
            kit_ids = [k.strip() for k in kit_id.split(",")]
            query += f" AND kit_id = ANY(${param_counter})"
            params.append(kit_ids)
            param_counter += 1

        # Add detection_type filter
        if detection_type:
            query += f" AND detection_type = ${param_counter}"
            params.append(detection_type)
            param_counter += 1

        query += f" ORDER BY time DESC LIMIT ${param_counter}"
        params.append(limit)

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        signals = [dict(row) for row in rows]

        return {
            "signals": signals,
            "count": len(signals),
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Failed to query signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/csv")
async def export_csv(
    request: Request,
    time_range: str = Query("1h", description="Time range: 1h, 24h, 7d, or custom:START,END"),
    kit_id: Optional[str] = Query(None, description="Filter by kit ID (comma-separated for multiple)"),
    rid_make: Optional[str] = Query(None, description="Filter by RID make"),
    track_type: Optional[str] = Query(None, description="Filter by track type: drone or aircraft"),
    user: str = Depends(require_auth)
):
    """
    Export drones to CSV format.

    Returns:
        CSV file with drone tracks.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    client_ip = request.client.host if request.client else None

    try:
        start_time, end_time = parse_time_range(time_range)

        # Build query (same as /api/drones but without limit)
        query = """
            SELECT
                time, kit_id, drone_id, lat, lon, alt, speed, heading,
                pilot_lat, pilot_lon, home_lat, home_lon, mac, rssi, freq,
                ua_type, operator_id, caa_id, rid_make, rid_model, rid_source, track_type
            FROM drones
            WHERE time >= $1 AND time <= $2
        """
        params = [start_time, end_time]
        param_counter = 3

        if kit_id:
            kit_ids = [k.strip() for k in kit_id.split(",")]
            query += f" AND kit_id = ANY(${param_counter})"
            params.append(kit_ids)
            param_counter += 1

        if rid_make:
            query += f" AND rid_make = ${param_counter}"
            params.append(rid_make)
            param_counter += 1

        if track_type:
            query += f" AND track_type = ${param_counter}"
            params.append(track_type)
            param_counter += 1

        query += " ORDER BY time DESC"

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        # Generate CSV
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

        csv_content = output.getvalue()
        output.close()

        # Return as downloadable file
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"wardragon_drones_{timestamp}.csv"

        # Audit log export
        if AUDIT_AVAILABLE:
            await audit_data_export(
                user=user,
                export_type="csv",
                record_count=len(rows),
                filters={"time_range": time_range, "kit_id": kit_id, "rid_make": rid_make, "track_type": track_type},
                client_ip=client_ip
            )

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Failed to export CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/repeated-drones")
async def get_repeated_drones(
    time_window_hours: int = Query(24, description="Time window in hours", ge=1, le=168),
    min_appearances: int = Query(2, description="Minimum number of appearances", ge=2)
):
    """
    Find drones seen multiple times within the time window.

    Returns:
        List of drones with multiple appearances, including all locations.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        query = """
            WITH recent_drones AS (
                SELECT
                    drone_id,
                    time,
                    kit_id,
                    lat,
                    lon
                FROM drones
                WHERE time >= NOW() - make_interval(hours => $1)
                    AND lat IS NOT NULL
                    AND lon IS NOT NULL
            ),
            drone_counts AS (
                SELECT
                    drone_id,
                    COUNT(*) AS appearance_count,
                    MIN(time) AS first_seen,
                    MAX(time) AS last_seen
                FROM recent_drones
                GROUP BY drone_id
                HAVING COUNT(*) >= $2
            )
            SELECT
                dc.drone_id,
                dc.first_seen,
                dc.last_seen,
                dc.appearance_count,
                json_agg(
                    json_build_object(
                        'lat', rd.lat,
                        'lon', rd.lon,
                        'kit_id', rd.kit_id,
                        'timestamp', rd.time
                    ) ORDER BY rd.time
                ) AS locations
            FROM drone_counts dc
            JOIN recent_drones rd ON dc.drone_id = rd.drone_id
            GROUP BY dc.drone_id, dc.first_seen, dc.last_seen, dc.appearance_count
            ORDER BY dc.appearance_count DESC, dc.last_seen DESC
            LIMIT 100
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, time_window_hours, min_appearances)

        results = [dict(row) for row in rows]

        return {
            "repeated_drones": results,
            "count": len(results),
            "time_window_hours": time_window_hours,
            "min_appearances": min_appearances
        }

    except Exception as e:
        logger.error(f"Failed to query repeated drones: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/coordinated")
async def get_coordinated_drones(
    time_window_minutes: int = Query(60, description="Time window in minutes", ge=1, le=1440),
    distance_threshold_m: float = Query(500, description="Distance threshold in meters", ge=10)
):
    """
    Detect coordinated drone activity using time and location clustering.

    Returns:
        Groups of drones appearing together in time and space.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        # Use the database function for coordinated activity detection
        query = "SELECT detect_coordinated_activity($1, $2) AS groups"

        async with db_pool.acquire() as conn:
            result = await conn.fetchval(query, time_window_minutes, distance_threshold_m)

        # Parse JSON result
        import json
        groups = json.loads(result) if result else []

        return {
            "coordinated_groups": groups,
            "count": len(groups),
            "time_window_minutes": time_window_minutes,
            "distance_threshold_m": distance_threshold_m
        }

    except Exception as e:
        logger.error(f"Failed to detect coordinated activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/pilot-reuse")
async def get_pilot_reuse(
    time_window_hours: int = Query(24, description="Time window in hours", ge=1, le=168),
    proximity_threshold_m: float = Query(50, description="Proximity threshold in meters", ge=10)
):
    """
    Find potential operator reuse across different drone IDs.

    Uses two methods:
    1. Exact operator_id matches
    2. Pilot locations within proximity threshold

    Returns:
        List of operators/locations with associated drones.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        # Method 1: Exact operator_id matches
        operator_query = """
            WITH recent_drones AS (
                SELECT
                    drone_id,
                    operator_id,
                    time,
                    pilot_lat,
                    pilot_lon
                FROM drones
                WHERE time >= NOW() - make_interval(hours => $1)
                    AND operator_id IS NOT NULL
            )
            SELECT
                operator_id AS pilot_identifier,
                'operator_id' AS correlation_method,
                json_agg(
                    json_build_object(
                        'drone_id', drone_id,
                        'timestamp', time,
                        'pilot_lat', pilot_lat,
                        'pilot_lon', pilot_lon
                    ) ORDER BY time DESC
                ) AS drones,
                COUNT(DISTINCT drone_id) AS drone_count
            FROM recent_drones
            GROUP BY operator_id
            HAVING COUNT(DISTINCT drone_id) >= 2
            ORDER BY drone_count DESC
        """

        # Method 2: Proximity-based clustering
        proximity_query = """
            WITH recent_pilots AS (
                SELECT DISTINCT ON (drone_id)
                    drone_id,
                    pilot_lat,
                    pilot_lon,
                    time
                FROM drones
                WHERE time >= NOW() - make_interval(hours => $1)
                    AND pilot_lat IS NOT NULL
                    AND pilot_lon IS NOT NULL
                    AND operator_id IS NULL
                ORDER BY drone_id, time DESC
            ),
            pilot_pairs AS (
                SELECT
                    p1.drone_id AS drone1_id,
                    p2.drone_id AS drone2_id,
                    p1.pilot_lat AS pilot1_lat,
                    p1.pilot_lon AS pilot1_lon,
                    calculate_distance_m(p1.pilot_lat, p1.pilot_lon, p2.pilot_lat, p2.pilot_lon) AS distance_m
                FROM recent_pilots p1
                CROSS JOIN recent_pilots p2
                WHERE p1.drone_id < p2.drone_id
                    AND calculate_distance_m(p1.pilot_lat, p1.pilot_lon, p2.pilot_lat, p2.pilot_lon) <= $2
            )
            SELECT
                CONCAT('PILOT_', ROUND(AVG(rp.pilot_lat)::numeric, 4), '_', ROUND(AVG(rp.pilot_lon)::numeric, 4)) AS pilot_identifier,
                'proximity' AS correlation_method,
                json_agg(
                    json_build_object(
                        'drone_id', rp.drone_id,
                        'timestamp', rp.time,
                        'pilot_lat', rp.pilot_lat,
                        'pilot_lon', rp.pilot_lon
                    ) ORDER BY rp.time DESC
                ) AS drones,
                COUNT(DISTINCT rp.drone_id) AS drone_count
            FROM pilot_pairs pp
            JOIN recent_pilots rp ON rp.drone_id = pp.drone1_id OR rp.drone_id = pp.drone2_id
            GROUP BY pp.drone1_id
            HAVING COUNT(DISTINCT rp.drone_id) >= 2
            ORDER BY drone_count DESC
        """

        async with db_pool.acquire() as conn:
            operator_rows = await conn.fetch(operator_query, time_window_hours)
            proximity_rows = await conn.fetch(proximity_query, time_window_hours, proximity_threshold_m)

        results = [dict(row) for row in operator_rows] + [dict(row) for row in proximity_rows]

        return {
            "pilot_reuse": results,
            "count": len(results),
            "time_window_hours": time_window_hours,
            "proximity_threshold_m": proximity_threshold_m
        }

    except Exception as e:
        logger.error(f"Failed to detect pilot reuse: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/anomalies")
async def get_anomalies(
    time_window_hours: int = Query(1, description="Time window in hours", ge=1, le=24)
):
    """
    Detect anomalous drone behavior.

    Detects:
    - Speed anomalies (>30 m/s)
    - Altitude anomalies (>400m for drones)
    - Rapid altitude changes (>50m in 10 seconds)
    - Multiple appearances (repeated sightings)

    Returns:
        List of anomalies with type, severity, and details.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        query = """
            WITH recent_drones AS (
                SELECT
                    drone_id,
                    time,
                    kit_id,
                    lat,
                    lon,
                    alt,
                    speed,
                    heading,
                    track_type,
                    rid_make,
                    rid_model,
                    LAG(alt) OVER (PARTITION BY drone_id ORDER BY time) AS prev_alt,
                    LAG(time) OVER (PARTITION BY drone_id ORDER BY time) AS prev_time
                FROM drones
                WHERE time >= NOW() - make_interval(hours => $1)
                    AND track_type = 'drone'
            ),
            speed_anomalies AS (
                SELECT
                    'speed' AS anomaly_type,
                    CASE
                        WHEN speed > 50 THEN 'critical'
                        WHEN speed > 40 THEN 'high'
                        ELSE 'medium'
                    END AS severity,
                    drone_id,
                    json_build_object(
                        'speed_ms', speed,
                        'lat', lat,
                        'lon', lon,
                        'kit_id', kit_id,
                        'rid_make', rid_make
                    ) AS details,
                    time AS timestamp
                FROM recent_drones
                WHERE speed > 30
            ),
            altitude_anomalies AS (
                SELECT
                    'altitude' AS anomaly_type,
                    CASE
                        WHEN alt > 500 THEN 'critical'
                        WHEN alt > 450 THEN 'high'
                        ELSE 'medium'
                    END AS severity,
                    drone_id,
                    json_build_object(
                        'altitude_m', alt,
                        'lat', lat,
                        'lon', lon,
                        'kit_id', kit_id,
                        'rid_make', rid_make
                    ) AS details,
                    time AS timestamp
                FROM recent_drones
                WHERE alt > 400
            ),
            rapid_altitude_changes AS (
                SELECT
                    'rapid_altitude_change' AS anomaly_type,
                    CASE
                        WHEN ABS(alt - prev_alt) > 100 THEN 'critical'
                        WHEN ABS(alt - prev_alt) > 75 THEN 'high'
                        ELSE 'medium'
                    END AS severity,
                    drone_id,
                    json_build_object(
                        'altitude_change_m', ABS(alt - prev_alt),
                        'time_diff_seconds', EXTRACT(EPOCH FROM (time - prev_time)),
                        'from_alt', prev_alt,
                        'to_alt', alt,
                        'lat', lat,
                        'lon', lon,
                        'kit_id', kit_id
                    ) AS details,
                    time AS timestamp
                FROM recent_drones
                WHERE prev_alt IS NOT NULL
                    AND prev_time IS NOT NULL
                    AND ABS(alt - prev_alt) > 50
                    AND EXTRACT(EPOCH FROM (time - prev_time)) <= 10
            )
            SELECT * FROM speed_anomalies
            UNION ALL
            SELECT * FROM altitude_anomalies
            UNION ALL
            SELECT * FROM rapid_altitude_changes
            ORDER BY timestamp DESC, severity DESC
            LIMIT 200
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, time_window_hours)

        results = [dict(row) for row in rows]

        return {
            "anomalies": results,
            "count": len(results),
            "time_window_hours": time_window_hours
        }

    except Exception as e:
        logger.error(f"Failed to detect anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/multi-kit")
async def get_multi_kit_detections(
    time_window_minutes: int = Query(15, description="Time window in minutes", ge=1, le=10080)
):
    """
    Find drones detected by multiple kits.

    Useful for triangulation and correlation analysis.

    Returns:
        List of drones with detections from multiple kits.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        # Query finds drones detected by multiple kits and returns ONE entry per kit
        # (the most recent observation from each kit for meaningful time comparison)
        query = """
            WITH recent_detections AS (
                -- Get all detections in the time window
                SELECT
                    drone_id,
                    kit_id,
                    lat,
                    lon,
                    alt,
                    freq,
                    rssi,
                    time,
                    rid_make,
                    rid_model
                FROM drones
                WHERE time >= NOW() - make_interval(mins => $1)
                    AND lat IS NOT NULL
                    AND lon IS NOT NULL
                    AND kit_id IS NOT NULL
            ),
            latest_per_kit AS (
                -- For each (drone_id, kit_id), get only the MOST RECENT observation
                -- This ensures times are close together for meaningful comparison
                SELECT DISTINCT ON (drone_id, kit_id)
                    drone_id,
                    kit_id,
                    lat,
                    lon,
                    alt,
                    freq,
                    rssi,
                    time,
                    rid_make,
                    rid_model
                FROM recent_detections
                ORDER BY drone_id, kit_id, time DESC, rssi DESC NULLS LAST
            ),
            multi_kit_groups AS (
                -- Group by drone and aggregate unique kits
                SELECT
                    drone_id,
                    COUNT(*) AS kit_count,
                    json_agg(
                        json_build_object(
                            'kit_id', kit_id,
                            'rssi', rssi,
                            'freq', freq,
                            'timestamp', time,
                            'lat', lat,
                            'lon', lon,
                            'alt', alt
                        ) ORDER BY rssi DESC NULLS LAST
                    ) AS kits,
                    MAX(rid_make) AS rid_make,
                    MAX(rid_model) AS rid_model,
                    MAX(time) AS latest_detection
                FROM latest_per_kit
                GROUP BY drone_id
                HAVING COUNT(*) >= 2
            )
            SELECT
                drone_id,
                kits,
                kit_count,
                (kit_count >= 3) AS triangulation_possible,
                rid_make,
                rid_model,
                latest_detection
            FROM multi_kit_groups
            ORDER BY kit_count DESC, latest_detection DESC
            LIMIT 100
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, time_window_minutes)

        # Parse the kits JSON field (asyncpg returns json_agg as string)
        results = []
        for row in rows:
            row_dict = dict(row)
            # Parse kits JSON string to actual array
            if isinstance(row_dict.get('kits'), str):
                import json
                try:
                    row_dict['kits'] = json.loads(row_dict['kits'])
                except json.JSONDecodeError:
                    row_dict['kits'] = []
            results.append(row_dict)

        return {
            "multi_kit_detections": results,
            "count": len(results),
            "time_window_minutes": time_window_minutes
        }

    except Exception as e:
        logger.error(f"Failed to query multi-kit detections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# RSSI-Based Location Estimation
# =============================================================================

def calculate_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS coordinates in meters using Haversine formula."""
    R = 6371000  # Earth's radius in meters

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def rssi_to_weight(rssi: float) -> float:
    """
    Convert RSSI value to a weight for centroid calculation.

    Stronger signals (less negative RSSI) get higher weights.
    Uses an exponential model since signal strength decreases exponentially with distance.

    RSSI scale (typical):
    - -40 to -55 dBm: Excellent (very close)
    - -56 to -65 dBm: Good
    - -66 to -75 dBm: Fair
    - -76 to -85 dBm: Weak
    - -86+ dBm: Very weak (far away)
    """
    if rssi is None or rssi == 0:
        return 0.1  # Minimum weight for missing data

    # Normalize RSSI to 0-1 range (approx -40 to -100 dBm range)
    # Higher (less negative) RSSI = stronger signal = closer = higher weight
    normalized = (rssi + 100) / 60  # Maps -100 to 0, -40 to 1
    normalized = max(0.01, min(1.0, normalized))  # Clamp to [0.01, 1.0]

    # Use exponential weighting to emphasize stronger signals
    # This helps because signal strength drops off rapidly with distance
    weight = normalized ** 2  # Square for stronger emphasis on close signals

    return max(0.01, weight)


def calculate_spoofing_score(error_meters: float, confidence_radius_m: float, num_kits: int) -> dict:
    """
    Calculate a spoofing score based on how much the reported position differs
    from the RSSI-estimated position.

    The score indicates how likely it is that the drone is spoofing its GPS location.

    Logic:
    - If error < confidence_radius: Normal (score near 0)
    - If error is 2-3x confidence_radius: Suspicious (score 0.3-0.6)
    - If error is 4x+ confidence_radius: Likely spoofing (score 0.7-1.0)

    The score is also adjusted by the number of kits - more kits = more confidence
    in the RSSI estimate, so deviations are more significant.

    Args:
        error_meters: Distance between reported and estimated position
        confidence_radius_m: RSSI estimation confidence radius
        num_kits: Number of kits that observed the drone

    Returns:
        dict with spoofing_score (0.0-1.0), spoofing_suspected (bool), spoofing_reason (str)
    """
    if error_meters is None or confidence_radius_m <= 0:
        return {
            "spoofing_score": None,
            "spoofing_suspected": None,
            "spoofing_reason": None
        }

    # Calculate ratio of error to expected accuracy
    error_ratio = error_meters / confidence_radius_m

    # Base score from error ratio
    # - ratio < 1.0: score near 0 (within expected accuracy)
    # - ratio 1.0-2.0: score 0-0.3 (slightly outside expected)
    # - ratio 2.0-4.0: score 0.3-0.6 (suspicious)
    # - ratio > 4.0: score 0.6-1.0 (likely spoofing)
    if error_ratio <= 1.0:
        base_score = error_ratio * 0.15  # 0 to 0.15
    elif error_ratio <= 2.0:
        base_score = 0.15 + (error_ratio - 1.0) * 0.15  # 0.15 to 0.3
    elif error_ratio <= 4.0:
        base_score = 0.3 + (error_ratio - 2.0) * 0.15  # 0.3 to 0.6
    else:
        base_score = 0.6 + min(0.4, (error_ratio - 4.0) * 0.05)  # 0.6 to 1.0

    # Adjust for number of kits - more kits = higher confidence in estimate
    # With 2 kits: confidence factor = 0.7 (moderate confidence)
    # With 3 kits: confidence factor = 0.85 (good confidence)
    # With 4+ kits: confidence factor = 1.0 (high confidence)
    if num_kits >= 4:
        kit_factor = 1.0
    elif num_kits == 3:
        kit_factor = 0.85
    elif num_kits == 2:
        kit_factor = 0.7
    else:
        kit_factor = 0.5  # Single kit is unreliable

    # Final score combines base score with kit confidence
    score = min(1.0, base_score * kit_factor)
    score = round(score, 2)

    # Determine if spoofing is suspected (threshold: 0.5)
    suspected = score >= 0.5

    # Generate reason string
    reason = None
    if suspected:
        if error_ratio > 4.0:
            reason = f"Position error ({error_meters:.0f}m) is {error_ratio:.1f}x the expected accuracy ({confidence_radius_m:.0f}m)"
        else:
            reason = f"Position error ({error_meters:.0f}m) significantly exceeds expected accuracy ({confidence_radius_m:.0f}m)"
    elif score >= 0.3:
        reason = f"Position deviation ({error_meters:.0f}m) is outside expected accuracy - warrants monitoring"

    return {
        "spoofing_score": score,
        "spoofing_suspected": suspected,
        "spoofing_reason": reason
    }


def rssi_to_distance_meters(rssi: float, tx_power: float = 0, path_loss_exp: float = 2.5) -> float:
    """
    Convert RSSI to estimated distance using log-distance path loss model.

    Formula: RSSI = TxPower - 10 * n * log10(d)
    Rearranged: d = 10^((TxPower - RSSI) / (10 * n))

    Args:
        rssi: Received signal strength in dBm (e.g., -65)
        tx_power: Transmitter power in dBm (default 0 dBm for drone)
        path_loss_exp: Path loss exponent (2.0=free space, 2.5-3.0=outdoor, 4.0=indoor)

    Returns:
        Estimated distance in meters
    """
    if rssi is None or rssi >= tx_power:
        return 10  # Minimum distance if signal is very strong or invalid

    # Calculate distance
    exponent = (tx_power - rssi) / (10 * path_loss_exp)
    distance = math.pow(10, exponent)

    # Clamp to reasonable range (10m to 10km)
    return max(10, min(10000, distance))


def estimate_location_from_rssi(observations: List[dict]) -> dict:
    """
    Estimate drone location using RSSI-based trilateration from kit positions.

    This algorithm estimates where a drone is located based on:
    - Kit positions (where the receivers are located)
    - RSSI values (signal strength from each kit)

    The algorithm:
    1. Converts RSSI to estimated distance from each kit
    2. For 2 kits: Uses weighted position along the line between kits
    3. For 3+ kits: Uses iterative trilateration to find best-fit position

    This is the core algorithm for:
    - Encrypted drones (no GPS broadcast, only RSSI/freq available)
    - Spoofing detection (compare estimated vs reported position)

    Args:
        observations: List of dicts with keys: kit_lat, kit_lon, rssi

    Returns:
        dict with estimated lat/lon, confidence radius, and distance estimates
    """
    if not observations:
        return None

    # Filter valid observations with kit positions
    valid_obs = [o for o in observations if o.get('kit_lat') and o.get('kit_lon')]

    if not valid_obs:
        return None

    if len(valid_obs) == 1:
        # Single kit - can only say "drone is somewhere near this kit"
        obs = valid_obs[0]
        dist = rssi_to_distance_meters(obs.get('rssi', -70))
        return {
            "lat": obs['kit_lat'],
            "lon": obs['kit_lon'],
            "confidence_radius_m": round(dist),
            "method": "single_kit",
            "estimated_distances": [{"kit_id": obs.get('kit_id'), "distance_m": round(dist)}]
        }

    if len(valid_obs) == 2:
        # Two kits - estimate position along line between them
        return _trilaterate_2_kits(valid_obs)

    # Three or more kits - proper trilateration
    return _trilaterate_3plus_kits(valid_obs)


def _trilaterate_2_kits(observations: List[dict]) -> dict:
    """
    Estimate location with 2 kits using distance-weighted positioning.

    With only 2 reference points, we can't solve for a unique position.
    We estimate a point along the line between the kits, weighted by
    the inverse of estimated distances (closer kit pulls the estimate toward it).
    """
    obs1, obs2 = observations[0], observations[1]

    # Get kit positions
    lat1, lon1 = obs1['kit_lat'], obs1['kit_lon']
    lat2, lon2 = obs2['kit_lat'], obs2['kit_lon']

    # Estimate distances from RSSI
    dist1 = rssi_to_distance_meters(obs1.get('rssi', -70))
    dist2 = rssi_to_distance_meters(obs2.get('rssi', -70))

    # Calculate distance between kits
    kit_separation = calculate_distance_meters(lat1, lon1, lat2, lon2)

    if kit_separation < 10:
        # Kits too close together - use midpoint
        return {
            "lat": (lat1 + lat2) / 2,
            "lon": (lon1 + lon2) / 2,
            "confidence_radius_m": round(max(dist1, dist2)),
            "method": "two_kit_midpoint",
            "estimated_distances": [
                {"kit_id": obs1.get('kit_id'), "distance_m": round(dist1)},
                {"kit_id": obs2.get('kit_id'), "distance_m": round(dist2)}
            ]
        }

    # Weight by inverse distance (closer = higher weight)
    w1 = 1.0 / (dist1 + 1)
    w2 = 1.0 / (dist2 + 1)
    total_weight = w1 + w2

    # Weighted position along the line between kits
    est_lat = (lat1 * w1 + lat2 * w2) / total_weight
    est_lon = (lon1 * w1 + lon2 * w2) / total_weight

    # Confidence radius - larger uncertainty with only 2 kits
    # Could be on either side of the line between kits
    avg_dist = (dist1 + dist2) / 2
    confidence_radius = max(100, min(avg_dist * 0.5, kit_separation / 2))

    return {
        "lat": est_lat,
        "lon": est_lon,
        "confidence_radius_m": round(confidence_radius, 1),
        "method": "two_kit_weighted",
        "estimated_distances": [
            {"kit_id": obs1.get('kit_id'), "distance_m": round(dist1)},
            {"kit_id": obs2.get('kit_id'), "distance_m": round(dist2)}
        ],
        "kit_separation_m": round(kit_separation)
    }


def _trilaterate_3plus_kits(observations: List[dict]) -> dict:
    """
    Estimate location with 3+ kits using iterative trilateration.

    With 3+ reference points, we can solve for the drone position.
    Uses gradient descent to find the point that minimizes
    the sum of squared errors between estimated and actual distances.
    """
    # Extract kit positions and estimated distances
    kits = []
    for obs in observations:
        dist = rssi_to_distance_meters(obs.get('rssi', -70))
        kits.append({
            'lat': obs['kit_lat'],
            'lon': obs['kit_lon'],
            'dist': dist,
            'kit_id': obs.get('kit_id')
        })

    # Initial guess: centroid of kit positions weighted by inverse distance
    total_weight = sum(1.0 / (k['dist'] + 1) for k in kits)
    est_lat = sum(k['lat'] / (k['dist'] + 1) for k in kits) / total_weight
    est_lon = sum(k['lon'] / (k['dist'] + 1) for k in kits) / total_weight

    # Iterative refinement using gradient descent
    # Convert to approximate meters for gradient calculation
    # ~111km per degree latitude, ~85km per degree longitude at mid-latitudes
    meters_per_deg_lat = 111000
    meters_per_deg_lon = 85000

    learning_rate = 0.5  # Step size in meters equivalent

    for iteration in range(200):
        grad_lat = 0
        grad_lon = 0

        for kit in kits:
            # Current distance from estimate to this kit
            current_dist = calculate_distance_meters(est_lat, est_lon, kit['lat'], kit['lon'])
            if current_dist < 1:
                current_dist = 1

            # Error: difference between current distance and expected distance
            error = current_dist - kit['dist']

            # Direction from estimate to kit (in degrees)
            dlat = kit['lat'] - est_lat
            dlon = kit['lon'] - est_lon

            # Gradient: move toward kit if we're too far, away if too close
            # Normalize by current distance
            grad_lat += error * dlat / current_dist
            grad_lon += error * dlon / current_dist

        # Update position (move in direction that reduces error)
        # Scale by learning rate and convert to degrees
        est_lat += (learning_rate * grad_lat) / meters_per_deg_lat
        est_lon += (learning_rate * grad_lon) / meters_per_deg_lon

        # Reduce learning rate over iterations for convergence
        if iteration > 50:
            learning_rate *= 0.99

    # Calculate final errors
    errors = []
    for kit in kits:
        actual_dist = calculate_distance_meters(est_lat, est_lon, kit['lat'], kit['lon'])
        error = abs(actual_dist - kit['dist'])
        errors.append(error)

    # Confidence radius based on mean error and number of kits
    mean_error = sum(errors) / len(errors)
    # More kits = more confidence
    confidence_factor = 2.0 / len(kits)  # 3 kits = 0.67, 4 kits = 0.5
    confidence_radius = mean_error * confidence_factor + 50  # Base 50m minimum
    confidence_radius = max(50, min(2000, confidence_radius))

    return {
        "lat": est_lat,
        "lon": est_lon,
        "confidence_radius_m": round(confidence_radius, 1),
        "method": "trilateration",
        "estimated_distances": [
            {"kit_id": k['kit_id'], "distance_m": round(k['dist'])} for k in kits
        ],
        "mean_error_m": round(mean_error, 1)
    }


@app.get("/api/analysis/estimate-location/{drone_id}", response_model=LocationEstimate)
async def estimate_drone_location(
    drone_id: str,
    timestamp: Optional[str] = Query(None, description="ISO timestamp for the observation (default: latest)"),
    time_window_seconds: int = Query(30, description="Time window around timestamp", ge=5, le=300)
):
    """
    Estimate drone location using RSSI-based triangulation from multiple kits.

    This endpoint uses a weighted centroid algorithm where each observing kit's
    position is weighted by its signal strength (RSSI). Kits with stronger signals
    are assumed to be closer to the drone and receive higher weights.

    Use cases:
    - Test estimation algorithm against drones with known GPS positions
    - Spoofing detection: Compare reported GPS against RSSI-estimated position
    - Future: Estimate location for encrypted drones with only RSSI data

    The response includes:
    - estimated: Calculated position based on RSSI weights
    - actual: Drone's reported GPS position (if available) for comparison
    - error_meters: Distance between estimated and actual (for algorithm validation)
    - confidence_radius_m: Estimated accuracy of the position
    - observations: Kit data used for the calculation
    - spoofing_score: 0.0-1.0 indicating likelihood of GPS spoofing
    - spoofing_suspected: True if spoofing_score exceeds threshold (0.5)
    - spoofing_reason: Explanation when spoofing is suspected or warrants monitoring

    Returns:
        LocationEstimate with estimated position, accuracy metrics, and spoofing analysis.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        # Parse timestamp or use current time
        if timestamp:
            try:
                target_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid timestamp format. Use ISO 8601.")
        else:
            target_time = datetime.utcnow()

        # Get drone observations within time window
        time_start = target_time - timedelta(seconds=time_window_seconds)
        time_end = target_time + timedelta(seconds=time_window_seconds)

        async with db_pool.acquire() as conn:
            # Get drone observations from different kits
            drone_query = """
                SELECT
                    d.kit_id,
                    d.rssi,
                    d.freq,
                    d.time,
                    d.lat as drone_lat,
                    d.lon as drone_lon,
                    d.alt as drone_alt
                FROM drones d
                WHERE d.drone_id = $1
                  AND d.time >= $2 AND d.time <= $3
                ORDER BY d.time DESC
            """
            drone_rows = await conn.fetch(drone_query, drone_id, time_start, time_end)

            if not drone_rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No observations found for drone {drone_id} in time window"
                )

            # Get unique kit IDs that observed this drone
            kit_ids = list(set(row['kit_id'] for row in drone_rows if row['kit_id']))

            if len(kit_ids) < 1:
                raise HTTPException(
                    status_code=400,
                    detail="No kit observations with RSSI data available"
                )

            # Get kit positions from system_health table (closest to observation time)
            kit_positions = {}
            for kit_id in kit_ids:
                kit_pos_query = """
                    SELECT lat, lon, alt, time
                    FROM system_health
                    WHERE kit_id = $1
                      AND lat IS NOT NULL AND lon IS NOT NULL
                      AND lat != 0 AND lon != 0
                    ORDER BY ABS(EXTRACT(EPOCH FROM (time - $2)))
                    LIMIT 1
                """
                kit_row = await conn.fetchrow(kit_pos_query, kit_id, target_time)
                if kit_row:
                    kit_positions[kit_id] = {
                        "lat": float(kit_row['lat']),
                        "lon": float(kit_row['lon']),
                        "alt": float(kit_row['alt']) if kit_row['alt'] else 0
                    }

        if not kit_positions:
            raise HTTPException(
                status_code=400,
                detail="No kit position data available. Ensure kits report GPS in system_health."
            )

        # Build observations list with kit positions and RSSI
        # Use the best (most recent or strongest) observation per kit
        observations = []
        kit_observations = {}

        for row in drone_rows:
            kit_id = row['kit_id']
            if kit_id not in kit_positions:
                continue

            # Keep best observation per kit (highest RSSI)
            current_rssi = row['rssi'] or -100
            if kit_id not in kit_observations or (kit_observations[kit_id].get('rssi') or -100) < current_rssi:
                kit_observations[kit_id] = {
                    "kit_id": kit_id,
                    "kit_lat": kit_positions[kit_id]['lat'],
                    "kit_lon": kit_positions[kit_id]['lon'],
                    "rssi": row['rssi'],
                    "freq": row['freq'],
                    "time": row['time'].isoformat() if row['time'] else None,
                    "drone_lat": float(row['drone_lat']) if row['drone_lat'] else None,
                    "drone_lon": float(row['drone_lon']) if row['drone_lon'] else None
                }

        observations = list(kit_observations.values())

        if len(observations) < 1:
            raise HTTPException(
                status_code=400,
                detail="Insufficient observations with kit positions for estimation"
            )

        # Get actual drone position (for comparison) from the closest observation
        actual_pos = None
        closest_obs = min(drone_rows, key=lambda r: abs((r['time'] - target_time).total_seconds()) if r['time'] else float('inf'))
        if closest_obs['drone_lat'] and closest_obs['drone_lon']:
            actual_pos = {
                "lat": float(closest_obs['drone_lat']),
                "lon": float(closest_obs['drone_lon'])
            }

        # Estimate location using weighted centroid
        estimate = estimate_location_from_rssi(observations)

        if not estimate:
            raise HTTPException(
                status_code=500,
                detail="Failed to calculate location estimate"
            )

        # Calculate error if we have actual position
        error_meters = None
        if actual_pos:
            error_meters = calculate_distance_meters(
                estimate['lat'], estimate['lon'],
                actual_pos['lat'], actual_pos['lon']
            )
            error_meters = round(error_meters, 1)

        # Calculate spoofing score based on error vs expected accuracy
        spoofing_result = calculate_spoofing_score(
            error_meters,
            estimate['confidence_radius_m'],
            len(observations)
        )

        return LocationEstimate(
            drone_id=drone_id,
            timestamp=target_time,
            actual=actual_pos,
            estimated={"lat": estimate['lat'], "lon": estimate['lon']},
            error_meters=error_meters,
            confidence_radius_m=estimate['confidence_radius_m'],
            observations=observations,
            algorithm=estimate['method'],
            estimated_distances=estimate.get('estimated_distances'),
            spoofing_score=spoofing_result['spoofing_score'],
            spoofing_suspected=spoofing_result['spoofing_suspected'],
            spoofing_reason=spoofing_result['spoofing_reason']
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to estimate drone location: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Security-Focused Pattern Detection Endpoints
# =============================================================================

@app.get("/api/patterns/security-alerts")
async def get_security_alerts(
    time_window_hours: int = Query(4, description="Time window in hours", ge=1, le=24)
):
    """
    Get consolidated security alerts with threat scoring.

    Combines rapid descent, night activity, low-slow patterns, and high speed
    into a single threat assessment view.

    Use cases:
    - Prison/facility perimeter monitoring
    - Critical infrastructure protection
    - Neighborhood surveillance

    Returns:
        List of flagged drone activity with threat scores and levels.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        query = """
            SELECT * FROM security_alerts
            WHERE time >= NOW() - make_interval(hours => $1)
            ORDER BY threat_score DESC, time DESC
            LIMIT 500
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, time_window_hours)

        alerts = [dict(row) for row in rows]

        # Count by threat level
        level_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for alert in alerts:
            level = alert.get('threat_level', 'low')
            if level in level_counts:
                level_counts[level] += 1

        return {
            "alerts": alerts,
            "count": len(alerts),
            "time_window_hours": time_window_hours,
            "threat_summary": level_counts
        }

    except Exception as e:
        logger.error(f"Failed to query security alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/loitering")
async def get_loitering_activity(
    lat: float = Query(..., description="Center latitude of monitored area"),
    lon: float = Query(..., description="Center longitude of monitored area"),
    radius_m: float = Query(500, description="Radius in meters to monitor", ge=50, le=5000),
    min_duration_minutes: int = Query(5, description="Minimum time in area to flag", ge=1, le=120),
    time_window_hours: int = Query(24, description="Time window to search", ge=1, le=168)
):
    """
    Detect drones loitering in a specific geographic area.

    Useful for monitoring:
    - Prison perimeters (contraband drops)
    - Secure facilities (surveillance attempts)
    - Neighborhoods (suspicious activity)
    - Critical infrastructure

    Returns:
        List of drones that stayed within the radius for longer than min_duration.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        query = """SELECT detect_loitering($1, $2, $3, $4, $5)"""

        async with db_pool.acquire() as conn:
            result = await conn.fetchval(query, lat, lon, radius_m, min_duration_minutes, time_window_hours)

        loitering = result if result else []

        return {
            "loitering_drones": loitering,
            "count": len(loitering) if loitering else 0,
            "search_area": {
                "center_lat": lat,
                "center_lon": lon,
                "radius_m": radius_m
            },
            "parameters": {
                "min_duration_minutes": min_duration_minutes,
                "time_window_hours": time_window_hours
            }
        }

    except Exception as e:
        logger.error(f"Failed to query loitering activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/rapid-descent")
async def get_rapid_descent_events(
    time_window_minutes: int = Query(60, description="Time window in minutes", ge=5, le=1440),
    min_descent_rate_mps: float = Query(5.0, description="Minimum descent rate (m/s)", ge=1.0, le=50.0),
    min_descent_m: float = Query(30.0, description="Minimum descent (meters)", ge=10.0, le=500.0)
):
    """
    Detect rapid altitude descents that may indicate payload drops.

    Common pattern for:
    - Contraband delivery to prisons
    - Drug drops
    - Illegal cargo delivery

    A rapid descent while hovering (low horizontal speed) is particularly suspicious.

    Returns:
        List of descent events with threat assessment.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        query = """SELECT detect_rapid_descent($1, $2, $3)"""

        async with db_pool.acquire() as conn:
            result = await conn.fetchval(query, time_window_minutes, min_descent_rate_mps, min_descent_m)

        descents = result if result else []

        # Count likely payload drops (rapid descent + low horizontal speed)
        payload_drops = sum(1 for d in descents if d.get('possible_payload_drop', False)) if descents else 0

        return {
            "descent_events": descents,
            "count": len(descents) if descents else 0,
            "possible_payload_drops": payload_drops,
            "parameters": {
                "time_window_minutes": time_window_minutes,
                "min_descent_rate_mps": min_descent_rate_mps,
                "min_descent_m": min_descent_m
            }
        }

    except Exception as e:
        logger.error(f"Failed to query rapid descent events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/night-activity")
async def get_night_activity(
    time_window_hours: int = Query(24, description="Time window in hours", ge=1, le=168),
    night_start_hour: int = Query(22, description="Hour when night begins (0-23)", ge=0, le=23),
    night_end_hour: int = Query(5, description="Hour when night ends (0-23)", ge=0, le=23)
):
    """
    Detect drone activity during night hours.

    Night flights near secure facilities are often unauthorized and indicate:
    - Contraband delivery attempts
    - Surveillance activities
    - Unauthorized reconnaissance

    Returns:
        List of drones active during night hours with risk assessment.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        query = """SELECT detect_night_activity($1, $2, $3)"""

        async with db_pool.acquire() as conn:
            result = await conn.fetchval(query, time_window_hours, night_start_hour, night_end_hour)

        activity = result if result else []

        # Count by risk level
        risk_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        if activity:
            for drone in activity:
                level = drone.get('risk_level', 'low')
                if level in risk_counts:
                    risk_counts[level] += 1

        return {
            "night_activity": activity,
            "count": len(activity) if activity else 0,
            "risk_summary": risk_counts,
            "parameters": {
                "time_window_hours": time_window_hours,
                "night_start_hour": night_start_hour,
                "night_end_hour": night_end_hour
            }
        }

    except Exception as e:
        logger.error(f"Failed to query night activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# LLM-Powered Natural Language Query Endpoints
# =============================================================================

# LLM Service instance (lazy initialization)
_llm_service = None


def get_llm_service():
    """Get or create LLM service instance."""
    global _llm_service
    if _llm_service is None:
        from llm_service import LLMService
        _llm_service = LLMService(db_pool)
    return _llm_service


class LLMQueryRequest(BaseModel):
    """Request model for LLM query."""
    question: str = Field(..., min_length=3, max_length=1000, description="Natural language question")
    session_id: Optional[str] = Field(None, description="Session ID for conversation context")
    include_summary: bool = Field(True, description="Include natural language summary of results")


class LLMQueryResponse(BaseModel):
    """Response model for LLM query."""
    success: bool
    response: Optional[str] = None  # Natural language response/summary
    results: List[dict] = []  # Query result data
    row_count: int = 0
    query_executed: Optional[str] = None  # SQL query for transparency
    session_id: Optional[str] = None
    error: Optional[str] = None


class LLMStatusResponse(BaseModel):
    """Response model for LLM status check."""
    available: bool
    message: Optional[str] = None  # Error message if not available
    ollama_url: Optional[str] = None
    model: Optional[str] = None
    available_models: Optional[List[str]] = None  # If Ollama running but model missing


@app.get("/api/llm/status", response_model=LLMStatusResponse)
async def get_llm_status():
    """
    Check if the LLM service is available and configured.

    Returns information about:
    - Whether LLM queries are enabled
    - Ollama connectivity status
    - Configured model
    """
    try:
        service = get_llm_service()
        status = await service.is_available()
        return LLMStatusResponse(
            available=status.get("available", False),
            message=status.get("message"),
            ollama_url=status.get("ollama_url"),
            model=status.get("model"),
            available_models=status.get("available_models")
        )
    except Exception as e:
        logger.error(f"Failed to check LLM status: {e}")
        return LLMStatusResponse(
            available=False,
            message=str(e),
            ollama_url=None,
            model=None
        )


@app.post("/api/llm/query", response_model=LLMQueryResponse)
async def llm_query(request: LLMQueryRequest):
    """
    Query drone detection data using natural language.

    Examples:
    - "What drones were seen in the last hour?"
    - "Show me DJI drones flying above 100 meters"
    - "How many unique drones were detected today?"
    - "Any FPV signals on 5800 MHz?"
    - "Which kit has the most detections?"

    The query is converted to safe SQL and executed against the database.
    Results are returned with an optional natural language summary.
    """
    if not db_pool:
        return LLMQueryResponse(
            success=False,
            error="Database unavailable"
        )

    try:
        service = get_llm_service()

        # Check if LLM is available
        status = await service.is_available()
        if not status["available"]:
            return LLMQueryResponse(
                success=False,
                error=f"LLM service unavailable: {status.get('message', 'Unknown error')}"
            )

        # Execute query
        result = await service.query(
            request.question,
            include_summary=request.include_summary
        )

        # Track conversation if session_id provided
        session_id = request.session_id
        if session_id:
            from llm_service import conversation_manager
            conversation_manager.add_turn(session_id, request.question, result)

        # Build natural language response
        if result.success:
            if result.summary:
                response_text = result.summary
            elif result.row_count == 0:
                response_text = f"No results found. {result.query_explanation}"
            else:
                response_text = f"Found {result.row_count} result{'s' if result.row_count != 1 else ''}. {result.query_explanation}"
        else:
            response_text = result.error or "Query failed"

        return LLMQueryResponse(
            success=result.success,
            response=response_text,
            results=result.data,
            row_count=result.row_count,
            query_executed=result.query_sql,
            session_id=session_id,
            error=result.error if not result.success else None
        )

    except Exception as e:
        logger.error(f"LLM query failed: {e}")
        return LLMQueryResponse(
            success=False,
            error=str(e)
        )


@app.get("/api/llm/examples")
async def get_llm_examples():
    """
    Get example queries to help users understand what they can ask.

    Returns categorized example queries for the UI.
    """
    try:
        service = get_llm_service()
        examples = service.get_example_queries()
        return {"examples": examples}
    except Exception as e:
        logger.error(f"Failed to get LLM examples: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/llm/session/{session_id}")
async def clear_llm_session(session_id: str):
    """
    Clear conversation history for a session.

    Use this when starting a new conversation topic.
    """
    try:
        from llm_service import conversation_manager
        conversation_manager.clear_session(session_id)
        return {"success": True, "message": f"Session {session_id} cleared"}
    except Exception as e:
        logger.error(f"Failed to clear session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Authentication Endpoints (Optional - enabled via AUTH_ENABLED=true)
# =============================================================================

class LoginRequest(BaseModel):
    """Login request model."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class LoginResponse(BaseModel):
    """Login response model."""
    success: bool
    message: str
    username: Optional[str] = None


@app.get("/api/auth/status")
async def get_authentication_status():
    """
    Get current authentication status.

    Returns whether auth is enabled and if the current request is authenticated.
    """
    return get_auth_status()


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: Request, credentials: LoginRequest, response: Response):
    """
    Authenticate and create a session.

    Only used when AUTH_ENABLED=true in .env.
    """
    if not is_auth_enabled():
        return LoginResponse(
            success=True,
            message="Authentication not required",
            username="anonymous"
        )

    client_ip = request.client.host if request.client else "unknown"

    # Check rate limiting
    if AUTH_AVAILABLE and not check_rate_limit(client_ip):
        if AUDIT_AVAILABLE:
            await audit_login(credentials.username, False, client_ip, reason="rate_limited")
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later."
        )

    # Authenticate
    if authenticate_user(credentials.username, credentials.password):
        token = create_access_token(credentials.username)
        set_auth_cookie(response, token)

        if AUTH_AVAILABLE:
            record_login_attempt(client_ip, success=True)
        if AUDIT_AVAILABLE:
            await audit_login(credentials.username, True, client_ip)

        return LoginResponse(
            success=True,
            message="Login successful",
            username=credentials.username
        )
    else:
        if AUTH_AVAILABLE:
            record_login_attempt(client_ip, success=False)
        if AUDIT_AVAILABLE:
            await audit_login(credentials.username, False, client_ip, reason="invalid_credentials")

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """
    End the current session.
    """
    if AUTH_AVAILABLE:
        clear_auth_cookie(response)

    user = await get_current_user(request)
    client_ip = request.client.host if request.client else "unknown"

    if AUDIT_AVAILABLE and user != "anonymous":
        await audit_logout(user, client_ip)

    return {"success": True, "message": "Logged out"}


@app.get("/api/auth/me")
async def get_current_user_info(request: Request):
    """
    Get information about the currently authenticated user.
    """
    user = await get_current_user(request)
    return {
        "authenticated": user is not None and user != "anonymous",
        "username": user,
        "auth_required": is_auth_enabled(),
    }


# =============================================================================
# Alerting Endpoints (Optional - enabled via ALERTING_ENABLED=true)
# =============================================================================

@app.get("/api/alerting/status")
async def get_alerting_status():
    """
    Get current alerting configuration status.
    """
    if not ALERTING_AVAILABLE or not alert_manager:
        return {
            "available": False,
            "message": "Alerting module not loaded"
        }
    return {
        "available": True,
        **alert_manager.get_status()
    }


@app.get("/api/alerting/webhooks")
async def list_webhooks(user: str = Depends(require_auth)):
    """
    List configured webhooks (URLs masked for security).
    """
    if not ALERTING_AVAILABLE or not alert_manager:
        return {"webhooks": [], "message": "Alerting not available"}
    return {"webhooks": alert_manager.list_webhooks()}


class WebhookConfig(BaseModel):
    """Webhook configuration model."""
    webhook_type: str = Field(..., description="Type: slack, discord, or generic")
    url: str = Field(..., description="Webhook URL")
    name: Optional[str] = Field(None, description="Display name")
    headers: Optional[dict] = Field(None, description="Custom headers (for generic webhooks)")


@app.post("/api/alerting/webhooks")
async def add_webhook(
    request: Request,
    config: WebhookConfig,
    user: str = Depends(require_auth)
):
    """
    Add a new webhook for alerting.
    """
    if not ALERTING_AVAILABLE or not alert_manager:
        raise HTTPException(status_code=503, detail="Alerting not available")

    alert_manager.add_webhook(
        webhook_type=config.webhook_type,
        url=config.url,
        name=config.name or config.webhook_type,
        headers=config.headers,
    )

    if AUDIT_AVAILABLE:
        from audit import AuditAction, AuditEvent, AuditResult
        event = AuditEvent(
            action=AuditAction.WEBHOOK_ADDED,
            result=AuditResult.SUCCESS,
            user=user,
            resource=config.webhook_type,
            details={"name": config.name},
            client_ip=request.client.host if request.client else None,
        )
        await audit_log.log(event)

    return {"success": True, "message": f"Webhook added: {config.name or config.webhook_type}"}


@app.post("/api/alerting/test")
async def test_alert(user: str = Depends(require_auth)):
    """
    Send a test alert to all configured webhooks.
    """
    if not ALERTING_AVAILABLE or not alert_manager:
        raise HTTPException(status_code=503, detail="Alerting not available")

    from alerting import Alert, AlertType, AlertSeverity

    test_alert = Alert(
        alert_type=AlertType.NEW_DRONE,
        severity=AlertSeverity.INFO,
        title="Test Alert",
        message="This is a test alert from WarDragon Analytics.",
        details={
            "triggered_by": user,
            "test": True,
        },
    )

    success = await alert_manager.send_alert(test_alert)
    return {
        "success": success,
        "message": "Test alert sent" if success else "Failed to send test alert"
    }


# =============================================================================
# Audit Log Endpoints (view-only)
# =============================================================================

@app.get("/api/audit/logs")
async def get_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action type"),
    user: Optional[str] = Query(None, description="Filter by username"),
    limit: int = Query(100, le=1000, description="Maximum results"),
    current_user: str = Depends(require_auth)
):
    """
    Query audit logs (requires authentication if enabled).

    Returns recent administrative actions for compliance and security review.
    """
    if not AUDIT_AVAILABLE or not audit_log:
        return {"logs": [], "message": "Audit logging to database not enabled"}

    try:
        action_enum = AuditAction(action) if action else None
    except ValueError:
        action_enum = None

    logs = await audit_log.query(
        action=action_enum,
        user=user,
        limit=limit,
    )

    return {
        "logs": logs,
        "count": len(logs),
        "limit": limit,
    }


# =============================================================================
# Main UI Endpoint
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_ui(request: Request):
    """
    Serve the main web UI with Leaflet map.

    If authentication is enabled and user is not logged in,
    redirects to login page.

    Returns:
        HTML page with embedded map and filters.
    """
    # Check if auth is required
    if is_auth_enabled():
        user = await get_current_user(request)
        if not user:
            # Redirect to login page (or show login modal)
            # For now, we'll serve the page and let JS handle login
            pass

    template_path = Path(__file__).parent / "templates" / "index.html"

    if not template_path.exists():
        raise HTTPException(status_code=500, detail="Template not found")

    try:
        with open(template_path, "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Failed to serve UI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Startup/Shutdown Hooks for Enterprise Features
# =============================================================================

@app.on_event("startup")
async def enterprise_startup():
    """Initialize enterprise features on startup."""
    # Set up audit log database connection
    if AUDIT_AVAILABLE and audit_log and db_pool:
        audit_log.set_db_pool(db_pool)
        audit_system_startup()

    # Log startup info
    logger.info(f"Enterprise features: auth={AUTH_AVAILABLE and is_auth_enabled()}, "
                f"alerting={ALERTING_AVAILABLE and alert_manager and alert_manager.is_enabled()}, "
                f"audit={AUDIT_AVAILABLE}")


@app.on_event("shutdown")
async def enterprise_shutdown():
    """Clean up enterprise features on shutdown."""
    if ALERTING_AVAILABLE and alert_manager:
        await alert_manager.close()

    if AUDIT_AVAILABLE:
        from audit import audit_system_shutdown
        audit_system_shutdown()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
