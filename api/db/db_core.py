import logging
import sqlite3
import time
import functools
import os
from typing import Dict, List, Optional, Any, Union, Tuple, cast

from .db_utils import extract_all_ingredient_ids, assemble_ingredient_full_names
from .sql_queries import (
    get_recipe_by_id_sql,
    get_all_recipes_sql,
    get_recipe_ingredients_by_recipe_id_sql_factory,
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def retry_on_db_locked(max_retries=3, initial_backoff=0.1):
    """Decorator to retry operations when database is locked"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            backoff = initial_backoff
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        last_error = e
                        logger.warning(
                            f"Database locked on attempt {attempt + 1}/{max_retries}. "
                            f"Retrying in {backoff:.2f}s..."
                        )
                        time.sleep(backoff)
                        backoff *= 2  # Exponential backoff
                    else:
                        # Other SQLite operational error, don't retry
                        raise
            logger.error(
                f"Database still locked after {max_retries} attempts: {str(last_error)}"
            )
            raise last_error or sqlite3.OperationalError(
                "Database still locked after multiple attempts"
            )

        return wrapper

    return decorator


class Database:
    def __init__(self):
        """Initialize the database connection to SQLite on EFS"""
        logger.info("Initializing Database class with SQLite on EFS")
        try:
            # Read database path from environment variable at runtime, not import time
            self.db_path = os.environ.get("DB_PATH", "/mnt/efs/cocktaildb.db")
            logger.info(f"Using database path: {self.db_path}")
            logger.info(
                f"DB_PATH environment variable: {os.environ.get('DB_PATH', 'not set')}"
            )
            logger.info(f"Database file exists: {os.path.exists(self.db_path)}")

            if os.path.exists(self.db_path):
                logger.info(
                    f"Database file size: {os.path.getsize(self.db_path)} bytes"
                )
            else:
                logger.warning(f"Database file does not exist at: {self.db_path}")

            # Test the connection
            self._test_connection()
            logger.info(
                f"Database initialization complete using SQLite at {self.db_path}"
            )
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}", exc_info=True)
            raise

    def _test_connection(self):
        """Test the database connection"""
        logger.info("Testing database connection...")
        retry_count = 0
        max_retries = 3
        last_error = None

        while retry_count < max_retries:
            try:
                # Actually open the connection to ensure database exists
                conn = self._get_connection()
                try:
                    conn.execute("SELECT * from ingredients limit 1")
                    logger.info("Successfully connected to database")
                    return
                finally:
                    conn.close()
            except Exception as e:
                last_error = e
                retry_count += 1
                logger.warning(
                    f"Connection attempt {retry_count} failed: {str(e)}. "
                    f"{'Retrying...' if retry_count < max_retries else 'Max retries reached.'}"
                )
                if retry_count < max_retries:
                    import time

                    time.sleep(2**retry_count)  # 2, 4, 8 seconds
        logger.error(
            f"Failed to connect to database after {max_retries} attempts: {str(last_error)}",
            exc_info=True,
        )
        raise last_error or Exception(
            "Failed to connect to database after multiple attempts"
        )

    def _get_connection(self):
        """Get a SQLite connection with proper settings"""
        # Set longer timeout for waiting on locks (30 seconds)
        conn = sqlite3.connect(
            self.db_path,
            timeout=10.0,  # Wait up to 10 seconds for the lock
            isolation_level=None,  # Enable autocommit mode, explicit transactions still work
        )
        # Set busy timeout to handle cases where the database is locked
        conn.execute("PRAGMA busy_timeout = 10000")  # 10 seconds in milliseconds
        # Optimize for concurrent access
        conn.execute(
            "PRAGMA journal_mode = WAL"
        )  # Write-Ahead Logging for better concurrency
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn

    @retry_on_db_locked()
    def execute_query(
        self, sql: str, parameters: Optional[Union[Dict[str, Any], Tuple]] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, int]]:
        """Execute a SQL query using SQLite"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)
            if sql.strip().upper().startswith(("SELECT", "WITH")):
                # For SELECT queries, return results
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
                return result
            else:
                # For non-SELECT queries, commit and return affected rows
                conn.commit()
                return {"rowCount": cursor.rowcount}
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error executing query: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    @retry_on_db_locked()
    def execute_transaction(self, queries: List[Dict[str, Any]]) -> None:
        """Execute multiple queries in a transaction"""
        conn = None
        try:
            conn = self._get_connection()
            conn.execute(
                "BEGIN IMMEDIATE"
            )  # Get lock immediately instead of on first write
            cursor = conn.cursor()

            for query in queries:
                sql = query.get("sql")
                params = query.get("parameters", {})
                if sql is not None:  # Handle case where sql might be None
                    cursor.execute(sql, params)
                else:
                    logger.warning("Skipping query with None SQL statement")

            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error executing transaction: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    @retry_on_db_locked()
    def create_ingredient(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new ingredient"""
        try:
            # SQLite doesn't have a direct equivalent to Postgres' add_ingredient function
            # We'll implement the path generation logic here
            parent_path = None
            if data.get("parent_id"):
                # Get parent's path
                parent = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        "SELECT path FROM ingredients WHERE id = :parent_id",
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
                    INSERT INTO ingredients (name, description, parent_id)
                    VALUES (:name, :description, :parent_id)
                    """,
                    {
                        "name": data.get("name").title() if data.get("name") else None,
                        "description": data.get("description"),
                        "parent_id": data.get("parent_id"),
                    },
                )
                new_id = cursor.lastrowid
                if new_id is None:
                    raise ValueError("Failed to get ingredient ID after insertion")

                # Generate the path
                if parent_path:
                    path = f"{parent_path}{new_id}/"
                else:
                    path = f"/{new_id}/"

                # Update the path
                cursor.execute(
                    "UPDATE ingredients SET path = :path WHERE id = :id",
                    {"path": path, "id": new_id},
                )

                conn.commit()

                # Fetch the created ingredient
                ingredient = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        "SELECT id, name, description, parent_id, path FROM ingredients WHERE id = :id",
                        {"id": new_id},
                    ),
                )
                return ingredient[0]
            except Exception as e:
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()
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
                        "SELECT parent_id, path FROM ingredients WHERE id = :id",
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
                            "SELECT path FROM ingredients WHERE id = :id",
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

                # Update ingredient with new path
                self.execute_query(
                    """
                    UPDATE ingredients 
                    SET name = COALESCE(:name, name),
                        description = COALESCE(:description, description),
                        parent_id = :parent_id,
                        path = :path
                    WHERE id = :id
                    """,
                    {
                        "id": ingredient_id,
                        "name": data.get("name"),
                        "description": data.get("description"),
                        "parent_id": new_parent_id,
                        "path": new_path,
                    },
                )

                # Update paths of descendants
                descendants = self.get_ingredient_descendants(ingredient_id)
                for descendant in descendants:
                    # Replace old path prefix with new path prefix
                    descendant_path = descendant["path"]
                    new_descendant_path = descendant_path.replace(old_path, new_path)

                    self.execute_query(
                        "UPDATE ingredients SET path = :path WHERE id = :id",
                        {"path": new_descendant_path, "id": descendant["id"]},
                    )
            else:
                # Simple update without changing the hierarchy
                self.execute_query(
                    """
                    UPDATE ingredients 
                    SET name = COALESCE(:name, name),
                        description = COALESCE(:description, description)
                    WHERE id = :id
                    """,
                    {
                        "id": ingredient_id,
                        "name": data.get("name"),
                        "description": data.get("description"),
                    },
                )

            # Fetch the updated ingredient
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path FROM ingredients WHERE id = :id",
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
                    "SELECT id FROM ingredients WHERE id = :id", {"id": ingredient_id}
                ),
            )
            if not ingredient:
                return False

            # Check if it has children
            children = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM ingredients WHERE parent_id = :parent_id",
                    {"parent_id": ingredient_id},
                ),
            )
            if children:
                raise ValueError("Cannot delete ingredient with child ingredients")

            # Check if it's used in recipes
            used_in_recipes = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT recipe_id FROM recipe_ingredients WHERE ingredient_id = :ingredient_id LIMIT 1",
                    {"ingredient_id": ingredient_id},
                ),
            )
            if used_in_recipes:
                raise ValueError("Cannot delete ingredient used in recipes")

            # Delete the ingredient
            self.execute_query(
                "DELETE FROM ingredients WHERE id = :id", {"id": ingredient_id}
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
                    "SELECT id, name, description, parent_id, path FROM ingredients ORDER BY path"
                ),
            )
            return result
        except Exception as e:
            logger.error(f"Error getting ingredients: {str(e)}")
            raise

    def get_ingredient(self, ingredient_id: int) -> Optional[Dict[str, Any]]:
        """Get a single ingredient by ID"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path FROM ingredients WHERE id = :id",
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
                    "SELECT path FROM ingredients WHERE id = :id", {"id": ingredient_id}
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
                WHERE path LIKE :path_pattern AND id != :id
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

    @retry_on_db_locked()
    def create_recipe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new recipe with its ingredients"""
        conn = None
        try:
            conn = self._get_connection()
            conn.execute("BEGIN IMMEDIATE")  # Get lock immediately
            cursor = conn.cursor()

            # Create the recipe
            cursor.execute(
                """
                INSERT INTO recipes (name, instructions, description, image_url, source, source_url)
                VALUES (:name, :instructions, :description, :image_url, :source, :source_url)
                """,
                {
                    "name": data["name"].title() if data["name"] else None,
                    "instructions": data.get("instructions"),
                    "description": data.get("description"),
                    "image_url": data.get("image_url"),
                    "source": data.get("source"),
                    "source_url": data.get("source_url"),
                },
            )

            # Get the recipe ID
            recipe_id = cursor.lastrowid
            if recipe_id is None:
                raise ValueError("Failed to get recipe ID after insertion")

            # Add recipe ingredients
            if "ingredients" in data:
                for ingredient in data["ingredients"]:
                    cursor.execute(
                        """
                        INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
                        VALUES (:recipe_id, :ingredient_id, :unit_id, :amount)
                        """,
                        {
                            "recipe_id": recipe_id,
                            "ingredient_id": ingredient["ingredient_id"],
                            "unit_id": ingredient.get("unit_id"),
                            "amount": ingredient.get("amount"),
                        },
                    )

            # Commit the transaction
            conn.commit()
            conn.close()
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
                conn.close()

    def get_recipes(
        self, cognito_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all recipes for list view (optimized - only ingredient counts, not full details)"""
        try:
            start_time = time.time()

            # Get basic recipe data
            params = {"cognito_user_id": cognito_user_id}
            recipes_result = cast(
                List[Dict[str, Any]],
                self.execute_query(get_all_recipes_sql, params),
            )

            if not recipes_result:
                return []

            # Get ingredient counts efficiently for all recipes in one query
            recipe_ids = [recipe["id"] for recipe in recipes_result]
            placeholders = ",".join("?" for _ in recipe_ids)

            ingredient_counts = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    f"""
                    SELECT recipe_id, COUNT(*) as ingredient_count
                    FROM recipe_ingredients
                    WHERE recipe_id IN ({placeholders})
                    GROUP BY recipe_id
                    """,
                    tuple(recipe_ids),
                ),
            )

            # Create a lookup map for ingredient counts
            count_map = {
                row["recipe_id"]: row["ingredient_count"] for row in ingredient_counts
            }

            # Add ingredient_count to each recipe
            for recipe in recipes_result:
                recipe["ingredient_count"] = count_map.get(recipe["id"], 0)

            total_time = time.time() - start_time
            logger.info(
                f"get_recipes: Total execution time: {total_time:.3f}s (optimized)"
            )
            return recipes_result

        except Exception as e:
            logger.error(f"Error getting recipes: {str(e)}")
            raise

    def get_recipes_with_ingredients(
        self, cognito_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all recipes with their full ingredient details (for detailed views)"""
        try:
            start_time = time.time()
            # 1. Get all recipes
            recipes_start = time.time()
            params = {"cognito_user_id": cognito_user_id}
            recipes_result = cast(
                List[Dict[str, Any]],
                self.execute_query(get_all_recipes_sql, params),
            )
            recipes_end = time.time()
            logger.info(
                f"get_recipes_with_ingredients: Fetched {len(recipes_result)} recipes in {recipes_end - recipes_start:.3f}s"
            )
            if not recipes_result:
                return []
            # 2. Fetch all recipe ingredients across all recipes
            recipe_ids = [recipe["id"] for recipe in recipes_result]
            ingredients_start = time.time()
            all_recipe_ingredients_list = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    get_recipe_ingredients_by_recipe_id_sql_factory(recipe_ids),
                    tuple(recipe_ids),
                ),
            )
            ingredients_end = time.time()
            logger.info(
                f"get_recipes_with_ingredients: Fetched {len(all_recipe_ingredients_list)} recipe ingredient entries in {ingredients_end - ingredients_start:.3f}s"
            )
            # 3. Identify all necessary ingredient IDs (direct + ancestors) using the helper
            ids_start = time.time()
            all_needed_ingredient_ids = extract_all_ingredient_ids(
                all_recipe_ingredients_list
            )
            ids_end = time.time()
            logger.info(
                f"get_recipes_with_ingredients: Identified {len(all_needed_ingredient_ids)} unique ingredient IDs in {ids_end - ids_start:.3f}s"
            )
            # 4. Fetch names for all needed ingredients in one query
            fetch_names_start = time.time()
            ingredient_names_map = {}
            if all_needed_ingredient_ids:
                placeholders = ",".join("?" for _ in all_needed_ingredient_ids)
                names_result = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        f"SELECT id, name FROM ingredients WHERE id IN ({placeholders})",
                        tuple(all_needed_ingredient_ids),
                    ),
                )
                ingredient_names_map = {row["id"]: row["name"] for row in names_result}
            fetch_names_end = time.time()
            logger.info(
                f"get_recipes_with_ingredients: Fetched {len(ingredient_names_map)} ingredient names in {fetch_names_end - fetch_names_start:.3f}s"
            )
            # 5. Assemble full names using the helper method
            assemble_names_start = time.time()
            assemble_ingredient_full_names(
                all_recipe_ingredients_list, ingredient_names_map
            )
            assemble_names_end = time.time()
            logger.info(
                f"get_recipes_with_ingredients: Assembled full names in {assemble_names_end - assemble_names_start:.3f}s"
            )
            # 6. Group ingredients by recipe
            grouping_start = time.time()
            recipe_ingredients_grouped = {recipe_id: [] for recipe_id in recipe_ids}
            for ing_data in all_recipe_ingredients_list:
                recipe_id = ing_data["recipe_id"]
                # Use the actual recipe_ingredient_id as 'id' for consistency if needed frontend
                ing_data["id"] = ing_data["recipe_ingredient_id"]
                recipe_ingredients_grouped[recipe_id].append(ing_data)
            grouping_end = time.time()
            logger.info(
                f"get_recipes_with_ingredients: Grouped ingredients in {grouping_end - grouping_start:.3f}s"
            )
            # 7. Combine recipes with their assembled ingredients
            combine_start = time.time()
            for recipe in recipes_result:
                recipe["ingredients"] = recipe_ingredients_grouped.get(recipe["id"], [])
            combine_end = time.time()
            logger.info(
                f"get_recipes_with_ingredients: Combined recipes and ingredients in {combine_end - combine_start:.3f}s"
            )
            total_time = time.time() - start_time
            logger.info(
                f"get_recipes_with_ingredients: Total execution time: {total_time:.3f}s"
            )
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
            if public_tags_str:
                for tag_data_str in public_tags_str.split(":::"):
                    try:
                        tag_id_str, tag_name = tag_data_str.split("|||", 1)
                        recipe["tags"].append(
                            {"id": int(tag_id_str), "name": tag_name, "type": "public"}
                        )
                    except ValueError as ve:
                        logger.warning(
                            f"Could not parse public tag_data_str '{tag_data_str}': {ve}"
                        )
            # Process private tags
            private_tags_str = recipe_data.get("private_tags_data")
            if (
                private_tags_str and cognito_user_id
            ):  # Only process if user_id was present for the query
                for tag_data_str in private_tags_str.split(":::"):
                    try:
                        tag_id_str, tag_name = tag_data_str.split("|||", 1)
                        recipe["tags"].append(
                            {"id": int(tag_id_str), "name": tag_name, "type": "private"}
                        )
                    except ValueError as ve:
                        logger.warning(
                            f"Could not parse private tag_data_str '{tag_data_str}': {ve}"
                        )
            # Fetch ingredients separately
            recipe["ingredients"] = self._get_recipe_ingredients(recipe_id)
            logger.info(
                f"Final assembled recipe {recipe_id} with tags: {recipe.get('tags')} and ingredients."
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
                """
                SELECT ri.id, ri.amount, ri.ingredient_id, i.name as ingredient_name,
                       ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation,
                       i.path as ingredient_path
                FROM recipe_ingredients ri
                JOIN ingredients i ON ri.ingredient_id = i.id
                LEFT JOIN units u ON ri.unit_id = u.id
                WHERE ri.recipe_id = :recipe_id
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
            placeholders = ",".join("?" for _ in all_needed_ids)
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

    @retry_on_db_locked()
    def delete_recipe(self, recipe_id: int) -> bool:
        """Delete a recipe and its ingredients"""
        conn = None
        try:
            conn = self._get_connection()
            conn.execute("BEGIN IMMEDIATE")  # Get lock immediately
            cursor = conn.cursor()

            # Check if recipe exists
            recipe = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM recipes WHERE id = :id", {"id": recipe_id}
                ),
            )
            if not recipe:
                return False

            # Note: We don't need to explicitly delete recipe_ingredients, ratings, or tags
            # because the ON DELETE CASCADE constraint will handle this automatically
            # Delete the recipe
            cursor.execute("DELETE FROM recipes WHERE id = :id", {"id": recipe_id})

            # Commit the transaction
            conn.commit()
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error deleting recipe {recipe_id}: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    @retry_on_db_locked()
    def update_recipe(
        self, recipe_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing recipe"""
        conn = None
        try:
            # Check if recipe exists first
            existing = self.execute_query(
                "SELECT id FROM recipes WHERE id = :id", {"id": recipe_id}
            )
            if not existing:
                return None

            conn = self._get_connection()
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

            # Update the main recipe details
            cursor.execute(
                """
                UPDATE recipes
                SET name = COALESCE(:name, name),
                    instructions = COALESCE(:instructions, instructions),
                    description = COALESCE(:description, description),
                    image_url = COALESCE(:image_url, image_url),
                    source = COALESCE(:source, source),
                    source_url = COALESCE(:source_url, source_url)
                WHERE id = :id
                """,
                {
                    "id": recipe_id,
                    "name": data.get("name"),
                    "instructions": data.get("instructions"),
                    "description": data.get("description"),
                    "image_url": data.get("image_url"),
                    "source": data.get("source"),
                    "source_url": data.get("source_url"),
                },
            )

            # Update ingredients if provided
            if "ingredients" in data:
                # Delete existing ingredients for this recipe
                cursor.execute(
                    "DELETE FROM recipe_ingredients WHERE recipe_id = :recipe_id",
                    {"recipe_id": recipe_id},
                )

                # Insert new ingredients
                for ingredient in data["ingredients"]:
                    cursor.execute(
                        """
                        INSERT INTO recipe_ingredients (recipe_id, ingredient_id, unit_id, amount)
                        VALUES (:recipe_id, :ingredient_id, :unit_id, :amount)
                        """,
                        {
                            "recipe_id": recipe_id,
                            "ingredient_id": ingredient["ingredient_id"],
                            "unit_id": ingredient.get("unit_id"),
                            "amount": ingredient.get("amount"),
                        },
                    )

            conn.commit()
            conn.close()
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
                conn.close()

    @retry_on_db_locked()
    def get_recipe_ratings(self, recipe_id: int) -> List[Dict[str, Any]]:
        """Get all ratings for a recipe"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating
                    FROM ratings 
                    WHERE recipe_id = :recipe_id
                    """,
                    {"recipe_id": recipe_id},
                ),
            )
            return result
        except Exception as e:
            logger.error(f"Error getting ratings for recipe {recipe_id}: {str(e)}")
            raise

    @retry_on_db_locked()
    def get_user_rating(self, recipe_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific user's rating for a recipe"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating, created_at
                    FROM ratings 
                    WHERE recipe_id = :recipe_id AND cognito_user_id = :user_id
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

    @retry_on_db_locked()
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
                    "SELECT id FROM recipes WHERE id = :id", {"id": data["recipe_id"]}
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
                    WHERE cognito_user_id = :user_id AND recipe_id = :recipe_id
                    """,
                    {
                        "user_id": data["cognito_user_id"],
                        "recipe_id": data["recipe_id"],
                    },
                ),
            )

            conn = self._get_connection()
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

            rating_id = None
            if existing_rating:
                # Update existing rating
                rating_id = existing_rating[0]["id"]
                cursor.execute(
                    """
                    UPDATE ratings
                    SET rating = :rating
                    WHERE cognito_user_id = :user_id AND recipe_id = :recipe_id
                    """,
                    {
                        "user_id": data["cognito_user_id"],
                        "recipe_id": data["recipe_id"],
                        "rating": data["rating"],
                    },
                )
            else:
                # Insert new rating
                cursor.execute(
                    """
                    INSERT INTO ratings (cognito_user_id, cognito_username, recipe_id, rating)
                    VALUES (:cognito_user_id, :cognito_username, :recipe_id, :rating)
                    """,
                    {
                        "cognito_user_id": data["cognito_user_id"],
                        "cognito_username": data["cognito_username"],
                        "recipe_id": data["recipe_id"],
                        "rating": data["rating"],
                    },
                )
                rating_id = cursor.lastrowid
                if rating_id is None:
                    raise ValueError("Failed to get rating ID after insertion")

            conn.commit()
            conn.close()
            conn = None

            # Fetch the created/updated rating
            rating = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating
                    FROM ratings
                    WHERE id = :id
                    """,
                    {"id": rating_id},
                ),
            )

            # Also fetch the updated average rating and count
            recipe_updated = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT avg_rating, rating_count FROM recipes WHERE id = :id",
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
                conn.close()

    @retry_on_db_locked()
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
                    WHERE cognito_user_id = :user_id AND recipe_id = :recipe_id
                    """,
                    {"user_id": user_id, "recipe_id": recipe_id},
                ),
            )
            if not existing_rating:
                raise ValueError("Rating not found for this user and recipe")

            conn = self._get_connection()
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

            # Delete the rating
            cursor.execute(
                """
                DELETE FROM ratings
                WHERE cognito_user_id = :user_id AND recipe_id = :recipe_id
                """,
                {"user_id": user_id, "recipe_id": recipe_id},
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
                conn.close()

    @retry_on_db_locked()
    def search_recipes(self, search_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search recipes with various criteria including ingredient queries

        Args:
            search_params: Dictionary containing search parameters:
                - name: Search recipe names (string)
                - min_rating: Minimum average rating (float)
                - tags: List of tags to search for (List[str])
                - ingredients: List of ingredient conditions (List[Dict])
                    Each condition has:
                    - id: Ingredient ID (will search for this ID in the path)
                    - operator: MUST or MUST_NOT

        Returns:
            List of matching recipes with their ingredients
        """
        try:
            # Start building the query
            query = """
            WITH recipe_data AS (
                SELECT id, name, instructions, description, image_url, source, source_url, avg_rating, rating_count
                FROM recipes
                WHERE 1=1
            """
            params = {}
            # Add name search condition if provided
            if search_params.get("name"):
                query += " AND name LIKE :name"
                params["name"] = f"%{search_params['name']}%"
            # Add minimum rating condition if provided
            if search_params.get("min_rating"):
                query += " AND avg_rating >= :min_rating"
                params["min_rating"] = float(search_params["min_rating"])
            # Add tag filtering if tags are provided
            if search_params.get("tags"):
                tags = search_params["tags"]
                if tags:  # Ensure tags list is not empty
                    query += """
                    AND EXISTS (
                    SELECT 1
                    FROM recipe_public_tags rpt
                    JOIN public_tags pt ON rpt.tag_id = pt.id
                    WHERE rpt.recipe_id = recipes.id AND pt.name IN ({})
                    )
                    """.format(",".join([":tag" + str(i) for i in range(len(tags))]))
                    for i, tag_name in enumerate(tags):
                        params["tag" + str(i)] = tag_name
            # Close the recipes CTE
            query += ")"

            # Handle ingredient filtering with different logical operators
            if (
                search_params.get("ingredients")
                and len(search_params["ingredients"]) > 0
            ):
                # Create separate CTEs for different ingredient operators
                must_ingredients = [
                    i for i in search_params["ingredients"] if i["operator"] == "MUST"
                ]
                must_not_ingredients = [
                    i
                    for i in search_params["ingredients"]
                    if i["operator"] == "MUST_NOT"
                ]
                # For MUST ingredients: recipes must contain at least one ingredient from each category
                if must_ingredients:
                    query += """
                    , must_matches AS (
                        SELECT recipe_id, COUNT(DISTINCT must_group) as match_count
                        FROM (
                    """
                    for i, ingredient in enumerate(must_ingredients):
                        if i > 0:
                            query += " UNION ALL "
                        query += f"""
                            SELECT ri.recipe_id, {i} as must_group
                            FROM recipe_ingredients ri 
                            JOIN ingredients i ON ri.ingredient_id = i.id
                            WHERE i.path LIKE :must_ing_path_{i}
                        """
                        # Use '%/ID/%' to match the ID in the path
                        params[f"must_ing_path_{i}"] = f"%/{ingredient['id']}/%"

                    query += """
                        ) must_groups
                        GROUP BY recipe_id
                        HAVING match_count = :must_ing_count
                    )
                    """
                    params["must_ing_count"] = len(must_ingredients)

                # For MUST_NOT ingredients: recipes must contain NONE of these ingredients or their children
                if must_not_ingredients:
                    query += """
                    , must_not_matches AS (
                        SELECT r.id as recipe_id
                        FROM recipe_data r
                        WHERE NOT EXISTS (
                            SELECT 1 
                            FROM recipe_ingredients ri
                            JOIN ingredients i ON ri.ingredient_id = i.id
                            WHERE ri.recipe_id = r.id
                            AND (
                    """
                    for i, ingredient in enumerate(must_not_ingredients):
                        if i > 0:
                            query += " OR "
                        query += f"i.path LIKE :must_not_ing_path_{i}"
                        params[f"must_not_ing_path_{i}"] = f"%/{ingredient['id']}/%"

                    query += """
                            )
                        )
                    )
                    """

                # Build the final query combining all conditions
                query += """
                SELECT r.*
                FROM recipe_data r
                """
                # Join with MUST ingredients if provided
                if must_ingredients:
                    query += " INNER JOIN must_matches mm ON r.id = mm.recipe_id"
                # Join with MUST_NOT ingredients if provided
                if must_not_ingredients:
                    query += " INNER JOIN must_not_matches mnm ON r.id = mnm.recipe_id"
                # Order by rating
                query += " ORDER BY r.avg_rating DESC"

            else:
                # Simple query without ingredient filtering
                query += "SELECT * FROM recipe_data ORDER BY avg_rating DESC"

            # Execute the query
            # Log the final query with parameter placeholders
            logger.info(f"Executing search query: {query}")

            # Log the query with actual parameter values for debugging
            debug_query = query
            for param_name, param_value in params.items():
                placeholder = f":{param_name}"
                if placeholder in debug_query:
                    debug_query = debug_query.replace(placeholder, str(param_value))

            logger.debug(f"Search query with params: {debug_query}")
            recipes_result = cast(
                List[Dict[str, Any]],
                self.execute_query(query, params),
            )

            # Get ingredient counts efficiently for search results
            if recipes_result:
                recipe_ids = [recipe["id"] for recipe in recipes_result]
                placeholders = ",".join("?" for _ in recipe_ids)

                ingredient_counts = cast(
                    List[Dict[str, Any]],
                    self.execute_query(
                        f"""
                        SELECT recipe_id, COUNT(*) as ingredient_count
                        FROM recipe_ingredients
                        WHERE recipe_id IN ({placeholders})
                        GROUP BY recipe_id
                        """,
                        tuple(recipe_ids),
                    ),
                )

                # Create a lookup map for ingredient counts
                count_map = {
                    row["recipe_id"]: row["ingredient_count"]
                    for row in ingredient_counts
                }

                # Add ingredient_count to each recipe
                for recipe in recipes_result:
                    recipe["ingredient_count"] = count_map.get(recipe["id"], 0)

            return recipes_result

        except Exception as e:
            logger.error(f"Error searching recipes: {str(e)}")
            raise

    # --- Tag Management ---

    @retry_on_db_locked()
    def create_public_tag(self, name: str) -> Dict[str, Any]:
        """Creates a new public tag. Returns the created tag."""
        try:
            self.execute_query(
                "INSERT INTO public_tags (name) VALUES (:name)", {"name": name}
            )
            # SQLite specific way to get last inserted ID if not returned directly
            # For this structure, we'll re-fetch. A more robust way would depend on DB specifics or ORM.
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name FROM public_tags WHERE name = :name",
                    {"name": name},
                ),
            )
            if not tag:  # Should not happen if insert succeeded
                raise sqlite3.DatabaseError("Failed to retrieve tag after creation.")
            return tag[0]
        except sqlite3.IntegrityError:
            logger.warning(f"Public tag '{name}' already exists.")
            # If it already exists, fetch and return it
            existing_tag = self.get_public_tag_by_name(name)
            if existing_tag:
                return existing_tag
            raise  # Should not happen if integrity error was due to name conflict
        except Exception as e:
            logger.error(f"Error creating public tag '{name}': {str(e)}")
            raise

    @retry_on_db_locked()
    def get_public_tag_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Gets a public tag by its name."""
        try:
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name FROM public_tags WHERE name = :name",
                    {"name": name},
                ),
            )
            return tag[0] if tag else None
        except Exception as e:
            logger.error(f"Error getting public tag by name '{name}': {str(e)}")
            raise

    @retry_on_db_locked()
    def create_private_tag(
        self, name: str, cognito_user_id: str, cognito_username: str
    ) -> Dict[str, Any]:
        """Creates a new private tag for a user. Returns the created tag."""
        try:
            self.execute_query(
                """
                INSERT INTO private_tags (name, cognito_user_id, cognito_username)
                VALUES (:name, :cognito_user_id, :cognito_username)
                """,
                {
                    "name": name,
                    "cognito_user_id": cognito_user_id,
                    "cognito_username": cognito_username,
                },
            )
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, name, cognito_user_id, cognito_username FROM private_tags 
                    WHERE name = :name AND cognito_user_id = :cognito_user_id
                    """,
                    {"name": name, "cognito_user_id": cognito_user_id},
                ),
            )
            if not tag:  # Should not happen
                raise sqlite3.DatabaseError(
                    "Failed to retrieve private tag after creation."
                )
            return tag[0]
        except sqlite3.IntegrityError:
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

    @retry_on_db_locked()
    def get_private_tag_by_name_and_user(
        self, name: str, cognito_user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Gets a private tag by its name and user ID."""
        try:
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """
                    SELECT id, name, cognito_user_id, cognito_username FROM private_tags 
                    WHERE name = :name AND cognito_user_id = :cognito_user_id
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
        """Get all public tags."""
        try:
            return cast(
                List[Dict[str, Any]],
                self.execute_query("SELECT id, name FROM public_tags ORDER BY name"),
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
                    SELECT id, name, cognito_user_id, cognito_username FROM private_tags 
                    WHERE cognito_user_id = :cognito_user_id ORDER BY name
                    """,
                    {"cognito_user_id": cognito_user_id},
                ),
            )
        except Exception as e:
            logger.error(
                f"Error getting private tags for user '{cognito_user_id}': {str(e)}"
            )
            raise

    @retry_on_db_locked()
    def add_public_tag_to_recipe(self, recipe_id: int, tag_id: int) -> bool:
        """Associates a public tag with a recipe."""
        try:
            result = self.execute_query(
                """
                INSERT INTO recipe_public_tags (recipe_id, tag_id) 
                VALUES (:recipe_id, :tag_id)
                ON CONFLICT(recipe_id, tag_id) DO NOTHING
                """,
                {"recipe_id": recipe_id, "tag_id": tag_id},
            )
            return result.get("rowCount", 0) > 0
        except Exception as e:
            logger.error(
                f"Error adding public tag {tag_id} to recipe {recipe_id}: {str(e)}"
            )
            raise

    @retry_on_db_locked()
    def add_private_tag_to_recipe(self, recipe_id: int, tag_id: int) -> bool:
        """Associates a private tag with a recipe."""
        try:
            # We assume tag_id corresponds to a private tag owned by the relevant user.
            # The check for tag ownership should happen in the handler before calling this.
            result = self.execute_query(
                """
                INSERT INTO recipe_private_tags (recipe_id, tag_id)
                VALUES (:recipe_id, :tag_id)
                ON CONFLICT(recipe_id, tag_id) DO NOTHING
                """,
                {"recipe_id": recipe_id, "tag_id": tag_id},
            )
            return result.get("rowCount", 0) > 0
        except Exception as e:
            logger.error(
                f"Error adding private tag {tag_id} to recipe {recipe_id}: {str(e)}"
            )
            raise

    @retry_on_db_locked()
    def remove_public_tag_from_recipe(self, recipe_id: int, tag_id: int) -> bool:
        """Removes the association of a public tag from a recipe."""
        try:
            result = self.execute_query(
                "DELETE FROM recipe_public_tags WHERE recipe_id = :recipe_id AND tag_id = :tag_id",
                {"recipe_id": recipe_id, "tag_id": tag_id},
            )
            return result.get("rowCount", 0) > 0
        except Exception as e:
            logger.error(
                f"Error removing public tag {tag_id} from recipe {recipe_id}: {str(e)}"
            )
            raise

    @retry_on_db_locked()
    def remove_private_tag_from_recipe(
        self, recipe_id: int, tag_id: int, cognito_user_id: str
    ) -> bool:
        """Removes the association of a private tag from a recipe, ensuring user ownership."""
        try:
            # Ensure the user owns the private tag they are trying to remove from the recipe
            result = self.execute_query(
                """
                DELETE FROM recipe_private_tags
                WHERE recipe_id = :recipe_id AND tag_id = :tag_id
                  AND EXISTS (SELECT 1 FROM private_tags pt WHERE pt.id = :tag_id AND pt.cognito_user_id = :cognito_user_id)
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
                    SELECT pt.id, pt.name
                    FROM recipe_public_tags rpt
                    JOIN public_tags pt ON rpt.tag_id = pt.id
                    WHERE rpt.recipe_id = :recipe_id
                    ORDER BY pt.name
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
                    SELECT pt.id, pt.name
                    FROM recipe_private_tags rpt
                    JOIN private_tags pt ON rpt.tag_id = pt.id
                    WHERE rpt.recipe_id = :recipe_id AND pt.cognito_user_id = :cognito_user_id
                    ORDER BY pt.name
                    """,
                    {"recipe_id": recipe_id, "cognito_user_id": cognito_user_id},
                ),
            )
        except Exception as e:
            logger.error(
                f"Error getting private tags for recipe {recipe_id} by user {cognito_user_id}: {str(e)}"
            )
            raise

    # --- End Tag Management ---
