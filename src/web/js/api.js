import config from './config.js';
import { isAuthenticated } from './auth.js';

class CocktailAPI {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl || config.apiUrl;
    }

    async handleResponse(response) {
        // Check for 204 No Content before trying to parse JSON
        if (response.status === 204) {
            return null; // Or return {}; depending on what the caller expects
        }
        
        // Handle 404 not found errors more gracefully
        if (response.status === 404) {
            // For ratings endpoint specifically, just return an empty array
            if (response.url.includes('/ratings/')) {
                return [];
            }
            // For other 404s, provide the error but with a clearer message
            const errorObj = { error: `Resource not found: ${response.url}` };
            throw new Error(errorObj.error);
        }

        try {
            const data = await response.json();
            if (response.status >= 400) {
                throw new Error(data.error || `API error: ${response.status}`);
            }
            return data;
        } catch (e) {
            // If we can't parse JSON (e.g., HTML error page returned)
            if (e instanceof SyntaxError) {
                throw new Error(`API returned invalid JSON: ${response.status} ${response.statusText}`);
            }
            throw e;
        }
    }

    // Common fetch options for all requests
    getFetchOptions(method = 'GET', body = null) {
        const options = {
            method,
            mode: 'cors',
            credentials: 'omit',  // Must be 'omit' for a server with wildcard CORS origin
            headers: {
                'Content-Type': 'application/json',
            },
        };

        // Always use the ID Token - API Gateway Authorizer expects this
        const idToken = localStorage.getItem('id_token');
        if (method !== 'GET') {
            // Require authentication for non-GET requests
            if (!isAuthenticated()) {
                throw new Error('Authentication required. Please log in to perform this action.');
            }            
            // Ensure we have a valid token
            const token = localStorage.getItem('token');
            if (!token) {
                throw new Error('No authentication token found. Please log in again.');
            }
        }
        if (idToken) {
            options.headers['Authorization'] = `Bearer ${idToken}`;
        }
        if (body) {
            options.body = JSON.stringify(body);
        }

        return options;
    }

    // Private helper for making requests
    async _request(path, method = 'GET', body = null) {
        const url = `${this.baseUrl}${path}`;
        const options = this.getFetchOptions(method, body);
        const response = await fetch(url, options);
        return this.handleResponse(response);
    }

    // Ingredients API
    async getIngredients() {
        return this._request('/ingredients');
    }

    async getIngredient(id) {
        return this._request(`/ingredients/${id}`);
    }

    async createIngredient(ingredientData) {        
        return this._request('/ingredients', 'POST', ingredientData);
    }

    async updateIngredient(id, ingredientData) {
        return this._request(`/ingredients/${id}`, 'PUT', ingredientData);
    }

    async deleteIngredient(id) {
        return this._request(`/ingredients/${id}`, 'DELETE');
    }

    // Recipes API
    async getRecipes() {
        return this._request('/recipes');
    }

    async getRecipe(id) {
        return this._request(`/recipes/${id}`);
    }

    async createRecipe(recipeData) {
        return this._request('/recipes', 'POST', recipeData);
    }

    async updateRecipe(id, recipeData) {
        return this._request(`/recipes/${id}`, 'PUT', recipeData);
    }

    async deleteRecipe(id) {
        return this._request(`/recipes/${id}`, 'DELETE');
    }

    // Search recipes with various criteria
    async searchRecipes(searchQuery) {
        // Build query string from the search parameters
        const queryParams = new URLSearchParams();
        
        // Add search filters to query params
        if (searchQuery.name) {
            queryParams.append('name', searchQuery.name);
        }
        
        if (searchQuery.rating) {
            queryParams.append('min_rating', searchQuery.rating);
        }
        
        if (searchQuery.tags && searchQuery.tags.length > 0) {
            // For multiple tags, append each one
            searchQuery.tags.forEach(tag => {
                queryParams.append('tags', tag);
            });
        }
        
        // Handle ingredient queries as a comma-separated list of ID:OPERATOR pairs
        if (searchQuery.ingredients && searchQuery.ingredients.length > 0) {
            const ingredientParams = searchQuery.ingredients.map(ing => 
                `${ing.id}:${ing.operator}`
            ).join(',');
            
            queryParams.append('ingredients', ingredientParams);
        }
        
        // Build the URL with query string
        const queryString = queryParams.toString();
        const url = `${this.baseUrl}/recipes?search=true${queryString ? `&${queryString}` : ''}`;
        
        // Always use GET for recipe searches
        const response = await fetch(url, this.getFetchOptions());
        return this.handleResponse(response);
    }

    // Units API
    async getUnits() {
        return this._request('/units');
    }

    async createUnit(unitData) {
        return this._request('/units', 'POST', unitData);
    }

    async getUnitsByType(type) {
        return this._request(`/units?type=${type}`);
    }
    
    // Ratings API
    async getRatings(recipeId) {
        try {
            // Ensure recipeId is defined and build a proper URL
            if (!recipeId) {
                console.error('Recipe ID is required for getRatings');
                return [];
            }

            // For debugging - log the full URL we're requesting
            const url = `${this.baseUrl}/ratings/${recipeId}`;
            console.log('Fetching ratings from:', url);
            
            // The handleResponse method now handles 404s for ratings
            return this._request(`/ratings/${recipeId}`);
        } catch (error) {
            console.error(`Error getting ratings for recipe ${recipeId}:`, error);
            return []; // Return empty array on error
        }
    }
    
    async setRating(recipeId, ratingData) {
        try {
            // Use POST for new ratings, PUT for updating existing ones
            // The backend will handle both the same way
            const method = ratingData.isUpdate ? 'PUT' : 'POST';
            return this._request(`/ratings/${recipeId}`, method, ratingData);
        } catch (error) {
            console.error(`Error setting rating for recipe ${recipeId}:`, error);
            throw error;
        }
    }
    
    async deleteRating(recipeId) {
        try {
            return this._request(`/ratings/${recipeId}`, 'DELETE');
        } catch (error) {
            console.error(`Error deleting rating for recipe ${recipeId}:`, error);
            throw error;
        }
    }

    // Helper to check if user is authenticated
    isAuthenticated() {
        return isAuthenticated();
    }

    // Add a tag to a recipe
    // jsTagType should be 'public' or 'private'
    // The backend expects { name: tagName } in the body
    async addTagToRecipe(recipeId, tagName, jsTagType) {
        const apiTagType = `${jsTagType}_tags`; // Converts to 'public_tags' or 'private_tags'
        const path = `/recipes/${recipeId}/${apiTagType}`;
        return this._request(path, 'POST', { name: tagName });
    }

    // Remove a tag from a recipe
    // jsTagType should be 'public' or 'private'
    async removeTagFromRecipe(recipeId, tagId, jsTagType) {
        const apiTagType = `${jsTagType}_tags`;
        const path = `/recipes/${recipeId}/${apiTagType}/${tagId}`;
        return this._request(path, 'DELETE');
    }

    // Get all public tags (if needed directly)
}

// Create and export the API instance
const api = new CocktailAPI();
export { api }; 