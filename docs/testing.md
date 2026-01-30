# Testing Guide for WarDragon Analytics

This document provides comprehensive information about testing WarDragon Analytics, including how to run tests, write new tests, and understand the testing infrastructure.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Markers](#test-markers)
- [Writing Tests](#writing-tests)
- [Coverage Reports](#coverage-reports)
- [Mocking Best Practices](#mocking-best-practices)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

---

## Overview

WarDragon Analytics uses **pytest** as the testing framework with support for:

- **Unit tests**: Fast, isolated tests without external dependencies
- **Integration tests**: Tests that require Docker Compose and database connections
- **Async tests**: Support for testing asynchronous code with `pytest-asyncio`
- **Coverage reporting**: Track code coverage with `pytest-cov`
- **CI/CD integration**: Automated testing on push/PR via GitHub Actions

### Test Philosophy

- **Unit tests should be fast**: No external dependencies, heavy use of mocks
- **Integration tests verify the full stack**: Database, API, collector service
- **Aim for 70%+ code coverage**: Enforced in CI/CD pipeline
- **Test behavior, not implementation**: Focus on what the code does, not how

---

## Test Structure

```
WarDragonAnalytics/
├── tests/                      # All test files
│   ├── __init__.py
│   ├── conftest.py            # Shared fixtures and configuration
│   ├── test_api.py            # API endpoint tests
│   ├── test_collector.py     # Collector service tests
│   ├── test_database.py      # Database integration tests
│   └── test_integration.py   # End-to-end integration tests
├── pytest.ini                 # Pytest configuration
├── .coveragerc                # Coverage configuration
└── .github/
    └── workflows/
        └── tests.yml          # CI/CD test pipeline
```

### Test File Naming Convention

- Test files: `test_*.py` or `*_test.py`
- Test functions: `test_*`
- Test classes: `Test*`

---

## Running Tests

### Prerequisites

Install test dependencies:

```bash
make install-test-deps
# OR
pip install pytest pytest-asyncio pytest-cov pytest-mock pytest-timeout
```

### Quick Reference

| Command | Description |
|---------|-------------|
| `make test` | Run unit tests (fast, no Docker) |
| `make test-unit` | Same as `make test` |
| `make test-integration` | Run integration tests (requires Docker Compose) |
| `make test-all` | Run all tests (unit + integration) |
| `make coverage` | Run tests with HTML coverage report |
| `make test-verbose` | Run tests with verbose output |
| `make test-clean` | Clean test artifacts |

### Running Unit Tests

Unit tests are fast and don't require any external services:

```bash
# Using Make
make test

# Using pytest directly
pytest -m unit

# With verbose output
pytest -m unit -v

# Run specific test file
pytest tests/test_api.py

# Run specific test function
pytest tests/test_api.py::test_health_endpoint
```

### Running Integration Tests

Integration tests require Docker Compose to be running:

```bash
# Start services
make start

# Run integration tests
make test-integration

# OR with pytest directly
export RUN_INTEGRATION_TESTS=1
pytest -m integration

# Stop services when done
make stop
```

### Running All Tests

```bash
# Make sure Docker Compose is running first
make start

# Run all tests
make test-all

# OR
export RUN_INTEGRATION_TESTS=1
pytest
```

### Running Specific Tests

```bash
# Run specific test file
make test-specific TEST=tests/test_api.py

# Run specific test function
make test-specific TEST=tests/test_api.py::test_health_endpoint

# Run tests matching a pattern
pytest -k "test_api"

# Run tests from multiple files
pytest tests/test_api.py tests/test_collector.py
```

---

## Test Markers

Pytest markers help organize and filter tests. Use markers to run specific test categories.

### Available Markers

| Marker | Description | Run With |
|--------|-------------|----------|
| `unit` | Unit tests (no external dependencies) | `pytest -m unit` |
| `integration` | Integration tests (requires Docker) | `pytest -m integration` |
| `slow` | Tests that take >1 second | `pytest -m slow` |
| `api` | FastAPI endpoint tests | `pytest -m api` |
| `collector` | Collector service tests | `pytest -m collector` |
| `database` | Database interaction tests | `pytest -m database` |
| `skip_ci` | Tests to skip in CI/CD | `pytest -m "not skip_ci"` |

### Using Markers

```bash
# Run only unit tests
pytest -m unit

# Run only API tests
pytest -m api

# Run unit tests except slow ones
pytest -m "unit and not slow"

# Run integration tests for database
pytest -m "integration and database"

# List all available markers
make test-markers
# OR
pytest --markers
```

### Marking Tests

Apply markers to test functions with decorators:

```python
import pytest

@pytest.mark.unit
@pytest.mark.api
def test_health_endpoint():
    """Test the /health endpoint."""
    # Test code here

@pytest.mark.integration
@pytest.mark.database
@pytest.mark.slow
def test_database_connection():
    """Test actual database connection."""
    # Test code here
```

---

## Writing Tests

### Test Structure

Follow the **Arrange-Act-Assert** pattern:

```python
import pytest

@pytest.mark.unit
def test_example_function():
    # Arrange: Set up test data and mocks
    input_data = {"key": "value"}

    # Act: Execute the function being tested
    result = my_function(input_data)

    # Assert: Verify the results
    assert result["status"] == "success"
    assert "output" in result
```

### Using Fixtures

Fixtures provide reusable test data and setup. They're defined in `tests/conftest.py`.

```python
import pytest

@pytest.mark.unit
def test_with_fixture(mock_kit_config):
    """Use the mock_kit_config fixture from conftest.py"""
    assert "kits" in mock_kit_config
    assert len(mock_kit_config["kits"]) > 0
```

### Common Fixtures

Available fixtures from `conftest.py`:

- `mock_kit_config`: Sample kit configuration
- `mock_drone_data`: Sample drone detection data
- `mock_fpv_data`: Sample FPV signal data
- `mock_httpx_client`: Mock HTTP client for API calls
- `test_client`: FastAPI test client
- `sample_query_params`: Sample API query parameters

### Testing Async Code

Use `pytest.mark.asyncio` for async tests:

```python
import pytest

@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_function():
    """Test an async function."""
    result = await my_async_function()
    assert result is not None
```

### Testing API Endpoints

Use the FastAPI test client:

```python
import pytest

@pytest.mark.unit
@pytest.mark.api
def test_api_endpoint(test_client):
    """Test an API endpoint."""
    response = test_client.get("/api/drones")
    assert response.status_code == 200
    data = response.json()
    assert "drones" in data
```

### Testing with Database

Integration tests can use the actual database:

```python
import pytest
import os

@pytest.mark.integration
@pytest.mark.database
def test_database_insert():
    """Test inserting data into the database."""
    if not os.getenv("RUN_INTEGRATION_TESTS"):
        pytest.skip("RUN_INTEGRATION_TESTS not set")

    # Test database operations
    # This requires Docker Compose to be running
```

### Adding New Tests

1. **Choose the appropriate test file** or create a new one:
   - API tests → `tests/test_api.py`
   - Collector tests → `tests/test_collector.py`
   - Database tests → `tests/test_database.py`
   - New module → `tests/test_<module_name>.py`

2. **Write your test function**:
   ```python
   import pytest

   @pytest.mark.unit  # Add appropriate markers
   def test_my_new_feature():
       """Test description here."""
       # Test code
       assert True
   ```

3. **Run the test**:
   ```bash
   pytest tests/test_<file>.py::test_my_new_feature -v
   ```

4. **Add to CI/CD**: Tests are automatically discovered by pytest

---

## Coverage Reports

Code coverage measures what percentage of your code is executed by tests.

### Generating Coverage Reports

```bash
# HTML report (most detailed)
make coverage

# View in browser
firefox htmlcov/index.html
# OR
open htmlcov/index.html

# Terminal report only
pytest -m unit --cov=app --cov-report=term

# XML report (for CI/CD)
make coverage-xml

# Check coverage threshold (fail if < 70%)
make test-coverage
```

### Coverage Output

```
---------- coverage: platform linux, python 3.11.0 -----------
Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
app/__init__.py             0      0   100%
app/api.py                156     42    73%   123-145, 234-256
app/collector.py          234     67    71%   345-367, 456-478
-----------------------------------------------------
TOTAL                     390     109   72%

Coverage report: htmlcov/index.html
```

### Coverage Configuration

Coverage is configured in `.coveragerc`:

- **Minimum threshold**: 70% (enforced in CI/CD)
- **Branch coverage**: Enabled (more thorough)
- **Excluded lines**: Debug code, abstract methods, `if __name__ == '__main__'`
- **Omitted files**: Test files, migrations, examples

### Improving Coverage

1. **Identify untested code**:
   ```bash
   pytest --cov=app --cov-report=term-missing
   ```

2. **Focus on critical paths**: Test error handling, edge cases

3. **Use mocks for external dependencies**: Database, HTTP calls, file I/O

4. **Don't aim for 100%**: 70-85% is a practical goal

---

## Mocking Best Practices

Mocking isolates the code under test from external dependencies.

### When to Mock

- **Always mock**: External APIs, databases (in unit tests), file I/O, time/dates
- **Don't mock**: The code you're testing, simple data structures

### Mocking HTTP Requests

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_call(mock_httpx_client):
    """Test HTTP API call with mocked client."""
    # Configure mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}

    mock_httpx_client.get.return_value = mock_response

    # Test code that uses httpx
    # ...
```

### Mocking Database Operations

```python
import pytest
from unittest.mock import MagicMock, patch

@pytest.mark.unit
def test_database_query():
    """Test database query with mocked connection."""
    with patch("app.collector.create_engine") as mock_engine:
        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "test"}]

        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_engine.return_value.connect.return_value.__enter__.return_value = mock_conn

        # Test code that queries database
        # ...
```

### Mocking Async Functions

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_operation():
    """Test async operation with mocked dependency."""
    mock_async_func = AsyncMock(return_value="success")

    # Use the mock in your test
    result = await mock_async_func()
    assert result == "success"
    mock_async_func.assert_called_once()
```

### Mocking Configuration Files

```python
import pytest
from unittest.mock import patch, mock_open

@pytest.mark.unit
def test_load_config():
    """Test loading configuration with mocked file."""
    mock_yaml = """
    kits:
      - id: test-kit
        name: Test Kit
    """

    with patch("builtins.open", mock_open(read_data=mock_yaml)):
        # Test code that loads config
        # ...
```

---

## CI/CD Integration

Tests run automatically on every push and pull request via GitHub Actions.

### Workflow Overview

The CI/CD pipeline (`.github/workflows/tests.yml`) runs:

1. **Unit tests** on Python 3.9, 3.10, 3.11
2. **Integration tests** with Docker Compose
3. **Coverage check** (fails if < 70%)
4. **Code quality checks** (ruff, black, isort, mypy)

### Workflow Triggers

Tests run on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`
- Manual trigger via GitHub Actions UI
- Changes to: `app/`, `tests/`, `requirements.txt`, test config files

### Viewing Results

1. Go to your GitHub repository
2. Click **Actions** tab
3. Click on a workflow run to see results
4. Download coverage artifacts from the run

### CI/CD Environment

- **OS**: Ubuntu Latest
- **Python**: 3.9, 3.10, 3.11
- **Services**: TimescaleDB, Docker Compose
- **Timeout**: 120 seconds for service startup
- **Coverage**: Uploaded as artifacts (30-day retention)

### Local CI Simulation

Run tests like CI does:

```bash
# Run exactly what CI runs for unit tests
pytest -m unit -v --tb=short --cov=app --cov-report=xml --cov-fail-under=70

# Run integration tests (requires Docker)
make start
export RUN_INTEGRATION_TESTS=1
pytest -m integration -v --tb=short
make stop
```

---

## Troubleshooting

### Tests Pass Locally But Fail in CI

**Possible causes**:
- Missing environment variables in CI
- Different Python versions
- Timing issues with Docker services
- File path differences

**Solutions**:
- Check GitHub Actions logs for errors
- Run tests with same Python version as CI
- Increase service startup timeouts
- Use absolute paths in tests

### Integration Tests Fail

**Problem**: `RUN_INTEGRATION_TESTS not set`

**Solution**:
```bash
export RUN_INTEGRATION_TESTS=1
pytest -m integration
```

**Problem**: Database connection refused

**Solution**:
```bash
# Ensure Docker Compose is running
make status

# Check TimescaleDB health
docker exec wardragon-timescaledb pg_isready -U wardragon

# Restart services if needed
make restart
```

### Coverage Below Threshold

**Problem**: Coverage check fails with < 70%

**Solution**:
```bash
# Generate detailed coverage report
make coverage

# Open HTML report to see what's missing
firefox htmlcov/index.html

# Focus on untested code paths
pytest --cov=app --cov-report=term-missing
```

### Async Test Warnings

**Problem**: `RuntimeWarning: coroutine was never awaited`

**Solution**:
```python
# Make sure to mark test as async and await calls
@pytest.mark.asyncio
async def test_async():
    result = await my_async_function()  # Don't forget await!
```

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'app'`

**Solution**:
```bash
# Run pytest from project root (WarDragonAnalytics/)
cd /path/to/WarDragonAnalytics
pytest

# Or add app to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:${PWD}/app"
pytest
```

### Fixture Not Found

**Problem**: `fixture 'mock_kit_config' not found`

**Solution**:
- Fixtures are defined in `tests/conftest.py`
- Make sure conftest.py is in the same directory as tests
- Check fixture name spelling

### Docker Services Not Starting

**Problem**: Integration tests timeout waiting for services

**Solution**:
```bash
# Check Docker daemon is running
docker ps

# Check service logs
make logs

# Restart Docker Compose
make restart

# Clean and rebuild
make clean
make start
```

---

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)

---

## Quick Command Reference

```bash
# Setup
make install-test-deps

# Run tests
make test                    # Unit tests only
make test-integration        # Integration tests (needs Docker)
make test-all               # All tests
make test-verbose           # Verbose output
make test-specific TEST=path # Specific test

# Coverage
make coverage               # HTML report
make coverage-xml           # XML report (CI/CD)
make test-coverage          # With threshold check

# Maintenance
make test-clean             # Clean artifacts
make test-markers           # List markers

# Pytest direct
pytest -m unit              # Unit tests
pytest -m integration       # Integration tests
pytest -v                   # Verbose
pytest --lf                 # Last failed
pytest --ff                 # Failed first
pytest -k "pattern"         # Match pattern
pytest -x                   # Stop on first failure
```

---

**Happy Testing!** If you have questions or issues, please open a GitHub issue or refer to the main [README.md](README.md).
