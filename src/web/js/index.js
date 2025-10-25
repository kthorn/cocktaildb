import { api } from './api.js';
import { createRecipeCard } from './recipeCard.js';

let currentRecipeIndex = 0;
let recipes = [];
let currentPage = 1;
let hasMoreRecipes = true;
let isLoadingRecipes = false;
const recipesPerPage = 12;

// Update stats display
async function updateStats() {
    try {
        const stats = await api.getStats();
        document.getElementById('total-ingredients').textContent = stats.ingredients_count;
        document.getElementById('total-recipes').textContent = stats.recipes_count;
    } catch (error) {
        console.error('Error updating stats:', error);
    }
}

// Load initial recipes (first page only)
async function loadInitialRecipes() {
    try {
        // Show loading message
        document.getElementById('recipe-display').innerHTML = '<p>Loading recipes...</p>';
        
        // Reset state
        recipes = [];
        currentPage = 1;
        hasMoreRecipes = true;
        isLoadingRecipes = false;
        
        // Load first page
        await loadMoreRecipes();
        
        // Display the first recipe if we have any
        if (recipes.length > 0) {
            displayRecipe(currentRecipeIndex);
        } else {
            document.getElementById('recipe-display').innerHTML = '<p>No recipes found.</p>';
        }
        
        updateStats();
    } catch (error) {
        console.error('Error loading initial recipes:', error);
        document.getElementById('recipe-display').innerHTML = '<p>Error loading recipes.</p>';
    }
}

// Load more recipes (for pagination/scroll)
async function loadMoreRecipes() {
    if (isLoadingRecipes || !hasMoreRecipes) {
        return;
    }
    
    isLoadingRecipes = true;
    
    try {
        console.log(`Loading page ${currentPage}...`);
        const result = await api.searchRecipes({}, currentPage, recipesPerPage, 'random', 'asc'); // Empty search returns all recipes in random order
        console.log(`Page ${currentPage} result:`, result);
        
        if (result && result.recipes && result.recipes.length > 0) {
            recipes = recipes.concat(result.recipes);
            console.log(`Added ${result.recipes.length} recipes. Total: ${recipes.length}`);
            
            // Check if there are more pages
            console.log('Pagination object:', result.pagination);
            hasMoreRecipes = result.pagination.has_next;
            console.log(`Has more pages: ${hasMoreRecipes}`);
            currentPage++;
        } else {
            console.log('No more recipes found');
            hasMoreRecipes = false;
        }
    } catch (error) {
        console.error('Error loading more recipes:', error);
        hasMoreRecipes = false;
    } finally {
        isLoadingRecipes = false;
    }
}

// Display a specific recipe by index
async function displayRecipe(index) {
    if (recipes.length === 0) return;
    
    // Ensure index is within bounds, but handle lazy loading
    if (index < 0) index = recipes.length - 1;
    if (index >= recipes.length) {
        // Check if we need to load more recipes
        if (hasMoreRecipes && !isLoadingRecipes) {
            await loadMoreRecipes();
            // After loading, check if we now have the recipe
            if (index >= recipes.length) {
                index = recipes.length - 1; // Fall back to last available
            }
        } else {
            index = 0; // Wrap to beginning
        }
    }
    
    currentRecipeIndex = index;
    
    try {
        // Use the already loaded full recipe data
        const recipe = recipes[index];
        if (recipe) {
            const recipeCard = createRecipeCard(recipe, true);
            
            document.getElementById('recipe-display').innerHTML = '';
            document.getElementById('recipe-display').appendChild(recipeCard);
        }
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
    loadInitialRecipes();
}); 