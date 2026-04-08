# Plan: User Groups with Shared Inventory

## Context

Users want to share a home bar inventory with family/housemates, so they can collectively answer "what can we make?" Today, inventory (`user_ingredients`) is strictly per-user.

### Core Simplification: Inventory Belongs to Groups, Not Users

Every user belongs to exactly one group. Inventory lives exclusively on groups — there is no separate per-user inventory. When a user signs up or first accesses inventory, they get an auto-created personal group (just them). To share a bar, they either invite others to their group or join someone else's.

**One group per user (for now).** Multi-group support can be added later. This removes the need for group switching, active-group tracking, and simplifies both the API and UI.

This means:
- **One inventory model** — `group_ingredients` replaces `user_ingredients`
- **No dual code paths** — all inventory operations go through the user's group
- **Sharing is just adding a member** — no data copying or syncing
- Existing `/user-ingredients` endpoints become **thin wrappers** that resolve the user's group and delegate to group inventory

### Migration Strategy

Existing `user_ingredients` data gets migrated:
1. Create a personal group for each user who has inventory
2. Copy their `user_ingredients` rows into `group_ingredients`
3. The old `user_ingredients` table is retained but no longer used by the app

Only a handful of users exist, so this is straightforward.

---

## Phase 1: Schema, Migration & Group CRUD

### New Database Tables

**Migration file:** `migrations/14_migration_add_user_groups.sql`
**Also update:** `infrastructure/postgres/schema.sql`

```sql
-- Groups
CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_by TEXT NOT NULL,           -- cognito_user_id
    invite_code TEXT NOT NULL UNIQUE,   -- random 8-char code for joining
    is_personal BOOLEAN NOT NULL DEFAULT FALSE, -- auto-created solo group
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Membership (one group per user enforced by UNIQUE on cognito_user_id)
CREATE TABLE user_group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    cognito_user_id TEXT NOT NULL UNIQUE, -- one group per user
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Group inventory (replaces user_ingredients)
CREATE TABLE group_ingredients (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL,             -- cognito_user_id who added it
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, ingredient_id)
);
```

Plus indexes, `updated_at` trigger on `user_groups`.

The `UNIQUE` constraint on `user_group_members.cognito_user_id` enforces one-group-per-user at the database level. When multi-group support is added later, this changes to `UNIQUE(group_id, cognito_user_id)`.

### Data Migration (in same migration file)

```sql
-- Create a personal group for each user with inventory
INSERT INTO user_groups (name, created_by, invite_code, is_personal)
SELECT DISTINCT
    'My Bar',
    cognito_user_id,
    encode(gen_random_bytes(6), 'hex'),  -- random invite code
    TRUE
FROM user_ingredients;

-- Add each user as owner of their personal group
INSERT INTO user_group_members (group_id, cognito_user_id, role)
SELECT ug.id, ug.created_by, 'owner'
FROM user_groups ug WHERE ug.is_personal = TRUE;

-- Migrate inventory data
INSERT INTO group_ingredients (group_id, ingredient_id, added_by, added_at)
SELECT ug.id, ui.ingredient_id, ui.cognito_user_id, ui.added_at
FROM user_ingredients ui
JOIN user_groups ug ON ug.created_by = ui.cognito_user_id AND ug.is_personal = TRUE;
```

### Group Management Endpoints

