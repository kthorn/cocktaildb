# Agent notes

`CLAUDE.md` is a symlink to this file.

## Environment

- Python: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python`. README "Python support" is the authoritative version policy.
- Database-backed tests use testcontainers, so they need Docker. If Docker is unavailable, those tests error at setup: report them as not run, not as passing.
- The root `package.json` is intentionally typeless; don't add `"type": "module"`.

## Checks

- Using that interpreter: full suite, as CI runs it, `python -m pytest -q`; formatting and lint, `python -m pre_commit run --all-files`.
- Node tests: `node --test tests/test_*.js tests/test_*.mjs`.
- There is no browser automation. For UI changes, list the manual checks you couldn't run.

## Conventions

- Commits use conventional prefixes (`feat:`, `fix:`, `chore:`, `docs:`). PRs include a summary and a test plan.
- Routes raise `core/exceptions.py` types and let the global handlers build the response. Don't wrap handlers in `except Exception` → `DatabaseException`: that turns client errors into 500s.
- A schema change needs both a new numbered file in `migrations/` and the matching edit to `infrastructure/postgres/schema.sql`.
- Caddy strips `/api/v1` (and legacy `/api`) before proxying, so FastAPI routes are declared without that prefix.

## Deployment and production

Deploys and migrations against dev or prod are human actions. Don't run them unless asked.

- Deploy only through `scripts/deploy-ec2.sh`. It stops the API before migrating.
- Never run `run-migrations.sh` by hand while the API is serving.
- Never delete the deploy pending marker to get past reconciliation.
- Operational procedures are in `docs/operations-runbook.md`.

Issues are tracked on GitHub (`gh issue list`).
