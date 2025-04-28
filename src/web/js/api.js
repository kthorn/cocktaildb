import config from './config.js';

class CocktailAPI {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl || config.apiUrl;
    }

    async handleResponse(response) {
        const data = await response.json();
        if (response.status >= 400) {
            throw new Error(data.error || 'An error occurred');
        }
        return data;
    }

    // Common fetch options for all requests
    getFetchOptions(method = 'GET', body = null) {
        const options = {
            method,
            mode: 'cors',
            credentials: 'omit',
            headers: {
                'Content-Type': 'application/json',
            },
        };
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
}

// Create and export the API instance
const api = new CocktailAPI();
export { api }; 