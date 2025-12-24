#!/bin/bash
set -euo pipefail

ENVIRONMENT="dev"
APP_DIR="/opt/cocktaildb"
MIGRATIONS_DIR="migrations"
DRY_RUN=false

show_help() {
  cat << EOT
Usage: $0 [dev|prod] [--dry-run]

Runs pending SQL migrations using psql and records them in schema_migrations.
EOT
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  show_help
  exit 0
fi

if [ "${1:-}" = "dev" ] || [ "${1:-}" = "prod" ]; then
  ENVIRONMENT="$1"
  shift
fi

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
fi

ENV_FILE="$APP_DIR/.env"
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

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
SQL

mapfile -t files < <(ls -1 "$MIGRATIONS_DIR"/*.sql 2>/dev/null | sort)

if [ "${#files[@]}" -eq 0 ]; then
  echo "No migrations found in $MIGRATIONS_DIR"
  exit 0
fi

for file in "${files[@]}"; do
  filename=$(basename "$file")
  applied=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT 1 FROM schema_migrations WHERE filename = '$filename';")
  if [ "$applied" = "1" ]; then
    continue
  fi

  if [ "$DRY_RUN" = true ]; then
    echo "Would apply: $filename"
    continue
  fi

  echo "Applying: $filename"
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$file"
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "INSERT INTO schema_migrations (filename) VALUES ('$filename');"
  echo "Applied: $filename"
done
