import base64
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Tuple, cast

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

from .db_utils import extract_all_ingredient_ids, assemble_ingredient_full_names
from .sql_queries import (
    get_recipe_by_id_sql,
    get_all_recipes_sql,
    get_recipe_ingredients_by_recipe_id_sql_factory,
    get_recipes_count_sql,
    get_ingredients_count_sql,
    INGREDIENT_SELECT_FIELDS,
)
from core.exceptions import ConflictException, ValidationException

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


class Database:
    # Class-level connection pool (shared across instances)
    _pool: pool.ThreadedConnectionPool = None

    def __init__(self):
        """Initialize the database connection to PostgreSQL"""
        logger.info("Initializing Database class with PostgreSQL")
        try:
            # Read connection parameters from environment variables
            self.conn_params = {
                'host': os.environ.get('DB_HOST', 'localhost'),
                'port': os.environ.get('DB_PORT', '5432'),
                'dbname': os.environ.get('DB_NAME', 'cocktaildb'),
                'user': os.environ.get('DB_USER', 'cocktaildb'),
                'password': os.environ.get('DB_PASSWORD', ''),
            }
            logger.info(
                f"PostgreSQL connection: {self.conn_params['host']}:{self.conn_params['port']}/{self.conn_params['dbname']}"
            )

            # Initialize the connection pool if not already done
            self._init_pool()

            # Test the connection
            self._test_connection()
            logger.info("Database initialization complete using PostgreSQL")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}", exc_info=True)
            raise

    def _init_pool(self):
        """Initialize the connection pool if not already initialized"""
        if Database._pool is None:
            logger.info("Creating new PostgreSQL connection pool")
            Database._pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                **self.conn_params
            )

    def _test_connection(self):
        """Test the database connection"""
        logger.info("Testing database connection...")
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            logger.info("Successfully connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}", exc_info=True)
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def _get_connection(self):
        """Get a connection from the pool"""
        return Database._pool.getconn()

    def _return_connection(self, conn):
        """Return a connection to the pool"""
        if Database._pool and conn:
            Database._pool.putconn(conn)

    def execute_query(
        self, sql: str, parameters: Optional[Union[Dict[str, Any], Tuple]] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, int]]:
        """Execute a SQL query using PostgreSQL"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)

            if sql.strip().upper().startswith(("SELECT", "WITH")):
                # For SELECT queries, return results
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
                cursor.close()
                return result
            else:
                # For non-SELECT queries, commit and return affected rows
                conn.commit()
                row_count = cursor.rowcount
                cursor.close()
                return {"rowCount": row_count}
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error executing query: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def execute_transaction(self, queries: List[Dict[str, Any]]) -> None:
        """Execute multiple queries in a transaction"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            for query in queries:
                sql = query.get("sql")
                params = query.get("parameters", {})
                if sql is not None:
                    cursor.execute(sql, params)

            conn.commit()
            cursor.close()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error executing transaction: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def create_ingredient(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new ingredient"""
        try:
            # Validate required data types
            name = data.get("name")
            if not isinstance(name, str):
                raise TypeError(
                    f"Ingredient name must be a string, got {type(name).__name__}"
                )
            if not name.strip():
                raise ValueError("Ingredient name cannot be empty or whitespace only")

            if data.get("description") is not None and not isinstance(
                data.get("description"), str
            ):
                raise TypeError(
                    f"Ingredient description must be a string or None, got {type(data.get('description')).__name__}"
                )

            if data.get("parent_id") is not None and not isinstance(
                data.get("parent_id"), int
            ):
                raise TypeError(
                    f"Ingredient parent_id must be an integer or None, got {type(data.get('parent_id')).__name__}"
                )

            # Implement the hierarchical path generation logic in Python
            parent_path = None
            if data.get("parent_id"):
                # Get parent's path
                parent = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        "SELECT path FROM ingredients WHERE id = %(parent_id)s",
                        {"parent_id": data.get("parent_id")},
                    ),
                )
                if not parent:
                    raise ValueError(
                        f"Parent ingredient with ID {data.get('parent_id')} does not exist"
                    )
                parent_path = parent[0]["path"]

            # Insert the ingredient first
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO ingredients (name, description, parent_id, allow_substitution)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        data.get("name"),
                        data.get("description"),
                        data.get("parent_id"),
                        data.get("allow_substitution", False),
                    ),
                )
                new_row = cursor.fetchone()
                if not new_row or new_row[0] is None:
                    raise ValueError("Failed to get ingredient ID after insertion")
                new_id = new_row[0]

                # Generate the path
                if parent_path:
                    path = f"{parent_path}{new_id}/"
                else:
                    path = f"/{new_id}/"

                # Update the path
                cursor.execute(
                    "UPDATE ingredients SET path = %s WHERE id = %s",
                    (path, new_id),
                )

                conn.commit()

                # Fetch the created ingredient
                ingredient = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        "SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients WHERE id = %(id)s",
                        {"id": new_id},
                    ),
                )
                return ingredient[0]
            except psycopg2.IntegrityError as e:
                if conn:
                    conn.rollback()
                error_msg = str(e).lower()
                # Check if it's a UNIQUE constraint violation on the name field
                if "unique" in error_msg and "name" in error_msg:
                    raise ConflictException(
                        f"An ingredient with the name '{data.get('name')}' already exists. Please use a different name.",
                        detail=str(e),
                    )
                # Re-raise other integrity errors
                raise
            except Exception:
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    self._return_connection(conn)
        except ConflictException:
            # Re-raise ConflictException without wrapping it
            raise
        except Exception as e:
            logger.error(f"Error creating ingredient: {str(e)}")
            raise

    def update_ingredient(
        self, ingredient_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing ingredient"""
        try:
            # Check if changing parent_id, as this affects the path
            if "parent_id" in data:
                old_ingredient = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        "SELECT parent_id, path FROM ingredients WHERE id = %(id)s",
                        {"id": ingredient_id},
                    ),
                )

                if not old_ingredient:
                    return None
                old_path = old_ingredient[0]["path"]
                new_parent_id = data.get("parent_id")

                # Check for circular reference
                if new_parent_id:
                    # Cannot be its own parent
                    if int(new_parent_id) == ingredient_id:
                        raise ValueError("Ingredient cannot be its own parent")

                    # Check if new parent exists
                    parent = cast(
                        List[Dict[str, Any]],
                        self.execute_query(
                            "SELECT path FROM ingredients WHERE id = %(id)s",
                            {"id": new_parent_id},
                        ),
                    )
                    if not parent:
                        raise ValueError(
                            f"Parent ingredient with ID {new_parent_id} does not exist"
                        )

                    # Check if new parent is not a descendant
                    descendants = self.get_ingredient_descendants(ingredient_id)
                    if any(d["id"] == new_parent_id for d in descendants):
                        raise ValueError(
                            "Cannot create circular reference in hierarchy"
                        )

                    # Calculate new path
                    new_path = f"{parent[0]['path']}{ingredient_id}/"
                else:
                    # Root level ingredient
                    new_path = f"/{ingredient_id}/"

                # Get descendants BEFORE updating the parent path
                descendants = self.get_ingredient_descendants(ingredient_id)

                # Build the update query dynamically to handle None values properly
                set_clauses = [
                    "name = COALESCE(%(name)s, name)",
                    "description = COALESCE(%(description)s, description)",
                    "parent_id = %(parent_id)s",
                    "path = %(path)s",
                ]
                query_params = {
                    "id": ingredient_id,
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "parent_id": new_parent_id,
                    "path": new_path,
                }

                # Handle allow_substitution explicitly
                if "allow_substitution" in data:
                    set_clauses.append("allow_substitution = %(allow_substitution)s")
                    query_params["allow_substitution"] = data.get("allow_substitution")

                # Update ingredient with new path
                self.execute_query(
                    f"""
                    UPDATE ingredients
                    SET {", ".join(set_clauses)}
                    WHERE id = %(id)s
                    """,
                    query_params,
                )

                # Update paths of descendants
                for descendant in descendants:
                    # Replace old path prefix with new path prefix
                    descendant_path = descendant["path"]
                    new_descendant_path = descendant_path.replace(old_path, new_path)

                    self.execute_query(
                        "UPDATE ingredients SET path = %(path)s WHERE id = %(id)s",
                        {"path": new_descendant_path, "id": descendant["id"]},
                    )
            else:
                # Simple update without changing the hierarchy
                # Build the update query dynamically to handle None values properly
                set_clauses = [
                    "name = COALESCE(%(name)s, name)",
                    "description = COALESCE(%(description)s, description)",
                ]
                query_params = {
                    "id": ingredient_id,
                    "name": data.get("name"),
                    "description": data.get("description"),
                }

                # Handle allow_substitution explicitly
                if "allow_substitution" in data:
                    set_clauses.append("allow_substitution = %(allow_substitution)s")
                    query_params["allow_substitution"] = data.get("allow_substitution")

                self.execute_query(
                    f"""
                    UPDATE ingredients
                    SET {", ".join(set_clauses)}
                    WHERE id = %(id)s
                    """,
                    query_params,
                )

            # Fetch the updated ingredient
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients WHERE id = %(id)s",
                    {"id": ingredient_id},
                ),
            )
            if result:
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error updating ingredient {ingredient_id}: {str(e)}")
            raise

    def delete_ingredient(self, ingredient_id: int) -> bool:
        """Delete an ingredient"""
        try:
            # Check if ingredient exists
            ingredient = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM ingredients WHERE id = %(id)s", {"id": ingredient_id}
                ),
            )
            if not ingredient:
                return False

            # Check if it has children
            children = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM ingredients WHERE parent_id = %(parent_id)s",
                    {"parent_id": ingredient_id},
                ),
            )
            if children:
                raise ValueError("Cannot delete ingredient with child ingredients")

            # Check if it's used in recipes
            used_in_recipes = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT recipe_id FROM recipe_ingredients WHERE ingredient_id = %(ingredient_id)s LIMIT 1",
                    {"ingredient_id": ingredient_id},
                ),
            )
            if used_in_recipes:
                raise ValueError("Cannot delete ingredient used in recipes")

            # Delete the ingredient
            self.execute_query(
                "DELETE FROM ingredients WHERE id = %(id)s", {"id": ingredient_id}
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting ingredient {ingredient_id}: {str(e)}")
            raise

    def get_ingredients(self) -> List[Dict[str, Any]]:
        """Get all ingredients"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients ORDER BY path"
                ),
            )
            return result
        except Exception as e:
            logger.error(f"Error getting ingredients: {str(e)}")
            raise

    def get_ingredient_by_name(self, ingredient_name: str) -> Optional[Dict[str, Any]]:
        """Get a single ingredient by name (case-insensitive)"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path FROM ingredients WHERE LOWER(name) = LOWER(%s)",
                    (ingredient_name,),
                ),
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(
                f"Error getting ingredient by name '{ingredient_name}': {str(e)}"
            )
            return None

    def search_ingredients(self, search_term: str) -> List[Dict[str, Any]]:
        """Search ingredients by name - first exact match, then partial match (case-insensitive)"""
        try:
            exact_result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients WHERE LOWER(name) = LOWER(%s)",
                    (search_term,),
                ),
            )
            # Mark exact matches
            for ingredient in exact_result:
                ingredient["exact_match"] = True
            if exact_result:
                return exact_result
            # Otherwise, fall back to partial match (ILIKE for case-insensitive)
            partial_result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients WHERE name ILIKE %s ORDER BY name",
                    (f"%{search_term}%",),
                ),
            )
            # Mark partial matches
            for ingredient in partial_result:
                ingredient["exact_match"] = False
            return partial_result
        except Exception as e:
            logger.error(
                f"Error searching ingredients with term '{search_term}': {str(e)}"
            )
            raise

    def search_ingredients_batch(
        self, ingredient_names: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Batch search for ingredients by name - returns mapping of names to ingredient data"""
        try:
            if not ingredient_names:
                return {}
            # Create case-insensitive lookup for exact matches
            unique_names = list(set(name.lower() for name in ingredient_names))
            placeholders = ",".join("%s" for _ in unique_names)

            exact_results = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    f"SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients WHERE LOWER(name) IN ({placeholders})",
                    tuple(unique_names),
                ),
            )

            # Build mapping from lowercase name to ingredient data
            results_map = {}
            for ingredient in exact_results:
                ingredient["exact_match"] = True
                results_map[ingredient["name"].lower()] = ingredient

            # Map back to original case names
            final_results = {}
            for original_name in ingredient_names:
                lower_name = original_name.lower()
                if lower_name in results_map:
                    final_results[original_name] = results_map[lower_name]
            return final_results

        except Exception as e:
            logger.error(f"Error in batch ingredient search: {str(e)}")
            raise

    def check_ingredient_names_batch(
        self, ingredient_names: List[str]
    ) -> Dict[str, bool]:
        """Batch check for duplicate ingredient names - returns mapping of names to exists status"""
        try:
            if not ingredient_names:
                return {}
            # Create case-insensitive lookup
            unique_names = list(set(name.lower() for name in ingredient_names))
            placeholders = ",".join("%s" for _ in unique_names)

            existing_results = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    f"SELECT LOWER(name) as name_lower FROM ingredients WHERE LOWER(name) IN ({placeholders})",
                    tuple(unique_names),
                ),
            )
            existing_names = {row["name_lower"] for row in existing_results}

            # Map back to original case names
            final_results = {}
            for original_name in ingredient_names:
                lower_name = original_name.lower()
                final_results[original_name] = lower_name in existing_names
            return final_results
        except Exception as e:
            logger.error(f"Error in batch ingredient name check: {str(e)}")
            raise

    def get_ingredient(self, ingredient_id: int) -> Optional[Dict[str, Any]]:
        """Get a single ingredient by ID"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path, allow_substitution FROM ingredients WHERE id = %(id)s",
                    {"id": ingredient_id},
                ),
            )
            if result:
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error getting ingredient {ingredient_id}: {str(e)}")
            raise

    def get_ingredient_descendants(self, ingredient_id: int) -> List[Dict[str, Any]]:
        """Get all descendants of an ingredient"""
        try:
            # Get the ingredient's path
            ingredient = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT path FROM ingredients WHERE id = %(id)s", {"id": ingredient_id}
                ),
            )
            if not ingredient:
                return []

            path = ingredient[0]["path"]

            # Get all ingredients where path starts with this path but is not this path
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                SELECT id, name, description, parent_id, path,
                       (LENGTH(path) - LENGTH(REPLACE(path, '/', '')) - 1) as level
                FROM ingredients
                WHERE path LIKE %(path_pattern)s AND id != %(id)s
                ORDER BY path
                """,
                    {"path_pattern": f"{path}%", "id": ingredient_id},
                ),
            )
            return result
        except Exception as e:
            logger.error(
                f"Error getting descendants for ingredient {ingredient_id}: {str(e)}"
            )
            raise

    def _validate_recipe_ingredients(self, ingredients: List[Dict[str, Any]]) -> None:
        """Validate recipe ingredients before database operations"""
        if not ingredients:
            return

        # Collect all ingredient IDs for batch validation
        ingredient_ids = []

        for i, ingredient in enumerate(ingredients):
            # Validate required fields
            if "ingredient_id" not in ingredient:
                raise ValueError(
                    f"Ingredient {i + 1}: missing required field 'ingredient_id'"
                )

            ingredient_id = ingredient["ingredient_id"]
            if ingredient_id is None:
                raise ValueError(f"Ingredient {i + 1}: 'ingredient_id' cannot be None")

            # Validate ingredient_id is an integer
            if not isinstance(ingredient_id, int):
                try:
                    ingredient_id = int(ingredient_id)
                    ingredient["ingredient_id"] = (
                        ingredient_id  # Update the dict with converted value
                    )
                except (ValueError, TypeError):
                    raise ValueError(
                        f"Ingredient {i + 1}: 'ingredient_id' must be an integer, got {type(ingredient_id).__name__}"
                    )

            ingredient_ids.append(ingredient_id)

            # Validate amount if present
            if "amount" in ingredient and ingredient["amount"] is not None:
                amount = ingredient["amount"]
                if not isinstance(amount, (int, float)):
                    try:
                        amount = float(amount)
                        ingredient["amount"] = (
                            amount  # Update the dict with converted value
                        )
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"Ingredient {i + 1}: 'amount' must be numeric, got {type(amount).__name__}: '{amount}'"
                        )

                # Validate amount is not negative
                if amount < 0:
                    raise ValueError(
                        f"Ingredient {i + 1}: 'amount' cannot be negative, got {amount}"
                    )

            # Validate unit_id if present
            if "unit_id" in ingredient and ingredient["unit_id"] is not None:
                unit_id = ingredient["unit_id"]
                if not isinstance(unit_id, int):
                    try:
                        unit_id = int(unit_id)
                        ingredient["unit_id"] = (
                            unit_id  # Update the dict with converted value
                        )
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"Ingredient {i + 1}: 'unit_id' must be an integer, got {type(unit_id).__name__}"
                        )

        # Batch validate that all ingredient IDs exist
        if ingredient_ids:
            self._validate_ingredients_exist(ingredient_ids)

    def _validate_ingredients_exist(self, ingredient_ids: List[int]) -> None:
        """Validate that all ingredient IDs exist in the database"""
        try:
            placeholders = ",".join("%s" for _ in ingredient_ids)
            existing_ids_result = self.execute_query(
                f"SELECT id FROM ingredients WHERE id IN ({placeholders})",
                tuple(ingredient_ids),
            )

            existing_ids = set(row["id"] for row in existing_ids_result)
            missing_ids = set(ingredient_ids) - existing_ids

            if missing_ids:
                missing_ids_str = ", ".join(str(id) for id in sorted(missing_ids))
                raise ValueError(f"Invalid ingredient IDs: {missing_ids_str}")

        except Exception as e:
            if "Invalid ingredient IDs" in str(e):
                raise  # Re-raise our custom validation error
            logger.error(f"Error validating ingredient existence: {str(e)}")
            raise ValueError("Failed to validate ingredient existence")

    def create_recipe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new recipe with its ingredients"""
        # Check for case-insensitive duplicate name
        recipe_name = data.get("name")
        if recipe_name:
            existing = self.execute_query(
                "SELECT id FROM recipes WHERE LOWER(name) = LOWER(%s)",
                (recipe_name,),
            )
            if existing:
                raise ConflictException(
                    f"A recipe with the name '{recipe_name}' already exists (case-insensitive). Please use a different name."
                )

        # Validate ingredients before starting database transaction
        if "ingredients" in data and data["ingredients"]:
            self._validate_recipe_ingredients(data["ingredients"])

        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            # Create the recipe
            cursor.execute(
                """
                INSERT INTO recipes (name, instructions, description, image_url, source, source_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    data["name"] if data["name"] else None,
                    data.get("instructions"),
                    data.get("description"),
                    data.get("image_url"),
                    data.get("source"),
                    data.get("source_url"),
                ),
            )

            # Get the recipe ID
            recipe_row = cursor.fetchone()
            if not recipe_row or recipe_row[0] is None:
                raise ValueError("Failed to get recipe ID after insertion")
            recipe_id = recipe_row[0]

            # Add recipe ingredients
            if "ingredients" in data:
                for ingredient in data["ingredients"]:
                    cursor.execute(
                        """
                        INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            recipe_id,
                            ingredient["ingredient_id"],
                            ingredient.get("unit_id"),
                            ingredient.get("amount"),
                        ),
                    )

            # Commit the transaction
            conn.commit()
            cursor.close()
            self._return_connection(conn)
            conn = None

            # Return the created recipe
            recipe = self.get_recipe(recipe_id)
            if not recipe:
                raise ValueError("Failed to retrieve created recipe")
            return recipe
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error creating recipe: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def bulk_create_recipes(self, recipes_data: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        """Create multiple recipes in a single transaction (optimized for bulk uploads)"""
        conn = None
        created_recipes = []

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            for data in recipes_data:
                # Validate ingredients before inserting
                if "ingredients" in data and data["ingredients"]:
                    self._validate_recipe_ingredients(data["ingredients"])

                # Insert recipe
                cursor.execute(
                    """
                    INSERT INTO recipes (name, instructions, description, image_url, source, source_url, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        data["name"] if data["name"] else None,
                        data.get("instructions"),
                        data.get("description"),
                        data.get("image_url"),
                        data.get("source"),
                        data.get("source_url"),
                        user_id,
                    ),
                )

                recipe_row = cursor.fetchone()
                if not recipe_row or recipe_row[0] is None:
                    raise ValueError(
                        f"Failed to get recipe ID after inserting '{data['name']}'"
                    )
                recipe_id = recipe_row[0]

                # Batch insert ingredients using executemany
                if "ingredients" in data and data["ingredients"]:
                    ingredient_rows = [
                        (
                            recipe_id,
                            ing["ingredient_id"],
                            ing.get("unit_id"),
                            ing.get("amount")
                        )
                        for ing in data["ingredients"]
                    ]
                    cursor.executemany(
                        """
                        INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
                        VALUES (%s, %s, %s, %s)
                        """,
                        ingredient_rows
                    )

                # Store minimal data to avoid extra queries
                created_recipes.append({
                    "id": recipe_id,
                    "name": data["name"],
                    "instructions": data.get("instructions"),
                    "description": data.get("description"),
                    "source": data.get("source"),
                    "source_url": data.get("source_url")
                })

            # Commit all recipes at once
            conn.commit()
            self._return_connection(conn)
            conn = None

            return created_recipes

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error in bulk_create_recipes: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def get_recipes_with_ingredients(
        self, cognito_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all recipes with their full ingredient details (for detailed views)"""
        try:
            # 1. Get all recipes
            params = {"cognito_user_id": cognito_user_id}
            recipes_result = cast(
                List[Dict[str, Any]],
                self.execute_query(get_all_recipes_sql, params),
            )
            if not recipes_result:
                return []
            # 2. Fetch all recipe ingredients across all recipes
            recipe_ids = [recipe["id"] for recipe in recipes_result]
            all_recipe_ingredients_list = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    get_recipe_ingredients_by_recipe_id_sql_factory(recipe_ids),
                    tuple(recipe_ids),
                ),
            )
            # 3. Identify all necessary ingredient IDs (direct + ancestors) using the helper
            all_needed_ingredient_ids = extract_all_ingredient_ids(
                all_recipe_ingredients_list
            )
            # 4. Fetch names for all needed ingredients in one query
            ingredient_names_map = {}
            if all_needed_ingredient_ids:
                placeholders = ",".join("%s" for _ in all_needed_ingredient_ids)
                names_result = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        f"SELECT id, name FROM ingredients WHERE id IN ({placeholders})",
                        tuple(all_needed_ingredient_ids),
                    ),
                )
                ingredient_names_map = {row["id"]: row["name"] for row in names_result}
            # 5. Assemble full names using the helper method
            assemble_ingredient_full_names(
                all_recipe_ingredients_list, ingredient_names_map
            )
            # 6. Group ingredients by recipe
            recipe_ingredients_grouped = {recipe_id: [] for recipe_id in recipe_ids}
            for ing_data in all_recipe_ingredients_list:
                recipe_id = ing_data["recipe_id"]
                # Use the actual recipe_ingredient_id as 'id' for consistency if needed frontend
                ing_data["id"] = ing_data["recipe_ingredient_id"]
                recipe_ingredients_grouped[recipe_id].append(ing_data)
            # 7. Combine recipes with their assembled ingredients
            for recipe in recipes_result:
                recipe["ingredients"] = recipe_ingredients_grouped.get(recipe["id"], [])
            return recipes_result
        except Exception as e:
            logger.error(f"Error getting recipes with ingredients: {str(e)}")
            raise

    def get_recipe(
        self, recipe_id: int, cognito_user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get a single recipe by ID with its ingredients and tags using GROUP_CONCAT for efficiency."""
        try:
            logger.info(f"Getting recipe {recipe_id} for user_id: {cognito_user_id}")
            params = {"recipe_id": recipe_id, "cognito_user_id": cognito_user_id}
            rows = cast(
                List[Dict[str, Any]],
                self.execute_query(get_recipe_by_id_sql, params),
            )
            if (
                not rows or rows[0]["id"] is None
            ):  # GROUP_CONCAT might return a row with NULLs if no recipe matches WHERE
                logger.info(f"Recipe {recipe_id} not found by GROUP_CONCAT query.")
                return None

            recipe_data = rows[0]
            recipe = {
                "id": recipe_data["id"],
                "name": recipe_data["name"],
                "instructions": recipe_data["instructions"],
                "description": recipe_data["description"],
                "image_url": recipe_data["image_url"],
                "source": recipe_data["source"],
                "source_url": recipe_data["source_url"],
                "avg_rating": recipe_data["avg_rating"],
                "rating_count": recipe_data["rating_count"],
                "user_rating": recipe_data["user_rating"],
                "ingredients": [],  # To be filled next
                "tags": [],
            }

            # Process public tags
            public_tags_str = recipe_data.get("public_tags_data")
            logger.info(f"Recipe {recipe_id} public_tags_data: '{public_tags_str}'")
            if public_tags_str:
                for tag_data_str in public_tags_str.split(":::"):
                    try:
                        tag_id_str, tag_name = tag_data_str.split("|||", 1)
                        tag_obj = {
                            "id": int(tag_id_str),
                            "name": tag_name,
                            "type": "public",
                        }
                        recipe["tags"].append(tag_obj)
                        logger.info(
                            f"Added public tag to recipe {recipe_id}: {tag_obj}"
                        )
                    except ValueError as ve:
                        logger.warning(
                            f"Could not parse public tag_data_str '{tag_data_str}': {ve}"
                        )
            # Process private tags
            private_tags_str = recipe_data.get("private_tags_data")
            logger.info(
                f"Recipe {recipe_id} private_tags_data: '{private_tags_str}' for user {cognito_user_id}"
            )
            if (
                private_tags_str and cognito_user_id
            ):  # Only process if user_id was present for the query
                for tag_data_str in private_tags_str.split(":::"):
                    try:
                        tag_id_str, tag_name = tag_data_str.split("|||", 1)
                        tag_obj = {
                            "id": int(tag_id_str),
                            "name": tag_name,
                            "type": "private",
                        }
                        recipe["tags"].append(tag_obj)
                        logger.info(
                            f"Added private tag to recipe {recipe_id}: {tag_obj}"
                        )
                    except ValueError as ve:
                        logger.warning(
                            f"Could not parse private tag_data_str '{tag_data_str}': {ve}"
                        )
            # Fetch ingredients separately
            recipe["ingredients"] = self._get_recipe_ingredients(recipe_id)

            # Log final tag list
            logger.info(
                f"Recipe {recipe_id} final tag list ({len(recipe['tags'])} tags): {recipe['tags']}"
            )

            return recipe

        except Exception as e:
            logger.error(
                f"Error getting recipe {recipe_id} (GROUP_CONCAT): {str(e)}",
                exc_info=True,
            )
            raise

    def _get_recipe_ingredients(self, recipe_id: int) -> List[Dict[str, Any]]:
        """Helper method to get ingredients for a recipe, optimized for ancestor lookup"""
        # Fetch direct ingredients for the recipe
        direct_ingredients = cast(
            List[Dict[str, Any]],
            self.execute_query(
                f"""
                SELECT {INGREDIENT_SELECT_FIELDS}
                FROM recipe_ingredients ri
                JOIN ingredients i ON ri.ingredient_id = i.id
                LEFT JOIN units u ON ri.unit_id = u.id
                WHERE ri.recipe_id = %(recipe_id)s
                ORDER BY ri.recipe_id ASC,
                    COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
                    ri.id ASC
                """,
                {"recipe_id": recipe_id},
            ),
        )

        if not direct_ingredients:
            return []

        # Identify all necessary ingredient IDs (direct + ancestors) using the helper
        all_needed_ids = extract_all_ingredient_ids(direct_ingredients)

        # Fetch names for all needed ingredients in one query
        ingredient_names = {}
        if all_needed_ids:
            placeholders = ",".join("%s" for _ in all_needed_ids)
            names_result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    f"SELECT id, name FROM ingredients WHERE id IN ({placeholders})",
                    tuple(all_needed_ids),
                ),
            )
            ingredient_names = {row["id"]: row["name"] for row in names_result}

        # Assemble full_name for each ingredient using the helper method
        assemble_ingredient_full_names(direct_ingredients, ingredient_names)

        # Map recipe_ingredient_id to id for frontend consistency
        for ingredient in direct_ingredients:
            ingredient["id"] = ingredient["recipe_ingredient_id"]

        return direct_ingredients

    def get_units(self) -> List[Dict[str, Any]]:
        """Get all measurement units"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, abbreviation, conversion_to_ml FROM units ORDER BY name"
                ),
            )
            return result
        except Exception as e:
            logger.error(f"Error getting units: {str(e)}")
            raise

    def get_units_by_type(self, unit_type: str) -> List[Dict[str, Any]]:
        """Get units filtered by type (this implementation returns all units since there's no type column)"""
        try:
            # Since the units table doesn't have a type column, we'll return all units
            # This could be enhanced later by adding a type column or filtering by name patterns
            logger.warning(
                f"get_units_by_type called with type '{unit_type}' but units table has no type column, returning all units"
            )
            return self.get_units()
        except Exception as e:
            logger.error(f"Error getting units by type {unit_type}: {str(e)}")
            raise

    def get_unit_by_name(self, unit_name: str) -> Optional[Dict[str, Any]]:
        """Get a unit by exact name match (case-insensitive)"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, abbreviation, conversion_to_ml FROM units WHERE LOWER(name) = LOWER(%s)",
                    (unit_name,),
                ),
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting unit by name '{unit_name}': {str(e)}")
            raise

    def get_unit_by_abbreviation(
        self, unit_abbreviation: str
    ) -> Optional[Dict[str, Any]]:
        """Get a unit by exact name match (case-insensitive)"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, abbreviation, conversion_to_ml FROM units WHERE LOWER(abbreviation) = LOWER(%s)",
                    (unit_abbreviation,),
                ),
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(
                f"Error getting unit by abbreviation '{unit_abbreviation}': {str(e)}"
            )
            raise

    def get_unit_by_name_or_abbreviation(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a unit by exact name or abbreviation match (case-insensitive)"""
        result = self.get_unit_by_name(name)
        if result:
            return result
        return self.get_unit_by_abbreviation(name)

    def validate_units_batch(self, unit_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch validate units by name or abbreviation - returns mapping of names to unit data"""
        try:
            if not unit_names:
                return {}
            # Create case-insensitive lookup for exact matches by name or abbreviation
            unique_names = list(set(name.lower() for name in unit_names))
            placeholders = ",".join("%s" for _ in unique_names)

            # Query for both name and abbreviation matches
            unit_results = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    f"""
                    SELECT id, name, abbreviation, conversion_to_ml 
                    FROM units 
                    WHERE LOWER(name) IN ({placeholders}) OR LOWER(abbreviation) IN ({placeholders})
                    """,
                    tuple(unique_names)
                    + tuple(unique_names),  # Parameters for both IN clauses
                ),
            )
            # Build mapping from lowercase name/abbreviation to unit data
            results_map = {}
            for unit in unit_results:
                unit_name_lower = unit["name"].lower()
                unit_abbr_lower = (
                    unit["abbreviation"].lower() if unit["abbreviation"] else None
                )

                # Map both name and abbreviation to this unit
                results_map[unit_name_lower] = unit
                if unit_abbr_lower:
                    results_map[unit_abbr_lower] = unit

            # Map back to original case names
            final_results = {}
            for original_name in unit_names:
                lower_name = original_name.lower()
                if lower_name in results_map:
                    final_results[original_name] = results_map[lower_name]
            return final_results

        except Exception as e:
            logger.error(f"Error in batch unit validation: {str(e)}")
            raise

    def check_recipe_names_batch(self, recipe_names: List[str]) -> Dict[str, bool]:
        """Batch check for duplicate recipe names - returns mapping of names to exists status"""
        try:
            if not recipe_names:
                return {}
            # Create case-insensitive lookup
            unique_names = list(set(name.lower() for name in recipe_names))
            placeholders = ",".join("%s" for _ in unique_names)

            existing_results = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    f"SELECT LOWER(name) as name_lower FROM recipes WHERE LOWER(name) IN ({placeholders})",
                    tuple(unique_names),
                ),
            )
            existing_names = {row["name_lower"] for row in existing_results}
            # Map back to original case names
            final_results = {}
            for original_name in recipe_names:
                lower_name = original_name.lower()
                final_results[original_name] = lower_name in existing_names
            return final_results

        except Exception as e:
            logger.error(f"Error in batch recipe name check: {str(e)}")
            raise

    def delete_recipe(self, recipe_id: int) -> bool:
        """Delete a recipe and its ingredients"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            # Check if recipe exists
            recipe = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM recipes WHERE id = %(id)s", {"id": recipe_id}
                ),
            )
            if not recipe:
                return False

            # Note: We don't need to explicitly delete recipe_ingredients, ratings, or tags
            # because the ON DELETE CASCADE constraint will handle this automatically
            cursor.execute("DELETE FROM recipes WHERE id = %s", (recipe_id,))

            conn.commit()
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error deleting recipe {recipe_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def update_recipe(
        self, recipe_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing recipe"""
        conn = None
        try:
            # Check if recipe exists first
            existing = self.execute_query(
                "SELECT id FROM recipes WHERE id = %(id)s", {"id": recipe_id}
            )
            if not existing:
                return None
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")
            cursor.execute(
                """
                UPDATE recipes
                SET name = COALESCE(%s, name),
                    instructions = COALESCE(%s, instructions),
                    description = COALESCE(%s, description),
                    image_url = COALESCE(%s, image_url),
                    source = COALESCE(%s, source),
                    source_url = COALESCE(%s, source_url)
                WHERE id = %s
                """,
                (
                    data.get("name"),
                    data.get("instructions"),
                    data.get("description"),
                    data.get("image_url"),
                    data.get("source"),
                    data.get("source_url"),
                    recipe_id,
                ),
            )

            # Update ingredients if provided
            if "ingredients" in data:
                # Delete existing ingredients for this recipe
                cursor.execute(
                    "DELETE FROM recipe_ingredients WHERE recipe_id = %s",
                    (recipe_id,),
                )

                # Insert new ingredients
                for ingredient in data["ingredients"]:
                    cursor.execute(
                        """
                        INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            recipe_id,
                            ingredient["ingredient_id"],
                            ingredient.get("unit_id"),
                            ingredient.get("amount"),
                        ),
                    )

            conn.commit()
            self._return_connection(conn)
            conn = None  # Ensure it's not closed again in finally if commit succeeded

            # Fetch and return the updated recipe
            return self.get_recipe(recipe_id)

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error updating recipe {recipe_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def get_recipe_ratings(self, recipe_id: int) -> List[Dict[str, Any]]:
        """Get all ratings for a recipe"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating
                    FROM ratings
                    WHERE recipe_id = %(recipe_id)s
                    """,
                    {"recipe_id": recipe_id},
                ),
            )
            return result
        except Exception as e:
            logger.error(f"Error getting ratings for recipe {recipe_id}: {str(e)}")
            raise

    def get_user_rating(self, recipe_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific user's rating for a recipe"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating
                    FROM ratings
                    WHERE recipe_id = %(recipe_id)s AND cognito_user_id = %(user_id)s
                    """,
                    {"recipe_id": recipe_id, "user_id": user_id},
                ),
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(
                f"Error getting user rating for recipe {recipe_id}, user {user_id}: {str(e)}"
            )
            raise

    def set_rating(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Set (add or update) a rating for a recipe"""
        conn = None
        try:
            # Check required fields
            if not data.get("cognito_user_id"):
                raise ValueError("User ID is required")
            if not data.get("cognito_username"):
                raise ValueError("Username is required")
            if not data.get("recipe_id"):
                raise ValueError("Recipe ID is required")
            if "rating" not in data or not (1 <= data["rating"] <= 5):
                raise ValueError("Rating must be between 1 and 5")

            # Check if recipe exists
            recipe = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM recipes WHERE id = %(id)s", {"id": data["recipe_id"]}
                ),
            )
            if not recipe:
                raise ValueError(f"Recipe with ID {data['recipe_id']} does not exist")

            # Check if user already rated this recipe
            existing_rating = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id FROM ratings
                    WHERE cognito_user_id = %(user_id)s AND recipe_id = %(recipe_id)s
                    """,
                    {
                        "user_id": data["cognito_user_id"],
                        "recipe_id": data["recipe_id"],
                    },
                ),
            )

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            rating_id = None
            if existing_rating:
                # Update existing rating
                rating_id = existing_rating[0]["id"]
                cursor.execute(
                    """
                    UPDATE ratings
                    SET rating = %s
                    WHERE cognito_user_id = %s AND recipe_id = %s
                    """,
                    (
                        data["rating"],
                        data["cognito_user_id"],
                        data["recipe_id"],
                    ),
                )
            else:
                # Insert new rating
                cursor.execute(
                    """
                    INSERT INTO ratings (cognito_user_id, cognito_username, recipe_id, rating)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        data["cognito_user_id"],
                        data["cognito_username"],
                        data["recipe_id"],
                        data["rating"],
                    ),
                )
                rating_row = cursor.fetchone()
                if not rating_row or rating_row[0] is None:
                    raise ValueError("Failed to get rating ID after insertion")
                rating_id = rating_row[0]

            conn.commit()
            self._return_connection(conn)
            conn = None

            # Fetch the created/updated rating
            rating = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating
                    FROM ratings
                    WHERE id = %(id)s
                    """,
                    {"id": rating_id},
                ),
            )

            # Also fetch the updated average rating and count
            recipe_updated = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT avg_rating, rating_count FROM recipes WHERE id = %(id)s",
                    {"id": data["recipe_id"]},
                ),
            )

            if rating and recipe_updated:
                result = rating[0]
                result["avg_rating"] = recipe_updated[0]["avg_rating"]
                result["rating_count"] = recipe_updated[0]["rating_count"]
                return result
            return {}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error setting rating: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def delete_rating(self, recipe_id: int, user_id: str) -> bool:
        """Delete a rating for a recipe by a specific user"""
        conn = None
        try:
            # Check if the rating exists
            existing_rating = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id FROM ratings
                    WHERE cognito_user_id = %(user_id)s AND recipe_id = %(recipe_id)s
                    """,
                    {"user_id": user_id, "recipe_id": recipe_id},
                ),
            )
            if not existing_rating:
                raise ValueError("Rating not found for this user and recipe")

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            # Delete the rating
            cursor.execute(
                """
                DELETE FROM ratings
                WHERE cognito_user_id = %s AND recipe_id = %s
                """,
                (user_id, recipe_id),
            )

            conn.commit()
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error deleting rating for recipe {recipe_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    # --- Tag Management ---

    def create_public_tag(self, name: str) -> Dict[str, Any]:
        """Creates a new public tag. Returns the created tag."""
        if not name:
            raise ValueError("Tag name cannot be empty")
        try:
            logger.info(f"DB: Creating public tag '{name}'")
            self.execute_query(
                "INSERT INTO tags (name, created_by) VALUES (%(name)s, NULL)",
                {"name": name},
            )
            # Re-fetch the tag to get its ID
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name FROM tags WHERE name = %(name)s AND created_by IS NULL",
                    {"name": name},
                ),
            )
            if not tag:  # Should not happen if insert succeeded
                logger.error(
                    f"DB: Failed to retrieve public tag '{name}' after creation"
                )
                raise psycopg2.DatabaseError("Failed to retrieve tag after creation.")
            logger.info(f"DB: Successfully created public tag: {tag[0]}")
            return tag[0]
        except psycopg2.IntegrityError:
            logger.warning(f"Public tag '{name}' already exists.")
            # If it already exists, fetch and return it
            existing_tag = self.get_public_tag_by_name(name)
            if existing_tag:
                return existing_tag
            raise  # Should not happen if integrity error was due to name conflict
        except Exception as e:
            logger.error(f"Error creating public tag '{name}': {str(e)}")
            raise

    def get_public_tag_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Gets a public tag by its name."""
        try:
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name FROM tags WHERE name = %(name)s AND created_by IS NULL",
                    {"name": name},
                ),
            )
            return tag[0] if tag else None
        except Exception as e:
            logger.error(f"Error getting public tag by name '{name}': {str(e)}")
            raise

    def create_private_tag(self, name: str, cognito_user_id: str) -> Dict[str, Any]:
        """Creates a new private tag for a user. Returns the created tag."""
        # Validate inputs
        if not name or not name.strip():
            raise ValueError("Tag name cannot be empty")
        if not cognito_user_id or not cognito_user_id.strip():
            raise ValueError("User ID cannot be empty")

        try:
            self.execute_query(
                """
                INSERT INTO tags (name, created_by)
                VALUES (%(name)s, %(cognito_user_id)s)
                """,
                {
                    "name": name.strip(),
                    "cognito_user_id": cognito_user_id.strip(),
                },
            )
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, name, created_by as cognito_user_id FROM tags
                    WHERE name = %(name)s AND created_by = %(cognito_user_id)s
                    """,
                    {"name": name.strip(), "cognito_user_id": cognito_user_id.strip()},
                ),
            )
            if not tag:  # Should not happen
                raise psycopg2.DatabaseError(
                    "Failed to retrieve private tag after creation."
                )
            return tag[0]
        except psycopg2.IntegrityError:
            logger.warning(
                f"Private tag '{name}' for user '{cognito_user_id}' already exists."
            )
            existing_tag = self.get_private_tag_by_name_and_user(name, cognito_user_id)
            if existing_tag:
                return existing_tag
            raise
        except Exception as e:
            logger.error(
                f"Error creating private tag '{name}' for user '{cognito_user_id}': {str(e)}"
            )
            raise

    def get_private_tag_by_name_and_user(
        self, name: str, cognito_user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Gets a private tag by its name and user ID."""
        try:
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, name, created_by as cognito_user_id FROM tags
                    WHERE name = %(name)s AND created_by = %(cognito_user_id)s
                    """,
                    {"name": name, "cognito_user_id": cognito_user_id},
                ),
            )
            return tag[0] if tag else None
        except Exception as e:
            logger.error(
                f"Error getting private tag by name '{name}' for user '{cognito_user_id}': {str(e)}"
            )
            raise

    def get_public_tags(self) -> List[Dict[str, Any]]:
        """Get all public tags with usage count."""
        try:
            return cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT 
                        t.id, 
                        t.name, 
                        COALESCE(COUNT(rt.recipe_id), 0) as usage_count
                    FROM tags t
                    LEFT JOIN recipe_tags rt ON t.id = rt.tag_id
                    WHERE t.created_by IS NULL 
                    GROUP BY t.id, t.name
                    ORDER BY t.name
                    """
                ),
            )
        except Exception as e:
            logger.error(f"Error getting public tags: {str(e)}")
            raise

    def get_private_tags(self, cognito_user_id: str) -> List[Dict[str, Any]]:
        """Get all private tags for a specific user."""
        try:
            return cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, name, created_by as cognito_user_id FROM tags
                    WHERE created_by = %(cognito_user_id)s ORDER BY name
                    """,
                    {"cognito_user_id": cognito_user_id},
                ),
            )
        except Exception as e:
            logger.error(
                f"Error getting private tags for user '{cognito_user_id}': {str(e)}"
            )
            raise

    def add_public_tag_to_recipe(self, recipe_id: int, tag_id: int) -> bool:
        """Associates a public tag with a recipe."""
        try:
            logger.info(f"DB: Adding public tag {tag_id} to recipe {recipe_id}")
            result = self.execute_query(
                """
                INSERT INTO recipe_tags (recipe_id, tag_id)
                VALUES (%(recipe_id)s, %(tag_id)s)
                ON CONFLICT(recipe_id, tag_id) DO NOTHING
                """,
                {"recipe_id": recipe_id, "tag_id": tag_id},
            )
            rows_affected = result.get("rowCount", 0)
            if rows_affected > 0:
                logger.info(
                    f"DB: Successfully added tag {tag_id} to recipe {recipe_id}"
                )
            else:
                logger.warning(
                    f"DB: Tag {tag_id} already associated with recipe {recipe_id} (conflict ignored)"
                )
            return rows_affected > 0
        except Exception as e:
            logger.error(
                f"Error adding public tag {tag_id} to recipe {recipe_id}: {str(e)}"
            )
            raise

    def add_private_tag_to_recipe(self, recipe_id: int, tag_id: int) -> bool:
        """Associates a private tag with a recipe."""
        try:
            # We assume tag_id corresponds to a private tag owned by the relevant user.
            # The check for tag ownership should happen in the handler before calling this.
            logger.info(f"DB: Adding private tag {tag_id} to recipe {recipe_id}")
            result = self.execute_query(
                """
                INSERT INTO recipe_tags (recipe_id, tag_id)
                VALUES (%(recipe_id)s, %(tag_id)s)
                ON CONFLICT(recipe_id, tag_id) DO NOTHING
                """,
                {"recipe_id": recipe_id, "tag_id": tag_id},
            )
            rows_affected = result.get("rowCount", 0)
            if rows_affected > 0:
                logger.info(
                    f"DB: Successfully added private tag {tag_id} to recipe {recipe_id}"
                )
            else:
                logger.warning(
                    f"DB: Private tag {tag_id} already associated with recipe {recipe_id} (conflict ignored)"
                )
            return rows_affected > 0
        except Exception as e:
            logger.error(
                f"Error adding private tag {tag_id} to recipe {recipe_id}: {str(e)}"
            )
            raise

    def remove_public_tag_from_recipe(self, recipe_id: int, tag_id: int) -> bool:
        """Removes the association of a public tag from a recipe."""
        try:
            result = self.execute_query(
                "DELETE FROM recipe_tags WHERE recipe_id = %(recipe_id)s AND tag_id = %(tag_id)s",
                {"recipe_id": recipe_id, "tag_id": tag_id},
            )
            return result.get("rowCount", 0) > 0
        except Exception as e:
            logger.error(
                f"Error removing public tag {tag_id} from recipe {recipe_id}: {str(e)}"
            )
            raise

    def remove_private_tag_from_recipe(
        self, recipe_id: int, tag_id: int, cognito_user_id: str
    ) -> bool:
        """Removes the association of a private tag from a recipe, ensuring user ownership."""
        try:
            # Ensure the user owns the private tag they are trying to remove from the recipe
            result = self.execute_query(
                """
                DELETE FROM recipe_tags
                WHERE recipe_id = %(recipe_id)s AND tag_id = %(tag_id)s
                  AND EXISTS (SELECT 1 FROM tags t WHERE t.id = %(tag_id)s AND t.created_by = %(cognito_user_id)s)
                """,
                {
                    "recipe_id": recipe_id,
                    "tag_id": tag_id,
                    "cognito_user_id": cognito_user_id,
                },
            )
            return result.get("rowCount", 0) > 0
        except Exception as e:
            logger.error(
                f"Error removing private tag {tag_id} from recipe {recipe_id} for user {cognito_user_id}: {str(e)}"
            )
            raise

    def _get_recipe_public_tags(self, recipe_id: int) -> List[Dict[str, Any]]:
        """Helper method to get all public tags for a specific recipe."""
        try:
            return cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT t.id, t.name
                    FROM recipe_tags rt
                    JOIN tags t ON rt.tag_id = t.id
                    WHERE rt.recipe_id = %(recipe_id)s AND t.created_by IS NULL
                    ORDER BY t.name
                    """,
                    {"recipe_id": recipe_id},
                ),
            )
        except Exception as e:
            logger.error(f"Error getting public tags for recipe {recipe_id}: {str(e)}")
            raise

    def _get_recipe_private_tags(
        self, recipe_id: int, cognito_user_id: str
    ) -> List[Dict[str, Any]]:
        """Helper method to get all private tags for a specific recipe by a specific user."""
        try:
            return cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT t.id, t.name
                    FROM recipe_tags rt
                    JOIN tags t ON rt.tag_id = t.id
                    WHERE rt.recipe_id = %(recipe_id)s AND t.created_by = %(cognito_user_id)s
                    ORDER BY t.name
                    """,
                    {"recipe_id": recipe_id, "cognito_user_id": cognito_user_id},
                ),
            )
        except Exception as e:
            logger.error(
                f"Error getting private tags for recipe {recipe_id} by user {cognito_user_id}: {str(e)}"
            )
            raise

    def get_tag(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """Gets a tag by its ID from the unified tags table."""
        try:
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """SELECT id, name,
                       CASE WHEN created_by IS NULL THEN 0 ELSE 1 END as is_private,
                       created_by as created_by
                       FROM tags WHERE id = %(tag_id)s""",
                    {"tag_id": tag_id},
                ),
            )
            if tag:
                result = tag[0]
                # For compatibility, add cognito_user_id field for private tags
                if result["is_private"] == 1:
                    result["cognito_user_id"] = result["created_by"]
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting tag by ID {tag_id}: {str(e)}")
            raise

    def add_recipe_tag(
        self, recipe_id: int, tag_id: int, is_private: bool, user_id: str
    ) -> bool:
        """Generic method to add a tag to a recipe."""
        try:
            if is_private:
                return self.add_private_tag_to_recipe(recipe_id, tag_id)
            else:
                return self.add_public_tag_to_recipe(recipe_id, tag_id)
        except Exception as e:
            logger.error(
                f"Error adding {'private' if is_private else 'public'} tag {tag_id} to recipe {recipe_id} for user {user_id}: {str(e)}"
            )
            raise

    def remove_recipe_tag(
        self, recipe_id: int, tag_id: int, is_private: bool, user_id: str
    ) -> bool:
        """Generic method to remove a tag from a recipe."""
        try:
            if is_private:
                return self.remove_private_tag_from_recipe(recipe_id, tag_id, user_id)
            else:
                return self.remove_public_tag_from_recipe(recipe_id, tag_id)
        except Exception as e:
            logger.error(
                f"Error removing {'private' if is_private else 'public'} tag {tag_id} from recipe {recipe_id} for user {user_id}: {str(e)}"
            )
            raise

    def delete_public_tag(self, tag_id: int) -> bool:
        """Delete a public tag completely from the database.
        This will CASCADE delete all recipe_tags associations.

        Args:
            tag_id: ID of the public tag to delete

        Returns:
            bool: True if tag was deleted, False if not found or is private
        """
        try:
            result = self.execute_query(
                "DELETE FROM tags WHERE id = %(tag_id)s AND created_by IS NULL",
                {"tag_id": tag_id},
            )
            success = result.get("rowCount", 0) > 0
            if success:
                logger.info(f"Successfully deleted public tag {tag_id}")
            return success
        except Exception as e:
            logger.error(f"Error deleting public tag {tag_id}: {str(e)}")
            raise

    def delete_private_tag(self, tag_id: int, user_id: str) -> bool:
        """Delete a private tag completely from the database.
        This will CASCADE delete all recipe_tags associations.
        Only the tag owner can delete their private tags.

        Args:
            tag_id: ID of the private tag to delete
            user_id: ID of the user attempting to delete (must be tag owner)

        Returns:
            bool: True if tag was deleted, False if not found or not owned by user
        """
        try:
            result = self.execute_query(
                "DELETE FROM tags WHERE id = %(tag_id)s AND created_by = %(user_id)s",
                {"tag_id": tag_id, "user_id": user_id},
            )
            success = result.get("rowCount", 0) > 0
            if success:
                logger.info(
                    f"Successfully deleted private tag {tag_id} for user {user_id}"
                )
            return success
        except Exception as e:
            logger.error(
                f"Error deleting private tag {tag_id} for user {user_id}: {str(e)}"
            )
            raise

    # --- End Tag Management ---

    # --- Pagination Methods ---
    def search_recipes_paginated(
        self,
        search_params: Dict[str, Any],
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "name",
        sort_order: str = "asc",
        user_id: Optional[str] = None,
        rating_type: str = "average",
        cursor: Optional[str] = None,
        return_pagination: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Search recipes with pagination"""
        try:
            from .sql_queries import (
                build_search_recipes_paginated_sql,
                build_search_recipes_keyset_sql,
            )

            # Build query parameters
            search_query = search_params.get("q")
            query_params = {
                "search_query": search_query,
                "search_query_with_wildcards": f"%{search_query}%"
                if search_query
                else None,
                "min_rating": search_params.get("min_rating"),
                "max_rating": search_params.get("max_rating"),
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "cognito_user_id": user_id,
            }
            use_keyset = sort_by != "random" and return_pagination
            cursor_payload = None
            if use_keyset and cursor:
                cursor_payload = self._decode_search_cursor(cursor, sort_by, sort_order)
                query_params["cursor_sort"] = cursor_payload["sort_value"]
                query_params["cursor_id"] = cursor_payload["id"]
            else:
                query_params["cursor_sort"] = None
                query_params["cursor_id"] = None
            if use_keyset:
                query_params["limit_plus_one"] = limit + 1
            # Handle ingredient filtering by converting names to IDs and paths
            must_ingredient_conditions = []
            must_not_ingredient_conditions = []
            has_invalid_ingredients = False

            if search_params.get("ingredients"):
                for i, ingredient_spec in enumerate(search_params["ingredients"]):
                    # Parse ingredient specification: "name" or "name:MUST" or "name:MUST_NOT"
                    ingredient_spec = ingredient_spec.strip()

                    if ":" in ingredient_spec:
                        ingredient_name, operator = ingredient_spec.split(":", 1)
                        ingredient_name = ingredient_name.strip()
                        operator = operator.strip().upper()
                    else:
                        ingredient_name = ingredient_spec
                        operator = "MUST"  # Default to MUST if no operator specified

                    ingredient = self.get_ingredient_by_name(ingredient_name)
                    if ingredient:
                        # Use path-based matching to include child ingredients
                        param_name = f"ingredient_path_{i}"
                        query_params[param_name] = f"%/{ingredient['id']}/%"
                        condition = f"i2.path LIKE %({param_name})s"

                        if operator == "MUST_NOT":
                            must_not_ingredient_conditions.append(condition)
                        else:  # MUST or any other value defaults to MUST
                            must_ingredient_conditions.append(condition)
                    else:
                        logger.warning(f"Ingredient not found: {ingredient_name}")
                        if operator != "MUST_NOT":
                            # Only fail for MUST ingredients that don't exist
                            # MUST_NOT for nonexistent ingredients should be ignored
                            has_invalid_ingredients = True

                # If any MUST ingredient doesn't exist, return no results
                if has_invalid_ingredients:
                    logger.info(
                        "Some MUST ingredients not found, returning empty results"
                    )
                    if return_pagination:
                        return {"recipes": [], "has_next": False, "next_cursor": None}
                    return []

            # Handle tag filtering
            tag_conditions = []
            if search_params.get("tags"):
                for i, tag_name in enumerate(search_params["tags"]):
                    tag_name = tag_name.strip()
                    if tag_name:
                        # Check if tag exists (both public and private)
                        public_tag = self.get_public_tag_by_name(tag_name)
                        private_tag = (
                            self.get_private_tag_by_name_and_user(tag_name, user_id)
                            if user_id
                            else None
                        )

                        if public_tag or private_tag:
                            # Recipe must have this tag (either public or private)
                            tag_param = f"tag_name_{i}"
                            query_params[tag_param] = tag_name

                            # Build condition for public tags (created_by IS NULL) or user's private tags
                            if user_id:
                                condition = f"(t3.name = %({tag_param})s AND (t3.created_by IS NULL OR t3.created_by = %(cognito_user_id)s))"
                            else:
                                condition = f"(t3.name = %({tag_param})s AND t3.created_by IS NULL)"
                            tag_conditions.append(condition)
                        else:
                            # Tag doesn't exist, return no results
                            logger.info(
                                f"Tag not found: {tag_name}, returning empty results"
                            )
                            if return_pagination:
                                return {"recipes": [], "has_next": False, "next_cursor": None}
                            return []

            logger.info(f"Searching recipes with params: {query_params}")
            logger.info(f"MUST ingredient conditions: {must_ingredient_conditions}")
            logger.info(
                f"MUST_NOT ingredient conditions: {must_not_ingredient_conditions}"
            )
            logger.info(f"Tag conditions: {tag_conditions}")

            # Check if inventory filtering is requested
            inventory_filter = search_params.get("inventory", False)

            # Build dynamic SQL query
            if use_keyset:
                paginated_sql = build_search_recipes_keyset_sql(
                    must_ingredient_conditions,
                    must_not_ingredient_conditions,
                    tag_conditions,
                    sort_by,
                    sort_order,
                    inventory_filter,
                    rating_type,
                )
            else:
                paginated_sql = build_search_recipes_paginated_sql(
                    must_ingredient_conditions,
                    must_not_ingredient_conditions,
                    tag_conditions,
                    sort_by,
                    sort_order,
                    inventory_filter,
                    rating_type,
                )
            # Get paginated results
            rows = cast(
                List[Dict[str, Any]], self.execute_query(paginated_sql, query_params)
            )

            # Debug: Log the number of rows returned from database
            logger.info(f"Database search returned {len(rows)} rows")

            # Group results by recipe ID and assemble full recipe objects
            recipes = {}
            for row in rows:
                recipe_id = row["id"]

                if recipe_id not in recipes:
                    # Create the base recipe object
                    recipes[recipe_id] = {
                        "id": recipe_id,
                        "name": row["name"],
                        "instructions": row["instructions"],
                        "description": row["description"],
                        "image_url": row.get("image_url"),
                        "source": row.get("source"),
                        "source_url": row.get("source_url"),
                        "avg_rating": row.get("avg_rating"),
                        "rating_count": row.get("rating_count"),
                        "user_rating": row.get("user_rating"),
                        "ingredients": [],
                        "tags": [],
                    }
                    if use_keyset:
                        recipes[recipe_id]["_sort_value"] = row.get("sort_value")

                    # Parse tags from GROUP_CONCAT format
                    if row.get("public_tags_data"):
                        for tag_data in row["public_tags_data"].split(":::"):
                            if tag_data and "|||" in tag_data:
                                tag_id, tag_name = tag_data.split("|||", 1)
                                recipes[recipe_id]["tags"].append(
                                    {
                                        "id": int(tag_id),
                                        "name": tag_name,
                                        "type": "public",
                                    }
                                )

                    if row.get("private_tags_data"):
                        for tag_data in row["private_tags_data"].split(":::"):
                            if tag_data and "|||" in tag_data:
                                tag_id, tag_name = tag_data.split("|||", 1)
                                recipes[recipe_id]["tags"].append(
                                    {
                                        "id": int(tag_id),
                                        "name": tag_name,
                                        "type": "private",
                                    }
                                )

                # Add ingredient if present
                if row.get("recipe_ingredient_id"):
                    ingredient = {
                        "ingredient_id": row["ingredient_id"],
                        "ingredient_name": row["ingredient_name"],
                        "ingredient_path": row.get("ingredient_path"),
                        "amount": row.get("amount"),
                        "unit_id": row.get("unit_id"),
                        "unit_name": row.get("unit_name"),
                        "unit_abbreviation": row.get("unit_abbreviation"),
                    }
                    recipes[recipe_id]["ingredients"].append(ingredient)

            # Assemble full names and hierarchy for all ingredients
            all_ingredients = []
            for recipe in recipes.values():
                all_ingredients.extend(recipe["ingredients"])

            # Extract all ingredient IDs for batch name lookup
            all_needed_ingredient_ids = extract_all_ingredient_ids(all_ingredients)
            ingredient_names_map = {}
            if all_needed_ingredient_ids:
                placeholders = ",".join("%s" for _ in all_needed_ingredient_ids)
                names_result = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        f"SELECT id, name FROM ingredients WHERE id IN ({placeholders})",
                        tuple(all_needed_ingredient_ids),
                    ),
                )
                ingredient_names_map = {row["id"]: row["name"] for row in names_result}

            # Assemble full_name and hierarchy for all ingredients
            assemble_ingredient_full_names(all_ingredients, ingredient_names_map)

            result = list(recipes.values())
            logger.info(f"Found {len(result)} recipes from search")

            if not return_pagination:
                for recipe in result:
                    recipe.pop("_sort_value", None)
                return result

            has_next = False
            next_cursor = None
            if use_keyset:
                if len(result) > limit:
                    has_next = True
                    result = result[:limit]
                if has_next and result:
                    last_recipe = result[-1]
                    sort_value = last_recipe.get("_sort_value")
                    next_cursor = self._encode_search_cursor(
                        sort_by, sort_order, sort_value, last_recipe["id"]
                    )
                for recipe in result:
                    recipe.pop("_sort_value", None)
            else:
                has_next = len(result) == limit
                for recipe in result:
                    recipe.pop("_sort_value", None)

            return {
                "recipes": result,
                "has_next": has_next,
                "next_cursor": next_cursor,
            }

        except Exception as e:
            logger.error(f"Error searching recipes with pagination: {str(e)}")
            raise

    def _encode_search_cursor(
        self, sort_by: str, sort_order: str, sort_value: Any, recipe_id: int
    ) -> str:
        if isinstance(sort_value, datetime):
            sort_value = sort_value.isoformat()
        payload = {
            "sort_by": sort_by,
            "sort_order": sort_order,
            "sort_value": sort_value,
            "id": recipe_id,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        return encoded

    def _decode_search_cursor(
        self, cursor: str, sort_by: str, sort_order: str
    ) -> Dict[str, Any]:
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            payload = json.loads(decoded)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValidationException("Invalid cursor value") from exc

        if payload.get("sort_by") != sort_by or payload.get("sort_order") != sort_order:
            raise ValidationException("Cursor does not match current sort parameters")

        sort_value = payload.get("sort_value")
        if sort_by == "created_at" and isinstance(sort_value, str):
            try:
                sort_value = datetime.fromisoformat(sort_value)
            except ValueError as exc:
                raise ValidationException("Invalid cursor timestamp") from exc

        cursor_id = payload.get("id")
        if cursor_id is None:
            raise ValidationException("Cursor is missing required fields")

        return {"sort_value": sort_value, "id": cursor_id}

    # --- End Pagination Methods ---

    # --- User Ingredient Tracking Methods ---

    def add_user_ingredient(self, user_id: str, ingredient_id: int) -> Dict[str, Any]:
        """Add an ingredient to a user's inventory, including all parent ingredients"""
        conn = None
        try:
            # Check if ingredient exists
            ingredient = self.get_ingredient(ingredient_id)
            if not ingredient:
                raise ValueError(f"Ingredient with ID {ingredient_id} does not exist")

            # Check if user already has this ingredient
            existing = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM user_ingredients WHERE cognito_user_id = %(user_id)s AND ingredient_id = %(ingredient_id)s",
                    {"user_id": user_id, "ingredient_id": ingredient_id},
                ),
            )

            if existing:
                # User already has this ingredient, raise exception
                raise ValueError(
                    f"Ingredient {ingredient_id} already exists in user's inventory"
                )

            # Get all parent ingredients from the path
            parent_ingredient_ids = []
            ingredient_path = ingredient["path"]

            # Parse the path to extract parent IDs
            # Path format is like "/1/23/45/" where 1, 23, 45 are ingredient IDs
            if ingredient_path:
                # Split by '/' and filter out empty strings
                path_parts = [part for part in ingredient_path.split("/") if part]
                # All parts except the last one are parent IDs
                parent_ingredient_ids = [int(part) for part in path_parts[:-1]]

            # Start a transaction to add all ingredients
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            # Add all parent ingredients first (if they don't already exist)
            for parent_id in parent_ingredient_ids:
                try:
                    # Use INSERT OR IGNORE to add parent ingredient only if it doesn't exist
                    cursor.execute(
                        """
                        INSERT INTO user_ingredients (cognito_user_id, ingredient_id)
                        VALUES (%s, %s)
                        ON CONFLICT (cognito_user_id, ingredient_id) DO NOTHING
                        """,
                        (user_id, parent_id),
                    )
                    if cursor.rowcount > 0:
                        logger.info(
                            f"Added parent ingredient {parent_id} to user {user_id}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Error adding parent ingredient {parent_id} to user {user_id}: {str(e)}"
                    )
                    # Continue with other parents - don't fail the entire operation

            # Add the main ingredient
            cursor.execute(
                "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (%s, %s)",
                (user_id, ingredient_id),
            )

            conn.commit()
            self._return_connection(conn)
            conn = None

            # Return the created record with ingredient details
            return {
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient["name"],
                "added_at": "now",  # PostgreSQL NOW()
                "parents_added": len(parent_ingredient_ids),
            }

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(
                f"Error adding ingredient {ingredient_id} to user {user_id}: {str(e)}"
            )
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def remove_user_ingredient(self, user_id: str, ingredient_id: int) -> bool:
        """Remove an ingredient from a user's inventory, but prevent removing parents if children exist"""
        try:
            # Check if user has this ingredient
            existing = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM user_ingredients WHERE cognito_user_id = %(user_id)s AND ingredient_id = %(ingredient_id)s",
                    {"user_id": user_id, "ingredient_id": ingredient_id},
                ),
            )

            if not existing:
                return False

            # Get the ingredient details to check for child ingredients
            ingredient = self.get_ingredient(ingredient_id)
            if not ingredient:
                return False

            # Check if this ingredient has any child ingredients in the user's inventory
            # Child ingredients would have paths that start with this ingredient's path
            ingredient_path = ingredient["path"]
            if ingredient_path:
                # Look for child ingredients in user's inventory
                child_ingredients = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        """
                        SELECT ui.ingredient_id, i.name, i.path
                        FROM user_ingredients ui
                        JOIN ingredients i ON ui.ingredient_id = i.id
                        WHERE ui.cognito_user_id = %(user_id)s
                        AND i.path LIKE %(child_path_pattern)s
                        AND i.id != %(ingredient_id)s
                        """,
                        {
                            "user_id": user_id,
                            "child_path_pattern": f"{ingredient_path}%",
                            "ingredient_id": ingredient_id,
                        },
                    ),
                )

                if child_ingredients:
                    # Get child ingredient names for the error message
                    child_names = [child["name"] for child in child_ingredients]
                    raise ValueError(
                        f"Cannot remove ingredient '{ingredient['name']}' because it has child ingredients in your inventory: {', '.join(child_names)}. Please remove the child ingredients first."
                    )

            # Remove the ingredient from user's inventory
            result = self.execute_query(
                "DELETE FROM user_ingredients WHERE cognito_user_id = %(user_id)s AND ingredient_id = %(ingredient_id)s",
                {"user_id": user_id, "ingredient_id": ingredient_id},
            )

            return result.get("rowCount", 0) > 0

        except Exception as e:
            logger.error(
                f"Error removing ingredient {ingredient_id} from user {user_id}: {str(e)}"
            )
            raise

    def get_user_ingredients(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all ingredients for a user with full ingredient details"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT ui.ingredient_id, ui.added_at, i.name, i.description, i.parent_id, i.path
                    FROM user_ingredients ui
                    JOIN ingredients i ON ui.ingredient_id = i.id
                    WHERE ui.cognito_user_id = %(user_id)s
                    ORDER BY i.name
                    """,
                    {"user_id": user_id},
                ),
            )
            return result

        except Exception as e:
            logger.error(f"Error getting ingredients for user {user_id}: {str(e)}")
            raise

    def add_user_ingredients_bulk(
        self, user_id: str, ingredient_ids: List[int]
    ) -> Dict[str, Any]:
        """Add multiple ingredients to a user's inventory"""
        conn = None
        try:
            if not ingredient_ids:
                return {
                    "added_count": 0,
                    "already_exists_count": 0,
                    "failed_count": 0,
                    "errors": [],
                }

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            added_count = 0
            already_exists_count = 0
            failed_count = 0
            errors = []

            for ingredient_id in ingredient_ids:
                try:
                    # Check if ingredient exists
                    ingredient_check = cast(
                        List[Dict[str, Any]],
                        self.execute_query(
                            "SELECT id FROM ingredients WHERE id = %(ingredient_id)s",
                            {"ingredient_id": ingredient_id},
                        ),
                    )
                    if not ingredient_check:
                        errors.append(
                            f"Ingredient with ID {ingredient_id} does not exist"
                        )
                        failed_count += 1
                        continue

                    # Check if user already has this ingredient
                    cursor.execute(
                        "SELECT id FROM user_ingredients WHERE cognito_user_id = %s AND ingredient_id = %s",
                        (user_id, ingredient_id),
                    )
                    existing = cursor.fetchone()

                    if existing:
                        already_exists_count += 1
                        continue

                    # Add the ingredient
                    cursor.execute(
                        "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (%s, %s)",
                        (user_id, ingredient_id),
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
            logger.error(f"Error in bulk add ingredients for user {user_id}: {str(e)}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def remove_user_ingredients_bulk(
        self, user_id: str, ingredient_ids: List[int]
    ) -> Dict[str, Any]:
        """Remove multiple ingredients from a user's inventory with ordered deletion (children first, then parents)"""
        conn = None
        try:
            if not ingredient_ids:
                logger.info(
                    f"Bulk remove called for user {user_id} with empty ingredient list"
                )
                return {"removed_count": 0, "not_found_count": 0}

            logger.info(
                f"Starting bulk remove for user {user_id} with {len(ingredient_ids)} ingredients: {ingredient_ids}"
            )

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN")

            removed_count = 0
            not_found_count = 0
            validation_errors = []

            # First pass: validate all ingredients exist and collect their details
            logger.info(
                f"Validating {len(ingredient_ids)} ingredients for existence and collecting details"
            )
            valid_ingredients = []
            for ingredient_id in ingredient_ids:
                try:
                    # Check if user has this ingredient
                    cursor.execute(
                        "SELECT id FROM user_ingredients WHERE cognito_user_id = %s AND ingredient_id = %s",
                        (user_id, ingredient_id),
                    )
                    existing = cursor.fetchone()

                    if not existing:
                        logger.debug(
                            f"Ingredient {ingredient_id} not found in user {user_id} inventory"
                        )
                        not_found_count += 1
                        continue

                    # Get the ingredient details
                    cursor.execute(
                        "SELECT id, name, path FROM ingredients WHERE id = %s",
                        (ingredient_id,),
                    )
                    ingredient = cursor.fetchone()

                    if not ingredient:
                        logger.warning(
                            f"Ingredient {ingredient_id} not found in ingredients table"
                        )
                        not_found_count += 1
                        continue

                    valid_ingredients.append(
                        {
                            "id": ingredient[0],
                            "name": ingredient[1],
                            "path": ingredient[2] or "",
                        }
                    )
                    logger.debug(
                        f"Ingredient {ingredient_id} ({ingredient[1]}) found with path: {ingredient[2]}"
                    )

                except Exception as e:
                    error_msg = f"Error validating ingredient {ingredient_id}: {str(e)}"
                    logger.error(error_msg)
                    validation_errors.append(error_msg)

            if validation_errors:
                conn.rollback()
                error_summary = f"Validation failed for {len(validation_errors)} ingredients: {'; '.join(validation_errors)}"
                logger.error(
                    f"Bulk remove validation failed for user {user_id}: {error_summary}"
                )
                raise ValueError(error_summary)

            # Create a set of ingredient IDs being removed for quick lookup
            ingredient_ids_to_remove = set(ing["id"] for ing in valid_ingredients)

            # Second pass: check for parent-child conflicts only for ingredients that won't be removed
            logger.info(
                f"Checking for parent-child conflicts for {len(valid_ingredients)} valid ingredients"
            )
            for ingredient in valid_ingredients:
                try:
                    ingredient_id = ingredient["id"]
                    ingredient_name = ingredient["name"]
                    ingredient_path = ingredient["path"]

                    # Check if this ingredient has any child ingredients in the user's inventory
                    if ingredient_path:
                        # Look for child ingredients in user's inventory
                        cursor.execute(
                            """
                            SELECT ui.ingredient_id, i.name, i.path
                            FROM user_ingredients ui
                            JOIN ingredients i ON ui.ingredient_id = i.id
                            WHERE ui.cognito_user_id = %s 
                            AND i.path LIKE %s
                            AND i.id != %s
                            """,
                            (user_id, f"{ingredient_path}%", ingredient_id),
                        )
                        child_ingredients = cursor.fetchall()

                        if child_ingredients:
                            # Check if any child ingredients are NOT being removed
                            children_not_being_removed = []
                            for child in child_ingredients:
                                child_id = child[0]
                                child_name = child[1]
                                if child_id not in ingredient_ids_to_remove:
                                    children_not_being_removed.append(child_name)

                            if children_not_being_removed:
                                error_msg = f"Cannot remove ingredient '{ingredient_name}' because it has child ingredients in your inventory that are not being removed: {', '.join(children_not_being_removed)}. Please include these child ingredients in the removal or remove them first."
                                logger.warning(
                                    f"Parent-child validation failed for ingredient {ingredient_id}: {error_msg}"
                                )
                                validation_errors.append(error_msg)
                                continue
                            else:
                                logger.debug(
                                    f"Ingredient {ingredient_id} ({ingredient_name}) has children but they are all being removed"
                                )

                    logger.debug(
                        f"Ingredient {ingredient_id} ({ingredient_name}) passed validation"
                    )

                except Exception as e:
                    error_msg = f"Error validating ingredient {ingredient_id}: {str(e)}"
                    logger.error(error_msg)
                    validation_errors.append(error_msg)

            # If there are validation errors, rollback and raise exception
            if validation_errors:
                conn.rollback()
                error_summary = f"Validation failed for {len(validation_errors)} ingredients: {'; '.join(validation_errors)}"
                logger.error(
                    f"Bulk remove validation failed for user {user_id}: {error_summary}"
                )
                raise ValueError(error_summary)

            # Third pass: sort ingredients by path depth (deepest first) to ensure children are deleted before parents
            logger.info("Sorting ingredients by path depth for ordered deletion")
            valid_ingredients.sort(
                key=lambda x: len(x["path"].split("/")) if x["path"] else 0,
                reverse=True,
            )

            # Fourth pass: remove ingredients in sorted order (children first, then parents)
            logger.info(
                f"Proceeding to remove {len(valid_ingredients)} ingredients in sorted order for user {user_id}"
            )
            for ingredient in valid_ingredients:
                try:
                    ingredient_id = ingredient["id"]
                    ingredient_name = ingredient["name"]

                    # Check if user still has this ingredient (re-check in case something changed)
                    cursor.execute(
                        "SELECT id FROM user_ingredients WHERE cognito_user_id = %s AND ingredient_id = %s",
                        (user_id, ingredient_id),
                    )
                    existing = cursor.fetchone()

                    if not existing:
                        logger.debug(
                            f"Ingredient {ingredient_id} no longer in user {user_id} inventory, skipping"
                        )
                        continue

                    # Remove the ingredient
                    cursor.execute(
                        "DELETE FROM user_ingredients WHERE cognito_user_id = %s AND ingredient_id = %s",
                        (user_id, ingredient_id),
                    )
                    removed_count += 1
                    logger.debug(
                        f"Successfully removed ingredient {ingredient_id} ({ingredient_name}) for user {user_id}"
                    )

                except Exception as e:
                    logger.error(
                        f"Error removing ingredient {ingredient_id} for user {user_id}: {str(e)}"
                    )
                    # Continue with other ingredients

            conn.commit()
            logger.info(
                f"Bulk remove completed for user {user_id}: {removed_count} removed, {not_found_count} not found"
            )

            return {"removed_count": removed_count, "not_found_count": not_found_count}

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(
                f"Error in bulk remove ingredients for user {user_id}: {str(e)}"
            )
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def get_ingredient_recommendations(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get ingredient recommendations that would unlock the most new recipes.

        This finds ingredients the user doesn't have that would complete the most
        "almost makeable" recipes (recipes where user has all but one ingredient).
        Respects allow_substitution rules for ingredient matching.
        """
        try:
            from .sql_queries import get_ingredient_recommendations_sql

            query = get_ingredient_recommendations_sql()

            result = cast(
                List[Dict[str, Any]],
                self.execute_query(query, {"user_id": user_id, "limit": limit}),
            )

            # Parse the recipe_names field (pipe-delimited string) into a list
            for row in result:
                if row.get("recipe_names"):
                    row["recipe_names"] = row["recipe_names"].split("|||")
                else:
                    row["recipe_names"] = []

            return result

        except Exception as e:
            logger.error(
                f"Error getting ingredient recommendations for user {user_id}: {str(e)}"
            )
            raise

    # --- End User Ingredient Tracking Methods ---

    # --- Count Methods ---

    def get_recipes_count(self) -> int:
        """Get total count of recipes"""
        try:
            result = self.execute_query(get_recipes_count_sql)
            return result[0]["total_count"] if result else 0
        except Exception as e:
            logger.error(f"Error getting recipes count: {str(e)}")
            raise

    def get_ingredients_count(self) -> int:
        """Get total count of ingredients"""
        try:
            result = self.execute_query(get_ingredients_count_sql)
            return result[0]["total_count"] if result else 0
        except Exception as e:
            logger.error(f"Error getting ingredients count: {str(e)}")
            raise

    # --- End Count Methods ---
