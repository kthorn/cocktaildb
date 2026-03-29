# Analytics Change-Triggered Refresh (Debounced)

## Problem
Analytics currently runs on a daily systemd timer or manual trigger, but the desired behavior is to refresh analytics only when data changes, and to debounce bursts of changes so we only run once per 15 minutes of inactivity.

## Goals
- Trigger analytics after relevant DB edits (create/update/delete).
- Debounce to a single run if multiple edits happen within a 15 minute window.
- Reuse the existing analytics runner (`cocktaildb-analytics.service`).
- Avoid running analytics daily.

## Non-Goals
- Rewriting analytics computation logic.
- Replacing the existing manual trigger script.
- Changing analytics storage formats.

## Proposed Architecture

**Flow:**
```
DB mutation (recipes/ingredients/recipe_ingredients/units/ratings/tags/recipe_tags)
  -> DB trigger marks analytics "dirty"
  -> Debounce service polls state
  -> If no new edits for 15 minutes, start cocktaildb-analytics.service
```

**Key pieces:**
1) **DB trigger + state table**
   - Add a small state table (e.g., `analytics_refresh_state`) with:
     - `dirty_at` (timestamp)
     - `last_run_at` (timestamp)
   - Add a trigger function that runs on INSERT/UPDATE/DELETE for analytics-relevant tables.
   - The trigger updates `dirty_at = now()` and leaves `last_run_at` untouched.

2) **Debounce worker**
   - Add a systemd timer/service pair (e.g., `cocktaildb-analytics-debounce.timer` + `.service`).
   - The service runs every 1 minute and:
     - Reads `dirty_at` and `last_run_at`.
     - If `dirty_at` is NULL -> do nothing.
     - If `dirty_at + 15 minutes <= now()` and `last_run_at < dirty_at`,
       then start `cocktaildb-analytics.service` and set `last_run_at = now()`.
   - Use a Postgres advisory lock to prevent multiple concurrent checks from triggering duplicate runs.

3) **Existing runner stays the same**
   - `infrastructure/systemd/cocktaildb-analytics.service` remains the entrypoint:
     `docker compose run --rm api python -m analytics.analytics_refresh`.
   - Manual trigger script (`infrastructure/scripts/trigger-analytics.sh`) remains unchanged.

## Configuration
- Debounce window: 15 minutes (configurable via env var in the debounce service).
- Poll interval: 60 seconds.

## Implementation Plan
1) **Schema updates (Postgres)**
   - Add state table in `infrastructure/postgres/schema.sql`:
     - `analytics_refresh_state` with a single row keyed by `id = 1`.
     - Columns: `dirty_at TIMESTAMP`, `last_run_at TIMESTAMP`.
   - Add a trigger function, e.g. `mark_analytics_dirty()`:
     - `UPDATE analytics_refresh_state SET dirty_at = CURRENT_TIMESTAMP WHERE id = 1;`
     - If the row is missing, insert it once during migration.
   - Attach triggers for `AFTER INSERT OR UPDATE OR DELETE` to:
     - `recipes`, `ingredients`, `recipe_ingredients`, `units`,
       `ratings`, `tags`, `recipe_tags`.
   - Optional: exclude changes that do not affect analytics
     (e.g., `ratings` if analytics ignores ratings).

2) **Debounce check script**
   - Add a small script in `infrastructure/scripts/analytics-debounce-check.sh`:
     - Reads `DB_*` env vars (same as API) for `psql` connection.
     - Acquires advisory lock (`pg_try_advisory_lock`) to prevent concurrent runs.
     - Reads `dirty_at`/`last_run_at` from `analytics_refresh_state`.
     - If `dirty_at` is NULL -> exit 0.
     - If `dirty_at + INTERVAL '15 minutes' <= now()` and
       (`last_run_at` IS NULL OR `last_run_at < dirty_at`):
       - `systemctl start cocktaildb-analytics.service`
       - `UPDATE analytics_refresh_state SET last_run_at = CURRENT_TIMESTAMP WHERE id = 1;`
     - Release advisory lock and exit.

3) **Systemd units**
   - Add `infrastructure/systemd/cocktaildb-analytics-debounce.service`:
     - `ExecStart=/usr/local/bin/analytics-debounce-check.sh`
     - `Environment=ANALYTICS_DEBOUNCE_MINUTES=15` (or read from env file).
   - Add `infrastructure/systemd/cocktaildb-analytics-debounce.timer`:
     - `OnUnitActiveSec=60` (run every minute).
     - `Persistent=true`.
   - Keep `infrastructure/systemd/cocktaildb-analytics.service` unchanged.

4) **Ansible deployment**
   - Copy the new script to `/usr/local/bin/analytics-debounce-check.sh`
     with `0755` perms.
   - Install and enable `cocktaildb-analytics-debounce.timer`.
   - Disable/remove `cocktaildb-analytics.timer` (daily run) and reload systemd.

5) **Migration (current Postgres)**
   - Add a SQL migration in `migrations/` to create `analytics_refresh_state`
     and seed the `id = 1` row.
   - Apply the migration to the current Postgres server for both dev and prod
     (same server process; separate DBs or schemas as applicable).
   - If migrations are applied manually today, document the exact command(s)
     to run against the live Postgres instance.
   - Replace the old Lambda-based migration runner with a server-based runner:
     - Add a CLI script (e.g., `infrastructure/scripts/run-migrations.sh`) that executes
       pending SQL files in `migrations/` using `psql` and a tracked
       `schema_migrations` table.
     - Wire the runner into the EC2 deployment workflow (Ansible task) so
       migrations run during deploys.
     - Ensure the runner supports both dev and prod DB targets via env vars.

6) **Ops checklist**
   - Verify `analytics_refresh_state` exists and row `id=1` is present.
   - Confirm `dirty_at` updates on a mutation.
   - Confirm timer is active: `systemctl status cocktaildb-analytics-debounce.timer`.
   - Confirm analytics runs once after 15 minutes of inactivity.

## Testing
- Manual: edit a recipe, confirm `dirty_at` updates.
- Manual: make multiple edits within 15 minutes, confirm only one analytics run.
- Manual: verify no analytics runs occur without DB changes.

## Ops Verification
- `SELECT * FROM analytics_refresh_state;` after a write
- `systemctl status cocktaildb-analytics-debounce.timer`
- `journalctl -u cocktaildb-analytics-debounce.service -n 50 --no-pager`
- Manual edit burst -> verify single analytics run

## Risks / Mitigations
- **Missed triggers:** DB-level triggers ensure any writer (API or script)
  marks analytics dirty.
- **Duplicate runs:** debounce + `last_run_at` check + advisory lock.
- **Long analytics runs:** existing systemd service already defines a timeout;
  debounce worker only starts it and records `last_run_at`.

## Rollout
- Deploy schema + debounce units.
- Disable daily analytics timer.
- Monitor first week to confirm expected cadence.
