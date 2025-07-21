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
                // For FastAPI HTTPException, the specific error message is in 'detail' field
                const errorMessage = data.detail || data.error || `API error: ${response.status}`;
                throw new Error(errorMessage);
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
    getFetchOptions(method = 'GET', body = null, requiresAuth = false) {
        const options = {
            method,
            mode: 'cors',
            credentials: 'omit',  // Must be 'omit' for a server with wildcard CORS origin
            headers: {},
        };

        // Only add Content-Type header for requests with body (POST, PUT, etc.)
        if (body) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }

        // Add Authorization header for non-GET requests or when explicitly required
        if (method !== 'GET' || requiresAuth) {
            // Require authentication for non-GET requests or auth-required GET requests
            if (!isAuthenticated()) {
                throw new Error('Authentication required. Please log in to perform this action.');
            }            
            // Ensure we have a valid token
            const token = localStorage.getItem('token');
            if (!token) {
                throw new Error('No authentication token found. Please log in again.');
            }
            // Use the ID Token for API Gateway Authorizer
            const idToken = localStorage.getItem('id_token');
            if (idToken) {
                options.headers['Authorization'] = `Bearer ${idToken}`;
            }
        }

        return options;
    }

    // Private helper for making requests
    async _request(path, method = 'GET', body = null, requiresAuth = false) {
        const url = `${this.baseUrl}${path}`;
        const options = this.getFetchOptions(method, body, requiresAuth);
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

    async bulkUploadRecipes(recipesData) {
        return this._request('/recipes/bulk', 'POST', recipesData);
    }

    async bulkUploadIngredients(ingredientsData) {
        return this._request('/ingredients/bulk', 'POST', ingredientsData);
    }

    // Search recipes with various criteria
    async searchRecipes(searchQuery, page = 1, limit = 20) {
        // Build query string from the search parameters
        const queryParams = new URLSearchParams();
        
        // Add pagination parameters
        queryParams.append('page', page.toString());
        queryParams.append('limit', limit.toString());
        
        // Add search filters to query params
        if (searchQuery.name) {
            console.log('Adding name query parameter:', searchQuery.name);
            queryParams.append('q', searchQuery.name);
        }
        
        if (searchQuery.rating) {
            queryParams.append('min_rating', searchQuery.rating);
        }
        
        if (searchQuery.tags && searchQuery.tags.length > 0) {
            // Send tags as a comma-separated string
            const tagsString = searchQuery.tags.join(',');
            queryParams.append('tags', tagsString);
        }
        
        // Handle ingredient queries as a comma-separated list of names with operators
        if (searchQuery.ingredients && searchQuery.ingredients.length > 0) {
            // Ingredients are already in the correct format: ["Vodka", "Gin:MUST_NOT", etc.]
            const ingredientsString = searchQuery.ingredients.join(',');
            queryParams.append('ingredients', ingredientsString);
        }
        
        // Add inventory filter if requested
        if (searchQuery.inventory) {
            queryParams.append('inventory', 'true');
        }
        
        // Build the URL with query string
        const queryString = queryParams.toString();
        console.log('Built query string:', queryString);
        
        // Use different endpoint for inventory searches
        let url;
        let requiresAuth = false;
        
        if (searchQuery.inventory) {
            // Remove inventory parameter from query string for the inventory endpoint
            const inventoryParams = new URLSearchParams();
            queryParams.forEach((value, key) => {
                if (key !== 'inventory') {
                    inventoryParams.append(key, value);
                }
            });
            const inventoryQueryString = inventoryParams.toString();
            url = `${this.baseUrl}/recipes/search/inventory${inventoryQueryString ? `?${inventoryQueryString}` : ''}`;
            requiresAuth = true;
        } else {
            url = `${this.baseUrl}/recipes/search${queryString ? `?${queryString}` : ''}`;
            requiresAuth = false;
        }
        
        console.log('Final search URL:', url);
        
        // Always use GET for recipe searches
        const response = await fetch(url, this.getFetchOptions('GET', null, requiresAuth));
        const data = await this.handleResponse(response);
        
        // Handle paginated search response format with metadata
        if (data && typeof data === 'object' && data.recipes) {
            return {
                recipes: data.recipes,
                pagination: {
                    page: data.pagination.page || page,
                    limit: data.pagination.limit || limit,
                    total: data.pagination.total_count || data.recipes.length,
                    has_next: data.pagination.has_next || false
                }
            };
        }
        // Fallback for direct array response (legacy format)
        return {
            recipes: data || [],
            pagination: { page: 1, limit: limit, total: (data || []).length, totalPages: 1 }
        };
    }

    // Units API
    async getUnits() {
        return this._request('/units');
    }

    
    // Ratings API
    
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
    

    // Helper to check if user is authenticated
    isAuthenticated() {
        return isAuthenticated();
    }

    // Add a tag to a recipe
    // jsTagType should be 'public' or 'private'
    async addTagToRecipe(recipeId, tagName, jsTagType) {
        let tagToUse;
        
        if (jsTagType === 'private') {
            // For private tags, check if it exists first
            const privateTags = await this.getPrivateTags();
            const existingTag = privateTags.find(tag => tag.name.toLowerCase() === tagName.toLowerCase());
            
            if (!existingTag) {
                // Create new private tag if it doesn't exist
                tagToUse = await this.createPrivateTag(tagName);
            } else {
                tagToUse = existingTag;
            }
            
            const path = `/recipes/${recipeId}/private_tags`;
            return this._request(path, 'POST', { tag_id: tagToUse.id });
        } else {
            // For public tags, check if it exists first
            const publicTags = await this.getPublicTags();
            const existingTag = publicTags.find(tag => tag.name.toLowerCase() === tagName.toLowerCase());
            
            if (!existingTag) {
                // Create new public tag if it doesn't exist
                tagToUse = await this.createPublicTag(tagName);
            } else {
                tagToUse = existingTag;
            }
            
            const path = `/recipes/${recipeId}/public_tags`;
            return this._request(path, 'POST', { tag_id: tagToUse.id });
        }
    }

    // Remove a tag from a recipe
    // jsTagType should be 'public' or 'private'
    async removeTagFromRecipe(recipeId, tagId, jsTagType) {
        const apiTagType = `${jsTagType}_tags`;
        const path = `/recipes/${recipeId}/${apiTagType}/${tagId}`;
        return this._request(path, 'DELETE');
    }

    // Get all public tags
    async getPublicTags() {
        return this._request('/tags/public');
    }

    // Create a public tag (requires authentication)
    async createPublicTag(tagName) {
        return this._request('/tags/public', 'POST', { name: tagName }, true);
    }

    // Get private tags (requires authentication)
    async getPrivateTags() {
        return this._request('/tags/private', 'GET', null, true);
    }

    // Create a private tag (requires authentication)
    async createPrivateTag(tagName) {
        return this._request('/tags/private', 'POST', { name: tagName }, true);
    }

    // User Ingredients API
    async getUserIngredients() {
        return this._request('/user-ingredients', 'GET', null, true);
    }

    async addUserIngredient(ingredientId) {
        return this._request('/user-ingredients', 'POST', { ingredient_id: ingredientId });
    }

    async removeUserIngredient(ingredientId) {
        return this._request(`/user-ingredients/${ingredientId}`, 'DELETE');
    }

    async bulkAddUserIngredients(ingredientIds) {
        return this._request('/user-ingredients/bulk', 'POST', { ingredient_ids: ingredientIds });
    }

    async bulkRemoveUserIngredients(ingredientIds) {
        return this._request('/user-ingredients/bulk', 'DELETE', { ingredient_ids: ingredientIds });
    }


}

// Create and export the API instance
const api = new CocktailAPI();
export { api }; 