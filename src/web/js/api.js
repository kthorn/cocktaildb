class CocktailAPI {
    constructor(baseUrl = 'http://localhost:3000/api') {
        this.baseUrl = baseUrl;
    }

    // Ingredients API
    async getIngredients() {
        const response = await fetch(`${this.baseUrl}/ingredients`);
        return await response.json();
    }

    async createIngredient(ingredientData) {
        const response = await fetch(`${this.baseUrl}/ingredients`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(ingredientData),
        });
        return await response.json();
    }

    async updateIngredient(id, ingredientData) {
        const response = await fetch(`${this.baseUrl}/ingredients/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(ingredientData),
        });
        return await response.json();
    }

    async deleteIngredient(id) {
        const response = await fetch(`${this.baseUrl}/ingredients/${id}`, {
            method: 'DELETE',
        });
        return await response.json();
    }

    // Recipes API
    async getRecipes() {
        const response = await fetch(`${this.baseUrl}/recipes`);
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