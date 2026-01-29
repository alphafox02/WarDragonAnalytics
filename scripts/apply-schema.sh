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

# Apply schema
echo -e "${YELLOW}Applying database schema...${NC}"

echo "Applying 01-init.sql..."
$DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon < timescaledb/01-init.sql

if [ -f "timescaledb/02-pattern-views.sql" ]; then
    echo "Applying 02-pattern-views.sql..."
    $DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon < timescaledb/02-pattern-views.sql
fi

echo ""
echo -e "${GREEN}Schema applied successfully!${NC}"
echo ""

# Verify tables exist
echo "Verifying tables..."
$DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon -c "\dt" | grep -E "(kits|drones|signals)" || true

echo ""
echo "If you see kits, drones, and signals tables above, the schema is ready."
echo "Restart the collector to begin: docker compose restart collector"
