#!/bin/bash
# Ordered EC2 deployment cutover. The normal Ansible deploy stages a complete
# release, then calls this script while the currently served release is intact.

set -uo pipefail

APP_HOME="${APP_HOME:-/opt/cocktaildb}"
RELEASE_ID="${RELEASE_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RELEASE_ROOT="${RELEASE_ROOT:-${APP_HOME}/releases/${RELEASE_ID}}"
SERVED_WEB="${SERVED_WEB:-${APP_HOME}/web}"
APP_ENV="${APP_ENV:-prod}"
DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-/var/lock/cocktaildb-deploy.lock}"
CUTOVER_OPS_DIR="${CUTOVER_OPS_DIR:-}"
MIGRATION_15="15_migration_add_user_groups.sql"
DOCKER_BIN="${DOCKER_BIN:-docker}"
CURL_BIN="${CURL_BIN:-curl}"
PSQL_BIN="${PSQL_BIN:-psql}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
HEALTH_ATTEMPTS="${HEALTH_ATTEMPTS:-15}"
HEALTH_DELAY_SECONDS="${HEALTH_DELAY_SECONDS:-2}"
HEALTH_CONNECT_TIMEOUT_SECONDS="${HEALTH_CONNECT_TIMEOUT_SECONDS:-2}"
HEALTH_MAX_TIME_SECONDS="${HEALTH_MAX_TIME_SECONDS:-5}"
STOP_TIMEOUT_SECONDS="${STOP_TIMEOUT_SECONDS:-60}"
NEW_IMAGE="cocktaildb-api:release-${RELEASE_ID}"
ROLLBACK_IMAGE="cocktaildb-api:rollback-${RELEASE_ID}"
PARITY_MARKER="${PARITY_MARKER:-${APP_HOME}/releases/.migration15-parity-required}"
NEW_API_STARTED=false
NEW_API_MAY_HAVE_WRITTEN=false
WRITERS_STOPPED=false

say() {
    printf '%s\n' "$*"
}

compose_current() {
    "$DOCKER_BIN" compose \
        --project-name cocktaildb \
        --project-directory "$APP_HOME" \
        -f "$APP_HOME/docker-compose.yml" \
        -f "$APP_HOME/docker-compose.prod.yml" \
        "$@"
}

load_database_environment() {
    local variable

    if [[ -f "$APP_HOME/.env" ]]; then
        set -a
        # shellcheck disable=SC1091
        . "$APP_HOME/.env" || return
        set +a
    fi
    for variable in DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME; do
        if [[ -z "${!variable:-}" ]]; then
            say "Missing $variable in ${APP_HOME}/.env"
            return 1
        fi
    done
    export PGPASSWORD="$DB_PASSWORD"
}

psql_scalar() {
    load_database_environment || return
    "$PSQL_BIN" \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -v ON_ERROR_STOP=1 \
        -tAc "$1"
}

op_pending() {
    (
        cd "$RELEASE_ROOT" || exit
        "$APP_HOME/scripts/run-migrations.sh" "$APP_ENV" --dry-run
    )
}

op_backup() {
    local backup_file

    load_database_environment || return
    BACKUP_DIR="$APP_HOME/backups" "$APP_HOME/scripts/backup-postgres.sh" --local-only || return
    backup_file=$(find "$APP_HOME/backups" -maxdepth 1 -type f -name 'backup-*.sql.gz' -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-) || return
    if [[ -z "$backup_file" || ! -s "$backup_file" ]]; then
        say "No nonempty pre-cutover backup was created."
        return 1
    fi
    gzip -t "$backup_file" || return
    say "Verified pre-cutover backup: $backup_file"
}

op_build() {
    local old_container_id old_image_id

    old_container_id=$(compose_current ps -q api) || return
    old_image_id=""
    if [[ -n "$old_container_id" ]]; then
        old_image_id=$($DOCKER_BIN inspect --format '{{.Image}}' "$old_container_id") || return
    elif "$DOCKER_BIN" image inspect cocktaildb-api:latest >/dev/null 2>&1; then
        old_image_id=$($DOCKER_BIN image inspect --format '{{.Id}}' cocktaildb-api:latest) || return
    fi
    if [[ -n "$old_image_id" ]]; then
        "$DOCKER_BIN" image tag "$old_image_id" "$ROLLBACK_IMAGE" || return
        say "Preserved previous API image as $ROLLBACK_IMAGE"
    fi

    "$DOCKER_BIN" build \
        --file "$RELEASE_ROOT/api/Dockerfile.prod" \
        --tag "$NEW_IMAGE" \
        "$RELEASE_ROOT"
}

