#!/bin/bash
################################################################################
# test-enterprise.sh - Test enterprise features (auth, alerting, audit)
#
# Description:
#   Tests the new enterprise features to verify they work correctly.
#   Can be run with services running or just to validate Python syntax.
#
# Usage:
#   ./scripts/test-enterprise.sh          # Full test (requires running services)
#   ./scripts/test-enterprise.sh --syntax # Syntax check only (no services needed)
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

echo -e "${BLUE}WarDragon Analytics - Enterprise Features Test${NC}"
echo "================================================="
echo ""

SYNTAX_ONLY=false
if [ "$1" == "--syntax" ]; then
    SYNTAX_ONLY=true
fi

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0

pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# =============================================================================
# Test 1: Python Syntax Validation
# =============================================================================
echo -e "${BLUE}Test 1: Python Syntax Validation${NC}"
echo "-----------------------------------"

for module in auth.py alerting.py audit.py api.py; do
    if [ -f "app/$module" ]; then
        if python3 -c "
import ast
with open('app/$module', 'r') as f:
    ast.parse(f.read())
" 2>/dev/null; then
            pass "$module - valid Python syntax"
        else
            fail "$module - syntax error"
        fi
    else
        fail "$module - file not found"
    fi
done

echo ""

# =============================================================================
# Test 2: SQL Schema Validation
# =============================================================================
echo -e "${BLUE}Test 2: SQL Schema Files${NC}"
echo "--------------------------"

for schema in 01-init.sql 02-pattern-views.sql 03-extended-fields.sql 04-audit-log.sql; do
    if [ -f "timescaledb/$schema" ]; then
        pass "$schema exists"
    else
        fail "$schema not found"
    fi
done

echo ""

# =============================================================================
# Test 3: Configuration Files
# =============================================================================
echo -e "${BLUE}Test 3: Configuration Files${NC}"
echo "-----------------------------"

# Check .env.example has new settings
if grep -q "AUTH_ENABLED" .env.example; then
    pass ".env.example has AUTH_ENABLED"
else
    fail ".env.example missing AUTH_ENABLED"
fi

if grep -q "ALERTING_ENABLED" .env.example; then
    pass ".env.example has ALERTING_ENABLED"
else
    fail ".env.example missing ALERTING_ENABLED"
fi

if grep -q "AUDIT_LOG_LEVEL" .env.example; then
    pass ".env.example has AUDIT_LOG_LEVEL"
else
    fail ".env.example missing AUDIT_LOG_LEVEL"
fi

if grep -q "SLACK_WEBHOOK_URL" .env.example; then
    pass ".env.example has SLACK_WEBHOOK_URL"
else
    fail ".env.example missing SLACK_WEBHOOK_URL"
fi

echo ""

# =============================================================================
# Test 4: Scripts
# =============================================================================
echo -e "${BLUE}Test 4: Script Files${NC}"
echo "----------------------"

if [ -x "scripts/setup-backup-cron.sh" ]; then
    pass "setup-backup-cron.sh is executable"
else
    if [ -f "scripts/setup-backup-cron.sh" ]; then
        warn "setup-backup-cron.sh exists but not executable"
    else
        fail "setup-backup-cron.sh not found"
    fi
fi

# Check quickstart.sh includes 04-audit-log.sql
if grep -q "04-audit-log.sql" quickstart.sh; then
    pass "quickstart.sh applies 04-audit-log.sql"
else
    fail "quickstart.sh does not apply 04-audit-log.sql"
fi

# Check apply-schema.sh includes 04-audit-log.sql
if grep -q "04-audit-log.sql" scripts/apply-schema.sh; then
    pass "apply-schema.sh applies 04-audit-log.sql"
else
    fail "apply-schema.sh does not apply 04-audit-log.sql"
fi

echo ""

if [ "$SYNTAX_ONLY" == "true" ]; then
    echo -e "${BLUE}Syntax-only mode - skipping API tests${NC}"
    echo ""
else
    # =============================================================================
    # Test 5: API Endpoints (requires running services)
    # =============================================================================
    echo -e "${BLUE}Test 5: API Endpoints${NC}"
    echo "-----------------------"

    # Check if web service is running
    if curl -s http://localhost:8090/health > /dev/null 2>&1; then
        pass "Web service is running"

        # Test auth status endpoint
        AUTH_STATUS=$(curl -s http://localhost:8090/api/auth/status)
        if echo "$AUTH_STATUS" | grep -q "auth_enabled"; then
            pass "/api/auth/status returns auth_enabled"
        else
            fail "/api/auth/status response invalid"
        fi

        # Test alerting status endpoint
        ALERT_STATUS=$(curl -s http://localhost:8090/api/alerting/status)
        if echo "$ALERT_STATUS" | grep -q "available"; then
            pass "/api/alerting/status returns available"
        else
            fail "/api/alerting/status response invalid"
        fi

        # Test that drones endpoint still works (backward compatibility)
        DRONES=$(curl -s "http://localhost:8090/api/drones?time_range=1h&limit=1")
        if echo "$DRONES" | grep -q "drones"; then
            pass "/api/drones still works (backward compatible)"
        else
            fail "/api/drones is broken"
        fi

        # Test that kits endpoint still works
        KITS=$(curl -s http://localhost:8090/api/kits)
        if echo "$KITS" | grep -q "kits"; then
            pass "/api/kits still works (backward compatible)"
        else
            fail "/api/kits is broken"
        fi

    else
        warn "Web service not running - skipping API tests"
        echo "  Start services with: docker compose up -d"
        echo "  Then re-run: ./scripts/test-enterprise.sh"
    fi

    echo ""

    # =============================================================================
    # Test 6: Database Schema (requires running services)
    # =============================================================================
    echo -e "${BLUE}Test 6: Database Schema${NC}"
    echo "-------------------------"

    # Find docker command
    DOCKER_CMD=""
    if command -v docker &> /dev/null; then
        DOCKER_CMD="docker"
    elif [ -x /usr/bin/docker ]; then
        DOCKER_CMD="/usr/bin/docker"
    fi

    if [ -n "$DOCKER_CMD" ]; then
        # Check if audit_log table exists
        if $DOCKER_CMD exec wardragon-timescaledb psql -U wardragon -d wardragon -c "\dt audit_log" 2>/dev/null | grep -q "audit_log"; then
            pass "audit_log table exists in database"
        else
            warn "audit_log table not found (run ./scripts/apply-schema.sh to create)"
        fi
    else
        warn "Docker not found - skipping database tests"
    fi

    echo ""
fi

# =============================================================================
# Summary
# =============================================================================
echo -e "${BLUE}=========================================="
echo "  Test Summary"
echo "==========================================${NC}"
echo ""
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Please review the output above.${NC}"
    exit 1
fi
