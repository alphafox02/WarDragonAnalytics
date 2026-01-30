#!/usr/bin/env python3
"""
WarDragon Analytics - LLM-Powered Query Service

Provides natural language querying of drone detection data using Ollama.
Converts user questions into safe, parameterized SQL queries.

Architecture:
1. User asks question in natural language
2. LLM extracts structured query parameters
3. Backend validates and executes safe query
4. Results returned with optional LLM summary

Security:
- LLM never generates raw SQL
- All queries use parameterized statements
- Field names validated against whitelist
- Operators validated against allowed set
"""

import os
import json
import logging
import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import httpx

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# LLM is enabled by default - will gracefully degrade if Ollama not available
LLM_ENABLED = os.environ.get("LLM_ENABLED", "true").lower() == "true"

# Ollama connection settings
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))

# Generation parameters
OLLAMA_MAX_TOKENS = int(os.environ.get("OLLAMA_MAX_TOKENS", "2048"))
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.1"))


# =============================================================================
# Schema Definition - What the LLM knows about our database
# =============================================================================

SCHEMA_CONTEXT = """
You are a query assistant for WarDragon Analytics, a drone detection and tracking system.
You help users query detection data using natural language.

## Available Tables and Fields

### drones table (drone/aircraft detections)
- time: timestamp of detection
- kit_id: which detection kit saw this (e.g., "wardragon-alpha")
- drone_id: unique identifier for the drone
- lat, lon: GPS coordinates (decimal degrees)
- alt: altitude in meters (MSL)
- height: height above ground level (AGL) in meters
- speed: ground speed in m/s
- vspeed: vertical speed in m/s (positive=climbing, negative=descending)
- heading: direction of travel in degrees (0-359)
- direction: direction from Remote ID broadcast
- pilot_lat, pilot_lon: pilot/operator location (if available)
- home_lat, home_lon: home/takeoff point (if available)
- mac: MAC address (for BLE/WiFi detection)
- rssi: signal strength in dBm
- freq: detection frequency in Hz
- rid_make: manufacturer (DJI, Autel, Skydio, Parrot, etc.)
- rid_model: model name (Mavic 3, Mini 4 Pro, etc.)
- rid_source: detection method (ble, wifi, dji)
- id_type: detection type (ble, wifi, dji for OcuSync)
- track_type: "drone" or "aircraft"
- op_status: operational status (ground, airborne, emergency)
- runtime: flight time in seconds
- operator_id: registered operator ID
- caa_id: civil aviation authority ID

### signals table (FPV/RF signal detections)
- time: timestamp of detection
- kit_id: which kit detected this
- freq_mhz: center frequency in MHz (5650-5950 for FPV)
- power_dbm: signal power in dBm
- bandwidth_mhz: signal bandwidth
- lat, lon, alt: kit location at detection time
- detection_type: "analog" or "dji"
- pal_conf: PAL video standard confidence (0.0-1.0)
- ntsc_conf: NTSC video standard confidence (0.0-1.0)
- source: detection stage ("guard" for energy detection, "confirm" for validation)
- signal_type: signal classification

### system_health table (kit status)
- time: timestamp
- kit_id: kit identifier
- lat, lon, alt: kit GPS position
- cpu_percent, memory_percent, disk_percent: resource usage (0-100)
- uptime_hours: system uptime
- temp_cpu, temp_gpu: CPU/GPU temperatures in Celsius
- pluto_temp, zynq_temp: SDR temperatures
- speed, track: kit movement (for mobile deployments)
- gps_fix: whether kit has GPS lock

### kits table (kit configuration)
- kit_id: unique identifier
- name: human-readable name
- location: deployment location
- api_url: kit API endpoint
- status: "online", "offline", "stale"
- last_seen: last communication time

## Domain Knowledge

### Regulatory Thresholds
- 400 feet (122 meters) is the typical FAA altitude limit for recreational drones
- Drones above this may require Part 107 waiver

### Speed Classifications
- Hovering: speed < 1 m/s
- Slow: 1-5 m/s
- Normal: 5-15 m/s
- Fast: 15-30 m/s
- Very fast (potentially FPV racing): > 30 m/s

### Altitude Classifications
- Low: < 30m (near ground, possible landing/takeoff)
- Normal: 30-122m (typical operation)
- High: 122-150m (approaching limit)
- Very high: > 150m (likely unauthorized)

### FPV Frequencies
- Common FPV bands: 5650-5950 MHz
- Band A (Boscam A): 5865, 5845, 5825, 5805, 5785, 5765, 5745, 5725
- Band B (Boscam B): 5733, 5752, 5771, 5790, 5809, 5828, 5847, 5866
- Band E (DJI/Raceband): 5658, 5695, 5732, 5769, 5806, 5843, 5880, 5917

### Detection Sources
- ble: Bluetooth Low Energy Remote ID
- wifi: WiFi Beacon/NaN Remote ID
- dji: DJI OcuSync/DroneID (proprietary protocol)

### Time Expressions
- "today": since midnight
- "yesterday": previous day
- "last hour": past 60 minutes
- "last night": 22:00-05:00 previous night
- "this morning": 05:00-12:00 today
- "this afternoon": 12:00-18:00 today
- "this evening": 18:00-22:00 today

## Response Format

You must respond with ONLY a JSON object (no markdown, no explanation). The JSON should have this structure:

{
    "understood": true/false,
    "query_type": "search" | "count" | "aggregate" | "compare" | "anomaly" | "unknown",
    "table": "drones" | "signals" | "system_health" | "kits",
    "select_fields": ["field1", "field2"],  // or ["*"] or ["COUNT(*)"]
    "filters": [
        {"field": "fieldname", "op": "=|>|<|>=|<=|!=|LIKE|IN|BETWEEN|IS NULL|IS NOT NULL", "value": "value or [list]"}
    ],
    "time_filter": {
        "type": "relative" | "absolute",
        "value": "1h" | "24h" | "7d" | {"start": "ISO datetime", "end": "ISO datetime"}
    },
    "group_by": ["field1"],  // optional
    "order_by": {"field": "fieldname", "direction": "ASC|DESC"},  // optional
    "limit": 100,
    "aggregations": [  // optional, for aggregate queries
        {"function": "COUNT|SUM|AVG|MIN|MAX", "field": "fieldname", "alias": "name"}
    ],
    "explanation": "Brief explanation of what this query will find",
    "clarification_needed": "Question to ask user if query is ambiguous"  // optional
}

If you cannot understand the query or it's not about drone data, set understood=false and explain why in the explanation field.
"""


