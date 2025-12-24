# Analytics Change Trigger + EC2 Migration Runner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a debounced, change-triggered analytics refresh and a psql-based migration runner with a one-command remote execution wrapper.

**Architecture:** Postgres triggers update a single-row analytics refresh state table on any relevant mutations. A systemd timer runs a debounce script every minute to start the existing analytics service after 15 minutes of inactivity. Migrations are applied by a local `psql` runner that tracks `schema_migrations`, and a local wrapper script rsyncs the repo to EC2 and runs the runner over SSH.

**Tech Stack:** Postgres (PL/pgSQL triggers), systemd, Bash, `psql`, Ansible, pytest (lightweight file-content tests).

### Task 1: Add analytics refresh state migration + schema updates

**Files:**
- Create: `migrations/09_migration_add_analytics_refresh_state.sql`
- Modify: `infrastructure/postgres/schema.sql`
- Create: `tests/test_analytics_trigger_migration_sql.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

def test_analytics_refresh_migration_contains_expected_sql():
    sql = Path("migrations/09_migration_add_analytics_refresh_state.sql").read_text()
    assert "CREATE TABLE" in sql
    assert "analytics_refresh_state" in sql
    assert "mark_analytics_dirty" in sql
    assert "CREATE TRIGGER" in sql
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analytics_trigger_migration_sql.py -v`
Expected: FAIL with file not found or missing content.

**Step 3: Write minimal implementation**

Create `migrations/09_migration_add_analytics_refresh_state.sql` with:

```sql
CREATE TABLE IF NOT EXISTS analytics_refresh_state (
    id INTEGER PRIMARY KEY,
    dirty_at TIMESTAMP,
    last_run_at TIMESTAMP
);

INSERT INTO analytics_refresh_state (id, dirty_at, last_run_at)
VALUES (1, NULL, NULL)
ON CONFLICT (id) DO NOTHING;

CREATE OR REPLACE FUNCTION mark_analytics_dirty()
RETURNS trigger AS $$
BEGIN
    UPDATE analytics_refresh_state
    SET dirty_at = CURRENT_TIMESTAMP
    WHERE id = 1;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS analytics_recipes_dirty ON recipes;
CREATE TRIGGER analytics_recipes_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipes
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_ingredients_dirty ON ingredients;
CREATE TRIGGER analytics_ingredients_dirty
AFTER INSERT OR UPDATE OR DELETE ON ingredients
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_recipe_ingredients_dirty ON recipe_ingredients;
CREATE TRIGGER analytics_recipe_ingredients_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipe_ingredients
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_units_dirty ON units;
CREATE TRIGGER analytics_units_dirty
AFTER INSERT OR UPDATE OR DELETE ON units
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_ratings_dirty ON ratings;
CREATE TRIGGER analytics_ratings_dirty
AFTER INSERT OR UPDATE OR DELETE ON ratings
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_tags_dirty ON tags;
CREATE TRIGGER analytics_tags_dirty
AFTER INSERT OR UPDATE OR DELETE ON tags
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_recipe_tags_dirty ON recipe_tags;
CREATE TRIGGER analytics_recipe_tags_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipe_tags
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();
```

Update `infrastructure/postgres/schema.sql` to include the same table + function + triggers for fresh installs. If schema.sql already defines triggers section, keep it near related tables.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_analytics_trigger_migration_sql.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add migrations/09_migration_add_analytics_refresh_state.sql infrastructure/postgres/schema.sql tests/test_analytics_trigger_migration_sql.py
git commit -m "feat: add analytics refresh state migration"
```

### Task 2: Add debounce script + systemd units + deploy wiring

**Files:**
- Create: `infrastructure/scripts/analytics-debounce-check.sh`
- Create: `infrastructure/systemd/cocktaildb-analytics-debounce.service`
- Create: `infrastructure/systemd/cocktaildb-analytics-debounce.timer`
- Modify: `infrastructure/ansible/playbooks/deploy.yml`
- Create: `tests/test_analytics_debounce_files.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

def test_debounce_script_and_units_exist():
    assert Path("infrastructure/scripts/analytics-debounce-check.sh").exists()
    assert Path("infrastructure/systemd/cocktaildb-analytics-debounce.service").exists()
    assert Path("infrastructure/systemd/cocktaildb-analytics-debounce.timer").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analytics_debounce_files.py -v`
Expected: FAIL with missing files.

**Step 3: Write minimal implementation**

Create `infrastructure/scripts/analytics-debounce-check.sh`:

```bash
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
```

Create `infrastructure/systemd/cocktaildb-analytics-debounce.service`:

```ini
[Unit]
Description=CocktailDB Analytics Debounce Check
After=network.target postgresql.service

