#!/usr/bin/env python3
"""
WarDragon Analytics - Audit Logging Module

Provides audit logging for administrative actions:
- Kit management (add, update, delete)
- Configuration changes
- Login/logout events
- Data exports
- Alert configuration changes

Audit logs are stored in:
1. Application log file (always)
2. Database table (if configured)

All audit logging is OPTIONAL but recommended for production.
"""

import os
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# Create separate audit logger
audit_logger = logging.getLogger("audit")

# =============================================================================
# Configuration
# =============================================================================

# Audit logging level
AUDIT_LOG_LEVEL = os.environ.get("AUDIT_LOG_LEVEL", "INFO")

# Audit to database (in addition to file)
AUDIT_TO_DATABASE = os.environ.get("AUDIT_TO_DATABASE", "false").lower() == "true"

# =============================================================================
# Audit Event Types
# =============================================================================

class AuditAction(str, Enum):
    """Types of auditable actions."""
    # Authentication
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"

    # Kit Management
    KIT_CREATED = "kit_created"
    KIT_UPDATED = "kit_updated"
    KIT_DELETED = "kit_deleted"
    KIT_TESTED = "kit_tested"

    # Data Operations
    DATA_EXPORTED = "data_exported"
    DATA_DELETED = "data_deleted"
    QUERY_EXECUTED = "query_executed"

    # Configuration
    CONFIG_CHANGED = "config_changed"
    WEBHOOK_ADDED = "webhook_added"
    WEBHOOK_REMOVED = "webhook_removed"

    # Alerts
    ALERT_SENT = "alert_sent"
    WATCHLIST_ADDED = "watchlist_added"
    WATCHLIST_REMOVED = "watchlist_removed"

    # System
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"


class AuditResult(str, Enum):
    """Result of an audited action."""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


@dataclass
class AuditEvent:
    """Represents an audit log entry."""
    action: AuditAction
    result: AuditResult
    user: str  # Username or IP address
    resource: Optional[str] = None  # What was acted upon (e.g., kit_id)
    details: Dict[str, Any] = field(default_factory=dict)
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "result": self.result.value,
            "user": self.user,
            "resource": self.resource,
            "details": self.details,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


# =============================================================================
# Audit Logger
# =============================================================================

