# WarDragon Analytics Test Suite

This directory contains the test suite for WarDragon Analytics, including both unit tests and integration tests.

## API Unit Tests Quick Start

The `test_api.py` module provides comprehensive unit tests for the FastAPI web service. These tests run **without Docker** and use mocked database connections for fast execution.

### Running API Tests

```bash
# Install test dependencies
cd /home/dragon/Downloads/wardragon-fpv-detect/WarDragonAnalytics
pip install pytest pytest-asyncio pytest-cov

# Run all API tests
pytest tests/test_api.py -v

# Run specific test class
pytest tests/test_api.py::TestHealthEndpoint -v

# Run with coverage
pytest tests/test_api.py --cov=app --cov-report=term-missing

# Run and generate HTML coverage report
pytest tests/test_api.py --cov=app --cov-report=html
open htmlcov/index.html
```

### API Test Coverage

The `test_api.py` file includes tests for:

- **GET /health** - Health check endpoint (3 tests)
- **GET /api/kits** - List kits with status (4 tests)
- **GET /api/drones** - Query drone tracks with filters (12 tests)
- **GET /api/signals** - Query FPV signals with filters (8 tests)
- **GET /api/export/csv** - Export drones to CSV (6 tests)
- **GET /** - Serve UI HTML page (2 tests)
- **Helper functions** - Time range parsing, kit status calculation (11 tests)
- **Error handling** - 404, 422, 500 status codes (2 tests)
- **End-to-end workflow** - Complete user journey (1 test)

**Total: 49 comprehensive unit tests**

### Test Features

- All tests use **mocked asyncpg connections** - no database required
- Tests verify **query parameter validation** (time_range, kit_id, limit)
- Tests check **error handling** (database unavailable, query failures)
- Tests validate **SQL query construction** with multiple filters
- Tests confirm **CSV export** with proper headers and formatting
- Each test includes detailed docstrings explaining what is verified

### Example Test Execution

```bash
# Successful run example
$ pytest tests/test_api.py -v

tests/test_api.py::TestHealthEndpoint::test_health_check_success PASSED           [ 2%]
tests/test_api.py::TestHealthEndpoint::test_health_check_database_unavailable PASSED [ 4%]
tests/test_api.py::TestKitsEndpoint::test_list_all_kits PASSED                   [ 6%]
tests/test_api.py::TestDronesEndpoint::test_query_drones_default_params PASSED   [ 8%]
tests/test_api.py::TestDronesEndpoint::test_query_drones_with_time_range PASSED  [10%]
tests/test_api.py::TestSignalsEndpoint::test_query_signals_default_params PASSED [12%]
tests/test_api.py::TestExportCSVEndpoint::test_export_csv_success PASSED         [14%]
...
======================== 49 passed in 2.34s =========================
```

### Test Fixtures

Key fixtures defined in `conftest.py`:

- `mock_asyncpg_pool` - Mock database connection pool
- `mock_asyncpg_connection` - Mock database connection with fetch/fetchval
- `client_with_mocked_db` - FastAPI TestClient with mocked database
- `api_sample_kits` - Sample kit data (3 kits with different statuses)
- `api_sample_drones` - Sample drone tracks (3 tracks: DJI, Autel, aircraft)
- `api_sample_signals` - Sample FPV signals (3 detections: analog, DJI)
- `mock_asyncpg_row` - Factory for creating mock database row objects

### Debugging Failed Tests

```bash
# Show detailed failure information
pytest tests/test_api.py -vv --tb=long

# Show print statements
pytest tests/test_api.py -s

# Run single test for debugging
pytest tests/test_api.py::TestDronesEndpoint::test_query_drones_with_kit_filter -vv -s

# Use pdb debugger on failure
pytest tests/test_api.py --pdb
```

## Test Structure

```
tests/
├── README.md                    # This file
├── conftest.py                  # Shared test fixtures (collector + API)
├── __init__.py                  # Package marker
├── test_api.py                  # Unit tests for API endpoints (NEW - 49 tests)
├── test_collector.py            # Unit tests for collector service
├── test_database.py             # Unit tests for database operations
├── test_integration.py          # Basic integration tests
└── integration/                 # Full-stack integration tests
    ├── __init__.py
    ├── conftest.py              # Integration test fixtures
    └── test_full_stack.py       # Full-stack integration tests
```

## Test Categories

### Unit Tests
Fast tests that don't require external dependencies (no Docker, no database).

**Files:** `test_database.py` (skips if `TEST_DATABASE_URL` not set)

**Run with:**
```bash
pytest -m "not api and not collector"
```

### API Tests
Tests for FastAPI endpoints. Require the app to start (which needs database connectivity).

**Files:** `test_api.py`, `test_patterns.py`

**Run with:**
```bash
pytest -m api
```

### Collector Tests
Tests for the collector service. Require heavy dependencies.

**Files:** `test_collector.py`

**Run with:**
```bash
pytest -m collector
```

### Integration Tests
Full-stack tests that require Docker Compose and a real database.

**Files:** `integration/test_full_stack.py`

**Run with:**
```bash
pytest -m integration
```

## Running Tests

### Prerequisites

1. **Python Dependencies:**
   ```bash
   pip install pytest pytest-asyncio pytest-cov httpx asyncpg sqlalchemy
   ```

2. **Docker and Docker Compose:**
   - Docker must be installed and running
   - Docker Compose v1.29+ or Docker Compose Plugin v2.0+

### Quick Start

**Run all tests:**
```bash
pytest
```

**Run only unit tests (fast, no Docker):**
```bash
pytest -m unit
```

**Run only integration tests:**
```bash
pytest -m integration
```

**Run specific test file:**
```bash
pytest tests/integration/test_full_stack.py
```

**Run specific test class:**
```bash
pytest tests/integration/test_full_stack.py::TestDronesAPI
```

**Run specific test:**
```bash
pytest tests/integration/test_full_stack.py::TestDronesAPI::test_query_all_drones
```

### Integration Tests with Docker

Integration tests automatically start and stop Docker containers. The test suite handles this for you.

**Manual Docker control (optional):**

Start test stack:
```bash
docker-compose -f docker-compose.test.yml up -d
```

Wait for services to be healthy:
```bash
# TimescaleDB
docker-compose -f docker-compose.test.yml ps timescaledb-test
# Web API
curl http://localhost:8090/health
```

Run tests:
```bash
pytest -m integration
```

Stop and clean up:
```bash
docker-compose -f docker-compose.test.yml down -v
```

**Note:** The `-v` flag removes volumes, ensuring a clean state for the next test run.

### Test Output Options

**Verbose output:**
```bash
pytest -v
```

**Show print statements:**
```bash
pytest -s
```

**Show detailed failure info:**
```bash
pytest -vv --tb=long
```

**Show test durations:**
```bash
pytest --durations=10
```

**Run with coverage:**
```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

## Test Markers

Tests are organized with pytest markers for easy filtering:

| Marker | Description |
|--------|-------------|
| `unit` | Fast unit tests, no external dependencies |
| `integration` | Full-stack tests requiring Docker |
| `slow` | Tests that take >1 second |
| `api` | API endpoint tests |
| `collector` | Collector service tests |
| `database` | Database interaction tests |

**Example usage:**
```bash
# Run only API tests
pytest -m api

# Run everything except slow tests
pytest -m "not slow"

# Run integration tests for API only
pytest -m "integration and api"
```

## Test Environment Variables

Integration tests use these environment variables (defaults shown):

```bash
# Database configuration
TEST_DB_HOST=localhost
TEST_DB_PORT=5432
TEST_DB_NAME=wardragon
TEST_DB_USER=wardragon
TEST_DB_PASSWORD=test_password

# API configuration
TEST_API_HOST=localhost
TEST_API_PORT=8090
```

**Override for custom setup:**
```bash
export TEST_DB_HOST=192.168.1.100
export TEST_API_PORT=9090
pytest -m integration
```

## Writing New Tests

### Unit Test Example

```python
import pytest

@pytest.mark.unit
def test_something():
    """Test description."""
    result = my_function()
    assert result == expected
```

### Integration Test Example

```python
import pytest

pytestmark = pytest.mark.integration

class TestMyFeature:
    """Test my feature with real database."""

    @pytest.mark.asyncio
    async def test_with_database(self, db_conn, clean_database):
        """Test database operations."""
        await db_conn.execute("INSERT INTO ...")
        result = await db_conn.fetchval("SELECT ...")
        assert result == expected

    def test_with_api(self, api_client, sample_data):
        """Test API endpoints."""
        response = api_client.get("/api/endpoint")
        assert response.status_code == 200
```

## Available Fixtures

### Integration Test Fixtures (from `integration/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `docker_services` | session | Ensures Docker Compose stack is running |
| `db_pool` | function | Async database connection pool |
| `db_conn` | function | Single database connection |
| `clean_database` | function | Cleans all tables before test |
| `api_client` | function | Synchronous HTTP client |
| `async_api_client` | function | Async HTTP client |
| `sample_kits` | function | Inserts 3 sample kits |
| `sample_drones` | function | Inserts sample drone data |
| `sample_signals` | function | Inserts sample signal data |
| `sample_health` | function | Inserts sample health data |

### Example Usage

```python
@pytest.mark.asyncio
async def test_my_feature(db_conn, clean_database, sample_kits, sample_drones):
    """
    Test with clean database and sample data.

    - clean_database: ensures tables are empty
    - sample_kits: inserts 3 test kits
    - sample_drones: inserts 5 test drones
    """
    # Your test code here
    result = await db_conn.fetch("SELECT * FROM drones")
    assert len(result) == 5
```

## Test Data

Sample data fixtures create realistic test scenarios:

**Sample Kits:**
- `test-kit-001`: Alpha (online)
- `test-kit-002`: Bravo (online)
- `test-kit-003`: Charlie (offline)

**Sample Drones:**
- DJI Mavic 3 (detected by kit-001)
- DJI Mini 4 Pro (detected by kit-002)
- Autel EVO II (detected by kit-001)
- Aircraft ADS-B (detected by kit-002)
- DJI Mavic 3 (detected by kit-002 - multi-kit tracking)

**Sample Signals:**
- 5658 MHz analog FPV (kit-001)
- 5917 MHz analog FPV (kit-001)
- 5745 MHz DJI digital (kit-002)
- 5800 MHz weak analog (kit-002)

## Troubleshooting

### Docker Errors

**Problem:** `Failed to start Docker services`

**Solution:**
```bash
# Check Docker is running
docker ps

# Clean up old containers
docker-compose -f docker-compose.test.yml down -v

# Rebuild if needed
docker-compose -f docker-compose.test.yml build --no-cache
```

### Port Conflicts

**Problem:** `Port 5432 or 8090 already in use`

**Solution:**
```bash
# Stop production stack
docker-compose down

# Or use custom ports
export TEST_DB_PORT=5433
export TEST_API_PORT=8091
pytest -m integration
```

### Database Connection Errors

**Problem:** `Database unavailable` or `Connection refused`

**Solution:**
```bash
# Check TimescaleDB is healthy
docker-compose -f docker-compose.test.yml ps

# View logs
docker-compose -f docker-compose.test.yml logs timescaledb-test

# Restart services
docker-compose -f docker-compose.test.yml restart
```

### Slow Tests

**Problem:** Tests timing out or running slowly

**Solution:**
```bash
# Run only fast tests
pytest -m "not slow"

# Increase timeout (requires pytest-timeout)
pytest --timeout=600

# Run tests in parallel (requires pytest-xdist)
pip install pytest-xdist
pytest -n auto  # Use all CPU cores
```

## CI/CD Integration

### Current GitHub Actions Configuration

The CI pipeline runs tests that don't require Docker or database connectivity:

```yaml
- name: Run unit tests
  run: |
    pytest -v --tb=short --ignore=tests/integration -m "not api and not collector"
```

This skips:
- `api` marked tests (require FastAPI app startup with database)
- `collector` marked tests (require heavy dependencies)
- `integration/` directory (require full Docker stack)

The remaining tests (like `test_database.py`) skip gracefully when `TEST_DATABASE_URL` is not set.

### Running Full Test Suite Locally

For comprehensive testing with Docker:

```bash
# Start the stack
docker-compose up -d

# Run all tests
pytest -v

# Run specific categories
pytest -m api -v        # API tests
pytest -m collector -v  # Collector tests
pytest -m integration   # Integration tests
```

## Best Practices

1. **Use appropriate markers** - Mark tests correctly for easy filtering
2. **Clean state** - Use `clean_database` fixture to ensure test isolation
3. **Descriptive names** - Use clear test names that describe what's being tested
4. **One assertion per test** - Keep tests focused and easy to debug
5. **Use fixtures** - Leverage provided fixtures for common setup
6. **Async tests** - Use `@pytest.mark.asyncio` for async test functions
7. **Test real scenarios** - Integration tests should match production workflows
8. **Document complex tests** - Add docstrings explaining test purpose and data flow

## Performance Tips

- Run unit tests frequently during development (fast feedback)
- Run integration tests before committing (comprehensive validation)
- Use `-m "not slow"` to skip long-running tests during rapid iteration
- Run full suite in CI/CD before merging to main branch
- Use `--durations=10` to identify slow tests for optimization

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [Docker Compose documentation](https://docs.docker.com/compose/)
- [TimescaleDB documentation](https://docs.timescale.com/)

## Getting Help

If you encounter issues with the test suite:

1. Check this README for troubleshooting steps
2. Review test logs: `tests/test-output.log`
3. Check Docker logs: `docker-compose -f docker-compose.test.yml logs`
4. Run with verbose output: `pytest -vv -s`
5. Consult the main project documentation

---

## Phase 2 Test Data Generator

The Phase 2 test data generator (`tests/generate_test_data.py`) creates realistic test scenarios with specific patterns for testing tactical dashboards and pattern detection features.

### Quick Start

```bash
# Generate all test scenarios (recommended for first-time setup)
python tests/generate_test_data.py --scenario all

# Generate specific scenario
python tests/generate_test_data.py --scenario coordinated --count 5

# Preview without inserting (dry run)
python tests/generate_test_data.py --scenario normal --dry-run

# Clean all test data
python tests/generate_test_data.py --clean
```

### Available Scenarios

#### 1. Normal Operations (`--scenario normal`)
**Purpose**: Baseline operations for testing dashboards with typical activity

**Generates**:
- 3 test kits (test-kit-001, test-kit-002, test-kit-003)
- 20-30 random drones with realistic flight patterns
- Altitude: 50-150m (typical consumer drone range)
- Speed: 5-15 m/s (typical flight speeds)
- Data spread over last 48 hours
- System health metrics for all kits

**Use Case**: Testing basic dashboards, verifying data collection, establishing baseline

**Example**:
```bash
python tests/generate_test_data.py --scenario normal
```

#### 2. Repeated Drone (`--scenario repeated`)
**Purpose**: Simulate surveillance pattern with same drone appearing multiple times

**Generates**:
- Same drone ID appearing 3-5 times over 24 hours
- Different locations each time (within same general area)
- Same operator ID across all appearances
- Realistic flight durations (15-30 minutes each)

**Use Case**: Testing repeated drone detection, surveillance pattern recognition

**Parameters**:
- `--count N`: Number of appearances (default: 5)
- `--drone-id ID`: Specific drone ID to use (default: auto-generated)

**Example**:
```bash
# 5 appearances of auto-generated drone
python tests/generate_test_data.py --scenario repeated --count 5

# 3 appearances of specific drone
python tests/generate_test_data.py --scenario repeated --count 3 --drone-id SURVEILLANCE-12345
```

#### 3. Coordinated Activity (`--scenario coordinated`)
**Purpose**: Simulate swarm/coordinated drone activity

**Generates**:
- 4-6 drones appearing together within 500m
- All drones appear within 5-minute window
- Similar altitudes (80-120m) and speeds (8-12 m/s)
- Coordinated flight patterns around central point

**Use Case**: Testing swarm detection, coordinated activity alerts

**Parameters**:
- `--count N`: Number of swarms to generate (default: 1)

**Example**:
```bash
# Generate 3 separate swarm events
python tests/generate_test_data.py --scenario coordinated --count 3
```

#### 4. Operator Reuse (`--scenario operator`)
**Purpose**: Simulate operator using multiple drones or clustered pilot locations

**Generates**:
- **Part A**: Same operator_id across 3 different drones at different times
- **Part B**: 3 different operators with pilots within 50m of each other

**Use Case**: Testing operator reuse detection, pilot proximity analysis

**Example**:
```bash
python tests/generate_test_data.py --scenario operator
```

#### 5. Multi-Kit Detections (`--scenario multikit`)
**Purpose**: Simulate triangulation opportunities with multiple kits

**Generates**:
- 3 kits positioned in triangular formation (5km apart)
- 5 drones flying in center area (visible to all kits)
- RSSI values calculated based on distance from each kit
- Simultaneous detections from multiple kits

**Use Case**: Testing multi-kit correlation, triangulation visualization, RSSI-based distance estimation

**Example**:
```bash
python tests/generate_test_data.py --scenario multikit
```

#### 6. Anomalies (`--scenario anomalies`)
**Purpose**: Simulate unusual flight behavior for anomaly detection testing

**Generates Three Types of Anomalies**:

1. **Speed Spike**:
   - Drone accelerates from 5 m/s to 40 m/s in 10 seconds
   - Returns to normal speed after spike

2. **Rapid Altitude Drop**:
   - Drone descends from 100m to 10m in 20 seconds
   - Simulates emergency landing or attack approach

3. **Erratic Heading Changes**:
   - Random heading changes every 5 seconds
   - Simulates GPS jamming or operator confusion

**Use Case**: Testing anomaly detection algorithms, alert thresholds

**Example**:
```bash
python tests/generate_test_data.py --scenario anomalies
```

#### 7. FPV Signals (`--scenario fpv`)
**Purpose**: Simulate 5.8GHz FPV signal detections

**Generates**:
- FPV signals at common frequencies (5740, 5760, 5800, 5820, 5840, 5860 MHz)
- Power levels: -90 to -60 dBm (realistic signal strengths)
- Intermittent detections (30% probability per 10-second interval)
- Both analog and DJI digital signal types
- Data spread over last 6 hours

**Use Case**: Testing FPV signal visualization, frequency analysis

**Example**:
```bash
python tests/generate_test_data.py --scenario fpv
```

#### 8. All Scenarios (`--scenario all`)
**Purpose**: Generate comprehensive test dataset with all pattern types

**Generates**:
- Normal operations (baseline)
- 5 repeated drone appearances
- 3 coordinated swarms
- Operator reuse patterns
- Multi-kit detections
- All three anomaly types
- FPV signal detections

**Use Case**: Initial setup, comprehensive testing, demo environment

**Example**:
```bash
python tests/generate_test_data.py --scenario all
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--scenario {all,normal,repeated,coordinated,operator,multikit,anomalies,fpv}` | Scenario to generate | Required |
| `--count N` | Count parameter for scenarios (appearances, swarms, etc.) | 5 |
| `--drone-id ID` | Specific drone ID for repeated scenario | Auto-generated |
| `--clean` | Clean all test data from database | N/A |
| `--dry-run` | Preview without inserting data | N/A |
| `--db-url URL` | Database URL | `DATABASE_URL` env or localhost |

### Database Connection

The generator uses the `DATABASE_URL` environment variable if set, otherwise defaults to:
```
postgresql://wardragon:test123@localhost:5432/wardragon
```

**Custom database URL**:
```bash
python tests/generate_test_data.py --scenario normal --db-url "postgresql://user:pass@host:port/database"
```

**Or set environment variable**:
```bash
export DATABASE_URL="postgresql://wardragon:mypassword@localhost:5432/wardragon"
python tests/generate_test_data.py --scenario all
```

### Dry Run Mode

Preview what would be generated without actually inserting data:

```bash
python tests/generate_test_data.py --scenario normal --dry-run
```

Output:
```
[DRY RUN] Would insert 3 kits
[DRY RUN] Would insert 1234 drone records
[DRY RUN] Would insert 456 health records

[DRY RUN] No data was actually inserted
```

### Cleaning Test Data

Remove all test data (kits starting with `test-kit-`):

```bash
python tests/generate_test_data.py --clean
```

Output:
```
Cleaned test data:
  Kits: 3
  Drones: 5432
  Signals: 876
  Health: 543
```

### Test Data Details

#### Kit Naming
All test kits are named `test-kit-001`, `test-kit-002`, etc., making them easy to identify and clean.

#### Drone IDs
- Normal drones: `DJI123456`, `AUT234567`, etc.
- Surveillance drones: `SURVEILLANCE-12345`
- Swarm drones: `SWARM-01-01`, `SWARM-01-02`, etc.
- Anomaly drones: `ANOMALY-SPEED-1234`, `ANOMALY-ALT-5678`, etc.

#### Timestamps
- Data is generated with realistic timestamps spread over time windows
- Normal scenario: Last 48 hours
- Repeated scenario: Last 24 hours
- Coordinated scenario: Last 24 hours
- Anomalies scenario: Last 1-3 hours
- FPV signals: Last 6 hours

#### Realistic Patterns
- Flight speeds: 5-15 m/s (normal), up to 40 m/s (anomalies)
- Altitudes: 50-150m (normal), 10-150m (anomalies)
- RSSI values: -90 to -50 dBm (distance-based)
- GPS coordinates: Centered around San Francisco Bay Area (configurable)

### Usage in Testing

#### Unit Tests
Use test data generator to populate database before running integration tests:

```bash
# Generate test data
python tests/generate_test_data.py --scenario all

# Run integration tests
pytest -m integration
```

#### Dashboard Testing
Generate specific scenarios to test dashboard features:

```bash
# Test repeated drone detection
python tests/generate_test_data.py --scenario repeated --count 5

# Open Grafana Pattern Analysis dashboard
# Verify "Repeated Drone IDs" panel shows the generated drone
```

#### API Testing
Test pattern detection APIs with realistic data:

```bash
# Generate swarm data
python tests/generate_test_data.py --scenario coordinated --count 3

# Test API endpoint
curl http://localhost:8090/api/patterns/coordinated?hours=24
```

### Performance Considerations

**Generation Speed**:
- Normal scenario: ~10-30 seconds (generates 1000-3000 drone records)
- All scenarios: ~60-120 seconds (generates 5000-10000 records)

**Database Impact**:
- Uses batch inserts (1000 records per batch) for efficiency
- Includes progress indicators for large datasets
- ON CONFLICT clauses prevent duplicate key errors

**Clean Up**:
Always clean test data before re-generating to avoid conflicts:
```bash
python tests/generate_test_data.py --clean
python tests/generate_test_data.py --scenario all
```

### Troubleshooting

#### psycopg2 Not Installed
```
Error: psycopg2 not installed. Install with: pip install psycopg2-binary
```

**Solution**:
```bash
pip install psycopg2-binary
# or
pip install -r app/requirements.txt
```

#### Database Connection Failed
```
Error: could not connect to server: Connection refused
```

**Solution**:
- Verify TimescaleDB is running: `docker-compose ps timescaledb`
- Check DATABASE_URL or --db-url parameter
- Ensure firewall allows connection to port 5432

#### No Data Showing in Dashboards After Generation
**Check**:
1. Verify data was inserted:
   ```sql
   docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "SELECT COUNT(*) FROM drones WHERE kit_id LIKE 'test-kit-%';"
   ```
2. Check Grafana time range matches generated data timeframe
3. Refresh Grafana dashboards (Ctrl+R or click refresh button)

### Advanced Usage

#### Custom Time Ranges
Edit the script to customize time ranges:

```python
# In scenario_normal():
start_time = end_time - timedelta(hours=48)  # Change to 72 for 3 days
```

#### Custom Locations
Change the base GPS coordinates:

```python
# At top of script:
BASE_LAT = 37.7749  # Change to your area
BASE_LON = -122.4194
```

#### Custom Drone Models
Add your own drone makes/models:

```python
DRONE_MAKES_MODELS = [
    ("DJI", "Mini 3 Pro"),
    ("YourBrand", "YourModel"),
    # ... add more
]
```

### Examples

#### Scenario 1: Demo Environment Setup
```bash
# Clean any existing test data
python tests/generate_test_data.py --clean

# Generate comprehensive dataset
python tests/generate_test_data.py --scenario all

# Verify in Grafana
# Open http://localhost:3000
# Navigate to "Tactical Overview" dashboard
```

#### Scenario 2: Test Surveillance Detection
```bash
# Generate repeated drone with 10 appearances
python tests/generate_test_data.py --scenario repeated --count 10 --drone-id TEST-SURVEILLANCE-001

# Test API
curl "http://localhost:8090/api/patterns/repeated-drones?hours=24"

# Should return TEST-SURVEILLANCE-001 with appearance_count=10
```

#### Scenario 3: Test Swarm Alert System
```bash
# Generate multiple swarms
python tests/generate_test_data.py --scenario coordinated --count 5

# Verify in Grafana Pattern Analysis dashboard
# "Coordinated Activity" panel should show 5 groups
```

---

## Collector Unit Tests

The `test_collector.py` module provides comprehensive unit tests for the collector service (`app/collector.py`).

### Running Collector Tests

```bash
# From the WarDragonAnalytics root directory
cd WarDragonAnalytics

# Run all collector tests
pytest tests/test_collector.py -v

# Run with coverage
pytest tests/test_collector.py --cov=app.collector --cov-report=term-missing

# Run specific test class
pytest tests/test_collector.py::TestKitHealth -v

# Generate HTML coverage report
pytest tests/test_collector.py --cov=app.collector --cov-report=html
```

### Collector Test Coverage

The test suite provides **68 comprehensive tests** covering:

#### KitHealth Class (15 tests)
- Initialization and default values
- Success/failure tracking
- Exponential backoff calculation (with max cap)
- Stale detection (recent/old/no data)
- Poll delay calculation
- Statistics generation

#### DatabaseWriter Class (20 tests)
- Engine initialization and error handling
- Connection testing
- Drone insertion (success, empty, partial failure, aircraft detection)
- Signal insertion (success, empty, FPV frequency detection)
- Health record insertion
- Kit status updates
- Timestamp parsing (datetime, ISO string, invalid)
- Safe type conversions (float, int, edge cases)
- Resource cleanup

#### KitCollector Class (18 tests)
- Initialization
- JSON fetching (success, timeout, HTTP error, retry logic)
- Drone/signal/status polling
- Concurrent endpoint polling
- Disabled kit handling
- Run loop with backoff scenarios

#### CollectorService Class (10 tests)
- Initialization
- Config loading (success, missing file, invalid YAML)
- Field validation (missing id, missing api_url)
- Database connection failure handling
- Collector creation for enabled kits
- Health monitoring
- Graceful shutdown

#### Signal Handlers (2 tests)
- SIGTERM handling
- SIGINT handling

#### Integration Tests (3 tests)
- Full polling cycle (all endpoints)
- Recovery after temporary failure
- Multi-kit concurrent polling

### Collector Coverage Goals

| Component | Target | Achieved |
|-----------|--------|----------|
| KitHealth | 95%+ | PASS 98% |
| DatabaseWriter | 85%+ | PASS 87% |
| KitCollector | 85%+ | PASS 86% |
| CollectorService | 80%+ | PASS 82% |
| **Overall** | **80%+** | **PASS 85%** |

### Key Features

- **No Docker required** - All tests use mocks
- **Fast execution** - Complete suite runs in ~2-3 seconds
- **Comprehensive coverage** - Tests success paths, errors, and edge cases
- **Async test support** - Full pytest-asyncio integration
- **CI/CD ready** - Perfect for automated testing

### Shared Fixtures (conftest.py)

The `conftest.py` provides reusable fixtures for both API and collector tests:

#### Mock Objects
- `mock_db_engine` - SQLAlchemy engine mock
- `mock_database_writer` - DatabaseWriter with mocked engine
- `mock_httpx_client` - Async HTTP client mock
- `mock_asyncpg_pool` - AsyncPG connection pool mock

#### Sample Data
- `sample_kit_config` - Single kit configuration
- `sample_kits_config` - Multiple kit configurations
- `sample_drone_data` - Drone detection records
- `sample_signal_data` - FPV signal records
- `sample_status_data` - System health data
- `temp_kits_config` - Temporary YAML config file

#### Utilities
- `event_loop` - Fresh async event loop per test
- `reset_module_state` - Cleans up global state between tests

