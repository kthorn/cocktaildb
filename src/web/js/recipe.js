import { api } from './api.js';
import { createRecipeCard } from './recipeCard.js';

document.addEventListener('DOMContentLoaded', async () => {
    const recipeContainer = document.getElementById('recipe-container');
    const loadingPlaceholder = recipeContainer.querySelector('.loading-placeholder');
    const pageTitle = document.getElementById('recipe-page-title');

    // Get recipe info from URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const recipeId = urlParams.get('id');
    const recipeName = urlParams.get('name');

    if (!recipeId && !recipeName) {
        // No recipe identifier provided
        loadingPlaceholder.innerHTML = '<p>No recipe specified. Please provide a recipe ID or name in the URL.</p>';
        return;
    }

    try {
        let recipe = null;
        if (recipeId) {
            recipe = await api.getRecipe(recipeId);
        } else {
            // Search for the recipe by name
            const result = await api.searchRecipes({ name: recipeName }, 1, 1);
            if (result && result.recipes && result.recipes.length > 0) {
                recipe = result.recipes[0];
            }
        }

        // Hide loading placeholder
        if (loadingPlaceholder) {
            loadingPlaceholder.remove();
        }

        if (recipe) {
            // Update page title
            pageTitle.textContent = recipe.name;
            document.title = `${recipe.name} - Mixology Tools`;

            // Create and display the recipe card
            const recipeCard = createRecipeCard(recipe, true, null, { showSimilar: true });
            recipeContainer.appendChild(recipeCard);
        } else {
            // Recipe not found
            recipeContainer.innerHTML = `
                <div class="error-message">
                    <p>Recipe not found.</p>
                    <p><a href="search.html">Search for other recipes</a></p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading recipe:', error);

        // Hide loading placeholder
        if (loadingPlaceholder) {
            loadingPlaceholder.remove();
        }

        // Show error message
        recipeContainer.innerHTML = `
            <div class="error-message">
                <p>Error loading recipe: ${error.message}</p>
                <p><a href="search.html">Go to search page</a></p>
            </div>
        `;
    }
});
