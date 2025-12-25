"""
Ingredient Management Testing
Comprehensive tests for hierarchical ingredient system including CRUD operations,
path management, and relationship validation
"""

import pytest


class TestIngredientCRUD:
    """Test basic CRUD operations for ingredients"""

    def test_create_ingredient_simple(self, db_instance):
        """Test creating a simple ingredient without parent"""
        db = db_instance

        data = {
                "name": "Test",
                "description": "Juniper-flavored spirit",
                "parent_id": None,
        }

        result = db.create_ingredient(data)

        assert result["id"] is not None
        assert result["name"] == "Test"
        assert result["description"] == "Juniper-flavored spirit"
        assert result["parent_id"] is None
        assert result["path"] == f"/{result['id']}/"

    def test_create_ingredient_with_parent(self, db_instance):
        """Test creating an ingredient with a parent"""
        db = db_instance

        # Create parent ingredient
        parent_data = {
                "name": "Spirits",
                "description": "Alcoholic spirits",
                "parent_id": None,
        }
        parent = db.create_ingredient(parent_data)

        # Create child ingredient
        child_data = {
                "name": "Test",
                "description": "Juniper-flavored spirit",
                "parent_id": parent["id"],
        }
        child = db.create_ingredient(child_data)

        assert child["parent_id"] == parent["id"]
        assert child["path"] == f"/{parent['id']}/{child['id']}/"

    def test_get_ingredient_by_id(self, db_instance):
        """Test retrieving ingredient by ID"""
        db = db_instance

        # Create ingredient
        data = {"name": "Test", "description": "Test gin", "parent_id": None}
        created = db.create_ingredient(data)

        # Retrieve by ID
        result = db.get_ingredient(created["id"])

        assert result is not None
        assert result["id"] == created["id"]
        assert result["name"] == "Test"

    def test_get_ingredient_nonexistent(self, db_instance):
        """Test retrieving non-existent ingredient"""
        db = db_instance

        result = db.get_ingredient(999)
        assert result is None

    def test_get_ingredient_by_name(self, db_instance):
        """Test retrieving ingredient by name (case-insensitive)"""
        db = db_instance

        # Create ingredient
        data = {
                "name": "London Dry Gin",
                "description": "Test gin",
                "parent_id": None,
        }
        created = db.create_ingredient(data)

        # Test case-insensitive retrieval
        result = db.get_ingredient_by_name("london dry gin")
        assert result is not None
        assert result["id"] == created["id"]

        result = db.get_ingredient_by_name("LONDON DRY GIN")
        assert result is not None
        assert result["id"] == created["id"]

    def test_get_ingredient_by_name_nonexistent(self, db_instance):
        """Test retrieving non-existent ingredient by name"""
        db = db_instance

        result = db.get_ingredient_by_name("Nonexistent Ingredient")
        assert result is None


