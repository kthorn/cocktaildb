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
        - Test Whiskey (parent, allow_substitution=True)
          - Test Bourbon (child, allow_substitution=True)
            - Test Maker's Mark (grandchild, allow_substitution=True)
            - Test Buffalo Trace (grandchild, allow_substitution=True)
            - Test Woodford Reserve (grandchild, allow_substitution=True)
        """
        # Create whiskey category - use unique name to avoid conflicts
        whiskey = db.create_ingredient({
            "name": "Test Whiskey",
            "description": "Base whiskey category for testing",
            "parent_id": None,
            "allow_substitution": True,
            "created_by": "test-user"
        })

        # Create bourbon subcategory
        bourbon = db.create_ingredient({
            "name": "Test Bourbon",
            "description": "American bourbon whiskey for testing",
            "parent_id": whiskey["id"],
            "allow_substitution": True,
            "created_by": "test-user"
        })

        # Create specific bourbon brands
        makers_mark = db.create_ingredient({
            "name": "Test Maker's Mark",
            "description": "Premium bourbon whiskey for testing",
            "parent_id": bourbon["id"],
            "allow_substitution": True,
            "created_by": "test-user"
        })

        buffalo_trace = db.create_ingredient({
            "name": "Test Buffalo Trace",
            "description": "Classic bourbon whiskey for testing",
            "parent_id": bourbon["id"],
            "allow_substitution": True,
            "created_by": "test-user"
        })

        woodford = db.create_ingredient({
            "name": "Test Woodford Reserve",
            "description": "Small batch bourbon for testing",
            "parent_id": bourbon["id"],
            "allow_substitution": True,
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
        - Test Amaro (parent, allow_substitution=False)
          - Test Amaro Nonino (child, allow_substitution=False)
          - Test Amaro Montenegro (child, allow_substitution=False)
          - Test Cynar (child, allow_substitution=False)
        """
        # Create amaro category with no substitution
        amaro = db.create_ingredient({
            "name": "Test Amaro",
            "description": "Italian herbal liqueur category for testing",
            "parent_id": None,
            "allow_substitution": False,  # No substitution allowed
            "created_by": "test-user"
        })

        # Create specific amaro types
        nonino = db.create_ingredient({
            "name": "Test Amaro Nonino",
            "description": "Light, elegant amaro for testing",
            "parent_id": amaro["id"],
            "allow_substitution": False,
            "created_by": "test-user"
        })

        montenegro = db.create_ingredient({
            "name": "Test Amaro Montenegro",
            "description": "Medium-bodied amaro for testing",
            "parent_id": amaro["id"],
            "allow_substitution": False,
            "created_by": "test-user"
        })

        cynar = db.create_ingredient({
            "name": "Test Cynar",
            "description": "Artichoke-based amaro for testing",
            "parent_id": amaro["id"],
            "allow_substitution": False,
            "created_by": "test-user"
        })

        return {
            "amaro": amaro,
            "nonino": nonino,
            "montenegro": montenegro,
            "cynar": cynar
        }

    def test_allow_substitution_creation_and_retrieval(self, db: Database):
        """Test that allow_substitution is properly stored and retrieved"""
        # Create ingredient with allow_substitution=True
        ingredient = db.create_ingredient({
            "name": "Test Rum",
            "description": "Test rum with substitution allowed",
            "parent_id": None,
            "allow_substitution": True,
            "created_by": "test-user"
        })

        assert ingredient["allow_substitution"] == 1  # SQLite stores booleans as integers

        # Retrieve and verify
        retrieved = db.get_ingredient(ingredient["id"])
        assert retrieved["allow_substitution"] == 1  # SQLite stores booleans as integers

        # Create ingredient with allow_substitution=False
        no_sub_ingredient = db.create_ingredient({
            "name": "Test Amaro",
            "description": "Test amaro with no substitution",
            "parent_id": None,
            "allow_substitution": False,
            "created_by": "test-user"
        })

        assert no_sub_ingredient["allow_substitution"] == 0  # SQLite stores booleans as integers

        # Create child ingredient with allow_substitution=True
        child_ingredient = db.create_ingredient({
            "name": "Test Brand",
            "description": "Test brand with substitution",
            "parent_id": ingredient["id"],
            "allow_substitution": True,
            "created_by": "test-user"
        })

        assert child_ingredient["allow_substitution"] == 1  # SQLite stores booleans as integers

    def test_allow_substitution_update(self, db: Database):
        """Test updating allow_substitution"""
        # Create ingredient
        ingredient = db.create_ingredient({
            "name": "Test Ingredient",
            "description": "Test ingredient for updating",
            "parent_id": None,
            "allow_substitution": True,
            "created_by": "test-user"
        })

        # Update allow_substitution to False
        updated = db.update_ingredient(ingredient["id"], {
            "allow_substitution": False
        })

        assert updated["allow_substitution"] == 0  # SQLite stores booleans as integers

        # Update back to True
        updated = db.update_ingredient(ingredient["id"], {
            "allow_substitution": True
        })

        assert updated["allow_substitution"] == 1  # SQLite stores booleans as integers

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
        # - Recipe calls for "Bourbon" (allow_substitution=True)
        # - User has "Maker's Mark" and "Buffalo Trace" (both allow_substitution=True)
        # - Substitution allowed within parent category
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
        # - Recipe calls for "Maker's Mark" (allow_substitution=True)
        # - User has "Buffalo Trace" and "Woodford" (both allow_substitution=True)
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
        # - Recipe calls for "Amaro Nonino" (allow_substitution=False)
        # - No substitution allowed
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
        # - Recipe calls for "Bourbon" (allow_substitution=True)
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

    def test_recursive_ancestor_substitution(self, db: Database):
        """Test recursive ancestor substitution through common ancestors"""
        # Create deeper hierarchy for testing recursive matching
        # Spirits (grandparent, allow_substitution=True)
        #   - Whiskey (parent, allow_substitution=True)
        #     - Bourbon (child, allow_substitution=True)
        #   - Brandy (parent, allow_substitution=True)
        #     - Cognac (child, allow_substitution=True)

        spirits = db.create_ingredient({
            "name": "Spirits",
            "description": "Base spirits category",
            "parent_id": None,
            "allow_substitution": True,  # Allow substitution
            "created_by": "test-user"
        })

        whiskey = db.create_ingredient({
            "name": "Test Whiskey L2",
            "description": "Whiskey spirits for recursive testing",
            "parent_id": spirits["id"],
            "allow_substitution": True,
            "created_by": "test-user"
        })

        bourbon = db.create_ingredient({
            "name": "Test Bourbon L2",
            "description": "American bourbon for recursive testing",
            "parent_id": whiskey["id"],
            "allow_substitution": True,
            "created_by": "test-user"
        })

        brandy = db.create_ingredient({
            "name": "Test Brandy L2",
            "description": "Brandy spirits for recursive testing",
            "parent_id": spirits["id"],
            "allow_substitution": True,
            "created_by": "test-user"
        })

        cognac = db.create_ingredient({
            "name": "Test Cognac L2",
            "description": "French cognac for recursive testing",
            "parent_id": brandy["id"],
            "allow_substitution": True,
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
        user_id = "test-user-recursive"
        db.add_user_ingredient(user_id, cognac["id"])

        # Should find recipe with recursive substitution
        # Both bourbon and cognac share the same grandparent (Spirits) with allow_substitution=True
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )

        # Recursive substitution should work because both bourbon and cognac
        # share the same grandparent (Spirits) with allow_substitution=True
        assert len(results) == 1
        assert results[0]["name"] == "Flexible Spirit Cocktail"

    def test_get_all_ingredients_includes_allow_substitution(self, db: Database):
        """Test that get_ingredients returns allow_substitution for all ingredients"""
        # Create some test ingredients
        self.setup_bourbon_hierarchy(db)
        self.setup_amaro_hierarchy(db)

        # Get all ingredients
        ingredients = db.get_ingredients()

        # Verify all ingredients have allow_substitution field
        for ingredient in ingredients:
            assert "allow_substitution" in ingredient
            # Should be integer (SQLite stores booleans as 0/1)
            assert isinstance(ingredient["allow_substitution"], int)
            assert ingredient["allow_substitution"] in (0, 1)

    def test_search_ingredients_includes_allow_substitution(self, db: Database):
        """Test that search_ingredients returns allow_substitution"""
        # Create test ingredients
        bourbons = self.setup_bourbon_hierarchy(db)

        # Search for bourbon
        results = db.search_ingredients("bourbon")

        # Should find bourbon ingredients with allow_substitution
        assert len(results) > 0
        for ingredient in results:
            assert "allow_substitution" in ingredient
            # All bourbon test ingredients should have allow_substitution=True
            if "Bourbon" in ingredient["name"] or "Whiskey" in ingredient["name"]:
                assert ingredient["allow_substitution"] == 1  # SQLite stores booleans as integers


class TestSubstitutionAPI:
    """Test API endpoints with substitution functionality"""

    @pytest.fixture
    def db(self, db_instance) -> Database:
        """Get a fresh database instance for each test"""
        return db_instance

    def test_parent_child_no_substitution_blocks_match(self, db: Database):
        """
        Test that user having parent ingredient doesn't match child that blocks substitution.
        Regression test for bug: User has Gin (allow_sub=false), recipe needs Old Tom Gin (allow_sub=false)
        → should NOT match (was incorrectly matching before fix)
        """
        # Create Gin (parent) with no substitution
        gin = db.create_ingredient({
            "name": "Test Gin",
            "description": "Base gin category",
            "parent_id": None,
            "allow_substitution": False,  # Parent doesn't allow substitution
            "created_by": "test-user"
        })

        # Create Old Tom Gin (child) with no substitution
        old_tom_gin = db.create_ingredient({
            "name": "Test Old Tom Gin",
            "description": "Sweetened gin style",
            "parent_id": gin["id"],
            "allow_substitution": False,  # Child doesn't allow substitution
            "created_by": "test-user"
        })

        # Create recipe requiring Old Tom Gin
        recipe = db.create_recipe({
            "name": "Martinez",
            "instructions": "Stir with ice and strain",
            "description": "Classic gin cocktail",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": old_tom_gin["id"],
                    "amount": 2.0,
                    "unit_id": 1
                }
            ]
        })

        # User has only the parent Gin (not Old Tom Gin)
        user_id = "test-user-gin-parent"
        db.add_user_ingredient(user_id, gin["id"])

        # Search should NOT find the recipe because:
        # - User has parent (Gin)
        # - Recipe needs child (Old Tom Gin) with allow_substitution=False
        # - Child doesn't allow parent substitution
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )

        assert len(results) == 0, "Recipe should NOT match when user has parent but child doesn't allow substitution"

    def test_blocking_middle_parent_prevents_match(self, db: Database):
        """
        Test that a blocking parent in the middle of hierarchy prevents substitution.
        Regression test for bug: User has Rum, recipe needs Wray And Nephew,
        but "Pot Still Unaged Rum" in between has allow_sub=false → should NOT match

        Hierarchy: Rum (yes) → Pot Still Unaged Rum (NO) → Wray And Nephew (yes)
        """
        # Create Rum (grandparent) with substitution allowed
        rum = db.create_ingredient({
            "name": "Test Rum Grandparent",
            "description": "Base rum category",
            "parent_id": None,
            "allow_substitution": True,  # Allows substitution
            "created_by": "test-user"
        })

        # Create Pot Still Unaged Rum (parent) with NO substitution
        pot_still = db.create_ingredient({
            "name": "Test Pot Still Unaged Rum",
            "description": "Unaged rum category - BLOCKS substitution",
            "parent_id": rum["id"],
            "allow_substitution": False,  # BLOCKS substitution
            "created_by": "test-user"
        })

        # Create Wray And Nephew (child) with substitution allowed
        wray_nephew = db.create_ingredient({
            "name": "Test Wray And Nephew",
            "description": "Specific overproof rum",
            "parent_id": pot_still["id"],
            "allow_substitution": True,  # Allows substitution
            "created_by": "test-user"
        })

        # Create recipe requiring Wray And Nephew
        recipe = db.create_recipe({
            "name": "Zombie",
            "instructions": "Mix all ingredients",
            "description": "Tiki classic requiring overproof rum",
            "created_by": "test-user",
            "ingredients": [
                {
                    "ingredient_id": wray_nephew["id"],
                    "amount": 1.0,
                    "unit_id": 1
                }
            ]
        })

        # User has only the grandparent Rum (not Pot Still or Wray And Nephew)
        user_id = "test-user-blocking-middle"
        db.add_user_ingredient(user_id, rum["id"])

        # Search should NOT find the recipe because:
        # - User has grandparent (Rum with allow_sub=true)
        # - Recipe needs grandchild (Wray And Nephew with allow_sub=true)
        # - BUT middle parent (Pot Still Unaged Rum) has allow_sub=false, BLOCKING the path
        results = db.search_recipes_paginated(
            search_params={"inventory": True},
            limit=10,
            offset=0,
            user_id=user_id
        )

        assert len(results) == 0, "Recipe should NOT match when blocking parent exists in substitution path"

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