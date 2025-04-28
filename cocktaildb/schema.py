from sqlalchemy import MetaData, Column, Integer, String, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.automap import automap_base

# Define Base with metadata reflection
metadata = MetaData()
Base = automap_base(metadata=metadata)

# These classes will be mapped to the existing database tables
# They don't create the tables, they just provide a Python interface


class Ingredient(Base):
    __tablename__ = "ingredients"

    # Explicitly define all columns
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    category = Column(String(50))
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey("ingredients.id"))
    path = Column(String(255))

    # Define relationships
    children = relationship(
        "Ingredient",
        backref="parent",
        foreign_keys="Ingredient.parent_id",
        remote_side="Ingredient.id",
    )

    # Helper methods for hierarchy operations
    def get_descendants(self, session):
        """Get all descendants of this ingredient using DB function"""
        from sqlalchemy import text

        result = session.execute(
            text("SELECT * FROM get_descendants(:id)"), {"id": self.id}
        )
        return result.fetchall()

    def get_ancestors(self, session):
        """Get all ancestors of this ingredient using DB function"""
        from sqlalchemy import text

        result = session.execute(
            text("SELECT * FROM get_ancestors(:id)"), {"id": self.id}
        )
        return result.fetchall()

    @classmethod
    def add_ingredient(
        cls, session, name, category=None, description=None, parent_id=None
    ):
        """Add a new ingredient with proper path generation using DB function"""
        from sqlalchemy import text

        result = session.execute(
            text("SELECT add_ingredient(:name, :category, :description, :parent_id)"),
            {
                "name": name,
                "category": category,
                "description": description,
                "parent_id": parent_id,
            },
        )
        new_id = result.scalar()
        session.flush()
        return session.query(cls).get(new_id)


class Unit(Base):
    __tablename__ = "units"

    # Explicitly define all columns
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    abbreviation = Column(String(10))


class Recipe(Base):
    __tablename__ = "recipes"

    # Explicitly define all columns
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    instructions = Column(Text)
    description = Column(Text)
    image_url = Column(String(255))

    # Define relationships
    recipe_ingredients = relationship("RecipeIngredient", back_populates="recipe")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    # Explicitly define all columns
    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"))
    amount = Column(Float)

    # Define relationships
    recipe = relationship("Recipe", back_populates="recipe_ingredients")
    ingredient = relationship("Ingredient")
    unit = relationship("Unit")


# Function to initialize the models by connecting to the database
def initialize_models(engine):
    """
    Initialize the models by reflecting the tables from the database.
    This must be called before using any of the models.

    Args:
        engine: SQLAlchemy engine connected to the database
    """
    metadata.reflect(engine)
    Base.prepare()
    return Base