class TestIngredientHierarchy:
    """Test hierarchical ingredient functionality"""

    def test_multi_level_hierarchy(self, db_instance):
        """Test creating multi-level ingredient hierarchy"""
        db = db_instance

        # Level 1: Spirits
        spirits = db.create_ingredient(
                {
                    "name": "Spirits",
                    "description": "Alcoholic spirits",
                    "parent_id": None,
                }
        )

        # Level 2: Gin
        gin = db.create_ingredient(
                {
                    "name": "Test",
                    "description": "Juniper-flavored spirit",
                    "parent_id": spirits["id"],
                }
        )

        # Level 3: London Dry Gin
        london_gin = db.create_ingredient(
                {
                    "name": "Specific Test",
                    "description": "A specific type of gin",
                    "parent_id": gin["id"],
                }
        )

        # Verify paths
        assert spirits["path"] == f"/{spirits['id']}/"
        assert gin["path"] == f"/{spirits['id']}/{gin['id']}/"
        assert (
                london_gin["path"]
                == f"/{spirits['id']}/{gin['id']}/{london_gin['id']}/"
        )

    def test_get_ingredient_descendants(self, db_instance):
        """Test retrieving all descendants of an ingredient"""
        db = db_instance

        # Create hierarchy
        spirits = db.create_ingredient(
                {"name": "Test_Base", "description": "Spirits", "parent_id": None}
        )
        gin = db.create_ingredient(
                {"name": "Test1", "description": "Gin", "parent_id": spirits["id"]}
        )
        vodka = db.create_ingredient(
                {"name": "Test2", "description": "Vodka", "parent_id": spirits["id"]}
        )
        london_gin = db.create_ingredient(
                {
                    "name": "London Dry Gin1",
                    "description": "London Gin",
                    "parent_id": gin["id"],
                }
        )

        # Get descendants of spirits
        descendants = db.get_ingredient_descendants(spirits["id"])

        assert len(descendants) == 3
        descendant_names = {d["name"] for d in descendants}
        assert descendant_names == {"Test1", "Test2", "London Dry Gin1"}

        # Verify level calculation
        gin_descendant = next(d for d in descendants if d["name"] == "Test1")
        london_gin_descendant = next(
                d for d in descendants if d["name"] == "London Dry Gin1"
        )

        assert gin_descendant["level"] == 2  # spirits -> gin
        assert london_gin_descendant["level"] == 3  # spirits -> gin -> london gin

    def test_get_ingredient_descendants_leaf_node(self, db_instance):
        """Test getting descendants of a leaf node"""
        db = db_instance

        # Create leaf ingredient
        gin = db.create_ingredient(
                {"name": "Test", "description": "Gin", "parent_id": None}
        )

        descendants = db.get_ingredient_descendants(gin["id"])
        assert len(descendants) == 0

    def test_get_ingredient_descendants_nonexistent(self, db_instance):
        """Test getting descendants of non-existent ingredient"""
        db = db_instance

        descendants = db.get_ingredient_descendants(999)
        assert len(descendants) == 0