# =============================================================================
# Allowed Fields and Operators (Security Whitelist)
# =============================================================================

ALLOWED_FIELDS = {
    "drones": {
        "time", "kit_id", "drone_id", "lat", "lon", "alt", "height", "speed", "vspeed",
        "heading", "direction", "pilot_lat", "pilot_lon", "home_lat", "home_lon",
        "mac", "rssi", "freq", "rid_make", "rid_model", "rid_source", "id_type",
        "track_type", "op_status", "runtime", "operator_id", "caa_id", "ua_type"
    },
    "signals": {
        "time", "kit_id", "freq_mhz", "power_dbm", "bandwidth_mhz", "lat", "lon", "alt",
        "detection_type", "pal_conf", "ntsc_conf", "source", "signal_type"
    },
    "system_health": {
        "time", "kit_id", "lat", "lon", "alt", "cpu_percent", "memory_percent",
        "disk_percent", "uptime_hours", "temp_cpu", "temp_gpu", "pluto_temp",
        "zynq_temp", "speed", "track", "gps_fix"
    },
    "kits": {
        "kit_id", "name", "location", "api_url", "status", "last_seen", "enabled", "created_at"
    }
}

ALLOWED_OPERATORS = {"=", ">", "<", ">=", "<=", "!=", "LIKE", "IN", "BETWEEN", "IS NULL", "IS NOT NULL"}
ALLOWED_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX", "COUNT DISTINCT"}
ALLOWED_TABLES = {"drones", "signals", "system_health", "kits"}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class QueryFilter:
    field: str
    op: str
    value: Any


@dataclass
class TimeFilter:
    filter_type: str  # "relative" or "absolute"
    value: Any  # "1h", "24h", "7d" or {"start": ..., "end": ...}


@dataclass
class Aggregation:
    function: str
    field: str
    alias: str


@dataclass
class ParsedQuery:
    understood: bool
    query_type: str
    table: str
    select_fields: List[str]
    filters: List[QueryFilter]
    time_filter: Optional[TimeFilter]
    group_by: List[str]
    order_by: Optional[Dict[str, str]]
    limit: int
    aggregations: List[Aggregation]
    explanation: str
    clarification_needed: Optional[str] = None
    error: Optional[str] = None


