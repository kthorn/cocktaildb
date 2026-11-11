# CocktailDB agent guide

CocktailDB (mixology.tools) is a cocktail recipe app: a FastAPI + PostgreSQL API and a vanilla-JS multi-page frontend built by Vite, served by Caddy on a single EC2 host per environment (dev, prod). `CLAUDE.md` is a symlink to this file; edit `AGENTS.md`.

## Repository map

- `api/`: FastAPI app (`main.py`), `routes/`, Pydantic `models/`, `dependencies/auth.py` (Cognito JWT), `core/` (settings, exceptions, global handlers), `db/` (`db_core.py` `Database` class, SQL constants in `sql_queries.py`, `db_analytics.py`), `templates/` (Jinja2 server-rendered recipe/ingredient pages).
- `src/web/`: frontend source. All backend calls go through `CocktailAPI` in `js/api.js`; auth is in `js/auth.js`.
- `packages/barcart/`: standalone similarity/analytics package (EMD, optimal transport) with its own tests; data-agnostic, takes DataFrames.
- `infrastructure/`: Ansible playbooks, Caddyfile, `postgres/schema.sql`, systemd backup/analytics timers, host-side scripts.
- `migrations/`: numbered SQL migrations (`NN_migration_*.sql`, rollbacks in `migrations/rollbacks/`). Files `01`–`08` predate PostgreSQL and use SQLite syntax.
- `scripts/`: deploy wrapper, frontend artifact, restore, and config generation.
- `template.yaml`: CloudFormation for shared AWS resources (Cognito, backup S3, IAM, DNS). Stacks are `cocktaildb-dev` and `cocktaildb-prod`.
- `tests/`: pytest suites plus Node tests (`test_*.js`, `test_*.mjs`).

## Environment

- Python: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python` (conda env `cocktaildb`). Runtime is 3.14; minimum supported syntax is 3.12. README "Python support" is the authoritative version policy.
- Node 22.22.2 (Vite needs ≥22.12). The root `package.json` is intentionally typeless so existing CommonJS scripts keep working; don't add `"type": "module"`.
- Database-backed tests start PostgreSQL through testcontainers, so Docker must be running. Without Docker, those tests error at fixture setup; say so rather than treating them as passed.

## Commands

`PY=/home/kurtt/miniforge3/envs/cocktaildb/bin/python`

- Full API suite (what CI runs): `$PY -m pytest -q`
- Focused frontend/deploy release gate: the exact command under "Tests and formatting" in `README.md`
- Barcart: `$PY -m pytest packages/barcart/tests`
- Node tests: `node --test tests/test_*.js tests/test_*.mjs`
- Frontend artifact: `npm ci && npm run build && npm run test:build`
- All formatters and linters: `$PY -m pre_commit run --all-files` (ruff, prettier, shfmt; CI is authoritative)
- Local frontend: `./scripts/local-config.sh` writes the gitignored `src/web/js/config.js`, then `./scripts/serve.sh` serves Vite on `http://localhost:8000`. For server-rendered pages, also run FastAPI on port 8001 with `FRONTEND_ASSET_MODE=development`, and browse through port 8000.
- Preview a built artifact: `npm run preview -- /path/to/config.js` (uses a disposable copy).

There is no browser automation. For UI changes, list the manual checks needed: index/search/analytics, nested recipe and ingredient pages, and login/callback/logout.

## Conventions

- Commits are conventional (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`). PRs include a short summary and a test plan.
- Python: Ruff, `snake_case`/`PascalCase`. JS/HTML/YAML: Prettier per `.prettierrc` (4 spaces, single quotes, 100 columns). Shell: shfmt `-i 4 -ci`. `api/templates/*.html` are Jinja2 and excluded from Prettier. Markdown is not auto-formatted.
- API routes: inject `db: Database = Depends(get_db)` (`db.database.get_database`, imported as `get_db`) and use auth dependencies from `dependencies/auth.py` (`get_current_user_optional`, `require_authentication`, `require_editor_access`). Raise `core/exceptions.py` types (`NotFoundException`, `ValidationException`, `ConflictException`, …) and let the global handlers format responses. Don't add catch-all `except Exception` blocks that re-wrap errors as `DatabaseException`; that turns client errors into 500s.
- Schema changes need both a new numbered migration and an update to `infrastructure/postgres/schema.sql`.
- Ingredients are hierarchical with materialized paths (`/1/23/45/`); searching by a parent includes descendants. Recipe `avg_rating`/`rating_count` are maintained by database triggers.
- Analytics are pre-generated JSON files under `ANALYTICS_PATH` (`v1/{type}.json`), not S3. A debounced systemd timer refreshes them after mutations.
- Frontend runtime config (`web/js/config.js`) comes from deployment or local setup and is never bundled into `dist/`.
- Caddy routes `/api/v1/*` (current) and `/api/*` (legacy) to the same FastAPI app with the prefix stripped, so routes are declared without `/api`.

## Deployment and operations

Deploying and running migrations against dev or prod are human actions. Don't do either unless explicitly asked.

- Deploy: `./scripts/deploy-ec2.sh <dev|prod> --frontend-artifact dist`. The wrapper stages config, publishes assets, stops the API, runs migrations, cuts over, and smoke-checks through Caddy. See `scripts/README.md` and `docs/operations-runbook.md`.
- Keep the deploy pending marker. Never delete it to bypass reconciliation, and never automatically restart an old API after possible writes.
- `infrastructure/scripts/run-migrations.sh [dev|prod] [--dry-run]` applies every unrecorded `migrations/*.sql`. Run it only through the deploy cutover, never by hand while the API is serving.
- On the hosts, the API runs in Docker Compose under `/opt/cocktaildb` (`sudo docker logs cocktaildb-api-1`). Caddy and PostgreSQL are host services (`journalctl -u caddy`, `-u postgresql`).
- SSH is via EC2 Instance Connect as `ec2-user` (Amazon Linux 2023, ARM64). Look up the instance with `aws ec2 describe-instances --filters "Name=tag:Name,Values=cocktaildb-dev" --query 'Reservations[0].Instances[0].InstanceId' --output text`. The runbook has the full procedure.
- Analytics refresh: `./infrastructure/scripts/trigger-analytics-remote.sh [host] [--bg|--status|--progress]`.
- Never commit secrets, `.env` files, or `src/web/js/config.js`.

## Where to look

- Issues: GitHub (`gh issue list`).
- `README.md`: Python policy, release gate, deployment overview.
- `TESTING.md`: test suite layout.
- `docs/operations-runbook.md`: operations, recovery, CloudWatch log queries.
- `docs/plans/`: active plans. Finished plans move to `docs/plans/completed/`.
