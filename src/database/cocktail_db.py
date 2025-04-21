from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Table,
    ForeignKey,
    Enum,
    Boolean,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import enum

Base = declarative_base()


class UnitType(enum.Enum):
    VOLUME = "volume"
    WEIGHT = "weight"
    COUNT = "count"
    OTHER = "other"


class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    name = Column(String(20), nullable=False, unique=True)
    abbreviation = Column(String(10), unique=True)
    type = Column(Enum(UnitType), nullable=False)
    conversion_factor = Column(Float)  # For converting to base unit
    description = Column(String(100))


# Association table for many-to-many relationship between cocktails and ingredients
cocktail_ingredients = Table(
    "cocktail_ingredients",
    Base.metadata,
    Column("cocktail_id", Integer, ForeignKey("cocktails.id"), primary_key=True),
    Column("ingredient_id", Integer, ForeignKey("ingredients.id"), primary_key=True),
    Column("amount", Float, nullable=False),
    Column("unit_id", Integer, ForeignKey("units.id"), nullable=False),
)


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(500))
    category = Column(String(50))  # e.g., spirit, mixer, garnish

    # Brand-specific fields
    is_brand = Column(Boolean, default=False)
    brand_producer = Column(String(100))

    # Self-referential relationship for ingredient hierarchy
    parent_id = Column(Integer, ForeignKey("ingredients.id"))
    children = relationship(
        "Ingredient", backref=relationship.backref("parent", remote_side=[id])
    )

    # Relationship with cocktails
    cocktails = relationship(
        "Cocktail", secondary="cocktail_ingredients", back_populates="ingredients"
    )


class Cocktail(Base):
    __tablename__ = "cocktails"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500))
    instructions = Column(String(1000))
    image_url = Column(String(255))
    # category = Column(String(50))  # e.g., classic, modern, tiki

    # Relationship with ingredients
    ingredients = relationship(
        "Ingredient", secondary=cocktail_ingredients, back_populates="cocktails"
    )


