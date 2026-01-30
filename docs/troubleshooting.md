# WarDragon Analytics - Troubleshooting Guide

Common issues, solutions, and debugging procedures for WarDragon Analytics.

---

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Installation and Setup Issues](#installation-and-setup-issues)
- [Database Problems](#database-problems)
- [API and Web UI Issues](#api-and-web-ui-issues)
- [Data Collection Problems](#data-collection-problems)
- [Grafana Dashboard Issues](#grafana-dashboard-issues)
- [Performance Issues](#performance-issues)
- [Docker and Container Issues](#docker-and-container-issues)
- [Network and Connectivity](#network-and-connectivity)
- [Pattern Detection Issues](#pattern-detection-issues)
- [Common Error Messages](#common-error-messages)
- [Recovery Procedures](#recovery-procedures)

---

## Quick Diagnostics

Run these commands first when troubleshooting:

### Health Check Script
```bash
./healthcheck.sh
```

This checks:
- Docker service status
- Container health
- Database connectivity
- API endpoint availability
- Disk space
- Resource usage

### Manual Health Checks
```bash
# Check all containers are running
docker ps

# Check container logs
docker logs wardragon-timescaledb --tail 50
docker logs wardragon-collector --tail 50
docker logs wardragon-api --tail 50
docker logs wardragon-grafana --tail 50

# Check database connectivity
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "SELECT 1"

# Check API health
curl http://localhost:8090/health

# Check Grafana
curl http://localhost:3000/api/health
```

### Quick Status Summary
```bash
# Use Makefile shortcuts
make status        # Container status
make health        # Health check
make logs          # View all logs
make db-stats      # Database statistics
```

---

## Installation and Setup Issues

### Issue: docker-compose command not found

**Symptoms:**
```
bash: docker-compose: command not found
```

**Causes:**
- Docker Compose not installed
- Docker Compose V2 syntax required

**Solutions:**

**Option 1:** Install Docker Compose V1
```bash
# Ubuntu/Debian
sudo apt-get install docker-compose

# Verify
docker-compose --version
```

**Option 2:** Use Docker Compose V2 (built into Docker)
```bash
# Replace docker-compose with docker compose (note the space)
docker compose up -d

# Or create alias
echo 'alias docker-compose="docker compose"' >> ~/.bashrc
source ~/.bashrc
```

### Issue: Permission denied accessing Docker

**Symptoms:**
```
Got permission denied while trying to connect to the Docker daemon socket
```

**Cause:** User not in docker group

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker

# Verify
docker ps
```

### Issue: Port already in use

**Symptoms:**
```
Error starting userland proxy: listen tcp 0.0.0.0:8090: bind: address already in use
```

**Cause:** Another service using required ports (3000, 5432, 8090)

**Solution:**

**Option 1:** Stop conflicting service
```bash
# Find what's using the port
sudo lsof -i :8090
sudo lsof -i :3000
sudo lsof -i :5432

# Kill the process (replace PID)
kill <PID>
```

**Option 2:** Change WarDragon Analytics ports
```bash
# Edit .env file
API_PORT=8091          # Change from 8090
GRAFANA_PORT=3001      # Change from 3000
DB_PORT=5433           # Change from 5432

# Restart services
docker-compose down
docker-compose up -d
```

### Issue: File not found errors during setup

**Symptoms:**
```
ERROR: Cannot start service timescaledb: error while creating mount source path ...
```

**Cause:** Required directories or files missing

**Solution:**
```bash
# Run setup script
make setup

# Or manually create required directories
mkdir -p timescaledb/init
mkdir -p grafana/dashboards-json
mkdir -p grafana/datasources
mkdir -p volumes/grafana-data
mkdir -p volumes/timescaledb-data

# Fix permissions
sudo chown -R $USER:$USER volumes/
```

### Issue: Environment variables not set

**Symptoms:**
- Services fail to start
- Database passwords incorrect
- Configuration missing

**Cause:** `.env` file not created or misconfigured

**Solution:**
```bash
# Copy example file
cp .env.example .env

# Generate secure passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32)
GRAFANA_PASSWORD=$(openssl rand -base64 16)

# Edit .env file
nano .env

# Set passwords
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
GRAFANA_PASSWORD=$GRAFANA_PASSWORD

# Verify
cat .env | grep PASSWORD

# Restart services
docker-compose down
docker-compose up -d
```

---

## Database Problems

### Issue: Database won't start

**Symptoms:**
```
wardragon-timescaledb | FATAL: database system is in recovery mode
```

**Causes:**
- Corrupted data
- Improper shutdown
- Insufficient disk space

**Solutions:**

**Check disk space:**
```bash
df -h
# Ensure sufficient space on volume mount
```

**Check logs:**
```bash
docker logs wardragon-timescaledb
```

**Reset database (DESTRUCTIVE - deletes all data):**
```bash
# Stop services
docker-compose down

# Remove database volume
docker volume rm wardragonanalytics_timescaledb-data

# Or manually delete
sudo rm -rf volumes/timescaledb-data/*

# Restart (will reinitialize)
docker-compose up -d timescaledb

# Wait for initialization
docker logs -f wardragon-timescaledb
```

### Issue: Database connection refused

**Symptoms:**
```
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Causes:**
- Database container not running
- Network issue
- Wrong credentials

**Solutions:**

**Check container status:**
```bash
docker ps | grep timescaledb

# If not running, start it
docker start wardragon-timescaledb

# Check logs
docker logs wardragon-timescaledb --tail 100
```

**Verify network:**
```bash
# Check if container is on correct network
docker network inspect wardragon-analytics

# Restart with network recreation
docker-compose down
docker-compose up -d
```

**Test connection:**
```bash
# From host
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "SELECT 1"

# From API container
docker exec wardragon-api python -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('postgresql://wardragon:wardragon@timescaledb:5432/wardragon'))"
```

### Issue: Database views missing (Pattern Detection)

**Symptoms:**
- Pattern APIs return errors
- Grafana dashboards show "relation does not exist"
- Error: `relation "active_threats" does not exist`

**Cause:** Pattern detection views not applied (Phase 2)

**Solution:**
```bash
# Copy SQL file to container
docker cp timescaledb/02-pattern-views.sql wardragon-timescaledb:/tmp/

# Apply views
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -f /tmp/02-pattern-views.sql

# Verify views created
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "\dv"

# Should show: active_threats, multi_kit_detections

# Verify functions created
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "\df"

# Should show: calculate_distance_m, detect_coordinated_activity
```

### Issue: Slow database queries

**Symptoms:**
- API requests timeout
- Grafana dashboards take > 30 seconds to load
- High CPU usage on database container

**Solutions:**

**Check query performance:**
```bash
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  SELECT query, calls, mean_exec_time, max_exec_time
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"
```

**Verify indexes:**
```bash
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "\di"

# Should show indexes on:
# - drones (time, kit_id, drone_id, rid_make, etc.)
# - signals (time, kit_id, freq_mhz, etc.)
```

**Vacuum and analyze:**
```bash
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  VACUUM ANALYZE drones;
  VACUUM ANALYZE signals;
  VACUUM ANALYZE kits;
"
```

**Check database statistics:**
```bash
make db-stats

# Or manually:
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  SELECT
    schemaname,
    tablename,
    n_live_tup as rows,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
  FROM pg_stat_user_tables
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

### Issue: Database disk space full

**Symptoms:**
```
ERROR: could not write to file: No space left on device
```

**Solution:**
```bash
# Check disk usage
df -h
du -sh volumes/timescaledb-data

# Clean old data (adjust retention as needed)
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  DELETE FROM drones WHERE time < NOW() - INTERVAL '30 days';
  DELETE FROM signals WHERE time < NOW() - INTERVAL '30 days';
  VACUUM FULL;
"

# Or use data retention policies (see deployment.md)
```

---

## API and Web UI Issues

### Issue: API returns 503 Service Unavailable

**Symptoms:**
```
{"detail": "Database unavailable"}
```

**Cause:** Database connection pool not initialized or database offline

**Solutions:**

**Check API logs:**
```bash
docker logs wardragon-api --tail 100
```

**Verify database is running:**
```bash
docker ps | grep timescaledb
```

**Restart API:**
```bash
docker restart wardragon-api

# Watch startup logs
docker logs -f wardragon-api
```

### Issue: Web UI shows no data

**Symptoms:**
- Map loads but no drone markers
- Table is empty
- "No data" message

**Causes:**
- No data in database
- API not responding
- Time range too narrow

**Solutions:**

**Check if data exists:**
```bash
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  SELECT COUNT(*) FROM drones WHERE time >= NOW() - INTERVAL '1 hour';
"
```

**Test API directly:**
```bash
curl http://localhost:8090/api/drones?time_range=24h
```

**Check browser console:**
1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for errors (CORS, 404, network failures)
4. Check Network tab for failed requests

**Verify collector is running:**
```bash
docker logs wardragon-collector --tail 50

# Should show polling activity like:
# "Polling kit-alpha..."
# "Inserted X drones from kit-alpha"
```

### Issue: Static files (CSS/JS) not loading

**Symptoms:**
- Web UI has no styling
- Map not rendering
- JavaScript errors in console

**Cause:** Static files not mounted or served correctly

**Solution:**

**Verify static files exist:**
```bash
ls -la app/static/
# Should show: style.css, map.js
```

**Check API logs for mount errors:**
```bash
docker logs wardragon-api | grep -i static
```

**Restart API container:**
```bash
docker restart wardragon-api
```

**Check file permissions:**
```bash
chmod 644 app/static/*.css app/static/*.js
```

### Issue: Pattern API endpoints return 500 errors

**Symptoms:**
```
{"detail": "Database error: ..."}
```

**Cause:** Database views or functions missing

**Solution:**

See [Database views missing](#issue-database-views-missing-pattern-detection) above.

**Verify all pattern endpoints:**
```bash
# Test each endpoint
curl http://localhost:8090/api/patterns/repeated-drones
curl http://localhost:8090/api/patterns/coordinated
curl http://localhost:8090/api/patterns/pilot-reuse
curl http://localhost:8090/api/patterns/anomalies
curl http://localhost:8090/api/patterns/multi-kit
```

---

## Data Collection Problems

### Issue: Collector not polling kits

**Symptoms:**
- No new data in database
- Collector logs show no activity
- Kits appear offline in Grafana

**Causes:**
- Collector container not running
- Kit configuration incorrect
- Network connectivity issues

**Solutions:**

**Check collector status:**
```bash
docker ps | grep collector

# If not running:
docker start wardragon-collector

# Check logs
docker logs wardragon-collector --tail 100
```

**Verify kits.yaml configuration:**
```bash
cat config/kits.yaml

# Should have at least one enabled kit:
# kits:
#   - kit_id: "kit-alpha"
#     name: "Alpha Kit"
#     api_url: "http://192.168.1.100:8088"
#     enabled: true
```

**Test kit connectivity:**
```bash
# From host
curl http://192.168.1.100:8088/api/drones

# From collector container
docker exec wardragon-collector curl http://192.168.1.100:8088/api/drones
```

**Restart collector:**
```bash
docker restart wardragon-collector
docker logs -f wardragon-collector
```

### Issue: Collector logs show "Connection refused"

**Symptoms:**
```
ERROR: Failed to poll kit-alpha: HTTPConnectionPool(...): Max retries exceeded
```

**Causes:**
- DragonSync not running on kit
- Wrong IP address in kits.yaml
- Firewall blocking connection

**Solutions:**

**Verify DragonSync is running:**
```bash
# SSH to the kit
ssh wardragon@192.168.1.100

# Check DragonSync status
systemctl status dragonsync
# or
ps aux | grep dragon_sync
```

**Test connectivity:**
```bash
# Ping kit
ping 192.168.1.100

# Test API port
nc -zv 192.168.1.100 8088

# Test API endpoint
curl http://192.168.1.100:8088/health
```

**Check firewall:**
```bash
# On kit, allow port 8088
sudo ufw allow 8088/tcp
sudo ufw reload
```

### Issue: Data not appearing in specific time range

**Symptoms:**
- Old data exists, but no new data after certain time
- Gaps in timeline

**Causes:**
- Collector stopped/restarted
- Kit went offline
- Clock drift on kit or Analytics server

**Solutions:**

**Check collector uptime:**
```bash
docker ps | grep collector
# Look at "UP" column for restart time
```

**Check system time synchronization:**
```bash
# On Analytics server
timedatectl status

# On kit (via SSH)
ssh wardragon@192.168.1.100 timedatectl status
```

**Manually sync time (if needed):**
```bash
sudo timedatectl set-ntp true
```

### Issue: Duplicate data appearing

**Symptoms:**
- Same drone ID appearing multiple times with identical timestamps
- Database growing faster than expected

**Cause:** Collector polling interval too fast, or multiple collectors running

**Solution:**

**Check collector configuration:**
```bash
# Verify only one collector running
docker ps | grep collector

# Check collector code for poll interval (should be 5+ seconds)
grep -r "POLL_INTERVAL" app/collector.py
```

**Add unique constraints (if needed):**
```bash
# Prevent exact duplicates (time + kit_id + drone_id)
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  CREATE UNIQUE INDEX IF NOT EXISTS idx_drones_unique
  ON drones (time, kit_id, drone_id);
"
```

---

## Grafana Dashboard Issues

### Issue: Dashboards not appearing

**Symptoms:**
- Grafana loads but no dashboards in "WarDragon Analytics" folder
- Empty dashboard list

**Cause:** Dashboard provisioning failed

**Solutions:**

**Check dashboard files exist:**
```bash
ls -la grafana/dashboards-json/
# Should show: tactical-overview.json, pattern-analysis.json, etc.
```

**Check provisioning config:**
```bash
cat grafana/dashboards/dashboard-provider.yaml
```

**Restart Grafana:**
```bash
docker restart wardragon-grafana

# Watch logs for provisioning
docker logs -f wardragon-grafana | grep -i dashboard
```

**Manually import dashboard:**
1. Login to Grafana (http://localhost:3000)
2. Click **+** → **Import**
3. Upload JSON file from `grafana/dashboards-json/`
4. Select TimescaleDB datasource
5. Click Import

### Issue: Dashboard shows "No data"

**Symptoms:**
- Dashboard loads but all panels show "No data"
- Time range selector works but no results

**Causes:**
- No data in selected time range
- Datasource misconfigured
- Query errors

**Solutions:**

**Expand time range:**
1. Click time range selector (top right)
2. Select "Last 24 hours" or "Last 7 days"

**Check datasource connection:**
1. Grafana → Configuration → Data Sources → TimescaleDB
2. Click "Test" button
3. Should show "Database Connection OK"

**If test fails:**
```bash
# Recreate datasource
docker restart wardragon-grafana

# Or check datasource config file
cat grafana/datasources/timescaledb.yaml
```

**Test query manually:**
```bash
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  SELECT COUNT(*) FROM drones WHERE time >= NOW() - INTERVAL '24 hours';
"
```

### Issue: Dashboard query errors

**Symptoms:**
- Red error boxes in panels
- "Backend plugin error" messages

**Common Errors:**

**1. "relation does not exist"**
```
ERROR: relation "active_threats" does not exist
```

**Solution:** Apply pattern views (see [Database views missing](#issue-database-views-missing-pattern-detection))

**2. "column does not exist"**
```
ERROR: column "some_column" does not exist
```

**Solution:** Check database schema matches dashboard queries
```bash
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "\d drones"
```

**3. "syntax error at or near"**
```
ERROR: syntax error at or near "..."
```

**Solution:**
- Edit panel query in Grafana
- Compare with queries in [dashboard-queries.md](dashboard-queries.md)
- Fix SQL syntax

### Issue: Grafana login failed

**Symptoms:**
- "Invalid username or password"
- Can't access Grafana

**Solution:**

**Reset admin password:**
```bash
# Stop Grafana
docker stop wardragon-grafana

# Reset password
docker exec wardragon-grafana grafana-cli admin reset-admin-password newpassword

# Or via environment variable
# Edit .env file:
GRAFANA_PASSWORD=newsecurepassword

# Restart
docker-compose up -d wardragon-grafana
```

---

## Performance Issues

### Issue: High CPU usage

**Symptoms:**
- `docker stats` shows high CPU
- System slowdown
- Queries timeout

**Solutions:**

**Identify culprit:**
```bash
# Check container CPU usage
docker stats --no-stream

# Check database queries
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  SELECT pid, query, state, query_start
  FROM pg_stat_activity
  WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%';
"
```

**Optimize database:**
- Reduce query time ranges
- Add missing indexes (see deployment.md)
- Increase Docker CPU limits (docker-compose.prod.yml)

**Optimize Grafana:**
- Reduce dashboard refresh rate
- Disable auto-refresh on unused dashboards
- Limit panel query complexity

### Issue: High memory usage

**Symptoms:**
- Container OOM (Out of Memory) kills
- System swap usage high

**Solutions:**

**Check memory usage:**
```bash
docker stats --no-stream
free -h
```

**Increase Docker memory limits:**

Edit `docker-compose.prod.yml`:
```yaml
services:
  timescaledb:
    mem_limit: 2g  # Increase from default
    memswap_limit: 2g
```

**Optimize database:**
```bash
# Reduce shared_buffers if needed
# Edit timescaledb/postgresql.conf
shared_buffers = 256MB  # Reduce if memory constrained
```

**Restart services:**
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Issue: Slow API responses

**Symptoms:**
- Web UI takes > 5 seconds to load data
- API timeouts
- Grafana panels timeout

**Solutions:**

**Check database query performance:**
See [Slow database queries](#issue-slow-database-queries)

**Add caching (advanced):**
- Use Redis for API response caching
- Implement ETag headers
- Cache pattern detection results

**Optimize queries:**
- Reduce time_range in requests
- Use kit_id filter to limit data
- Limit result counts

---

## Docker and Container Issues

### Issue: Container keeps restarting

**Symptoms:**
```
docker ps shows "Restarting (1) X seconds ago"
```

**Solution:**

**Check logs:**
```bash
docker logs wardragon-<container-name> --tail 100
```

**Common causes:**
- Configuration error (fix config and restart)
- Missing dependency (rebuild image)
- Database connection failure (check DATABASE_URL)

**Disable restart to debug:**
```bash
# Edit docker-compose.yml, change restart policy
restart: "no"  # Instead of "unless-stopped"

# Restart and check logs
docker-compose up -d
docker logs -f wardragon-<container-name>
```

### Issue: Cannot remove container

**Symptoms:**
```
Error response from daemon: conflict: unable to delete ... container is running
```

**Solution:**
```bash
# Force stop and remove
docker stop wardragon-<container-name>
docker rm -f wardragon-<container-name>

# Or use docker-compose
docker-compose down --remove-orphans
```

### Issue: Image build fails

**Symptoms:**
- Docker build errors
- pip install failures

**Solutions:**

**Clear build cache:**
```bash
docker-compose build --no-cache
```

**Check Dockerfile:**
```bash
# Verify Dockerfile exists in app directory
ls -la app/Dockerfile
```

**Rebuild from scratch:**
```bash
docker-compose down
docker system prune -a --volumes  # WARNING: Removes all unused images/volumes
docker-compose build
docker-compose up -d
```

---

## Network and Connectivity

### Issue: Containers can't communicate

**Symptoms:**
- API can't connect to database
- Collector can't reach API

**Solution:**

**Check Docker network:**
```bash
# List networks
docker network ls

# Inspect WarDragon network
docker network inspect wardragon-analytics

# Recreate network
docker-compose down
docker-compose up -d
```

**Verify container network membership:**
```bash
docker inspect wardragon-api | grep -A 10 Networks
docker inspect wardragon-timescaledb | grep -A 10 Networks
```

### Issue: Can't access web UI from external network

**Symptoms:**
- Works on localhost, fails from other machines
- Connection timeout from remote IPs

**Solutions:**

**Check firewall:**
```bash
# Allow ports through UFW (Ubuntu)
sudo ufw allow 8090/tcp  # API/Web UI
sudo ufw allow 3000/tcp  # Grafana
sudo ufw reload
```

**Check binding:**
```bash
# Verify ports are bound to 0.0.0.0 (not 127.0.0.1)
sudo netstat -tlnp | grep 8090
sudo netstat -tlnp | grep 3000

# Should show: 0.0.0.0:8090, not 127.0.0.1:8090
```

**Update docker-compose.yml if needed:**
```yaml
services:
  web:
    ports:
      - "0.0.0.0:8090:8090"  # Explicitly bind to all interfaces
```

---

## Pattern Detection Issues

### Issue: No repeated drones detected

**Symptoms:**
- `/api/patterns/repeated-drones` returns empty array
- Expected surveillance pattern not detected

**Solutions:**

**Check data exists:**
```bash
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  SELECT drone_id, COUNT(*) as appearances
  FROM drones
  WHERE time >= NOW() - INTERVAL '24 hours'
  GROUP BY drone_id
  HAVING COUNT(*) > 1
  ORDER BY appearances DESC;
"
```

**Adjust parameters:**
```bash
# Try wider time window
curl "http://localhost:8090/api/patterns/repeated-drones?time_window_hours=168"

# Lower minimum appearances
curl "http://localhost:8090/api/patterns/repeated-drones?min_appearances=2"
```

### Issue: No coordinated activity detected

**Symptoms:**
- `/api/patterns/coordinated` returns empty
- Expected swarm not detected

**Solutions:**

**Verify simultaneous detections:**
```bash
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -c "
  SELECT time_bucket('1 minute', time) as bucket, COUNT(DISTINCT drone_id)
  FROM drones
  WHERE time >= NOW() - INTERVAL '1 hour'
  GROUP BY bucket
  HAVING COUNT(DISTINCT drone_id) >= 2
  ORDER BY bucket DESC;
"
```

**Adjust parameters:**
```bash
# Increase distance threshold
curl "http://localhost:8090/api/patterns/coordinated?distance_threshold_m=1000"

# Expand time window
curl "http://localhost:8090/api/patterns/coordinated?time_window_minutes=120"
```

---

## Common Error Messages

### "Database unavailable"
**Cause:** Database connection pool not initialized
**Fix:** Restart API container, verify database is running

### "No space left on device"
**Cause:** Disk full
**Fix:** Clean old data, expand disk, or adjust retention policies

### "Port already in use"
**Cause:** Another service using required port
**Fix:** Change ports in `.env` or stop conflicting service

### "Permission denied"
**Cause:** File/directory permissions incorrect
**Fix:** `chmod`/`chown` files, add user to docker group

### "Cannot allocate memory"
**Cause:** Insufficient RAM
**Fix:** Increase Docker memory limits, reduce service memory usage

### "relation does not exist"
**Cause:** Database schema/views not applied
**Fix:** Apply init scripts and pattern views

---

## Recovery Procedures

### Complete System Reset (DESTRUCTIVE)

**WARNING:** This deletes all data.

```bash
# Stop all services
docker-compose down

# Remove all volumes (DELETES ALL DATA)
docker volume rm wardragonanalytics_timescaledb-data
docker volume rm wardragonanalytics_grafana-data

# Or manually:
sudo rm -rf volumes/timescaledb-data/*
sudo rm -rf volumes/grafana-data/*

# Rebuild and start fresh
docker-compose build
docker-compose up -d

# Wait for initialization
sleep 30

# Apply pattern views
docker cp timescaledb/02-pattern-views.sql wardragon-timescaledb:/tmp/
docker exec wardragon-timescaledb psql -U wardragon -d wardragon -f /tmp/02-pattern-views.sql

# Verify
./healthcheck.sh
```

### Database Backup and Restore

**Backup:**
```bash
# Create backup
make backup

# Or manually:
docker exec wardragon-timescaledb pg_dump -U wardragon wardragon | gzip > backup_$(date +%Y%m%d).sql.gz
```

**Restore:**
```bash
# Stop services
docker-compose down

# Remove old database
docker volume rm wardragonanalytics_timescaledb-data

# Start database
docker-compose up -d timescaledb

# Wait for init
sleep 10

# Restore backup
gunzip < backup_20260120.sql.gz | docker exec -i wardragon-timescaledb psql -U wardragon -d wardragon

# Restart all services
docker-compose up -d
```

### Configuration Reset

**Reset to defaults without losing data:**
```bash
# Stop services
docker-compose down

# Backup current config
cp .env .env.backup
cp config/kits.yaml config/kits.yaml.backup

# Restore defaults
cp .env.example .env
cp config/kits.yaml.example config/kits.yaml

# Edit with your settings
nano .env
nano config/kits.yaml

# Restart
docker-compose up -d
```

---

## Getting Help

### Diagnostic Information to Collect

When seeking support, provide:

1. **System information:**
   ```bash
   uname -a
   docker --version
   docker-compose --version
   ```

2. **Container status:**
   ```bash
   docker ps -a
   ```

3. **Logs:**
   ```bash
   docker logs wardragon-timescaledb --tail 100 > db.log
   docker logs wardragon-api --tail 100 > api.log
   docker logs wardragon-collector --tail 100 > collector.log
   docker logs wardragon-grafana --tail 100 > grafana.log
   ```

4. **Configuration (redact passwords):**
   ```bash
   cat .env | sed 's/PASSWORD=.*/PASSWORD=REDACTED/'
   cat config/kits.yaml
   ```

5. **Health check output:**
   ```bash
   ./healthcheck.sh
   ```

### Resources

- **Documentation:** [README.md](../README.md), [operator-guide.md](operator-guide.md)
- **Deployment:** [deployment.md](deployment.md)
- **API Reference:** [api-reference.md](api-reference.md)
- **Grafana Guide:** [grafana-dashboards.md](grafana-dashboards.md)
- **Architecture:** [architecture.md](architecture.md)

---

**Last Updated:** 2026-01-20
**WarDragon Analytics** - Multi-kit drone surveillance platform
