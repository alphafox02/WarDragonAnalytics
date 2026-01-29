#!/bin/bash
################################################################################
# reset-db.sh - Drop all tables and reinitialize database
#
# Description:
#   Connects to TimescaleDB, drops all tables, and re-runs init scripts.
#   WARNING: This will permanently delete all collected data!
#
# Usage:
#   ./scripts/reset-db.sh
#
# Prerequisites:
#   - Database container must be running
#   - .env file must be configured
#
################################################################################

set -e  # Exit on error

# Color output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo -e "${BLUE}WarDragon Analytics - Database Reset${NC}"
echo "=========================================="
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
    exit 1
fi

# Source .env to get DB_PASSWORD
export $(grep -v '^#' .env | xargs)

# Check if database container is running
if ! $DOCKER_COMPOSE ps | grep -q "timescaledb.*Up"; then
    echo -e "${RED}Error: TimescaleDB container is not running${NC}"
    echo "Start services first: ./scripts/start.sh"
    exit 1
fi

# Warning prompt
echo -e "${RED}WARNING: This will delete ALL data from the database!${NC}"
echo "  - All drone tracks"
echo "  - All FPV signal detections"
echo "  - All system health logs"
echo "  - All kit configurations"
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
echo ""
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Database reset cancelled."
    exit 0
fi

# Drop all tables
echo -e "${YELLOW}Dropping all tables...${NC}"
$DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon <<EOF
-- Drop hypertables (must be done before regular tables)
DROP TABLE IF EXISTS drones CASCADE;
DROP TABLE IF EXISTS signals CASCADE;
DROP TABLE IF EXISTS system_health CASCADE;

-- Drop regular tables
DROP TABLE IF EXISTS kits CASCADE;

-- Drop any materialized views
DROP MATERIALIZED VIEW IF EXISTS drones_hourly CASCADE;
DROP MATERIALIZED VIEW IF EXISTS signals_hourly CASCADE;

\echo 'All tables dropped.'
EOF

# Reinitialize database
echo -e "${YELLOW}Reinitializing database schema...${NC}"

# Check if init scripts exist
if [ ! -f "timescaledb/01-init.sql" ]; then
    echo -e "${RED}Error: timescaledb/01-init.sql not found${NC}"
    echo "Cannot reinitialize without init script."
    exit 1
fi

# Run init scripts
echo "Applying 01-init.sql..."
$DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon < timescaledb/01-init.sql

if [ -f "timescaledb/02-pattern-views.sql" ]; then
    echo "Applying 02-pattern-views.sql..."
    $DOCKER_COMPOSE exec -T timescaledb psql -U wardragon -d wardragon < timescaledb/02-pattern-views.sql
fi

echo ""
echo -e "${GREEN}Database reset complete!${NC}"
echo ""
echo "The database has been reinitialized with empty tables."
echo "You can now start collecting data again."
echo ""
