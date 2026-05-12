#!/bin/bash
################################################################################
# apply-schema.sh - Apply database schema to existing database
#
# Description:
#   Applies the init SQL and pattern views to an existing database.
#   Use this if tables are missing but the database exists.
#   This will NOT delete existing data.
#
# Usage:
#   ./scripts/apply-schema.sh
#
################################################################################

set -e

# Color output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo -e "${BLUE}WarDragon Analytics - Apply Database Schema${NC}"
echo "=============================================="
echo ""

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
    echo -e "${RED}Error: docker command not found${NC}"
    exit 1
fi

DOCKER_COMPOSE="$DOCKER_CMD compose"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Run ./quickstart.sh first to generate .env"
    exit 1
fi

# Source .env
export $(grep -v '^#' .env | xargs)

# Check if database container is running
if ! $DOCKER_COMPOSE ps | grep -q "timescaledb.*Up"; then
    echo -e "${RED}Error: TimescaleDB container is not running${NC}"
    echo "Start services first: docker compose up -d"
    exit 1
fi

# Check if init scripts exist
if [ ! -f "timescaledb/01-init.sql" ]; then
    echo -e "${RED}Error: timescaledb/01-init.sql not found${NC}"
    exit 1
fi

# Apply schema. 01-init.sql uses bare CREATE TABLE — already-exists errors when
# re-applied to a populated DB are harmless. Later migrations all use IF NOT
# EXISTS / ALTER TABLE IF NOT EXISTS, so we fail loudly on any error there to
# catch real schema drift rather than letting it slip silently.
echo -e "${YELLOW}Applying database schema...${NC}"

apply_strict() {
    local file="$1"
    local label="$2"
    if [ ! -f "$file" ]; then
        return 0
    fi
    echo "Applying ${label}..."
    if ! $DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon -v ON_ERROR_STOP=1 < "$file"; then
        echo -e "${RED}ERROR: ${label} failed to apply.${NC}"
        exit 1
    fi
}

apply_tolerant() {
    local file="$1"
    local label="$2"
    if [ ! -f "$file" ]; then
        return 0
    fi
    echo "Applying ${label}..."
    $DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon < "$file" > /dev/null 2>&1 || true
}

apply_tolerant "timescaledb/01-init.sql"               "01-init.sql"
apply_strict   "timescaledb/02-pattern-views.sql"      "02-pattern-views.sql"
apply_strict   "timescaledb/03-extended-fields.sql"    "03-extended-fields.sql (extended telemetry fields)"
apply_strict   "timescaledb/04-audit-log.sql"          "04-audit-log.sql (audit logging table)"
apply_strict   "timescaledb/05-mqtt-support.sql"       "05-mqtt-support.sql (MQTT source column)"
apply_strict   "timescaledb/06-transport.sql"          "06-transport.sql (RF transport field)"
apply_strict   "timescaledb/07-extended-fields-v2.sql" "07-extended-fields-v2.sql (DragonSync v2 extended fields)"

echo ""
echo -e "${GREEN}Schema applied successfully!${NC}"
echo ""

# Verify tables exist
echo "Verifying tables..."
$DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon -c "\dt" | grep -E "(kits|drones|signals)" || true

echo ""
echo "If you see kits, drones, and signals tables above, the schema is ready."
echo "Restart the collector to begin: docker compose restart collector"