@dataclass
class QueryResult:
    success: bool
    data: List[Dict[str, Any]]
    row_count: int
    query_explanation: str
    execution_time_ms: float
    summary: Optional[str] = None
    error: Optional[str] = None
    query_sql: Optional[str] = None  # Executed SQL for transparency


# =============================================================================
# Ollama Client
# =============================================================================

class OllamaClient:
    """Async client for Ollama API."""

    def __init__(self, base_url: str = OLLAMA_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = OLLAMA_TIMEOUT
        self.max_tokens = OLLAMA_MAX_TOKENS
        self.temperature = OLLAMA_TEMPERATURE

    async def is_available(self) -> Tuple[bool, Optional[str]]:
        """Check if Ollama is available and the model is loaded.

        Returns:
            Tuple of (available: bool, model_name: str or None)
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check if our model is available (handle version tags)
                    model_base = self.model.split(":")[0]
                    for m in models:
                        if model_base in m:
                            return True, m
                    # Ollama is running but model not found
                    return False, None
                return False, None
        except Exception as e:
            logger.warning(f"Ollama availability check failed: {e}")
            return False, None

    async def get_available_models(self) -> List[str]:
        """Get list of available models in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [m.get("name", "") for m in data.get("models", [])]
                return []
        except Exception as e:
            logger.warning(f"Failed to get Ollama models: {e}")
            return []

    async def generate(self, prompt: str, system: str = None) -> str:
        """Generate a response from the LLM."""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                }
            }
            if system:
                payload["system"] = system

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except httpx.TimeoutException:
            logger.error(f"Ollama request timed out after {self.timeout}s")
            raise
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise


# =============================================================================
# Query Parser
# =============================================================================

class QueryParser:
    """Parses LLM output into validated query structure."""

    def __init__(self):
        self.ollama = OllamaClient()

    async def parse_natural_language(self, user_query: str) -> ParsedQuery:
        """Convert natural language to structured query."""

        # Build the prompt
        prompt = f"""User question: {user_query}

Convert this to a query structure. Respond with ONLY valid JSON, no markdown code blocks."""

        try:
            # Get LLM response
            response = await self.ollama.generate(prompt, system=SCHEMA_CONTEXT)

            # Extract JSON from response (handle markdown code blocks if present)
            json_str = self._extract_json(response)

            # Parse JSON
            parsed = json.loads(json_str)

            # Validate and convert to ParsedQuery
            return self._validate_parsed_query(parsed)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return ParsedQuery(
                understood=False,
                query_type="unknown",
                table="drones",
                select_fields=["*"],
                filters=[],
                time_filter=None,
                group_by=[],
                order_by=None,
                limit=100,
                aggregations=[],
                explanation="",
                error=f"Failed to parse query: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Query parsing error: {e}")
            return ParsedQuery(
                understood=False,
                query_type="unknown",
                table="drones",
                select_fields=["*"],
                filters=[],
                time_filter=None,
                group_by=[],
                order_by=None,
                limit=100,
                aggregations=[],
                explanation="",
                error=f"Query parsing failed: {str(e)}"
            )

    def _extract_json(self, response: str) -> str:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Remove markdown code blocks if present
        response = response.strip()
        if response.startswith("```"):
            # Find the end of the code block
            lines = response.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            response = "\n".join(json_lines)

        # Find JSON object boundaries
        start = response.find("{")
        end = response.rfind("}") + 1
        if start != -1 and end > start:
            return response[start:end]

        return response

    def _validate_parsed_query(self, parsed: Dict) -> ParsedQuery:
        """Validate and sanitize parsed query against whitelist."""

        # Validate table
        table = parsed.get("table", "drones")
        if table not in ALLOWED_TABLES:
            table = "drones"

        # Validate select fields
        select_fields = parsed.get("select_fields", ["*"])
        if select_fields != ["*"] and select_fields != ["COUNT(*)"]:
            valid_fields = []
            for f in select_fields:
                # Handle aggregation functions
                if "(" in f:
                    continue  # Skip, handled by aggregations
                if f in ALLOWED_FIELDS.get(table, set()):
                    valid_fields.append(f)
            select_fields = valid_fields if valid_fields else ["*"]

        # Validate filters
        filters = []
        for f in parsed.get("filters", []):
            field = f.get("field", "")
            op = f.get("op", "=").upper()
            value = f.get("value")

            if field in ALLOWED_FIELDS.get(table, set()) and op in ALLOWED_OPERATORS:
                filters.append(QueryFilter(field=field, op=op, value=value))

        # Validate time filter
        time_filter = None
        tf = parsed.get("time_filter")
        if tf:
            time_filter = TimeFilter(
                filter_type=tf.get("type", "relative"),
                value=tf.get("value", "1h")
            )

        # Validate group_by
        group_by = []
        for g in parsed.get("group_by", []):
            if g in ALLOWED_FIELDS.get(table, set()):
                group_by.append(g)

        # Validate order_by
        order_by = None
        ob = parsed.get("order_by")
        if ob and ob.get("field") in ALLOWED_FIELDS.get(table, set()):
            order_by = {
                "field": ob["field"],
                "direction": "DESC" if ob.get("direction", "").upper() == "DESC" else "ASC"
            }

        # Validate limit
        limit = min(max(parsed.get("limit", 100), 1), 1000)

        # Validate aggregations
        aggregations = []
        for agg in parsed.get("aggregations", []):
            func = agg.get("function", "").upper()
            agg_field = agg.get("field", "*")
            alias = agg.get("alias", "result")

            if func in ALLOWED_FUNCTIONS:
                if agg_field == "*" or agg_field in ALLOWED_FIELDS.get(table, set()):
                    aggregations.append(Aggregation(function=func, field=agg_field, alias=alias))

        return ParsedQuery(
            understood=parsed.get("understood", True),
            query_type=parsed.get("query_type", "search"),
            table=table,
            select_fields=select_fields,
            filters=filters,
            time_filter=time_filter,
            group_by=group_by,
            order_by=order_by,
            limit=limit,
            aggregations=aggregations,
            explanation=parsed.get("explanation", ""),
            clarification_needed=parsed.get("clarification_needed")
        )


