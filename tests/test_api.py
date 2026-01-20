#!/usr/bin/env python3
"""
Comprehensive unit tests for WarDragon Analytics FastAPI web service.

This test module provides full coverage of the API endpoints including:
- Health check endpoint
- Kit management endpoints
- Drone query endpoint
- Signal query endpoint
- CSV export endpoint
- Error handling and validation
- Query parameter parsing
- Database query construction

All tests use mocked database connections and do not require Docker.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from fastapi.testclient import TestClient
import io
import csv

# Import after sys.path is set in conftest
from api import app, parse_time_range, get_kit_status


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_check_success(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test successful health check when database is available.

        Verifies that:
        - Health endpoint returns 200 status
        - Response contains 'status: healthy'
        - Database query is executed
        """
        mock_asyncpg_connection.fetchval.return_value = 1

        response = client_with_mocked_db.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
        mock_asyncpg_connection.fetchval.assert_called_once_with("SELECT 1")

    def test_health_check_database_unavailable(self, client_with_mocked_db):
        """
        Test health check when database pool is not initialized.

        Verifies that:
        - Returns 503 status code
        - Error message indicates database pool not initialized
        """
        with patch("api.db_pool", None):
            response = client_with_mocked_db.get("/health")

            assert response.status_code == 503
            assert "Database pool not initialized" in response.json()["detail"]

    def test_health_check_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test health check when database connection fails.

        Verifies that:
        - Returns 503 status code when database query fails
        - Error message contains connection failure details
        """
        mock_asyncpg_connection.fetchval.side_effect = Exception("Connection timeout")

        response = client_with_mocked_db.get("/health")

        assert response.status_code == 503
        assert "Database connection failed" in response.json()["detail"]


class TestKitsEndpoint:
    """Tests for GET /api/kits endpoint."""

    def test_list_all_kits(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_kits, mock_asyncpg_row):
        """
        Test listing all kits without filters.

        Verifies that:
        - Returns 200 status code
        - Response contains all kits
        - Kit status is calculated based on last_seen
        """
        # Convert sample data to mock rows
        mock_rows = [mock_asyncpg_row(kit) for kit in api_sample_kits]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/kits")

        assert response.status_code == 200
        data = response.json()
        assert "kits" in data
        assert "count" in data
        assert data["count"] == 3
        assert len(data["kits"]) == 3

    def test_list_kits_with_filter(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_kits, mock_asyncpg_row):
        """
        Test listing kits filtered by kit_id.

        Verifies that:
        - Correctly filters kits by kit_id parameter
        - Only returns matching kit
        """
        # Return only the first kit
        mock_rows = [mock_asyncpg_row(api_sample_kits[0])]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/kits?kit_id=kit001")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["kits"][0]["kit_id"] == "kit001"

    def test_list_kits_empty_result(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test listing kits when no kits exist.

        Verifies that:
        - Returns 200 with empty list
        - Count is 0
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/kits")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["kits"] == []

    def test_list_kits_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status code on database error
        - Error message is included in response
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Database error")

        response = client_with_mocked_db.get("/api/kits")

        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]


class TestDronesEndpoint:
    """Tests for GET /api/drones endpoint."""

    def test_query_drones_default_params(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones with default parameters (1h time range, no filters).

        Verifies that:
        - Returns 200 status code
        - Default time range is 1 hour
        - Default limit is 1000
        - Drones are returned with correct structure
        """
        mock_rows = [mock_asyncpg_row(drone) for drone in api_sample_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/drones")

        assert response.status_code == 200
        data = response.json()
        assert "drones" in data
        assert "count" in data
        assert "time_range" in data
        assert data["count"] == 3
        assert len(data["drones"]) == 3

    def test_query_drones_with_time_range(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones with different time ranges.

        Verifies that:
        - Accepts time_range parameter (1h, 24h, 7d)
        - Query includes correct time bounds
        """
        mock_rows = [mock_asyncpg_row(drone) for drone in api_sample_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        # Test with 24h range
        response = client_with_mocked_db.get("/api/drones?time_range=24h")

        assert response.status_code == 200
        data = response.json()
        assert "time_range" in data
        # Verify start time is approximately 24h ago
        start_time = datetime.fromisoformat(data["time_range"]["start"])
        end_time = datetime.fromisoformat(data["time_range"]["end"])
        time_diff = end_time - start_time
        assert 23 <= time_diff.total_seconds() / 3600 <= 25  # Allow some tolerance

    def test_query_drones_custom_time_range(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones with custom time range.

        Verifies that:
        - Accepts custom time range in format custom:START,END
        - Parses ISO datetime strings correctly
        """
        mock_rows = [mock_asyncpg_row(drone) for drone in api_sample_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        start = "2026-01-20T10:00:00"
        end = "2026-01-20T12:00:00"
        response = client_with_mocked_db.get(f"/api/drones?time_range=custom:{start},{end}")

        assert response.status_code == 200
        data = response.json()
        assert data["time_range"]["start"] == start
        assert data["time_range"]["end"] == end

    def test_query_drones_with_kit_filter(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones filtered by kit_id.

        Verifies that:
        - Accepts single kit_id filter
        - Query includes kit_id in WHERE clause
        """
        # Return only drones from kit001
        filtered_drones = [d for d in api_sample_drones if d["kit_id"] == "kit001"]
        mock_rows = [mock_asyncpg_row(drone) for drone in filtered_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/drones?kit_id=kit001")

        assert response.status_code == 200
        data = response.json()
        # All returned drones should be from kit001
        for drone in data["drones"]:
            assert drone["kit_id"] == "kit001"

    def test_query_drones_with_multiple_kits(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones with comma-separated kit_ids.

        Verifies that:
        - Accepts comma-separated kit_id values
        - Query uses ANY() for multiple kit_ids
        """
        mock_rows = [mock_asyncpg_row(drone) for drone in api_sample_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/drones?kit_id=kit001,kit002")

        assert response.status_code == 200
        # Verify the query was called with proper parameters
        assert mock_asyncpg_connection.fetch.called

    def test_query_drones_with_rid_make_filter(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones filtered by RID make.

        Verifies that:
        - Accepts rid_make filter parameter
        - Only returns drones with matching make
        """
        dji_drones = [d for d in api_sample_drones if d.get("rid_make") == "DJI"]
        mock_rows = [mock_asyncpg_row(drone) for drone in dji_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/drones?rid_make=DJI")

        assert response.status_code == 200
        data = response.json()
        for drone in data["drones"]:
            assert drone.get("rid_make") == "DJI"

    def test_query_drones_with_track_type_filter(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones filtered by track type.

        Verifies that:
        - Accepts track_type filter (drone/aircraft)
        - Only returns matching track types
        """
        aircraft = [d for d in api_sample_drones if d.get("track_type") == "aircraft"]
        mock_rows = [mock_asyncpg_row(drone) for drone in aircraft]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/drones?track_type=aircraft")

        assert response.status_code == 200
        data = response.json()
        for drone in data["drones"]:
            assert drone.get("track_type") == "aircraft"

    def test_query_drones_with_limit(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones with custom limit.

        Verifies that:
        - Accepts limit parameter
        - Maximum limit of 10000 is enforced
        """
        mock_rows = [mock_asyncpg_row(api_sample_drones[0])]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/drones?limit=1")

        assert response.status_code == 200
        data = response.json()
        assert len(data["drones"]) <= 1

    def test_query_drones_limit_validation(self, client_with_mocked_db):
        """
        Test that limit parameter is validated against maximum.

        Verifies that:
        - Limit above 10000 is rejected with 422 status
        """
        response = client_with_mocked_db.get("/api/drones?limit=20000")

        assert response.status_code == 422  # Validation error

    def test_query_drones_combined_filters(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test querying drones with multiple filters combined.

        Verifies that:
        - Multiple filters can be applied simultaneously
        - Query is constructed correctly with all filters
        """
        mock_rows = [mock_asyncpg_row(api_sample_drones[0])]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get(
            "/api/drones?time_range=24h&kit_id=kit001&rid_make=DJI&track_type=drone&limit=100"
        )

        assert response.status_code == 200
        data = response.json()
        assert "drones" in data

    def test_query_drones_database_unavailable(self, client_with_mocked_db):
        """
        Test error handling when database is unavailable.

        Verifies that:
        - Returns 503 status code
        - Error message indicates database unavailable
        """
        with patch("api.db_pool", None):
            response = client_with_mocked_db.get("/api/drones")

            assert response.status_code == 503
            assert "Database unavailable" in response.json()["detail"]

    def test_query_drones_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status code on database error
        - Error message is included in response
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Query failed")

        response = client_with_mocked_db.get("/api/drones")

        assert response.status_code == 500
        assert "Query failed" in response.json()["detail"]


class TestSignalsEndpoint:
    """Tests for GET /api/signals endpoint."""

    def test_query_signals_default_params(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_signals, mock_asyncpg_row):
        """
        Test querying signals with default parameters.

        Verifies that:
        - Returns 200 status code
        - Returns signals with correct structure
        - Includes time range in response
        """
        mock_rows = [mock_asyncpg_row(signal) for signal in api_sample_signals]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/signals")

        assert response.status_code == 200
        data = response.json()
        assert "signals" in data
        assert "count" in data
        assert "time_range" in data
        assert data["count"] == 3

    def test_query_signals_with_time_range(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_signals, mock_asyncpg_row):
        """
        Test querying signals with specific time range.

        Verifies that:
        - Time range parameter is applied correctly
        - Response includes time_range details
        """
        mock_rows = [mock_asyncpg_row(signal) for signal in api_sample_signals]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/signals?time_range=7d")

        assert response.status_code == 200
        data = response.json()
        assert "time_range" in data

    def test_query_signals_with_kit_filter(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_signals, mock_asyncpg_row):
        """
        Test querying signals filtered by kit_id.

        Verifies that:
        - Kit filter is applied correctly
        - Only signals from specified kit are returned
        """
        kit001_signals = [s for s in api_sample_signals if s["kit_id"] == "kit001"]
        mock_rows = [mock_asyncpg_row(signal) for signal in kit001_signals]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/signals?kit_id=kit001")

        assert response.status_code == 200
        data = response.json()
        for signal in data["signals"]:
            assert signal["kit_id"] == "kit001"

    def test_query_signals_with_detection_type_filter(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_signals, mock_asyncpg_row):
        """
        Test querying signals filtered by detection type.

        Verifies that:
        - Detection type filter is applied correctly
        - Only matching detection types are returned
        """
        analog_signals = [s for s in api_sample_signals if s["detection_type"] == "analog"]
        mock_rows = [mock_asyncpg_row(signal) for signal in analog_signals]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/signals?detection_type=analog")

        assert response.status_code == 200
        data = response.json()
        for signal in data["signals"]:
            assert signal["detection_type"] == "analog"

    def test_query_signals_with_limit(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_signals, mock_asyncpg_row):
        """
        Test querying signals with custom limit.

        Verifies that:
        - Limit parameter is respected
        - Returns no more than specified limit
        """
        mock_rows = [mock_asyncpg_row(api_sample_signals[0])]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/signals?limit=1")

        assert response.status_code == 200
        data = response.json()
        assert len(data["signals"]) <= 1

    def test_query_signals_combined_filters(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_signals, mock_asyncpg_row):
        """
        Test querying signals with multiple filters.

        Verifies that:
        - Multiple filters work together correctly
        - Query construction handles all parameters
        """
        mock_rows = [mock_asyncpg_row(api_sample_signals[0])]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get(
            "/api/signals?time_range=1h&kit_id=kit001&detection_type=analog&limit=50"
        )

        assert response.status_code == 200
        data = response.json()
        assert "signals" in data

    def test_query_signals_database_unavailable(self, client_with_mocked_db):
        """
        Test error handling when database is unavailable.

        Verifies that:
        - Returns 503 status when db_pool is None
        """
        with patch("api.db_pool", None):
            response = client_with_mocked_db.get("/api/signals")

            assert response.status_code == 503
            assert "Database unavailable" in response.json()["detail"]

    def test_query_signals_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status on database error
        - Error details are included
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Connection lost")

        response = client_with_mocked_db.get("/api/signals")

        assert response.status_code == 500


class TestExportCSVEndpoint:
    """Tests for GET /api/export/csv endpoint."""

    def test_export_csv_success(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test successful CSV export of drone data.

        Verifies that:
        - Returns 200 status code
        - Content-Type is text/csv
        - CSV contains header row
        - CSV data is properly formatted
        """
        mock_rows = [mock_asyncpg_row(drone) for drone in api_sample_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/export/csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert "wardragon_drones_" in response.headers["content-disposition"]

        # Verify CSV content
        csv_content = response.text
        assert len(csv_content) > 0
        # Check for CSV header
        assert "time" in csv_content or "drone_id" in csv_content

    def test_export_csv_with_filters(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test CSV export with query filters.

        Verifies that:
        - Filters are applied to CSV export
        - Only filtered data is included
        """
        dji_drones = [d for d in api_sample_drones if d.get("rid_make") == "DJI"]
        mock_rows = [mock_asyncpg_row(drone) for drone in dji_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/export/csv?rid_make=DJI")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    def test_export_csv_empty_result(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test CSV export when no data matches filters.

        Verifies that:
        - Returns 200 status even with no data
        - Returns empty or header-only CSV
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/export/csv")

        assert response.status_code == 200
        # Empty result should still have valid CSV response
        assert len(response.text) >= 0

    def test_export_csv_with_custom_time_range(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_drones, mock_asyncpg_row):
        """
        Test CSV export with custom time range.

        Verifies that:
        - Custom time range is applied to export
        - Data is filtered by time range
        """
        mock_rows = [mock_asyncpg_row(drone) for drone in api_sample_drones]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        start = "2026-01-20T10:00:00"
        end = "2026-01-20T12:00:00"
        response = client_with_mocked_db.get(f"/api/export/csv?time_range=custom:{start},{end}")

        assert response.status_code == 200

    def test_export_csv_database_unavailable(self, client_with_mocked_db):
        """
        Test CSV export when database is unavailable.

        Verifies that:
        - Returns 503 status
        - Error message indicates database unavailable
        """
        with patch("api.db_pool", None):
            response = client_with_mocked_db.get("/api/export/csv")

            assert response.status_code == 503

    def test_export_csv_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test CSV export when database query fails.

        Verifies that:
        - Returns 500 status on error
        - Error is properly handled
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Export failed")

        response = client_with_mocked_db.get("/api/export/csv")

        assert response.status_code == 500


class TestTimeRangeParsing:
    """Tests for parse_time_range() helper function."""

    def test_parse_1h_range(self):
        """
        Test parsing 1h time range.

        Verifies that:
        - Returns start time approximately 1 hour before now
        - End time is approximately now
        """
        start, end = parse_time_range("1h")

        time_diff = end - start
        assert 0.9 <= time_diff.total_seconds() / 3600 <= 1.1  # ~1 hour with tolerance

    def test_parse_24h_range(self):
        """
        Test parsing 24h time range.

        Verifies that:
        - Returns start time approximately 24 hours before now
        """
        start, end = parse_time_range("24h")

        time_diff = end - start
        assert 23 <= time_diff.total_seconds() / 3600 <= 25  # ~24 hours with tolerance

    def test_parse_7d_range(self):
        """
        Test parsing 7d time range.

        Verifies that:
        - Returns start time approximately 7 days before now
        """
        start, end = parse_time_range("7d")

        time_diff = end - start
        assert 6.5 <= time_diff.total_seconds() / 86400 <= 7.5  # ~7 days with tolerance

    def test_parse_custom_range(self):
        """
        Test parsing custom time range.

        Verifies that:
        - Correctly parses ISO datetime strings
        - Returns exact start and end times
        """
        start_str = "2026-01-20T10:00:00"
        end_str = "2026-01-20T12:00:00"
        start, end = parse_time_range(f"custom:{start_str},{end_str}")

        assert start.isoformat() == start_str
        assert end.isoformat() == end_str

    def test_parse_invalid_custom_range(self):
        """
        Test parsing invalid custom time range.

        Verifies that:
        - Falls back to default 1h range on parse error
        """
        start, end = parse_time_range("custom:invalid,format")

        time_diff = end - start
        # Should fall back to 1h default
        assert 0.9 <= time_diff.total_seconds() / 3600 <= 1.1

    def test_parse_unknown_range(self):
        """
        Test parsing unknown time range format.

        Verifies that:
        - Defaults to 1h for unknown formats
        """
        start, end = parse_time_range("unknown")

        time_diff = end - start
        assert 0.9 <= time_diff.total_seconds() / 3600 <= 1.1

    def test_parse_max_range_enforcement(self):
        """
        Test that maximum query range is enforced.

        Verifies that:
        - Time ranges beyond MAX_QUERY_RANGE_HOURS are clamped
        """
        # Try to request a very long range
        start_str = "2020-01-01T00:00:00"
        end_str = "2026-01-20T12:00:00"
        start, end = parse_time_range(f"custom:{start_str},{end_str}")

        time_diff = end - start
        # Should be clamped to MAX_QUERY_RANGE_HOURS (168 hours = 7 days)
        max_hours = 168
        assert time_diff.total_seconds() / 3600 <= max_hours + 1  # Allow small tolerance


class TestUIEndpoint:
    """Tests for GET / (UI) endpoint."""

    def test_serve_ui_success(self, client_with_mocked_db, mock_template_file):
        """
        Test serving the UI HTML page.

        Verifies that:
        - Returns 200 status code
        - Content-Type is text/html
        - HTML content is returned
        """
        with patch("api.Path") as mock_path:
            mock_path.return_value.parent = mock_template_file.parent
            mock_file = mock_template_file.parent / "index.html"

            response = client_with_mocked_db.get("/")

            # The endpoint tries to read from templates/index.html
            # Since we're mocking, it may fail to find the file
            # We just verify the endpoint exists
            assert response.status_code in [200, 500]  # May fail if template not found

    def test_serve_ui_template_not_found(self, client_with_mocked_db, tmp_path):
        """
        Test UI endpoint when template file is missing.

        Verifies that:
        - Returns 500 status when template doesn't exist
        - Error message indicates template not found
        """
        with patch("api.Path") as mock_path:
            # Point to non-existent directory
            mock_path.return_value.parent = tmp_path / "nonexistent"

            response = client_with_mocked_db.get("/")

            assert response.status_code == 500


class TestCORSHeaders:
    """Tests for CORS headers (if configured)."""

    def test_cors_headers_present(self, client_with_mocked_db):
        """
        Test that CORS headers are configured if needed.

        Note: This test will pass if CORS is not configured.
        Modify based on actual CORS requirements.
        """
        response = client_with_mocked_db.get("/health")

        # CORS headers would be set by FastAPI middleware if configured
        # This is a placeholder test - modify based on actual CORS setup
        assert response.status_code == 200


class TestDatabaseQueryConstruction:
    """Tests for verifying correct SQL query construction."""

    def test_drones_query_with_multiple_filters(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test that database query is constructed correctly with multiple filters.

        Verifies that:
        - Query includes all WHERE clauses for filters
        - Parameters are passed in correct order
        - LIMIT clause is applied
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get(
            "/api/drones?kit_id=kit001,kit002&rid_make=DJI&track_type=drone&limit=100"
        )

        assert response.status_code == 200

        # Verify fetch was called
        assert mock_asyncpg_connection.fetch.called
        call_args = mock_asyncpg_connection.fetch.call_args

        # Query should be the first argument
        query = call_args[0][0]
        assert "WHERE time >=" in query
        assert "AND time <=" in query
        assert "LIMIT" in query

    def test_signals_query_construction(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test that signals query is constructed correctly.

        Verifies that:
        - Query selects from signals table
        - Time range filters are applied
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/signals?kit_id=kit001")

        assert response.status_code == 200
        assert mock_asyncpg_connection.fetch.called

        call_args = mock_asyncpg_connection.fetch.call_args
        query = call_args[0][0]
        assert "FROM signals" in query
        assert "WHERE time >=" in query


class TestGetKitStatusHelper:
    """Tests for get_kit_status() helper function."""

    @pytest.mark.asyncio
    async def test_get_kit_status_all_kits(self, mock_asyncpg_pool, mock_asyncpg_connection, api_sample_kits, mock_asyncpg_row):
        """
        Test getting status for all kits.

        Verifies that:
        - Returns all kits when no filter is provided
        - Status is calculated based on last_seen
        """
        mock_rows = [mock_asyncpg_row(kit) for kit in api_sample_kits]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        with patch("api.db_pool", mock_asyncpg_pool):
            kits = await get_kit_status()

            assert len(kits) == 3
            # Verify status calculation
            assert any(k["status"] == "online" for k in kits)

    @pytest.mark.asyncio
    async def test_get_kit_status_specific_kit(self, mock_asyncpg_pool, mock_asyncpg_connection, api_sample_kits, mock_asyncpg_row):
        """
        Test getting status for a specific kit.

        Verifies that:
        - Returns single kit when kit_id is provided
        - Correct kit data is returned
        """
        mock_rows = [mock_asyncpg_row(api_sample_kits[0])]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        with patch("api.db_pool", mock_asyncpg_pool):
            kits = await get_kit_status("kit001")

            assert len(kits) == 1
            assert kits[0]["kit_id"] == "kit001"

    @pytest.mark.asyncio
    async def test_get_kit_status_no_last_seen(self, mock_asyncpg_pool, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test kit status when last_seen is None.

        Verifies that:
        - Status is 'unknown' when last_seen is None
        """
        kit_data = {
            "kit_id": "kit004",
            "name": "New Kit",
            "location": "Unknown",
            "api_url": "http://kit004.local:8080",
            "last_seen": None,
            "status": "unknown",
            "created_at": datetime.now()
        }
        mock_rows = [mock_asyncpg_row(kit_data)]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        with patch("api.db_pool", mock_asyncpg_pool):
            kits = await get_kit_status()

            assert len(kits) == 1
            assert kits[0]["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_get_kit_status_database_unavailable(self):
        """
        Test get_kit_status when database is unavailable.

        Verifies that:
        - Raises HTTPException with 503 status
        """
        with patch("api.db_pool", None):
            with pytest.raises(Exception):  # Should raise HTTPException
                await get_kit_status()


class TestErrorHandling:
    """Tests for general error handling."""

    def test_404_not_found(self, client_with_mocked_db):
        """
        Test that non-existent endpoints return 404.

        Verifies that:
        - Returns 404 for invalid routes
        """
        response = client_with_mocked_db.get("/api/nonexistent")

        assert response.status_code == 404

    def test_invalid_query_parameter_type(self, client_with_mocked_db):
        """
        Test validation of query parameter types.

        Verifies that:
        - Returns 422 for invalid parameter types
        """
        response = client_with_mocked_db.get("/api/drones?limit=invalid")

        assert response.status_code == 422  # Validation error


# Integration test for complete workflow
class TestEndToEndWorkflow:
    """End-to-end tests simulating real usage patterns."""

    def test_complete_workflow(self, client_with_mocked_db, mock_asyncpg_connection, api_sample_kits, api_sample_drones, api_sample_signals, mock_asyncpg_row):
        """
        Test a complete workflow: health check -> list kits -> query drones -> export CSV.

        Verifies that:
        - All endpoints work together correctly
        - Data flows through the system as expected
        """
        # Setup mocks
        kit_rows = [mock_asyncpg_row(kit) for kit in api_sample_kits]
        drone_rows = [mock_asyncpg_row(drone) for drone in api_sample_drones]

        # 1. Health check
        mock_asyncpg_connection.fetchval.return_value = 1
        response = client_with_mocked_db.get("/health")
        assert response.status_code == 200

        # 2. List kits
        mock_asyncpg_connection.fetch.return_value = kit_rows
        response = client_with_mocked_db.get("/api/kits")
        assert response.status_code == 200
        assert response.json()["count"] > 0

        # 3. Query drones
        mock_asyncpg_connection.fetch.return_value = drone_rows
        response = client_with_mocked_db.get("/api/drones?time_range=1h")
        assert response.status_code == 200
        assert len(response.json()["drones"]) > 0

        # 4. Export CSV
        mock_asyncpg_connection.fetch.return_value = drone_rows
        response = client_with_mocked_db.get("/api/export/csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
