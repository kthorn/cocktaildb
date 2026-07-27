# User Groups with Shared Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable users to share a home bar inventory with family/housemates by moving inventory from per-user `user_ingredients` to group-based `group_ingredients`, with group CRUD, join/leave flows, and backward-compatible API wrappers.

**Architecture:** Every user belongs to exactly one group. Inventory lives on groups. Old `/user-ingredients` endpoints become thin wrappers that resolve the user's group and delegate. New `/groups` endpoints provide group management and group-scoped inventory. The frontend gets a new "My Bar" groups page while the existing "My Ingredients" page shows a group-name banner.

**Tech Stack:** Python/FastAPI (backend), PostgreSQL (database), Vanilla JS (frontend), pytest (tests)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `migrations/14_migration_add_user_groups.sql` | Schema migration + data migration |
| `infrastructure/postgres/schema.sql` | Add 3 new tables + indexes + trigger |
| `api/db/db_core.py` | Group CRUD, group inventory, and user_ingredient wrapper methods |
| `api/db/sql_queries.py` | Update inventory filter and recommendations to use `group_ingredients` |
| `api/routes/groups.py` | **New** — Group CRUD + group inventory endpoints |
| `api/routes/user_ingredients.py` | Repoint to group inventory (backward-compat wrappers) |
| `api/routes/recipes.py` | Resolve user's group for inventory search |
| `api/models/requests.py` | Add group request models |
| `api/models/responses.py` | Add group response models |
| `api/main.py` | Register groups router |
| `src/web/groups.html` | **New** — Groups management page |
| `src/web/js/groups.js` | **New** — `GroupsManager` class |
| `src/web/js/api.js` | Add group API methods |
| `src/web/js/navigation.js` | Update nav items |
| `src/web/user-ingredients.html` | Add group name banner |
| `tests/test_db_groups.py` | **New** — Group and group inventory tests |
| `tests/test_api_groups.py` | **New** — Group route integration tests |

---

## Task 1: Schema Migration — Create Tables

**Files:**
- Create: `migrations/14_migration_add_user_groups.sql`
- Modify: `infrastructure/postgres/schema.sql`

- [ ] **Step 1: Create the migration file**

Create `migrations/14_migration_add_user_groups.sql`:

```sql
-- Migration: Add user groups, memberships, and group ingredients tables
-- This enables shared inventory between users in the same group.

-- Enable pgcrypto for gen_random_bytes()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Groups
CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    invite_code TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Membership (one group per user enforced by UNIQUE on cognito_user_id)
CREATE TABLE user_group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    cognito_user_id TEXT NOT NULL UNIQUE,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Group inventory (replaces user_ingredients)
CREATE TABLE group_ingredients (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL,
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
CREATE TRIGGER update_user_groups_updated_at
    BEFORE UPDATE ON user_groups
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Data migration: Create personal group for each user with inventory
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

- [ ] **Step 2: Update `infrastructure/postgres/schema.sql`**

Add after the `user_ingredients` table definition (after line 94) and before `analytics_refresh_state` (line 96):

```sql
CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    invite_code TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    cognito_user_id TEXT NOT NULL UNIQUE,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE group_ingredients (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, ingredient_id)
);
```

Add indexes after existing `idx_user_ingredients_ingredient_id` (around line 125):

```sql
CREATE INDEX idx_user_groups_invite_code ON user_groups(invite_code);
CREATE INDEX idx_user_group_members_group_id ON user_group_members(group_id);
CREATE INDEX idx_user_group_members_cognito_user_id ON user_group_members(cognito_user_id);
CREATE INDEX idx_group_ingredients_group_id ON group_ingredients(group_id);
CREATE INDEX idx_group_ingredients_ingredient_id ON group_ingredients(ingredient_id);
```

Add trigger after existing `update_ingredients_updated_at` trigger (after line 255):

```sql
CREATE TRIGGER update_user_groups_updated_at
    BEFORE UPDATE ON user_groups
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

- [ ] **Step 3: Verify schema changes by running existing tests**

Run: `python -m pytest tests/test_db_user_ingredients.py -v --tb=short`

