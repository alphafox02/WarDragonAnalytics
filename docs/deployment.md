# WarDragon Analytics - Deployment Guide

Production-ready deployment guide for WarDragon Analytics using Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- Minimum 2GB RAM, 50GB disk space
- Network access to WarDragon kits running DragonSync

## Quick Start

### 1. Initial Setup

```bash
# Clone or navigate to WarDragonAnalytics directory
cd WarDragonAnalytics

# Copy environment template
cp .env.example .env

# Edit .env with your passwords and configuration
nano .env  # or vim, code, etc.
```

### 2. Generate Strong Passwords

```bash
# Generate database password
openssl rand -base64 32

# Generate Grafana password
openssl rand -base64 32

# Generate Grafana secret key
openssl rand -base64 32
```

Update `.env` with these generated values.

### 3. Configure Kits

Edit `config/kits.yaml` to define your WarDragon kits:

```yaml
kits:
  - id: kit-001
    name: "Mobile Unit Alpha"
    api_url: "http://192.168.1.100:8088"
    location: "Field Operations"
    enabled: true
```

### 4. Set Permissions

```bash
# Create and secure volume directories
mkdir -p ./volumes/timescale-data ./volumes/grafana-data
chmod 700 ./volumes/timescale-data ./volumes/grafana-data

# Grafana volume needs specific user (GID 472)
sudo chown -R 472:472 ./volumes/grafana-data
```

### 5. Start Services

```bash
# Pull images and build containers
docker-compose pull
docker-compose build

# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f
```

### 6. Verify Deployment

```bash
# Check TimescaleDB health
docker exec wardragon-timescaledb pg_isready -U wardragon

# Check collector logs
docker-compose logs collector

# Access Web UI
curl http://localhost:8090/health

# Access Grafana
# Open browser to http://localhost:3000
# Login: admin / <your GRAFANA_PASSWORD from .env>
```

## Service Endpoints

| Service | URL | Description |
|---------|-----|-------------|
| Web UI | http://localhost:8090 | FastAPI web interface |
| Grafana | http://localhost:3000 | Grafana dashboards |
| TimescaleDB | localhost:5432 | PostgreSQL (local only) |

## Production Deployment

### Security Hardening

1. **Use Strong Passwords**
   - Minimum 20 characters
   - Mix of alphanumeric and special characters
   - Use password manager

2. **Network Security**
   - TimescaleDB bound to localhost only (already configured)
   - Use reverse proxy (nginx/Traefik) for SSL/TLS
   - Configure firewall (UFW/iptables)

3. **Firewall Configuration**
   ```bash
   # Allow Web UI (if exposed directly)
   sudo ufw allow 8090/tcp

   # Allow Grafana (if exposed directly)
   sudo ufw allow 3000/tcp

   # For reverse proxy (nginx/Traefik)
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   ```

4. **CORS Configuration**
   - Update `CORS_ORIGINS` in `.env` with specific domains
   - Never use `*` in production

5. **File Permissions**
   ```bash
   # Protect sensitive files
   chmod 600 .env
   chmod 700 volumes/
   ```

### Reverse Proxy Setup (nginx)

Example nginx configuration for SSL termination:

```nginx
# /etc/nginx/sites-available/wardragon-analytics

server {
    listen 80;
    server_name analytics.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name analytics.example.com;

    ssl_certificate /etc/letsencrypt/live/analytics.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/analytics.example.com/privkey.pem;

    # Web UI
    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name grafana.example.com;

    ssl_certificate /etc/letsencrypt/live/grafana.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/grafana.example.com/privkey.pem;

    # Grafana
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and reload:
```bash
sudo ln -s /etc/nginx/sites-available/wardragon-analytics /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Maintenance

### Backup Database

```bash
# Backup to SQL file
docker exec wardragon-timescaledb pg_dump -U wardragon wardragon > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup to compressed file
docker exec wardragon-timescaledb pg_dump -U wardragon wardragon | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Restore Database

```bash
# Restore from SQL file
docker exec -i wardragon-timescaledb psql -U wardragon wardragon < backup.sql
```

### Update Services

```bash
# Pull latest images
docker-compose pull

# Rebuild application containers
docker-compose build --no-cache

# Restart services
docker-compose down
docker-compose up -d
```

### Monitor Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f collector
docker-compose logs -f web
docker-compose logs -f grafana

# Last 100 lines
docker-compose logs --tail=100 collector
```