class TestIngredientUpdate:
    """Test ingredient update operations"""

    def test_update_ingredient_basic_fields(self, db_instance):
        """Test updating basic ingredient fields"""
        db = db_instance

        # Create ingredient
        original = db.create_ingredient(
                {
                    "name": "Test",
                    "description": "Original description",
                    "parent_id": None,
                }
        )

        # Update ingredient
        update_data = {"name": "Premium Gin", "description": "Updated description"}

        updated = db.update_ingredient(original["id"], update_data)

        assert updated is not None
        assert updated["name"] == "Premium Gin"
        assert updated["description"] == "Updated description"
        assert updated["path"] == original["path"]  # Path unchanged

    def test_update_ingredient_change_parent(self, db_instance):
        """Test updating ingredient parent (path changes)"""
        db = db_instance

        # Create hierarchy
        spirits = db.create_ingredient(
                {"name": "Spirits", "description": "Spirits", "parent_id": None}
        )
        liqueurs = db.create_ingredient(
                {"name": "Liqueurs", "description": "Liqueurs", "parent_id": None}
        )
        gin = db.create_ingredient(
                {"name": "Test", "description": "Gin", "parent_id": spirits["id"]}
        )

        original_path = gin["path"]

        # Move gin from spirits to liqueurs
        updated = db.update_ingredient(gin["id"], {"parent_id": liqueurs["id"]})

        assert updated["parent_id"] == liqueurs["id"]
        assert updated["path"] == f"/{liqueurs['id']}/{gin['id']}/"
        assert updated["path"] != original_path

    def test_update_ingredient_to_root_level(self, db_instance):
        """Test moving ingredient to root level (no parent)"""
        db = db_instance

        # Create hierarchy
        spirits = db.create_ingredient(
                {"name": "Spirits", "description": "Spirits", "parent_id": None}
        )
        gin = db.create_ingredient(
                {"name": "Test", "description": "Gin", "parent_id": spirits["id"]}
        )

        # Move gin to root level
        updated = db.update_ingredient(gin["id"], {"parent_id": None})

        assert updated["parent_id"] is None
        assert updated["path"] == f"/{gin['id']}/"

    def test_update_ingredient_descendants_path_update(self, db_instance):
        """Test that descendant paths are updated when parent path changes"""
        db = db_instance

        # Create hierarchy
        spirits = db.create_ingredient(
                {"name": "Spirits", "description": "Spirits", "parent_id": None}
        )
        liqueurs = db.create_ingredient(
                {"name": "Liqueurs", "description": "Liqueurs", "parent_id": None}
        )
        gin = db.create_ingredient(
                {"name": "Test", "description": "Gin", "parent_id": spirits["id"]}
        )
        london_gin = db.create_ingredient(
                {
                    "name": "London Gin",
                    "description": "London Gin",
                    "parent_id": gin["id"],
                }
        )

        # Move gin to liqueurs (this should update london_gin's path too)
        db.update_ingredient(gin["id"], {"parent_id": liqueurs["id"]})

        # Verify london_gin's path was updated
        updated_london_gin = db.get_ingredient(london_gin["id"])
        assert (
                updated_london_gin["path"]
                == f"/{liqueurs['id']}/{gin['id']}/{london_gin['id']}/"
        )

    def test_update_ingredient_circular_reference_prevention(
        self, db_instance
    ):
        """Test that circular references are prevented"""
        db = db_instance

        # Create hierarchy
        spirits = db.create_ingredient(
                {"name": "Spirits", "description": "Spirits", "parent_id": None}
        )
        gin = db.create_ingredient(
                {"name": "Test", "description": "Gin", "parent_id": spirits["id"]}
        )
        london_gin = db.create_ingredient(
                {
                    "name": "London Gin",
                    "description": "London Gin",
                    "parent_id": gin["id"],
                }
        )

        # Try to make spirits a child of london_gin (would create cycle)
        with pytest.raises(ValueError, match="Cannot create circular reference"):
                db.update_ingredient(spirits["id"], {"parent_id": london_gin["id"]})

    def test_update_ingredient_self_parent_prevention(self, db_instance):
        """Test that ingredient cannot be its own parent"""
        db = db_instance

        gin = db.create_ingredient(
                {"name": "Test", "description": "Gin", "parent_id": None}
        )

        # Try to make gin its own parent
        with pytest.raises(ValueError, match="Ingredient cannot be its own parent"):
                db.update_ingredient(gin["id"], {"parent_id": gin["id"]})

    def test_update_ingredient_nonexistent_parent(self, db_instance):
        """Test updating with non-existent parent"""
        db = db_instance

        gin = db.create_ingredient(
                {"name": "Test", "description": "Gin", "parent_id": None}
        )

        with pytest.raises(
                ValueError, match="Parent ingredient with ID 999 does not exist"
        ):
                db.update_ingredient(gin["id"], {"parent_id": 999})

    def test_update_ingredient_nonexistent(self, db_instance):
        """Test updating non-existent ingredient"""
        db = db_instance

        result = db.update_ingredient(999, {"name": "New Name"})
        assert result is None


class TestIngredientDeletion:
    """Test ingredient deletion operations"""

    def test_delete_ingredient_simple(self, db_instance):
        """Test deleting a simple ingredient"""
        db = db_instance

        gin = db.create_ingredient(
                {"name": "Test", "description": "Test", "parent_id": None}
        )

        result = db.delete_ingredient(gin["id"])
        assert result is True

        # Verify deletion
        assert db.get_ingredient(gin["id"]) is None

    def test_delete_ingredient_with_children(self, db_instance):
        """Test that ingredients with children cannot be deleted"""
        db = db_instance

        parent = db.create_ingredient(
                {"name": "Parent", "description": "Parent", "parent_id": None}
        )
        _ = db.create_ingredient(
                {"name": "Child", "description": "Test", "parent_id": parent["id"]}
        )

        # Try to delete parent with children
        with pytest.raises(
                ValueError, match="Cannot delete ingredient with child ingredients"
        ):
                db.delete_ingredient(parent["id"])

    def test_delete_ingredient_used_in_recipe(self, db_instance):
        """Test that ingredients used in recipes cannot be deleted"""
        db = db_instance

        # Create ingredient
        gin = db.create_ingredient(
                {"name": "Test", "description": "Gin", "parent_id": None}
        )

        # Create recipe using the ingredient
        recipe_data = {
                "name": "Test Martini",
                "instructions": "Stir and strain",
                "ingredients": [{"ingredient_id": gin["id"], "amount": 2.0}],
        }
        db.create_recipe(recipe_data)

        # Try to delete ingredient used in recipe
        with pytest.raises(
                ValueError, match="Cannot delete ingredient used in recipes"
        ):
                db.delete_ingredient(gin["id"])

    def test_delete_ingredient_nonexistent(self, db_instance):
        """Test deleting non-existent ingredient"""
        db = db_instance

        result = db.delete_ingredient(999)
        assert result is False


