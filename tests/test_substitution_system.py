"""
Tests for ingredient substitution system functionality

This test suite verifies that the substitution_level field works correctly
for ingredient search and recipe matching scenarios.
"""

import pytest
from api.db.database import get_database
from api.db.db_core import Database


class TestIngredientSubstitution:
    """Test cases for ingredient substitution levels"""

    @pytest.fixture
    def db(self, db_instance) -> Database:
        """Get a fresh database instance for each test"""
        return db_instance

    def setup_bourbon_hierarchy(self, db: Database):
        """
        Set up a bourbon ingredient hierarchy for testing:
        - Test Whiskey (parent, level 1)
          - Test Bourbon (child, level NULL - inherits from parent)
            - Test Maker's Mark (grandchild, level NULL - inherits)
            - Test Buffalo Trace (grandchild, level NULL - inherits)
            - Test Woodford Reserve (grandchild, level NULL - inherits)
        """
        # Create whiskey category - use unique name to avoid conflicts
        whiskey = db.create_ingredient({
            "name": "Test Whiskey",
            "description": "Base whiskey category for testing",
            "parent_id": None,
            "substitution_level": 1,
            "created_by": "test-user"
        })
        
        # Create bourbon subcategory
        bourbon = db.create_ingredient({
            "name": "Test Bourbon",
            "description": "American bourbon whiskey for testing",
            "parent_id": whiskey["id"],
            "substitution_level": None,  # Inherits from parent (1)
            "created_by": "test-user"
        })
        
        # Create specific bourbon brands
        makers_mark = db.create_ingredient({
            "name": "Test Maker's Mark",
            "description": "Premium bourbon whiskey for testing",
            "parent_id": bourbon["id"],
            "substitution_level": None,  # Inherits from parent (1)
            "created_by": "test-user"
        })
        
        buffalo_trace = db.create_ingredient({
            "name": "Test Buffalo Trace",
            "description": "Classic bourbon whiskey for testing",
            "parent_id": bourbon["id"],
            "substitution_level": None,  # Inherits from parent (1)
            "created_by": "test-user"
        })
        
        woodford = db.create_ingredient({
            "name": "Test Woodford Reserve",
            "description": "Small batch bourbon for testing",
            "parent_id": bourbon["id"],
            "substitution_level": None,  # Inherits from parent (1)
            "created_by": "test-user"
        })
        
        return {
            "whiskey": whiskey,
            "bourbon": bourbon,
            "makers_mark": makers_mark,
            "buffalo_trace": buffalo_trace,
            "woodford": woodford
        }

    def setup_amaro_hierarchy(self, db: Database):
        """
        Set up an amaro hierarchy where each is unique (no substitution):
        - Test Amaro (parent, level 0 - no substitution)
          - Test Amaro Nonino (child, level NULL - inherits 0)
          - Test Amaro Montenegro (child, level NULL - inherits 0)
          - Test Cynar (child, level NULL - inherits 0)
        """
        # Create amaro category with no substitution
        amaro = db.create_ingredient({
            "name": "Test Amaro",
            "description": "Italian herbal liqueur category for testing",
            "parent_id": None,
            "substitution_level": 0,  # No substitution allowed
            "created_by": "test-user"
        })
        
        # Create specific amaro types
        nonino = db.create_ingredient({
            "name": "Test Amaro Nonino",
            "description": "Light, elegant amaro for testing",
            "parent_id": amaro["id"],
            "substitution_level": None,  # Inherits from parent (0)
            "created_by": "test-user"
        })
        
        montenegro = db.create_ingredient({
            "name": "Test Amaro Montenegro",
            "description": "Medium-bodied amaro for testing",
            "parent_id": amaro["id"],
            "substitution_level": None,  # Inherits from parent (0)
            "created_by": "test-user"
        })
        
        cynar = db.create_ingredient({
            "name": "Test Cynar",
            "description": "Artichoke-based amaro for testing",
            "parent_id": amaro["id"],
            "substitution_level": None,  # Inherits from parent (0)
            "created_by": "test-user"
        })
        
        return {
            "amaro": amaro,
            "nonino": nonino,
            "montenegro": montenegro,
            "cynar": cynar
        }

    def test_substitution_level_creation_and_retrieval(self, db: Database):
        """Test that substitution_level is properly stored and retrieved"""
        # Create ingredient with substitution level 1
        ingredient = db.create_ingredient({
            "name": "Test Rum",
            "description": "Test rum with substitution level 1",
            "parent_id": None,
            "substitution_level": 1,
            "created_by": "test-user"
        })
        
        assert ingredient["substitution_level"] == 1
        
        # Retrieve and verify
        retrieved = db.get_ingredient(ingredient["id"])
        assert retrieved["substitution_level"] == 1
        
        # Create ingredient with substitution level 0
        no_sub_ingredient = db.create_ingredient({
            "name": "Test Amaro",
            "description": "Test amaro with no substitution",
            "parent_id": None,
            "substitution_level": 0,
            "created_by": "test-user"
        })
        
        assert no_sub_ingredient["substitution_level"] == 0
        
        # Create ingredient with NULL substitution level (inherits)
        inherit_ingredient = db.create_ingredient({
            "name": "Test Brand",
            "description": "Test brand that inherits",
            "parent_id": ingredient["id"],
            "substitution_level": None,
            "created_by": "test-user"
        })
        
        assert inherit_ingredient["substitution_level"] is None

    def test_substitution_level_update(self, db: Database):
        """Test updating substitution levels"""
        # Create ingredient
        ingredient = db.create_ingredient({
            "name": "Test Ingredient",
            "description": "Test ingredient for updating",
            "parent_id": None,
            "substitution_level": 1,
            "created_by": "test-user"
        })
        
        # Update substitution level
        updated = db.update_ingredient(ingredient["id"], {
            "substitution_level": 0
        })
        
        assert updated["substitution_level"] == 0
        
        # Update to NULL (inherit)
        updated = db.update_ingredient(ingredient["id"], {
            "substitution_level": None
        })
        
        assert updated["substitution_level"] is None

    def test_bourbon_substitution_in_search(self, db: Database):
        """Test that bourbon brands can substitute for each other in recipe search"""
        # Set up bourbon hierarchy
        bourbons = self.setup_bourbon_hierarchy(db)
        
        # Create a recipe that calls for bourbon (parent category) with ingredients included
        recipe = db.create_recipe({
            "name": "Old Fashioned",
            "instructions": "Muddle sugar with bitters, add bourbon, stir",
            "description": "Classic whiskey cocktail",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": bourbons["bourbon"]["id"],
                    "amount": 2.0,
                    "unit_id": 1
                }
            ]
        })
        
        # Add user ingredients - they have specific bourbon brands
        user_id = "test-user-123"
        db.add_user_ingredient(user_id, bourbons["makers_mark"]["id"])
        db.add_user_ingredient(user_id, bourbons["buffalo_trace"]["id"])
        
        # Search for recipes with user's ingredients
        # This should find the Old Fashioned because:
        # - Recipe calls for "Bourbon" (substitution_level = NULL, inherits 1 from Whiskey)
        # - User has "Maker's Mark" and "Buffalo Trace" (both inherit level 1)
        # - Level 1 allows substitution within parent category
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )
        
        assert len(results) == 1
        assert results[0]["name"] == "Old Fashioned"

    def test_specific_bourbon_brand_recipe(self, db: Database):
        """Test recipe that calls for specific bourbon brand"""
        # Set up bourbon hierarchy
        bourbons = self.setup_bourbon_hierarchy(db)
        
        # Create recipe that calls for specific Maker's Mark with ingredients included
        recipe = db.create_recipe({
            "name": "Maker's Mark Manhattan",
            "instructions": "Stir with vermouth and bitters",
            "description": "Manhattan with specific bourbon brand",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": bourbons["makers_mark"]["id"],
                    "amount": 2.0,
                    "unit_id": 1
                }
            ]
        })
        
        # User has different bourbon brands
        user_id = "test-user-456"
        db.add_user_ingredient(user_id, bourbons["buffalo_trace"]["id"])
        db.add_user_ingredient(user_id, bourbons["woodford"]["id"])
        
        # Search should still find the recipe because:
        # - Recipe calls for "Maker's Mark" (inherits substitution_level 1)
        # - User has "Buffalo Trace" and "Woodford" (both inherit level 1)  
        # - All are siblings under "Bourbon" parent, so substitution allowed
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )
        
        assert len(results) == 1
        assert results[0]["name"] == "Maker's Mark Manhattan"

    def test_amaro_no_substitution(self, db: Database):
        """Test that amaro types don't substitute for each other"""
        # Set up amaro hierarchy with no substitution
        amaros = self.setup_amaro_hierarchy(db)
        
        # Create recipe that calls for Amaro Nonino specifically with ingredients included
        recipe = db.create_recipe({
            "name": "Paper Plane",
            "instructions": "Shake all ingredients",
            "description": "Modern classic with Amaro Nonino",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": amaros["nonino"]["id"],
                    "amount": 0.75,
                    "unit_id": 1
                }
            ]
        })
        
        # User has different amaro
        user_id = "test-user-789"
        db.add_user_ingredient(user_id, amaros["montenegro"]["id"])
        db.add_user_ingredient(user_id, amaros["cynar"]["id"])
        
        # Search should NOT find the recipe because:
        # - Recipe calls for "Amaro Nonino" (inherits substitution_level 0)
        # - Level 0 means no substitution allowed
        # - User doesn't have exact "Amaro Nonino"
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )
        
        assert len(results) == 0

    def test_amaro_exact_match_works(self, db: Database):
        """Test that exact amaro matches still work"""
        # Set up amaro hierarchy
        amaros = self.setup_amaro_hierarchy(db)
        
        # Create recipe with Amaro Montenegro with ingredients included
        recipe = db.create_recipe({
            "name": "Montenegro Spritz",
            "instructions": "Build in glass with prosecco",
            "description": "Refreshing amaro cocktail",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": amaros["montenegro"]["id"],
                    "amount": 1.0,
                    "unit_id": 1
                }
            ]
        })
        
        # User has the exact same amaro
        user_id = "test-user-exact"
        db.add_user_ingredient(user_id, amaros["montenegro"]["id"])
        
        # Should find the recipe (exact match)
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )
        
        assert len(results) == 1
        assert results[0]["name"] == "Montenegro Spritz"

    def test_recipe_calls_for_category_user_has_brand(self, db: Database):
        """Test when recipe calls for category and user has specific brand"""
        # Set up bourbon hierarchy
        bourbons = self.setup_bourbon_hierarchy(db)
        
        # Create recipe that calls for general "Bourbon" category with ingredients included
        recipe = db.create_recipe({
            "name": "Bourbon Sour",
            "instructions": "Shake with lemon and simple syrup",
            "description": "Classic sour with bourbon",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": bourbons["bourbon"]["id"],
                    "amount": 2.0,
                    "unit_id": 1
                }
            ]
        })
        
        # User has specific bourbon brand
        user_id = "test-user-brand"
        db.add_user_ingredient(user_id, bourbons["woodford"]["id"])
        
        # Should find recipe because:
        # - Recipe calls for "Bourbon" (substitution_level NULL, inherits 1)
        # - User has "Woodford Reserve" (path matches /whiskey_id/bourbon_id/woodford_id)
        # - Path-based matching handles category -> brand scenario
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )
        
        assert len(results) == 1
        assert results[0]["name"] == "Bourbon Sour"

    def test_mixed_substitution_levels_in_recipe(self, db: Database):
        """Test recipe with both substitutable and non-substitutable ingredients"""
        # Set up both hierarchies
        bourbons = self.setup_bourbon_hierarchy(db)
        amaros = self.setup_amaro_hierarchy(db)
        
        # Create recipe with both bourbon (substitutable) and specific amaro (not substitutable) with ingredients included
        recipe = db.create_recipe({
            "name": "Boulevardier Variation",
            "instructions": "Stir with sweet vermouth",
            "description": "Bourbon and amaro cocktail",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": bourbons["bourbon"]["id"],
                    "amount": 2.0,
                    "unit_id": 1
                },
                {
                    "ingredient_id": amaros["nonino"]["id"],
                    "amount": 1.0,
                    "unit_id": 1
                }
            ]
        })
        
        # User has different bourbon brand (OK) but different amaro (NOT OK)
        user_id = "test-user-mixed"
        db.add_user_ingredient(user_id, bourbons["makers_mark"]["id"])  # Different bourbon - should work
        db.add_user_ingredient(user_id, amaros["montenegro"]["id"])      # Different amaro - won't work
        
        # Should NOT find recipe because amaro requirement not met
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )
        
        assert len(results) == 0
        
        # Now give user correct amaro
        db.add_user_ingredient(user_id, amaros["nonino"]["id"])
        
        # Should find recipe now
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )
        
        assert len(results) == 1
        assert results[0]["name"] == "Boulevardier Variation"

    def test_substitution_level_2_grandparent_substitution(self, db: Database):
        """Test substitution_level 2 for grandparent-level substitution"""
        # Create deeper hierarchy for testing level 2
        # Spirits (grandparent, level 2)
        #   - Whiskey (parent, level NULL - inherits 2)  
        #     - Bourbon (child, level NULL - inherits 2)
        #   - Brandy (parent, level NULL - inherits 2)
        #     - Cognac (child, level NULL - inherits 2)
        
        spirits = db.create_ingredient({
            "name": "Spirits",
            "description": "Base spirits category",
            "parent_id": None,
            "substitution_level": 2,  # Allow grandparent-level substitution
            "created_by": "test-user"
        })
        
        whiskey = db.create_ingredient({
            "name": "Test Whiskey L2",
            "description": "Whiskey spirits for level 2 testing",
            "parent_id": spirits["id"],
            "substitution_level": None,  # Inherits 2
            "created_by": "test-user"
        })
        
        bourbon = db.create_ingredient({
            "name": "Test Bourbon L2",
            "description": "American bourbon for level 2 testing",
            "parent_id": whiskey["id"],
            "substitution_level": None,  # Inherits 2
            "created_by": "test-user"
        })
        
        brandy = db.create_ingredient({
            "name": "Test Brandy L2",
            "description": "Brandy spirits for level 2 testing",
            "parent_id": spirits["id"],
            "substitution_level": None,  # Inherits 2
            "created_by": "test-user"
        })
        
        cognac = db.create_ingredient({
            "name": "Test Cognac L2",
            "description": "French cognac for level 2 testing",
            "parent_id": brandy["id"],
            "substitution_level": None,  # Inherits 2
            "created_by": "test-user"
        })
        
        # Create recipe calling for bourbon with ingredients included
        recipe = db.create_recipe({
            "name": "Flexible Spirit Cocktail",
            "instructions": "Mix with other ingredients",
            "description": "Cocktail that works with various spirits",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": bourbon["id"],
                    "amount": 2.0,
                    "unit_id": 1
                }
            ]
        })
        
        # User has cognac (different branch but same grandparent)
        user_id = "test-user-level2"
        db.add_user_ingredient(user_id, cognac["id"])
        
        # Should find recipe with level 2 substitution
        # (This would require implementing level 2 logic in the SQL query)
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )
        
        # Level 2 substitution should work because both bourbon and cognac 
        # share the same grandparent (Spirits) with substitution_level 2
        assert len(results) == 1
        assert results[0]["name"] == "Flexible Spirit Cocktail"

    def test_get_all_ingredients_includes_substitution_level(self, db: Database):
        """Test that get_ingredients returns substitution_level for all ingredients"""
        # Create some test ingredients
        self.setup_bourbon_hierarchy(db)
        self.setup_amaro_hierarchy(db)
        
        # Get all ingredients
        ingredients = db.get_ingredients()
        
        # Verify all ingredients have substitution_level field
        for ingredient in ingredients:
            assert "substitution_level" in ingredient
            # Should be int, None, or 0
            assert ingredient["substitution_level"] is None or isinstance(ingredient["substitution_level"], int)

    def test_search_ingredients_includes_substitution_level(self, db: Database):
        """Test that search_ingredients returns substitution_level"""
        # Create test ingredients
        bourbons = self.setup_bourbon_hierarchy(db)
        
        # Search for bourbon
        results = db.search_ingredients("bourbon")
        
        # Should find bourbon ingredients with substitution_level
        assert len(results) > 0
        for ingredient in results:
            assert "substitution_level" in ingredient
            if ingredient["name"] == "Whiskey":
                assert ingredient["substitution_level"] == 1
            elif ingredient["name"] == "Bourbon":
                assert ingredient["substitution_level"] is None  # Inherits from parent


class TestSubstitutionAPI:
    """Test API endpoints with substitution functionality"""
    
    def test_ingredient_create_with_substitution_level(self):
        """Test creating ingredient via API with substitution_level"""
        # This would test the FastAPI endpoints
        # Implementation depends on test client setup
        pass
    
    def test_ingredient_update_substitution_level(self):
        """Test updating substitution_level via API"""
        pass
    
    def test_bulk_ingredient_upload_with_substitution(self):
        """Test bulk upload with substitution levels"""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])