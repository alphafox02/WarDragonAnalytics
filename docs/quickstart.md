# WarDragon Analytics - Quick Start Guide

Get up and running with WarDragon Analytics in 5 minutes.

---

## Prerequisites

Before you begin, ensure you have:

1. **Docker** (version 20.10 or later)
   ```bash
   docker --version
   ```

2. **Docker Compose** (version 2.0 or later)
   ```bash
   docker-compose --version
   # OR
   docker compose version
   ```

3. **One or more WarDragon kits** running [DragonSync](https://github.com/alphafox02/DragonSync) with API enabled (default port 8088)

4. **Network connectivity** between Analytics host and WarDragon kit(s)

5. **System Requirements:**
   - 2GB RAM minimum (4GB recommended for multi-kit)
   - 50GB disk space (for 30 days of data from 5 kits)
   - Linux, macOS, or Windows with WSL2

### Installing Docker on Ubuntu

If you don't have Docker installed, here's the recommended setup for Ubuntu:

```bash
# Add Docker's official GPG key
sudo apt-get update
sudo apt-get install ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add the repository to Apt sources
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

# Install Docker packages
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to the docker group (avoids needing sudo for docker commands)
sudo usermod -aG docker $USER
```

**Important:** After adding your user to the docker group, log out and back in for the change to take effect.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/WarDragonAnalytics.git
cd WarDragonAnalytics
```

### 2. Configure Environment Variables

Copy the example environment file and edit it:

```bash
cp .env.example .env
nano .env  # or use your preferred editor
```

**Set these required variables:**

```env
# Database password (change this!)
DB_PASSWORD=your_secure_db_password_here

# Grafana admin password (change this!)
GRAFANA_PASSWORD=your_secure_grafana_password_here

# Optional: Custom ports
# WEB_PORT=8090
# GRAFANA_PORT=3000
# DB_PORT=5432
```

**IMPORTANT:** Use strong, unique passwords! These will secure your database and Grafana access.

### 3. Configure WarDragon Kits

Copy the example kits configuration:

```bash
cp config/kits.yaml.example config/kits.yaml
nano config/kits.yaml
```

**Edit to add your kit(s):**

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

**For single-kit local deployment (Analytics on same device as DragonSync):**

```yaml
kits:
  - id: local-kit
    name: "Local WarDragon Kit"
    api_url: "http://127.0.0.1:8088"
    enabled: true
```

### 4. Make Scripts Executable

```bash
chmod +x scripts/*.sh
```

---

## Starting Services

### Start all services in one command:

```bash
./scripts/start.sh
```

This will:
1. Pull the latest Docker images
2. Build the application containers
3. Start all services in detached mode
4. Display access URLs

**Expected output:**
```
WarDragon Analytics - Starting Services
==========================================

Pulling latest Docker images...
Building application images...
Starting containers...

==========================================
WarDragon Analytics is running!
==========================================

Access the services at:
  Web UI:  http://localhost:8090
  Grafana: http://localhost:3000
```

---

## Accessing the Interfaces

### Web UI (http://localhost:8090)

- **Main Map:** Real-time drone tracks from all kits
- **Kit Management:** Add/remove/configure kits
- **Export:** CSV and KML export for analysis

### Grafana (http://localhost:3000)

- **Default Login:**
  - Username: `admin`
  - Password: (from your `.env` file)

- **Pre-built Dashboards:**
  - Operations Overview
  - Kit Health Monitoring
  - Drone Analytics
  - Signal Analysis

---

## Testing with Sample Data

Use the included test data generator to simulate drone detections:

```bash
python3 app/test_data_generator.py
```

This will:
- Generate realistic drone tracks
- Simulate FPV signal detections
- Populate the database with test data
- Allow you to verify the UI and dashboards

**Check the data in:**
- Web UI: http://localhost:8090
- Grafana: http://localhost:3000

---

## Viewing Logs

### Tail logs from all services:

```bash
./scripts/logs.sh
```

### View logs for a specific service:

```bash
./scripts/logs.sh collector      # Collector service only
./scripts/logs.sh timescaledb    # Database only
./scripts/logs.sh web            # Web UI only
./scripts/logs.sh grafana        # Grafana only
```

### Follow logs with custom options:

```bash
./scripts/logs.sh -f --tail=50   # Last 50 lines, follow mode
```

---

## Managing Services

### Stop all services (preserve data):

```bash
./scripts/stop.sh
```

### Restart services:

```bash
./scripts/stop.sh
./scripts/start.sh
```

### Check container status:

```bash
docker-compose ps
```

---

## Database Operations

### Backup database:

```bash
./scripts/backup.sh
```

Backups are saved to `./backups/` with timestamp:
- `wardragon_analytics_20260119_143022.sql.gz`

**Restore a backup:**

```bash
gunzip -c backups/wardragon_analytics_20260119_143022.sql.gz | \
  docker-compose exec -T timescaledb psql -U wardragon -d wardragon
```

### Reset database (delete all data):

```bash
./scripts/reset-db.sh
```

**WARNING:** This permanently deletes all collected data!

---

## Cleanup

### Stop containers but keep data:

```bash
./scripts/stop.sh
```

### Stop containers and remove them (keep data volumes):

```bash
docker-compose down
```

### Complete cleanup (removes all data):

```bash
./scripts/cleanup.sh
```

You'll be prompted to confirm before data deletion.

### Keep containers stopped but preserve volumes:

```bash
./scripts/cleanup.sh --keep-volumes
```

---

## Troubleshooting

### Services won't start

1. **Check Docker is running:**
   ```bash
   docker ps
   ```

2. **Check port conflicts:**
   ```bash
   sudo lsof -i :8090
   sudo lsof -i :3000
   sudo lsof -i :5432
   ```

3. **View error logs:**
   ```bash
   ./scripts/logs.sh
   ```

### Cannot connect to WarDragon kit

1. **Verify kit API is accessible:**
   ```bash
   curl http://192.168.1.100:8088/status
   ```

2. **Check network connectivity:**
   ```bash
   ping 192.168.1.100
   ```

3. **Verify DragonSync API is enabled** on the kit (check DragonSync config)

4. **Check firewall rules** on both Analytics host and kit

### Database connection errors

1. **Check TimescaleDB container is running:**
   ```bash
   docker-compose ps timescaledb
   ```

2. **Verify .env DB_PASSWORD matches:**
   ```bash
   grep DB_PASSWORD .env
   ```

3. **Check database logs:**
   ```bash
   ./scripts/logs.sh timescaledb
   ```

### Out of disk space

1. **Check disk usage:**
   ```bash
   df -h
   docker system df
   ```

2. **Clean up old Docker data:**
   ```bash
   docker system prune -a --volumes
   ```

3. **Reduce data retention** (edit `timescaledb/init.sql` retention policies)

---

## Data Retention

By default, Analytics retains:
- **Raw data:** 30 days (drones, signals)
- **System health:** 90 days
- **Hourly aggregates:** 1 year

To modify retention, edit `timescaledb/init.sql` and reinitialize:

```sql
-- Example: Change to 7 days
SELECT add_retention_policy('drones', INTERVAL '7 days');
```

Then reset the database:
```bash
./scripts/reset-db.sh
```

---

## Production Deployment Tips

### Run on server/cloud instance:

1. **Use strong passwords** in `.env`
2. **Configure firewall** to restrict access:
   ```bash
   sudo ufw allow from 192.168.1.0/24 to any port 8090
   sudo ufw allow from 192.168.1.0/24 to any port 3000
   ```
3. **Enable HTTPS** with reverse proxy (nginx/Caddy)
4. **Set up automated backups:**
   ```bash
   # Add to crontab
   0 2 * * * cd /path/to/WarDragonAnalytics && ./scripts/backup.sh /mnt/backups
   ```

### Multi-kit deployment:

1. Configure all kits in `config/kits.yaml`
2. Ensure Analytics host is reachable from all kits
3. Monitor kit health in Grafana "Kit Health" dashboard
4. Scale resources if needed (edit `docker-compose.yml` resource limits)

---

## Next Steps

1. **Explore Grafana dashboards** - See pre-built analytics and visualizations
2. **Configure alerts** - Set up geofencing and RID watchlist (coming soon)
3. **Export data** - Use CSV/KML export for offline analysis
4. **Customize dashboards** - Create your own Grafana panels
5. **Read the docs:**
   - [Architecture Design](architecture.md)
   - [Development Guide](development.md) (coming soon)
   - [Deployment Guide](deployment.md)

---

## Utility Scripts Reference

| Script | Description | Example |
|--------|-------------|---------|
| `start.sh` | Start all services | `./scripts/start.sh` |
| `stop.sh` | Stop services gracefully | `./scripts/stop.sh` |
| `logs.sh` | Tail service logs | `./scripts/logs.sh collector` |
| `backup.sh` | Backup database | `./scripts/backup.sh /mnt/usb/backups` |
| `reset-db.sh` | Reset database (delete all data) | `./scripts/reset-db.sh` |
| `cleanup.sh` | Complete cleanup | `./scripts/cleanup.sh` |

---

## Getting Help

- **Issues:** [GitHub Issues](https://github.com/yourusername/WarDragonAnalytics/issues)
- **DragonSync:** [alphafox02/DragonSync](https://github.com/alphafox02/DragonSync)
- **Documentation:** [architecture.md](architecture.md)

---

## License

Apache 2.0 (same as DragonSync)

---

**Happy tracking!**
