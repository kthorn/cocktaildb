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
                throw new Error('Authentication required. Please log in to create ingredients.');
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

    // Ingredients API
    async getIngredients() {
        const response = await fetch(`${this.baseUrl}/ingredients`, this.getFetchOptions());
        return this.handleResponse(response);
    }

    async getIngredient(id) {
        const response = await fetch(`${this.baseUrl}/ingredients/${id}`, this.getFetchOptions());
        return this.handleResponse(response);
    }

    async createIngredient(ingredientData) {        
        const response = await fetch(
            `${this.baseUrl}/ingredients`,
            this.getFetchOptions('POST', ingredientData)
        );
        return this.handleResponse(response);
    }

    async updateIngredient(id, ingredientData) {
        const response = await fetch(
            `${this.baseUrl}/ingredients/${id}`,
            this.getFetchOptions('PUT', ingredientData)
        );
        return this.handleResponse(response);
    }

    async deleteIngredient(id) {
        const response = await fetch(
            `${this.baseUrl}/ingredients/${id}`,
            this.getFetchOptions('DELETE')
        );
        return this.handleResponse(response);
    }

    // Recipes API
    async getRecipes() {
        const response = await fetch(`${this.baseUrl}/recipes`, this.getFetchOptions());
        return this.handleResponse(response);
    }

    async getRecipe(id) {
        const response = await fetch(`${this.baseUrl}/recipes/${id}`, this.getFetchOptions());
        return this.handleResponse(response);
    }

    async createRecipe(recipeData) {
        const response = await fetch(
            `${this.baseUrl}/recipes`,
            this.getFetchOptions('POST', recipeData)
        );
        return this.handleResponse(response);
    }

    async updateRecipe(id, recipeData) {
        const response = await fetch(
            `${this.baseUrl}/recipes/${id}`,
            this.getFetchOptions('PUT', recipeData)
        );
        return this.handleResponse(response);
    }

    async deleteRecipe(id) {
        const response = await fetch(
            `${this.baseUrl}/recipes/${id}`,
            this.getFetchOptions('DELETE')
        );
        return this.handleResponse(response);
    }

    // Units API
    async getUnits() {
        const response = await fetch(`${this.baseUrl}/units`, this.getFetchOptions());
        return this.handleResponse(response);
    }

    async createUnit(unitData) {
        const response = await fetch(
            `${this.baseUrl}/units`,
            this.getFetchOptions('POST', unitData)
        );
        return this.handleResponse(response);
    }

    async getUnitsByType(type) {
        const response = await fetch(
            `${this.baseUrl}/units?type=${type}`,
            this.getFetchOptions()
        );
        return this.handleResponse(response);
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
            
            const response = await fetch(
                url,
                this.getFetchOptions()
            );
            
            // The handleResponse method now handles 404s for ratings
            return this.handleResponse(response);
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
            const response = await fetch(
                `${this.baseUrl}/ratings/${recipeId}`,
                this.getFetchOptions(method, ratingData)
            );
            return this.handleResponse(response);
        } catch (error) {
            console.error(`Error setting rating for recipe ${recipeId}:`, error);
            throw error;
        }
    }
    
    async deleteRating(recipeId) {
        try {
            const response = await fetch(
                `${this.baseUrl}/ratings/${recipeId}`,
                this.getFetchOptions('DELETE')
            );
            return this.handleResponse(response);
        } catch (error) {
            console.error(`Error deleting rating for recipe ${recipeId}:`, error);
            throw error;
        }
    }

    // Helper to check if user is authenticated
    isAuthenticated() {
        return isAuthenticated();
    }
}

// Create and export the API instance
const api = new CocktailAPI();
export { api }; 