# User Groups with Shared Inventory Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task. This is the authoritative implementation plan; it supersedes the April 8 draft.

**Status:** Ready to implement after repository review on 2026-09-08 and incorporation of the independent review’s deployment blocker. Task 8 must be implemented before deploying this feature. No application changes or migrations have been executed.

**Goal:** Share one home bar inventory among trusted group members while preserving existing inventory API behavior and personal ratings/private tags.

**Architecture:** A user has at most one membership, enforced by PostgreSQL, and receives a personal group on first inventory/group access. Inventory methods resolve membership and operate exclusively on `group_ingredients`. Group management, inventory authorization, and membership transitions execute on one connection in one transaction.

**Tech Stack:** FastAPI, Pydantic, psycopg2/PostgreSQL 15, vanilla JavaScript, pytest/testcontainers, Node contract tests.

## Review findings resolved

| Draft defect | Implementation decision |
| --- | --- |
| Migration 14 already exists (`14_migration_roll_up_ingredient_values.sql`). | Use `15_migration_add_user_groups.sql`; recheck numbering before implementation. |
| `SELECT DISTINCT user_id, random_code` generates a row per inventory item because random codes differ. | Deduplicate users in a subquery before generating codes; test multi-item migration. |
| Route-only membership checks race with kicks, joins, and writes; `ON CONFLICT DO NOTHING` can return a new group without moving membership. | Authorize and move membership inside the transaction; require exactly one updated membership. |
| Draft returns pooled connections twice on some error and same-group join paths. | One connection owner, one `finally` return, cursor context manager, rollback on failure. |
| Creating a group silently abandons existing inventory. | Creation with existing membership returns 409; rename the existing bar with PUT. |
| Group route references unimported ingredient request models; DELETE bulk route is shadowed by dynamic ingredient route. | Import all three ingredient models and register static routes before dynamic routes. |
| Search route puts `group_id` in parameters but `Database.search_recipes_paginated` never binds it. | Resolve/bind at the DB entry point, including direct callers and both search SQL builders. |
| Draft leaves old DB inventory methods and recommendation SQL active. | Preserve public Python method signatures as wrappers; eliminate application SQL access to the old table. |
| Draft frontend uses `import api` although the module exports `{ api }`, relative nav links, and console-only errors. | Named import, root-relative navigation, visible status region, DOM behavior tests. |
| Draft accepts missing-table failures, misses legacy test seeds, and has no migration/concurrency tests. | Establish schema fixtures first; explicit migration, race, compatibility, search, and UI gates below. |
| Independent review: the normal deployment publishes frontend early and migrates while old API writers remain live. | Task 8 changes and tests the actual deployment path to enforce staging, writer shutdown, migration verification, API readiness, and frontend publication in order. |

## Product and API contract

Keep the existing one-group, equal-permission design. All members can rename, rotate invitations, and remove other members. Cognito authorization roles remain unrelated to bar memberships. No ownership roles, multi-group selector, notifications, or Cognito profile lookup are added.

