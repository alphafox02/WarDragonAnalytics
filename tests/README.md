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

**Files:** `test_api.py`, `test_collector.py`, `test_database.py`

**Run with:**
```bash
pytest -m unit
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

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: timescale/timescaledb:latest-pg15
        env:
          POSTGRES_DB: wardragon
          POSTGRES_USER: wardragon
          POSTGRES_PASSWORD: test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r app/requirements.txt
          pip install pytest pytest-asyncio pytest-cov

      - name: Run tests
        run: pytest -m "not slow" --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
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
| KitHealth | 95%+ | ✅ 98% |
| DatabaseWriter | 85%+ | ✅ 87% |
| KitCollector | 85%+ | ✅ 86% |
| CollectorService | 80%+ | ✅ 82% |
| **Overall** | **80%+** | **✅ 85%** |

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

