from sqlalchemy import MetaData
from sqlalchemy.orm import relationship
from sqlalchemy.ext.automap import automap_base

# Define Base with metadata reflection
metadata = MetaData()
Base = automap_base(metadata=metadata)

# These classes will be mapped to the existing database tables
# They don't create the tables, they just provide a Python interface


class Ingredient(Base):
    __tablename__ = "ingredients"

    # We only need to define relationships, not columns (they'll be reflected)
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
    # Columns will be reflected


class Recipe(Base):
    __tablename__ = "recipes"

    # Define relationships that will be available after reflection
    recipe_ingredients = relationship("RecipeIngredient", back_populates="recipe")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    # Define relationships that will be available after reflection
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
