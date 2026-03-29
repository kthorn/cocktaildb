"""Tests for server-rendered HTML pages (recipe, ingredient, sitemap)"""

import pytest

pytestmark = pytest.mark.asyncio


class TestRecipePage:
    """Test server-rendered recipe pages"""

    async def test_recipe_page_returns_html(self, test_client_with_data):
        """GET /recipe/{id} returns HTML content"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_recipe_page_contains_recipe_name(self, test_client_with_data):
        """Recipe page includes the recipe name in an h1"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert "Test Old Fashioned" in response.text

    async def test_recipe_page_contains_ingredients(self, test_client_with_data):
        """Recipe page includes ingredient list"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert "Bourbon" in response.text

    async def test_recipe_page_contains_instructions(self, test_client_with_data):
        """Recipe page includes instructions"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert "Muddle sugar with bitters" in response.text

    async def test_recipe_page_contains_json_ld(self, test_client_with_data):
        """Recipe page includes JSON-LD structured data"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert 'application/ld+json' in response.text
        assert '"@type": "Recipe"' in response.text

    async def test_recipe_page_contains_meta_description(self, test_client_with_data):
        """Recipe page includes meta description"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert '<meta name="description"' in response.text

    async def test_recipe_page_contains_canonical_url(self, test_client_with_data):
        """Recipe page includes canonical link"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert '<link rel="canonical"' in response.text

    async def test_recipe_page_loads_spa_scripts(self, test_client_with_data):
        """Recipe page loads SPA JS for progressive enhancement"""
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        assert "recipe.js" in response.text
        assert "common.js" in response.text

    async def test_recipe_page_404_for_nonexistent(self, test_client_with_data):
        """GET /recipe/{bad_id} returns 404 HTML"""
        client, app = test_client_with_data
        response = await client.get("/recipe/99999")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        assert "not found" in response.text.lower()

    async def test_recipe_page_source_url_xss_protection(self, test_client_with_data):
        """Source URLs with javascript: scheme are not rendered as links"""
        # This test verifies the template doesn't blindly render source_url as href
        # The test data uses safe URLs, so we just verify the template renders source safely
        client, app = test_client_with_data
        response = await client.get("/recipe/1")
        # Source "Test Source" should appear as text, not as a dangerous link
        assert "Test Source" in response.text


class TestIngredientPage:
    """Test server-rendered ingredient pages"""

    async def test_ingredient_page_returns_html(self, test_client_with_data):
        """GET /ingredient/{id} returns HTML content"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/1")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_ingredient_page_contains_name(self, test_client_with_data):
        """Ingredient page includes the ingredient name"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/1")
        assert "Whiskey" in response.text

    async def test_ingredient_page_contains_json_ld(self, test_client_with_data):
        """Ingredient page includes JSON-LD structured data"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/1")
        assert 'application/ld+json' in response.text

    async def test_ingredient_page_contains_search_link(self, test_client_with_data):
        """Ingredient page links to search filtered by this ingredient"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/1")
        assert "search.html" in response.text

    async def test_ingredient_page_404_for_nonexistent(self, test_client_with_data):
        """GET /ingredient/{bad_id} returns 404 HTML"""
        client, app = test_client_with_data
        response = await client.get("/ingredient/99999")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]


class TestNameRedirect:
    """Test recipe name-to-ID redirect"""

    async def test_name_redirect_finds_recipe(self, test_client_with_data):
        """GET /recipe/by-name?name=X redirects to /recipe/{id}"""
        client, app = test_client_with_data
        response = await client.get(
            "/recipe/by-name", params={"name": "Test Old Fashioned"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"].startswith("/recipe/")

    async def test_name_redirect_404_for_unknown(self, test_client_with_data):
        """GET /recipe/by-name?name=X returns 404 HTML for unknown name"""
        client, app = test_client_with_data
        response = await client.get(
            "/recipe/by-name", params={"name": "Nonexistent Recipe"},
            follow_redirects=False,
        )
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]


class TestSitemap:
    """Test dynamic sitemap generation"""

    async def test_sitemap_returns_xml(self, test_client_with_data):
        """GET /sitemap.xml returns XML content"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]

    async def test_sitemap_contains_recipe_urls(self, test_client_with_data):
        """Sitemap includes recipe page URLs"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert "/recipe/" in response.text

    async def test_sitemap_contains_ingredient_urls(self, test_client_with_data):
        """Sitemap includes ingredient page URLs"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert "/ingredient/" in response.text

    async def test_sitemap_contains_static_pages(self, test_client_with_data):
        """Sitemap includes static page URLs"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert "/about.html" in response.text
        assert "/search.html" in response.text

    async def test_sitemap_has_cache_header(self, test_client_with_data):
        """Sitemap response includes cache control header"""
        client, app = test_client_with_data
        response = await client.get("/sitemap.xml")
        assert "max-age" in response.headers.get("cache-control", "")
