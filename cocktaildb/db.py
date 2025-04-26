import json
import os
import boto3
import logging
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    Float,
    create_engine,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.pool import NullPool

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.WARNING)

Base = declarative_base()


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    category = Column(String(50))
    description = Column(Text)


class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    abbreviation = Column(String(10))


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    instructions = Column(Text)
    description = Column(Text)
    image_url = Column(String(255))

    ingredients = relationship("RecipeIngredient", back_populates="recipe")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"))
    amount = Column(Float)

    recipe = relationship("Recipe", back_populates="ingredients")
    ingredient = relationship("Ingredient")
    unit = relationship("Unit")


class Database:
    def __init__(self):
        """Initialize the database connection"""
        logger.info("Initializing Database class")
        self.Ingredient = Ingredient
        self.Unit = Unit
        self.Recipe = Recipe
        self.RecipeIngredient = RecipeIngredient

        try:
            self.engine = self._get_db_engine()
            Session = sessionmaker(bind=self.engine)
            self.session = Session()

            # Create tables if they don't exist
            logger.info("Creating tables if they don't exist")
            Base.metadata.create_all(self.engine)
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

            # Connection parameters for better performance and debugging
            connect_args = {
                "timeout": 10,  # 10 seconds connection timeout
                "application_name": "CocktailDB-API",
            }

            # Create a connection string with explicit parameters
            connection_string = (
                f"postgresql+pg8000://{username}:{password}@{endpoint}:{port}/{db_name}"
            )
            logger.info(
                f"Attempting to connect with connection string: postgresql+pg8000://{username}:****@{endpoint}:{port}/{db_name}"
            )

            # Create a connection to the RDS database
            # Using NullPool to avoid connection pooling overhead in Lambda
            logger.info("Creating database engine")
            engine = create_engine(
                connection_string,
                poolclass=NullPool,
                connect_args=connect_args,
                echo=True,  # Enable SQL debugging
            )
            logger.info("Database engine created successfully")

            # Test the connection
            logger.info("Testing database connection...")
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT 1"))
                    logger.info(
                        "Successfully connected to database and executed test query"
                    )
            except Exception as e:
                logger.error(f"Failed to connect to database: {str(e)}", exc_info=True)
                raise

            return engine
        except Exception as e:
            logger.error(f"Error getting database engine: {str(e)}", exc_info=True)
            raise

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
