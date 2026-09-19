# Shared bar inventory

Every user receives one personal bar on first group/inventory access. Inventory belongs to the bar; joining a bar shares it with the other members. Personal ratings and private tags remain private to each user.

All bar members have the same permissions. Any member may rename the bar, regenerate its invitation code, or remove another member. Membership in a bar does not confer Cognito editor/admin privileges.

## Inventory and membership behavior

- Joining copies all ingredients from your current bar into the destination bar and moves your membership there. Ingredients already in the destination keep their original attribution and timestamp. Other source-bar members keep their inventory.
- Joining your current bar is a no-op. Invalid codes do not change membership or create a personal bar. Codes for empty bars cannot be used to rejoin them.
- Leaving requires a choice to copy the shared inventory or start empty. The UI defaults to copying. The last member cannot leave a solo bar; rename it instead.
- Removing another member creates a personal bar for them with a copy of the entire inventory. Self-removal uses the leave action.
- Creating a named bar is supported only before the user has a membership; existing members rename their bar instead.
- Old empty bars persist. There is no background cleanup or ownership role in this release.

The existing `/user-ingredients` endpoints and Python DB methods operate on the caller's current bar. Their response shapes and behavior remain compatible: single-add includes ancestors; bulk-add adds only the specified ingredients; a parent cannot be removed while an unselected descendant remains. The old `user_ingredients` table is retained for migration/recovery and is not read or written by the application.

## API

Paths here omit the deployed `/api/v1` prefix. All endpoints require authentication. Explicit group-ID operations check the caller's membership inside the same transaction as the operation.

| Method | Path | Body |
| --- | --- | --- |
| GET | `/groups/mine` | None; ensures a personal bar |
| POST | `/groups` | `{"name":"Home","description":null}` |
| PUT | `/groups/{id}` | Supplied `name`/`description` fields only |
| POST | `/groups/join` | `{"invite_code":"012345abcdef"}` |
| POST | `/groups/{id}/leave` | `{"copy_inventory":true}` |
| DELETE | `/groups/{id}/members/{user_id}` | None |
| POST | `/groups/{id}/invite-code/regenerate` | None |
| GET, POST | `/groups/{id}/ingredients` | POST: `{"ingredient_id":1}` |
| POST, DELETE | `/groups/{id}/ingredients/bulk` | `{"ingredient_ids":[1,2]}` |
| DELETE | `/groups/{id}/ingredients/{ingredient_id}` | None |
| GET | `/groups/{id}/ingredients/recommendations?limit=20` | None |

Group-object responses contain `id`, `name`, nullable `description`, `invite_code`, `created_at`, `updated_at`, `members` (`cognito_user_id`, `joined_at`), and `member_count`. Create returns 201; the other group-object operations return 200. Inventory response models match the legacy API, including 201 for add/bulk-add. Member removal returns a message with 200.

Names are trimmed and nonblank (100 characters maximum); descriptions have a 500-character maximum. Omitted update fields are unchanged; null description clears it. Invite input is trimmed and lowercased, then validated as exactly 12 hex characters. Leave requires an explicit boolean. Malformed input returns 422, unknown invite/target member 404, nonmember access 403, creating a second bar/solo leave 409, and self-removal 400. Validation logs exclude input values, including invite codes.

## Transactions

`api/db/group_inventory.py` supplies `Database` with group and inventory methods. A transaction-scoped advisory lock (`73421, 1`) serializes membership resolution, authorization, inventory operations, and inventory-filtered searches. Cursor helpers share one connection; no nested pool acquisition occurs inside these transactions. Ordinary searches without inventory filtering do not acquire the lock.

The coarse lock is intentional for the current small deployment. If contention becomes material, replace it with a reviewed finer-grained locking protocol; do not remove it independently from authorization/copy operations.

Search retains the authenticated user ID for personal ratings and tags and resolves the group ID internally. Caller-supplied group IDs cannot select someone else's inventory. Page-number requests use offsets; cursor requests use keyset pagination. Both fetch an extra row to determine whether another page exists.

## Migration and deployment

Migration `15_migration_add_user_groups.sql` creates the new schema and backfills one group for each distinct legacy inventory user inside one transaction. It preserves ingredient IDs, timestamps, and the original user as `added_by`. Null legacy timestamps abort the migration before DDL so historical data is not fabricated. Fresh installs use matching DDL in `infrastructure/postgres/schema.sql`.

Use the normal `scripts/deploy-ec2.sh dev|prod` path documented in [scripts/README.md](../scripts/README.md). The deployment playbook must stage the new assets and use the tested cutover helper. **Do not deploy this feature using the old migrate-while-serving playbook.** Do not call `scripts/run-remote-migrations.sh` alone for the initial cutover: that helper does not stop writers.

The enforced order is:

1. Stage an unserved release, including frontend config; inspect pending migrations and verify a pre-cutover backup.
2. Build the new API image without starting it; preserve the old image.
3. Stop all old API writers and verify they exited.
4. Run pending migrations and verify their recorded state. For the initial group migration, compare membership and inventory in both directions, including timestamps and attribution.
5. Start the new API and require readiness before publishing the staged frontend.

An outer host lifecycle lock excludes overlapping Ansible deployments before any shared file changes; the cutover helper also holds its own process lock. Failed plays retain the outer lock for inspection; follow the documented stale-lock recovery before retrying. The initial legacy/group parity check must not run on ordinary subsequent deployments, because legitimate group edits diverge from the retained legacy table. A failed/uncertain first migration requires recovery before retry rather than blindly replaying SQL. Pending migrations other than 15 also run; review the complete list before cutover.

### Failure and recovery

Build/preflight failure leaves the old API and frontend available. After writer shutdown, SQL/parity failure leaves writers stopped and prevents new API startup/publication. An unready new API is stopped and the frontend is not published. Never automatically restart the old application after migration: it would write only the retained legacy table and invalidate the backfill.

The migration runner records `schema_migrations` separately from the SQL transaction. If SQL committed but recording failed, inspect schema and exact backfill parity, then record the verified filename before retry. If the SQL transaction rolled back, confirm that before clearing any cutover recovery marker. Follow the cutover helper's phase-specific instructions in the scripts README.

Before the new API starts, the untouched legacy rows and preserved old image allow a reviewed recovery to the old release. If old writers resume after a successful migration, the group backfill is stale: either restore the pre-cutover database before retry or perform a reviewed reconciliation while stopped. Merely rerunning an already-recorded migration will not copy those writes.

After the new API starts, assume it may have accepted writes even if a later health check fails. Code rollback alone is unsafe. Stop writers and either repair the new release or perform a reviewed reverse export of each current member's group inventory into their legacy user rows. Restore a backup only with explicit acceptance of losing subsequent writes. Preserve backups and the failed release until recovery is verified.

## Verification

Install `requirements-test.txt` with Python 3.12 or newer; it includes Ansible and YAML support for the local deployment harness. The implementation includes PostgreSQL migration/parity, membership/inventory/concurrency, HTTP authorization, search/privacy, and deployment-order/failure tests, plus Node UI behavior tests. Run the commands in the [implementation plan](plans/2026-09-08-user-groups-inventory.md).

Browser acceptance can use two isolated mock-auth sessions against a disposable local API/database to exercise the complete UI-to-database path. Production Cognito authentication and an actual EC2 cutover still need their normal environment smoke checks during an authorized release; no live deployment is part of this PR.