# =============================================================================
# Query Builder
# =============================================================================

class QueryBuilder:
    """Builds safe parameterized SQL from ParsedQuery."""

    def build_query(self, parsed: ParsedQuery) -> Tuple[str, List[Any]]:
        """Build SQL query and parameters from ParsedQuery."""

        params = []
        param_idx = 1

        # Build SELECT clause
        if parsed.aggregations:
            select_parts = []
            for agg in parsed.aggregations:
                if agg.function == "COUNT DISTINCT":
                    select_parts.append(f"COUNT(DISTINCT {agg.field}) AS {agg.alias}")
                else:
                    select_parts.append(f"{agg.function}({agg.field}) AS {agg.alias}")
            # Add group by fields to select
            for g in parsed.group_by:
                if g not in select_parts:
                    select_parts.append(g)
            select_clause = ", ".join(select_parts)
        elif parsed.select_fields == ["*"]:
            select_clause = "*"
        else:
            select_clause = ", ".join(parsed.select_fields)

        # Build FROM clause
        from_clause = parsed.table

        # Build WHERE clause
        where_parts = []

        # Add time filter
        if parsed.time_filter:
            if parsed.time_filter.filter_type == "relative":
                interval = self._parse_relative_time(parsed.time_filter.value)
                where_parts.append(f"time >= NOW() - INTERVAL '{interval}'")
            elif parsed.time_filter.filter_type == "absolute":
                val = parsed.time_filter.value
                if isinstance(val, dict):
                    where_parts.append(f"time >= ${param_idx}")
                    params.append(val.get("start"))
                    param_idx += 1
                    where_parts.append(f"time <= ${param_idx}")
                    params.append(val.get("end"))
                    param_idx += 1
        else:
            # Default to last hour
            where_parts.append("time >= NOW() - INTERVAL '1 hour'")

        # Add filters
        for f in parsed.filters:
            if f.op == "IS NULL":
                where_parts.append(f"{f.field} IS NULL")
            elif f.op == "IS NOT NULL":
                where_parts.append(f"{f.field} IS NOT NULL")
            elif f.op == "IN":
                if isinstance(f.value, list):
                    placeholders = ", ".join([f"${param_idx + i}" for i in range(len(f.value))])
                    where_parts.append(f"{f.field} IN ({placeholders})")
                    params.extend(f.value)
                    param_idx += len(f.value)
            elif f.op == "BETWEEN":
                if isinstance(f.value, list) and len(f.value) == 2:
                    where_parts.append(f"{f.field} BETWEEN ${param_idx} AND ${param_idx + 1}")
                    params.extend(f.value)
                    param_idx += 2
            elif f.op == "LIKE":
                where_parts.append(f"{f.field} ILIKE ${param_idx}")
                params.append(f"%{f.value}%")
                param_idx += 1
            else:
                where_parts.append(f"{f.field} {f.op} ${param_idx}")
                params.append(f.value)
                param_idx += 1

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"

        # Build GROUP BY clause
        group_by_clause = ""
        if parsed.group_by:
            group_by_clause = f" GROUP BY {', '.join(parsed.group_by)}"

        # Build ORDER BY clause
        order_by_clause = ""
        if parsed.order_by:
            order_by_clause = f" ORDER BY {parsed.order_by['field']} {parsed.order_by['direction']}"
        elif not parsed.aggregations:
            order_by_clause = " ORDER BY time DESC"

        # Build LIMIT clause
        limit_clause = f" LIMIT {parsed.limit}"

        # Assemble query
        query = f"SELECT {select_clause} FROM {from_clause} WHERE {where_clause}{group_by_clause}{order_by_clause}{limit_clause}"

        return query, params

    def _parse_relative_time(self, value: str) -> str:
        """Convert relative time to PostgreSQL interval string."""
        if value == "1h":
            return "1 hour"
        elif value == "24h":
            return "24 hours"
        elif value == "7d":
            return "7 days"
        elif value == "30d":
            return "30 days"
        elif value == "today":
            return "1 day"
        elif value == "yesterday":
            return "2 days"  # Will need adjustment
        else:
            # Try to parse custom format like "2h", "3d", etc.
            match = re.match(r"(\d+)(h|d|m|w)", value)
            if match:
                num, unit = match.groups()
                units = {"h": "hours", "d": "days", "m": "minutes", "w": "weeks"}
                return f"{num} {units.get(unit, 'hours')}"
            return "1 hour"


