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
        // Show loading message
        document.getElementById('recipe-display').innerHTML = '<p>Loading recipes...</p>';
        
        // Load all recipes by fetching pages until we get them all
        recipes = [];
        let page = 1;
        let hasMore = true;
        
        while (hasMore) {
            const result = await api.getRecipesWithFullData(page, 10); // Use larger page size for efficiency
            
            if (result && result.recipes && result.recipes.length > 0) {
                recipes = recipes.concat(result.recipes);
                
                // Check if there are more pages
                hasMore = result.pagination && result.pagination.has_next;
                page++;
            } else {
                hasMore = false;
            }
        }
        
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
function displayRecipe(index) {
    if (recipes.length === 0) return;
    
    // Ensure index is within bounds
    if (index < 0) index = recipes.length - 1;
    if (index >= recipes.length) index = 0;
    
    currentRecipeIndex = index;
    
    try {
        // Use the already loaded full recipe data
        const recipe = recipes[index];
        const recipeCard = createRecipeCard(recipe, true);
        
        document.getElementById('recipe-display').innerHTML = '';
        document.getElementById('recipe-display').appendChild(recipeCard);
    } catch (error) {
        console.error('Error displaying recipe:', error);
        document.getElementById('recipe-display').innerHTML = '<p>Error loading recipe.</p>';
    }
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
    loadRecipes(1);
}); 