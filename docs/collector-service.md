# WarDragon Analytics Collector Service

Production-ready data collection service that polls DragonSync APIs from multiple WarDragon kits and stores normalized data in TimescaleDB.

## Features

- **Async Multi-Kit Polling**: Concurrent polling of multiple kits using asyncio
- **Three Endpoint Types**: Fetches `/drones`, `/signals`, and `/status` data
- **Health Tracking**: Monitors kit availability (online/offline/stale)
- **Exponential Backoff**: Automatic retry with backoff for offline kits
- **Connection Pooling**: Efficient HTTP and database connection reuse
- **Graceful Shutdown**: Handles SIGTERM/SIGINT for clean service stops
- **Comprehensive Logging**: Structured logging with health statistics
- **Data Normalization**: Handles various DragonSync API response formats
- **Error Recovery**: Resilient to network failures and database issues

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Collector Service                          │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │           CollectorService                         │    │
│  │  - Loads kits.yaml configuration                   │    │
│  │  - Creates HTTP client pool                        │    │
│  │  - Spawns async tasks for each kit                 │    │
│  │  - Monitors health every 60s                       │    │
│  └────────────┬───────────────────────────────────────┘    │
│               │                                             │
│       ┌───────┴────────┬─────────────┬──────────────┐      │
│       │                │             │              │      │
│  ┌────▼─────┐   ┌─────▼────┐   ┌────▼─────┐   ┌───▼───┐  │
│  │ Kit A    │   │ Kit B    │   │ Kit C    │   │ Kit D │  │
│  │ Collector│   │ Collector│   │ Collector│   │Collect│  │
│  │          │   │          │   │          │   │       │  │
│  │  Poll    │   │  Poll    │   │  Poll    │   │  Poll │  │
│  │  every   │   │  every   │   │  every   │   │  every│  │
│  │  5s      │   │  5s      │   │  5s      │   │  5s   │  │
│  └────┬─────┘   └─────┬────┘   └────┬─────┘   └───┬───┘  │
│       │               │             │              │      │
│       └───────┬───────┴─────────────┴──────────────┘      │
│               │                                             │
│       ┌───────▼────────────────────────────────────┐      │
│       │      DatabaseWriter                        │      │
│       │  - Connection pooling                      │      │
│       │  - Batch inserts                           │      │
│       │  - Error handling                          │      │
│       └───────┬────────────────────────────────────┘      │
└───────────────┼─────────────────────────────────────────────┘
                │
        ┌───────▼────────┐
        │  TimescaleDB   │
        │  (PostgreSQL)  │
        └────────────────┘
```

## Components

### 1. CollectorService
Main orchestrator that:
- Loads kit configuration from `kits.yaml`
- Initializes database connection pool
- Creates HTTP client with connection pooling
- Spawns async task for each enabled kit
- Monitors overall health and logs statistics

### 2. KitCollector
Per-kit polling handler that:
- Fetches `/drones` endpoint (drone/aircraft tracks)
- Fetches `/signals` endpoint (FPV signal detections)
- Fetches `/status` endpoint (system health, GPS)
- Normalizes API responses to database schema
- Handles kit-specific errors and retries

### 3. KitHealth
Health tracker that:
- Tracks online/offline/stale status
- Counts consecutive failures
- Calculates exponential backoff delays
- Maintains success/failure statistics
- Provides health metrics for monitoring

### 4. DatabaseWriter
Database interface that:
- Manages connection pool (10 base, 20 overflow)
- Inserts normalized drone records
- Inserts signal detections
- Inserts system health metrics
- Updates kit status table
- Handles database errors gracefully

## Configuration

### Environment Variables

```bash
# Database connection (required)
DATABASE_URL=postgresql://wardragon:password@localhost:5432/wardragon

# Kit configuration file (required)
KITS_CONFIG=/config/kits.yaml

# Polling intervals
POLL_INTERVAL=5              # Poll /drones and /signals every 5s
STATUS_POLL_INTERVAL=30      # Poll /status every 30s

# HTTP settings
REQUEST_TIMEOUT=10           # HTTP request timeout in seconds
MAX_RETRIES=3                # Max retry attempts per request

