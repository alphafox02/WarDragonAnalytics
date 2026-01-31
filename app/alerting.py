#!/usr/bin/env python3
"""
WarDragon Analytics - Alerting and Notification Module

Provides webhook-based alerting for:
- Drone detections (new drones, watchlist matches)
- Security alerts (anomalies, night activity, rapid descent)
- FPV signal detections
- Kit status changes (offline, online)

Supports:
- Slack webhooks
- Discord webhooks
- Generic HTTP POST webhooks
- Custom headers for authentication

All alerting is OPTIONAL - disabled by default.
Enable by configuring webhook URLs in .env or via the API.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import json

import httpx

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Alerting is DISABLED by default
ALERTING_ENABLED = os.environ.get("ALERTING_ENABLED", "false").lower() == "true"

# Webhook URLs (from environment)
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
GENERIC_WEBHOOK_URL = os.environ.get("GENERIC_WEBHOOK_URL", "")
GENERIC_WEBHOOK_HEADERS = os.environ.get("GENERIC_WEBHOOK_HEADERS", "")  # JSON string

# Alert throttling (prevent spam)
ALERT_COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN_SECONDS", "60"))

# =============================================================================
# Alert Types
# =============================================================================

class AlertType(str, Enum):
    """Types of alerts that can be sent."""
    NEW_DRONE = "new_drone"
    WATCHLIST_MATCH = "watchlist_match"
    SECURITY_ALERT = "security_alert"
    FPV_SIGNAL = "fpv_signal"
    KIT_OFFLINE = "kit_offline"
    KIT_ONLINE = "kit_online"
    ANOMALY = "anomaly"
    NIGHT_ACTIVITY = "night_activity"
    RAPID_DESCENT = "rapid_descent"
    LOITERING = "loitering"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Represents an alert to be sent."""
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert alert to dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# Alert Manager
# =============================================================================