class AuditLog:
    """
    Centralized audit logging with optional database storage.
    """

    def __init__(self):
        self._db_pool = None
        self._setup_file_logger()

    def _setup_file_logger(self):
        """Configure the audit file logger."""
        # Set up audit logger with JSON formatting
        audit_handler = logging.StreamHandler()
        audit_formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "audit": %(message)s}'
        )
        audit_handler.setFormatter(audit_formatter)
        audit_logger.addHandler(audit_handler)
        audit_logger.setLevel(getattr(logging, AUDIT_LOG_LEVEL.upper(), logging.INFO))

    def set_db_pool(self, pool):
        """Set database connection pool for database audit storage."""
        self._db_pool = pool
        if AUDIT_TO_DATABASE:
            logger.info("Audit logging to database enabled")

    async def _write_to_database(self, event: AuditEvent):
        """Write audit event to database."""
        if not self._db_pool or not AUDIT_TO_DATABASE:
            return

        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO audit_log
                    (timestamp, action, result, username, resource, details, client_ip, user_agent)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                    event.timestamp,
                    event.action.value,
                    event.result.value,
                    event.user,
                    event.resource,
                    json.dumps(event.details),
                    event.client_ip,
                    event.user_agent,
                )
        except Exception as e:
            logger.error(f"Failed to write audit event to database: {e}")

    async def log(self, event: AuditEvent):
        """Log an audit event."""
        # Always log to file
        audit_logger.info(event.to_json())

        # Optionally log to database
        if AUDIT_TO_DATABASE and self._db_pool:
            await self._write_to_database(event)

    def log_sync(self, event: AuditEvent):
        """
        Synchronous logging (for non-async contexts).
        Only writes to file, not database.
        """
        audit_logger.info(event.to_json())

    async def query(
        self,
        action: Optional[AuditAction] = None,
        user: Optional[str] = None,
        resource: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[dict]:
        """
        Query audit logs from database.
        Only works if AUDIT_TO_DATABASE is enabled.
        """
        if not self._db_pool or not AUDIT_TO_DATABASE:
            return []

        try:
            query = "SELECT * FROM audit_log WHERE 1=1"
            params = []
            param_idx = 1

            if action:
                query += f" AND action = ${param_idx}"
                params.append(action.value)
                param_idx += 1

            if user:
                query += f" AND username = ${param_idx}"
                params.append(user)
                param_idx += 1

            if resource:
                query += f" AND resource = ${param_idx}"
                params.append(resource)
                param_idx += 1

            if start_time:
                query += f" AND timestamp >= ${param_idx}"
                params.append(start_time)
                param_idx += 1

            if end_time:
                query += f" AND timestamp <= ${param_idx}"
                params.append(end_time)
                param_idx += 1

            query += f" ORDER BY timestamp DESC LIMIT ${param_idx}"
            params.append(limit)

            async with self._db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to query audit logs: {e}")
            return []


# =============================================================================
# Global Audit Log Instance
# =============================================================================

audit_log = AuditLog()


# =============================================================================
# Helper Functions for Common Audit Events
# =============================================================================

async def audit_login(user: str, success: bool, client_ip: str = None,
                      user_agent: str = None, reason: str = None):
    """Audit a login attempt."""
    event = AuditEvent(
        action=AuditAction.LOGIN_SUCCESS if success else AuditAction.LOGIN_FAILED,
        result=AuditResult.SUCCESS if success else AuditResult.FAILURE,
        user=user,
        client_ip=client_ip,
        user_agent=user_agent,
        details={"reason": reason} if reason else {},
    )
    await audit_log.log(event)


async def audit_logout(user: str, client_ip: str = None):
    """Audit a logout."""
    event = AuditEvent(
        action=AuditAction.LOGOUT,
        result=AuditResult.SUCCESS,
        user=user,
        client_ip=client_ip,
    )
    await audit_log.log(event)


async def audit_kit_action(action: AuditAction, kit_id: str, user: str,
                           success: bool, details: dict = None, client_ip: str = None):
    """Audit a kit management action."""
    event = AuditEvent(
        action=action,
        result=AuditResult.SUCCESS if success else AuditResult.FAILURE,
        user=user,
        resource=kit_id,
        details=details or {},
        client_ip=client_ip,
    )
    await audit_log.log(event)


async def audit_data_export(user: str, export_type: str, record_count: int,
                            filters: dict = None, client_ip: str = None):
    """Audit a data export."""
    event = AuditEvent(
        action=AuditAction.DATA_EXPORTED,
        result=AuditResult.SUCCESS,
        user=user,
        details={
            "export_type": export_type,
            "record_count": record_count,
            "filters": filters or {},
        },
        client_ip=client_ip,
    )
    await audit_log.log(event)


async def audit_config_change(user: str, setting: str, old_value: Any,
                               new_value: Any, client_ip: str = None):
    """Audit a configuration change."""
    event = AuditEvent(
        action=AuditAction.CONFIG_CHANGED,
        result=AuditResult.SUCCESS,
        user=user,
        resource=setting,
        details={
            "old_value": str(old_value),
            "new_value": str(new_value),
        },
        client_ip=client_ip,
    )
    await audit_log.log(event)


async def audit_watchlist_change(action: str, drone_id: str, user: str,
                                  client_ip: str = None):
    """Audit a watchlist change."""
    audit_action = AuditAction.WATCHLIST_ADDED if action == "added" else AuditAction.WATCHLIST_REMOVED
    event = AuditEvent(
        action=audit_action,
        result=AuditResult.SUCCESS,
        user=user,
        resource=drone_id,
        client_ip=client_ip,
    )
    await audit_log.log(event)


def audit_system_startup():
    """Audit system startup (synchronous)."""
    event = AuditEvent(
        action=AuditAction.SYSTEM_STARTUP,
        result=AuditResult.SUCCESS,
        user="system",
        details={
            "audit_to_database": AUDIT_TO_DATABASE,
        },
    )
    audit_log.log_sync(event)


def audit_system_shutdown():
    """Audit system shutdown (synchronous)."""
    event = AuditEvent(
        action=AuditAction.SYSTEM_SHUTDOWN,
        result=AuditResult.SUCCESS,
        user="system",
    )
    audit_log.log_sync(event)


# =============================================================================
# Database Schema for Audit Logs (optional)
# =============================================================================

AUDIT_TABLE_SQL = """
-- Audit log table (optional - for persistent audit storage)
-- Run this SQL if you enable AUDIT_TO_DATABASE=true

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    username TEXT NOT NULL,
    resource TEXT,
    details JSONB DEFAULT '{}',
    client_ip TEXT,
    user_agent TEXT
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_username ON audit_log(username);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource) WHERE resource IS NOT NULL;

-- Retention policy (keep audit logs for 1 year)
-- SELECT add_retention_policy('audit_log', INTERVAL '1 year', if_not_exists => true);
"""

# =============================================================================
# Startup logging
# =============================================================================

logger.info(f"Audit logging initialized (database: {AUDIT_TO_DATABASE})")