# Backoff settings
INITIAL_BACKOFF=5.0          # Initial backoff delay in seconds
MAX_BACKOFF=300.0            # Maximum backoff delay (5 minutes)

# Health monitoring
STALE_THRESHOLD=60           # Mark kit stale after 60s of no data
```

### Kit Configuration (kits.yaml)

```yaml
kits:
  - id: kit-001
    name: "Mobile Unit Alpha"
    api_url: "http://192.168.1.100:8088"
    location: "Field Operations"
    enabled: true

  - id: kit-002
    name: "Fixed Site Bravo"
    api_url: "http://10.0.0.50:8088"
    location: "Headquarters"
    enabled: true
```

## Database Schema

The collector writes to three TimescaleDB hypertables:

### drones (hypertable)
- Primary key: `(time, kit_id, drone_id)`
- Stores: Remote ID tracks, ADS-B aircraft, pilot location, home point
- Fields: lat, lon, alt, speed, heading, mac, rssi, operator_id, etc.

### signals (hypertable)
- Primary key: `(time, kit_id, freq_mhz)`
- Stores: FPV frequency detections (5.8GHz analog, DJI)
- Fields: freq_mhz, power_dbm, bandwidth_mhz, detection_type

### system_health (hypertable)
- Primary key: `(time, kit_id)`
- Stores: Kit GPS, CPU, memory, disk, temps
- Fields: lat, lon, cpu_percent, memory_percent, uptime_hours, temps

### kits (regular table)
- Primary key: `kit_id`
- Stores: Kit metadata and current status
- Fields: name, location, api_url, last_seen, status

## Running the Collector

### With Docker (Recommended)

```bash
# Build image
docker build -t wardragon-analytics:latest .

# Run collector service
docker run -d \
  --name wardragon-collector \
  --env-file .env \
  -v $(pwd)/config:/config:ro \
  wardragon-analytics:latest \
  python collector.py
```

### With Docker Compose

```yaml
services:
  collector:
    build: ./app
    environment:
      DATABASE_URL: postgresql://wardragon:${DB_PASSWORD}@timescaledb:5432/wardragon
      KITS_CONFIG: /config/kits.yaml
      POLL_INTERVAL: 5
    volumes:
      - ./config:/config:ro
    depends_on:
      - timescaledb
    restart: always
```

### Standalone Python

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://wardragon:password@localhost:5432/wardragon"
export KITS_CONFIG="./config/kits.yaml"

# Run collector
python collector.py
```

## Monitoring

### Health Logs

The collector logs health statistics every 60 seconds:

```
2026-01-19 23:00:00 - __main__ - INFO - === Kit Health Status ===
2026-01-19 23:00:00 - __main__ - INFO - Kit kit-001: online | Success rate: 98.5% | Requests: 720 (OK: 709, Failed: 11)
2026-01-19 23:00:00 - __main__ - INFO - Kit kit-002: offline | Success rate: 0.0% | Requests: 120 (OK: 0, Failed: 120)
2026-01-19 23:00:00 - __main__ - INFO -   Last error: Request error fetching /drones: Connection refused
2026-01-19 23:00:00 - __main__ - INFO - ========================================
```

### Kit Status

Each kit transitions through these states:
- **unknown**: Initial state before first poll
- **online**: Successfully polling and receiving data
- **offline**: Failed to connect or fetch data
- **stale**: No data received in last 60 seconds (STALE_THRESHOLD)
- **error**: Unexpected error occurred

### Backoff Behavior

When a kit fails:
1. **Attempt 1**: Retry after 5s (INITIAL_BACKOFF)
2. **Attempt 2**: Retry after 10s (5 * 2^1)
3. **Attempt 3**: Retry after 20s (5 * 2^2)
4. **Attempt 4**: Retry after 40s (5 * 2^3)
5. **Attempt 5**: Retry after 80s (5 * 2^4)
6. **Attempt 6+**: Retry after 300s (MAX_BACKOFF)

This prevents overwhelming offline kits while still attempting recovery.

## Error Handling

### Network Errors
- Timeouts trigger automatic retry with linear backoff
- Connection errors trigger exponential backoff
- HTTP errors (4xx, 5xx) are logged but don't retry immediately

