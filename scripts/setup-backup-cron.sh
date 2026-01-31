#!/bin/bash
################################################################################
# setup-backup-cron.sh - Set up automated daily backups via cron
#
# Description:
#   Adds a cron job to run database backups daily at a specified time.
#   Backups are stored in the backups/ directory with 7-day retention.
#
# Usage:
#   ./scripts/setup-backup-cron.sh             # Default: 2 AM daily
#   ./scripts/setup-backup-cron.sh 3           # Set to 3 AM daily
#   ./scripts/setup-backup-cron.sh remove      # Remove the cron job
#
################################################################################

set -e

# Color output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_SCRIPT="$PROJECT_DIR/scripts/backup.sh"

echo -e "${BLUE}WarDragon Analytics - Backup Cron Setup${NC}"
echo "=========================================="
echo ""

# Check if backup script exists
if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo -e "${RED}Error: backup.sh not found at $BACKUP_SCRIPT${NC}"
    exit 1
fi

# Handle removal
if [ "$1" == "remove" ]; then
    echo -e "${YELLOW}Removing backup cron job...${NC}"

    # Remove existing cron entry
    crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" | crontab - 2>/dev/null || true

    echo -e "${GREEN}Backup cron job removed.${NC}"
    exit 0
fi

# Parse hour argument (default: 2 AM)
BACKUP_HOUR="${1:-2}"

# Validate hour
if ! [[ "$BACKUP_HOUR" =~ ^[0-9]+$ ]] || [ "$BACKUP_HOUR" -lt 0 ] || [ "$BACKUP_HOUR" -gt 23 ]; then
    echo -e "${RED}Error: Hour must be between 0 and 23${NC}"
    exit 1
fi

echo "Backup script: $BACKUP_SCRIPT"
echo "Backup time: ${BACKUP_HOUR}:00 daily"
echo ""

# Create cron entry
CRON_ENTRY="0 $BACKUP_HOUR * * * $BACKUP_SCRIPT >> $PROJECT_DIR/logs/backup.log 2>&1"

# Check if cron entry already exists
if crontab -l 2>/dev/null | grep -q "$BACKUP_SCRIPT"; then
    echo -e "${YELLOW}Updating existing backup cron job...${NC}"
    # Remove old entry and add new one
    (crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT"; echo "$CRON_ENTRY") | crontab -
else
    echo -e "${YELLOW}Adding new backup cron job...${NC}"
    # Add new entry
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
fi

# Create logs directory if needed
mkdir -p "$PROJECT_DIR/logs"

# Verify
echo ""
echo -e "${GREEN}Backup cron job configured!${NC}"
echo ""
echo "Current cron entries:"
crontab -l 2>/dev/null | grep "$BACKUP_SCRIPT" || echo "  (none found)"
echo ""
echo "Backups will run daily at ${BACKUP_HOUR}:00"
echo "Backup location: $PROJECT_DIR/backups/"
echo "Log file: $PROJECT_DIR/logs/backup.log"
echo ""
echo "To test the backup manually:"
echo "  $BACKUP_SCRIPT"
echo ""
echo "To remove the cron job:"
echo "  $0 remove"
