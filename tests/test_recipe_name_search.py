"""
Tests for recipe name search functionality
"""

import pytest


class TestRecipeNameSearch:
    """Test recipe search by name functionality"""

    def test_search_recipes_by_name_exact_match(self, test_client_production_readonly):
        """Test searching recipes by exact name match"""
        client = test_client_production_readonly
        # First get all recipes to find a valid name
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            # Use the first recipe's name for exact search
            recipe_name = all_data["recipes"][0]["name"]
            
            response = client.get(f"/recipes/search?q={recipe_name}")
            assert response.status_code == 200
            data = response.json()
            
            # Should find at least one recipe with that exact name
            assert data["pagination"]["total_count"] >= 1
            assert len(data["recipes"]) >= 1
            
            # Verify the returned recipe contains the search term
            found_recipe = next((r for r in data["recipes"] if r["name"] == recipe_name), None)
            assert found_recipe is not None, f"Should find recipe with exact name '{recipe_name}'"

    def test_search_recipes_by_name_partial_match(self, test_client_production_readonly):
        """Test searching recipes by partial name match"""
        client = test_client_production_readonly
        # First get all recipes to find a name we can partially match
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            # Use first few characters of a recipe name
            recipe_name = all_data["recipes"][0]["name"]
            if len(recipe_name) >= 3:
                partial_name = recipe_name[:3]
                
                response = client.get(f"/recipes/search?q={partial_name}")
                assert response.status_code == 200
                data = response.json()
                
                # Should return some results
                assert "recipes" in data
                assert "pagination" in data
                
                # All returned recipes should contain the search term in their name
                for recipe in data["recipes"]:
                    assert partial_name.lower() in recipe["name"].lower(), (
                        f"Recipe '{recipe['name']}' should contain '{partial_name}'"
                    )

    def test_search_recipes_by_name_case_insensitive(self, test_client_production_readonly):
        """Test that name search is case-insensitive"""
        client = test_client_production_readonly
        # Get a recipe name to test with
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            original_name = all_data["recipes"][0]["name"]
            
            # Test different case variations
            test_cases = [
                original_name.lower(),
                original_name.upper(),
                original_name.title()
            ]
            
            expected_count = None
            for search_term in test_cases:
                response = client.get(f"/recipes/search?q={search_term}")
                assert response.status_code == 200
                data = response.json()
                
                if expected_count is None:
                    expected_count = data["pagination"]["total_count"]
                else:
                    assert data["pagination"]["total_count"] == expected_count, (
                        f"Case-insensitive search failed: '{search_term}' returned "
                        f"{data['pagination']['total_count']} recipes, expected {expected_count}"
                    )

    def test_search_recipes_by_name_nonexistent(self, test_client_production_readonly):
        """Test searching for a recipe name that doesn't exist"""
        client = test_client_production_readonly
        response = client.get("/recipes/search?q=NonexistentRecipeName123456")
        assert response.status_code == 200
        data = response.json()
        
        # Should return no results
        assert data["pagination"]["total_count"] == 0
        assert len(data["recipes"]) == 0

    def test_search_recipes_by_name_empty_query(self, test_client_production_readonly):
        """Test searching with empty name query"""
        client = test_client_production_readonly
        response = client.get("/recipes/search?q=")
        assert response.status_code == 200
        data = response.json()
        
        # Empty query should return all recipes (same as no filter)
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        assert data["pagination"]["total_count"] == all_data["pagination"]["total_count"]

    def test_search_recipes_by_name_whitespace_query(self, test_client_production_readonly):
        """Test searching with whitespace-only query"""
        client = test_client_production_readonly
        response = client.get("/recipes/search?q=   ")
        assert response.status_code == 200
        data = response.json()
        
        # Whitespace query should return all recipes (same as no filter after stripping)
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        assert data["pagination"]["total_count"] == all_data["pagination"]["total_count"]

    def test_search_recipes_by_name_whitespace_trimming(self, test_client_production_readonly):
        """Test that leading/trailing whitespace is trimmed from search queries"""
        client = test_client_production_readonly
        
        # Get a recipe name to test with
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            recipe_name = all_data["recipes"][0]["name"]
            
            # Test with leading/trailing whitespace
            padded_name = f"  {recipe_name}  "
            response = client.get(f"/recipes/search?q={padded_name}")
            assert response.status_code == 200
            data = response.json()
            
            # Should find the same results as searching without whitespace
            clean_response = client.get(f"/recipes/search?q={recipe_name}")
            assert clean_response.status_code == 200
            clean_data = clean_response.json()
            
            assert data["pagination"]["total_count"] == clean_data["pagination"]["total_count"]

    def test_search_recipes_by_name_special_characters(self, test_client_production_readonly):
        """Test searching with special characters in name"""
        client = test_client_production_readonly
        # Test with common cocktail special characters
        special_chars = ["'", "-", "&", ".", "(", ")"]
        
        for char in special_chars:
            response = client.get(f"/recipes/search?q={char}")
            assert response.status_code == 200
            data = response.json()
            
            # Should return valid response (may be empty results)
            assert "recipes" in data
            assert "pagination" in data
            assert isinstance(data["pagination"]["total_count"], int)

    def test_search_recipes_by_name_with_numbers(self, test_client_production_readonly):
        """Test searching for recipe names containing numbers"""
        client = test_client_production_readonly
        # Test searching for numbers - the search may find matches in name, description, or instructions
        number_searches = ["21", "7", "1", "2"]
        
        for search_term in number_searches:
            response = client.get(f"/recipes/search?q={search_term}")
            assert response.status_code == 200
            data = response.json()
            
            # Should return valid response
            assert "recipes" in data
            assert "pagination" in data
            
            # Note: The search API searches across name, description, and instructions
            # So we don't assert that the number must be in the name specifically
            # We just verify the API returns valid results for numeric searches

    def test_search_recipes_name_vs_no_filter_difference(self, test_client_production_readonly):
        """Test that name filtering actually filters results"""
        client = test_client_production_readonly
        # Get all recipes (no filter)
        all_response = client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            # Use a specific recipe name that should return fewer results
            specific_name = all_data["recipes"][0]["name"][:4]  # First 4 characters
            
            name_response = client.get(f"/recipes/search?q={specific_name}")
            assert name_response.status_code == 200
            name_data = name_response.json()
            
            # Name search should typically return fewer or equal results
            assert name_data["pagination"]["total_count"] <= all_data["pagination"]["total_count"]

    def test_search_recipes_by_name_url_encoding(self, test_client_production_readonly):
        """Test that URL-encoded search terms work correctly"""
        client = test_client_production_readonly
        import urllib.parse
        
        # Test with a space (should be encoded as %20 or +)
        search_term = "test recipe"
        encoded_term = urllib.parse.quote_plus(search_term)
        
        response = client.get(f"/recipes/search?q={encoded_term}")
        assert response.status_code == 200
        data = response.json()
        
        # Should return valid response
        assert "recipes" in data
        assert "pagination" in data

    def test_search_recipes_by_name_long_query(self, test_client_production_readonly):
        """Test searching with very long query string"""
        client = test_client_production_readonly
        long_query = "a" * 100  # 100 character string
        
        response = client.get(f"/recipes/search?q={long_query}")
        assert response.status_code == 200
        data = response.json()
        
        # Should return valid response (likely empty)
        assert "recipes" in data
        assert "pagination" in data
        assert data["pagination"]["total_count"] == 0  # Unlikely to match anything