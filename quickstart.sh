#!/bin/bash
# WarDragon Analytics Quick Start Script
# Automated setup and deployment

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "=========================================="
echo "  WarDragon Analytics Quick Start"
echo "=========================================="
echo -e "${NC}"

# Find docker command
DOCKER_CMD=""
if command -v docker &> /dev/null; then
    DOCKER_CMD="docker"
elif [ -x /usr/bin/docker ]; then
    DOCKER_CMD="/usr/bin/docker"
elif [ -x /usr/local/bin/docker ]; then
    DOCKER_CMD="/usr/local/bin/docker"
fi

if [ -z "$DOCKER_CMD" ]; then
    echo -e "${RED}ERROR: Docker not found${NC}"
    echo "Please install Docker first: https://docs.docker.com/engine/install/"
    exit 1
fi

DOCKER_COMPOSE="$DOCKER_CMD compose"

# Check prerequisites
echo "Checking prerequisites..."
echo -e "${GREEN}[OK] Docker found${NC}"
echo -e "${GREEN}[OK] docker compose found${NC}"
echo ""

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env

    # Generate passwords (URL-safe: no +, /, = characters that break DB connection strings)
    echo "Generating secure passwords..."
    DB_PASS=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')
    GRAFANA_PASS=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')
    GRAFANA_SECRET=$(openssl rand -base64 32)

    # Update .env
    sed -i "s|CHANGEME_STRONG_PASSWORD_HERE|$DB_PASS|" .env
    sed -i "s|CHANGEME_GRAFANA_PASSWORD_HERE|$GRAFANA_PASS|" .env
    sed -i "s|CHANGEME_GRAFANA_SECRET_KEY_HERE|$GRAFANA_SECRET|" .env

    echo -e "${GREEN}[OK] .env file created with secure passwords${NC}"
    echo ""
    echo -e "${YELLOW}IMPORTANT: Save these credentials!${NC}"
    echo "Grafana Admin Password: $GRAFANA_PASS"
    echo ""
else
    echo -e "${YELLOW}! .env file already exists, skipping...${NC}"
    echo ""
fi

# Create directories
echo "Creating directories..."
mkdir -p volumes/timescale-data volumes/grafana-data logs/collector config
chmod 700 volumes/timescale-data volumes/grafana-data
echo -e "${GREEN}[OK] Directories created${NC}"
echo ""

# Check if kits.yaml exists
if [ ! -f config/kits.yaml ]; then
    echo -e "${YELLOW}! config/kits.yaml not found${NC}"
    echo "The default kits.yaml will be used (points to localhost:8088)"
    echo "Edit config/kits.yaml to configure your WarDragon kits"
    echo ""
fi

# Pull images
echo "Pulling Docker images (this may take a few minutes)..."
$DOCKER_COMPOSE pull

# Build application containers
echo "Building application containers..."
$DOCKER_COMPOSE build

echo -e "${GREEN}[OK] Docker images ready${NC}"
echo ""

# Bring up TimescaleDB first and apply migrations BEFORE starting the rest of
# the stack. Otherwise mqtt-ingest/collector race the migrations: they start
# subscribing to MQTT immediately, the first message tries to INSERT into a
# table that's missing v2 columns (transport, description, etc.), and inserts
# fail silently until migrations finish. Order: db -> migrate -> everyone else.
echo "Starting TimescaleDB..."
$DOCKER_COMPOSE up -d timescaledb

echo "Waiting for TimescaleDB to become healthy (up to 60 seconds)..."
sleep 5

TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    if $DOCKER_CMD exec wardragon-timescaledb pg_isready -U wardragon &> /dev/null; then
        echo -e "${GREEN}[OK] TimescaleDB is healthy${NC}"
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo -n "."
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo -e "${RED}WARNING: TimescaleDB did not become healthy within timeout${NC}"
    echo "Check logs: $DOCKER_COMPOSE logs timescaledb"
fi

echo ""

# Apply database schema (all scripts use IF NOT EXISTS, safe for new and existing installs).
# Errors here are loud — we need migrations to succeed before mqtt-ingest starts,
# otherwise it races and drops the first batch of messages.
echo "Applying database schema..."

