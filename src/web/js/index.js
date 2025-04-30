import { api } from './api.js';
import { initAuth } from './auth.js';

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Fetch and display statistics
    fetchStatistics();
    
    // Initialize authentication UI
    initAuth();
});

async function fetchStatistics() {
    try {
        // Fetch ingredients count using the API instance
        const ingredients = await api.getIngredients();
        document.getElementById('total-ingredients').textContent = ingredients.length;

        // Fetch recipes count using the API instance
        const recipes = await api.getRecipes();
        document.getElementById('total-recipes').textContent = recipes.length;
    } catch (error) {
        console.error('Error fetching statistics:', error);
        document.getElementById('total-ingredients').textContent = 'Error';
        document.getElementById('total-recipes').textContent = 'Error';
    }
} 