- Joining copies the **entire current group's** inventory into the target (including when leaving a shared bar), then moves only the joining user. Existing destination rows retain their attribution/timestamp; source rows remain unchanged. UI must explain the merge before submission.
- Joining the current group is a successful no-op, with no membership timestamp change. An invalid code changes nothing, including for a user with no group.
- Leaving creates a new personal group and moves membership atomically. Require an explicit `copy_inventory` boolean; the UI defaults it to true. Solo leave returns 409; users rename their solo bar instead.
- Removing another member always creates a personal group for that member and copies the full inventory. The removed user cannot answer a prompt, so the initiating UI explains this behavior. Self-removal returns 400 and must use leave instead. Missing target membership returns 404.
- Empty groups persist as in the original design, but cannot be joined with an old invite code. A user can only join a group with at least one current member; otherwise return 404. There is no orphan cleanup in this release.
- `POST /groups` creates a named personal group only for a user without membership. Existing members get 409 without any change. Ordinary UI starts with auto-created `My Bar` and renames it; no redundant create form.
- `GET /groups/mine` auto-creates when needed. Group-ID routes never auto-create membership as a substitute for authorization. Nonmembers get 403 without group data or invite codes.
- `GroupCreate`: trimmed, nonblank name, max 100; optional description, max 500. `GroupUpdate`: same validation for supplied name, reject explicit null name; omitted fields unchanged, explicit null description clears it; empty update is a successful no-op. Use `model_dump(exclude_unset=True)` to distinguish omission from null.
- Invite codes retain the original 12 hex characters (`secrets.token_hex(6)`). Trim and lowercase input and validate exactly 12 hex characters. Malformed input returns 422, well-formed unknown/retired code 404. Do not log codes or request bodies; existing rate limiter applies to these routes.
- `GroupMemberResponse`: `cognito_user_id`, `joined_at`; no fabricated username. Display the ID and mark the current member using `getUserInfo().cognitoUserId`.
- All successful group-object responses (create, mine, update, join, leave, regenerate) use `GroupDetailResponse`: `id`, `name`, nullable `description`, `invite_code`, `created_at`, `updated_at`, `members`, `member_count`. Derive count from the returned member list in the same transaction. Create returns 201; other group-object operations return 200; kick returns existing `MessageResponse` with 200.

Paths below are router paths; the deployed proxy adds `/api/v1`:

| Method | Path | Result |
| --- | --- | --- |
| POST | `/groups` | Create, 201 or 409 |
| GET | `/groups/mine` | Current detail, ensure membership |
| PUT | `/groups/{group_id}` | Update detail |
| POST | `/groups/join` | Merge and move by invite code |
| POST | `/groups/{group_id}/leave` | New personal detail |
| DELETE | `/groups/{group_id}/members/{user_id}` | Remove another member |
| POST | `/groups/{group_id}/invite-code/regenerate` | Detail with new code |
| GET, POST | `/groups/{group_id}/ingredients` | Existing inventory list/add response shapes |
| POST, DELETE | `/groups/{group_id}/ingredients/bulk` | Existing bulk response shapes |
| DELETE | `/groups/{group_id}/ingredients/{ingredient_id}` | Existing deletion response shape |
| GET | `/groups/{group_id}/ingredients/recommendations` | Existing recommendation response shape |

Preserve all six `/user-ingredients` endpoints and DB method signatures. Single add includes ancestor insertion and duplicate rejection; bulk add preserves current explicit-items-only behavior and counts (it currently does **not** auto-add ancestors). Bulk removal validates the entire requested set before deleting children then parents; an unselected remaining descendant rejects the operation without partial deletion. Preserve error categories, inventory list ordering, and recommendation substitution rules. Shared rows retain `added_by` internally; the legacy response does not acquire required new fields. Ratings and private tags remain keyed by the authenticated user's ID.

## Transaction protocol

For this small initial deployment, use one transaction-scoped advisory lock for all group/inventory operations: `SELECT pg_advisory_xact_lock(73421, 1)`. This deliberately serializes these operations across bars and avoids competing user/group lock orders. Ordinary recipe searches without inventory filtering are unaffected. Revisit granularity only if measured traffic requires it.

Every public group/inventory method acquires that lock **before** resolving membership or checking authorization, holds it through reads/writes and response assembly, and commits or rolls back before returning the connection. Inventory-filtered recipe search follows the same protocol through query execution. This covers implicit user wrappers as well as explicit group endpoints. No HTTP calls, UI interaction, or nested connection acquisition while holding the lock.

Add cursor-taking private helpers in `Database` for group creation, membership lookup/check, detail assembly, inventory operations, and transitions. Never call `execute_query()`, `get_user_group()`, `get_ingredient()`, or another public transaction-owning method from inside this transaction. Execute their needed queries with the existing cursor. The transaction owner follows this exact resource pattern:

