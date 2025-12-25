#!/bin/bash
set -euo pipefail

TARGET_ENV="dev"
APP_DIR="/opt/cocktaildb"
HOST=""
SSH_KEY="${SSH_KEY:-}"
MIGRATION_FILE="${COCKTAILDB_MIGRATION_FILE:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

show_help() {
  cat << EOT
Usage: $0 [dev|prod]

Runs /opt/cocktaildb/scripts/run-migrations.sh over SSH.
Note: run the Ansible deploy first so /opt/cocktaildb ownership and scripts are set.
Optional env:
  SSH_KEY=/path/to/key.pem
  COCKTAILDB_MIGRATION_FILE=/absolute/or/relative/path/to/migration.sql
EOT
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  show_help
  exit 0
fi

if [ "${1:-}" = "dev" ] || [ "${1:-}" = "prod" ]; then
  TARGET_ENV="$1"
fi

if [ "$TARGET_ENV" = "prod" ]; then
  HOST="ec2-user@mixology.tools"
else
  HOST="ec2-user@dev.mixology.tools"
fi

SSH_OPTS=()
if [ -n "$SSH_KEY" ]; then
  SSH_OPTS+=("-i" "$SSH_KEY")
fi

if [ -z "$MIGRATION_FILE" ]; then
  MIGRATION_FILE=$(ls -1 "$REPO_ROOT"/migrations/*.sql 2>/dev/null | sort | tail -n 1)
fi

if [ -n "$MIGRATION_FILE" ] && [ -f "$MIGRATION_FILE" ]; then
  remote_tmp="/tmp/$(basename "$MIGRATION_FILE")"
  scp "${SSH_OPTS[@]}" "$MIGRATION_FILE" "$HOST:$remote_tmp"
  ssh "${SSH_OPTS[@]}" "$HOST" "sudo -u cocktaildb mkdir -p $APP_DIR/migrations && sudo mv $remote_tmp $APP_DIR/migrations/"
else
  echo "No migration file found to upload. Set COCKTAILDB_MIGRATION_FILE or ensure $REPO_ROOT/migrations exists."
  exit 1
fi

ssh "${SSH_OPTS[@]}" "$HOST" "cd $APP_DIR && sudo -u cocktaildb ./scripts/run-migrations.sh"
