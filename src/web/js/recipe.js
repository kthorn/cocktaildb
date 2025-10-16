import { api } from './api.js';
import { createRecipeCard } from './recipeCard.js';

document.addEventListener('DOMContentLoaded', async () => {
    const recipeContainer = document.getElementById('recipe-container');
    const loadingPlaceholder = recipeContainer.querySelector('.loading-placeholder');
    const pageTitle = document.getElementById('recipe-page-title');

    // Get recipe name from URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const recipeName = urlParams.get('name');

    if (!recipeName) {
        // No recipe name provided
        loadingPlaceholder.innerHTML = '<p>No recipe specified. Please provide a recipe name in the URL.</p>';
        return;
    }

    try {
        // Search for the recipe by name
        const result = await api.searchRecipes({ name: recipeName }, 1, 1);

        // Hide loading placeholder
        if (loadingPlaceholder) {
            loadingPlaceholder.remove();
        }

        if (result && result.recipes && result.recipes.length > 0) {
            const recipe = result.recipes[0];

            // Update page title
            pageTitle.textContent = recipe.name;
            document.title = `${recipe.name} - Mixology Tools`;

            // Create and display the recipe card
            const recipeCard = createRecipeCard(recipe, true);
            recipeContainer.appendChild(recipeCard);
        } else {
            // Recipe not found
            recipeContainer.innerHTML = `
                <div class="error-message">
                    <p>Recipe "${decodeURIComponent(recipeName)}" not found.</p>
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
