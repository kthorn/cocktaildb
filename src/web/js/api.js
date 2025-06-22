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
    async getRecipes(page = 1, limit = 20) {
        const response = await this._request(`/recipes?page=${page}&limit=${limit}`);
        // Handle paginated response format with metadata
        if (response && typeof response === 'object' && response.recipes) {
            return {
                recipes: response.recipes,
                pagination: {
                    page: response.page || page,
                    limit: response.limit || limit,
                    total: response.total || response.recipes.length,
                    totalPages: response.total_pages || Math.ceil((response.total || response.recipes.length) / limit)
                }
            };
        }
        // Fallback for direct array response (legacy format)
        return {
            recipes: response || [],
            pagination: { page: 1, limit: limit, total: (response || []).length, totalPages: 1 }
        };
    }

    async getRecipe(id) {
        return this._request(`/recipes/${id}`);
    }

    // Get all recipes with full details (ingredients, instructions, etc.)
    // Now uses paginated endpoint that returns full details directly
    async getRecipesWithFullData(page = 1, limit = 20) {
        return this.getRecipes(page, limit);
    }

    // Search recipes and return full details
    // Now uses paginated search endpoint that returns full details directly
    async searchRecipesWithFullData(searchQuery, page = 1, limit = 20) {
        return this.searchRecipes(searchQuery, page, limit);
    }

    // Legacy helper method - DEPRECATED
    // Note: This method is no longer needed since paginated endpoints return full recipe details
    // Keeping for backward compatibility with existing code
    async enrichRecipes(basicRecipes, onBatchLoaded = null) {
        console.warn('enrichRecipes() is deprecated - use paginated endpoints that return full details directly');
        
        if (!basicRecipes || basicRecipes.length === 0) {
            return basicRecipes;
        }

        const fullRecipes = [];
        const batchSize = 5; // Process 5 recipes at a time to prevent server overload
        
        for (let i = 0; i < basicRecipes.length; i += batchSize) {
            const batch = basicRecipes.slice(i, i + batchSize);
            const batchPromises = batch.map(async (recipe) => {
                try {
                    return await this.getRecipe(recipe.id);
                } catch (error) {
                    console.error(`Error fetching full recipe data for ${recipe.id}:`, error);
                    return recipe; // Fallback to basic recipe data
                }
            });
            
            const batchResults = await Promise.all(batchPromises);
            fullRecipes.push(...batchResults);
            
            // Call the callback with the current batch if provided
            if (typeof onBatchLoaded === 'function') {
                onBatchLoaded(batchResults, fullRecipes.length, basicRecipes.length);
            }
            
            // Small delay between batches to be gentle on the backend
            if (i + batchSize < basicRecipes.length) {
                await new Promise(resolve => setTimeout(resolve, 50));
            }
        }
        
        return fullRecipes;
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
    async searchRecipes(searchQuery, page = 1, limit = 20) {
        // Build query string from the search parameters
        const queryParams = new URLSearchParams();
        
        // Add pagination parameters
        queryParams.append('page', page.toString());
        queryParams.append('limit', limit.toString());
        
        // Add search filters to query params
        if (searchQuery.name) {
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
        
        // Build the URL with query string
        const queryString = queryParams.toString();
        const url = `${this.baseUrl}/recipes/search${queryString ? `?${queryString}` : ''}`;
        
        // Always use GET for recipe searches
        const response = await fetch(url, this.getFetchOptions());
        const data = await this.handleResponse(response);
        
        // Handle paginated search response format with metadata
        if (data && typeof data === 'object' && data.recipes) {
            return {
                recipes: data.recipes,
                pagination: {
                    page: data.pagination.page || page,
                    limit: data.pagination.limit || limit,
                    total: data.pagination.total_count || data.recipes.length,
                    totalPages: data.pagination.total_pages || Math.ceil((data.pagination.total_count || data.recipes.length) / limit)
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

    // Get current user info (requires authentication)
    async getCurrentUserInfo() {
        return this._request('/auth/me', 'GET', null, true);
    }

    // Get all recipes with full details and progressive loading support
    // Now uses paginated endpoint - progressive loading handled by pagination
    async getRecipesWithFullDataProgressive(onPageLoaded = null, page = 1, limit = 20) {
        const result = await this.getRecipes(page, limit);
        
        // Call the callback with the loaded page if provided
        if (typeof onPageLoaded === 'function') {
            onPageLoaded(result.recipes, result.pagination);
        }
        
        return result;
    }

    // Search recipes and return full details with progressive loading support
    // Now uses paginated search endpoint - progressive loading handled by pagination
    async searchRecipesWithFullDataProgressive(searchQuery, onPageLoaded = null, page = 1, limit = 20) {
        const result = await this.searchRecipes(searchQuery, page, limit);
        
        // Call the callback with the loaded page if provided
        if (typeof onPageLoaded === 'function') {
            onPageLoaded(result.recipes, result.pagination);
        }
        
        return result;
    }
}

// Create and export the API instance
const api = new CocktailAPI();
export { api }; 