# =============================================================================
# LLM Service (Main Interface)
# =============================================================================

class LLMService:
    """Main service for LLM-powered queries."""

    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.parser = QueryParser()
        self.builder = QueryBuilder()
        self.ollama = OllamaClient()

    async def is_available(self) -> Dict[str, Any]:
        """Check if LLM service is available."""
        if not LLM_ENABLED:
            return {
                "available": False,
                "message": "LLM integration is disabled. Set LLM_ENABLED=true to enable.",
                "ollama_url": OLLAMA_URL,
                "model": None
            }

        ollama_available, model_name = await self.ollama.is_available()

        if ollama_available:
            return {
                "available": True,
                "message": None,
                "ollama_url": OLLAMA_URL,
                "model": model_name or OLLAMA_MODEL
            }
        else:
            # Check if Ollama is running but model is missing
            available_models = await self.ollama.get_available_models()
            if available_models:
                return {
                    "available": False,
                    "message": f"Model '{OLLAMA_MODEL}' not found. Run: ollama pull {OLLAMA_MODEL}",
                    "ollama_url": OLLAMA_URL,
                    "model": None,
                    "available_models": available_models[:5]  # Show first 5 models
                }
            else:
                return {
                    "available": False,
                    "message": f"Ollama not reachable at {OLLAMA_URL}. Is Ollama running?",
                    "ollama_url": OLLAMA_URL,
                    "model": None
                }

    async def query(self, user_question: str, include_summary: bool = True) -> QueryResult:
        """Process a natural language query and return results."""
        import time
        start_time = time.time()

        if not LLM_ENABLED:
            return QueryResult(
                success=False,
                data=[],
                row_count=0,
                query_explanation="",
                execution_time_ms=0,
                error="LLM integration is disabled"
            )

        try:
            # Parse natural language to structured query
            parsed = await self.parser.parse_natural_language(user_question)

            if not parsed.understood:
                return QueryResult(
                    success=False,
                    data=[],
                    row_count=0,
                    query_explanation=parsed.explanation,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=parsed.error or "Could not understand the query"
                )

            if parsed.clarification_needed:
                return QueryResult(
                    success=False,
                    data=[],
                    row_count=0,
                    query_explanation=parsed.explanation,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=f"Clarification needed: {parsed.clarification_needed}"
                )

            # Build SQL query
            query, params = self.builder.build_query(parsed)
            logger.info(f"Executing query: {query} with params: {params}")

            # Execute query
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            data = [dict(row) for row in rows]

            # Generate summary if requested and there's data
            summary = None
            if include_summary and data and len(data) > 0:
                summary = await self._generate_summary(user_question, data, parsed)

            execution_time = (time.time() - start_time) * 1000

            # Format query for display (replace placeholders with params for readability)
            display_query = query
            for i, param in enumerate(params, 1):
                display_query = display_query.replace(f"${i}", repr(param), 1)

            return QueryResult(
                success=True,
                data=data,
                row_count=len(data),
                query_explanation=parsed.explanation,
                execution_time_ms=execution_time,
                summary=summary,
                query_sql=display_query
            )

        except Exception as e:
            logger.error(f"Query execution error: {e}")
            return QueryResult(
                success=False,
                data=[],
                row_count=0,
                query_explanation="",
                execution_time_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )

    async def _generate_summary(self, question: str, data: List[Dict], parsed: ParsedQuery) -> str:
        """Generate a natural language summary of query results."""
        try:
            # Limit data for summary to avoid token limits
            sample_size = min(10, len(data))
            data_sample = data[:sample_size]

            prompt = f"""The user asked: "{question}"

The query returned {len(data)} results. Here's a sample of the data:
{json.dumps(data_sample, default=str, indent=2)}

Provide a brief, informative summary (2-3 sentences) of what was found.
Focus on key insights relevant to drone detection and security.
Be specific about numbers, patterns, or notable findings.
Do not start with "The query" or "Based on the data" - just state the findings directly."""

            response = await self.ollama.generate(prompt)
            return response.strip()

        except Exception as e:
            logger.warning(f"Failed to generate summary: {e}")
            return None

    def get_example_queries(self) -> List[Dict[str, str]]:
        """Return example queries for the UI."""
        return [
            {
                "category": "Recent Activity",
                "queries": [
                    "What drones were seen in the last hour?",
                    "Show me recent FPV signals",
                    "Any activity in the last 24 hours?",
                    "How many unique drones today?"
                ]
            },
            {
                "category": "Filtering",
                "queries": [
                    "Show me DJI drones",
                    "Drones flying above 100 meters",
                    "Fast drones (speed over 20 m/s)",
                    "Any drones with pilot location?"
                ]
            },
            {
                "category": "Analysis",
                "queries": [
                    "Which manufacturer is most common?",
                    "Busiest kit today?",
                    "Average flight altitude?",
                    "Drones seen by multiple kits?"
                ]
            },
            {
                "category": "Security",
                "queries": [
                    "Any high altitude flights?",
                    "Night time activity?",
                    "Drones near (lat, lon)?",
                    "Hovering drones (low speed)?"
                ]
            }
        ]