# 01-init.sql uses bare CREATE TABLE — already-exists errors on re-apply against
# an existing DB are expected and harmless (the tables are already there from
# the initial postgres entrypoint init). The later migrations all use
# IF NOT EXISTS / ALTER TABLE IF NOT EXISTS and are strictly idempotent, so we
# fail loudly on any error there to avoid silent schema drift.
apply_migration() {
    local file="$1"
    local label="$2"
    local strict="${3:-strict}"
    if [ ! -f "$file" ]; then
        return 0
    fi
    echo "Applying ${label}..."
    if [ "$strict" = "strict" ]; then
        if ! $DOCKER_CMD exec -i wardragon-timescaledb psql -U wardragon -d wardragon -v ON_ERROR_STOP=1 < "$file" > /dev/null; then
            echo -e "${RED}ERROR: ${label} failed to apply. Aborting before starting the rest of the stack.${NC}"
            echo "Re-run: $DOCKER_CMD exec -i wardragon-timescaledb psql -U wardragon -d wardragon < $file"
            exit 1
        fi
    else
        # Tolerant mode: 01-init.sql on an existing DB will error on CREATE TABLE
        # statements for tables that already exist. That's expected.
        $DOCKER_CMD exec -i wardragon-timescaledb psql -U wardragon -d wardragon < "$file" > /dev/null 2>&1 || true
    fi
}

apply_migration "timescaledb/01-init.sql"               "01-init.sql"                                       tolerant
apply_migration "timescaledb/02-pattern-views.sql"      "02-pattern-views.sql"                              strict
apply_migration "timescaledb/03-extended-fields.sql"    "03-extended-fields.sql"                            strict
apply_migration "timescaledb/04-audit-log.sql"          "04-audit-log.sql (audit log)"                      strict
apply_migration "timescaledb/05-mqtt-support.sql"       "05-mqtt-support.sql (MQTT source column)"          strict
apply_migration "timescaledb/06-transport.sql"          "06-transport.sql (RF transport field)"             strict
apply_migration "timescaledb/07-extended-fields-v2.sql" "07-extended-fields-v2.sql (DragonSync v2 fields)"  strict

echo -e "${GREEN}[OK] Database schema applied${NC}"
echo ""

# Now bring up the rest of the stack — collector, mqtt-ingest, web, grafana,
# mosquitto. mqtt-ingest can safely start ingesting because the schema is ready.
echo "Starting remaining services..."
$DOCKER_COMPOSE up -d

echo -e "${GREEN}[OK] Services started${NC}"
echo ""

# Display status
echo "Checking service status..."
$DOCKER_COMPOSE ps
echo ""

# Display access information
echo -e "${GREEN}"
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="
echo -e "${NC}"
echo ""
echo "Service URLs:"
echo "  Web UI:   http://localhost:8090"
echo "  Grafana:  http://localhost:3000"
echo ""
echo "Grafana Login:"
echo "  Username: admin"
echo "  Password: (check .env file or output above)"
echo ""
echo "Next Steps:"
echo "  1. Add kits via Web UI (http://localhost:8090) or edit config/kits.yaml"
echo "  2. Restart collector: $DOCKER_COMPOSE restart collector"
echo "  3. Access Grafana and configure dashboards"
echo "  4. Review docs/deployment.md for production setup"
echo ""
echo -e "${BLUE}MQTT Ingest (Enabled by Default):${NC}"
echo "  Kits can push data via MQTT for real-time updates."
echo "  MQTT broker is running on port 1883 (no authentication by default)."
echo "  Configure DragonSync on kits: mqtt_host = THIS_SERVER_IP, mqtt_port = 1883"
echo "  See docs/mqtt-ingest.md for security hardening options."
echo ""
echo "  To disable MQTT (use HTTP polling only):"
echo "    $DOCKER_COMPOSE up -d --scale mosquitto=0 --scale mqtt-ingest=0"
echo ""
echo "Useful Commands:"
echo "  Check status:    make status"
echo "  View logs:       make logs"
echo "  Health check:    ./healthcheck.sh"
echo "  Stop:            make stop"
echo "  Backup DB:       make backup"
echo ""
echo -e "${YELLOW}For production deployment, review SECURITY.md${NC}"
echo ""
