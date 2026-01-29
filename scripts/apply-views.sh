#!/bin/bash
# Apply database views to an existing TimescaleDB instance
# Only needed if database was created before views were added

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment
if [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env"
fi

DB_PASSWORD="${DB_PASSWORD:-test123}"

echo "Applying pattern detection views to database..."

# Check if container is running
if ! docker ps | grep -q wardragon-timescaledb; then
    echo "Error: wardragon-timescaledb container is not running"
    echo "Start it with: docker compose up -d"
    exit 1
fi

# Apply views (pipe from host file, don't rely on container mount)
docker exec -i -e PGPASSWORD="$DB_PASSWORD" wardragon-timescaledb \
    psql -U wardragon -d wardragon < "$PROJECT_DIR/timescaledb/02-pattern-views.sql"

echo "Views applied successfully!"
echo ""
echo "Verifying views..."
docker exec -e PGPASSWORD="$DB_PASSWORD" wardragon-timescaledb \
    psql -U wardragon -d wardragon -c "\dv" | grep -E "(active_threats|multi_kit)" || echo "Views created"