# =============================================================================
# Conversation History (for follow-up questions)
# =============================================================================

class ConversationManager:
    """Manages conversation context for follow-up questions."""

    def __init__(self, max_history: int = 10):
        self.conversations: Dict[str, List[Dict]] = {}
        self.max_history = max_history

    def add_turn(self, session_id: str, user_query: str, result: QueryResult):
        """Add a conversation turn."""
        if session_id not in self.conversations:
            self.conversations[session_id] = []

        self.conversations[session_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "user_query": user_query,
            "result_count": result.row_count,
            "explanation": result.query_explanation
        })

        # Trim history
        if len(self.conversations[session_id]) > self.max_history:
            self.conversations[session_id] = self.conversations[session_id][-self.max_history:]

    def get_context(self, session_id: str) -> str:
        """Get conversation context for follow-up queries."""
        if session_id not in self.conversations:
            return ""

        history = self.conversations[session_id]
        if not history:
            return ""

        context_parts = ["Previous queries in this session:"]
        for turn in history[-5:]:  # Last 5 turns
            context_parts.append(f"- \"{turn['user_query']}\" ({turn['result_count']} results)")

        return "\n".join(context_parts)

    def clear_session(self, session_id: str):
        """Clear conversation history for a session."""
        if session_id in self.conversations:
            del self.conversations[session_id]


# Global conversation manager
conversation_manager = ConversationManager()