New route file: `api/routes/groups.py`, prefix `/groups`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/groups` | required | Create group (creator = owner) |
| GET | `/groups/mine` | required | Get user's current group + members |
| PUT | `/groups/{group_id}` | owner/admin | Update name/description |
| DELETE | `/groups/{group_id}` | owner | Delete group (reverts members to personal groups) |
| POST | `/groups/join` | required | Join via invite code (leaves current group) |
| DELETE | `/groups/{group_id}/members/{user_id}` | owner/admin or self | Remove member / leave (reverts to personal group) |
| PUT | `/groups/{group_id}/members/{user_id}/role` | owner | Change member role |
| POST | `/groups/{group_id}/invite-code/regenerate` | owner/admin | New invite code |

### Auto-Creation of Personal Group

When a user first interacts with inventory (or groups) and has no group yet, auto-create a personal group for them. This handles:
- New users who sign up after the migration
- Existing users who never added any ingredients

Implemented as a helper: `ensure_user_has_group(user_id)` in `db_core.py`, called from the groups and inventory routes.

### Merging Inventories on Group Join

When a user joins a group and their current group already has ingredients, **merge (union)** those ingredients into the joined group. Duplicates are skipped. This way no one loses ingredients when consolidating into a shared bar.

Implemented in `join_group_by_code()`:
```sql
INSERT INTO group_ingredients (group_id, ingredient_id, added_by, added_at)
SELECT %(new_group_id)s, gi.ingredient_id, gi.added_by, gi.added_at
FROM group_ingredients gi
JOIN user_group_members ugm ON gi.group_id = ugm.group_id
WHERE ugm.cognito_user_id = %(user_id)s
ON CONFLICT (group_id, ingredient_id) DO NOTHING;
```

Then move the user's membership to the new group. Their old personal group is kept (in case they leave later and need to revert).

### Leaving a Group / Being Removed

When a user leaves a shared group (or is removed), they revert to their personal group:
- If their personal group still exists, re-join it
- If not, auto-create a new personal group
- Their ingredients stay in the shared group (they contributed them)

### Models

**Requests** (`api/models/requests.py`): `GroupCreate`, `GroupUpdate`, `GroupJoin`, `GroupMemberRoleUpdate`
**Responses** (`api/models/responses.py`): `GroupResponse`, `GroupDetailResponse`, `GroupMemberResponse`

### Database Methods (`api/db/db_core.py`)

- `ensure_user_has_group(user_id)` — idempotent; creates personal group if none exists, returns group
- `create_group(user_id, name, description)` — insert group + owner membership in transaction
- `get_user_group(user_id)` — returns the user's single group
- `get_group_detail(group_id)` — group info with members list
- `get_group_membership(user_id, group_id)` — for auth checks
- `join_group_by_code(user_id, invite_code)` — merge inventory, move membership
- `leave_group(user_id, group_id)` — revert to personal group
- `remove_group_member(group_id, target_user_id)` — kick member, revert them
- `update_member_role()`, `delete_group()`, `update_group()`, `regenerate_invite_code()`

---

## Phase 2: Group Inventory (Replacing User Inventory)

### New Endpoints (nested under `/groups/{group_id}/ingredients`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/groups/{group_id}/ingredients` | member | List group inventory |
| POST | `/groups/{group_id}/ingredients` | member | Add ingredient |
| POST | `/groups/{group_id}/ingredients/bulk` | member | Bulk add |
| DELETE | `/groups/{group_id}/ingredients/{ingredient_id}` | member | Remove ingredient |
| DELETE | `/groups/{group_id}/ingredients/bulk` | member | Bulk remove |
| GET | `/groups/{group_id}/ingredients/recommendations` | member | Recommendations |

### Repoint Existing `/user-ingredients` Endpoints

Keep `api/routes/user_ingredients.py` as **backward-compatible wrappers**:
- Each endpoint calls `ensure_user_has_group(user_id)` to get the user's group
- Delegates to the same DB methods as the group inventory endpoints
- Frontend continues to work without changes initially

### Database Methods

Adapt existing `add_user_ingredient` / `remove_user_ingredient` / bulk / list / recommendations methods to operate on `group_ingredients` with a `group_id` parameter. The old `user_id`-based methods become thin wrappers that resolve the user's group first.

---

## Phase 3: Recipe Search Integration

### Modify SQL Builders (`api/db/sql_queries.py`)

The inventory filter currently queries:
```sql
SELECT 1 FROM user_ingredients ui_check
WHERE ui_check.cognito_user_id = %(cognito_user_id)s ...
```

Change to query `group_ingredients` with the user's group:
```sql
SELECT 1 FROM group_ingredients gi_check
WHERE gi_check.group_id = %(group_id)s ...
```

### Modify Recipe Search Route (`api/routes/recipes.py`)

- Resolve user's group via `get_user_group(user_id)`
- Pass `group_id` instead of `cognito_user_id` to search params

### Adapt Recommendations SQL

Change `get_ingredient_recommendations_sql()` `user_inventory` CTE to read from `group_ingredients` keyed on `group_id`.

---

