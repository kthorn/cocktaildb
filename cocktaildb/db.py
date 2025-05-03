import logging
import sqlite3
import time
import functools
from typing import Dict, List, Optional, Any, Union, Tuple, cast

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.WARNING)

db_path = "/mnt/efs/cocktaildb.db"


# Global metadata cache to prevent repeated reflection
_METADATA_INITIALIZED = False


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
            self.db_path = db_path

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

    @retry_on_db_locked()
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

                old_parent_id = old_ingredient[0]["parent_id"]
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

    @retry_on_db_locked()
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

    def get_ingredient_ancestors_by_path(self, path: str) -> List[Dict[str, Any]]:
        """Get all ancestors of an ingredient using its path

        Args:
            path: The path of the ingredient

        Returns:
            List of ancestor ingredients ordered from root to leaf
        """
        try:
            # Parse the path to get ancestor IDs
            ancestor_ids = []
            parts = path.strip("/").split("/")

            # Extract all IDs except the last one (which is the ingredient itself)
            for part in parts[:-1]:  # Skip the last part which is the ingredient itself
                if part and part.isdigit():
                    ancestor_ids.append(int(part))
            if not ancestor_ids:
                return []

            # Get all ancestors
            placeholders = ", ".join("?" for _ in ancestor_ids)
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    f"""
                SELECT id, name, description, parent_id, path,
                       (LENGTH(path) - LENGTH(REPLACE(path, '/', '')) - 1) as level
                FROM ingredients 
                WHERE id IN ({placeholders})
                ORDER BY path
                """,
                    tuple(ancestor_ids),
                ),
            )
            return result
        except Exception as e:
            logger.error(
                f"Error getting ancestors for ingredient with path {path}: {str(e)}"
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
                    "name": data["name"],
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

    def get_recipes(self) -> List[Dict[str, Any]]:
        """Get all recipes with their ingredients"""
        try:
            recipes_result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, instructions, description, image_url, source, source_url, avg_rating, rating_count FROM recipes"
                ),
            )

            for recipe in recipes_result:
                recipe["ingredients"] = self._get_recipe_ingredients(recipe["id"])

            return recipes_result
        except Exception as e:
            logger.error(f"Error getting recipes: {str(e)}")
            raise

    def get_recipe(self, recipe_id: int) -> Optional[Dict[str, Any]]:
        """Get a single recipe by ID with its ingredients"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, instructions, description, image_url, source, source_url, avg_rating, rating_count FROM recipes WHERE id = :id",
                    {"id": recipe_id},
                ),
            )
            if result:
                recipe = result[0]
                recipe["ingredients"] = self._get_recipe_ingredients(recipe_id)
                return recipe
            return None
        except Exception as e:
            logger.error(f"Error getting recipe {recipe_id}: {str(e)}")
            raise

    def _get_recipe_ingredients(self, recipe_id: int) -> List[Dict[str, Any]]:
        """Helper method to get ingredients for a recipe"""
        result = cast(
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
        # Add full_name for each ingredient
        for ingredient in result:
            ingredient_path = ingredient["ingredient_path"]
            # Get ancestors using the path directly
            ancestors = self.get_ingredient_ancestors_by_path(ingredient_path)
            # Generate full name
            if ancestors:
                ancestor_names = [ancestor["name"] for ancestor in reversed(ancestors)]
                ingredient["full_name"] = (
                    f"{ingredient['ingredient_name']} [{';'.join(ancestor_names)}]"
                )
            else:
                ingredient["full_name"] = ingredient["ingredient_name"]

        return result

    def get_units(self) -> List[Dict[str, Any]]:
        """Get all measurement units"""
        try:
            result = cast(
                List[Dict[str, Any]],
                self.execute_query(
                    "SELECT id, name, abbreviation FROM units ORDER BY name"
                ),
            )
            return result
        except Exception as e:
            logger.error(f"Error getting units: {str(e)}")
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
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating, comment, 
                           datetime(created_at, 'localtime') as created_at
                    FROM ratings 
                    WHERE recipe_id = :recipe_id
                    ORDER BY created_at DESC
                    """,
                    {"recipe_id": recipe_id},
                ),
            )
            return result
        except Exception as e:
            logger.error(f"Error getting ratings for recipe {recipe_id}: {str(e)}")
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
                    SET rating = :rating,
                        comment = COALESCE(:comment, comment)
                    WHERE cognito_user_id = :user_id AND recipe_id = :recipe_id
                    """,
                    {
                        "user_id": data["cognito_user_id"],
                        "recipe_id": data["recipe_id"],
                        "rating": data["rating"],
                        "comment": data.get("comment"),
                    },
                )
            else:
                # Insert new rating
                cursor.execute(
                    """
                    INSERT INTO ratings (cognito_user_id, cognito_username, recipe_id, rating, comment)
                    VALUES (:cognito_user_id, :cognito_username, :recipe_id, :rating, :comment)
                    """,
                    {
                        "cognito_user_id": data["cognito_user_id"],
                        "cognito_username": data["cognito_username"],
                        "recipe_id": data["recipe_id"],
                        "rating": data["rating"],
                        "comment": data.get("comment", ""),
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
                    SELECT id, cognito_user_id, cognito_username, recipe_id, rating, comment,
                           datetime(created_at, 'localtime') as created_at
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
