#!/bin/bash
# infrastructure/scripts/backup-postgres.sh
# Backup PostgreSQL database to S3
#
# Usage:
#   ./backup-postgres.sh               # Normal backup
#   ./backup-postgres.sh --local-only  # Skip S3 upload
#   ./backup-postgres.sh --dry-run     # Show what would be done

set -euo pipefail

# Configuration from environment or defaults
DB_NAME="${DB_NAME:-cocktaildb}"
DB_USER="${DB_USER:-cocktaildb}"
DB_HOST="${DB_HOST:-localhost}"
DB_PASSWORD="${DB_PASSWORD:-}"
BACKUP_BUCKET="${BACKUP_BUCKET:-}"
BACKUP_DIR="${BACKUP_DIR:-/opt/cocktaildb/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# Export password for pg_dump (PostgreSQL uses PGPASSWORD env var)
export PGPASSWORD="$DB_PASSWORD"

# Parse arguments
DRY_RUN=false
LOCAL_ONLY=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --local-only)
            LOCAL_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date -u +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="backup-${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

echo "=== PostgreSQL Backup ==="
echo "Database: $DB_NAME"
echo "Host: $DB_HOST"
echo "Backup file: $BACKUP_PATH"
echo "S3 Bucket: ${BACKUP_BUCKET:-<not configured>}"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would create backup: $BACKUP_PATH"
    echo "[DRY RUN] Would upload to: s3://${BACKUP_BUCKET}/${BACKUP_FILE}"
    exit 0
fi

# Create backup using pg_dump
echo "Creating backup..."
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_PATH"

# Get backup size
BACKUP_SIZE=$(du -h "$BACKUP_PATH" | cut -f1)
echo "Backup created: $BACKUP_PATH ($BACKUP_SIZE)"

# Upload to S3 if bucket is configured and not local-only
if [ -n "$BACKUP_BUCKET" ] && [ "$LOCAL_ONLY" = false ]; then
    echo "Uploading to s3://${BACKUP_BUCKET}/${BACKUP_FILE}..."
    aws s3 cp "$BACKUP_PATH" "s3://${BACKUP_BUCKET}/${BACKUP_FILE}"
    echo "Upload complete"
else
    if [ -z "$BACKUP_BUCKET" ]; then
        echo "Note: BACKUP_BUCKET not set, skipping S3 upload"
    else
        echo "Note: --local-only specified, skipping S3 upload"
    fi
fi

# Clean up old local backups
echo ""
echo "Cleaning up local backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "backup-*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete -print 2>/dev/null | \
    while read -r deleted; do echo "  Deleted: $deleted"; done || true

# Clean up old S3 backups (if bucket is configured)
if [ -n "$BACKUP_BUCKET" ] && [ "$LOCAL_ONLY" = false ]; then
    echo "Cleaning up S3 backups older than ${RETENTION_DAYS} days..."
    CUTOFF_DATE=$(date -u -d "${RETENTION_DAYS} days ago" +"%Y-%m-%d" 2>/dev/null || \
                  date -u -v-${RETENTION_DAYS}d +"%Y-%m-%d")

    aws s3 ls "s3://${BACKUP_BUCKET}/" 2>/dev/null | while read -r line; do
        FILE_DATE=$(echo "$line" | awk '{print $1}')
        FILE_NAME=$(echo "$line" | awk '{print $4}')
        if [[ "$FILE_NAME" == backup-*.sql.gz ]] && [[ "$FILE_DATE" < "$CUTOFF_DATE" ]]; then
            echo "  Deleting old backup: $FILE_NAME"
            aws s3 rm "s3://${BACKUP_BUCKET}/${FILE_NAME}"
        fi
    done || true
fi

echo ""
echo "=== Backup Complete ==="
echo "Local: $BACKUP_PATH"
if [ -n "$BACKUP_BUCKET" ] && [ "$LOCAL_ONLY" = false ]; then
    echo "S3: s3://${BACKUP_BUCKET}/${BACKUP_FILE}"
fi
