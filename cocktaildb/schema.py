from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# Define Base and cache metadata to avoid reflection overhead
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