```python
conn = self._get_connection()
try:
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(73421, 1)")
            result = operation(cursor)
    return result
finally:
    self._return_connection(conn)
```

`operation` above represents a private cursor helper, not a new public callback API. psycopg2 connection context commits on success and rolls back on exceptions. Serialize auto-creation by rechecking membership under this lock; no broad `IntegrityError` catch returning `None`. Retry only invite-code uniqueness collisions using a SAVEPOINT and a fresh token (maximum five attempts); re-raise other integrity failures. Roll back the savepoint before retrying PostgreSQL statements.

For transitions, validate actor, target membership, destination invite code and nonempty destination under the lock. Copy inventory with `INSERT ... SELECT ... ON CONFLICT (group_id, ingredient_id) DO NOTHING`; update the existing membership by both user and expected source group, set `joined_at=CURRENT_TIMESTAMP`, and assert `rowcount == 1`. Insert membership only if the user had none. A failure rolls back group creation, copies, and membership changes together. Kicks accept **actor_user_id and target_user_id**, and validate both within this transaction. Do not delegate a kick to a separately committed leave operation.

## Task 1: Migration and fresh-schema parity

**Create:** `migrations/15_migration_add_user_groups.sql`, `tests/test_user_groups_migration.py`.
**Modify:** `infrastructure/postgres/schema.sql`, `tests/conftest.py` only if new fixture support is needed.

- [ ] Write migration tests using PostgreSQL connections and a pre-feature schema fixture. Capture the current schema as a test fixture before adding group tables (create `tests/fixtures/pre_user_groups_schema.sql`). Never apply a backfill test to the already-updated fresh schema.
- [ ] Seed one user with multiple ingredients, another user sharing one of those ingredients, and known timestamps; run migration; assert one membership/group per distinct user, identical inventory content and timestamps, original user as `added_by`, and unchanged legacy rows. Also test empty inventory, explicit null legacy timestamps, and transactional rollback on injected failure. The old schema permits null timestamps: the migration must reject these with a clear preflight error and no schema/data changes, rather than invent historical timestamps. Resolve any such data before cutover.
- [ ] Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_user_groups_migration.py -v`; expect failure because the migration is absent.
- [ ] Implement these schema objects inside explicit `BEGIN; ... COMMIT;` (the migration runner does not wrap files):

```sql
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM user_ingredients WHERE added_at IS NULL) THEN
        RAISE EXCEPTION 'Resolve null user_ingredients.added_at before group migration';
    END IF;
END $$;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    invite_code TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE user_group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    cognito_user_id TEXT NOT NULL UNIQUE,
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE group_ingredients (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL,
    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (group_id, ingredient_id)
);
CREATE INDEX idx_user_group_members_group_id ON user_group_members(group_id);
CREATE INDEX idx_group_ingredients_ingredient_id ON group_ingredients(ingredient_id);
CREATE TRIGGER update_user_groups_updated_at
    BEFORE UPDATE ON user_groups FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TEMP TABLE user_group_mapping ON COMMIT DROP AS
