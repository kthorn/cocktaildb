#!/bin/bash
# Restore an EC2 PostgreSQL database from an S3 backup.

set -euo pipefail

ENVIRONMENT="${1:-}"
BACKUP_URI="${2:-}"

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    echo "Usage: $0 <dev|prod> s3://cocktaildbbackups-<account>-<env>/backup-<timestamp>.sql.gz" >&2
    exit 2
fi
TRUSTED_BACKUP_PATTERN="^s3://cocktaildbbackups-[0-9]+-${ENVIRONMENT}/backup-[A-Za-z0-9._-]+\\.sql\\.gz$"
if [[ ! "$BACKUP_URI" =~ $TRUSTED_BACKUP_PATTERN ]]; then
    echo "Backup must be a .sql.gz file in the $ENVIRONMENT CocktailDB backup bucket." >&2
    exit 2
fi

if [[ "$ENVIRONMENT" == "prod" ]]; then
    HOST="mixology.tools"
    BASE_URL="https://mixology.tools"
else
    HOST="dev.mixology.tools"
    BASE_URL="https://dev.mixology.tools"
fi

SSH_USER="${SSH_USER:-ec2-user}"
SSH_KEY="${SSH_KEY:-}"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [[ -n "$SSH_KEY" ]]; then
    SSH_OPTS+=(-i "$SSH_KEY")
fi

cat <<EOF
WARNING: This replaces the $ENVIRONMENT database with:
  $BACKUP_URI

The selected backup will be downloaded and validated before a safety backup runs.
If restoration fails after database writers stop, they will remain stopped.
EOF
read -r -p "Type 'RESTORE $ENVIRONMENT' to continue: " confirmation
if [[ "$confirmation" != "RESTORE $ENVIRONMENT" ]]; then
    echo "Restore cancelled."
    exit 1
fi

printf -v quoted_backup '%q' "$BACKUP_URI"
printf -v quoted_base_url '%q' "$BASE_URL"

# shellcheck disable=SC2029 # Arguments are escaped with printf %q before client expansion.
ssh "${SSH_OPTS[@]}" "$SSH_USER@$HOST" \
    "sudo bash -s -- $quoted_backup $quoted_base_url" <<'REMOTE'
set -euo pipefail

BACKUP_URI="$1"
BASE_URL="$2"
APP_HOME="${APP_HOME:-/opt/cocktaildb}"
DB_NAME="cocktaildb"
DB_USER="cocktaildb"
LOCK_FILE="${LOCK_FILE:-/run/lock/cocktaildb-restore.lock}"
RESTORE_DIR="${RESTORE_DIR:-/tmp}"
WRITERS_STOPPED=false

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "Another restore is already running." >&2
    exit 1
fi
RESTORE_FILE=$(mktemp "$RESTORE_DIR/cocktaildb-restore.XXXXXX.sql.gz")
TIMERS=(
    cocktaildb-analytics.timer
    cocktaildb-analytics-debounce.timer
    cocktaildb-backup.timer
)
SERVICES=(cocktaildb-analytics-debounce.service cocktaildb-analytics.service)
ACTIVE_TIMERS=()

stop_writers() {
    local failed=0
    cd "$APP_HOME"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml stop api >/dev/null 2>&1 || failed=1
    systemctl stop "${TIMERS[@]}" "${SERVICES[@]}" >/dev/null 2>&1 || failed=1
    return "$failed"
}

writers_are_stopped() {
    local running_services status unit
    if ! running_services=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml \
        ps --status running --services api); then
        return 2
    fi
    if [[ -n "$running_services" ]]; then
        return 1
    fi
    for unit in "${TIMERS[@]}" "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$unit"; then
            return 1
        else
            status=$?
            if [[ $status -ne 3 ]]; then
                return 2
            fi
        fi
    done
    return 0
}

cleanup() {
    status=$?
    trap - EXIT
    rm -f "$RESTORE_FILE"
    if [[ $status -ne 0 && "$WRITERS_STOPPED" == true ]]; then
        stop_writers || true
        if writers_are_stopped; then
            echo "Restore failed; the API and analytics remain stopped. Recover using the reported safety backup before restarting services." >&2
        else
            echo "CRITICAL: could not verify that all database writers stopped. Isolate the host and stop the API and analytics services manually." >&2
        fi
    fi
    exit "$status"
}
trap cleanup EXIT

echo "Downloading and validating $BACKUP_URI..."
aws s3 cp "$BACKUP_URI" "$RESTORE_FILE"
gzip -t "$RESTORE_FILE"
DUMP_HEADER=$(gzip -dc "$RESTORE_FILE" | sed -n '1,20p')
if [[ "$DUMP_HEADER" != *"-- PostgreSQL database dump"* ]]; then
    echo "Backup is not a PostgreSQL plain-text dump." >&2
    exit 1
fi

echo "Creating safety backup..."
systemctl start cocktaildb-backup.service
SAFETY_BACKUP=$(find "$APP_HOME/backups" -maxdepth 1 -name 'backup-*.sql.gz' -printf '%T@ %p\n' | sort -nr | sed -n '1s/^[^ ]* //p')
echo "Safety backup: ${SAFETY_BACKUP:-see journalctl -u cocktaildb-backup.service}"

for timer in "${TIMERS[@]}"; do
    if systemctl is-active --quiet "$timer"; then
        ACTIVE_TIMERS+=("$timer")
    else
        status=$?
        if [[ $status -ne 3 ]]; then
            echo "Could not determine whether $timer is active." >&2
            exit 1
        fi
    fi
done
WRITERS_STOPPED=true
stop_writers
writers_are_stopped

runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();"
runuser -u postgres -- dropdb --if-exists "$DB_NAME"
runuser -u postgres -- createdb --owner="$DB_USER" --template=template0 "$DB_NAME"
gzip -dc "$RESTORE_FILE" | runuser -u postgres -- psql -v ON_ERROR_STOP=1 "$DB_NAME"

echo "Starting and verifying the API..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api
READY=false
for attempt in {1..12}; do
    if curl --max-time 30 --fail --silent --show-error "$BASE_URL/health" >/dev/null &&
       curl --max-time 30 --fail --silent --show-error "$BASE_URL/api/v1/stats" >/dev/null; then
        READY=true
        break
    fi
    if [[ $attempt -lt 12 ]]; then
        sleep 5
    fi
done
if [[ "$READY" != true ]]; then
    echo "API did not become ready after restore." >&2
    exit 1
fi
if [[ ${#ACTIVE_TIMERS[@]} -gt 0 ]]; then
    systemctl start "${ACTIVE_TIMERS[@]}"
fi
WRITERS_STOPPED=false
REMOTE

echo "Restore completed and the API is healthy."