### Database Errors
- Failed inserts are logged and skipped (doesn't block other records)
- Connection pool automatically recovers from transient failures
- Pre-ping validates connections before use

### Data Format Issues
- Missing fields use `None` (NULL in database)
- Invalid types are safely converted or set to `None`
- Malformed JSON responses are logged and skipped

## Performance

### Throughput
- **Typical load**: 100-500 database inserts/second
- **Peak load**: 1000+ inserts/second (10 kits with heavy activity)
- **Latency**: < 10s from drone detection to database storage

### Resource Usage
- **CPU**: 5-20% on 4-core system (10 kits)
- **Memory**: 100-300 MB (includes connection pools)
- **Network**: 1-10 KB/s per kit (depends on data volume)
- **Database connections**: 10 base + 20 overflow

### Optimization Tips
1. Increase `POLL_INTERVAL` for slower updates
2. Reduce `STATUS_POLL_INTERVAL` to 60s+ for less critical health data
3. Use database connection pooling (already implemented)
4. Deploy collector close to kits (same network) to reduce latency

## Troubleshooting

### Collector won't start

```bash
# Check database connectivity
psql $DATABASE_URL -c "SELECT 1"

# Verify kits.yaml exists and is valid
python -c "import yaml; print(yaml.safe_load(open('/config/kits.yaml')))"

# Check logs
docker logs wardragon-collector
```

### Kit showing as offline

```bash
# Test kit API manually
curl http://192.168.1.100:8088/status

# Check network connectivity
ping 192.168.1.100

# Verify DragonSync is running on kit
ssh wardragon@192.168.1.100 "systemctl status dragonsync"
```

### High database latency

```bash
# Check TimescaleDB performance
docker exec -it timescaledb psql -U wardragon -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"

# Review slow queries
docker exec -it timescaledb psql -U wardragon -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"

# Optimize with indexes (if needed)
docker exec -it timescaledb psql -U wardragon -c "CREATE INDEX IF NOT EXISTS idx_drones_kit_time ON drones(kit_id, time DESC);"
```

### Memory issues

```bash
# Check connection pool usage
# (Add to collector.py for debugging)
logger.info(f"DB pool: {db.engine.pool.status()}")

# Reduce pool size if needed
# Set in environment: DB_POOL_SIZE=5 DB_MAX_OVERFLOW=10
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio pytest-cov

# Run tests
pytest tests/test_collector.py -v

# Run with coverage
pytest tests/test_collector.py --cov=collector --cov-report=html
```

### Debugging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python collector.py

# Use Python debugger
import pdb; pdb.set_trace()  # Add to code
python collector.py

# Profile performance
python -m cProfile -o collector.prof collector.py
python -m pstats collector.prof
```

### Code Quality

```bash
# Format code
black collector.py

# Lint code
ruff check collector.py

# Type check
mypy collector.py
```

## Security

### Best Practices
1. **Database credentials**: Use environment variables or secrets management
2. **Network security**: Run collector on trusted network
3. **API authentication**: Add API keys in Phase 4 (future)
4. **Container security**: Run as non-root user (wardragon:1000)
5. **TLS/SSL**: Use HTTPS for remote kit connections

### Secrets Management

```bash
# Use Docker secrets (Swarm)
docker secret create db_password /path/to/db_password.txt

# Use Kubernetes secrets
kubectl create secret generic wardragon-db \
  --from-literal=password='your-password'

# Use .env file (development only)
echo "DATABASE_URL=postgresql://..." > .env
docker run --env-file .env ...
```

## Production Checklist

- [ ] Database schema initialized (`timescaledb/init.sql`)
- [ ] Kit configuration created (`config/kits.yaml`)
- [ ] Environment variables set (`.env` file)
- [ ] Firewall rules allow kit API access
- [ ] Database backups configured
- [ ] Log aggregation configured (optional)
- [ ] Monitoring/alerting configured (optional)
- [ ] Resource limits set (CPU/memory)
- [ ] Health checks enabled
- [ ] Auto-restart enabled (`restart: always`)

## License

Apache 2.0 (same as DragonSync)

## Support

- **Issues**: [GitHub Issues](https://github.com/alphafox02/WarDragonAnalytics/issues)
- **Documentation**: [architecture.md](architecture.md)
- **DragonSync**: [alphafox02/DragonSync](https://github.com/alphafox02/DragonSync)