SELECT cognito_user_id, encode(gen_random_bytes(6), 'hex') AS invite_code
FROM (SELECT DISTINCT cognito_user_id FROM user_ingredients) AS users;
INSERT INTO user_groups (name, invite_code)
SELECT 'My Bar', invite_code FROM user_group_mapping;
INSERT INTO user_group_members (group_id, cognito_user_id)
SELECT g.id, m.cognito_user_id
FROM user_group_mapping m JOIN user_groups g USING (invite_code);
INSERT INTO group_ingredients (group_id, ingredient_id, added_by, added_at)
SELECT m.group_id, ui.ingredient_id, ui.cognito_user_id, ui.added_at
FROM user_ingredients ui JOIN user_group_members m USING (cognito_user_id);
```

- [ ] Add the table/extension/index/trigger DDL to `schema.sql` (not the legacy-data preflight or backfill), placing the trigger after its existing function definition. Avoid redundant indexes already covered by unique constraints. If pgcrypto is added, add `DROP EXTENSION IF EXISTS pgcrypto CASCADE` to the schema-reset fixture before its function-drop loop.
- [ ] Run migration tests and existing schema tests: `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_user_groups_migration.py tests/test_schema_optimizations.py -v`. Expect all pass. A random migration token collision rolls back the whole migration; retry only after confirming rollback.
- [ ] Commit only the migration, schema, and associated fixture/tests: `feat: add group inventory schema and backfill`.

## Task 2: Models, transaction helpers, personal groups

**Modify:** `api/models/requests.py`, `api/models/responses.py`, `api/db/db_core.py`.
**Create:** `tests/test_models_groups.py`, `tests/test_db_groups.py`.

- [ ] Write model boundary tests for all validation and omitted/null behavior in the contract; DB tests for ensure idempotence, distinct users, create conflict preserving inventory, update/clear description, actor authorization, detail counts, and invite rotation.
- [ ] Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_models_groups.py tests/test_db_groups.py -v`; expect missing models/methods to fail.
- [ ] Implement group request/response models and transaction helpers above. Public entry points: `ensure_user_has_group(user_id)`, `create_group(user_id, name, description)`, `get_user_group(user_id)`, `get_group_detail(actor_user_id, group_id)`, `update_group(actor_user_id, group_id, changes)`, `regenerate_invite_code(actor_user_id, group_id)`. Internal detail helper returns the complete response dict.
- [ ] Repeat tests; expect pass. Add connection lifecycle assertions for success, failure, retry, and no-op; only one pool return per checkout.
- [ ] Commit: `feat: add transactional personal group management`.

## Task 3: Membership transitions and race tests

**Modify:** `api/db/db_core.py`, `tests/test_db_groups.py`.
**Create:** `tests/test_db_groups_concurrency.py`.

- [ ] Write join/leave/kick tests for the full contract, duplicate union preserving destination attribution, invalid code no side effects, same-group no-op, solo leave, self-kick, and failure after copy/before membership update rolling everything back.
- [ ] Add concurrency tests with separate connections/threads, synchronization events, and bounded timeouts. Do not share cursors or reset the class pool while workers run. Test ensure/ensure, join/join for one user, join/rotation, kick/join, and reciprocal kicks. Assert outcomes correspond to a serial ordering, exactly one membership, no failed-operation copies or personal groups, and no deadlocks.
- [ ] Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_db_groups.py tests/test_db_groups_concurrency.py -v`; expect missing transition behavior to fail.
- [ ] Implement `join_group_by_code(user_id, invite_code)`, `leave_group(user_id, group_id, copy_inventory)`, `remove_group_member(actor_user_id, group_id, target_user_id)` with the transaction protocol. No `ON CONFLICT DO NOTHING` on membership moves.
- [ ] Repeat tests; expect pass, including previously failing assertions. Commit: `feat: add atomic group membership transitions`.

## Task 4: Inventory methods and compatibility wrappers

**Modify:** `api/db/db_core.py`, `api/db/sql_queries.py`, `tests/test_db_user_ingredients.py`, `tests/test_bulk_ingredients.py`, `tests/test_ingredient_recommendations.py`.
**Create:** `tests/test_db_group_inventory.py`.

- [ ] Write group inventory tests: shared visibility, isolated groups, nonmember access denied, single-add ancestors/duplicates, actual persisted timestamps, explicit-only bulk add counts, whole-set bulk removal validation, and recommendation parity.
- [ ] Port old test seeds/assertions that directly reference `user_ingredients` to the wrapper API or membership-scoped group SQL. Keep legacy-table SQL only in migration tests and explicit assertions that runtime operations leave it untouched. Search all tests, not only the files listed above: `rg -n 'user_ingredients' tests api`.
- [ ] Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_db_group_inventory.py tests/test_db_user_ingredients.py tests/test_bulk_ingredients.py tests/test_ingredient_recommendations.py -v`; expect missing group behavior to fail.
- [ ] Implement cursor helpers for add/remove/list/bulk/recommendations. Public group inventory methods take `actor_user_id, group_id` plus their existing operation arguments. All authorization and descendant checks happen under the transaction lock. Use INSERT RETURNING for stored timestamps; do not emit the string `now` as a datetime.
- [ ] Make `add_user_ingredient`, `remove_user_ingredient`, `get_user_ingredients`, `add_user_ingredients_bulk`, `remove_user_ingredients_bulk`, and `get_ingredient_recommendations` resolve/ensure membership and delegate to these private helpers within one transaction. Keep their signatures and established return keys (including single-add `ingredient_name`). Reuse one recommendation SQL function with `group_id`; do not retain a second active legacy SQL implementation.
- [ ] Prevalidate missing IDs for bulk add and preserve per-input counts, including repeated IDs. Unexpected SQL errors abort the transaction; never continue issuing statements after an SQL error without a savepoint rollback. Do not report a successful commit when PostgreSQL rolled back an aborted transaction.
- [ ] Add kick/write, join/write, and parent-remove/child-add races to `tests/test_db_groups_concurrency.py`. Under the lock a stale explicit group request fails; a legacy request resolves its current group. Source inventory copy is consistent with that ordering.
- [ ] Repeat targeted tests plus concurrency tests; expect pass. Commit: `feat: share inventory through compatible database wrappers`.

