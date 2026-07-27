# Plan: User Groups with Shared Inventory

**Status:** Refined

## Context

Users want to share a home bar inventory with family/housemates, so they can collectively answer "what can we make?" Today, inventory (`user_ingredients`) is strictly per-user.

### Core Simplification: Inventory Belongs to Groups, Not Users

Every user belongs to exactly one group. Inventory lives exclusively on groups — there is no separate per-user inventory. When a user signs up or first accesses inventory, they get an auto-created personal group (just them). To share a bar, they either invite others to their group or join someone else's.

**Note:** `cognito_user_id` refers to the Cognito "sub" claim (UUID string) that uniquely identifies each user.

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
-- Enable pgcrypto for gen_random_bytes()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Groups
CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    invite_code TEXT NOT NULL UNIQUE,   -- random 12-char hex code for joining
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Membership (one group per user enforced by UNIQUE on cognito_user_id)
CREATE TABLE user_group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    cognito_user_id TEXT NOT NULL UNIQUE, -- one group per user
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

-- Indexes for performance
CREATE INDEX idx_user_groups_invite_code ON user_groups(invite_code);
CREATE INDEX idx_user_group_members_group_id ON user_group_members(group_id);
CREATE INDEX idx_user_group_members_cognito_user_id ON user_group_members(cognito_user_id);
CREATE INDEX idx_group_ingredients_group_id ON group_ingredients(group_id);
CREATE INDEX idx_group_ingredients_ingredient_id ON group_ingredients(ingredient_id);

-- updated_at trigger for user_groups
-- Note: update_updated_at_column() already exists in the base schema (infrastructure/postgres/schema.sql:169-175).
-- CREATE OR REPLACE is safe — it will overwrite the existing definition with an identical function.
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_user_groups_updated_at
    BEFORE UPDATE ON user_groups
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

The `UNIQUE` constraint on `user_group_members.cognito_user_id` enforces one-group-per-user at the database level. When multi-group support is added later, this changes to `UNIQUE(group_id, cognito_user_id)`.

### Data Migration (in same migration file)

```sql
-- Create a personal group for each user with inventory
-- generate 12-char hex invite codes (encode(gen_random_bytes(6), 'hex') = 12 hex chars)
CREATE TEMP TABLE user_group_mapping AS
SELECT DISTINCT cognito_user_id, encode(gen_random_bytes(6), 'hex') as invite_code
FROM user_ingredients;

INSERT INTO user_groups (name, invite_code)
SELECT 'My Bar', invite_code FROM user_group_mapping;

-- Add each user as member of their personal group
INSERT INTO user_group_members (group_id, cognito_user_id)
SELECT ug.id, m.cognito_user_id
FROM user_groups ug
JOIN user_group_mapping m ON ug.invite_code = m.invite_code;

-- Migrate inventory data
INSERT INTO group_ingredients (group_id, ingredient_id, added_by, added_at)
SELECT ug.id, ui.ingredient_id, ui.cognito_user_id, ui.added_at
FROM user_ingredients ui
JOIN user_group_members ugm ON ugm.cognito_user_id = ui.cognito_user_id
JOIN user_groups ug ON ug.id = ugm.group_id;

DROP TABLE user_group_mapping;
```

### Group Management Endpoints

New route file: `api/routes/groups.py`, prefix `/groups`

**Authorization:** All endpoints with `{group_id}` in the path must verify the authenticated user is a member of that group before proceeding. Use `get_group_membership(user_id, group_id)` to check.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/groups` | required | Create group (user becomes first member) |
| GET | `/groups/mine` | required | Get user's current group + members |
| PUT | `/groups/{group_id}` | member | Update name/description |
| POST | `/groups/join` | required | Join via invite code (leaves current group). Returns 404 if code invalid. |
| DELETE | `/groups/{group_id}/members/{user_id}` | member | Remove member from group (kick). Leaving uses the endpoint below. |
| POST | `/groups/{group_id}/leave` | member | Leave group. Request body: `{ "copy_inventory": true/false }`. Uses POST with body instead of DELETE+query params for clarity. |
| POST | `/groups/{group_id}/invite-code/regenerate` | member | New invite code |

Note: All members have equal permissions. Any member can update group info, regenerate invite codes, or remove other members. **Known limitation (Phase 1):** There is no owner or admin role. This means any member can remove any other member, including the group's original creator. This is acceptable for Phase 1 since all members are trusted (family/housemates) and groups are small. A roles/permissions model can be added in a future phase.

### Auto-Creation of Group

When a user first interacts with inventory (or groups) and has no group yet, auto-create a group for them. This handles:
- New users who sign up after the migration
- Existing users who never added any ingredients

Implemented as a helper: `ensure_user_has_group(user_id)` in `db_core.py`, called from the groups and inventory routes.

**Race condition handling:** Two simultaneous requests for a user with no group could both try to insert into `user_group_members`, hitting the `UNIQUE` constraint on `cognito_user_id`. The implementation must catch this `IntegrityError` and re-query for the group (which now exists) rather than failing. Pattern:

```python
try:
    # insert group + membership in transaction
