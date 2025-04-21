class CocktailAPI {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.initializeApiUrl();
    }

    async initializeApiUrl() {
        if (!this.baseUrl) {
            try {
                // Fetch the configuration from the config endpoint
                const response = await fetch('/api/config');
                const config = await response.json();

                if (config.apiUrl) {
                    this.baseUrl = config.apiUrl;
                } else {
                    console.error('API Gateway URL not found in configuration');
                    this.baseUrl = 'https://your-api-gateway-url.execute-api.${AWS::Region}.amazonaws.com/api';
                }
            } catch (error) {
                console.error('Error fetching configuration:', error);
                this.baseUrl = 'https://your-api-gateway-url.execute-api.${AWS::Region}.amazonaws.com/api';
            }
        }
    }

    async handleResponse(response) {
        const data = await response.json();
        if (response.status >= 400) {
            throw new Error(data.error || 'An error occurred');
        }
        return data;
    }

    // Ingredients API
    async getIngredients() {
        const response = await fetch(`${this.baseUrl}/ingredients`);
        return this.handleResponse(response);
    }

    async getIngredient(id) {
        const response = await fetch(`${this.baseUrl}/ingredients/${id}`);
        return this.handleResponse(response);
    }

    async createIngredient(ingredientData) {
        const response = await fetch(`${this.baseUrl}/ingredients`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(ingredientData),
        });
        return this.handleResponse(response);
    }

    async updateIngredient(id, ingredientData) {
        const response = await fetch(`${this.baseUrl}/ingredients/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(ingredientData),
        });
        return this.handleResponse(response);
    }

    async deleteIngredient(id) {
        const response = await fetch(`${this.baseUrl}/ingredients/${id}`, {
            method: 'DELETE',
        });
        return this.handleResponse(response);
    }

    // Recipes API
    async getRecipes() {
        const response = await fetch(`${this.baseUrl}/recipes`);
        return await response.json();
    }

    async getRecipe(id) {
        const response = await fetch(`${this.baseUrl}/recipes/${id}`);
        return await response.json();
    }

    async createRecipe(recipeData) {
        const response = await fetch(`${this.baseUrl}/recipes`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(recipeData),
        });
        return await response.json();
    }

    async updateRecipe(id, recipeData) {
        const response = await fetch(`${this.baseUrl}/recipes/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(recipeData),
        });
        return await response.json();
    }

    async deleteRecipe(id) {
        const response = await fetch(`${this.baseUrl}/recipes/${id}`, {
            method: 'DELETE',
        });
        return await response.json();
    }

    // Units API
    async getUnits() {
        const response = await fetch(`${this.baseUrl}/units`);
        return await response.json();
    }

    async createUnit(unitData) {
        const response = await fetch(`${this.baseUrl}/units`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(unitData),
        });
        return await response.json();
    }

    async getUnitsByType(type) {
        const response = await fetch(`${this.baseUrl}/units?type=${type}`);
        return await response.json();
    }
}

// Create a global API instance
const api = new CocktailAPI(); 