### Database Maintenance

```bash
# Connect to TimescaleDB
docker exec -it wardragon-timescaledb psql -U wardragon wardragon

# Check database size
SELECT pg_size_pretty(pg_database_size('wardragon'));

# Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Vacuum and analyze
VACUUM ANALYZE;
```

## Troubleshooting

### Service Won't Start

```bash
# Check service status
docker-compose ps

# Check logs for errors
docker-compose logs <service-name>

# Restart specific service
docker-compose restart <service-name>
```

### Database Connection Issues

```bash
# Verify TimescaleDB is running
docker-compose ps timescaledb

# Check database logs
docker-compose logs timescaledb

# Test connection from collector
docker exec wardragon-collector python -c "import psycopg2; conn = psycopg2.connect('postgresql://wardragon:PASSWORD@timescaledb:5432/wardragon'); print('Connected!')"
```

### Collector Not Polling

```bash
# Check collector logs
docker-compose logs -f collector

# Verify kits.yaml configuration
cat config/kits.yaml

# Test kit API manually
curl http://<kit-ip>:8088/status
curl http://<kit-ip>:8088/drones
```

### Grafana Connection Issues

```bash
# Check Grafana logs
docker-compose logs grafana

# Verify datasource configuration
docker exec wardragon-grafana cat /etc/grafana/provisioning/datasources/timescaledb.yaml

# Test database connection from Grafana
docker exec wardragon-grafana psql -h timescaledb -U wardragon -d wardragon -c "SELECT version();"
```

### Out of Disk Space

```bash
# Check Docker disk usage
docker system df

# Clean up unused resources
docker system prune -a

# Check volume sizes
du -sh volumes/*

# Check TimescaleDB data compression
docker exec wardragon-timescaledb psql -U wardragon wardragon -c "
SELECT
    hypertable_name,
    pg_size_pretty(before_compression_total_bytes) as before,
    pg_size_pretty(after_compression_total_bytes) as after,
    round(100 - (after_compression_total_bytes::numeric / before_compression_total_bytes::numeric * 100), 2) as compression_ratio
FROM timescaledb_information.hypertable_compression_stats;
"
```

## Performance Tuning

### TimescaleDB Optimization

The docker-compose.yml includes optimized PostgreSQL settings. For larger deployments, consider:

```bash
# Edit docker-compose.yml timescaledb command section
shared_buffers=512MB          # 25% of system RAM
effective_cache_size=2GB      # 50-75% of system RAM
work_mem=16MB                 # Increase for complex queries
maintenance_work_mem=256MB    # Increase for faster VACUUM
```

### Collector Performance

Adjust polling intervals in `.env`:

```bash
# Faster polling (more database load)
POLL_INTERVAL_DRONES=2
POLL_INTERVAL_STATUS=15

# Slower polling (less load, higher latency)
POLL_INTERVAL_DRONES=10
POLL_INTERVAL_STATUS=60
```

### Query Performance

```bash
# Check slow queries
docker exec wardragon-timescaledb psql -U wardragon wardragon -c "
SELECT
    query,
    calls,
    total_time,
    mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"

# Create additional indexes if needed
# Connect to database and analyze query plans
EXPLAIN ANALYZE SELECT ...;
```

## Monitoring

### Health Checks

All services include health checks. Monitor with:

```bash
# Check health status
docker-compose ps

# Watch health status continuously
watch -n 5 docker-compose ps
```

### Resource Usage

```bash
# Monitor container resources
docker stats

# Check specific service
docker stats wardragon-collector wardragon-timescaledb
```

### Alerting

Set up monitoring with Prometheus/Alertmanager (future enhancement):
- Collector polling failures
- Database connection issues
- Disk space warnings
- High query latency

## Scaling

### Vertical Scaling

Increase resources for TimescaleDB:

```yaml
# docker-compose.yml
services:
  timescaledb:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

### Horizontal Scaling

For high-availability deployments:
- Use TimescaleDB clustering (requires Enterprise)
- Load balance multiple collector instances
- Use external PostgreSQL cluster

## Support

For issues, check:
1. Service logs: `docker-compose logs -f`
2. Health checks: `docker-compose ps`
3. Network connectivity: `docker network inspect wardragon-net`
4. Database status: `docker exec wardragon-timescaledb pg_isready`

## License

See project LICENSE file.
