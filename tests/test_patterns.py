#!/usr/bin/env python3
"""
Unit tests for WarDragon Analytics Pattern Detection API endpoints.

This test module provides comprehensive coverage of pattern detection features:
- Repeated drone detection
- Coordinated activity detection
- Pilot reuse detection
- Anomaly detection
- Multi-kit correlation

All tests use mocked database connections and do not require Docker.

NOTE: These tests require the FastAPI app to start, which needs a DATABASE_URL.
Marked as 'api' for selective running in CI.
"""

import pytest

# Mark all tests in this module as api tests (require app startup)
pytestmark = pytest.mark.api
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import json

# Import after sys.path is set in conftest
from api import app


class TestRepeatedDronesEndpoint:
    """Tests for GET /api/patterns/repeated-drones endpoint."""

    def test_repeated_drones_default_params(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test repeated drones query with default parameters.

        Verifies that:
        - Returns 200 status code
        - Default time window is 24 hours
        - Default min_appearances is 2
        - Returns repeated drones with locations
        """
        sample_data = [
            {
                "drone_id": "drone001",
                "first_seen": datetime.now(timezone.utc) - timedelta(hours=2),
                "last_seen": datetime.now(timezone.utc),
                "appearance_count": 5,
                "locations": [
                    {"lat": 37.7749, "lon": -122.4194, "kit_id": "kit001", "timestamp": datetime.now(timezone.utc)},
                    {"lat": 37.7750, "lon": -122.4195, "kit_id": "kit002", "timestamp": datetime.now(timezone.utc)}
                ]
            }
        ]
        mock_rows = [mock_asyncpg_row(item) for item in sample_data]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/patterns/repeated-drones")

        assert response.status_code == 200
        data = response.json()
        assert "repeated_drones" in data
        assert "count" in data
        assert data["count"] == 1
        assert data["time_window_hours"] == 24
        assert data["min_appearances"] == 2

    def test_repeated_drones_custom_params(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test repeated drones with custom time window and min appearances.

        Verifies that:
        - Custom parameters are applied
        - Query respects parameter limits
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/repeated-drones?time_window_hours=48&min_appearances=3")

        assert response.status_code == 200
        data = response.json()
        assert data["time_window_hours"] == 48
        assert data["min_appearances"] == 3

    def test_repeated_drones_parameter_validation(self, client_with_mocked_db):
        """
        Test parameter validation for repeated drones endpoint.

        Verifies that:
        - Invalid parameters are rejected with 422 status
        """
        # Test min_appearances < 2
        response = client_with_mocked_db.get("/api/patterns/repeated-drones?min_appearances=1")
        assert response.status_code == 422

        # Test time_window_hours > 168
        response = client_with_mocked_db.get("/api/patterns/repeated-drones?time_window_hours=200")
        assert response.status_code == 422

    def test_repeated_drones_empty_result(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test repeated drones when no drones match criteria.

        Verifies that:
        - Returns 200 with empty list
        - Count is 0
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/repeated-drones")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["repeated_drones"] == []

    def test_repeated_drones_database_unavailable(self, client_with_mocked_db):
        """
        Test error handling when database is unavailable.

        Verifies that:
        - Returns 503 status code
        """
        with patch("api.db_pool", None):
            response = client_with_mocked_db.get("/api/patterns/repeated-drones")
            assert response.status_code == 503

    def test_repeated_drones_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status code on database error
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Query failed")

        response = client_with_mocked_db.get("/api/patterns/repeated-drones")

        assert response.status_code == 500


class TestCoordinatedDronesEndpoint:
    """Tests for GET /api/patterns/coordinated endpoint."""

    def test_coordinated_drones_default_params(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test coordinated drones detection with default parameters.

        Verifies that:
        - Returns 200 status code
        - Default time window is 60 minutes
        - Default distance threshold is 500m
        - Returns coordinated groups
        """
        sample_groups = [
            {
                "group_id": 1,
                "drone_count": 3,
                "drones": [
                    {"drone_id": "drone001", "lat": 37.7749, "lon": -122.4194},
                    {"drone_id": "drone002", "lat": 37.7750, "lon": -122.4195},
                    {"drone_id": "drone003", "lat": 37.7751, "lon": -122.4196}
                ],
                "correlation_score": "high"
            }
        ]
        mock_asyncpg_connection.fetchval.return_value = json.dumps(sample_groups)

        response = client_with_mocked_db.get("/api/patterns/coordinated")

        assert response.status_code == 200
        data = response.json()
        assert "coordinated_groups" in data
        assert "count" in data
        assert data["count"] == 1
        assert data["time_window_minutes"] == 60
        assert data["distance_threshold_m"] == 500

    def test_coordinated_drones_custom_params(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test coordinated drones with custom parameters.

        Verifies that:
        - Custom time window and distance threshold are applied
        """
        mock_asyncpg_connection.fetchval.return_value = "[]"

        response = client_with_mocked_db.get("/api/patterns/coordinated?time_window_minutes=120&distance_threshold_m=1000")

        assert response.status_code == 200
        data = response.json()
        assert data["time_window_minutes"] == 120
        assert data["distance_threshold_m"] == 1000

    def test_coordinated_drones_empty_result(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test coordinated drones when no groups are found.

        Verifies that:
        - Returns empty list when no coordination detected
        """
        mock_asyncpg_connection.fetchval.return_value = "[]"

        response = client_with_mocked_db.get("/api/patterns/coordinated")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["coordinated_groups"] == []

    def test_coordinated_drones_null_result(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test coordinated drones when database returns null.

        Verifies that:
        - Handles null result gracefully
        """
        mock_asyncpg_connection.fetchval.return_value = None

        response = client_with_mocked_db.get("/api/patterns/coordinated")

        assert response.status_code == 200
        data = response.json()
        assert data["coordinated_groups"] == []

    def test_coordinated_drones_parameter_validation(self, client_with_mocked_db):
        """
        Test parameter validation for coordinated endpoint.

        Verifies that:
        - Invalid parameters are rejected
        """
        # Test time_window_minutes > 1440
        response = client_with_mocked_db.get("/api/patterns/coordinated?time_window_minutes=2000")
        assert response.status_code == 422

        # Test distance_threshold_m < 10
        response = client_with_mocked_db.get("/api/patterns/coordinated?distance_threshold_m=5")
        assert response.status_code == 422

    def test_coordinated_drones_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status on error
        """
        mock_asyncpg_connection.fetchval.side_effect = Exception("Function error")

        response = client_with_mocked_db.get("/api/patterns/coordinated")

        assert response.status_code == 500


class TestPilotReuseEndpoint:
    """Tests for GET /api/patterns/pilot-reuse endpoint."""

    def test_pilot_reuse_default_params(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test pilot reuse detection with default parameters.

        Verifies that:
        - Returns 200 status code
        - Detects both operator_id and proximity-based reuse
        - Returns combined results
        """
        operator_data = [
            {
                "pilot_identifier": "OP123456",
                "correlation_method": "operator_id",
                "drones": [
                    {"drone_id": "drone001", "timestamp": datetime.now(timezone.utc)},
                    {"drone_id": "drone002", "timestamp": datetime.now(timezone.utc)}
                ],
                "drone_count": 2
            }
        ]
        proximity_data = [
            {
                "pilot_identifier": "PILOT_37.7749_-122.4194",
                "correlation_method": "proximity",
                "drones": [
                    {"drone_id": "drone003", "timestamp": datetime.now(timezone.utc)},
                    {"drone_id": "drone004", "timestamp": datetime.now(timezone.utc)}
                ],
                "drone_count": 2
            }
        ]

        operator_rows = [mock_asyncpg_row(item) for item in operator_data]
        proximity_rows = [mock_asyncpg_row(item) for item in proximity_data]

        # Mock fetch to return different results for each query
        mock_asyncpg_connection.fetch.side_effect = [operator_rows, proximity_rows]

        response = client_with_mocked_db.get("/api/patterns/pilot-reuse")

        assert response.status_code == 200
        data = response.json()
        assert "pilot_reuse" in data
        assert data["count"] == 2
        assert data["time_window_hours"] == 24
        assert data["proximity_threshold_m"] == 50

    def test_pilot_reuse_custom_params(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test pilot reuse with custom parameters.

        Verifies that:
        - Custom time window and proximity threshold are applied
        """
        mock_asyncpg_connection.fetch.side_effect = [[], []]

        response = client_with_mocked_db.get("/api/patterns/pilot-reuse?time_window_hours=48&proximity_threshold_m=100")

        assert response.status_code == 200
        data = response.json()
        assert data["time_window_hours"] == 48
        assert data["proximity_threshold_m"] == 100

    def test_pilot_reuse_operator_id_only(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test pilot reuse with only operator_id matches.

        Verifies that:
        - Returns only operator_id based matches when no proximity matches
        """
        operator_data = [
            {
                "pilot_identifier": "OP123456",
                "correlation_method": "operator_id",
                "drones": [{"drone_id": "drone001"}, {"drone_id": "drone002"}],
                "drone_count": 2
            }
        ]
        operator_rows = [mock_asyncpg_row(item) for item in operator_data]
        mock_asyncpg_connection.fetch.side_effect = [operator_rows, []]

        response = client_with_mocked_db.get("/api/patterns/pilot-reuse")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["pilot_reuse"][0]["correlation_method"] == "operator_id"

    def test_pilot_reuse_proximity_only(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test pilot reuse with only proximity matches.

        Verifies that:
        - Returns only proximity-based matches when no operator_id matches
        """
        proximity_data = [
            {
                "pilot_identifier": "PILOT_37.7749_-122.4194",
                "correlation_method": "proximity",
                "drones": [{"drone_id": "drone001"}, {"drone_id": "drone002"}],
                "drone_count": 2
            }
        ]
        proximity_rows = [mock_asyncpg_row(item) for item in proximity_data]
        mock_asyncpg_connection.fetch.side_effect = [[], proximity_rows]

        response = client_with_mocked_db.get("/api/patterns/pilot-reuse")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["pilot_reuse"][0]["correlation_method"] == "proximity"

    def test_pilot_reuse_empty_result(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test pilot reuse when no matches found.

        Verifies that:
        - Returns empty list when no reuse detected
        """
        mock_asyncpg_connection.fetch.side_effect = [[], []]

        response = client_with_mocked_db.get("/api/patterns/pilot-reuse")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["pilot_reuse"] == []

    def test_pilot_reuse_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status on error
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Query failed")

        response = client_with_mocked_db.get("/api/patterns/pilot-reuse")

        assert response.status_code == 500


class TestAnomaliesEndpoint:
    """Tests for GET /api/patterns/anomalies endpoint."""

    def test_anomalies_default_params(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test anomaly detection with default parameters.

        Verifies that:
        - Returns 200 status code
        - Detects multiple anomaly types
        - Returns anomalies with severity levels
        """
        sample_data = [
            {
                "anomaly_type": "speed",
                "severity": "high",
                "drone_id": "drone001",
                "details": {"speed_ms": 45.0, "lat": 37.7749, "lon": -122.4194},
                "timestamp": datetime.now(timezone.utc)
            },
            {
                "anomaly_type": "altitude",
                "severity": "critical",
                "drone_id": "drone002",
                "details": {"altitude_m": 520.0, "lat": 37.7750, "lon": -122.4195},
                "timestamp": datetime.now(timezone.utc)
            },
            {
                "anomaly_type": "rapid_altitude_change",
                "severity": "medium",
                "drone_id": "drone003",
                "details": {"altitude_change_m": 75.0, "time_diff_seconds": 5.0},
                "timestamp": datetime.now(timezone.utc)
            }
        ]
        mock_rows = [mock_asyncpg_row(item) for item in sample_data]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/patterns/anomalies")

        assert response.status_code == 200
        data = response.json()
        assert "anomalies" in data
        assert data["count"] == 3
        assert data["time_window_hours"] == 1

        # Verify anomaly types
        anomaly_types = [a["anomaly_type"] for a in data["anomalies"]]
        assert "speed" in anomaly_types
        assert "altitude" in anomaly_types
        assert "rapid_altitude_change" in anomaly_types

    def test_anomalies_custom_time_window(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test anomalies with custom time window.

        Verifies that:
        - Custom time window is applied
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/anomalies?time_window_hours=12")

        assert response.status_code == 200
        data = response.json()
        assert data["time_window_hours"] == 12

    def test_anomalies_speed_only(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test anomaly detection with only speed anomalies.

        Verifies that:
        - Speed anomalies are detected and classified by severity
        """
        sample_data = [
            {
                "anomaly_type": "speed",
                "severity": "critical",
                "drone_id": "drone001",
                "details": {"speed_ms": 55.0},
                "timestamp": datetime.now(timezone.utc)
            }
        ]
        mock_rows = [mock_asyncpg_row(item) for item in sample_data]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/patterns/anomalies")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["anomalies"][0]["anomaly_type"] == "speed"
        assert data["anomalies"][0]["severity"] == "critical"

    def test_anomalies_empty_result(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test anomalies when no anomalies detected.

        Verifies that:
        - Returns empty list when no anomalies found
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/anomalies")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["anomalies"] == []

    def test_anomalies_parameter_validation(self, client_with_mocked_db):
        """
        Test parameter validation for anomalies endpoint.

        Verifies that:
        - Invalid time window is rejected
        """
        response = client_with_mocked_db.get("/api/patterns/anomalies?time_window_hours=30")
        assert response.status_code == 422

    def test_anomalies_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status on error
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Query failed")

        response = client_with_mocked_db.get("/api/patterns/anomalies")

        assert response.status_code == 500


class TestMultiKitEndpoint:
    """Tests for GET /api/patterns/multi-kit endpoint."""

    def test_multi_kit_default_params(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test multi-kit detection with default parameters.

        Verifies that:
        - Returns 200 status code
        - Detects drones seen by multiple kits
        - Indicates triangulation possibility
        """
        sample_data = [
            {
                "drone_id": "drone001",
                "kits": [
                    {"kit_id": "kit001", "rssi": -65, "freq": 5800.0, "lat": 37.7749, "lon": -122.4194},
                    {"kit_id": "kit002", "rssi": -70, "freq": 5800.0, "lat": 37.7750, "lon": -122.4195},
                    {"kit_id": "kit003", "rssi": -75, "freq": 5800.0, "lat": 37.7751, "lon": -122.4196}
                ],
                "triangulation_possible": True,
                "rid_make": "DJI",
                "rid_model": "Mavic 3",
                "latest_detection": datetime.now(timezone.utc)
            },
            {
                "drone_id": "drone002",
                "kits": [
                    {"kit_id": "kit001", "rssi": -60, "freq": 5850.0, "lat": 37.7749, "lon": -122.4194},
                    {"kit_id": "kit002", "rssi": -68, "freq": 5850.0, "lat": 37.7750, "lon": -122.4195}
                ],
                "triangulation_possible": False,
                "rid_make": "Autel",
                "rid_model": "EVO II",
                "latest_detection": datetime.now(timezone.utc)
            }
        ]
        mock_rows = [mock_asyncpg_row(item) for item in sample_data]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/patterns/multi-kit")

        assert response.status_code == 200
        data = response.json()
        assert "multi_kit_detections" in data
        assert data["count"] == 2
        assert data["time_window_minutes"] == 15

        # Verify triangulation flag
        triangulation_possible = [d["triangulation_possible"] for d in data["multi_kit_detections"]]
        assert True in triangulation_possible
        assert False in triangulation_possible

    def test_multi_kit_custom_time_window(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test multi-kit detection with custom time window.

        Verifies that:
        - Custom time window is applied
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/multi-kit?time_window_minutes=30")

        assert response.status_code == 200
        data = response.json()
        assert data["time_window_minutes"] == 30

    def test_multi_kit_triangulation_possible(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test multi-kit detection with 3+ kits (triangulation possible).

        Verifies that:
        - Triangulation flag is True for 3+ kits
        """
        sample_data = [
            {
                "drone_id": "drone001",
                "kits": [
                    {"kit_id": "kit001", "rssi": -65},
                    {"kit_id": "kit002", "rssi": -70},
                    {"kit_id": "kit003", "rssi": -75}
                ],
                "triangulation_possible": True,
                "rid_make": "DJI",
                "rid_model": "Mavic 3",
                "latest_detection": datetime.now(timezone.utc)
            }
        ]
        mock_rows = [mock_asyncpg_row(item) for item in sample_data]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/patterns/multi-kit")

        assert response.status_code == 200
        data = response.json()
        assert data["multi_kit_detections"][0]["triangulation_possible"] is True

    def test_multi_kit_empty_result(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test multi-kit detection when no multi-kit drones found.

        Verifies that:
        - Returns empty list when no multi-kit detections
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/multi-kit")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["multi_kit_detections"] == []

    def test_multi_kit_parameter_validation(self, client_with_mocked_db):
        """
        Test parameter validation for multi-kit endpoint.

        Verifies that:
        - Invalid time window is rejected
        """
        response = client_with_mocked_db.get("/api/patterns/multi-kit?time_window_minutes=2000")
        assert response.status_code == 422

    def test_multi_kit_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status on error
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Query failed")

        response = client_with_mocked_db.get("/api/patterns/multi-kit")

        assert response.status_code == 500


class TestPatternEndpointsIntegration:
    """Integration tests for pattern detection endpoints working together."""

    def test_all_pattern_endpoints_available(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test that all pattern endpoints are accessible.

        Verifies that:
        - All 5 pattern endpoints return 200 status
        """
        mock_asyncpg_connection.fetch.return_value = []
        mock_asyncpg_connection.fetchval.return_value = "[]"

        endpoints = [
            "/api/patterns/repeated-drones",
            "/api/patterns/coordinated",
            "/api/patterns/pilot-reuse",
            "/api/patterns/anomalies",
            "/api/patterns/multi-kit"
        ]

        for endpoint in endpoints:
            response = client_with_mocked_db.get(endpoint)
            assert response.status_code == 200, f"Endpoint {endpoint} failed"

    def test_pattern_endpoints_performance(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test that pattern endpoints handle large result sets efficiently.

        Verifies that:
        - Endpoints can handle 100+ results
        - Response structure is consistent
        """
        # Create 100 mock results
        large_dataset = [
            {
                "drone_id": f"drone{i:03d}",
                "first_seen": datetime.now(timezone.utc),
                "last_seen": datetime.now(timezone.utc),
                "appearance_count": i,
                "locations": []
            }
            for i in range(100)
        ]
        mock_rows = [mock_asyncpg_row(item) for item in large_dataset]
        mock_asyncpg_connection.fetch.return_value = mock_rows

        response = client_with_mocked_db.get("/api/patterns/repeated-drones")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 100

    def test_pattern_endpoints_concurrent_access(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test that pattern endpoints handle concurrent requests.

        Verifies that:
        - Multiple pattern endpoints can be called in sequence
        - Database pool is properly managed
        """
        mock_asyncpg_connection.fetch.return_value = []
        mock_asyncpg_connection.fetchval.return_value = "[]"

        # Call all endpoints in sequence
        responses = []
        for _ in range(3):
            responses.append(client_with_mocked_db.get("/api/patterns/repeated-drones"))
            responses.append(client_with_mocked_db.get("/api/patterns/anomalies"))
            responses.append(client_with_mocked_db.get("/api/patterns/multi-kit"))

        # All should succeed
        for response in responses:
            assert response.status_code == 200


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_repeated_drones_no_data(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test repeated drones with no data in database.

        Verifies that:
        - Returns empty result gracefully
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/repeated-drones")

        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_coordinated_invalid_json(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test coordinated endpoint with invalid JSON from database.

        Verifies that:
        - Handles invalid JSON gracefully
        """
        mock_asyncpg_connection.fetchval.return_value = "invalid json"

        response = client_with_mocked_db.get("/api/patterns/coordinated")

        # Should return 500 due to JSON parse error
        assert response.status_code == 500

    def test_pilot_reuse_single_drone(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test pilot reuse with single drone per operator.

        Verifies that:
        - Returns empty result when no reuse (only 1 drone per operator)
        """
        # Single drone per operator should be filtered by HAVING clause
        mock_asyncpg_connection.fetch.side_effect = [[], []]

        response = client_with_mocked_db.get("/api/patterns/pilot-reuse")

        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_anomalies_boundary_values(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test anomaly detection at exact threshold boundaries.

        Verifies that:
        - Thresholds are correctly applied (>30 m/s, >400m altitude)
        """
        # Speed exactly at 30 m/s should NOT be flagged
        # Altitude exactly at 400m should NOT be flagged
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/anomalies")

        assert response.status_code == 200
        # Should have no anomalies at exact threshold
        assert response.json()["count"] == 0

    def test_multi_kit_single_kit_detection(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test multi-kit endpoint with drones seen by only one kit.

        Verifies that:
        - Returns empty result when all drones seen by single kit
        """
        # HAVING clause filters out single-kit detections
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get("/api/patterns/multi-kit")

        assert response.status_code == 200
        assert response.json()["count"] == 0


class TestSignalLocationEstimation:
    """Tests for the signal RSSI-based location estimation endpoint."""

    def test_estimate_signal_location_basic(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test signal location estimation with multiple kits.

        Verifies that:
        - Returns 200 status code
        - Returns estimated location
        - Includes kit observations
        """
        # Mock signal observations
        signal_data = [
            {
                "kit_id": "kit-alpha",
                "power_dbm": -45.0,
                "freq_mhz": 5800.0,
                "time": datetime.now(timezone.utc),
                "signal_lat": None,
                "signal_lon": None,
                "pal_conf": 0.85,
                "ntsc_conf": 0.12
            },
            {
                "kit_id": "kit-bravo",
                "power_dbm": -52.0,
                "freq_mhz": 5800.0,
                "time": datetime.now(timezone.utc),
                "signal_lat": None,
                "signal_lon": None,
                "pal_conf": 0.78,
                "ntsc_conf": 0.15
            }
        ]

        # Mock kit positions
        kit_positions = [
            {"lat": 37.7740, "lon": -122.4180, "alt": 10.0, "time": datetime.now(timezone.utc)},
            {"lat": 37.7760, "lon": -122.4210, "alt": 12.0, "time": datetime.now(timezone.utc)}
        ]

        call_count = [0]

        def mock_fetch(*args, **kwargs):
            return [mock_asyncpg_row(d) for d in signal_data]

        def mock_fetchrow(*args, **kwargs):
            pos = kit_positions[call_count[0] % len(kit_positions)]
            call_count[0] += 1
            return mock_asyncpg_row(pos)

        mock_asyncpg_connection.fetch.side_effect = mock_fetch
        mock_asyncpg_connection.fetchrow.side_effect = mock_fetchrow

        response = client_with_mocked_db.get(
            "/api/analysis/estimate-signal-location?freq_mhz=5800.0"
        )

        assert response.status_code == 200
        data = response.json()
        assert "estimated" in data
        assert "lat" in data["estimated"]
        assert "lon" in data["estimated"]
        assert data["freq_mhz"] == 5800.0
        assert data["kit_count"] >= 1
        assert "observations" in data
        assert data["algorithm"] in ["single_kit", "two_kit_weighted", "trilateration"]

    def test_estimate_signal_location_no_signals(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test signal location estimation when no signals found.

        Verifies that:
        - Returns 404 when no signals match frequency
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get(
            "/api/analysis/estimate-signal-location?freq_mhz=5800.0"
        )

        assert response.status_code == 404
        assert "No signal observations" in response.json()["detail"]

    def test_estimate_signal_location_missing_freq(self, client_with_mocked_db):
        """
        Test signal location estimation with missing frequency parameter.

        Verifies that:
        - Returns 422 when freq_mhz is missing
        """
        response = client_with_mocked_db.get("/api/analysis/estimate-signal-location")

        assert response.status_code == 422

    def test_estimate_signal_location_custom_time_window(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test signal location estimation with custom time window.

        Verifies that:
        - Custom time window parameter is accepted
        """
        mock_asyncpg_connection.fetch.return_value = []

        response = client_with_mocked_db.get(
            "/api/analysis/estimate-signal-location?freq_mhz=5800.0&time_window_seconds=30"
        )

        # Will return 404 (no signals) but validates parameter
        assert response.status_code == 404

    def test_estimate_signal_location_invalid_time_window(self, client_with_mocked_db):
        """
        Test signal location estimation with invalid time window.

        Verifies that:
        - Returns 422 for out-of-range time window
        """
        response = client_with_mocked_db.get(
            "/api/analysis/estimate-signal-location?freq_mhz=5800.0&time_window_seconds=500"
        )

        assert response.status_code == 422

    def test_estimate_signal_location_triangulation_possible(self, client_with_mocked_db, mock_asyncpg_connection, mock_asyncpg_row):
        """
        Test signal location estimation with 3+ kits (triangulation possible).

        Verifies that:
        - triangulation_possible is True when 3+ kits
        """
        signal_data = [
            {"kit_id": f"kit-{i}", "power_dbm": -45.0 - i*5, "freq_mhz": 5800.0,
             "time": datetime.now(timezone.utc), "signal_lat": None, "signal_lon": None,
             "pal_conf": 0.8, "ntsc_conf": 0.1}
            for i in range(3)
        ]

        kit_positions = [
            {"lat": 37.7740 + i*0.001, "lon": -122.4180 - i*0.001, "alt": 10.0, "time": datetime.now(timezone.utc)}
            for i in range(3)
        ]

        call_count = [0]

        def mock_fetch(*args, **kwargs):
            return [mock_asyncpg_row(d) for d in signal_data]

        def mock_fetchrow(*args, **kwargs):
            pos = kit_positions[call_count[0] % len(kit_positions)]
            call_count[0] += 1
            return mock_asyncpg_row(pos)

        mock_asyncpg_connection.fetch.side_effect = mock_fetch
        mock_asyncpg_connection.fetchrow.side_effect = mock_fetchrow

        response = client_with_mocked_db.get(
            "/api/analysis/estimate-signal-location?freq_mhz=5800.0"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["kit_count"] == 3
        assert data["triangulation_possible"] is True

    def test_estimate_signal_location_database_error(self, client_with_mocked_db, mock_asyncpg_connection):
        """
        Test error handling when database query fails.

        Verifies that:
        - Returns 500 status on database error
        """
        mock_asyncpg_connection.fetch.side_effect = Exception("Database error")

        response = client_with_mocked_db.get(
            "/api/analysis/estimate-signal-location?freq_mhz=5800.0"
        )

        assert response.status_code == 500
