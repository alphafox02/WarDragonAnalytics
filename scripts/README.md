# WarDragon Analytics - Utility Scripts

This directory contains utility scripts for managing WarDragon Analytics.

## Available Scripts

### start.sh
**Start all services**

Starts all Docker containers in detached mode with pre-flight checks.

```bash
./scripts/start.sh
```

- Checks for required configuration files
- Pulls latest Docker images
- Builds application containers
- Starts all services
- Displays access URLs

---

### stop.sh
**Stop services gracefully**

Stops all containers gracefully while preserving data volumes.

```bash
./scripts/stop.sh
```

- Gracefully stops all containers
- Preserves all data volumes
- Does NOT remove containers or data

---

### logs.sh
**View service logs**

Tail logs from all services or specific services.

```bash
# All services
./scripts/logs.sh

# Specific service
./scripts/logs.sh collector
./scripts/logs.sh timescaledb
./scripts/logs.sh web
./scripts/logs.sh grafana

# Custom options
./scripts/logs.sh -f --tail=50
```

---

### backup.sh
**Backup database**

Creates a timestamped, compressed backup of the TimescaleDB database.

```bash
# Backup to default location (./backups/)
./scripts/backup.sh

# Backup to custom location
./scripts/backup.sh /mnt/usb/backups
```

**Output:**
- `wardragon_analytics_YYYYMMDD_HHMMSS.sql.gz`
- Automatically removes backups older than 7 days

**Restore:**
```bash
gunzip -c backups/wardragon_analytics_20260119_143022.sql.gz | \
  docker-compose exec -T timescaledb psql -U wardragon -d wardragon
```

---

### reset-db.sh
**Reset database**

Drops all tables and reinitializes the database schema.

```bash
./scripts/reset-db.sh
```

**WARNING:** This permanently deletes all data!
- Drops all hypertables (drones, signals, system_health)
- Drops all regular tables (kits)
- Drops materialized views
- Re-runs init.sql to create fresh schema

---

### cleanup.sh
**Complete cleanup**

Stops containers and optionally removes all data.

```bash
# Remove everything including data
./scripts/cleanup.sh

# Stop containers but keep data volumes
./scripts/cleanup.sh --keep-volumes
```

**Full cleanup removes:**
- All containers
- All volumes (database and Grafana data)
- Orphaned containers
- Dangling images

---

## Script Requirements

All scripts require:
- Docker and Docker Compose installed
- Run from the WarDragonAnalytics project directory
- Proper permissions (make executable with `chmod +x scripts/*.sh`)

Scripts that interact with the database also require:
- `.env` file configured with `DB_PASSWORD`
- TimescaleDB container running (except cleanup.sh)

---

## Making Scripts Executable

If the scripts are not executable, run:

```bash
chmod +x scripts/*.sh
```

---

## Common Workflows

### First-time setup:
```bash
./scripts/start.sh
```

### Daily operations:
```bash
./scripts/logs.sh                 # Check logs
./scripts/backup.sh               # Backup data
```

### Troubleshooting:
```bash
./scripts/logs.sh collector       # Check collector logs
./scripts/stop.sh                 # Stop services
./scripts/start.sh                # Restart services
```

### Maintenance:
```bash
./scripts/backup.sh               # Backup before maintenance
./scripts/reset-db.sh             # Reset if needed
./scripts/cleanup.sh              # Full cleanup
```

---

## Error Handling

All scripts:
- Exit on error (`set -e`)
- Check for required tools (docker, docker-compose)
- Provide colored output for better visibility
- Include confirmation prompts for destructive operations

---

### setup-backup-cron.sh
**Configure automated backups**

Sets up a cron job for daily automatic backups.

```bash
# Set up daily backups at 2 AM (default)
./scripts/setup-backup-cron.sh

# Set up daily backups at 3 AM
./scripts/setup-backup-cron.sh 3

# Remove the backup cron job
./scripts/setup-backup-cron.sh remove
```

---

## Automation

### Automated Backups (Easy Way)

Use the setup script:

```bash
./scripts/setup-backup-cron.sh    # Sets up daily 2 AM backups
```

### Automated Backups (Manual)

Add to crontab for daily backups at 2 AM:

```bash
crontab -e
```

Add line:
```
0 2 * * * cd /path/to/WarDragonAnalytics && ./scripts/backup.sh /mnt/backups
```

### Health Monitoring

Check if services are running:

```bash
docker-compose ps | grep -q "Up" || ./scripts/start.sh
```

---

## Customization

Feel free to modify scripts for your deployment:
- Change backup retention (default: 7 days)
- Adjust log tail limits (default: 100 lines)
- Add custom health checks
- Integrate with monitoring systems

---

For more information, see [QUICKSTART.md](../QUICKSTART.md)