class TestIngredientConstraints:
    """Test ingredient constraints and validation"""

    def test_ingredient_name_uniqueness(self, db_instance):
        """Test that ingredient names must be unique (case-insensitive)"""
        db = db_instance

        # Create first ingredient
        db.create_ingredient(
                {"name": "Test", "description": "First gin", "parent_id": None}
        )

        # Try to create with same name (different case)
        from core.exceptions import ConflictException
        with pytest.raises(ConflictException):
                db.create_ingredient(
                    {"name": "Test", "description": "Second gin", "parent_id": None}
                )

    def test_ingredient_parent_foreign_key(self, db_instance):
        """Test parent_id foreign key constraint"""
        db = db_instance

        # Try to create ingredient with invalid parent_id
        with pytest.raises(ValueError):
                db.create_ingredient(
                    {
                        "name": "Test",
                        "description": "Gin",
                        "parent_id": 999,  # Non-existent parent
                    }
                )

    def test_ingredient_path_generation(self, db_instance):
        """Test that paths are correctly generated"""
        db = db_instance

        # Root level ingredient
        root = db.create_ingredient(
                {"name": "Root", "description": "Root", "parent_id": None}
        )
        assert root["path"] == f"/{root['id']}/"

        # Child ingredient
        child = db.create_ingredient(
                {"name": "Child", "description": "Child", "parent_id": root["id"]}
        )
        assert child["path"] == f"/{root['id']}/{child['id']}/"

        # Grandchild ingredient
        grandchild = db.create_ingredient(
                {
                    "name": "Grandchild",
                    "description": "Grandchild",
                    "parent_id": child["id"],
                }
        )
        assert (
                grandchild["path"] == f"/{root['id']}/{child['id']}/{grandchild['id']}/"
        )


class TestIngredientEdgeCases:
    """Test edge cases and error conditions"""

    def test_ingredient_empty_name(self, db_instance):
        """Test creating ingredient with empty name"""
        db = db_instance

        with pytest.raises(ValueError, match="empty or whitespace only"):  # Should fail due to validation
                db.create_ingredient(
                    {"name": "", "description": "Test", "parent_id": None}
                )

    def test_ingredient_none_name(self, db_instance):
        """Test creating ingredient with None name"""
        db = db_instance

        with pytest.raises(Exception):  # Should fail due to NOT NULL constraint
                db.create_ingredient(
                    {"name": None, "description": "Test", "parent_id": None}
                )

    def test_ingredient_unicode_name(self, db_instance):
        """Test creating ingredient with unicode characters"""
        db = db_instance

        unicode_name = "Café Liqueur 🍸"
        result = db.create_ingredient(
                {"name": unicode_name, "description": "Unicode test", "parent_id": None}
        )

        assert result["name"] == unicode_name

    def test_ingredient_special_characters(self, db_instance):
        """Test creating ingredient with special characters"""
        db = db_instance

        special_name = 'St-Germain\'s "Premium" Elderflower & Herbs (100%)'
        result = db.create_ingredient(
                {
                    "name": special_name,
                    "description": "Special chars test",
                    "parent_id": None,
                }
        )

        assert result["name"] == special_name