Expected: All existing user ingredient tests still PASS (the new tables don't affect existing functionality since user_ingredients table still exists).

- [ ] **Step 4: Commit**

```bash
git add migrations/14_migration_add_user_groups.sql infrastructure/postgres/schema.sql
git commit -m "feat: add user_groups, user_group_members, and group_ingredients tables"
```

---

## Task 2: Group Request and Response Models

**Files:**
- Modify: `api/models/requests.py`
- Modify: `api/models/responses.py`

- [ ] **Step 1: Add group request models to `api/models/requests.py`**

Append after `UserIngredientBulkRemove` class (after line 247):

```python
class GroupCreate(BaseModel):
    """Request model for creating a group"""
    name: str = Field(..., description="Group name", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Group description", max_length=500)


class GroupUpdate(BaseModel):
    """Request model for updating a group"""
    name: Optional[str] = Field(None, description="Group name", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Group description", max_length=500)


class GroupJoin(BaseModel):
    """Request model for joining a group via invite code"""
    invite_code: str = Field(..., description="Invite code to join the group", min_length=1)


class GroupLeave(BaseModel):
    """Request model for leaving a group"""
    copy_inventory: bool = Field(False, description="Whether to copy group inventory to new personal group")
```

Add `Optional` to the existing imports at the top of `requests.py` if not already present. Check the imports — `Optional` is used but verify.

- [ ] **Step 2: Add group response models to `api/models/responses.py`**

Append after `IngredientRecommendationListResponse` class (after line 335):

```python
class GroupMemberResponse(BaseModel):
    """Response model for a group member"""
    cognito_user_id: str = Field(..., description="User ID of the group member")
    username: Optional[str] = Field(None, description="Username (if available)")
    joined_at: datetime = Field(..., description="When the user joined the group")

    class Config:
        from_attributes = True


class GroupResponse(BaseModel):
    """Response model for a group"""
    id: int = Field(..., description="Group ID")
    name: str = Field(..., description="Group name")
    description: Optional[str] = Field(None, description="Group description")
    invite_code: str = Field(..., description="Invite code for joining the group")
    created_at: datetime = Field(..., description="When the group was created")
    updated_at: datetime = Field(..., description="When the group was last updated")

    class Config:
        from_attributes = True


class GroupDetailResponse(BaseModel):
    """Response model for a group with members"""
    id: int = Field(..., description="Group ID")
    name: str = Field(..., description="Group name")
    description: Optional[str] = Field(None, description="Group description")
    invite_code: str = Field(..., description="Invite code for joining the group")
    members: List[GroupMemberResponse] = Field(default=[], description="List of group members")
    member_count: int = Field(..., description="Number of members in the group")
    created_at: datetime = Field(..., description="When the group was created")
    updated_at: datetime = Field(..., description="When the group was last updated")

    class Config:
        from_attributes = True
```

Verify `List` and `datetime` are already imported in `responses.py`.

- [ ] **Step 3: Verify models load correctly**

Run: `python -c "from api.models.requests import GroupCreate, GroupUpdate, GroupJoin, GroupLeave; from api.models.responses import GroupResponse, GroupDetailResponse, GroupMemberResponse; print('Models loaded OK')"`

Workdir: `/home/kurtt/cocktaildb/api`

Expected: `Models loaded OK`

- [ ] **Step 4: Commit**

```bash
git add api/models/requests.py api/models/responses.py
git commit -m "feat: add group request and response models"
```

---

## Task 3: Group Database Methods — CRUD and Helper Methods

**Files:**
- Modify: `api/db/db_core.py`
- Create: `tests/test_db_groups.py` (start)

- [ ] **Step 1: Write failing tests for `ensure_user_has_group`**

Create `tests/test_db_groups.py`:

```python
"""Tests for group CRUD, membership, and group inventory database methods"""

import pytest
from psycopg2 import IntegrityError


class TestGroupCRUD:
    """Tests for group creation, retrieval, and membership"""

    def test_ensure_user_has_group_creates_new_group(self, db_instance):
        """ensure_user_has_group creates a group for a user who doesn't have one"""
        group = db_instance.ensure_user_has_group("user-1")
        assert group is not None
        assert group["name"] == "My Bar"
        assert group["invite_code"] is not None
        assert len(group["invite_code"]) == 12

    def test_ensure_user_has_group_idempotent(self, db_instance):
        """ensure_user_has_group returns existing group if user already has one"""
        group1 = db_instance.ensure_user_has_group("user-1")
        group2 = db_instance.ensure_user_has_group("user-1")
        assert group1["id"] == group2["id"]

    def test_ensure_user_has_group_different_users_different_groups(self, db_instance):
        """Different users get different groups"""
        group1 = db_instance.ensure_user_has_group("user-1")
        group2 = db_instance.ensure_user_has_group("user-2")
        assert group1["id"] != group2["id"]

    def test_create_group_with_custom_name(self, db_instance):
        """create_group creates a group with a custom name"""
        group = db_instance.create_group("user-1", "Family Bar", "Our shared bar")
        assert group["name"] == "Family Bar"
        assert group["description"] == "Our shared bar"
        assert group["invite_code"] is not None

    def test_create_group_adds_creator_as_member(self, db_instance):
        """create_group makes the creator a member"""
        group = db_instance.create_group("user-1", "Family Bar")
        members = db_instance.get_group_members(group["id"])
        assert len(members) == 1
        assert members[0]["cognito_user_id"] == "user-1"

    def test_get_user_group_returns_user_group(self, db_instance):
        """get_user_group returns the group a user belongs to"""
        group = db_instance.ensure_user_has_group("user-1")
        result = db_instance.get_user_group("user-1")
        assert result is not None
        assert result["id"] == group["id"]

    def test_get_user_group_returns_none_for_user_without_group(self, db_instance):
        """get_user_group returns None if user has no group"""
        result = db_instance.get_user_group("nonexistent-user")
        assert result is None

    def test_get_group_detail_returns_group_with_members(self, db_instance):
        """get_group_detail returns group info with member list"""
        group = db_instance.ensure_user_has_group("user-1")
        detail = db_instance.get_group_detail(group["id"])
        assert detail["id"] == group["id"]
        assert detail["name"] == "My Bar"
        assert len(detail["members"]) == 1
        assert detail["member_count"] == 1

    def test_get_group_membership_returns_true_for_member(self, db_instance):
        """get_group_membership returns truthy record for a group member"""
        group = db_instance.ensure_user_has_group("user-1")
        membership = db_instance.get_group_membership("user-1", group["id"])
        assert membership is not None
        assert membership["cognito_user_id"] == "user-1"

    def test_get_group_membership_returns_none_for_non_member(self, db_instance):
        """get_group_membership returns None for a non-member"""
        group = db_instance.ensure_user_has_group("user-1")
        membership = db_instance.get_group_membership("user-2", group["id"])
        assert membership is None

    def test_update_group_name(self, db_instance):
        """update_group changes group name"""
        group = db_instance.ensure_user_has_group("user-1")
        updated = db_instance.update_group(group["id"], name="Updated Name")
        assert updated["name"] == "Updated Name"

    def test_update_group_description(self, db_instance):
        """update_group changes group description"""
        group = db_instance.ensure_user_has_group("user-1")
        updated = db_instance.update_group(group["id"], description="New description")
        assert updated["description"] == "New description"

    def test_regenerate_invite_code(self, db_instance):
        """regenerate_invite_code creates a new invite code"""
        group = db_instance.ensure_user_has_group("user-1")
        old_code = group["invite_code"]
        updated = db_instance.regenerate_invite_code(group["id"])
        assert updated["invite_code"] != old_code
        assert len(updated["invite_code"]) == 12
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_db_groups.py::TestGroupCRUD -v --tb=short`

Expected: FAIL with `AttributeError: 'Database' object has no attribute 'ensure_user_has_group'`

- [ ] **Step 3: Implement group CRUD methods in `api/db/db_core.py`**

Add the following methods to the `Database` class in `api/db/db_core.py`. Add them after the user ingredient methods (after line 2662, the `# --- End User Ingredient Tracking Methods ---` comment). First, add `import psycopg2` at the top if not already there (it is), and add the `IntegrityError` import.

At the top of `db_core.py`, add `IntegrityError` to the psycopg2 imports. Change line 8-10:

```python
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
```

to:

```python
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool, IntegrityError
```

Then add these methods after line 2662:

```python
    # --- Group Management Methods ---

    def ensure_user_has_group(self, user_id: str) -> Dict[str, Any]:
        """Ensure a user has a group. Creates one if none exists. Idempotent."""
        existing_group = self.get_user_group(user_id)
        if existing_group:
            return existing_group

        conn = None
        try:
            import secrets
            invite_code = secrets.token_hex(6)

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            try:
                cursor.execute(
                    "INSERT INTO user_groups (name, invite_code) VALUES (%s, %s) RETURNING id, name, description, invite_code, created_at, updated_at",
                    ("My Bar", invite_code),
                )
                group_row = cursor.fetchone()
                group_id = group_row[0]
                group_data = {
                    "id": group_row[0],
                    "name": group_row[1],
                    "description": group_row[2],
                    "invite_code": group_row[3],
                    "created_at": group_row[4],
                    "updated_at": group_row[5],
                }

                cursor.execute(
                    "INSERT INTO user_group_members (group_id, cognito_user_id) VALUES (%s, %s)",
                    (group_id, user_id),
                )

                conn.commit()
                cursor.close()
                self._return_connection(conn)
                conn = None

                return group_data

            except IntegrityError:
                conn.rollback()
                cursor.close()
                self._return_connection(conn)
                conn = None
                return self.get_user_group(user_id)

        except Exception as e:
            if conn:
                conn.rollback()
                self._return_connection(conn)
            logger.error(f"Error ensuring user {user_id} has group: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def create_group(self, user_id: str, name: str, description: str = None) -> Dict[str, Any]:
        """Create a new group and add the user as its first member"""
        import secrets
        invite_code = secrets.token_hex(6)

        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            cursor.execute(
                "INSERT INTO user_groups (name, invite_code, description) VALUES (%s, %s, %s) RETURNING id, name, description, invite_code, created_at, updated_at",
                (name, invite_code, description),
            )
            group_row = cursor.fetchone()
            group_id = group_row[0]
            group_data = {
                "id": group_row[0],
                "name": group_row[1],
                "description": group_row[2],
                "invite_code": group_row[3],
                "created_at": group_row[4],
                "updated_at": group_row[5],
            }

            # If user already has a group, remove from old group first
            cursor.execute(
                "DELETE FROM user_group_members WHERE cognito_user_id = %s",
                (user_id,),
            )

            cursor.execute(
                "INSERT INTO user_group_members (group_id, cognito_user_id) VALUES (%s, %s)",
                (group_id, user_id),
            )

            conn.commit()
            cursor.close()
            self._return_connection(conn)
            conn = None

            return group_data

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error creating group for user {user_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def get_user_group(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the group a user belongs to. Returns None if user has no group."""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT ug.id, ug.name, ug.description, ug.invite_code, ug.created_at, ug.updated_at
                    FROM user_groups ug
                    JOIN user_group_members ugm ON ug.id = ugm.group_id
                    WHERE ugm.cognito_user_id = %(user_id)s
                    """,
                    {"user_id": user_id},
                ),
            )
            if result:
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error getting group for user {user_id}: {str(e)}")
            raise

    def get_group_detail(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Get group details including members"""
        try:
            group_result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, invite_code, created_at, updated_at FROM user_groups WHERE id = %(group_id)s",
                    {"group_id": group_id},
                ),
            )
            if not group_result:
                return None
            group = group_result[0]

            members = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT cognito_user_id, joined_at
                    FROM user_group_members
                    WHERE group_id = %(group_id)s
                    ORDER BY joined_at
                    """,
                    {"group_id": group_id},
                ),
            )

            group["members"] = members
            group["member_count"] = len(members)
            return group
        except Exception as e:
            logger.error(f"Error getting group detail for group {group_id}: {str(e)}")
            raise

    def get_group_members(self, group_id: int) -> List[Dict[str, Any]]:
        """Get all members of a group"""
        try:
            return cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT cognito_user_id, joined_at FROM user_group_members WHERE group_id = %(group_id)s ORDER BY joined_at",
                    {"group_id": group_id},
                ),
            )
        except Exception as e:
            logger.error(f"Error getting members for group {group_id}: {str(e)}")
            raise

    def get_group_membership(self, user_id: str, group_id: int) -> Optional[Dict[str, Any]]:
        """Check if a user is a member of a group. Returns membership record or None."""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, group_id, cognito_user_id, joined_at FROM user_group_members WHERE cognito_user_id = %(user_id)s AND group_id = %(group_id)s",
                    {"user_id": user_id, "group_id": group_id},
                ),
            )
            if result:
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error checking membership for user {user_id} in group {group_id}: {str(e)}")
            raise

    def update_group(self, group_id: int, name: str = None, description: str = None) -> Dict[str, Any]:
        """Update group name and/or description"""
        try:
            updates = []
            params = {"group_id": group_id}
            if name is not None:
                updates.append("name = %(name)s")
                params["name"] = name
            if description is not None:
                updates.append("description = %(description)s")
                params["description"] = description

            if not updates:
                result = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        "SELECT id, name, description, invite_code, created_at, updated_at FROM user_groups WHERE id = %(group_id)s",
                        {"group_id": group_id},
                    ),
                )
                if result:
                    return result[0]
                raise ValueError(f"Group {group_id} not found")

            sql = f"UPDATE user_groups SET {', '.join(updates)} WHERE id = %(group_id)s"
            self.execute_query(sql, params)

            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, invite_code, created_at, updated_at FROM user_groups WHERE id = %(group_id)s",
                    {"group_id": group_id},
                ),
            )
            if result:
                return result[0]
            raise ValueError(f"Group {group_id} not found")
        except Exception as e:
            logger.error(f"Error updating group {group_id}: {str(e)}")
            raise

    def regenerate_invite_code(self, group_id: int) -> Dict[str, Any]:
        """Generate a new invite code for a group"""
        import secrets
        new_code = secrets.token_hex(6)
        try:
            self.execute_query(
                "UPDATE user_groups SET invite_code = %(invite_code)s WHERE id = %(group_id)s",
                {"invite_code": new_code, "group_id": group_id},
            )
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, invite_code, created_at, updated_at FROM user_groups WHERE id = %(group_id)s",
                    {"group_id": group_id},
                ),
            )
            if result:
                return result[0]
            raise ValueError(f"Group {group_id} not found")
        except Exception as e:
            logger.error(f"Error regenerating invite code for group {group_id}: {str(e)}")
            raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db_groups.py::TestGroupCRUD -v --tb=short`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/db/db_core.py tests/test_db_groups.py
git commit -m "feat: add group CRUD database methods with tests"
```

---

## Task 4: Group Database Methods — Join, Leave, Remove Member

**Files:**
- Modify: `api/db/db_core.py`
- Modify: `tests/test_db_groups.py`

- [ ] **Step 1: Write failing tests for join, leave, and remove member**

Append to `tests/test_db_groups.py`, add these test classes:

```python
class TestGroupJoinLeave:
    """Tests for joining and leaving groups"""

    def test_join_group_by_code(self, db_instance):
        """A user can join a group using an invite code"""
        group = db_instance.ensure_user_has_group("user-1")
        invite_code = group["invite_code"]
        result = db_instance.join_group_by_code("user-2", invite_code)
        assert result["id"] == group["id"]
        membership = db_instance.get_group_membership("user-2", group["id"])
        assert membership is not None

    def test_join_group_by_invalid_code_returns_none(self, db_instance):
        """Joining with an invalid invite code returns None"""
        result = db_instance.join_group_by_code("user-1", "invalid_code")
        assert result is None

    def test_join_group_merges_inventory(self, db_instance_with_data):
        """When user joins a group, their inventory merges into the group"""
        db = db_instance_with_data
        db.ensure_user_has_group("user-1")
        db.ensure_user_has_group("user-2")

        group1 = db.get_user_group("user-1")
        group2 = db.get_user_group("user-2")

        db.add_group_ingredient(group1["id"], "user-1", 1)
        db.add_group_ingredient(group2["id"], "user-2", 2)

        result = db.join_group_by_code("user-2", group1["invite_code"])
        assert result is not None

        ingredients = db.get_group_ingredients(group1["id"])
        ingredient_ids = [i["ingredient_id"] for i in ingredients]
        assert 1 in ingredient_ids
        assert 2 in ingredient_ids

    def test_leave_group_creates_new_group(self, db_instance):
        """Leaving a group creates a new personal group"""
        group = db_instance.ensure_user_has_group("user-1")
        result = db.leave_group("user-1", group["id"], copy_inventory=False)
        assert result is not None
        assert result["name"] == "My Bar"
        assert result["id"] != group["id"]

    def test_leave_group_with_copy_inventory(self, db_instance_with_data):
        """Leaving with copy_inventory=True copies ingredients to new group"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredient(group["id"], "user-1", 1)
        db.add_group_ingredient(group["id"], "user-1", 2)

        new_group = db.leave_group("user-1", group["id"], copy_inventory=True)
        new_ingredients = db.get_group_ingredients(new_group["id"])
        assert len(new_ingredients) == 2

    def test_leave_group_without_copy_inventory(self, db_instance_with_data):
        """Leaving with copy_inventory=False starts fresh"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredient(group["id"], "user-1", 1)

        new_group = db.leave_group("user-1", group["id"], copy_inventory=False)
        new_ingredients = db.get_group_ingredients(new_group["id"])
        assert len(new_ingredients) == 0

    def test_remove_group_member(self, db_instance_with_data):
        """Removing a member from a group"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.join_group_by_code("user-2", group["invite_code"])

        db.remove_group_member(group["id"], "user-2")
        membership = db.get_group_membership("user-2", group["id"])
        assert membership is None

    def test_remove_group_member_creates_new_group(self, db_instance_with_data):
        """Removed member gets a new personal group"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.join_group_by_code("user-2", group["invite_code"])

        db.remove_group_member(group["id"], "user-2")
        new_group = db.get_user_group("user-2")
        assert new_group is not None
        assert new_group["id"] != group["id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db_groups.py::TestGroupJoinLeave -v --tb=short`

Expected: FAIL with `AttributeError` for `join_group_by_code`, `leave_group`, etc.

- [ ] **Step 3: Implement join, leave, and remove member methods**

Add these methods to `api/db/db_core.py` after the `regenerate_invite_code` method:

```python
    def join_group_by_code(self, user_id: str, invite_code: str) -> Optional[Dict[str, Any]]:
        """Join a group by invite code. Merges user's current inventory into the target group."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            cursor.execute(
                "SELECT id, name, description, invite_code, created_at, updated_at FROM user_groups WHERE invite_code = %s",
                (invite_code,),
            )
            target_group = cursor.fetchone()
            if not target_group:
                conn.rollback()
                cursor.close()
                self._return_connection(conn)
                conn = None
                return None

            target_group_id = target_group[0]
            target_group_data = {
                "id": target_group[0],
                "name": target_group[1],
                "description": target_group[2],
                "invite_code": target_group[3],
                "created_at": target_group[4],
                "updated_at": target_group[5],
            }

            cursor.execute(
                "SELECT group_id FROM user_group_members WHERE cognito_user_id = %s",
                (user_id,),
            )
            current_membership = cursor.fetchone()
            current_group_id = current_membership[0] if current_membership else None

            if current_group_id == target_group_id:
                conn.commit()
                cursor.close()
                self._return_connection(conn)
                return target_group_data

            if current_group_id is not None:
                cursor.execute(
                    """
                    INSERT INTO group_ingredients (group_id, ingredient_id, added_by, added_at)
                    SELECT %s, gi.ingredient_id, gi.added_by, gi.added_at
                    FROM group_ingredients gi
                    WHERE gi.group_id = %s
                    ON CONFLICT (group_id, ingredient_id) DO NOTHING
                    """,
                    (target_group_id, current_group_id),
                )

            cursor.execute(
                "DELETE FROM user_group_members WHERE cognito_user_id = %s",
                (user_id,),
            )

            cursor.execute(
                "INSERT INTO user_group_members (group_id, cognito_user_id) VALUES (%s, %s)",
                (target_group_id, user_id),
            )

            conn.commit()
            cursor.close()
            self._return_connection(conn)
            conn = None

            return target_group_data

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error joining group for user {user_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def leave_group(self, user_id: str, group_id: int, copy_inventory: bool = False) -> Dict[str, Any]:
        """Leave a group. Creates a new personal group. Optionally copies inventory."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            import secrets
            new_invite_code = secrets.token_hex(6)
            cursor.execute(
                "INSERT INTO user_groups (name, invite_code) VALUES (%s, %s) RETURNING id, name, description, invite_code, created_at, updated_at",
                ("My Bar", new_invite_code),
            )
            new_group_row = cursor.fetchone()
            new_group_id = new_group_row[0]
            new_group_data = {
                "id": new_group_row[0],
                "name": new_group_row[1],
                "description": new_group_row[2],
                "invite_code": new_group_row[3],
                "created_at": new_group_row[4],
                "updated_at": new_group_row[5],
            }

            if copy_inventory:
                cursor.execute(
                    """
                    INSERT INTO group_ingredients (group_id, ingredient_id, added_by, added_at)
                    SELECT %s, gi.ingredient_id, gi.added_by, gi.added_at
                    FROM group_ingredients gi
                    WHERE gi.group_id = %s
                    ON CONFLICT (group_id, ingredient_id) DO NOTHING
                    """,
                    (new_group_id, group_id),
                )

            cursor.execute(
                "DELETE FROM user_group_members WHERE cognito_user_id = %s AND group_id = %s",
                (user_id, group_id),
            )

            cursor.execute(
                "INSERT INTO user_group_members (group_id, cognito_user_id) VALUES (%s, %s) ON CONFLICT (cognito_user_id) DO NOTHING",
                (new_group_id, user_id),
            )

            conn.commit()
            cursor.close()
            self._return_connection(conn)
            conn = None

            return new_group_data

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error leaving group for user {user_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def remove_group_member(self, group_id: int, target_user_id: str) -> bool:
        """Remove a member from a group. Creates a new personal group for them."""
        try:
            membership = self.get_group_membership(target_user_id, group_id)
            if not membership:
                return False

            self.leave_group(target_user_id, group_id, copy_inventory=True)
            return True
        except Exception as e:
            logger.error(f"Error removing member {target_user_id} from group {group_id}: {str(e)}")
            raise
```

- [ ] **Step 4: Add the `db_instance_with_data` fixture to `tests/test_db_groups.py`**

Add this import and fixture at the top of the test file (after imports):

```python
import pytest
from psycopg2 import IntegrityError
```

And ensure the `db_instance` fixture is available (it comes from `conftest.py` which is autouse). The `db_instance_with_data` fixture is also from conftest.py.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_db_groups.py -v --tb=short`

Expected: All group CRUD and join/leave tests PASS.

- [ ] **Step 6: Commit**

```bash
git add api/db/db_core.py tests/test_db_groups.py
git commit -m "feat: add group join/leave/remove-member database methods with tests"
```

---

## Task 5: Group Inventory Database Methods

**Files:**
- Modify: `api/db/db_core.py`
- Modify: `tests/test_db_groups.py`

- [ ] **Step 1: Write failing tests for group ingredient methods**

Append to `tests/test_db_groups.py`:

```python
class TestGroupIngredients:
    """Tests for group ingredient operations"""

    def test_add_group_ingredient(self, db_instance_with_data):
        """Add an ingredient to a group's inventory"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        result = db.add_group_ingredient(group["id"], "user-1", 1)
        assert result["ingredient_id"] == 1
        assert "ingredient_name" in result

    def test_add_group_ingredient_with_parents(self, db_instance_with_data):
        """Adding a child ingredient auto-adds parent ingredients"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        result = db.add_group_ingredient(group["id"], "user-1", 8)
        assert result["parents_added"] >= 1

        ingredients = db.get_group_ingredients(group["id"])
        ingredient_ids = [i["ingredient_id"] for i in ingredients]
        assert 8 in ingredient_ids
        assert 1 in ingredient_ids

    def test_add_duplicate_group_ingredient_raises(self, db_instance_with_data):
        """Adding a duplicate ingredient raises ValueError"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredient(group["id"], "user-1", 1)
        with pytest.raises(ValueError):
            db.add_group_ingredient(group["id"], "user-1", 1)

    def test_remove_group_ingredient(self, db_instance_with_data):
        """Remove an ingredient from a group's inventory"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredient(group["id"], "user-1", 1)
        result = db.remove_group_ingredient(group["id"], 1)
        assert result is True
        ingredients = db.get_group_ingredients(group["id"])
        assert len(ingredients) == 0

    def test_remove_group_ingredient_parent_with_children_fails(self, db_instance_with_data):
        """Removing a parent ingredient when children exist fails"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredient(group["id"], "user-1", 8)
        with pytest.raises(ValueError, match="child ingredients"):
            db.remove_group_ingredient(group["id"], 1)

    def test_remove_leaf_ingredient_succeeds(self, db_instance_with_data):
        """Removing a leaf ingredient always succeeds"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredient(group["id"], "user-1", 8)
        result = db.remove_group_ingredient(group["id"], 8)
        assert result is True

    def test_get_group_ingredients(self, db_instance_with_data):
        """Get all ingredients for a group"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredient(group["id"], "user-1", 1)
        db.add_group_ingredient(group["id"], "user-1", 2)
        ingredients = db.get_group_ingredients(group["id"])
        assert len(ingredients) == 2

    def test_add_group_ingredients_bulk(self, db_instance_with_data):
        """Bulk add ingredients to group"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        result = db.add_group_ingredients_bulk(group["id"], "user-1", [1, 2, 3])
        assert result["added_count"] == 3

    def test_remove_group_ingredients_bulk(self, db_instance_with_data):
        """Bulk remove ingredients from group"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredients_bulk(group["id"], "user-1", [1, 2, 3])
        result = db.remove_group_ingredients_bulk(group["id"], [1, 2, 3])
        assert result["removed_count"] == 3

    def test_group_ingredient_recommendations(self, db_instance_with_data):
        """Get ingredient recommendations for a group"""
        db = db_instance_with_data
        group = db.ensure_user_has_group("user-1")
        db.add_group_ingredient(group["id"], "user-1", 1)
        db.add_group_ingredient(group["id"], "user-1", 8)
        recommendations = db.get_group_ingredient_recommendations(group["id"], 5)
        assert isinstance(recommendations, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db_groups.py::TestGroupIngredients -v --tb=short`

Expected: FAIL with `AttributeError` for `add_group_ingredient`, etc.

- [ ] **Step 3: Implement group ingredient methods in `api/db/db_core.py`**

Add these methods after the `remove_group_member` method. These follow the same patterns as the existing user_ingredient methods but operate on `group_id` instead of `user_id`:

```python
    def add_group_ingredient(self, group_id: int, user_id: str, ingredient_id: int) -> Dict[str, Any]:
        """Add an ingredient to a group's inventory, including all parent ingredients"""
        conn = None
        try:
            ingredient = self.get_ingredient(ingredient_id)
            if not ingredient:
                raise ValueError(f"Ingredient with ID {ingredient_id} does not exist")

            existing = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM group_ingredients WHERE group_id = %(group_id)s AND ingredient_id = %(ingredient_id)s",
                    {"group_id": group_id, "ingredient_id": ingredient_id},
                ),
            )
            if existing:
                raise ValueError(
                    f"Ingredient {ingredient_id} already exists in group's inventory"
                )

            parent_ingredient_ids = []
            ingredient_path = ingredient["path"]
            if ingredient_path:
                path_parts = [part for part in ingredient_path.split("/") if part]
                parent_ingredient_ids = [int(part) for part in path_parts[:-1]]

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            for parent_id in parent_ingredient_ids:
                try:
                    cursor.execute(
                        """
                        INSERT INTO group_ingredients (group_id, ingredient_id, added_by)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (group_id, ingredient_id) DO NOTHING
                        """,
                        (group_id, parent_id, user_id),
                    )
                    if cursor.rowcount > 0:
                        logger.info(f"Added parent ingredient {parent_id} to group {group_id}")
                except Exception as e:
                    logger.warning(f"Error adding parent ingredient {parent_id} to group {group_id}: {str(e)}")

            cursor.execute(
                "INSERT INTO group_ingredients (group_id, ingredient_id, added_by) VALUES (%s, %s, %s)",
                (group_id, ingredient_id, user_id),
            )

            conn.commit()
            cursor.close()
            self._return_connection(conn)
            conn = None

            return {
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient["name"],
                "added_at": "now",
                "parents_added": len(parent_ingredient_ids),
            }

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error adding ingredient {ingredient_id} to group {group_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def remove_group_ingredient(self, group_id: int, ingredient_id: int) -> bool:
        """Remove an ingredient from a group's inventory, but prevent removing parents if children exist"""
        try:
            existing = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM group_ingredients WHERE group_id = %(group_id)s AND ingredient_id = %(ingredient_id)s",
                    {"group_id": group_id, "ingredient_id": ingredient_id},
                ),
            )
            if not existing:
                return False

            ingredient = self.get_ingredient(ingredient_id)
            if not ingredient:
                return False

            ingredient_path = ingredient["path"]
            if ingredient_path:
                child_ingredients = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        """
                        SELECT gi.ingredient_id, i.name, i.path
                        FROM group_ingredients gi
                        JOIN ingredients i ON gi.ingredient_id = i.id
                        WHERE gi.group_id = %(group_id)s
                        AND i.path LIKE %(child_path_pattern)s
                        AND i.id != %(ingredient_id)s
                        """,
                        {
                            "group_id": group_id,
                            "child_path_pattern": f"{ingredient_path}%",
                            "ingredient_id": ingredient_id,
                        },
                    ),
                )
                if child_ingredients:
                    child_names = [child["name"] for child in child_ingredients]
                    raise ValueError(
                        f"Cannot remove ingredient '{ingredient['name']}' because it has child ingredients in your inventory: {', '.join(child_names)}. Please remove the child ingredients first."
                    )

            result = self.execute_query(
                "DELETE FROM group_ingredients WHERE group_id = %(group_id)s AND ingredient_id = %(ingredient_id)s",
                {"group_id": group_id, "ingredient_id": ingredient_id},
            )
            return result.get("rowCount", 0) > 0

        except Exception as e:
            logger.error(f"Error removing ingredient {ingredient_id} from group {group_id}: {str(e)}")
            raise

    def get_group_ingredients(self, group_id: int) -> List[Dict[str, Any]]:
        """Get all ingredients for a group"""
        try:
            return cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT gi.ingredient_id, gi.added_at, gi.added_by, i.name, i.description, i.parent_id, i.path
                    FROM group_ingredients gi
                    JOIN ingredients i ON gi.ingredient_id = i.id
                    WHERE gi.group_id = %(group_id)s
                    ORDER BY i.name
                    """,
                    {"group_id": group_id},
                ),
            )
        except Exception as e:
            logger.error(f"Error getting ingredients for group {group_id}: {str(e)}")
            raise

    def add_group_ingredients_bulk(self, group_id: int, user_id: str, ingredient_ids: List[int]) -> Dict[str, Any]:
        """Add multiple ingredients to a group's inventory"""
        conn = None
        try:
            if not ingredient_ids:
                return {"added_count": 0, "already_exists_count": 0, "failed_count": 0, "errors": []}

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            added_count = 0
            already_exists_count = 0
            failed_count = 0
            errors = []

            for ingredient_id in ingredient_ids:
                try:
                    ingredient_check = cast(
                        List[Dict[str, Any]],
                        self.execute_query(
                            "SELECT id FROM ingredients WHERE id = %(ingredient_id)s",
                            {"ingredient_id": ingredient_id},
                        ),
                    )
                    if not ingredient_check:
                        errors.append(f"Ingredient with ID {ingredient_id} does not exist")
                        failed_count += 1
                        continue

                    cursor.execute(
                        "SELECT id FROM group_ingredients WHERE group_id = %s AND ingredient_id = %s",
                        (group_id, ingredient_id),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        already_exists_count += 1
                        continue

                    cursor.execute(
                        "INSERT INTO group_ingredients (group_id, ingredient_id, added_by) VALUES (%s, %s, %s)",
                        (group_id, ingredient_id, user_id),
                    )
                    added_count += 1

                except Exception as e:
                    errors.append(f"Error adding ingredient {ingredient_id}: {str(e)}")
                    failed_count += 1

            conn.commit()

            return {
                "added_count": added_count,
                "already_exists_count": already_exists_count,
                "failed_count": failed_count,
                "errors": errors,
            }

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error in bulk add ingredients for group {group_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def remove_group_ingredients_bulk(self, group_id: int, ingredient_ids: List[int]) -> Dict[str, Any]:
        """Remove multiple ingredients from a group's inventory with ordered deletion"""
        conn = None
        try:
            if not ingredient_ids:
                return {"removed_count": 0, "not_found_count": 0}

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            removed_count = 0
            not_found_count = 0
            validation_errors = []

            valid_ingredients = []
            for ingredient_id in ingredient_ids:
                try:
                    cursor.execute(
                        "SELECT id FROM group_ingredients WHERE group_id = %s AND ingredient_id = %s",
                        (group_id, ingredient_id),
                    )
                    existing = cursor.fetchone()
                    if not existing:
                        not_found_count += 1
                        continue

                    cursor.execute(
                        "SELECT id, name, path FROM ingredients WHERE id = %s",
                        (ingredient_id,),
                    )
                    ingredient = cursor.fetchone()
                    if not ingredient:
                        not_found_count += 1
                        continue

                    valid_ingredients.append({
                        "id": ingredient[0],
                        "name": ingredient[1],
                        "path": ingredient[2] or "",
                    })
                except Exception as e:
                    validation_errors.append(f"Error validating ingredient {ingredient_id}: {str(e)}")

            if validation_errors:
                conn.rollback()
                raise ValueError(f"Validation failed: {'; '.join(validation_errors)}")

            ingredient_ids_to_remove = set(ing["id"] for ing in valid_ingredients)

            for ingredient in valid_ingredients:
                try:
                    ingredient_id = ingredient["id"]
                    ingredient_name = ingredient["name"]
                    ingredient_path = ingredient["path"]

                    if ingredient_path:
                        cursor.execute(
                            """
                            SELECT gi.ingredient_id, i.name, i.path
                            FROM group_ingredients gi
                            JOIN ingredients i ON gi.ingredient_id = i.id
                            WHERE gi.group_id = %s
                            AND i.path LIKE %s
                            AND i.id != %s
                            """,
                            (group_id, f"{ingredient_path}%", ingredient_id),
                        )
                        child_ingredients = cursor.fetchall()

                        if child_ingredients:
                            children_not_being_removed = []
                            for child in child_ingredients:
                                child_id = child[0]
                                child_name = child[1]
                                if child_id not in ingredient_ids_to_remove:
                                    children_not_being_removed.append(child_name)

                            if children_not_being_removed:
                                validation_errors.append(
                                    f"Cannot remove ingredient '{ingredient_name}' because it has child ingredients in your inventory that are not being removed: {', '.join(children_not_being_removed)}"
                                )
                                continue

                except Exception as e:
                    validation_errors.append(f"Error validating ingredient {ingredient_id}: {str(e)}")

            if validation_errors:
                conn.rollback()
                raise ValueError(f"Validation failed: {'; '.join(validation_errors)}")

            valid_ingredients.sort(
                key=lambda x: len(x["path"].split("/")) if x["path"] else 0,
                reverse=True,
            )

            for ingredient in valid_ingredients:
                try:
                    ingredient_id = ingredient["id"]
                    cursor.execute(
                        "SELECT id FROM group_ingredients WHERE group_id = %s AND ingredient_id = %s",
                        (group_id, ingredient_id),
                    )
                    existing = cursor.fetchone()
                    if not existing:
                        continue

                    cursor.execute(
                        "DELETE FROM group_ingredients WHERE group_id = %s AND ingredient_id = %s",
                        (group_id, ingredient_id),
                    )
                    removed_count += 1

                except Exception as e:
                    logger.error(f"Error removing ingredient {ingredient_id} from group {group_id}: {str(e)}")

            conn.commit()

            return {"removed_count": removed_count, "not_found_count": not_found_count}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error in bulk remove ingredients for group {group_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def get_group_ingredient_recommendations(self, group_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get ingredient recommendations for a group (which ingredients would unlock the most recipes)"""
        try:
            from .sql_queries import get_group_ingredient_recommendations_sql

            query = get_group_ingredient_recommendations_sql()
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(query, {"group_id": group_id, "limit": limit}),
            )

            for row in result:
                if row.get("recipe_names"):
                    row["recipe_names"] = row["recipe_names"].split("|||")
                else:
                    row["recipe_names"] = []

            return result
        except Exception as e:
            logger.error(f"Error getting ingredient recommendations for group {group_id}: {str(e)}")
            raise
```

- [ ] **Step 4: Add `get_group_ingredient_recommendations_sql` to `api/db/sql_queries.py`**

Add the following function at the end of `sql_queries.py` (after `get_ingredient_recommendations_sql`):

```python
def get_group_ingredient_recommendations_sql() -> str:
    """Build SQL query for ingredient recommendations using group inventory"""

    substitution_match_adapted = INGREDIENT_SUBSTITUTION_MATCH.replace(
        'i_user.allow_substitution', 'ui.user_allow_substitution'
    ).replace(
        'i_user.parent_id', 'ui.parent_id'
    ).replace(
        'i_user.path', 'ui.path'
    ).replace(
        'i_user.id', 'ui.ingredient_id'
    ).replace(
        'i_recipe.allow_substitution', 'rr.required_allow_substitution'
    ).replace(
        'i_recipe.parent_id', 'rr.required_parent_id'
    ).replace(
        'i_recipe.path', 'rr.required_ingredient_path'
    ).replace(
        'i_recipe.id', 'rr.required_ingredient_id'
    )

    query = f"""
    WITH
    user_inventory AS (
        SELECT
            gi.ingredient_id,
            i.path,
            i.parent_id,
            COALESCE(i.allow_substitution, FALSE) as user_allow_substitution
        FROM group_ingredients gi
        JOIN ingredients i ON gi.ingredient_id = i.id
        WHERE gi.group_id = %(group_id)s
    ),
    recipe_requirements AS (
        SELECT
            ri.recipe_id,
            ri.ingredient_id as required_ingredient_id,
            i.name as required_ingredient_name,
            i.path as required_ingredient_path,
            i.parent_id as required_parent_id,
            COALESCE(i.allow_substitution, FALSE) as required_allow_substitution
        FROM recipe_ingredients ri
        JOIN ingredients i ON ri.ingredient_id = i.id
    ),
    requirement_satisfaction AS (
        SELECT
            rr.recipe_id,
            rr.required_ingredient_id,
            rr.required_ingredient_name,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM user_inventory ui
                    WHERE
                        {substitution_match_adapted}
                ) THEN 1
                ELSE 0
            END as is_satisfied
        FROM recipe_requirements rr
    ),
    almost_makeable_recipes AS (
        SELECT
            recipe_id,
            COUNT(*) as total_requirements,
            SUM(is_satisfied) as satisfied_count,
            COUNT(*) - SUM(is_satisfied) as missing_count
        FROM requirement_satisfaction
        GROUP BY recipe_id
        HAVING COUNT(*) - SUM(is_satisfied) = 1
    ),
    missing_ingredients AS (
        SELECT
            rs.recipe_id,
            rs.required_ingredient_id as missing_ingredient_id,
            rs.required_ingredient_name as missing_ingredient_name
        FROM requirement_satisfaction rs
        JOIN almost_makeable_recipes amr ON rs.recipe_id = amr.recipe_id
        WHERE rs.is_satisfied = 0
    ),
    ingredient_impact AS (
        SELECT
            mi.missing_ingredient_id,
            COUNT(*) as recipes_unlocked,
            STRING_AGG(r.name, '|||') as recipe_names
        FROM missing_ingredients mi
        JOIN recipes r ON mi.recipe_id = r.id
        GROUP BY mi.missing_ingredient_id
        ORDER BY recipes_unlocked DESC
        LIMIT %(limit)s
    )
    SELECT
        i.id,
        i.name,
        i.description,
        i.parent_id,
        i.path,
        i.allow_substitution,
        ii.recipes_unlocked,
        ii.recipe_names
    FROM ingredient_impact ii
    JOIN ingredients i ON ii.missing_ingredient_id = i.id
    ORDER BY ii.recipes_unlocked DESC
    """

    return query
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_db_groups.py::TestGroupIngredients -v --tb=short`

Expected: All group ingredient tests PASS.

- [ ] **Step 6: Commit**

```bash
git add api/db/db_core.py api/db/sql_queries.py tests/test_db_groups.py
git commit -m "feat: add group inventory database methods and recommendation SQL"
```

---

## Task 6: Group Routes

**Files:**
- Create: `api/routes/groups.py`
- Modify: `api/main.py`

- [ ] **Step 1: Create `api/routes/groups.py`**

```python
"""Group management endpoints for the CocktailDB API"""

import logging
from fastapi import APIRouter, Depends, status, HTTPException

from dependencies.auth import UserInfo, require_authentication
from db.database import get_database as get_db
from db.db_core import Database
from models.requests import GroupCreate, GroupUpdate, GroupJoin, GroupLeave
from models.responses import (
    GroupResponse,
    GroupDetailResponse,
    GroupMemberResponse,
    UserIngredientResponse,
    UserIngredientListResponse,
    UserIngredientBulkResponse,
    IngredientRecommendationListResponse,
    IngredientRecommendationResponse,
    MessageResponse,
)
from core.exceptions import NotFoundException, DatabaseException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/groups", tags=["groups"])


def _verify_group_membership(db: Database, user_id: str, group_id: int):
    """Verify user is a member of the group, raise 403 if not"""
    membership = db.get_group_membership(user_id, group_id)
    if not membership:
        raise HTTPException(
            status_code=403,
            detail=f"User is not a member of group {group_id}"
        )
    return membership


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: GroupCreate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Create a new group (user becomes first member)"""
    try:
        group = db.create_group(
            user.user_id,
            group_data.name,
            group_data.description,
        )
        return GroupResponse(
            id=group["id"],
            name=group["name"],
            description=group.get("description"),
            invite_code=group["invite_code"],
            created_at=group["created_at"],
            updated_at=group["updated_at"],
        )
    except Exception as e:
        logger.error(f"Error creating group for user {user.user_id}: {str(e)}")
        raise DatabaseException("Failed to create group", detail=str(e))


@router.get("/mine", response_model=GroupDetailResponse)
async def get_my_group(
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get the current user's group with members"""
    try:
        group = db.ensure_user_has_group(user.user_id)
        detail = db.get_group_detail(group["id"])

        member_responses = []
        for member in detail["members"]:
            member_responses.append(
                GroupMemberResponse(
                    cognito_user_id=member["cognito_user_id"],
                    username=None,
                    joined_at=member["joined_at"],
                )
            )

        return GroupDetailResponse(
            id=detail["id"],
            name=detail["name"],
            description=detail.get("description"),
            invite_code=detail["invite_code"],
            members=member_responses,
            member_count=detail["member_count"],
            created_at=detail["created_at"],
            updated_at=detail["updated_at"],
        )
    except Exception as e:
        logger.error(f"Error getting group for user {user.user_id}: {str(e)}")
        raise DatabaseException("Failed to get group", detail=str(e))


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    group_data: GroupUpdate,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Update group name and/or description (must be a member)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        updated = db.update_group(
            group_id,
            name=group_data.name,
            description=group_data.description,
        )
        return GroupResponse(
            id=updated["id"],
            name=updated["name"],
            description=updated.get("description"),
            invite_code=updated["invite_code"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"],
        )
    except ValueError as e:
        raise NotFoundException(str(e))
    except Exception as e:
        logger.error(f"Error updating group {group_id}: {str(e)}")
        raise DatabaseException("Failed to update group", detail=str(e))


@router.post("/join", response_model=GroupDetailResponse)
async def join_group(
    join_data: GroupJoin,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Join a group using an invite code"""
    try:
        group = db.join_group_by_code(user.user_id, join_data.invite_code)
        if not group:
            raise NotFoundException("Invalid invite code")

        detail = db.get_group_detail(group["id"])

        member_responses = []
        for member in detail["members"]:
            member_responses.append(
                GroupMemberResponse(
                    cognito_user_id=member["cognito_user_id"],
                    username=None,
                    joined_at=member["joined_at"],
                )
            )

        return GroupDetailResponse(
            id=detail["id"],
            name=detail["name"],
            description=detail.get("description"),
            invite_code=detail["invite_code"],
            members=member_responses,
            member_count=detail["member_count"],
            created_at=detail["created_at"],
            updated_at=detail["updated_at"],
        )
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error joining group for user {user.user_id}: {str(e)}")
        raise DatabaseException("Failed to join group", detail=str(e))


@router.delete("/{group_id}/members/{target_user_id}", response_model=MessageResponse)
async def remove_member(
    group_id: int,
    target_user_id: str,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove a member from the group (must be a member yourself)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        success = db.remove_group_member(group_id, target_user_id)
        if not success:
            raise NotFoundException(f"User {target_user_id} is not a member of group {group_id}")

        return MessageResponse(message=f"Member {target_user_id} removed from group {group_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error removing member {target_user_id} from group {group_id}: {str(e)}")
        raise DatabaseException("Failed to remove member", detail=str(e))


@router.post("/{group_id}/leave", response_model=GroupDetailResponse)
async def leave_group(
    group_id: int,
    leave_data: GroupLeave,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Leave a group. Creates a new personal group. Optionally copies inventory."""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        new_group = db.leave_group(user.user_id, group_id, copy_inventory=leave_data.copy_inventory)

        detail = db.get_group_detail(new_group["id"])

        member_responses = []
        for member in detail["members"]:
            member_responses.append(
                GroupMemberResponse(
                    cognito_user_id=member["cognito_user_id"],
                    username=None,
                    joined_at=member["joined_at"],
                )
            )

        return GroupDetailResponse(
            id=detail["id"],
            name=detail["name"],
            description=detail.get("description"),
            invite_code=detail["invite_code"],
            members=member_responses,
            member_count=detail["member_count"],
            created_at=detail["created_at"],
            updated_at=detail["updated_at"],
        )
    except Exception as e:
        logger.error(f"Error leaving group {group_id} for user {user.user_id}: {str(e)}")
        raise DatabaseException("Failed to leave group", detail=str(e))


@router.post("/{group_id}/invite-code/regenerate", response_model=GroupResponse)
async def regenerate_invite_code(
    group_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Regenerate the invite code for a group (must be a member)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        updated = db.regenerate_invite_code(group_id)
        return GroupResponse(
            id=updated["id"],
            name=updated["name"],
            description=updated.get("description"),
            invite_code=updated["invite_code"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"],
        )
    except ValueError as e:
        raise NotFoundException(str(e))
    except Exception as e:
        logger.error(f"Error regenerating invite code for group {group_id}: {str(e)}")
        raise DatabaseException("Failed to regenerate invite code", detail=str(e))


# --- Group Ingredient Endpoints ---


@router.get("/{group_id}/ingredients", response_model=UserIngredientListResponse)
async def get_group_ingredients(
    group_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get all ingredients in a group's inventory (must be a member)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        ingredients = db.get_group_ingredients(group_id)

        ingredient_responses = []
        for ingredient in ingredients:
            ingredient_responses.append(
                UserIngredientResponse(
                    ingredient_id=ingredient["ingredient_id"],
                    name=ingredient["name"],
                    description=ingredient.get("description"),
                    parent_id=ingredient.get("parent_id"),
                    path=ingredient.get("path"),
                    added_at=ingredient["added_at"]
                )
            )

        return UserIngredientListResponse(
            ingredients=ingredient_responses,
            total_count=len(ingredient_responses)
        )
    except Exception as e:
        logger.error(f"Error getting ingredients for group {group_id}: {str(e)}")
        raise DatabaseException("Failed to retrieve group ingredients", detail=str(e))


@router.post("/{group_id}/ingredients", response_model=UserIngredientResponse, status_code=status.HTTP_201_CREATED)
async def add_group_ingredient(
    group_id: int,
    ingredient_data: UserIngredientAdd,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add an ingredient to a group's inventory (must be a member)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        result = db.add_group_ingredient(group_id, user.user_id, ingredient_data.ingredient_id)

        return UserIngredientResponse(
            ingredient_id=result["ingredient_id"],
            name=result["ingredient_name"],
            description=None,
            parent_id=None,
            path=None,
            added_at=result["added_at"]
        )
    except ValueError as e:
        if "does not exist" in str(e):
            raise NotFoundException(str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding ingredient to group {group_id}: {str(e)}")
        raise DatabaseException("Failed to add ingredient to group inventory", detail=str(e))


@router.post("/{group_id}/ingredients/bulk", response_model=UserIngredientBulkResponse, status_code=status.HTTP_201_CREATED)
async def add_group_ingredients_bulk(
    group_id: int,
    bulk_data: UserIngredientBulkAdd,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Bulk add ingredients to a group's inventory (must be a member)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        result = db.add_group_ingredients_bulk(group_id, user.user_id, bulk_data.ingredient_ids)

        return UserIngredientBulkResponse(
            added_count=result["added_count"],
            already_exists_count=result.get("already_exists_count"),
            failed_count=result.get("failed_count"),
            errors=result.get("errors", [])
        )
    except Exception as e:
        logger.error(f"Error bulk adding ingredients to group {group_id}: {str(e)}")
        raise DatabaseException("Failed to bulk add ingredients to group inventory", detail=str(e))


@router.delete("/{group_id}/ingredients/{ingredient_id}", response_model=MessageResponse)
async def remove_group_ingredient(
    group_id: int,
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove an ingredient from a group's inventory (must be a member)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        success = db.remove_group_ingredient(group_id, ingredient_id)

        if not success:
            raise NotFoundException(f"Ingredient {ingredient_id} not found in group's inventory")

        return MessageResponse(
            message=f"Ingredient {ingredient_id} removed from group inventory successfully"
        )
    except NotFoundException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing ingredient {ingredient_id} from group {group_id}: {str(e)}")
        raise DatabaseException("Failed to remove ingredient from group inventory", detail=str(e))


@router.delete("/{group_id}/ingredients/bulk", response_model=UserIngredientBulkResponse)
async def remove_group_ingredients_bulk(
    group_id: int,
    bulk_data: UserIngredientBulkRemove,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Bulk remove ingredients from a group's inventory (must be a member)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        result = db.remove_group_ingredients_bulk(group_id, bulk_data.ingredient_ids)

        return UserIngredientBulkResponse(
            removed_count=result["removed_count"],
            not_found_count=result.get("not_found_count")
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error bulk removing ingredients from group {group_id}: {str(e)}")
        raise DatabaseException("Failed to bulk remove ingredients from group inventory", detail=str(e))


@router.get("/{group_id}/ingredients/recommendations", response_model=IngredientRecommendationListResponse)
async def get_group_ingredient_recommendations(
    group_id: int,
    limit: int = 20,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get ingredient recommendations for a group (must be a member)"""
    _verify_group_membership(db, user.user_id, group_id)

    try:
        recommendations = db.get_group_ingredient_recommendations(group_id, limit)

        recommendation_responses = []
        for rec in recommendations:
            recommendation_responses.append(
                IngredientRecommendationResponse(
                    id=rec["id"],
                    name=rec["name"],
                    description=rec.get("description"),
                    parent_id=rec.get("parent_id"),
                    path=rec.get("path"),
                    allow_substitution=rec.get("allow_substitution", False),
                    recipes_unlocked=rec["recipes_unlocked"],
                    recipe_names=rec["recipe_names"]
                )
            )

        return IngredientRecommendationListResponse(
            recommendations=recommendation_responses,
            total_count=len(recommendation_responses)
        )
    except Exception as e:
        logger.error(f"Error getting ingredient recommendations for group {group_id}: {str(e)}")
        raise DatabaseException("Failed to retrieve group ingredient recommendations", detail=str(e))
```

- [ ] **Step 2: Register the groups router in `api/main.py`**

In `api/main.py`, add the import for groups route (around line 30):

Change:
```python
from routes import ingredients, recipes, ratings, units, tags, auth, admin, user_ingredients, stats, analytics, pages
```

to:
```python
from routes import ingredients, recipes, ratings, units, tags, auth, admin, user_ingredients, stats, analytics, pages, groups
```

Add the router registration after `user_ingredients.router` (around line 102):

```python
app.include_router(groups.router)
```

- [ ] **Step 3: Verify the groups routes load correctly**

Run: `python -c "from api.routes.groups import router; print(f'Routes: {len(router.routes)}')"`

Workdir: `/home/kurtt/cocktaildb/api`

Expected: `Routes: 12` (or similar number, confirming routes are registered)

- [ ] **Step 4: Commit**

```bash
git add api/routes/groups.py api/main.py
git commit -m "feat: add group management and group inventory API routes"
```

---

## Task 7: Repoint User Ingredients Routes to Group Inventory

**Files:**
- Modify: `api/routes/user_ingredients.py`

- [ ] **Step 1: Update `user_ingredients.py` to use group inventory**

Replace the entire content of `api/routes/user_ingredients.py` with backward-compatible wrappers that resolve the user's group and delegate to group inventory methods:

```python
"""User ingredient endpoints - backward-compatible wrappers that delegate to group inventory"""

import logging
from fastapi import APIRouter, Depends, status, HTTPException

from dependencies.auth import UserInfo, require_authentication
from db.database import get_database as get_db
from db.db_core import Database
from models.requests import UserIngredientAdd, UserIngredientBulkAdd, UserIngredientBulkRemove
from models.responses import (
    UserIngredientResponse,
    UserIngredientListResponse,
    UserIngredientBulkResponse,
    MessageResponse,
    IngredientRecommendationResponse,
    IngredientRecommendationListResponse,
)
from core.exceptions import NotFoundException, DatabaseException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-ingredients", tags=["user-ingredients"])


def _get_user_group_id(db: Database, user_id: str) -> int:
    """Resolve the user's group ID, auto-creating if needed"""
    group = db.ensure_user_has_group(user_id)
    return group["id"]


@router.post("", response_model=UserIngredientResponse, status_code=status.HTTP_201_CREATED)
async def add_user_ingredient(
    ingredient_data: UserIngredientAdd,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add an ingredient to user's inventory (delegates to group inventory)"""
    try:
        group_id = _get_user_group_id(db, user.user_id)
        result = db.add_group_ingredient(group_id, user.user_id, ingredient_data.ingredient_id)

        return UserIngredientResponse(
            ingredient_id=result["ingredient_id"],
            name=result["ingredient_name"],
            description=None,
            parent_id=None,
            path=None,
            added_at=result["added_at"]
        )

    except ValueError as e:
        if "does not exist" in str(e):
            raise NotFoundException(str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding ingredient to user inventory: {str(e)}")
        raise DatabaseException("Failed to add ingredient to inventory", detail=str(e))


@router.delete("/bulk", response_model=UserIngredientBulkResponse)
async def remove_user_ingredients_bulk(
    bulk_data: UserIngredientBulkRemove,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove multiple ingredients from user's inventory (delegates to group inventory)"""
    try:
        group_id = _get_user_group_id(db, user.user_id)
        result = db.remove_group_ingredients_bulk(group_id, bulk_data.ingredient_ids)

        return UserIngredientBulkResponse(
            removed_count=result["removed_count"],
            not_found_count=result["not_found_count"]
        )

    except ValueError as e:
        logger.warning(f"Validation error during bulk remove for user {user.user_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error bulk removing ingredients from user inventory: {str(e)}")
        raise DatabaseException("Failed to bulk remove ingredients from inventory", detail=str(e))


@router.delete("/{ingredient_id}", response_model=MessageResponse)
async def remove_user_ingredient(
    ingredient_id: int,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Remove an ingredient from user's inventory (delegates to group inventory)"""
    try:
        group_id = _get_user_group_id(db, user.user_id)
        success = db.remove_group_ingredient(group_id, ingredient_id)

        if not success:
            raise NotFoundException(f"Ingredient {ingredient_id} not found in user's inventory")

        return MessageResponse(
            message=f"Ingredient {ingredient_id} removed from inventory successfully"
        )

    except NotFoundException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing ingredient from user inventory: {str(e)}")
        raise DatabaseException("Failed to remove ingredient from inventory", detail=str(e))


@router.get("", response_model=UserIngredientListResponse)
async def get_user_ingredients(
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get all ingredients in user's inventory (delegates to group inventory)"""
    try:
        group_id = _get_user_group_id(db, user.user_id)
        ingredients = db.get_group_ingredients(group_id)

        ingredient_responses = []
        for ingredient in ingredients:
            ingredient_responses.append(
                UserIngredientResponse(
                    ingredient_id=ingredient["ingredient_id"],
                    name=ingredient["name"],
                    description=ingredient.get("description"),
                    parent_id=ingredient.get("parent_id"),
                    path=ingredient.get("path"),
                    added_at=ingredient["added_at"]
                )
            )

        return UserIngredientListResponse(
            ingredients=ingredient_responses,
            total_count=len(ingredient_responses)
        )

    except Exception as e:
        logger.error(f"Error getting user ingredients: {str(e)}")
        raise DatabaseException("Failed to retrieve user ingredients", detail=str(e))


@router.post("/bulk", response_model=UserIngredientBulkResponse, status_code=status.HTTP_201_CREATED)
async def add_user_ingredients_bulk(
    bulk_data: UserIngredientBulkAdd,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Add multiple ingredients to user's inventory (delegates to group inventory)"""
    try:
        group_id = _get_user_group_id(db, user.user_id)
        result = db.add_group_ingredients_bulk(group_id, user.user_id, bulk_data.ingredient_ids)

        return UserIngredientBulkResponse(
            added_count=result["added_count"],
            already_exists_count=result.get("already_exists_count"),
            failed_count=result.get("failed_count"),
            errors=result.get("errors", [])
        )

    except Exception as e:
        logger.error(f"Error bulk adding ingredients to user inventory: {str(e)}")
        raise DatabaseException("Failed to bulk add ingredients to inventory", detail=str(e))


@router.get("/recommendations", response_model=IngredientRecommendationListResponse)
async def get_ingredient_recommendations(
    limit: int = 20,
    db: Database = Depends(get_db),
    user: UserInfo = Depends(require_authentication),
):
    """Get ingredient recommendations (delegates to group recommendations)"""
    try:
        group_id = _get_user_group_id(db, user.user_id)
        recommendations = db.get_group_ingredient_recommendations(group_id, limit)

        recommendation_responses = []
        for rec in recommendations:
            recommendation_responses.append(
                IngredientRecommendationResponse(
                    id=rec["id"],
                    name=rec["name"],
                    description=rec.get("description"),
                    parent_id=rec.get("parent_id"),
                    path=rec.get("path"),
                    allow_substitution=rec.get("allow_substitution", False),
                    recipes_unlocked=rec["recipes_unlocked"],
                    recipe_names=rec["recipe_names"]
                )
            )

        return IngredientRecommendationListResponse(
            recommendations=recommendation_responses,
            total_count=len(recommendation_responses)
        )

    except Exception as e:
        logger.error(f"Error getting ingredient recommendations: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredient recommendations", detail=str(e))
```

- [ ] **Step 2: Run existing user ingredient tests to verify backward compatibility**

Run: `python -m pytest tests/test_db_user_ingredients.py -v --tb=short`

Expected: Any tests that directly call `db.add_user_ingredient()` and similar methods will FAIL because those methods still exist but are now wrappers. Actually, the DB methods still exist — the route change doesn't affect the DB layer. The existing DB tests should still pass since they call the old `user_ingredients` methods directly. Only if the tests go through the API route layer would they use the new flow.

Actually, the existing `test_db_user_ingredients.py` tests call `db.add_user_ingredient()` etc. directly — these still exist and work on the `user_ingredients` table. The route changes don't affect those tests. They should pass.

However, the REST API tests (if any exist in `test_api_integration.py`) will now go through `ensure_user_has_group` → `group_ingredients`. These need the group tables. We'll address integration tests in Task 9.

For now, run: `python -m pytest tests/test_db_user_ingredients.py -v --tb=short`

Expected: All existing DB tests PASS (they use `user_ingredients` table directly).

- [ ] **Step 3: Commit**

```bash
git add api/routes/user_ingredients.py
git commit -m "feat: repoint user-ingredients endpoints to group inventory as backward-compat wrappers"
```

---

## Task 8: Recipe Search Integration — Update SQL and Routes

**Files:**
- Modify: `api/db/sql_queries.py`
- Modify: `api/routes/recipes.py`

- [ ] **Step 1: Update inventory filter in `sql_queries.py` to accept `group_id`**

The `build_search_recipes_paginated_sql` and `build_search_recipes_keyset_sql` functions use `%(cognito_user_id)s` in the inventory filter. We need to support both the old `user_ingredients` table (for backward compatibility during migration) and the new `group_ingredients` table.

Replace the inventory filter sections in both functions. The filter currently reads from `user_ingredients` with `ui_check.cognito_user_id`. Change it to read from `group_ingredients` with `gi_check.group_id`.

In `build_search_recipes_paginated_sql`, find the inventory filter block (around line 191-209) and replace:

```python
    if inventory_filter:
        base_sql += """ AND r.id IN (
            SELECT r_inv.id
            FROM recipes r_inv
            WHERE r_inv.id = r.id
            AND NOT EXISTS (
                SELECT 1 FROM recipe_ingredients ri_missing
                LEFT JOIN ingredients i_recipe ON ri_missing.ingredient_id = i_recipe.id
                WHERE ri_missing.recipe_id = r_inv.id
                AND NOT EXISTS (
                    SELECT 1 FROM user_ingredients ui_check
                    LEFT JOIN ingredients i_user ON ui_check.ingredient_id = i_user.id
                    WHERE ui_check.cognito_user_id = %(cognito_user_id)s
                    AND (
                        {substitution_match}
                    )
                )
            )
        )"""
```

with:

```python
    if inventory_filter:
        base_sql += """ AND r.id IN (
            SELECT r_inv.id
            FROM recipes r_inv
            WHERE r_inv.id = r.id
            AND NOT EXISTS (
                SELECT 1 FROM recipe_ingredients ri_missing
                LEFT JOIN ingredients i_recipe ON ri_missing.ingredient_id = i_recipe.id
                WHERE ri_missing.recipe_id = r_inv.id
                AND NOT EXISTS (
                    SELECT 1 FROM group_ingredients gi_check
                    LEFT JOIN ingredients i_user ON gi_check.ingredient_id = i_user.id
                    WHERE gi_check.group_id = %(group_id)s
                    AND (
                        {substitution_match}
                    )
                )
            )
        )"""
```

Make the same change in `build_search_recipes_keyset_sql` (the inventory filter block around lines 342-360).

- [ ] **Step 2: Update the `recipes.py` route to resolve user's group**

In `api/routes/recipes.py`, wherever `inventory_filter` is set to `True`, add group resolution. Find where `cognito_user_id` is set for search params and add group resolution.

You'll need to:
1. Import `ensure_user_has_group` or call `db.ensure_user_has_group(user.user_id)` when inventory filtering is enabled
2. Pass `group_id` instead of (or in addition to) `cognito_user_id` to the search params

Locate the search endpoint and where `search_params["cognito_user_id"]` and `search_params["inventory"]` are set. Add:

```python
if search_params.get("inventory") and user:
    group = db.ensure_user_has_group(user.user_id)
    search_params["group_id"] = group["id"]
```

This needs to be done in the authenticated search endpoint. Check the exact code in `recipes.py` to find where these params are assembled.

- [ ] **Step 3: Update `get_ingredient_recommendations_sql` in `sql_queries.py`**

Already added the `get_group_ingredient_recommendations_sql` function in Task 5. The old `get_ingredient_recommendations_sql` still references `user_ingredients`. We'll keep both for now — the route layer will use the group version.

- [ ] **Step 4: Run existing recipe search tests**

Run: `python -m pytest tests/ -k "search" -v --tb=short`

Expected: Search tests may need group tables. If they fail due to missing tables, that's expected since the test schema needs updating. This will be addressed by updating conftest to include group tables.

- [ ] **Step 5: Commit**

```bash
git add api/db/sql_queries.py api/routes/recipes.py
git commit -m "feat: update recipe search and inventory filter to use group_ingredients"
```

---

## Task 9: Update Test Schema and Add Integration Tests

**Files:**
- Modify: `infrastructure/postgres/schema.sql` (already done in Task 1)
- Modify: `tests/conftest.py` (if needed for new fixtures)
- Create: `tests/test_api_groups.py`

- [ ] **Step 1: Verify test schema includes group tables**

Since `conftest.py` applies `schema.sql` for each test function (via `pg_db_with_schema` fixture), and we updated `schema.sql` in Task 1, the group tables should automatically be available in tests.

Run: `python -m pytest tests/test_db_groups.py -v --tb=short`

Expected: All group tests PASS.

- [ ] **Step 2: Create `tests/test_api_groups.py` for route integration tests**

```python
"""Integration tests for group management API endpoints"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture(scope="function")
async def groups_client(test_client_memory_with_app, mock_user):
    """Test client with mocked authentication for groups endpoints"""
    from dependencies.auth import UserInfo, require_authentication

    client, app = test_client_memory_with_app

    user_info = UserInfo(
        user_id=mock_user["user_id"],
        username=mock_user.get("username"),
        email=mock_user.get("email"),
        groups=mock_user.get("cognito:groups", []),
        claims=mock_user,
    )

    def override_require_authentication():
        return user_info

    app.dependency_overrides[require_authentication] = override_require_authentication

    yield client

    if require_authentication in app.dependency_overrides:
        del app.dependency_overrides[require_authentication]


@pytest.mark.asyncio
async def test_create_group(groups_client):
    """POST /groups creates a new group"""
    response = await groups_client.post(
        "/groups",
        json={"name": "Test Bar", "description": "A test group"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Bar"
    assert data["description"] == "A test group"
    assert "invite_code" in data


@pytest.mark.asyncio
async def test_get_my_group_auto_creates(groups_client):
    """GET /groups/mine auto-creates a group for the user"""
    response = await groups_client.get("/groups/mine")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "My Bar"
    assert data["member_count"] == 1


@pytest.mark.asyncio
async def test_update_group_name(groups_client):
    """PUT /groups/{id} updates group name"""
    response = await groups_client.get("/groups/mine")
    group_id = response.json()["id"]

    response = await groups_client.put(
        f"/groups/{group_id}",
        json={"name": "Renamed Bar"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Bar"


@pytest.mark.asyncio
async def test_regenerate_invite_code(groups_client):
    """POST /groups/{id}/invite-code/regenerate creates new code"""
    response = await groups_client.get("/groups/mine")
    group_id = response.json()["id"]
    old_code = response.json()["invite_code"]

    response = await groups_client.post(f"/groups/{group_id}/invite-code/regenerate")
    assert response.status_code == 200
    new_code = response.json()["invite_code"]
    assert new_code != old_code


@pytest.mark.asyncio
async def test_non_member_cannot_access_group(groups_client):
    """Non-member gets 403 when accessing group endpoints"""
    from dependencies.auth import UserInfo, require_authentication
    from api.main import app

    other_user = UserInfo(
        user_id="other-user-456",
        username="otheruser",
        email="other@example.com",
        groups=[],
        claims={"sub": "other-user-456"},
    )

    response = await groups_client.get("/groups/mine")
    group_id = response.json()["id"]

    app.dependency_overrides[require_authentication] = lambda: other_user

    response = await groups_client.put(
        f"/groups/{group_id}",
        json={"name": "Hack"},
    )
    assert response.status_code == 403

    del app.dependency_overrides[require_authentication]
```

- [ ] **Step 3: Run integration tests**

Run: `python -m pytest tests/test_api_groups.py -v --tb=short`

Expected: All group API integration tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_api_groups.py
git commit -m "test: add group API integration tests"
```

---

## Task 10: Frontend — API Client Methods

**Files:**
- Modify: `src/web/js/api.js`

- [ ] **Step 1: Add group API methods to `src/web/js/api.js`**

Add these methods to the `CocktailAPI` class in `api.js`, after the existing `getIngredientRecommendations` method (around line 442) and before the Stats API section:

```javascript
    // Groups API
    async getMyGroup() {
        return this._request('/groups/mine', 'GET', null, true);
    }

    async createGroup(data) {
        return this._request('/groups', 'POST', data, true);
    }

    async updateGroup(groupId, data) {
        return this._request(`/groups/${groupId}`, 'PUT', data, true);
    }

    async joinGroup(inviteCode) {
        return this._request('/groups/join', 'POST', { invite_code: inviteCode }, true);
    }

    async leaveGroup(groupId, copyInventory) {
        return this._request(`/groups/${groupId}/leave`, 'POST', { copy_inventory: copyInventory }, true);
    }

    async removeGroupMember(groupId, userId) {
        return this._request(`/groups/${groupId}/members/${userId}`, 'DELETE', null, true);
    }

    async regenerateInviteCode(groupId) {
        return this._request(`/groups/${groupId}/invite-code/regenerate`, 'POST', null, true);
    }

    async getGroupIngredients(groupId) {
        return this._request(`/groups/${groupId}/ingredients`, 'GET', null, true);
    }

    async addGroupIngredient(groupId, ingredientId) {
        return this._request(`/groups/${groupId}/ingredients`, 'POST', { ingredient_id: ingredientId }, true);
    }

    async removeGroupIngredient(groupId, ingredientId) {
        return this._request(`/groups/${groupId}/ingredients/${ingredientId}`, 'DELETE', null, true);
    }

    async bulkAddGroupIngredients(groupId, ingredientIds) {
        return this._request(`/groups/${groupId}/ingredients/bulk`, 'POST', { ingredient_ids: ingredientIds }, true);
    }

    async bulkRemoveGroupIngredients(groupId, ingredientIds) {
        return this._request(`/groups/${groupId}/ingredients/bulk`, 'DELETE', { ingredient_ids: ingredientIds }, true);
    }

    async getGroupRecommendations(groupId, limit = 20) {
        return this._request(`/groups/${groupId}/ingredients/recommendations?limit=${limit}`, 'GET', null, true);
    }
```

- [ ] **Step 2: Verify API client loads**

Run: `node -e "import('./src/web/js/api.js').then(() => console.log('API module loaded OK')).catch(e => console.error(e))"` (or check in browser). Since this is a module, just verify no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add src/web/js/api.js
git commit -m "feat: add group API client methods"
```

---

## Task 11: Frontend — Navigation Update

**Files:**
- Modify: `src/web/js/navigation.js`

- [ ] **Step 1: Update navigation configuration**

In `src/web/js/navigation.js`, update the `my-ingredients` nav item and add the groups nav item. Change the `shortLabel` of `my-ingredients` from `'My Bar'` to `'Ingredients'`, and add a new `groups` nav item after it:

Find the `my-ingredients` item (around line 33-42):

```javascript
    {
      id: 'my-ingredients',
      label: 'My Ingredients',
      shortLabel: 'My Bar',   // Shorter label for compact spaces
      href: 'user-ingredients.html',
      icon: '🍸',
      mobileBottom: true,
      mobileMenu: true,
      desktop: true,
      authRequired: true,
      adminOnly: false
    },
```

Change `shortLabel` from `'My Bar'` to `'Ingredients'`, and add a new item after it:

```javascript
    {
      id: 'my-ingredients',
      label: 'My Ingredients',
      shortLabel: 'Ingredients',
      href: 'user-ingredients.html',
      icon: '🍸',
      mobileBottom: false,
      mobileMenu: true,
      desktop: true,
      authRequired: true,
      adminOnly: false
    },
    {
      id: 'groups',
      label: 'My Bar',
      shortLabel: 'My Bar',
      href: 'groups.html',
      icon: '👥',
      mobileBottom: true,
      mobileMenu: true,
      desktop: true,
      authRequired: true,
      adminOnly: false
    },
```

Note: `my-ingredients` now has `mobileBottom: false` since "My Bar" takes the mobile bottom spot.

- [ ] **Step 2: Commit**

```bash
git add src/web/js/navigation.js
git commit -m "feat: add My Bar nav item, rename My Ingredients shortLabel"
```

---

## Task 12: Frontend — Groups Page HTML

**Files:**
- Create: `src/web/groups.html`

- [ ] **Step 1: Create `src/web/groups.html`**

```html
<!DOCTYPE html>
<html lang="en">

<head>
    <title>My Bar - Mixology Tools</title>
    <!-- Prevent FOUC (Flash of Unstyled Content) with common.js fallback -->
</head>

<body>
    <!-- Header will be loaded by common.js -->

    <main>
        <section class="page-header">
            <h2>My Bar</h2>
            <p>Share your bar inventory with family and housemates</p>
        </section>

        <div class="auth-required-content">
            <!-- Group Info -->
            <section class="group-info" id="group-info-section">
                <div class="section-header">
                    <h3 id="group-name-display">My Bar</h3>
                    <button id="edit-group-btn" class="btn btn-secondary">Edit</button>
                </div>
                <p id="group-description-display" class="group-description"></p>
                <p id="member-count-display" class="group-meta"></p>
            </section>

            <!-- Edit Group Form (hidden by default) -->
            <section class="group-edit-form hidden" id="group-edit-section">
                <div class="section-header">
                    <h3>Edit Group</h3>
                    <button id="cancel-edit-group-btn" class="btn btn-secondary">Cancel</button>
                </div>
                <form id="edit-group-form">
                    <div class="form-group">
                        <label for="group-name-input">Group Name</label>
                        <input type="text" id="group-name-input" maxlength="100" required />
                    </div>
                    <div class="form-group">
                        <label for="group-description-input">Description</label>
                        <textarea id="group-description-input" maxlength="500" rows="3"></textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">Save Changes</button>
                </form>
            </section>

            <!-- Invite Code -->
            <section class="invite-code-section">
                <div class="section-header">
                    <h3>Invite Code</h3>
                    <button id="regenerate-code-btn" class="btn btn-secondary">Regenerate</button>
                </div>
                <p class="invite-code-hint">Share this code with someone to invite them to your bar</p>
                <div class="invite-code-display" id="invite-code-display">
                    <code id="invite-code-text">Loading...</code>
                    <button id="copy-code-btn" class="btn btn-secondary">Copy</button>
                </div>
            </section>

            <!-- Join a Group -->
            <section class="join-group-section">
                <div class="section-header">
                    <h3>Join a Group</h3>
                </div>
                <div class="join-group-form">
                    <input type="text" id="join-code-input" placeholder="Enter invite code" maxlength="12" />
                    <button id="join-group-btn" class="btn btn-primary">Join</button>
                </div>
                <p class="join-warning">Joining another group will merge your current inventory into the new group.</p>
                <div id="join-group-message" class="message hidden"></div>
            </section>

            <!-- Members List -->
            <section class="members-section">
                <div class="section-header">
                    <h3 id="members-header">Members</h3>
                </div>
                <ul id="members-list" class="members-list">
                    <li class="loading-placeholder">Loading members...</li>
                </ul>
            </section>

            <!-- Leave Group -->
            <section class="leave-group-section hidden" id="leave-group-section">
                <div class="section-header">
                    <h3>Leave Group</h3>
                </div>
                <p id="leave-group-prompt"></p>
                <div class="leave-group-options">
                    <label>
                        <input type="checkbox" id="copy-inventory-checkbox" checked />
                        Copy ingredients from the group to your new personal bar
                    </label>
                </div>
                <button id="leave-group-btn" class="btn btn-danger">Leave Group</button>
                <div id="leave-group-message" class="message hidden"></div>
            </section>
        </div>

        <div class="auth-required-message hidden">
            <p>Please <button id="login-prompt-btn" class="btn btn-link">login</button> to manage your bar group.</p>
        </div>
    </main>

    <!-- Footer will be loaded by common.js -->

    <script type="module" src="js/common.js"></script>
    <script type="module" src="js/api.js"></script>
    <script type="module" src="js/groups.js"></script>
</body>

</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/web/groups.html
git commit -m "feat: add groups page HTML"
```

---

## Task 13: Frontend — Groups Manager JavaScript

**Files:**
- Create: `src/web/js/groups.js`

- [ ] **Step 1: Create `src/web/js/groups.js`**

```javascript
import api from './api.js';
import { isAuthenticated, getUserInfo } from './auth.js';

export class GroupsManager {
    constructor() {
        this.group = null;
        this.isEditing = false;
    }

    async init() {
        const authed = await isAuthenticated();
        if (!authed) {
            this.showAuthMessage();
            return;
        }

        this.bindEvents();
        await this.loadGroup();
    }

    bindEvents() {
        document.getElementById('edit-group-btn')?.addEventListener('click', () => this.showEditForm());
        document.getElementById('cancel-edit-group-btn')?.addEventListener('click', () => this.hideEditForm());
        document.getElementById('edit-group-form')?.addEventListener('submit', (e) => this.handleEditGroup(e));
        document.getElementById('regenerate-code-btn')?.addEventListener('click', () => this.handleRegenerateCode());
        document.getElementById('copy-code-btn')?.addEventListener('click', () => this.handleCopyCode());
        document.getElementById('join-group-btn')?.addEventListener('click', () => this.handleJoinGroup());
        document.getElementById('leave-group-btn')?.addEventListener('click', () => this.handleLeaveGroup());
        document.getElementById('login-prompt-btn')?.addEventListener('click', () => {
            window.location.href = 'index.html';
        });
    }

    async loadGroup() {
        try {
            this.group = await api.getMyGroup();
            this.renderGroup();
        } catch (error) {
            console.error('Error loading group:', error);
            this.showError('Failed to load group information.');
        }
    }

    renderGroup() {
        if (!this.group) return;

        document.getElementById('group-name-display').textContent = this.group.name;
        document.getElementById('group-description-display').textContent = this.group.description || '';
        document.getElementById('member-count-display').textContent =
            `${this.group.member_count} member${this.group.member_count !== 1 ? 's' : ''}`;
        document.getElementById('invite-code-text').textContent = this.group.invite_code;

        this.renderMembers();

        const leaveSection = document.getElementById('leave-group-section');
        if (this.group.member_count > 1) {
            leaveSection.classList.remove('hidden');
            document.getElementById('leave-group-prompt').textContent =
                `Leave "${this.group.name}"? You will get a new personal bar.`;
        } else {
            leaveSection.classList.add('hidden');
        }
    }

    renderMembers() {
        const list = document.getElementById('members-list');
        if (!this.group || !this.group.members) {
            list.innerHTML = '<li>Loading members...</li>';
            return;
        }

        const userInfo = getUserInfo();
        const currentUserId = userInfo?.cognitoUserId;

        list.innerHTML = this.group.members.map(member => {
            const isCurrentUser = member.cognito_user_id === currentUserId;
            const displayName = isCurrentUser ? `${member.cognito_user_id} (you)` : member.cognito_user_id;
            const removeButton = !isCurrentUser && this.group.member_count > 1
                ? `<button class="btn btn-danger btn-sm remove-member-btn" data-user-id="${member.cognito_user_id}">Remove</button>`
                : '';
            return `<li class="member-item">
                <span class="member-name">${displayName}</span>
                ${removeButton}
            </li>`;
        }).join('');

        list.querySelectorAll('.remove-member-btn').forEach(btn => {
            btn.addEventListener('click', () => this.handleRemoveMember(btn.dataset.userId));
        });
    }

    showEditForm() {
        document.getElementById('group-info-section').classList.add('hidden');
        document.getElementById('group-edit-section').classList.remove('hidden');
        document.getElementById('group-name-input').value = this.group.name;
        document.getElementById('group-description-input').value = this.group.description || '';
        this.isEditing = true;
    }

    hideEditForm() {
        document.getElementById('group-info-section').classList.remove('hidden');
        document.getElementById('group-edit-section').classList.add('hidden');
        this.isEditing = false;
    }

    async handleEditGroup(event) {
        event.preventDefault();
        const name = document.getElementById('group-name-input').value.trim();
        const description = document.getElementById('group-description-input').value.trim();

        try {
            const updated = await api.updateGroup(this.group.id, { name, description });
            this.group = { ...this.group, ...updated };
            this.renderGroup();
            this.hideEditForm();
        } catch (error) {
            console.error('Error updating group:', error);
            this.showError('Failed to update group.');
        }
    }

    async handleRegenerateCode() {
        if (!confirm('Are you sure? The old invite code will no longer work.')) return;

        try {
            const updated = await api.regenerateInviteCode(this.group.id);
            this.group = { ...this.group, ...updated };
            this.renderGroup();
        } catch (error) {
            console.error('Error regenerating invite code:', error);
            this.showError('Failed to regenerate invite code.');
        }
    }

    async handleCopyCode() {
        const code = this.group.invite_code;
        try {
            await navigator.clipboard.writeText(code);
            const btn = document.getElementById('copy-code-btn');
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
        } catch {
            const input = document.getElementById('join-code-input');
            input.value = code;
            input.select();
        }
    }

    async handleJoinGroup() {
        const code = document.getElementById('join-code-input').value.trim();
        if (!code) {
            this.showMessage('join-group-message', 'Please enter an invite code.', 'error');
            return;
        }

        try {
            const result = await api.joinGroup(code);
            this.group = result;
            this.renderGroup();
            document.getElementById('join-code-input').value = '';
            this.showMessage('join-group-message', 'Successfully joined the group!', 'success');
        } catch (error) {
            console.error('Error joining group:', error);
            this.showMessage('join-group-message', 'Failed to join group. Check the invite code.', 'error');
        }
    }

    async handleRemoveMember(userId) {
        if (!confirm(`Remove this member from the group?`)) return;

        try {
            await api.removeGroupMember(this.group.id, userId);
            await this.loadGroup();
        } catch (error) {
            console.error('Error removing member:', error);
            this.showError('Failed to remove member.');
        }
    }

    async handleLeaveGroup() {
        const copyInventory = document.getElementById('copy-inventory-checkbox').checked;
        if (!confirm(`Are you sure you want to leave "${this.group.name}"?`)) return;

        try {
            const newGroup = await api.leaveGroup(this.group.id, copyInventory);
            this.group = newGroup;
            this.renderGroup();
            this.showMessage('leave-group-message', 'You have left the group.', 'success');
        } catch (error) {
            console.error('Error leaving group:', error);
            this.showMessage('leave-group-message', 'Failed to leave group.', 'error');
        }
    }

    showMessage(elementId, text, type) {
        const el = document.getElementById(elementId);
        if (!el) return;
        el.textContent = text;
        el.className = `message ${type}`;
        el.classList.remove('hidden');
        setTimeout(() => el.classList.add('hidden'), 5000);
    }

    showError(text) {
        console.error(text);
    }

    showAuthMessage() {
        document.querySelector('.auth-required-content')?.classList.add('hidden');
        document.querySelector('.auth-required-message')?.classList.remove('hidden');
    }
}

const manager = new GroupsManager();
manager.init();
```

- [ ] **Step 2: Commit**

```bash
git add src/web/js/groups.js
git commit -m "feat: add GroupsManager class with full group management UI"
```

---

## Task 14: Frontend — Update Inventory Page Group Banner

**Files:**
- Modify: `src/web/user-ingredients.html`
- Modify: `src/web/js/user-ingredients.js`

- [ ] **Step 1: Add group banner to `src/web/user-ingredients.html`**

In `user-ingredients.html`, add a group banner after the `<h2>` tag in the page header and before the `auth-required-content` div. Find (around line 13-16):

```html
<section class="page-header">
    <h2>My Ingredients & Tags</h2>
    <p>Manage your personal ingredient inventory and private tags</p>
</section>
```

Change to:

```html
<section class="page-header">
    <h2>My Ingredients & Tags</h2>
    <p>Manage your personal ingredient inventory and private tags</p>
</section>

<div class="auth-required-content">
    <div id="group-banner" class="group-banner hidden">
        <p>You're viewing inventory for <strong id="group-name-link"></strong></p>
    </div>
```

And close the `<div>` before the `auth-required-message` section. The HTML structure should have the group banner inside the `auth-required-content` div, before the `current-ingredients` section.

- [ ] **Step 2: Add group name population to `src/web/js/user-ingredients.js`**

In the `UserIngredientsManager.init()` method (around line 23-35), after checking auth and before loading data, add a call to load the group name:

Add this method to the class:

```javascript
async loadGroupBanner() {
    try {
        const group = await api.getMyGroup();
        const banner = document.getElementById('group-banner');
        const link = document.getElementById('group-name-link');
        if (banner && link) {
            link.textContent = group.name;
            link.style.cursor = 'pointer';
            link.style.textDecoration = 'underline';
            link.addEventListener('click', () => {
                window.location.href = 'groups.html';
            });
            banner.classList.remove('hidden');
        }
    } catch (error) {
        // Silently ignore - group banner is not critical
        console.debug('Could not load group banner:', error);
    }
}
```

Call `this.loadGroupBanner()` in the `init()` method, after setting up auth and before `this.loadData()`.

- [ ] **Step 3: Commit**

```bash
git add src/web/user-ingredients.html src/web/js/user-ingredients.js
git commit -m "feat: add group name banner to inventory page"
```

---

## Task 15: Run Full Test Suite and Verify

**Files:**
- No new files

- [ ] **Step 1: Run all existing tests to verify no regressions**

Run: `python -m pytest tests/ -v --tb=short`

Expected: All existing tests that don't require the group tables should PASS. Any test that uses the API routes (which now call `ensure_user_has_group`) will create group tables via the schema.sql which was updated.

If any tests fail, investigate and fix.

- [ ] **Step 2: Run the new group-specific tests**

Run: `python -m pytest tests/test_db_groups.py tests/test_api_groups.py -v --tb=short`

Expected: All group tests PASS.

- [ ] **Step 3: Verify the frontend loads**

Start the dev server: `npx live-server src/web --port=8000` (or `./scripts/serve.sh`)

Open the browser and verify:
1. The "My Bar" nav item appears
2. The groups page loads and shows group info
3. The inventory page shows the group banner

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: resolve any regression issues from group integration"
```

---

## Self-Review Checklist

- [ ] **Spec coverage — Phase 1 (Schema & Group CRUD):** Migration file created (Task 1), models added (Task 2), DB methods implemented (Tasks 3-4), routes created (Task 6), auto-creation handled via `ensure_user_has_group` (Task 3), race condition handled via IntegrityError catch (Task 3)
- [ ] **Spec coverage — Phase 2 (Group Inventory):** Group ingredient methods implemented (Task 5), user_ingredients routes repointed (Task 7), group inventory routes added (Task 6)
- [ ] **Spec coverage — Phase 3 (Recipe Search):** SQL updated to use `group_ingredients` (Task 8), route resolves group_id (Task 8)
- [ ] **Spec coverage — Phase 4 (Frontend):** API client methods (Task 10), navigation updated (Task 11), groups page HTML+JS (Tasks 12-13), inventory banner (Task 14)
- [ ] **Placeholder scan:** No TBD, TODO, or "implement later" in any task step
- [ ] **Type consistency:** `ensure_user_has_group` returns dict with `id`, `name`, `description`, `invite_code` — consistent across all callers. `GroupResponse` and `GroupDetailResponse` use the same field names
- [ ] **Migration safety:** Migration handles existing `user_ingredients` data, uses temp table pattern, and doesn't drop the old table