except psycopg2.IntegrityError:
    # Another request created the group first — re-query and return it
    return get_user_group(user_id)
```

### Merging Inventories on Group Join

When a user joins a group and their current group already has ingredients, **merge (union)** those ingredients into the joined group. Duplicates are skipped. This way no one loses ingredients when consolidating into a shared bar.

**Race condition handling:** The `join_group_by_code()` operation should use a database transaction to ensure atomicity. If two users try to join the same group simultaneously, PostgreSQL's UNIQUE constraints and transaction isolation will prevent duplicate memberships.

Implemented in `join_group_by_code()`:
```sql
INSERT INTO group_ingredients (group_id, ingredient_id, added_by, added_at)
SELECT %(new_group_id)s, gi.ingredient_id, gi.added_by, gi.added_at
FROM group_ingredients gi
JOIN user_group_members ugm ON gi.group_id = ugm.group_id
WHERE ugm.cognito_user_id = %(user_id)s
ON CONFLICT (group_id, ingredient_id) DO NOTHING;
```

Then move the user's membership to the new group. Their old group is kept (in case they leave later and need to copy inventory back). **Accepted behavior:** when all members leave a group, the group row and its remaining data persist as an orphan. There is no cleanup job in Phase 1. In practice this is fine because the only way a group becomes empty is when the last member leaves (and they've already been prompted to copy inventory). A future phase may add a cascading cleanup.

### Leaving a Group / Being Removed

When a user leaves a shared group (or is removed), they create a new group:
- Create a new group via `ensure_user_has_group()`
- **Prompt to copy inventory:** "Copy ingredients from [group name]?"
  - Yes → copy all ingredients from the old group to the new group (skip duplicates)
  - No → start fresh with empty group
- Their membership is removed from the old group

**Frontend:** The "Leave group" button is hidden if the group has only one member. Users are always in a group, so there's no need to leave a solo group.

### Models

**Requests** (`api/models/requests.py`): `GroupCreate`, `GroupUpdate`, `GroupJoin`, `GroupLeave` (with `copy_inventory: bool`)
**Responses** (`api/models/responses.py`): `GroupResponse`, `GroupDetailResponse`, `GroupMemberResponse`

### Database Methods (`api/db/db_core.py`)

- `ensure_user_has_group(user_id)` — idempotent; creates personal group if none exists, returns group
- `create_group(user_id, name, description)` — insert group + membership in a single database transaction (same pattern as `create_recipe` in `db_core.py`: get connection, begin, insert group, insert membership, commit)
- `get_user_group(user_id)` — returns the user's single group
- `get_group_detail(group_id)` — group info with members list
- `get_group_membership(user_id, group_id)` — for auth checks
- `join_group_by_code(user_id, invite_code)` — merge inventory, move membership
- `leave_group(user_id, group_id, copy_inventory)` — use POST `/groups/{group_id}/leave` with body `{ "copy_inventory": true/false }`; creates new group, optionally copies inventory, removes from old group. Must run in a transaction.
- `remove_group_member(group_id, target_user_id)` — kick member, revert them
- `update_group()`, `regenerate_invite_code()`

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
- **All** existing endpoints must be repointed, including:
  - `POST /user-ingredients` → add to group inventory
  - `GET /user-ingredients` → list group inventory
  - `DELETE /user-ingredients/{ingredient_id}` → remove from group inventory
  - `POST /user-ingredients/bulk` → bulk add to group inventory
  - `DELETE /user-ingredients/bulk` → bulk remove from group inventory
  - `GET /user-ingredients/recommendations` → group-based recommendations

### Database Methods

Adapt existing `add_user_ingredient` / `remove_user_ingredient` / bulk / list / recommendations methods to operate on `group_ingredients` with a `group_id` parameter. The old `user_id`-based methods become thin wrappers that resolve the user's group first.

**Parent ingredient auto-addition:** The current `add_user_ingredient()` (`db_core.py:2154-2244`) automatically adds all parent ingredients from the hierarchy path when a child ingredient is added (e.g., adding "Wray & Nephew" also adds "Rum"). The new `add_group_ingredient()` must replicate this behavior using the same path-walking logic, inserting parent ingredients into `group_ingredients` with `ON CONFLICT DO NOTHING`.

**Parent-child removal constraint:** The current `remove_user_ingredient()` (`db_core.py:2246-2309`) prevents removing a parent ingredient if child ingredients still exist in the user's inventory. The new `remove_group_ingredient()` must enforce the same constraint against the group's inventory — check for children in `group_ingredients` (via the ingredient path) and reject the removal with a descriptive error message.

**Recommendations backward compatibility:** The existing `GET /user-ingredients/recommendations` endpoint must also be repointed to resolve the user's group and delegate to the group-based recommendation method, same as the other `/user-ingredients` endpoints.

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

**Rename conflict resolution:** The existing "My Ingredients" nav item (`id: 'my-ingredients'`) already uses `shortLabel: 'My Bar'` and points to `user-ingredients.html`. To avoid confusion:

1. Rename the existing "My Ingredients" item's `shortLabel` from `'My Bar'` to `'Ingredients'`
2. Rename the existing item's `label` from `'My Ingredients'` to `'My Ingredients'` (keep as-is)
3. Add a new `"My Bar"` nav item for the groups page

Update `NAV_CONFIG.primary` in `src/web/js/navigation.js`:
```javascript
// Existing item — update shortLabel
{
    id: 'my-ingredients',
    label: 'My Ingredients',
    shortLabel: 'Ingredients',   // Changed from 'My Bar' to avoid conflict
    href: 'user-ingredients.html',
    icon: '🍸',
    mobileBottom: true,
    mobileMenu: true,
    desktop: true,
    authRequired: true,
    adminOnly: false
},
// New item
{
    id: 'groups',
    label: 'My Bar',
    href: 'groups.html',
    icon: '👥',
    mobileBottom: true,
    mobileMenu: true,
    desktop: true,
    authRequired: true,
    adminOnly: false
}
```
Note: The project uses text-based icons (e.g., "+") rather than an icon library.

### API Client (`src/web/js/api.js`)

Add methods:
- `getMyGroup()` — GET `/groups/mine`
- `createGroup(data)` — POST `/groups`
- `updateGroup(groupId, data)` — PUT `/groups/{group_id}`
- `joinGroup(inviteCode)` — POST `/groups/join`
- `leaveGroup(groupId, copyInventory)` — POST `/groups/{group_id}/leave` with body `{ "copy_inventory": true/false }`
- `removeMember(groupId, userId)` — DELETE `/groups/{group_id}/members/{userId}`
- `regenerateInviteCode(groupId)` — POST `/groups/{group_id}/invite-code/regenerate`

### Groups Page UI (`groups.html` + `groups.js`)

**Sections:**

1. **Group Info Header** — group name, description, member count
   - Edit button to rename group

2. **Invite Code Card** — display current invite code
   - Copy-to-clipboard button
   - "Regenerate" button
   - Short explanation: "Share this code with someone to invite them to your bar"

3. **Join a Group** — text input + "Join" button
   - Enter invite code to join another group
   - Warning: "Joining will merge your current inventory into the new group"

4. **Members List** — shows all group members
   - Each member: name
   - "Remove" button for each member (including self, labeled "Leave")
   - Leave button hidden if group has only one member

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
| `tests/test_db_groups.py` | **New** — tests for group CRUD, join/leave, inventory merge |

---

## Verification

1. **Run migration** against dev DB: Copy migration file to server and run `./scripts/run-migrations.sh dev`
2. **Verify migration**: check that existing users have personal groups and their ingredients migrated
3. **Run existing tests** to confirm no regressions: `python -m pytest tests/`
4. **Test backward compat**: existing `/user-ingredients` endpoints still work, now backed by `group_ingredients`
5. **Test group CRUD**: create group, get details, update
6. **Test join flow**: get invite code, join with another user, verify inventory merged
7. **Test leave flow**: leave shared group, verify new group created, verify inventory copied (or not) based on choice
8. **Test recipe search**: `inventory=true` uses group's inventory
9. **Test authorization**: non-members can't access group
10. **Test frontend**: groups page renders, invite/join works, inventory page shows group name
