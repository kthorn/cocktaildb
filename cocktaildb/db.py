import json
import logging
import os

import boto3
from schema import Base, Ingredient, Recipe, RecipeIngredient, Unit, initialize_models
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.WARNING)


# Global metadata cache to prevent repeated reflection
_METADATA_INITIALIZED = False


class Database:
    def __init__(self):
        """Initialize the database connection"""
        global _METADATA_INITIALIZED
        logger.info("Initializing Database class")
        self.Ingredient = Ingredient
        self.Unit = Unit
        self.Recipe = Recipe
        self.RecipeIngredient = RecipeIngredient

        try:
            self.engine = self._get_db_engine()

            # Use scoped_session for thread safety
            self.session_factory = sessionmaker(bind=self.engine)
            self.Session = scoped_session(self.session_factory)
            self.session = self.Session()

            # Initialize models and create tables if they don't exist
            if not _METADATA_INITIALIZED:
                logger.info("Initializing metadata and creating tables if needed")
                initialize_models(self.engine)
                Base.metadata.create_all(self.engine)
                _METADATA_INITIALIZED = True
                logger.info("Metadata initialization complete")
            else:
                logger.info("Using cached metadata, skipping table creation check")

            logger.info("Database initialization complete")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}", exc_info=True)
            raise

    def _get_db_engine(self):
        """Get the database engine using Secrets Manager and RDS Data API"""
        logger.info("Getting database engine")

        try:
            client = boto3.client("secretsmanager")
            secret_arn = os.environ.get("DB_SECRET_ARN")
            db_name = os.environ.get("DB_NAME")
            db_cluster_arn = os.environ.get("DB_CLUSTER_ARN")

            # Validate required environment variables
            if not secret_arn or not db_name or not db_cluster_arn:
                raise ValueError(
                    "Missing required environment variables: DB_SECRET_ARN, DB_NAME, or DB_CLUSTER_ARN"
                )

            # Get database credentials from Secrets Manager
            secret_response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(secret_response["SecretString"])
            username = secret["username"]
            password = secret["password"]

            # Get the database endpoint from the cluster ARN
            cluster_parts = db_cluster_arn.split(":")
            region = cluster_parts[3]
            account_id = cluster_parts[4]
            cluster_name = cluster_parts[-1]

            # RDS client to get the endpoint
            try:
                rds_client = boto3.client("rds", region_name=region)
                logger.info("Created RDS client")
                response = rds_client.describe_db_clusters(
                    DBClusterIdentifier=cluster_name
                )
                logger.info("Successfully retrieved cluster information")
                endpoint = response["DBClusters"][0]["Endpoint"]
                port = response["DBClusters"][0]["Port"]
                logger.info(f"Database endpoint: {endpoint}")
                logger.info(f"Database port: {port}")
            except Exception as e:
                logger.error(
                    f"Error getting cluster information: {str(e)}", exc_info=True
                )
                raise

            # Enhanced connection parameters for better performance
            connect_args = {
                "timeout": 30,  # Increase timeout from 10 to 30 seconds
                "application_name": "CocktailDB-API",
                "tcp_keepalive": True,
                # Using only parameters supported by pg8000
                # "connect_timeout": 15,  # Not supported by pg8000
                "ssl_context": True,  # Enable SSL connection
            }

            # Create a connection string with explicit parameters
            connection_string = (
                f"postgresql+pg8000://{username}:{password}@{endpoint}:{port}/{db_name}"
            )
            logger.info(
                f"Attempting to connect with connection string: postgresql+pg8000://{username}:****@{endpoint}:{port}/{db_name}"
            )

            # Create a connection to the RDS database
            # Using QueuePool for connection pooling in Lambda
            logger.info("Creating database engine with connection pooling")
            engine = create_engine(
                connection_string,
                poolclass=QueuePool,  # Use connection pooling
                pool_size=3,  # Reduce pool size for Lambda
                max_overflow=5,  # Reduce max overflow for Lambda
                pool_timeout=30,  # Connection request timeout
                pool_recycle=300,  # Recycle connections after 5 minutes (more frequent in Lambda)
                pool_pre_ping=True,  # Verify connections before use
                connect_args=connect_args,
                echo=(
                    os.environ.get("SQL_DEBUG", "false").lower() == "true"
                ),  # Only enable SQL echo in debug mode
            )
            logger.info("Database engine created successfully")

            # Test the connection - with retry logic
            logger.info("Testing database connection...")
            retry_count = 0
            max_retries = 3
            last_error = None

            while retry_count < max_retries:
                try:
                    with engine.connect() as conn:
                        conn.execute(text("SELECT 1"))
                        logger.info(
                            "Successfully connected to database and executed test query"
                        )
                        return engine
                except Exception as e:
                    last_error = e
                    retry_count += 1
                    logger.warning(
                        f"Connection attempt {retry_count} failed: {str(e)}. "
                        f"{'Retrying...' if retry_count < max_retries else 'Max retries reached.'}"
                    )
                    if retry_count < max_retries:
                        # Add exponential backoff before retrying
                        import time

                        time.sleep(2**retry_count)  # 2, 4, 8 seconds

            # If we've exhausted retries, log the error and raise
            logger.error(
                f"Failed to connect to database after {max_retries} attempts: {str(last_error)}",
                exc_info=True,
            )
            raise last_error or Exception(
                "Failed to connect to database after multiple attempts"
            )

        except Exception as e:
            logger.error(f"Error getting database engine: {str(e)}", exc_info=True)

            # If the environment variable is set, use a SQLite fallback for local development/testing
            if os.environ.get("USE_SQLITE_FALLBACK", "false").lower() == "true":
                logger.warning("Using SQLite fallback database")
                sqlite_path = os.environ.get("SQLITE_PATH", "cocktaildb.db")
                engine = create_engine(f"sqlite:///{sqlite_path}")
                Base.metadata.create_all(engine)
                return engine

            raise

    def __del__(self):
        """Clean up resources when the object is deleted"""
        if hasattr(self, "session") and self.session:
            self.session.close()

    def close(self):
        """Explicitly close the session"""
        if hasattr(self, "session") and self.session:
            self.session.close()

    def create_ingredient(self, data):
        """Create a new ingredient"""
        try:
            ingredient = Ingredient(
                name=data.get("name"),
                category=data.get("category"),
                description=data.get("description"),
            )
            self.session.add(ingredient)
            self.session.commit()
            return ingredient
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error creating ingredient: {str(e)}")
            raise

    def update_ingredient(self, ingredient_id, data):
        """Update an existing ingredient"""
        try:
            ingredient = (
                self.session.query(Ingredient)
                .filter(Ingredient.id == ingredient_id)
                .first()
            )
            if ingredient:
                ingredient.name = data.get("name", ingredient.name)
                ingredient.category = data.get("category", ingredient.category)
                ingredient.description = data.get("description", ingredient.description)
                self.session.commit()
            return ingredient
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error updating ingredient {ingredient_id}: {str(e)}")
            raise

    def delete_ingredient(self, ingredient_id):
        """Delete an ingredient"""
        try:
            ingredient = (
                self.session.query(Ingredient)
                .filter(Ingredient.id == ingredient_id)
                .first()
            )
            if ingredient:
                self.session.delete(ingredient)
                self.session.commit()
                return True
            return False
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error deleting ingredient {ingredient_id}: {str(e)}")
            raise

    def create_recipe(self, data):
        """Create a new recipe with its ingredients"""
        try:
            # Create the recipe
            recipe = Recipe(
                name=data.get("name"),
                instructions=data.get("instructions"),
                description=data.get("description"),
                image_url=data.get("image_url"),
            )
            self.session.add(recipe)
            self.session.flush()  # Flush to get the recipe ID

            # Add recipe ingredients if provided
            if "ingredients" in data:
                for ingredient_data in data["ingredients"]:
                    recipe_ingredient = RecipeIngredient(
                        recipe_id=recipe.id,
                        ingredient_id=ingredient_data["ingredient_id"],
                        unit_id=ingredient_data.get("unit_id"),
                        amount=ingredient_data.get("amount"),
                    )
                    self.session.add(recipe_ingredient)

            self.session.commit()
            return recipe
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error creating recipe: {str(e)}")
            raise

    def update_recipe(self, recipe_id, data):
        """Update an existing recipe and its ingredients"""
        try:
            recipe = self.session.query(Recipe).filter(Recipe.id == recipe_id).first()
            if recipe:
                # Update basic recipe information
                recipe.name = data.get("name", recipe.name)
                recipe.instructions = data.get("instructions", recipe.instructions)
                recipe.description = data.get("description", recipe.description)
                recipe.image_url = data.get("image_url", recipe.image_url)

                # Update ingredients if provided
                if "ingredients" in data:
                    # Remove existing ingredients
                    self.session.query(RecipeIngredient).filter(
                        RecipeIngredient.recipe_id == recipe_id
                    ).delete()

                    # Add new ingredients
                    for ingredient_data in data["ingredients"]:
                        recipe_ingredient = RecipeIngredient(
                            recipe_id=recipe.id,
                            ingredient_id=ingredient_data["ingredient_id"],
                            unit_id=ingredient_data.get("unit_id"),
                            amount=ingredient_data.get("amount"),
                        )
                        self.session.add(recipe_ingredient)

                self.session.commit()
            return recipe
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error updating recipe {recipe_id}: {str(e)}")
            raise

    def delete_recipe(self, recipe_id):
        """Delete a recipe and its associated ingredients"""
        try:
            recipe = self.session.query(Recipe).filter(Recipe.id == recipe_id).first()
            if recipe:
                # Delete associated recipe ingredients first
                self.session.query(RecipeIngredient).filter(
                    RecipeIngredient.recipe_id == recipe_id
                ).delete()

                # Delete the recipe
                self.session.delete(recipe)
                self.session.commit()
                return True
            return False
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error deleting recipe {recipe_id}: {str(e)}")
            raise

    def get_units(self):
        """Get all measurement units"""
        try:
            units = self.session.query(Unit).all()
            return units
        except Exception as e:
            logger.error(f"Error getting units: {str(e)}")
            raise