## Task 5: HTTP routes and response contracts

**Create:** `api/routes/groups.py`, `tests/test_api_groups.py`.
**Modify:** `api/main.py`, `api/routes/user_ingredients.py`; existing API inventory tests as needed.

- [ ] Use `test_client_memory_with_app`/`test_client_with_data` and override `dependencies.auth.require_authentication` with `UserInfo`, following existing fixtures. Test every route unauthenticated and as a nonmember, successful response validation, invalid bodies, target missing, create conflict, self-kick, and DELETE bulk routing.
- [ ] Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_api_groups.py -v`; expect 404 for routes not implemented.
- [ ] Implement the endpoint table and register router beside `user_ingredients` in `api/main.py`. Import `UserIngredientAdd`, `UserIngredientBulkAdd`, and `UserIngredientBulkRemove` explicitly. Register `/ingredients/bulk` before `/{ingredient_id}` for DELETE. Pass authenticated actor to DB methods, never take actor identity from request data.
- [ ] Keep existing inventory endpoints calling the now-compatible DB wrappers. Preserve expected HTTP errors through exception handling; do not convert HTTP/domain exceptions into 500s. Apply the same existing inventory errors to group endpoints. Set `Cache-Control: private, no-store` on group responses containing membership/invitation data.
- [ ] Test that membership authorization occurs in the DB method, including direct calls, and that no result exposes another group's invite code. Verify OpenAPI builds successfully through the test app; request/response model import mistakes must fail this gate.
- [ ] Repeat tests and existing inventory API coverage. Commit: `feat: expose authorized group management and inventory routes`.

## Task 6: Recipe search and personal-data isolation

**Modify:** `api/db/db_core.py` (`search_recipes_paginated`), `api/db/sql_queries.py` (both search builders), `api/routes/recipes.py` (documentation only unless tests require a contract change).
**Create:** `tests/test_group_inventory_search.py`.
**Modify tests as needed:** `tests/test_search_sorting.py`, `tests/test_pagination.py`, `tests/test_substitution_integration.py`, `tests/test_combined_search.py`.

- [ ] Write tests for group-shared inventory results through ordinary/authenticated search endpoints and direct DB calls; cover keyset pages, offset/random path, substitutions, new empty user inventory, anonymous inventory rejection, and ordinary anonymous search without group creation.
- [ ] Seed different private tags and ratings for two members; assert shared inventory does not share their private tags/ratings or rating sort. Repeat after join, leave, and kick.
- [ ] Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_group_inventory_search.py -v`; expect old per-user results to fail.
- [ ] Resolve `group_id` inside `Database.search_recipes_paginated` only when `search_params.get('inventory')` is true and `user_id` is present. Reject anonymous inventory at the DB entry as well as the existing route. Ignore any caller-supplied group ID. Bind `query_params['group_id']` from membership, while retaining `query_params['cognito_user_id'] = user_id` for ratings/private tags.
- [ ] Run inventory-filtered search on the same locked connection as resolution. Refactor its query execution into a cursor-taking internal path; ingredient-name lookups and other preparatory DB calls must use that cursor or occur before entering the locked transaction. Do not call nested public group methods under the lock.
- [ ] In **both** `build_search_recipes_paginated_sql` and `build_search_recipes_keyset_sql`, change only the inventory table/key to `group_ingredients` and `group_id`. Preserve interpolated substitution SQL and all user-specific expressions. Both existing builders call `.format(substitution_match=INGREDIENT_SUBSTITUTION_MATCH)` on return; retain that substitution step and its aliases.
- [ ] Repeat new tests and `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/ -k 'search or pagination or substitution or recommendation' -v`; expect pass, not missing-table failures. Commit: `feat: use shared inventory in recipe search`.

