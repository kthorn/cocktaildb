import json
import os
import boto3
import sqlalchemy
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session, sessionmaker

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
        self.Ingredient = Ingredient
        self.Unit = Unit
        self.Recipe = Recipe
        self.RecipeIngredient = RecipeIngredient

        self.engine = self._get_db_engine()
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)

    def _get_db_engine(self):
        """Get the database engine using Secrets Manager and RDS Data API"""
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
        cluster_name = cluster_parts[6].split("/")[1]

        # RDS client to get the endpoint
        rds_client = boto3.client("rds")
        response = rds_client.describe_db_clusters(DBClusterIdentifier=cluster_name)

        endpoint = response["DBClusters"][0]["Endpoint"]

        # Create a connection to the RDS database
        engine = create_engine(
            f"postgresql://{username}:{password}@{endpoint}:5432/{db_name}"
        )

        return engine

    def create_ingredient(self, data):
        """Create a new ingredient"""
        ingredient = Ingredient(
            name=data.get("name"),
            category=data.get("category"),
            description=data.get("description"),
        )
        self.session.add(ingredient)
        self.session.commit()
        return ingredient

    def update_ingredient(self, ingredient_id, data):
        """Update an existing ingredient"""
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

    def delete_ingredient(self, ingredient_id):
        """Delete an ingredient"""
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
