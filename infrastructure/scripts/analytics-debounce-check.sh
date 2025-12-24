#!/bin/bash
set -euo pipefail

APP_DIR="/opt/cocktaildb"
ENV_FILE="$APP_DIR/.env"
DEBOUNCE_MINUTES="${ANALYTICS_DEBOUNCE_MINUTES:-15}"
LOCK_KEY=424242

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

: "${DB_HOST:?Missing DB_HOST}"
: "${DB_PORT:?Missing DB_PORT}"
: "${DB_USER:?Missing DB_USER}"
: "${DB_PASSWORD:?Missing DB_PASSWORD}"
: "${DB_NAME:?Missing DB_NAME}"

export PGPASSWORD="$DB_PASSWORD"

lock_acquired=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT pg_try_advisory_lock($LOCK_KEY);")
if [ "$lock_acquired" != "t" ]; then
  exit 0
fi

read -r dirty_at last_run_at <<<"$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT dirty_at, last_run_at FROM analytics_refresh_state WHERE id = 1;")"

if [ -z "$dirty_at" ]; then
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT pg_advisory_unlock($LOCK_KEY);" >/dev/null
  exit 0
fi

ready=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT (dirty_at + INTERVAL '$DEBOUNCE_MINUTES minutes' <= NOW()) AND (last_run_at IS NULL OR last_run_at < dirty_at) FROM analytics_refresh_state WHERE id = 1;")

if [ "$ready" = "t" ]; then
  systemctl start cocktaildb-analytics.service
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "UPDATE analytics_refresh_state SET last_run_at = CURRENT_TIMESTAMP WHERE id = 1;"
fi

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT pg_advisory_unlock($LOCK_KEY);" >/dev/null
