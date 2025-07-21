import logging
import sqlite3
import time
import functools
import os
import re
import unicodedata
from typing import Dict, List, Optional, Any, Union, Tuple, cast

from .db_utils import extract_all_ingredient_ids, assemble_ingredient_full_names
from .sql_queries import (
    get_recipe_by_id_sql,
    get_all_recipes_sql,
    get_recipe_ingredients_by_recipe_id_sql_factory,
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def remove_accents(text: str) -> str:
    """
    Remove accents from text for accent-insensitive search.
    Normalizes to NFD (decomposed form) and removes combining characters.
    """
    if not text:
        return text
    # Normalize to NFD (decomposed form) and remove combining characters
    return re.sub(r"[\u0300-\u036f]", "", unicodedata.normalize("NFD", text))


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

    def get_db_path(self) -> str:
        """Get the database file path"""
        return self.db_path

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
        # Enable foreign key constraints (must be done for each connection in SQLite)
        conn.execute("PRAGMA foreign_keys = ON")
        # Optimize for concurrent access by multiple lambdas
        conn.execute("PRAGMA busy_timeout = 10000")  # 10 seconds in milliseconds
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA locking_mode = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -10000")
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries

        # Register custom function for accent-insensitive search
        conn.create_function("remove_accents", 1, remove_accents)

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
                        "name": data.get("name"),
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

                # Get descendants BEFORE updating the parent path
                descendants = self.get_ingredient_descendants(ingredient_id)

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

    def get_ingredient_by_name(self, ingredient_name: str) -> Optional[Dict[str, Any]]:
        """Get a single ingredient by name (case-insensitive)"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path FROM ingredients WHERE LOWER(name) = LOWER(?)",
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
                    "SELECT id, name, description, parent_id, path FROM ingredients WHERE LOWER(name) = LOWER(?)",
                    (search_term,),
                ),
            )
            # Mark exact matches
            for ingredient in exact_result:
                ingredient["exact_match"] = True
            if exact_result:
                return exact_result
            # Otherwise, fall back to partial match
            partial_result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, description, parent_id, path FROM ingredients WHERE LOWER(name) LIKE LOWER(?) ORDER BY name",
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
            placeholders = ",".join("?" for _ in unique_names)

            exact_results = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    f"SELECT id, name, description, parent_id, path FROM ingredients WHERE LOWER(name) IN ({placeholders})",
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
            placeholders = ",".join("?" for _ in unique_names)

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
                    "name": data["name"] if data["name"] else None,
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

    def get_recipes_with_ingredients(
        self, cognito_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all recipes with their full ingredient details (for detailed views)"""
        try:
            start_time = time.time()
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
                placeholders = ",".join("?" for _ in all_needed_ingredient_ids)
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

    def get_unit_by_name(self, unit_name: str) -> Optional[Dict[str, Any]]:
        """Get a unit by exact name match (case-insensitive)"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, abbreviation, conversion_to_ml FROM units WHERE LOWER(name) = LOWER(?)",
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
                    "SELECT id, name, abbreviation, conversion_to_ml FROM units WHERE LOWER(abbreviation) = LOWER(?)",
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
            placeholders = ",".join("?" for _ in unique_names)

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
            placeholders = ",".join("?" for _ in unique_names)

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
            cursor.execute("DELETE FROM recipes WHERE id = :id", {"id": recipe_id})

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
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating
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
            # Add name search condition if provided (accent-insensitive)
            if search_params.get("name"):
                query += (
                    " AND remove_accents(LOWER(name)) LIKE remove_accents(LOWER(:name))"
                )
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
                    FROM recipe_tags rt
                    JOIN tags t ON rt.tag_id = t.id
                    WHERE rt.recipe_id = recipes.id AND t.created_by IS NULL AND t.name IN ({})
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
        if not name:
            raise ValueError("Tag name cannot be empty")
        try:
            self.execute_query(
                "INSERT INTO tags (name, created_by) VALUES (:name, NULL)",
                {"name": name},
            )
            # SQLite specific way to get last inserted ID if not returned directly
            # For this structure, we'll re-fetch. A more robust way would depend on DB specifics or ORM.
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name FROM tags WHERE name = :name AND created_by IS NULL",
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
                    "SELECT id, name FROM tags WHERE name = :name AND created_by IS NULL",
                    {"name": name},
                ),
            )
            return tag[0] if tag else None
        except Exception as e:
            logger.error(f"Error getting public tag by name '{name}': {str(e)}")
            raise

    @retry_on_db_locked()
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
                VALUES (:name, :cognito_user_id)
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
                    WHERE name = :name AND created_by = :cognito_user_id
                    """,
                    {"name": name.strip(), "cognito_user_id": cognito_user_id.strip()},
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
                    SELECT id, name, created_by as cognito_user_id FROM tags 
                    WHERE name = :name AND created_by = :cognito_user_id
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
                self.execute_query(
                    "SELECT id, name FROM tags WHERE created_by IS NULL ORDER BY name"
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
                    WHERE created_by = :cognito_user_id ORDER BY name
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
                INSERT INTO recipe_tags (recipe_id, tag_id) 
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
                INSERT INTO recipe_tags (recipe_id, tag_id)
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
                "DELETE FROM recipe_tags WHERE recipe_id = :recipe_id AND tag_id = :tag_id",
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
                DELETE FROM recipe_tags
                WHERE recipe_id = :recipe_id AND tag_id = :tag_id
                  AND EXISTS (SELECT 1 FROM tags t WHERE t.id = :tag_id AND t.created_by = :cognito_user_id)
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
                    WHERE rt.recipe_id = :recipe_id AND t.created_by IS NULL
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
                    WHERE rt.recipe_id = :recipe_id AND t.created_by = :cognito_user_id
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

    @retry_on_db_locked()
    def get_tag(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """Gets a tag by its ID from the unified tags table."""
        try:
            tag = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    """SELECT id, name, 
                       CASE WHEN created_by IS NULL THEN 0 ELSE 1 END as is_private,
                       created_by as created_by
                       FROM tags WHERE id = :tag_id""",
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

    @retry_on_db_locked()
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

    @retry_on_db_locked()
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

    # --- End Tag Management ---

    # --- Pagination Methods ---
    @retry_on_db_locked()
    def search_recipes_paginated(
        self,
        search_params: Dict[str, Any],
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "name",
        sort_order: str = "asc",
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search recipes with pagination"""
        try:
            from .sql_queries import (
                build_search_recipes_paginated_sql,
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

            # Debug: Log the exact search query parameter being used in SQL
            if query_params.get("search_query"):
                logger.info(
                    f"SQL search_query parameter: '{query_params['search_query']}'"
                )
                logger.info(
                    f"SQL search_query_with_wildcards parameter: '{query_params['search_query_with_wildcards']}'"
                )
            else:
                logger.info("No search_query parameter provided to SQL")

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
                        condition = f"i2.path LIKE :{param_name}"

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
                                condition = f"(t3.name = :{tag_param} AND (t3.created_by IS NULL OR t3.created_by = :cognito_user_id))"
                            else:
                                condition = f"(t3.name = :{tag_param} AND t3.created_by IS NULL)"
                            tag_conditions.append(condition)
                        else:
                            # Tag doesn't exist, return no results
                            logger.info(
                                f"Tag not found: {tag_name}, returning empty results"
                            )
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
            paginated_sql = build_search_recipes_paginated_sql(
                must_ingredient_conditions,
                must_not_ingredient_conditions,
                tag_conditions,
                sort_by,
                sort_order,
                inventory_filter,
            )

            # Debug: Log the SQL execution details
            logger.info(f"Executing search with {len(query_params)} parameters")
            if query_params.get("search_query"):
                logger.info(
                    f"About to execute SQL search for: '{query_params['search_query']}'"
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
                        "amount": row.get("amount"),
                        "unit_id": row.get("unit_id"),
                        "unit_name": row.get("unit_name"),
                        "unit_abbreviation": row.get("unit_abbreviation"),
                    }
                    recipes[recipe_id]["ingredients"].append(ingredient)

            result = list(recipes.values())
            logger.info(f"Found {len(result)} recipes from search")
            return result

        except Exception as e:
            logger.error(f"Error searching recipes with pagination: {str(e)}")
            raise

    # --- End Pagination Methods ---

    # --- User Ingredient Tracking Methods ---

    @retry_on_db_locked()
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
                    "SELECT id FROM user_ingredients WHERE cognito_user_id = :user_id AND ingredient_id = :ingredient_id",
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
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

            # Add all parent ingredients first (if they don't already exist)
            for parent_id in parent_ingredient_ids:
                try:
                    # Use INSERT OR IGNORE to add parent ingredient only if it doesn't exist
                    cursor.execute(
                        "INSERT OR IGNORE INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
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
                "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
                (user_id, ingredient_id),
            )

            conn.commit()
            conn.close()
            conn = None

            # Return the created record with ingredient details
            return {
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient["name"],
                "added_at": "now",  # SQLite CURRENT_TIMESTAMP
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
                conn.close()

    @retry_on_db_locked()
    def remove_user_ingredient(self, user_id: str, ingredient_id: int) -> bool:
        """Remove an ingredient from a user's inventory, but prevent removing parents if children exist"""
        try:
            # Check if user has this ingredient
            existing = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id FROM user_ingredients WHERE cognito_user_id = :user_id AND ingredient_id = :ingredient_id",
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
                        WHERE ui.cognito_user_id = :user_id 
                        AND i.path LIKE :child_path_pattern
                        AND i.id != :ingredient_id
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
                "DELETE FROM user_ingredients WHERE cognito_user_id = :user_id AND ingredient_id = :ingredient_id",
                {"user_id": user_id, "ingredient_id": ingredient_id},
            )

            return result.get("rowCount", 0) > 0

        except Exception as e:
            logger.error(
                f"Error removing ingredient {ingredient_id} from user {user_id}: {str(e)}"
            )
            raise

    @retry_on_db_locked()
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
                    WHERE ui.cognito_user_id = :user_id
                    ORDER BY i.name
                    """,
                    {"user_id": user_id},
                ),
            )
            return result

        except Exception as e:
            logger.error(f"Error getting ingredients for user {user_id}: {str(e)}")
            raise

    @retry_on_db_locked()
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
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

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
                            "SELECT id FROM ingredients WHERE id = :ingredient_id",
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
                    existing = cursor.execute(
                        "SELECT id FROM user_ingredients WHERE cognito_user_id = ? AND ingredient_id = ?",
                        (user_id, ingredient_id),
                    ).fetchone()

                    if existing:
                        already_exists_count += 1
                        continue

                    # Add the ingredient
                    cursor.execute(
                        "INSERT INTO user_ingredients (cognito_user_id, ingredient_id) VALUES (?, ?)",
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
                conn.close()

    @retry_on_db_locked()
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
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()

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
                    existing = cursor.execute(
                        "SELECT id FROM user_ingredients WHERE cognito_user_id = ? AND ingredient_id = ?",
                        (user_id, ingredient_id),
                    ).fetchone()

                    if not existing:
                        logger.debug(
                            f"Ingredient {ingredient_id} not found in user {user_id} inventory"
                        )
                        not_found_count += 1
                        continue

                    # Get the ingredient details
                    ingredient = cursor.execute(
                        "SELECT id, name, path FROM ingredients WHERE id = ?",
                        (ingredient_id,),
                    ).fetchone()

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
                        child_ingredients = cursor.execute(
                            """
                            SELECT ui.ingredient_id, i.name, i.path
                            FROM user_ingredients ui
                            JOIN ingredients i ON ui.ingredient_id = i.id
                            WHERE ui.cognito_user_id = ? 
                            AND i.path LIKE ?
                            AND i.id != ?
                            """,
                            (user_id, f"{ingredient_path}%", ingredient_id),
                        ).fetchall()

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
            logger.info(f"Sorting ingredients by path depth for ordered deletion")
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
                    existing = cursor.execute(
                        "SELECT id FROM user_ingredients WHERE cognito_user_id = ? AND ingredient_id = ?",
                        (user_id, ingredient_id),
                    ).fetchone()

                    if not existing:
                        logger.debug(
                            f"Ingredient {ingredient_id} no longer in user {user_id} inventory, skipping"
                        )
                        continue

                    # Remove the ingredient
                    cursor.execute(
                        "DELETE FROM user_ingredients WHERE cognito_user_id = ? AND ingredient_id = ?",
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
                conn.close()

    # --- End User Ingredient Tracking Methods ---