class AlertManager:
    """
    Manages alert sending and throttling.
    Thread-safe for concurrent access.
    """

    def __init__(self):
        self._last_alerts: Dict[str, datetime] = {}  # key -> last_sent_time
        self._webhooks: List[Dict[str, Any]] = []
        self._load_webhooks_from_env()
        self._enabled = ALERTING_ENABLED
        self._http_client: Optional[httpx.AsyncClient] = None

    def _load_webhooks_from_env(self):
        """Load webhook configurations from environment."""
        if SLACK_WEBHOOK_URL:
            self._webhooks.append({
                "type": "slack",
                "url": SLACK_WEBHOOK_URL,
                "name": "Slack",
            })
            logger.info("Loaded Slack webhook configuration")

        if DISCORD_WEBHOOK_URL:
            self._webhooks.append({
                "type": "discord",
                "url": DISCORD_WEBHOOK_URL,
                "name": "Discord",
            })
            logger.info("Loaded Discord webhook configuration")

        if GENERIC_WEBHOOK_URL:
            headers = {}
            if GENERIC_WEBHOOK_HEADERS:
                try:
                    headers = json.loads(GENERIC_WEBHOOK_HEADERS)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse GENERIC_WEBHOOK_HEADERS as JSON")

            self._webhooks.append({
                "type": "generic",
                "url": GENERIC_WEBHOOK_URL,
                "name": "Generic Webhook",
                "headers": headers,
            })
            logger.info("Loaded generic webhook configuration")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    def is_enabled(self) -> bool:
        """Check if alerting is enabled."""
        return self._enabled and len(self._webhooks) > 0

    def get_status(self) -> dict:
        """Get alerting status for API."""
        return {
            "enabled": self._enabled,
            "webhooks_configured": len(self._webhooks),
            "webhook_types": [w["type"] for w in self._webhooks],
            "cooldown_seconds": ALERT_COOLDOWN_SECONDS,
        }

    def add_webhook(self, webhook_type: str, url: str, name: str = "", headers: dict = None):
        """Add a webhook dynamically."""
        webhook = {
            "type": webhook_type,
            "url": url,
            "name": name or webhook_type,
            "headers": headers or {},
        }
        self._webhooks.append(webhook)
        logger.info(f"Added {webhook_type} webhook: {name}")

    def remove_webhook(self, url: str) -> bool:
        """Remove a webhook by URL."""
        initial_count = len(self._webhooks)
        self._webhooks = [w for w in self._webhooks if w["url"] != url]
        return len(self._webhooks) < initial_count

    def list_webhooks(self) -> List[dict]:
        """List configured webhooks (URLs masked for security)."""
        return [
            {
                "type": w["type"],
                "name": w["name"],
                "url_masked": w["url"][:30] + "..." if len(w["url"]) > 30 else w["url"],
            }
            for w in self._webhooks
        ]

    def _get_throttle_key(self, alert: Alert) -> str:
        """Generate a throttle key for an alert."""
        # Group similar alerts together for throttling
        if alert.alert_type == AlertType.NEW_DRONE:
            return f"new_drone:{alert.details.get('drone_id', 'unknown')}"
        elif alert.alert_type == AlertType.WATCHLIST_MATCH:
            return f"watchlist:{alert.details.get('drone_id', 'unknown')}"
        elif alert.alert_type in (AlertType.KIT_OFFLINE, AlertType.KIT_ONLINE):
            return f"kit_status:{alert.details.get('kit_id', 'unknown')}"
        else:
            return f"{alert.alert_type.value}:{alert.severity.value}"

    def _is_throttled(self, alert: Alert) -> bool:
        """Check if an alert should be throttled."""
        key = self._get_throttle_key(alert)
        now = datetime.utcnow()

        if key in self._last_alerts:
            elapsed = (now - self._last_alerts[key]).total_seconds()
            if elapsed < ALERT_COOLDOWN_SECONDS:
                return True

        self._last_alerts[key] = now
        return False

    def _format_slack_message(self, alert: Alert) -> dict:
        """Format alert for Slack webhook."""
        severity_emoji = {
            AlertSeverity.INFO: ":information_source:",
            AlertSeverity.WARNING: ":warning:",
            AlertSeverity.HIGH: ":rotating_light:",
            AlertSeverity.CRITICAL: ":fire:",
        }

        severity_color = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ffcc00",
            AlertSeverity.HIGH: "#ff6600",
            AlertSeverity.CRITICAL: "#ff0000",
        }

        emoji = severity_emoji.get(alert.severity, ":bell:")
        color = severity_color.get(alert.severity, "#808080")

        # Build fields from details
        fields = []
        for key, value in alert.details.items():
            if value is not None:
                fields.append({
                    "title": key.replace("_", " ").title(),
                    "value": str(value),
                    "short": True,
                })

        return {
            "attachments": [
                {
                    "color": color,
                    "fallback": f"{emoji} {alert.title}",
                    "pretext": f"{emoji} *WarDragon Alert*",
                    "title": alert.title,
                    "text": alert.message,
                    "fields": fields[:10],  # Limit fields
                    "footer": "WarDragon Analytics",
                    "ts": int(alert.timestamp.timestamp()),
                }
            ]
        }

    def _format_discord_message(self, alert: Alert) -> dict:
        """Format alert for Discord webhook."""
        severity_color = {
            AlertSeverity.INFO: 0x36a64f,
            AlertSeverity.WARNING: 0xffcc00,
            AlertSeverity.HIGH: 0xff6600,
            AlertSeverity.CRITICAL: 0xff0000,
        }

        color = severity_color.get(alert.severity, 0x808080)

        # Build fields from details
        fields = []
        for key, value in alert.details.items():
            if value is not None:
                fields.append({
                    "name": key.replace("_", " ").title(),
                    "value": str(value),
                    "inline": True,
                })

        return {
            "embeds": [
                {
                    "title": f"WarDragon Alert: {alert.title}",
                    "description": alert.message,
                    "color": color,
                    "fields": fields[:25],  # Discord limit
                    "footer": {"text": "WarDragon Analytics"},
                    "timestamp": alert.timestamp.isoformat(),
                }
            ]
        }

    def _format_generic_message(self, alert: Alert) -> dict:
        """Format alert for generic webhook (raw JSON)."""
        return alert.to_dict()

    async def send_alert(self, alert: Alert) -> bool:
        """
        Send an alert to all configured webhooks.
        Returns True if at least one webhook succeeded.
        """
        if not self.is_enabled():
            logger.debug("Alerting disabled, skipping alert")
            return False

        if self._is_throttled(alert):
            logger.debug(f"Alert throttled: {alert.title}")
            return False

        client = await self._get_client()
        success = False

        for webhook in self._webhooks:
            try:
                # Format message based on webhook type
                if webhook["type"] == "slack":
                    payload = self._format_slack_message(alert)
                elif webhook["type"] == "discord":
                    payload = self._format_discord_message(alert)
                else:
                    payload = self._format_generic_message(alert)

                headers = {"Content-Type": "application/json"}
                if webhook.get("headers"):
                    headers.update(webhook["headers"])

                response = await client.post(
                    webhook["url"],
                    json=payload,
                    headers=headers,
                )

                if response.status_code in (200, 201, 204):
                    logger.info(f"Alert sent to {webhook['name']}: {alert.title}")
                    success = True
                else:
                    logger.warning(
                        f"Webhook {webhook['name']} returned {response.status_code}: {response.text[:100]}"
                    )

            except Exception as e:
                logger.error(f"Failed to send alert to {webhook['name']}: {e}")

        return success

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# =============================================================================
# Global Alert Manager Instance
# =============================================================================