## Task 7: API client and usable group page

**Create:** `src/web/groups.html`, `src/web/js/groups.js`, `tests/test_groups.mjs`.
**Modify:** `src/web/js/api.js`, `src/web/js/navigation.js`, `src/web/user-ingredients.html`, `src/web/js/user-ingredients.js`, `src/web/styles.css`, `tests/test_frontend_node.py`, `tests/test_navigation_paths.mjs`.

- [ ] Write Node behavior tests using the repository's existing DOM/fetch stubbing approach for actual named module import, authenticated GET, join/leave/kick refresh, rejected actions with visible errors, busy-state recovery, auth fallback, and safe rendering of names/descriptions. Register the script in `test_frontend_node.py`.
- [ ] Run `node tests/test_groups.mjs`; expect missing module/behavior to fail.
- [ ] Add `CocktailAPI` methods `getMyGroup`, `createGroup`, `updateGroup`, `joinGroup`, `leaveGroup`, `removeGroupMember`, `regenerateInviteCode`, plus the six group inventory counterparts. Use `_request`; all group GETs pass `requiresAuth=true`. Encode the target user ID in the URL with `encodeURIComponent`.
- [ ] Build the page using the existing `common.js` header/footer/auth wiring and `import { api } from './api.js'`. Include group name/description edit, invite copy/rotate, join warning, member list, leave checkbox, and an always-visible status region with `role="status"`. Keep leave controls hidden for solo groups. Existing `getUserInfo().cognitoUserId` identifies self.
- [ ] Render user-controlled values with `textContent`/DOM creation, not interpolated `innerHTML`. Bind controls once; disable mutation controls while a request is pending, restore in `finally`, and reload current group after transitions or stale-access errors. A load failure must show an error and retry control. Login fallback invokes the existing login button after header initialization.
- [ ] Add accessible labels and keyboard-operable controls. On auth loss clear the displayed group/invite state and show the auth prompt. Handle clipboard errors with a selectable code field. Explain before joining that all ingredients in the current shared bar will be copied; before kicking explain that the removed member keeps a copy.
- [ ] Add a `My Bar` groups nav item with `/groups.html`, set existing inventory short label to `Ingredients`, and preserve root-relative links. Check five-item mobile bottom navigation at narrow widths. Use a real `<a href="/groups.html">` for the inventory banner inside the existing auth content; do not duplicate its wrapper. Banner loading failure must not block ingredient loading. Wording: shared bar inventory and **personal** private tags.
- [ ] Add styles matching current components and verify status messages remain visible after leave hides its old section. Run `node tests/test_groups.mjs`, `node tests/test_navigation_paths.mjs`, and `node --check src/web/js/groups.js`. Expect all pass; syntax checks alone do not verify module imports.
- [ ] Commit: `feat: add shared bar management interface`.

