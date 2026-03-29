import { api } from './api.js';
import { createRecipeCard } from './recipeCard.js';

document.addEventListener('DOMContentLoaded', async () => {
    const recipeContainer = document.getElementById('recipe-container');
    const loadingPlaceholder = recipeContainer?.querySelector('.loading-placeholder');
    const pageTitle = document.getElementById('recipe-page-title');

    // Get recipe ID from URL path (/recipe/42) or query param (?id=42) as fallback
    const pathMatch = window.location.pathname.match(/^\/recipe\/(\d+)$/);
    const recipeId = pathMatch ? pathMatch[1] : new URLSearchParams(window.location.search).get('id');
    const recipeName = new URLSearchParams(window.location.search).get('name');

    if (!recipeId && !recipeName) {
        if (loadingPlaceholder) {
            loadingPlaceholder.innerHTML = '<p>No recipe specified.</p>';
        }
        return;
    }

    try {
        let recipe = null;
        if (recipeId) {
            recipe = await api.getRecipe(recipeId);
        } else {
            const result = await api.searchRecipes({ name: recipeName }, 1, 1);
            if (result && result.recipes && result.recipes.length > 0) {
                recipe = result.recipes[0];
            }
        }

        if (recipe) {
            // Update page title
            if (pageTitle) pageTitle.textContent = recipe.name;
            document.title = `${recipe.name} - Mixology Tools`;

            // Remove loading placeholder if present
            if (loadingPlaceholder) loadingPlaceholder.remove();

            // Clear SSR content and render interactive card
            recipeContainer.innerHTML = '';
            const recipeCard = createRecipeCard(recipe, true, null, { showSimilar: true });
            recipeContainer.appendChild(recipeCard);
        } else if (loadingPlaceholder) {
            // Only show error if we had a loading placeholder (non-SSR page)
            loadingPlaceholder.innerHTML = `
                <p>Recipe not found.</p>
                <p><a href="/search.html">Search for other recipes</a></p>
            `;
        }
        // If no recipe and no placeholder (SSR page), SSR content stays visible
    } catch (error) {
        console.error('Error loading recipe:', error);
        if (loadingPlaceholder) {
            loadingPlaceholder.innerHTML = `
                <p>Error loading recipe: ${error.message}</p>
                <p><a href="/search.html">Go to search page</a></p>
            `;
        }
        // On error with SSR content: leave SSR visible, don't overwrite
    }
});
