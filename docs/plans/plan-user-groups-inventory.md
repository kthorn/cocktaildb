# Plan: User Groups with Shared Inventory

## Context

Users want to share a home bar inventory with family/housemates, so they can collectively answer "what can we make?" Today, inventory (`user_ingredients`) is strictly per-user. This feature adds groups where members share a **separate** group inventory -- mirroring a real shared bar shelf.

**Why separate inventory (not a union of members' inventories):**
- Removing a personal ingredient shouldn't silently affect the family bar
- Cleaner UX: the group bar is its own entity, stocked independently
- Better performance: queries hit one table with `group_id`, no multi-user UNIONs
- Simpler permissions: "can this user modify the group?" is a clean check

---

## Phase 1: Schema & Group CRUD

### New Database Tables

**Migration file:** `migrations/14_migration_add_user_groups.sql`
**Also update:** `infrastructure/postgres/schema.sql`

```sql
CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_by TEXT NOT NULL,           -- cognito_user_id
    invite_code TEXT NOT NULL UNIQUE,   -- random 8-char code for joining
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    cognito_user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, cognito_user_id)
);

CREATE TABLE group_ingredients (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL,             -- cognito_user_id who added it
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, ingredient_id)
);
```

Plus appropriate indexes, trigger for `updated_at` on `user_groups`.

### Group Management Endpoints

New route file: `api/routes/groups.py`, prefix `/groups`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/groups` | required | Create group (creator = owner) |
| GET | `/groups` | required | List user's groups |
| GET | `/groups/{group_id}` | member | Group details + members |
| PUT | `/groups/{group_id}` | owner/admin | Update name/description |
| DELETE | `/groups/{group_id}` | owner | Delete group |
| POST | `/groups/join` | required | Join via invite code |
| DELETE | `/groups/{group_id}/members/{user_id}` | owner/admin or self | Remove member / leave |
| PUT | `/groups/{group_id}/members/{user_id}/role` | owner | Change member role |
| POST | `/groups/{group_id}/invite-code/regenerate` | owner/admin | New invite code |

### Models

**Requests** (`api/models/requests.py`): `GroupCreate`, `GroupUpdate`, `GroupJoin`, `GroupMemberRoleUpdate`
**Responses** (`api/models/responses.py`): `GroupResponse`, `GroupDetailResponse`, `GroupMemberResponse`, `GroupListResponse`

### Database Methods (`api/db/db_core.py`)

- `create_group(user_id, name, description)` -- insert group + owner membership in transaction, generate invite code via `secrets.token_urlsafe`
- `get_user_groups(user_id)`, `get_group(group_id)`, `get_group_detail(group_id)`
- `get_group_membership(user_id, group_id)` -- for auth checks
- `join_group_by_code(user_id, invite_code)`, `remove_group_member()`, `update_member_role()`
- `delete_group()`, `update_group()`, `regenerate_invite_code()`

Register router in `api/main.py`.

---

## Phase 2: Group Inventory Management

### Endpoints (nested under `/groups/{group_id}/ingredients`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/groups/{group_id}/ingredients` | member | List group inventory |
| POST | `/groups/{group_id}/ingredients` | member | Add ingredient |
| POST | `/groups/{group_id}/ingredients/bulk` | member | Bulk add |
| DELETE | `/groups/{group_id}/ingredients/{ingredient_id}` | member | Remove ingredient |
| DELETE | `/groups/{group_id}/ingredients/bulk` | member | Bulk remove |
| GET | `/groups/{group_id}/ingredients/recommendations` | member | Recommendations |

### Database Methods

Mirror existing `add_user_ingredient` / `remove_user_ingredient` / bulk / list / recommendations methods, adapted for `group_id`.

**Reuse opportunity:** Extract parent-ingredient-auto-add logic from `add_user_ingredient` into a shared helper that both user and group ingredient methods call.

### Models

Reuse `UserIngredientAdd`, `UserIngredientBulkAdd`, `UserIngredientBulkRemove` request models.
Add `GroupIngredientResponse` and `GroupIngredientListResponse` (adds `added_by` field).

---

## Phase 3: Recipe Search Integration

### Modify Existing SQL Builders (`api/db/sql_queries.py`)

The inventory filter in `build_search_recipes_paginated_sql()` (line ~191) and `build_search_recipes_keyset_sql()` currently queries:
```sql
SELECT 1 FROM user_ingredients ui_check WHERE ui_check.cognito_user_id = %(cognito_user_id)s ...
```

When `group_id` is provided, swap to:
```sql
SELECT 1 FROM group_ingredients gi_check WHERE gi_check.group_id = %(group_id)s ...
```

Add `group_id: Optional[int] = None` parameter to both SQL builder functions.

### Modify Recipe Search Route (`api/routes/recipes.py`)

Add `group_id: Optional[int] = Query(None)` to search endpoints. When provided with `inventory=true`:
1. Validate user is a member of the group
2. Pass `group_id` to search params instead of `cognito_user_id`

### Adapt Recommendations SQL

Modify `get_ingredient_recommendations_sql()` to accept a group mode, changing the `user_inventory` CTE to read from `group_ingredients`.

---

## Files to Modify

| File | Change |
|------|--------|
| `migrations/14_migration_add_user_groups.sql` | **New** - migration SQL |
| `infrastructure/postgres/schema.sql` | Add 3 new tables |
| `api/routes/groups.py` | **New** - all group + group inventory endpoints |
| `api/main.py` | Register groups router |
| `api/models/requests.py` | Add group request models |
| `api/models/responses.py` | Add group response models |
| `api/db/db_core.py` | Add ~15 group/membership/inventory methods |
| `api/db/sql_queries.py` | Add `group_id` param to inventory filter SQL builders |
| `api/routes/recipes.py` | Add `group_id` query param to search endpoints |

---

## Verification

1. **Run migration** against dev DB: `./infrastructure/scripts/run-migrations.sh -f migrations/14_migration_add_user_groups.sql -e dev`
2. **Run existing tests** to confirm no regressions: `python -m pytest tests/`
3. **Test group CRUD** via API: create group, list groups, get details, update, delete
4. **Test join flow**: get invite code, join with another user, verify membership
5. **Test group inventory**: add/remove ingredients, verify list, check bulk operations
6. **Test recipe search with group inventory**: create group, add ingredients, search with `inventory=true&group_id=X`, verify correct recipes returned
7. **Test authorization**: non-members can't access group, members can't do owner-only actions