## Task 8: Enforce deployment cutover and failure handling

**Modify:** `infrastructure/ansible/playbooks/deploy.yml`, `scripts/deploy-ec2.sh`, `scripts/README.md`.
**Create:** `tests/test_group_inventory_deploy.py`.
**Dependencies:** Tasks 1–7. This task is a release prerequisite, not an optional operational follow-up.

The current playbook syncs frontend directly into the served `{{ app_home }}/web/` directory, runs migrations with the old API container still serving requests, then rebuilds/restarts the API. An old inventory write after backfill would be absent from the group inventory. Replace that behavior in the normal path reached by `scripts/deploy-ec2.sh`; a manual warning alone does not close this finding.

- [ ] Write deployment tests that assert the normal playbook reaches the ordered cutover below, and exercise its failure branches with stubbed migration, Docker, health-check, and publication operations. Use a local Ansible test harness with isolated temporary paths; no SSH, live database, AWS, or real deployment. Assert observable operation order and stopped/running/published state, not only task labels.
- [ ] Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_group_inventory_deploy.py -v`; expect the existing early publication and migrate-before-stop behavior to fail.
- [ ] Stage frontend files **and generated `js/config.js`** in an unserved directory; preserve the currently served frontend until API readiness succeeds. Stage/build the new API image without starting it, and retain the existing container/image for recovery. Ensure queued `Restart API`/`Restart Caddy` handlers cannot start the new release or publish assets ahead of the cutover gate. Build/preflight failure must leave the old API and frontend available.
- [ ] Before stopping writers, verify the selected release contains migration 15, inspect all pending migration filenames, and verify a recoverable pre-cutover backup is available. Prevent overlapping deployments with a host-level deployment lock held through completion/failure handling. Do not assume the group transaction advisory lock protects the old application.
- [ ] Stop and wait for every old API container/process serving this installation to exit before calling `run-migrations.sh`. For the current single API Compose service, explicitly stop `api` and verify it is stopped. An in-flight request must complete or roll back before the backfill starts. Do not use `up --build --force-recreate` as the first writer-stop operation after migration.
- [ ] Run pending migrations only after writer shutdown. Before starting the new API, verify migration 15 is recorded, one membership exists per legacy inventory user, and each legacy ingredient/timestamp/attribution has an exact matching group row. Check both directions for the initial backfill, using set comparisons rather than row counts alone. Perform this legacy parity gate only when migration 15 was pending at the start of this cutover; later group edits intentionally diverge from the retained legacy table. If SQL succeeded but migration bookkeeping failed, halt for the documented recovery instead of replaying the file.
- [ ] Start the staged API only after migration and parity succeed. Require a bounded successful health/readiness check before promoting the staged frontend and its config into the served directory. A frontend request must never see the new group UI while the old API is still running. Preserve the previous frontend until promotion succeeds; report a publication failure rather than claiming release success.
- [ ] Implement explicit failure handling (Ansible `block`/`rescue` or an equivalent tested helper): stop failure prevents migration; migration/parity failure prevents new API startup and frontend publication; API readiness failure prevents frontend publication and stops the failed new API. Leave writers stopped on failures after shutdown and report the failed phase plus recovery instructions. Never unconditionally restart the old API in an `always` block: successful backfill followed by old writes would make retry unsafe. Once the new API has started, assume it may have accepted writes even if readiness later fails, and require the post-write recovery procedure.
- [ ] Cover successful first cutover, a later deployment with migration 15 already applied, build failure, stop failure, SQL failure, bookkeeping/parity failure, readiness failure, and publication failure. Assert no migration occurs while the old API is running, no new API starts after migration verification failure, and no frontend is promoted before readiness. Include a request completed immediately before shutdown in migration integration coverage to prove its inventory is copied. Test that pending restart handlers and the ordinary `scripts/deploy-ec2.sh` entry point cannot bypass the gates.
- [ ] Repeat `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_group_inventory_deploy.py tests/test_run_migrations_script.py tests/test_run_remote_migrations_script.py -v`; expect all pass. Document the normal enforced deployment and recovery commands in `scripts/README.md`, including staged/served paths and how to resume after a failed phase. Commit: `fix: enforce group inventory deployment cutover`.

## Task 9: Integration verification and rollout instructions

**Create:** `docs/user-groups-inventory.md` (API contract, operational cutover, recovery).
**Modify:** implementation/test files only for evidenced failures; update this plan's checkboxes as completed.

- [ ] Run `docker info` and use the project environment. Full backend gate: `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/ -v --tb=short`. PostgreSQL container startup failures block verification; do not label them expected feature failures. Report production-backup-dependent skips separately and run those with an available `PROD_BACKUP_PATH` when validating upgrade compatibility.
- [ ] Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest packages/barcart/tests/ -q` and `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files`. Review formatter changes before committing. Check `git diff --check`.
- [ ] Audit `rg -n 'user_ingredients' api tests`: API filenames/method names and migration/legacy preservation tests are allowed; no runtime SQL may read/write old inventory. Verify group recommendation/search SQL are the only runtime inventory model.
- [ ] Browser acceptance with two accounts: migrated/personal inventory, rename, invite rotation and stale code rejection, join union, shared edits/search/recommendations, independent private tags/ratings, kick with copy, leave with/without copy, auth expiry, and mobile navigation. Confirm stale tabs cannot modify the former group and recover by loading the current group.
- [ ] Document the maintenance-window cutover **implemented and tested in Task 8**: verify backup; stage/build release assets without starting the new app; stop **all** old API writers; apply migration; verify exact backfill parity; start and check new API; publish frontend. Record authenticated legacy/group/search smoke-test results during an authorized deployment. Do not run old and new inventory writers concurrently. Documentation must name the enforced normal deployment entry point, not substitute a manual sequence for its implementation. This task prepares deployment instructions, not authorization to deploy.
- [ ] Use the real runner `infrastructure/scripts/run-migrations.sh` (installed on EC2 as `/opt/cocktaildb/scripts/run-migrations.sh`). The remote helper is `scripts/run-remote-migrations.sh`; set `COCKTAILDB_MIGRATION_FILE=migrations/15_migration_add_user_groups.sql` when explicitly deploying through the Task 8 cutover. The remote migration helper alone does not stop writers and must not be used as a standalone initial group-inventory cutover. Review all pending migrations first: the runner applies all unrecorded files, not only the selected uploaded file. Do not use `--force-init`.
- [ ] Explain runner recovery: schema change and backfill are atomic inside the SQL file, but the runner records `schema_migrations` separately. If marking fails after a successful migration, inspect tables and parity and record the verified filename before rerunning; the non-idempotent migration must not be blindly replayed.
- [ ] Explain rollback: before new writes, restore the pre-cutover backup or return to old app with old table intact. After new writes, simply reverting code loses access to current inventory. Stop writers and use a reviewed reverse export of each current member's group inventory into legacy user rows (or restore backup with explicitly accepted loss). Retained old rows alone are not a safe post-write rollback.
- [ ] Record actual command results, skips/blockers, and browser findings in the PR. Commit only reviewed paths with an appropriate conventional message; no `git add -A` because unrelated `research/` exists in this checkout.

## Completion criteria

Migration preserves every legacy inventory row exactly once in its user's personal group; fresh schemas match upgraded schemas. All runtime inventory access uses group membership, including direct DB callers and both search pagination modes. Transaction tests demonstrate coherent membership/copy behavior and no stale authorization. Existing API clients retain their shapes and semantics. Group UI works with current imports/auth/navigation and reports failures visibly. Required tests and formatting pass. The normal deployment automation enforces and tests writer shutdown before migration, initial backfill verification, API readiness before frontend publication, and safe failure handling; the matching cutover/recovery procedure is documented. Implementation completion requires this evidence; this document review does not claim those tests have run.
