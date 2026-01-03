"""
Tests for recipe name search functionality
"""

import pytest

pytestmark = pytest.mark.asyncio


class TestRecipeNameSearch:
    """Test recipe search by name functionality"""

    async def test_search_recipes_by_name_exact_match(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes by exact name match"""
        # First get all recipes to find a valid name
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            # Use the first recipe's name for exact search
            recipe_name = all_data["recipes"][0]["name"]
            
            response = await client.get(f"/recipes/search?q={recipe_name}")
            assert response.status_code == 200
            data = response.json()
            
            # Should find at least one recipe with that exact name
            assert data["pagination"]["total_count"] >= 1
            assert len(data["recipes"]) >= 1
            
            # Verify the returned recipe contains the search term
            found_recipe = next((r for r in data["recipes"] if r["name"] == recipe_name), None)
            assert found_recipe is not None, f"Should find recipe with exact name '{recipe_name}'"

    async def test_search_recipes_by_name_partial_match(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching recipes by partial name match"""
        # First get all recipes to find a name we can partially match
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            # Use first few characters of a recipe name
            recipe_name = all_data["recipes"][0]["name"]
            if len(recipe_name) >= 3:
                partial_name = recipe_name[:3]
                
                response = await client.get(f"/recipes/search?q={partial_name}")
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

    async def test_search_recipes_by_name_case_insensitive(self, test_client_with_data):
        client, app = test_client_with_data
        """Test that name search is case-insensitive"""
        # Get a recipe name to test with
        all_response = await client.get("/recipes/search")
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
                response = await client.get(f"/recipes/search?q={search_term}")
                assert response.status_code == 200
                data = response.json()
                
                if expected_count is None:
                    expected_count = data["pagination"]["total_count"]
                else:
                    assert data["pagination"]["total_count"] == expected_count, (
                        f"Case-insensitive search failed: '{search_term}' returned "
                        f"{data['pagination']['total_count']} recipes, expected {expected_count}"
                    )

    async def test_search_recipes_by_name_nonexistent(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching for a recipe name that doesn't exist"""
        response = await client.get("/recipes/search?q=NonexistentRecipeName123456")
        assert response.status_code == 200
        data = response.json()
        
        # Should return no results
        assert data["pagination"]["total_count"] == 0
        assert len(data["recipes"]) == 0

    async def test_search_recipes_by_name_empty_query(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with empty name query"""
        response = await client.get("/recipes/search?q=")
        assert response.status_code == 200
        data = response.json()
        
        # Empty query should return all recipes (same as no filter)
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        assert data["pagination"]["total_count"] == all_data["pagination"]["total_count"]

    async def test_search_recipes_by_name_whitespace_query(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with whitespace-only query"""
        response = await client.get("/recipes/search?q=   ")
        assert response.status_code == 200
        data = response.json()
        
        # Whitespace query should return all recipes (same as no filter after stripping)
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        assert data["pagination"]["total_count"] == all_data["pagination"]["total_count"]

    async def test_search_recipes_by_name_whitespace_trimming(self, test_client_with_data):
        client, app = test_client_with_data
        """Test that leading/trailing whitespace is trimmed from search queries"""
        
        # Get a recipe name to test with
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            recipe_name = all_data["recipes"][0]["name"]
            
            # Test with leading/trailing whitespace
            padded_name = f"  {recipe_name}  "
            response = await client.get(f"/recipes/search?q={padded_name}")
            assert response.status_code == 200
            data = response.json()
            
            # Should find the same results as searching without whitespace
            clean_response = await client.get(f"/recipes/search?q={recipe_name}")
            assert clean_response.status_code == 200
            clean_data = clean_response.json()
            
            assert data["pagination"]["total_count"] == clean_data["pagination"]["total_count"]

    async def test_search_recipes_by_name_special_characters(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with special characters in name"""
        # Test with common cocktail special characters
        special_chars = ["'", "-", "&", ".", "(", ")"]
        
        for char in special_chars:
            response = await client.get(f"/recipes/search?q={char}")
            assert response.status_code == 200
            data = response.json()
            
            # Should return valid response (may be empty results)
            assert "recipes" in data
            assert "pagination" in data
            assert isinstance(data["pagination"]["total_count"], int)

    async def test_search_recipes_by_name_with_numbers(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching for recipe names containing numbers"""
        # Test searching for numbers - the search may find matches in name, description, or instructions
        number_searches = ["21", "7", "1", "2"]
        
        for search_term in number_searches:
            response = await client.get(f"/recipes/search?q={search_term}")
            assert response.status_code == 200
            data = response.json()
            
            # Should return valid response
            assert "recipes" in data
            assert "pagination" in data
            
            # Note: The search API searches across name, description, and instructions
            # So we don't assert that the number must be in the name specifically
            # We just verify the API returns valid results for numeric searches

    async def test_search_recipes_name_vs_no_filter_difference(self, test_client_with_data):
        client, app = test_client_with_data
        """Test that name filtering actually filters results"""
        # Get all recipes (no filter)
        all_response = await client.get("/recipes/search")
        assert all_response.status_code == 200
        all_data = all_response.json()
        
        if all_data["recipes"]:
            # Use a specific recipe name that should return fewer results
            specific_name = all_data["recipes"][0]["name"][:4]  # First 4 characters
            
            name_response = await client.get(f"/recipes/search?q={specific_name}")
            assert name_response.status_code == 200
            name_data = name_response.json()
            
            # Name search should typically return fewer or equal results
            assert name_data["pagination"]["total_count"] <= all_data["pagination"]["total_count"]

    async def test_search_recipes_by_name_url_encoding(self, test_client_with_data):
        client, app = test_client_with_data
        """Test that URL-encoded search terms work correctly"""
        import urllib.parse
        
        # Test with a space (should be encoded as %20 or +)
        search_term = "test recipe"
        encoded_term = urllib.parse.quote_plus(search_term)
        
        response = await client.get(f"/recipes/search?q={encoded_term}")
        assert response.status_code == 200
        data = response.json()
        
        # Should return valid response
        assert "recipes" in data
        assert "pagination" in data

    async def test_search_recipes_by_name_long_query(self, test_client_with_data):
        client, app = test_client_with_data
        """Test searching with very long query string"""
        long_query = "a" * 100  # 100 character string
        
        response = await client.get(f"/recipes/search?q={long_query}")
        assert response.status_code == 200
        data = response.json()
        
        # Should return valid response (likely empty)
        assert "recipes" in data
        assert "pagination" in data
        assert data["pagination"]["total_count"] == 0  # Unlikely to match anything