[Service]
Type=oneshot
User=cocktaildb
Group=cocktaildb
EnvironmentFile=/opt/cocktaildb/.env
Environment=ANALYTICS_DEBOUNCE_MINUTES=15
ExecStart=/usr/local/bin/analytics-debounce-check.sh
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cocktaildb-analytics-debounce
```

Create `infrastructure/systemd/cocktaildb-analytics-debounce.timer`:

```ini
[Unit]
Description=Run CocktailDB Analytics Debounce Check Every Minute

[Timer]
OnUnitActiveSec=60
Persistent=true

[Install]
WantedBy=timers.target
```

Update `infrastructure/ansible/playbooks/deploy.yml`:
- Add a task to copy `infrastructure/scripts/analytics-debounce-check.sh` to `/usr/local/bin/analytics-debounce-check.sh` with `0755`.
- Enable `cocktaildb-analytics-debounce.timer`.
- Disable `cocktaildb-analytics.timer` (daily) or leave it stopped/disabled.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_analytics_debounce_files.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add infrastructure/scripts/analytics-debounce-check.sh infrastructure/systemd/cocktaildb-analytics-debounce.service infrastructure/systemd/cocktaildb-analytics-debounce.timer infrastructure/ansible/playbooks/deploy.yml tests/test_analytics_debounce_files.py
git commit -m "feat: add analytics debounce service"
```

### Task 3: Add psql migration runner script

**Files:**
- Create: `infrastructure/scripts/run-migrations.sh`
- Create: `tests/test_run_migrations_script.py`

**Step 1: Write the failing test**

```python
import subprocess
from pathlib import Path

def test_run_migrations_help():
    script = Path("infrastructure/scripts/run-migrations.sh")
    assert script.exists()
    result = subprocess.run(["bash", str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Usage" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_migrations_script.py -v`
Expected: FAIL with missing script.

**Step 3: Write minimal implementation**

Create `infrastructure/scripts/run-migrations.sh`:

```bash
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_run_migrations_script.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add infrastructure/scripts/run-migrations.sh tests/test_run_migrations_script.py
git commit -m "feat: add psql migration runner"
```

### Task 4: Add local remote-run wrapper script

**Files:**
- Create: `scripts/run-remote-migrations.sh`
- Create: `tests/test_run_remote_migrations_script.py`

**Step 1: Write the failing test**

```python
import subprocess
from pathlib import Path

def test_run_remote_migrations_help():
    script = Path("scripts/run-remote-migrations.sh")
    assert script.exists()
    result = subprocess.run(["bash", str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Usage" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_remote_migrations_script.py -v`
Expected: FAIL with missing script.

**Step 3: Write minimal implementation**

Create `scripts/run-remote-migrations.sh`:

```bash
#!/bin/bash
set -euo pipefail

TARGET_ENV="dev"
APP_DIR="/opt/cocktaildb"
HOST=""
SSH_KEY="${COCKTAILDB_SSH_KEY:-}"

show_help() {
  cat << EOT
Usage: $0 [dev|prod]

Runs /opt/cocktaildb/scripts/run-migrations.sh over SSH.
Note: run the Ansible deploy first so /opt/cocktaildb ownership and scripts are set.
Optional env:
  COCKTAILDB_SSH_KEY=/path/to/key.pem
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

ssh "${SSH_OPTS[@]}" "$HOST" "cd $APP_DIR && ./scripts/run-migrations.sh"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_run_remote_migrations_script.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/run-remote-migrations.sh tests/test_run_remote_migrations_script.py
git commit -m "feat: add remote migration wrapper"
```

### Task 5: Ops verification checklist (docs)

**Files:**
- Modify: `docs/plans/2025-12-23-analytics-change-trigger.md`

**Step 1: Add verification notes**

Append a short “Ops Verification” section:
- `SELECT * FROM analytics_refresh_state;` after a write
- `systemctl status cocktaildb-analytics-debounce.timer`
- `journalctl -u cocktaildb-analytics-debounce.service -n 50 --no-pager`
- Manual edit burst -> verify single analytics run

**Step 2: Commit**

```bash
git add docs/plans/2025-12-23-analytics-change-trigger.md
git commit -m "docs: add analytics trigger ops verification"
```

### Manual Verification (post-implementation)

- Run the Ansible deploy first so `/opt/cocktaildb` ownership and scripts are set.
- Run `scripts/run-remote-migrations.sh dev` and confirm migrations apply on dev.
- If SSH requires a specific key, use `COCKTAILDB_SSH_KEY=~/.ssh/cocktaildb-ec2.pem scripts/run-remote-migrations.sh dev`.
- Update a recipe and verify `analytics_refresh_state.dirty_at` updates.
- Make multiple edits inside 15 minutes and confirm analytics runs once after inactivity.
- Confirm daily `cocktaildb-analytics.timer` is disabled and debounce timer is active.

Plan complete and saved to `docs/plans/2025-12-23-analytics-change-trigger-implementation.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