op_stop() {
    compose_current stop --timeout "$STOP_TIMEOUT_SECONDS" api
}

op_verify_stopped() {
    local running

    running=$(compose_current ps --status running -q api) || return
    if [[ -n "$running" ]]; then
        say "API writer containers are still running: $running"
        return 1
    fi
}

op_migrate() {
    (
        cd "$RELEASE_ROOT" || exit
        "$APP_HOME/scripts/run-migrations.sh" "$APP_ENV"
    )
}

op_verify_recorded() {
    local recorded

    recorded=$(psql_scalar "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE filename = '${MIGRATION_15}');") || return
    [[ "$recorded" =~ ^[[:space:]]*t[[:space:]]*$ ]]
}

op_verify_parity() {
    local membership_ok parity_ok

    membership_ok=$(psql_scalar "
        SELECT NOT EXISTS (
            SELECT DISTINCT ui.cognito_user_id
            FROM user_ingredients ui
            LEFT JOIN user_group_members m
              ON m.cognito_user_id = ui.cognito_user_id
            WHERE m.id IS NULL
        )
        AND NOT EXISTS (
            SELECT cognito_user_id
            FROM user_group_members
            WHERE cognito_user_id IN (
                SELECT DISTINCT cognito_user_id FROM user_ingredients
            )
            GROUP BY cognito_user_id
            HAVING COUNT(*) <> 1
        );") || return
    [[ "$membership_ok" =~ ^[[:space:]]*t[[:space:]]*$ ]] || return 1

    parity_ok=$(psql_scalar "
        SELECT NOT EXISTS (
            (SELECT ui.cognito_user_id, ui.ingredient_id,
                    ui.cognito_user_id AS added_by, ui.added_at
             FROM user_ingredients ui)
            EXCEPT
            (SELECT m.cognito_user_id, gi.ingredient_id,
                    gi.added_by, gi.added_at
             FROM user_group_members m
             JOIN group_ingredients gi ON gi.group_id = m.group_id)
        )
        AND NOT EXISTS (
            (SELECT m.cognito_user_id, gi.ingredient_id,
                    gi.added_by, gi.added_at
             FROM user_group_members m
             JOIN group_ingredients gi ON gi.group_id = m.group_id)
            EXCEPT
            (SELECT ui.cognito_user_id, ui.ingredient_id,
                    ui.cognito_user_id AS added_by, ui.added_at
             FROM user_ingredients ui)
        );") || return
    [[ "$parity_ok" =~ ^[[:space:]]*t[[:space:]]*$ ]]
}

op_start() {
    "$DOCKER_BIN" image tag "$NEW_IMAGE" cocktaildb-api:latest || return
    compose_current up -d --no-build --no-deps --force-recreate api
}

op_health() {
    local attempt

    for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
        if "$CURL_BIN" \
            --fail \
            --silent \
            --show-error \
            --connect-timeout "$HEALTH_CONNECT_TIMEOUT_SECONDS" \
            --max-time "$HEALTH_MAX_TIME_SECONDS" \
            "$HEALTH_URL" >/dev/null; then
            return 0
        fi
        if ((attempt < HEALTH_ATTEMPTS)); then
            sleep "$HEALTH_DELAY_SECONDS"
        fi
    done
    return 1
}

op_stop_new() {
    compose_current stop --timeout "$STOP_TIMEOUT_SECONDS" api
}

op_publish() {
    local previous_web

    previous_web="$APP_HOME/releases/previous-web-${RELEASE_ID}"
    if [[ -e "$previous_web" ]]; then
        say "Refusing to overwrite preserved frontend: $previous_web"
        return 1
    fi

    if [[ -e "$SERVED_WEB" || -L "$SERVED_WEB" ]]; then
        mv "$SERVED_WEB" "$previous_web" || return
    fi
    if ! mv "$RELEASE_ROOT/web" "$SERVED_WEB"; then
        if [[ -e "$previous_web" || -L "$previous_web" ]]; then
            mv "$previous_web" "$SERVED_WEB"
        fi
        return 1
    fi
    say "Previous frontend preserved at $previous_web"
}

run_operation() {
    local operation="$1"

    if [[ -n "$CUTOVER_OPS_DIR" ]]; then
        "$CUTOVER_OPS_DIR/$operation"
    else
        "op_$operation"
    fi
}

fail_cutover() {
    local failed_phase="$1"
    local status="$2"

    if [[ ("$failed_phase" == start || "$failed_phase" == health) && "$NEW_API_STARTED" == true ]]; then
        if run_operation stop_new; then
            NEW_API_STARTED=false
        else
            say "Warning: failed to stop the unready new API; stop it manually."
        fi
    fi

    say "Cutover failed during ${failed_phase}."
    if [[ "$WRITERS_STOPPED" == false ]]; then
        say "The old API and served frontend were left in place. Fix the failure and rerun the normal deploy."
    elif [[ "$NEW_API_MAY_HAVE_WRITTEN" == true ]]; then
        say "The new API may have accepted writes. Keep the old API stopped; repair publication or use the documented post-write recovery procedure."
    else
        say "API writers remain stopped and the previous frontend remains served. Inspect migration state and parity before resuming; do not blindly replay migration 15 or restart the old API."
    fi
    exit "$status"
}

run_phase() {
    local phase="$1"
    local status

    say "CUTOVER phase=$phase"
    if run_operation "$phase"; then
        return 0
    else
        status=$?
        fail_cutover "$phase" "$status"
    fi
}

mkdir -p "$(dirname "$DEPLOY_LOCK_FILE")"
exec 9>"$DEPLOY_LOCK_FILE"
if ! flock -n 9; then
    fail_cutover lock 73
fi

parity_recovery_at_start=false
if [[ -f "$PARITY_MARKER" ]]; then
    parity_recovery_at_start=true
fi

if [[ ! -f "$RELEASE_ROOT/migrations/$MIGRATION_15" ]]; then
    fail_cutover preflight 1
fi
if [[ ! -d "$RELEASE_ROOT/web" || ! -f "$RELEASE_ROOT/web/js/config.js" ]]; then
    fail_cutover preflight 1
fi

say "CUTOVER phase=pending"
if pending_output=$(run_operation pending); then
    say "$pending_output"
else
    fail_cutover pending $?
fi
if grep -Fqx "Would apply: $MIGRATION_15" <<<"$pending_output"; then
    migration_15_was_pending=true
else
    migration_15_was_pending=false
fi
if [[ "$parity_recovery_at_start" == true && "$migration_15_was_pending" == true ]]; then
    say "A prior migration 15 attempt has uncertain SQL/bookkeeping state and must not be replayed."
    say "Inspect the schema and exact legacy/group parity, then either record the verified filename or remove the marker only after confirming the SQL rolled back."
    fail_cutover recovery 1
fi
if [[ "$migration_15_was_pending" == true || "$parity_recovery_at_start" == true ]]; then
    initial_parity_required=true
else
    initial_parity_required=false
fi

run_phase backup
run_phase build
run_phase stop
WRITERS_STOPPED=true
run_phase verify_stopped
if [[ "$migration_15_was_pending" == true ]]; then
    if ! printf '%s\n' "$RELEASE_ID" > "$PARITY_MARKER"; then
        fail_cutover recovery_marker 1
    fi
fi
run_phase migrate
run_phase verify_recorded
if [[ "$initial_parity_required" == true ]]; then
    run_phase verify_parity
    if ! rm -f "$PARITY_MARKER"; then
        fail_cutover recovery_marker 1
    fi
fi
NEW_API_STARTED=true
NEW_API_MAY_HAVE_WRITTEN=true
run_phase start
run_phase health
run_phase publish

say "Cutover complete: API ready and frontend published from $RELEASE_ROOT"