class Database:
    def __init__(self):
        self.engine = create_engine(os.getenv("DATABASE_URL"))
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def get_cocktail(self, cocktail_id: int) -> Cocktail:
        return self.session.query(Cocktail).filter_by(id=cocktail_id).first()

    def create_cocktail(self, cocktail_data: dict) -> Cocktail:
        # Handle ingredients separately
        ingredients_data = cocktail_data.pop("ingredients", [])
        cocktail = Cocktail(**cocktail_data)

        # Add ingredients with their amounts and units
        for ingredient_data in ingredients_data:
            ingredient = (
                self.session.query(Ingredient)
                .filter_by(name=ingredient_data["name"])
                .first()
            )

            if not ingredient:
                ingredient = Ingredient(
                    name=ingredient_data["name"],
                    category=ingredient_data.get("category"),
                )
                self.session.add(ingredient)

            # Get or create the unit
            unit = (
                self.session.query(Unit).filter_by(name=ingredient_data["unit"]).first()
            )

            if not unit:
                raise ValueError(f"Unit '{ingredient_data['unit']}' not found")

            # Add the ingredient to the cocktail with amount and unit
            cocktail.ingredients.append(ingredient)
            # Set the amount and unit in the association table
            cocktail_ingredients.insert().values(
                cocktail_id=cocktail.id,
                ingredient_id=ingredient.id,
                amount=ingredient_data.get("amount"),
                unit_id=unit.id,
            )

        self.session.add(cocktail)
        self.session.commit()
        return cocktail

    def update_cocktail(self, cocktail_id: int, cocktail_data: dict) -> Cocktail:
        cocktail = self.get_cocktail(cocktail_id)
        if cocktail:
            # Handle ingredients separately
            ingredients_data = cocktail_data.pop("ingredients", None)

            # Update basic cocktail properties
            for key, value in cocktail_data.items():
                setattr(cocktail, key, value)

            # Update ingredients if provided
            if ingredients_data is not None:
                # Clear existing ingredients
                cocktail.ingredients = []

                # Add new ingredients
                for ingredient_data in ingredients_data:
                    ingredient = (
                        self.session.query(Ingredient)
                        .filter_by(name=ingredient_data["name"])
                        .first()
                    )

                    if not ingredient:
                        ingredient = Ingredient(
                            name=ingredient_data["name"],
                            category=ingredient_data.get("category"),
                        )
                        self.session.add(ingredient)

                    # Get or create the unit
                    unit = (
                        self.session.query(Unit)
                        .filter_by(name=ingredient_data["unit"])
                        .first()
                    )

                    if not unit:
                        raise ValueError(f"Unit '{ingredient_data['unit']}' not found")

                    cocktail.ingredients.append(ingredient)
                    # Update the amount and unit in the association table
                    cocktail_ingredients.update().where(
                        cocktail_ingredients.c.cocktail_id == cocktail.id,
                        cocktail_ingredients.c.ingredient_id == ingredient.id,
                    ).values(amount=ingredient_data.get("amount"), unit_id=unit.id)

            self.session.commit()
        return cocktail

    def delete_cocktail(self, cocktail_id: int) -> bool:
        cocktail = self.get_cocktail(cocktail_id)
        if cocktail:
            self.session.delete(cocktail)
            self.session.commit()
            return True
        return False

    def get_ingredient(self, ingredient_id: int) -> Ingredient:
        return self.session.query(Ingredient).filter_by(id=ingredient_id).first()

    def create_ingredient(self, ingredient_data: dict) -> Ingredient:
        ingredient = Ingredient(**ingredient_data)
        self.session.add(ingredient)
        self.session.commit()
        return ingredient

    def update_ingredient(
        self, ingredient_id: int, ingredient_data: dict
    ) -> Ingredient:
        ingredient = self.get_ingredient(ingredient_id)
        if ingredient:
            for key, value in ingredient_data.items():
                setattr(ingredient, key, value)
            self.session.commit()
        return ingredient

    def delete_ingredient(self, ingredient_id: int) -> bool:
        ingredient = self.get_ingredient(ingredient_id)
        if ingredient:
            self.session.delete(ingredient)
            self.session.commit()
            return True
        return False

    def get_unit(self, unit_id: int) -> Unit:
        return self.session.query(Unit).filter_by(id=unit_id).first()

    def create_unit(self, unit_data: dict) -> Unit:
        unit = Unit(**unit_data)
        self.session.add(unit)
        self.session.commit()
        return unit

    def update_unit(self, unit_id: int, unit_data: dict) -> Unit:
        unit = self.get_unit(unit_id)
        if unit:
            for key, value in unit_data.items():
                setattr(unit, key, value)
            self.session.commit()
        return unit

    def delete_unit(self, unit_id: int) -> bool:
        unit = self.get_unit(unit_id)
        if unit:
            self.session.delete(unit)
            self.session.commit()
            return True
        return False

    def get_units_by_type(self, unit_type: UnitType) -> list[Unit]:
        return self.session.query(Unit).filter_by(type=unit_type).all()

    def convert_amount(self, amount: float, from_unit: Unit, to_unit: Unit) -> float:
        """Convert an amount from one unit to another"""
        if from_unit.type != to_unit.type:
            raise ValueError(
                f"Cannot convert between different unit types: {from_unit.type} and {to_unit.type}"
            )

        # Convert to base unit first, then to target unit
        base_amount = amount * from_unit.conversion_factor
        return base_amount / to_unit.conversion_factor

    def create_ingredient_with_parent(
        self, ingredient_data: dict, parent_name: str = None
    ) -> Ingredient:
        """
        Create an ingredient with an optional parent.

        Example:
        - create_ingredient_with_parent({'name': 'Bourbon', 'category': 'spirit'}, parent_name='Whiskey')
        - create_ingredient_with_parent({
            'name': 'Blanton\'s',
            'is_brand': True,
            'brand_producer': 'Buffalo Trace',
            'category': 'spirit'
          }, parent_name='Bourbon')
        """
        # Create the ingredient
        ingredient = Ingredient(**ingredient_data)

        # Link to parent if specified
        if parent_name:
            parent = self.session.query(Ingredient).filter_by(name=parent_name).first()
            if not parent:
                raise ValueError(f"Parent ingredient '{parent_name}' not found")
            ingredient.parent = parent

        self.session.add(ingredient)
        self.session.commit()
        return ingredient

    def get_ingredient_by_name(self, name: str) -> Ingredient:
        """Get an ingredient by name"""
        return self.session.query(Ingredient).filter_by(name=name).first()

    def get_ingredient_hierarchy(self, ingredient_id: int) -> list[Ingredient]:
        """Get the full hierarchy for an ingredient (including parents)"""
        ingredient = self.get_ingredient(ingredient_id)
        if not ingredient:
            return []

        # Start with the ingredient itself
        hierarchy = [ingredient]
        current = ingredient

        # Move up the tree
        while current.parent:
            hierarchy.append(current.parent)
            current = current.parent

        # Return in order from most generic to most specific
        return list(reversed(hierarchy))

    def get_subtypes(self, ingredient_id: int) -> list[Ingredient]:
        """Get all ingredient subtypes (children)"""
        ingredient = self.get_ingredient(ingredient_id)
        if not ingredient:
            return []

        # Recursive function to collect all descendants
        def collect_children(ing):
            result = []
            for child in ing.children:
                result.append(child)
                result.extend(collect_children(child))
            return result

        return collect_children(ingredient)

    def get_compatible_ingredients(self, ingredient_id: int) -> list[Ingredient]:
        """Get all ingredients compatible with this one (including self, parent types, and subtypes)"""
        ingredient = self.get_ingredient(ingredient_id)
        if not ingredient:
            return []

        # Get all parent types
        hierarchy = self.get_ingredient_hierarchy(ingredient_id)

        # Get all subtypes
        subtypes = self.get_subtypes(ingredient_id)

        # Combine them all (including the original ingredient which is in the hierarchy)
        return hierarchy + subtypes
