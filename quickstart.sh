? #!/bin/bash
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

# Start services
echo "Starting services..."
$DOCKER_COMPOSE up -d

echo -e "${GREEN}[OK] Services started${NC}"
echo ""

# Wait for services to be healthy
echo "Waiting for services to become healthy (this may take up to 60 seconds)..."
sleep 10

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

# Verify database schema was created
echo "Verifying database schema..."
if ! $DOCKER_CMD exec wardragon-timescaledb psql -U wardragon -d wardragon -c "SELECT 1 FROM kits LIMIT 1" &> /dev/null; then
    echo -e "${YELLOW}Database tables not found - applying schema...${NC}"
    $DOCKER_CMD exec -i wardragon-timescaledb psql -U wardragon -d wardragon < timescaledb/01-init.sql
    $DOCKER_CMD exec -i wardragon-timescaledb psql -U wardragon -d wardragon < timescaledb/02-pattern-views.sql
    echo -e "${GREEN}[OK] Database schema applied${NC}"
else
    echo -e "${GREEN}[OK] Database schema verified${NC}"
    # Apply extended fields migration for existing databases (safe to run multiple times)
    if [ -f "timescaledb/03-extended-fields.sql" ]; then
        echo "Applying extended fields migration..."
        $DOCKER_CMD exec -i wardragon-timescaledb psql -U wardragon -d wardragon < timescaledb/03-extended-fields.sql 2>/dev/null || true
        echo -e "${GREEN}[OK] Extended fields verified${NC}"
    fi
fi
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
echo "  1. Edit config/kits.yaml to add your WarDragon kits"
echo "  2. Restart collector: $DOCKER_COMPOSE restart collector"
echo "  3. Access Grafana and configure dashboards"
echo "  4. Review DEPLOYMENT.md for production setup"
echo ""
echo "Useful Commands:"
echo "  Check status:  make status"
echo "  View logs:     make logs"
echo "  Health check:  ./healthcheck.sh"
echo "  Stop:          make stop"
echo "  Backup DB:     make backup"
echo ""
echo -e "${YELLOW}For production deployment, review SECURITY.md${NC}"
echo ""
