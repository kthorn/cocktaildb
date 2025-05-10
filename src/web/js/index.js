import { api } from './api.js';
import { createRecipeCard } from './recipeCard.js';

let currentRecipeIndex = 0;
let recipes = [];

// Update stats display
async function updateStats() {
    try {
        const ingredients = await api.getIngredients();        
        document.getElementById('total-ingredients').textContent = ingredients.length;
        document.getElementById('total-recipes').textContent = recipes.length;
    } catch (error) {
        console.error('Error updating stats:', error);
    }
}

// Load and display a recipe
async function loadRecipes() {
    try {
        recipes = await api.getRecipes();
        if (recipes.length > 0) {
            displayRecipe(currentRecipeIndex);
        } else {
            document.getElementById('recipe-display').innerHTML = '<p>No recipes found.</p>';
        }
        updateStats();
    } catch (error) {
        console.error('Error loading recipes:', error);
        document.getElementById('recipe-display').innerHTML = '<p>Error loading recipes.</p>';
    }
}

// Display a specific recipe by index
async function displayRecipe(index) {
    if (recipes.length === 0) return;
    
    // Ensure index is within bounds
    if (index < 0) index = recipes.length - 1;
    if (index >= recipes.length) index = 0;
    
    currentRecipeIndex = index;
    
    try {
        // Fetch fresh recipe data
        const recipe = await api.getRecipe(recipes[index].id);
        const recipeCard = createRecipeCard(recipe);
        
        document.getElementById('recipe-display').innerHTML = '';
        document.getElementById('recipe-display').appendChild(recipeCard);
    } catch (error) {
        console.error('Error displaying recipe:', error);
        document.getElementById('recipe-display').innerHTML = '<p>Error loading recipe.</p>';
    }
}

// Event listeners for carousel arrows
document.getElementById('prev-recipe').addEventListener('click', async () => {
    await displayRecipe(currentRecipeIndex - 1);
});

document.getElementById('next-recipe').addEventListener('click', async () => {
    await displayRecipe(currentRecipeIndex + 1);
});

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    loadRecipes();
}); 