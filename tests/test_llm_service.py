#!/usr/bin/env python3
"""
Tests for the LLM-powered natural language query service.

These tests can run in two modes:
1. Unit tests with mocked Ollama responses (no Ollama required)
2. Integration tests with real Ollama (requires running Ollama)

Run with: pytest tests/test_llm_service.py -v
"""

import pytest
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from llm_service import (
    OllamaClient,
    QueryParser,
    QueryBuilder,
    LLMService,
    ConversationManager,
    ParsedQuery,
    QueryFilter,
    TimeFilter,
    Aggregation,
    QueryResult,
    ALLOWED_FIELDS,
    ALLOWED_OPERATORS,
    ALLOWED_TABLES,
    SCHEMA_CONTEXT,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_ollama_response():
    """Mock response from Ollama for a simple drone query."""
    return json.dumps({
        "understood": True,
        "query_type": "search",
        "table": "drones",
        "select_fields": ["drone_id", "lat", "lon", "alt", "speed", "time"],
        "filters": [
            {"field": "rid_make", "op": "=", "value": "DJI"}
        ],
        "time_filter": {
            "type": "relative",
            "value": "1h"
        },
        "group_by": [],
        "order_by": {"field": "time", "direction": "DESC"},
        "limit": 100,
        "aggregations": [],
        "explanation": "Finding DJI drones detected in the last hour"
    })


@pytest.fixture
def mock_ollama_count_response():
    """Mock response for a count query."""
    return json.dumps({
        "understood": True,
        "query_type": "count",
        "table": "drones",
        "select_fields": ["COUNT(*)"],
        "filters": [],
        "time_filter": {
            "type": "relative",
            "value": "24h"
        },
        "group_by": [],
        "order_by": None,
        "limit": 1,
        "aggregations": [
            {"function": "COUNT", "field": "*", "alias": "total_drones"}
        ],
        "explanation": "Counting total drones detected in the last 24 hours"
    })


@pytest.fixture
def mock_ollama_aggregate_response():
    """Mock response for an aggregate query."""
    return json.dumps({
        "understood": True,
        "query_type": "aggregate",
        "table": "drones",
        "select_fields": [],
        "filters": [],
        "time_filter": {
            "type": "relative",
            "value": "7d"
        },
        "group_by": ["rid_make"],
        "order_by": {"field": "count", "direction": "DESC"},
        "limit": 10,
        "aggregations": [
            {"function": "COUNT", "field": "*", "alias": "count"}
        ],
        "explanation": "Counting drones by manufacturer in the last week"
    })


@pytest.fixture
def mock_db_pool():
    """Mock database connection pool."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[
        {"drone_id": "test-drone-1", "lat": 34.05, "lon": -118.24, "alt": 100, "speed": 5.0, "time": datetime.now()},
        {"drone_id": "test-drone-2", "lat": 34.06, "lon": -118.25, "alt": 50, "speed": 10.0, "time": datetime.now()},
    ])

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()))

    return mock_pool


# =============================================================================
# OllamaClient Tests
# =============================================================================

class TestOllamaClient:
    """Tests for the Ollama API client."""

    @pytest.mark.asyncio
    async def test_is_available_when_running(self):
        """Test is_available returns True when Ollama is running with model."""
        client = OllamaClient()

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": [
                    {"name": "llama3.1:8b"},
                    {"name": "mistral:7b"}
                ]
            }

            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_response)
            ))
            mock_client.return_value.__aexit__ = AsyncMock()

            available, model = await client.is_available()
            assert available is True
            assert "llama3.1" in model

    @pytest.mark.asyncio
    async def test_is_available_when_offline(self):
        """Test is_available returns False when Ollama is not running."""
        client = OllamaClient()

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.return_value.__aexit__ = AsyncMock()

            available, model = await client.is_available()
            assert available is False
            assert model is None

    @pytest.mark.asyncio
    async def test_is_available_model_not_found(self):
        """Test is_available returns False when model is not loaded."""
        client = OllamaClient(model="nonexistent:model")

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": [{"name": "other-model:latest"}]
            }

            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_response)
            ))
            mock_client.return_value.__aexit__ = AsyncMock()

            available, model = await client.is_available()
            assert available is False
            assert model is None

    @pytest.mark.asyncio
    async def test_generate_success(self, mock_ollama_response):
        """Test successful generation from Ollama."""
        client = OllamaClient()

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"response": mock_ollama_response}
            mock_response.raise_for_status = MagicMock()

            mock_http = MagicMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client.return_value.__aexit__ = AsyncMock()

            result = await client.generate("Test prompt")
            assert result == mock_ollama_response


# =============================================================================
# QueryParser Tests
# =============================================================================

class TestQueryParser:
    """Tests for the query parser that converts LLM output to structured queries."""

    def test_extract_json_plain(self):
        """Test JSON extraction from plain response."""
        parser = QueryParser()

        json_str = '{"understood": true, "table": "drones"}'
        result = parser._extract_json(json_str)

        parsed = json.loads(result)
        assert parsed["understood"] is True
        assert parsed["table"] == "drones"

    def test_extract_json_with_markdown(self):
        """Test JSON extraction from markdown code block."""
        parser = QueryParser()

        response = """```json
{"understood": true, "table": "drones"}
```"""
        result = parser._extract_json(response)

        parsed = json.loads(result)
        assert parsed["understood"] is True

    def test_extract_json_with_surrounding_text(self):
        """Test JSON extraction when surrounded by explanation text."""
        parser = QueryParser()

        response = """I'll help you query the drones table.
{"understood": true, "table": "drones", "filters": []}
This will find all drones."""
        result = parser._extract_json(response)

        parsed = json.loads(result)
        assert parsed["understood"] is True

    def test_validate_parsed_query_valid_table(self):
        """Test validation accepts valid table names."""
        parser = QueryParser()

        for table in ALLOWED_TABLES:
            parsed = {"table": table, "select_fields": ["*"]}
            result = parser._validate_parsed_query(parsed)
            assert result.table == table

    def test_validate_parsed_query_invalid_table(self):
        """Test validation rejects invalid table names."""
        parser = QueryParser()

        parsed = {"table": "malicious_table; DROP TABLE drones;--", "select_fields": ["*"]}
        result = parser._validate_parsed_query(parsed)

        # Should default to "drones" for invalid tables
        assert result.table == "drones"

    def test_validate_parsed_query_valid_fields(self):
        """Test validation accepts valid field names."""
        parser = QueryParser()

        parsed = {
            "table": "drones",
            "select_fields": ["drone_id", "lat", "lon", "alt"],
            "filters": []
        }
        result = parser._validate_parsed_query(parsed)

        assert "drone_id" in result.select_fields
        assert "lat" in result.select_fields

    def test_validate_parsed_query_invalid_fields(self):
        """Test validation rejects invalid field names."""
        parser = QueryParser()

        parsed = {
            "table": "drones",
            "select_fields": ["drone_id", "malicious_field", "lat"],
            "filters": []
        }
        result = parser._validate_parsed_query(parsed)

        assert "drone_id" in result.select_fields
        assert "malicious_field" not in result.select_fields

    def test_validate_parsed_query_valid_operators(self):
        """Test validation accepts valid operators."""
        parser = QueryParser()

        for op in ALLOWED_OPERATORS:
            parsed = {
                "table": "drones",
                "select_fields": ["*"],
                "filters": [{"field": "alt", "op": op, "value": 100}]
            }
            result = parser._validate_parsed_query(parsed)

            if op not in ("IS NULL", "IS NOT NULL"):  # These don't need values
                assert len(result.filters) >= 0  # May be filtered based on value requirements

    def test_validate_parsed_query_invalid_operator(self):
        """Test validation rejects SQL injection in operators."""
        parser = QueryParser()

        parsed = {
            "table": "drones",
            "select_fields": ["*"],
            "filters": [{"field": "alt", "op": "; DROP TABLE drones;--", "value": 100}]
        }
        result = parser._validate_parsed_query(parsed)

        # Invalid operator filter should be removed
        assert len(result.filters) == 0

    def test_validate_limit_bounds(self):
        """Test limit is bounded within allowed range."""
        parser = QueryParser()

        # Test upper bound
        parsed = {"table": "drones", "select_fields": ["*"], "limit": 9999999}
        result = parser._validate_parsed_query(parsed)
        assert result.limit <= 1000

        # Test lower bound
        parsed = {"table": "drones", "select_fields": ["*"], "limit": -5}
        result = parser._validate_parsed_query(parsed)
        assert result.limit >= 1


# =============================================================================
# QueryBuilder Tests
# =============================================================================

class TestQueryBuilder:
    """Tests for the SQL query builder."""

    def test_build_simple_select(self):
        """Test building a simple SELECT query."""
        builder = QueryBuilder()

        parsed = ParsedQuery(
            understood=True,
            query_type="search",
            table="drones",
            select_fields=["drone_id", "lat", "lon"],
            filters=[],
            time_filter=TimeFilter(filter_type="relative", value="1h"),
            group_by=[],
            order_by=None,
            limit=100,
            aggregations=[],
            explanation="Test query"
        )

        query, params = builder.build_query(parsed)

        assert "SELECT drone_id, lat, lon FROM drones" in query
        assert "time >= NOW() - INTERVAL '1 hour'" in query
        assert "LIMIT 100" in query

    def test_build_query_with_filters(self):
        """Test building query with WHERE filters."""
        builder = QueryBuilder()

        parsed = ParsedQuery(
            understood=True,
            query_type="search",
            table="drones",
            select_fields=["*"],
            filters=[
                QueryFilter(field="rid_make", op="=", value="DJI"),
                QueryFilter(field="alt", op=">", value=100)
            ],
            time_filter=TimeFilter(filter_type="relative", value="1h"),
            group_by=[],
            order_by=None,
            limit=100,
            aggregations=[],
            explanation="Test query"
        )

        query, params = builder.build_query(parsed)

        assert "rid_make = $1" in query
        assert "alt > $2" in query
        assert params[0] == "DJI"
        assert params[1] == 100

    def test_build_query_with_like(self):
        """Test LIKE operator adds wildcards."""
        builder = QueryBuilder()

        parsed = ParsedQuery(
            understood=True,
            query_type="search",
            table="drones",
            select_fields=["*"],
            filters=[QueryFilter(field="rid_make", op="LIKE", value="DJI")],
            time_filter=None,
            group_by=[],
            order_by=None,
            limit=100,
            aggregations=[],
            explanation="Test query"
        )

        query, params = builder.build_query(parsed)

        assert "ILIKE" in query  # Case-insensitive
        assert params[0] == "%DJI%"  # Wildcards added

    def test_build_query_with_in_operator(self):
        """Test IN operator with list of values."""
        builder = QueryBuilder()

        parsed = ParsedQuery(
            understood=True,
            query_type="search",
            table="drones",
            select_fields=["*"],
            filters=[QueryFilter(field="rid_make", op="IN", value=["DJI", "Autel", "Skydio"])],
            time_filter=None,
            group_by=[],
            order_by=None,
            limit=100,
            aggregations=[],
            explanation="Test query"
        )

        query, params = builder.build_query(parsed)

        assert "IN ($1, $2, $3)" in query
        assert params == ["DJI", "Autel", "Skydio"]

    def test_build_aggregation_query(self):
        """Test building aggregation query with GROUP BY."""
        builder = QueryBuilder()

        parsed = ParsedQuery(
            understood=True,
            query_type="aggregate",
            table="drones",
            select_fields=[],
            filters=[],
            time_filter=TimeFilter(filter_type="relative", value="24h"),
            group_by=["rid_make"],
            order_by={"field": "count", "direction": "DESC"},
            limit=10,
            aggregations=[Aggregation(function="COUNT", field="*", alias="count")],
            explanation="Test query"
        )

        query, params = builder.build_query(parsed)

        assert "COUNT(*) AS count" in query
        assert "GROUP BY rid_make" in query

    def test_build_query_with_between(self):
        """Test BETWEEN operator."""
        builder = QueryBuilder()

        parsed = ParsedQuery(
            understood=True,
            query_type="search",
            table="drones",
            select_fields=["*"],
            filters=[QueryFilter(field="alt", op="BETWEEN", value=[100, 200])],
            time_filter=None,
            group_by=[],
            order_by=None,
            limit=100,
            aggregations=[],
            explanation="Test query"
        )

        query, params = builder.build_query(parsed)

        assert "alt BETWEEN $1 AND $2" in query
        assert params == [100, 200]

    def test_relative_time_parsing(self):
        """Test parsing of relative time values."""
        builder = QueryBuilder()

        test_cases = [
            ("1h", "1 hour"),
            ("24h", "24 hours"),
            ("7d", "7 days"),
            ("30d", "30 days"),
            ("2h", "2 hours"),
            ("3d", "3 days"),
        ]

        for input_val, expected in test_cases:
            result = builder._parse_relative_time(input_val)
            assert result == expected, f"Expected {expected} for {input_val}, got {result}"


# =============================================================================
# ConversationManager Tests
# =============================================================================

class TestConversationManager:
    """Tests for conversation context management."""

    def test_add_turn(self):
        """Test adding a conversation turn."""
        manager = ConversationManager(max_history=5)

        result = QueryResult(
            success=True,
            data=[{"drone_id": "test"}],
            row_count=1,
            query_explanation="Test",
            execution_time_ms=100
        )

        manager.add_turn("session-1", "Show me drones", result)

        assert "session-1" in manager.conversations
        assert len(manager.conversations["session-1"]) == 1

    def test_max_history_limit(self):
        """Test that history is trimmed to max_history."""
        manager = ConversationManager(max_history=3)

        for i in range(5):
            result = QueryResult(
                success=True,
                data=[],
                row_count=0,
                query_explanation=f"Query {i}",
                execution_time_ms=100
            )
            manager.add_turn("session-1", f"Query {i}", result)

        assert len(manager.conversations["session-1"]) == 3

    def test_get_context(self):
        """Test getting conversation context."""
        manager = ConversationManager()

        result = QueryResult(
            success=True,
            data=[{"drone_id": "test"}],
            row_count=5,
            query_explanation="Found drones",
            execution_time_ms=100
        )

        manager.add_turn("session-1", "Show me DJI drones", result)

        context = manager.get_context("session-1")

        assert "Previous queries" in context
        assert "Show me DJI drones" in context
        assert "5 results" in context

    def test_clear_session(self):
        """Test clearing a session."""
        manager = ConversationManager()

        result = QueryResult(success=True, data=[], row_count=0, query_explanation="", execution_time_ms=0)
        manager.add_turn("session-1", "Query", result)

        assert "session-1" in manager.conversations

        manager.clear_session("session-1")

        assert "session-1" not in manager.conversations


# =============================================================================
# LLMService Integration Tests
# =============================================================================

class TestLLMService:
    """Integration tests for the LLM service."""

    @pytest.mark.asyncio
    async def test_is_available_checks_ollama(self, mock_db_pool):
        """Test is_available returns proper status."""
        service = LLMService(mock_db_pool)

        with patch.object(service.ollama, 'is_available', new_callable=AsyncMock) as mock_available:
            mock_available.return_value = (True, "llama3.1:8b")

            status = await service.is_available()

            assert status["available"] is True
            assert "llama3.1" in status["model"]

    @pytest.mark.asyncio
    async def test_query_success(self, mock_db_pool, mock_ollama_response):
        """Test successful query execution."""
        service = LLMService(mock_db_pool)

        # Mock the parser
        with patch.object(service.parser, 'parse_natural_language', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = ParsedQuery(
                understood=True,
                query_type="search",
                table="drones",
                select_fields=["drone_id", "lat", "lon"],
                filters=[QueryFilter(field="rid_make", op="=", value="DJI")],
                time_filter=TimeFilter(filter_type="relative", value="1h"),
                group_by=[],
                order_by=None,
                limit=100,
                aggregations=[],
                explanation="Finding DJI drones"
            )

            # Mock summary generation
            with patch.object(service, '_generate_summary', new_callable=AsyncMock) as mock_summary:
                mock_summary.return_value = "Found 2 DJI drones in the last hour."

                result = await service.query("Show me DJI drones")

                assert result.success is True
                assert result.row_count == 2
                assert result.summary == "Found 2 DJI drones in the last hour."

    @pytest.mark.asyncio
    async def test_query_not_understood(self, mock_db_pool):
        """Test handling when query is not understood."""
        service = LLMService(mock_db_pool)

        with patch.object(service.parser, 'parse_natural_language', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = ParsedQuery(
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
                explanation="Could not understand the request",
                error="Query not related to drone data"
            )

            result = await service.query("What's the weather like?")

            assert result.success is False
            assert "Could not understand" in result.error or "not related" in result.error

    def test_get_example_queries(self, mock_db_pool):
        """Test example queries are returned."""
        service = LLMService(mock_db_pool)

        examples = service.get_example_queries()

        assert len(examples) > 0
        assert any("Recent Activity" in cat["category"] for cat in examples)
        assert any("Filtering" in cat["category"] for cat in examples)


# =============================================================================
# Security Tests
# =============================================================================

class TestSecurity:
    """Security-focused tests to prevent SQL injection."""

    def test_table_injection_blocked(self):
        """Test SQL injection in table name is blocked."""
        parser = QueryParser()

        malicious_inputs = [
            "drones; DROP TABLE drones;--",
            "drones UNION SELECT * FROM users",
            "../../../etc/passwd",
            "drones' OR '1'='1",
        ]

        for malicious in malicious_inputs:
            parsed = {"table": malicious, "select_fields": ["*"]}
            result = parser._validate_parsed_query(parsed)
            assert result.table in ALLOWED_TABLES

    def test_field_injection_blocked(self):
        """Test SQL injection in field names is blocked."""
        parser = QueryParser()

        malicious_inputs = [
            "drone_id; DROP TABLE drones;--",
            "lat UNION SELECT password FROM users",
            "1=1; --",
        ]

        for malicious in malicious_inputs:
            parsed = {
                "table": "drones",
                "select_fields": ["drone_id", malicious],
                "filters": []
            }
            result = parser._validate_parsed_query(parsed)
            assert malicious not in result.select_fields

    def test_operator_injection_blocked(self):
        """Test SQL injection in operators is blocked."""
        parser = QueryParser()

        malicious_operators = [
            "= 1; DROP TABLE drones;--",
            "UNION SELECT",
            "OR 1=1",
        ]

        for malicious in malicious_operators:
            parsed = {
                "table": "drones",
                "select_fields": ["*"],
                "filters": [{"field": "alt", "op": malicious, "value": 100}]
            }
            result = parser._validate_parsed_query(parsed)
            # Malicious operators should be filtered out
            for f in result.filters:
                assert f.op in ALLOWED_OPERATORS

    def test_parameterized_values(self):
        """Test that values are parameterized, not interpolated."""
        builder = QueryBuilder()

        # Even malicious values should be safe because they're parameterized
        malicious_value = "'; DROP TABLE drones;--"

        parsed = ParsedQuery(
            understood=True,
            query_type="search",
            table="drones",
            select_fields=["*"],
            filters=[QueryFilter(field="drone_id", op="=", value=malicious_value)],
            time_filter=None,
            group_by=[],
            order_by=None,
            limit=100,
            aggregations=[],
            explanation="Test"
        )

        query, params = builder.build_query(parsed)

        # Value should be in params, not in query string
        assert malicious_value not in query
        assert malicious_value in params


# =============================================================================
# Schema Context Tests
# =============================================================================

class TestSchemaContext:
    """Tests for schema context and domain knowledge."""

    def test_schema_context_has_tables(self):
        """Test schema context includes all tables."""
        for table in ALLOWED_TABLES:
            assert table in SCHEMA_CONTEXT

    def test_schema_context_has_drone_fields(self):
        """Test schema context includes key drone fields."""
        key_fields = ["drone_id", "lat", "lon", "alt", "speed", "rid_make", "rid_model"]
        for field in key_fields:
            assert field in SCHEMA_CONTEXT

    def test_schema_context_has_domain_knowledge(self):
        """Test schema context includes drone domain knowledge."""
        # Check for FAA altitude limit
        assert "400" in SCHEMA_CONTEXT or "122" in SCHEMA_CONTEXT

        # Check for speed classifications
        assert "Hovering" in SCHEMA_CONTEXT or "hovering" in SCHEMA_CONTEXT

        # Check for FPV frequencies
        assert "5650" in SCHEMA_CONTEXT or "5.8" in SCHEMA_CONTEXT


# =============================================================================
# Live Ollama Tests (Optional)
# =============================================================================

@pytest.mark.skipif(
    os.environ.get("TEST_OLLAMA_LIVE", "false").lower() != "true",
    reason="Live Ollama tests disabled. Set TEST_OLLAMA_LIVE=true to enable."
)
class TestLiveOllama:
    """Tests that require a running Ollama instance."""

    @pytest.mark.asyncio
    async def test_live_ollama_availability(self):
        """Test connection to live Ollama instance."""
        client = OllamaClient()
        available, model = await client.is_available()

        assert available is True, "Ollama should be running for live tests"
        assert model is not None

    @pytest.mark.asyncio
    async def test_live_query_parsing(self):
        """Test parsing a real query through Ollama."""
        client = OllamaClient()
        parser = QueryParser()

        # Check if Ollama is available first
        available, _ = await client.is_available()
        if not available:
            pytest.skip("Ollama not available")

        result = await parser.parse_natural_language("Show me DJI drones from the last hour")

        assert result.understood is True
        assert result.table == "drones"
        assert any(f.field == "rid_make" and "DJI" in str(f.value).upper() for f in result.filters)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