alert_manager = AlertManager()


# =============================================================================
# Helper Functions for Common Alerts
# =============================================================================

async def alert_new_drone(drone_id: str, rid_make: str = None, lat: float = None,
                          lon: float = None, kit_id: str = None):
    """Send alert for a new drone detection."""
    alert = Alert(
        alert_type=AlertType.NEW_DRONE,
        severity=AlertSeverity.INFO,
        title=f"New Drone Detected: {drone_id}",
        message=f"A new drone has been detected by the system.",
        details={
            "drone_id": drone_id,
            "rid_make": rid_make,
            "latitude": lat,
            "longitude": lon,
            "kit_id": kit_id,
        },
    )
    return await alert_manager.send_alert(alert)


async def alert_watchlist_match(drone_id: str, watchlist_entry: str = None,
                                 lat: float = None, lon: float = None):
    """Send alert for a watchlist match."""
    alert = Alert(
        alert_type=AlertType.WATCHLIST_MATCH,
        severity=AlertSeverity.HIGH,
        title=f"Watchlist Match: {drone_id}",
        message=f"A drone on the watchlist has been detected!",
        details={
            "drone_id": drone_id,
            "watchlist_entry": watchlist_entry,
            "latitude": lat,
            "longitude": lon,
        },
    )
    return await alert_manager.send_alert(alert)


async def alert_security_event(title: str, message: str, severity: AlertSeverity,
                                details: dict = None):
    """Send a generic security alert."""
    alert = Alert(
        alert_type=AlertType.SECURITY_ALERT,
        severity=severity,
        title=title,
        message=message,
        details=details or {},
    )
    return await alert_manager.send_alert(alert)


async def alert_fpv_signal(freq_mhz: float, power_dbm: float = None,
                           lat: float = None, lon: float = None, kit_id: str = None):
    """Send alert for FPV signal detection."""
    alert = Alert(
        alert_type=AlertType.FPV_SIGNAL,
        severity=AlertSeverity.WARNING,
        title=f"FPV Signal Detected: {freq_mhz:.1f} MHz",
        message=f"An FPV video signal has been detected on {freq_mhz:.1f} MHz.",
        details={
            "frequency_mhz": freq_mhz,
            "power_dbm": power_dbm,
            "latitude": lat,
            "longitude": lon,
            "kit_id": kit_id,
        },
    )
    return await alert_manager.send_alert(alert)


async def alert_kit_status(kit_id: str, status: str, kit_name: str = None):
    """Send alert for kit status change."""
    is_offline = status.lower() == "offline"
    alert = Alert(
        alert_type=AlertType.KIT_OFFLINE if is_offline else AlertType.KIT_ONLINE,
        severity=AlertSeverity.WARNING if is_offline else AlertSeverity.INFO,
        title=f"Kit {status.title()}: {kit_name or kit_id}",
        message=f"WarDragon kit '{kit_name or kit_id}' is now {status}.",
        details={
            "kit_id": kit_id,
            "kit_name": kit_name,
            "status": status,
        },
    )
    return await alert_manager.send_alert(alert)


async def alert_anomaly(drone_id: str, anomaly_type: str, severity: AlertSeverity,
                        details: dict = None):
    """Send alert for detected anomaly."""
    alert = Alert(
        alert_type=AlertType.ANOMALY,
        severity=severity,
        title=f"Anomaly Detected: {anomaly_type}",
        message=f"Anomalous behavior detected for drone {drone_id}.",
        details={"drone_id": drone_id, "anomaly_type": anomaly_type, **(details or {})},
    )
    return await alert_manager.send_alert(alert)


# =============================================================================
# Startup logging
# =============================================================================

if alert_manager.is_enabled():
    logger.info(f"Alerting ENABLED with {len(alert_manager._webhooks)} webhook(s)")
else:
    if ALERTING_ENABLED:
        logger.warning("ALERTING_ENABLED=true but no webhooks configured")
    else:
        logger.info("Alerting DISABLED (set ALERTING_ENABLED=true and configure webhooks to enable)")
