# Refactoring and Dead Code Cleanup Implementation Plan

**Goal:** Implement the six approved audit findings with small changes and preserve public API behavior except the identified duplicate work.

**Architecture:** Keep existing route and database interfaces. Extract a shared cached-analytics loader and a shared tag insertion operation, retain private-tag authorization, and let common frontend startup initialize authentication. Remove unreferenced SQL helpers/imports and the obsolete pagination response model after moving its test to the active model.

**Tech stack:** FastAPI, PostgreSQL/psycopg2, pytest, vanilla JavaScript, Node, Ruff, Prettier.

## Tasks

- [x] Remove unused SQL helpers in `api/db/sql_queries.py`, their imports in `api/db/db_core.py`, and the remaining Ruff F401 findings in `api/`. Verify references and rerun Ruff.
- [x] Remove duplicate auth initialization in `src/web/js/admin.js`. Add a Node regression test that exercises page startup and checks one auth timer/listener set, including admin setup.
- [x] Replace eager `setdefault` lookup in `api/routes/ingredients.py` with an explicit cache membership check. First demonstrate repeated and missing ingredient lookups in a failing regression test; then rerun bulk-value tests.
- [x] Extract cached JSON loading in `api/routes/analytics.py`. Preserve missing/configuration error details, live ratings, cache headers, and hierarchical drill-down. Verify endpoint success/error behavior using focused tests.
- [x] Share insertion SQL between public/private tag methods in `api/db/db_core.py`, preserving wrapper interfaces, conflict return values, and ownership checks. Run tag tests and focused database-operation tests.
- [x] Replace permissive pagination scaffolding in `tests/test_pagination.py` with strict tests for the actual `/recipes/search` contract. Remove `PaginatedRecipeResponse` in `api/models/responses.py` after confirming no runtime uses. Cover defaults, validation, metadata, filtering across nonempty pages, and recipe data.
- [x] Review the full diff for scope compliance and code quality. Run focused pytest/Node tests, API unused-import checks, repository formatters, and `git diff --check`. Attempt relevant PostgreSQL integration tests and report any environment blocker.

## Execution

Use independent agents for frontend startup, analytics loading, and pagination tests/models; the primary agent owns dead code, CSV lookup caching, and tag insertion. Avoid concurrent edits to shared files. Leave changes uncommitted for user review.

## Environment baseline

Working tree was clean. `docker info` reports Docker unavailable in this WSL distro; PostgreSQL testcontainers require Docker. Use the installed `~/miniforge3/envs/cocktaildb/bin/python` for Python checks.

## Verification results

- Combined focused pytest run: **110 passed**, with existing dependency deprecation warnings. Includes the new auth, CSV, tag-insertion and analytics tests, existing frontend/analytics/helper contracts, and pagination models/request validation.
- CSV regressions failed before the fix for both repeated existing IDs and repeated missing IDs; both pass after the fix. The auth startup regression similarly detected two timers before the fix and one afterward.
- API Ruff `F401,F841`, Node syntax checks, all repository formatter hooks (including new untracked test files), and `git diff --check` pass.
- PostgreSQL integration tests were attempted, including a retry outside the sandbox. Testcontainers cannot start because the local Docker socket is absent. The seeded pagination and PostgreSQL tag/bulk-value tests therefore still need a Docker-enabled run.
- ASGI file-response/request tests were run outside the sandbox after a sandboxed run stalled; the final combined run completed in under one second.

- Independent final review: no findings; all six approved changes are within scope.