## Phase 4: Frontend

### New Files

| File | Purpose |
|------|---------|
| `src/web/groups.html` | Groups management page |
| `src/web/js/groups.js` | `GroupsManager` class |

### Navigation

Add to `NAV_CONFIG.primary` in `src/web/js/navigation.js`:
```javascript
{
    id: 'groups',
    label: 'My Bar',
    href: 'groups.html',
    icon: 'users',  // or similar
    authRequired: true
}
```

### API Client (`src/web/js/api.js`)

Add methods:
- `getMyGroup()` — GET `/groups/mine`
- `createGroup(data)` — POST `/groups`
- `updateGroup(groupId, data)` — PUT `/groups/{group_id}`
- `joinGroup(inviteCode)` — POST `/groups/join`
- `leaveGroup(groupId)` — DELETE `/groups/{group_id}/members/{userId}`
- `removeMember(groupId, userId)` — DELETE `/groups/{group_id}/members/{userId}`
- `updateMemberRole(groupId, userId, role)` — PUT `/groups/{group_id}/members/{userId}/role`
- `regenerateInviteCode(groupId)` — POST `/groups/{group_id}/invite-code/regenerate`

### Groups Page UI (`groups.html` + `groups.js`)

**Sections:**

1. **Group Info Header** — group name, description, member count
   - Edit button (owner/admin only) to rename group
   - Shows "Personal" badge if `is_personal`

2. **Invite Code Card** — shown to owner/admin
   - Display current invite code with copy-to-clipboard button
   - "Regenerate" button
   - Short explanation: "Share this code with someone to invite them to your bar"

3. **Join a Group** — text input + "Join" button
   - Enter invite code to join another group
   - Warning: "Joining will merge your current inventory into the new group"

4. **Members List** — shows all group members
   - Each member: name, role badge (owner/admin/member)
   - Owner can: change roles, remove members
   - Self: "Leave group" button (not shown to owner, or shown with ownership transfer prompt)

5. **Auth-required fallback** — login prompt for unauthenticated users

### Changes to Existing Inventory Page (`src/web/user-ingredients.html`)

Add a small banner/link at top: "You're viewing inventory for **{group name}**" with a link to the groups page. This makes it clear whose bar you're looking at, especially after joining a shared group.

---

## Files to Modify

| File | Change |
|------|--------|
| `migrations/14_migration_add_user_groups.sql` | **New** — schema + data migration |
| `infrastructure/postgres/schema.sql` | Add 3 new tables |
| `api/routes/groups.py` | **New** — group CRUD + group inventory endpoints |
| `api/main.py` | Register groups router |
| `api/models/requests.py` | Add group request models |
| `api/models/responses.py` | Add group response models |
| `api/db/db_core.py` | Add group methods, repoint inventory methods to `group_ingredients` |
| `api/db/sql_queries.py` | Change inventory filter to use `group_ingredients` + `group_id` |
| `api/routes/recipes.py` | Resolve user's group for inventory search |
| `api/routes/user_ingredients.py` | Repoint to group inventory (backward compat wrappers) |
| `src/web/groups.html` | **New** — groups management page |
| `src/web/js/groups.js` | **New** — `GroupsManager` class |
| `src/web/js/api.js` | Add group API methods |
| `src/web/js/navigation.js` | Add "My Bar" nav item |
| `src/web/user-ingredients.html` | Add group name banner |

---

## Verification

1. **Run migration** against dev DB: `./infrastructure/scripts/run-migrations.sh -f migrations/14_migration_add_user_groups.sql -e dev`
2. **Verify migration**: check that existing users have personal groups and their ingredients migrated
3. **Run existing tests** to confirm no regressions: `python -m pytest tests/`
4. **Test backward compat**: existing `/user-ingredients` endpoints still work, now backed by `group_ingredients`
5. **Test group CRUD**: create group, get details, update, delete
6. **Test join flow**: get invite code, join with another user, verify inventory merged
7. **Test leave flow**: leave shared group, verify reverted to personal group
8. **Test recipe search**: `inventory=true` uses group's inventory
9. **Test authorization**: non-members can't access group, members can't do owner-only actions
10. **Test frontend**: groups page renders, invite/join works, inventory page shows group name
