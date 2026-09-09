"""Transactional bar membership and inventory operations.

All operations use one transaction-scoped lock. Helpers accept its cursor so
membership checks and the operation cannot be separated by a concurrent move.
"""

from contextlib import contextmanager
import secrets

from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor

from core.exceptions import (
    CocktailDBException,
    ConflictException,
    NotFoundException,
    ValidationException,
)


class GroupInventoryMixin:
    @contextmanager
    def _group_transaction(self):
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(73421, 1)")
                    yield cursor
        finally:
            self._return_connection(conn)

    @staticmethod
    def _membership(cursor, user_id):
        cursor.execute(
            "SELECT group_id FROM user_group_members WHERE cognito_user_id=%s",
            (user_id,),
        )
        row = cursor.fetchone()
        return row["group_id"] if row else None

    def _require_membership(self, cursor, user_id, group_id):
        if self._membership(cursor, user_id) != group_id:
            raise CocktailDBException(
                "You are not a member of this group", status_code=403
            )

    @staticmethod
    def _group_detail(cursor, group_id):
        cursor.execute("SELECT * FROM user_groups WHERE id=%s", (group_id,))
        row = cursor.fetchone()
        if row is None:
            raise NotFoundException("Group not found")
        detail = dict(row)
        cursor.execute(
            "SELECT cognito_user_id, joined_at FROM user_group_members WHERE group_id=%s ORDER BY joined_at, cognito_user_id",
            (group_id,),
        )
        detail["members"] = [dict(member) for member in cursor.fetchall()]
        detail["member_count"] = len(detail["members"])
        return detail

    @staticmethod
    def _new_invite(cursor, statement, params):
        # Retry only a collision on the invitation's unique constraint.
        for _ in range(5):
            cursor.execute("SAVEPOINT invite_code")
            try:
                cursor.execute(statement, (secrets.token_hex(6), *params))
                result = cursor.fetchone()
            except IntegrityError as error:
                cursor.execute("ROLLBACK TO SAVEPOINT invite_code")
                cursor.execute("RELEASE SAVEPOINT invite_code")
                if error.diag.constraint_name != "user_groups_invite_code_key":
                    raise
            else:
                cursor.execute("RELEASE SAVEPOINT invite_code")
                return result["id"]
        raise ConflictException("Could not generate a unique invite code; please retry")

    def _create_personal_group(self, cursor, name="My Bar", description=None):
        return self._new_invite(
            cursor,
            "INSERT INTO user_groups (invite_code,name,description) VALUES (%s,%s,%s) RETURNING id",
            (name, description),
        )

    def _ensure_group(self, cursor, user_id):
        group_id = self._membership(cursor, user_id)
        if group_id is None:
            group_id = self._create_personal_group(cursor)
            cursor.execute(
                "INSERT INTO user_group_members (group_id,cognito_user_id) VALUES (%s,%s)",
                (group_id, user_id),
            )
        return group_id

    def ensure_user_has_group(self, user_id):
        with self._group_transaction() as cursor:
            return self._group_detail(cursor, self._ensure_group(cursor, user_id))

    def get_user_group(self, user_id):
        with self._group_transaction() as cursor:
            group_id = self._membership(cursor, user_id)
            return (
                self._group_detail(cursor, group_id) if group_id is not None else None
            )

    def create_group(self, user_id, name, description=None):
        with self._group_transaction() as cursor:
            if self._membership(cursor, user_id) is not None:
                raise ConflictException("You already have a bar; rename it instead")
            group_id = self._create_personal_group(cursor, name, description)
            cursor.execute(
                "INSERT INTO user_group_members (group_id,cognito_user_id) VALUES (%s,%s)",
                (group_id, user_id),
            )
            return self._group_detail(cursor, group_id)

    def get_group_detail(self, actor_user_id, group_id):
        with self._group_transaction() as cursor:
            self._require_membership(cursor, actor_user_id, group_id)
            return self._group_detail(cursor, group_id)

    def update_group(self, actor_user_id, group_id, changes):
        with self._group_transaction() as cursor:
            self._require_membership(cursor, actor_user_id, group_id)
            # Column names are selected only from this fixed allowlist.
            fields = [key for key in ("name", "description") if key in changes]
            if fields:
                assignments = ", ".join(f"{key}=%s" for key in fields)
                cursor.execute(
                    f"UPDATE user_groups SET {assignments} WHERE id=%s",
                    (*[changes[key] for key in fields], group_id),
                )
            return self._group_detail(cursor, group_id)

    def regenerate_invite_code(self, actor_user_id, group_id):
        with self._group_transaction() as cursor:
            self._require_membership(cursor, actor_user_id, group_id)
            self._new_invite(
                cursor,
                "UPDATE user_groups SET invite_code=%s WHERE id=%s RETURNING id",
                (group_id,),
            )
            return self._group_detail(cursor, group_id)

    @staticmethod
    def _copy_inventory(cursor, source, destination):
        cursor.execute(
            """INSERT INTO group_ingredients (group_id,ingredient_id,added_by,added_at)
            SELECT %s,ingredient_id,added_by,added_at FROM group_ingredients WHERE group_id=%s
            ON CONFLICT (group_id,ingredient_id) DO NOTHING""",
            (destination, source),
        )

    @staticmethod
    def _move_membership(cursor, user_id, source, destination):
        if source is None:
            cursor.execute(
                "INSERT INTO user_group_members (cognito_user_id,group_id) VALUES (%s,%s)",
                (user_id, destination),
            )
        else:
            cursor.execute(
                "UPDATE user_group_members SET group_id=%s,joined_at=CURRENT_TIMESTAMP WHERE cognito_user_id=%s AND group_id=%s",
                (destination, user_id, source),
            )
        if cursor.rowcount != 1:
            raise ConflictException("Group membership changed; please reload")

    def join_group_by_code(self, user_id, invite_code):
        with self._group_transaction() as cursor:
            cursor.execute(
                """SELECT id FROM user_groups WHERE invite_code=%s
                AND EXISTS (SELECT 1 FROM user_group_members WHERE group_id=user_groups.id)""",
                (invite_code,),
            )
            row = cursor.fetchone()
            if row is None:
                raise NotFoundException("Invite code not found")
            destination = row["id"]
            source = self._membership(cursor, user_id)
            if source != destination:
                if source is not None:
                    self._copy_inventory(cursor, source, destination)
                self._move_membership(cursor, user_id, source, destination)
            return self._group_detail(cursor, destination)

    def _leave_group(self, cursor, user_id, group_id, copy_inventory):
        destination = self._create_personal_group(cursor)
        if copy_inventory:
            self._copy_inventory(cursor, group_id, destination)
        self._move_membership(cursor, user_id, group_id, destination)
        return self._group_detail(cursor, destination)

    def leave_group(self, user_id, group_id, copy_inventory):
        with self._group_transaction() as cursor:
            self._require_membership(cursor, user_id, group_id)
            if self._group_detail(cursor, group_id)["member_count"] <= 1:
                raise ConflictException(
                    "You are the only member; rename your bar instead"
                )
            return self._leave_group(cursor, user_id, group_id, copy_inventory)

    def remove_group_member(self, actor_user_id, group_id, target_user_id):
        with self._group_transaction() as cursor:
            self._require_membership(cursor, actor_user_id, group_id)
            if actor_user_id == target_user_id:
                raise ValidationException("Use leave to remove yourself from a group")
            if self._membership(cursor, target_user_id) != group_id:
                raise NotFoundException("Member not found")
            self._leave_group(cursor, target_user_id, group_id, True)
            return True

    def _inventory_operation(self, operation, user_id, group_id, *args):
        with self._group_transaction() as cursor:
            if group_id is None:
                group_id = self._ensure_group(cursor, user_id)
            else:
                self._require_membership(cursor, user_id, group_id)
            return operation(cursor, user_id, group_id, *args)

    @staticmethod
    def _list_inventory(cursor, user_id, group_id):
        cursor.execute(
            """SELECT gi.ingredient_id,gi.added_at,i.name,i.description,i.parent_id,i.path
            FROM group_ingredients gi JOIN ingredients i ON i.id=gi.ingredient_id
            WHERE gi.group_id=%s ORDER BY i.name""",
            (group_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _add_inventory(cursor, user_id, group_id, ingredient_id):
        cursor.execute(
            "SELECT id,name,path FROM ingredients WHERE id=%s", (ingredient_id,)
        )
        ingredient = cursor.fetchone()
        if ingredient is None:
            raise ValueError(f"Ingredient with ID {ingredient_id} does not exist")
        cursor.execute(
            "SELECT 1 FROM group_ingredients WHERE group_id=%s AND ingredient_id=%s",
            (group_id, ingredient_id),
        )
        if cursor.fetchone():
            raise ValueError(
                f"Ingredient {ingredient_id} already exists in user's inventory"
            )
        parents = [
            int(value) for value in (ingredient["path"] or "").split("/") if value
        ][:-1]
        for parent in parents:
            cursor.execute(
                """INSERT INTO group_ingredients (group_id,ingredient_id,added_by) VALUES (%s,%s,%s)
                ON CONFLICT (group_id,ingredient_id) DO NOTHING""",
                (group_id, parent, user_id),
            )
        cursor.execute(
            "INSERT INTO group_ingredients (group_id,ingredient_id,added_by) VALUES (%s,%s,%s) RETURNING added_at",
            (group_id, ingredient_id, user_id),
        )
        return {
            "ingredient_id": ingredient_id,
            "ingredient_name": ingredient["name"],
            "added_at": cursor.fetchone()["added_at"],
            "parents_added": len(parents),
        }

    @staticmethod
    def _bulk_add_inventory(cursor, user_id, group_id, ingredient_ids):
        result = {
            "added_count": 0,
            "already_exists_count": 0,
            "failed_count": 0,
            "errors": [],
        }
        for ingredient_id in ingredient_ids:
            cursor.execute("SELECT 1 FROM ingredients WHERE id=%s", (ingredient_id,))
            if cursor.fetchone() is None:
                result["failed_count"] += 1
                result["errors"].append(
                    f"Ingredient with ID {ingredient_id} does not exist"
                )
                continue
            cursor.execute(
                """INSERT INTO group_ingredients (group_id,ingredient_id,added_by) VALUES (%s,%s,%s)
                ON CONFLICT (group_id,ingredient_id) DO NOTHING""",
                (group_id, ingredient_id, user_id),
            )
            result["added_count" if cursor.rowcount else "already_exists_count"] += 1
        return result

    @staticmethod
    def _bulk_remove_inventory(cursor, user_id, group_id, ingredient_ids):
        # Validate the whole set before writing, so unselected descendants block it.
        cursor.execute(
            """SELECT gi.ingredient_id,i.name,i.path FROM group_ingredients gi
            JOIN ingredients i ON i.id=gi.ingredient_id WHERE gi.group_id=%s""",
            (group_id,),
        )
        inventory = {row["ingredient_id"]: dict(row) for row in cursor.fetchall()}
        requested = set(ingredient_ids)
        selected = requested.intersection(inventory)
        for ingredient_id in selected:
            ingredient = inventory[ingredient_id]
            children = [
                row["name"]
                for key, row in inventory.items()
                if key not in requested
                and ingredient["path"]
                and row["path"]
                and row["path"].startswith(ingredient["path"])
            ]
            if children:
                raise ValueError(
                    f"Cannot remove ingredient '{ingredient['name']}' because it has child ingredients in your inventory: {', '.join(children)}. Please remove the child ingredients first."
                )
        removed = 0
        for ingredient_id in sorted(
            selected, key=lambda key: len(inventory[key]["path"] or ""), reverse=True
        ):
            cursor.execute(
                "DELETE FROM group_ingredients WHERE group_id=%s AND ingredient_id=%s",
                (group_id, ingredient_id),
            )
            removed += cursor.rowcount
        return {
            "removed_count": removed,
            "not_found_count": sum(1 for key in ingredient_ids if key not in inventory),
        }

    def _remove_inventory(self, cursor, user_id, group_id, ingredient_id):
        return bool(
            self._bulk_remove_inventory(cursor, user_id, group_id, [ingredient_id])[
                "removed_count"
            ]
        )

    @staticmethod
    def _recommend_inventory(cursor, user_id, group_id, limit=20):
        from .sql_queries import get_ingredient_recommendations_sql

        cursor.execute(
            get_ingredient_recommendations_sql(), {"group_id": group_id, "limit": limit}
        )
        result = [dict(row) for row in cursor.fetchall()]
        for row in result:
            row["recipe_names"] = (
                row["recipe_names"].split("|||") if row.get("recipe_names") else []
            )
        return result

    def get_group_ingredients(self, actor_user_id, group_id):
        return self._inventory_operation(self._list_inventory, actor_user_id, group_id)

    def add_group_ingredient(self, actor_user_id, group_id, ingredient_id):
        return self._inventory_operation(
            self._add_inventory, actor_user_id, group_id, ingredient_id
        )

    def remove_group_ingredient(self, actor_user_id, group_id, ingredient_id):
        return self._inventory_operation(
            self._remove_inventory, actor_user_id, group_id, ingredient_id
        )

    def add_group_ingredients_bulk(self, actor_user_id, group_id, ingredient_ids):
        return self._inventory_operation(
            self._bulk_add_inventory, actor_user_id, group_id, ingredient_ids
        )

    def remove_group_ingredients_bulk(self, actor_user_id, group_id, ingredient_ids):
        return self._inventory_operation(
            self._bulk_remove_inventory, actor_user_id, group_id, ingredient_ids
        )

    def get_group_ingredient_recommendations(self, actor_user_id, group_id, limit=20):
        return self._inventory_operation(
            self._recommend_inventory, actor_user_id, group_id, limit
        )

    def get_user_ingredients(self, user_id):
        return self._inventory_operation(self._list_inventory, user_id, None)

    def add_user_ingredient(self, user_id, ingredient_id):
        return self._inventory_operation(
            self._add_inventory, user_id, None, ingredient_id
        )

    def remove_user_ingredient(self, user_id, ingredient_id):
        return self._inventory_operation(
            self._remove_inventory, user_id, None, ingredient_id
        )

    def add_user_ingredients_bulk(self, user_id, ingredient_ids):
        return self._inventory_operation(
            self._bulk_add_inventory, user_id, None, ingredient_ids
        )

    def remove_user_ingredients_bulk(self, user_id, ingredient_ids):
        return self._inventory_operation(
            self._bulk_remove_inventory, user_id, None, ingredient_ids
        )

    def get_ingredient_recommendations(self, user_id, limit=20):
        return self._inventory_operation(
            self._recommend_inventory, user_id, None, limit
        )
