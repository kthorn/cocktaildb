import { loadHeader } from './common.js';
import { fetchRecipes, fetchIngredients } from './api.js';
import { createRecipeCard } from './recipeCard.js';

let currentRecipeIndex = 0;
let recipes = [];

// Update stats display
async function updateStats() {
    try {
        const ingredients = await fetchIngredients();
        const recipesData = await fetchRecipes();
        
        document.getElementById('total-ingredients').textContent = ingredients.length;
        document.getElementById('total-recipes').textContent = recipesData.length;
    } catch (error) {
        console.error('Error updating stats:', error);
    }
}

// Load and display a recipe
async function loadRecipes() {
    try {
        recipes = await fetchRecipes();
        if (recipes.length > 0) {
            displayRecipe(currentRecipeIndex);
        } else {
            document.getElementById('recipe-display').innerHTML = '<p>No recipes found.</p>';
        }
    } catch (error) {
        console.error('Error loading recipes:', error);
        document.getElementById('recipe-display').innerHTML = '<p>Error loading recipes.</p>';
    }
}

// Display a specific recipe by index
function displayRecipe(index) {
    if (recipes.length === 0) return;
    
    // Ensure index is within bounds
    if (index < 0) index = recipes.length - 1;
    if (index >= recipes.length) index = 0;
    
    currentRecipeIndex = index;
    
    const recipe = recipes[index];
    const recipeCard = createRecipeCard(recipe);
    
    document.getElementById('recipe-display').innerHTML = '';
    document.getElementById('recipe-display').appendChild(recipeCard);
}

// Event listeners for carousel arrows
document.getElementById('prev-recipe').addEventListener('click', () => {
    displayRecipe(currentRecipeIndex - 1);
});

document.getElementById('next-recipe').addEventListener('click', () => {
    displayRecipe(currentRecipeIndex + 1);
});

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    loadRecipes();
    updateStats();
}); 