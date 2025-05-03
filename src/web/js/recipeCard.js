// Recipe card component for displaying cocktail recipes
import { api } from './api.js';
import { isAuthenticated } from './auth.js';

/**
 * Creates and returns a recipe card element for the given recipe
 * @param {Object} recipe - Recipe data
 * @param {boolean} showActions - Whether to show edit/delete buttons
 * @param {Function} onRecipeDeleted - Callback when recipe is deleted
 * @returns {HTMLElement} The recipe card element
 */
export function createRecipeCard(recipe, showActions = true, onRecipeDeleted = null) {
    const card = document.createElement('div');
    card.className = 'recipe-card';
    
    // Only show action buttons if user is authenticated and showActions is true
    const shouldShowActions = showActions && isAuthenticated();
    
    card.innerHTML = `
        <h4>${recipe.name}</h4>
        <p>${recipe.description || 'No description'}</p>
        <div class="ingredients">
            <h5>Ingredients</h5>
            <ul>
                ${recipe.ingredients.map(ing => {
                    // Format with proper spaces between amount, unit and ingredient name
                    const unitDisplay = ing.unit_name ? `${ing.unit_name} ` : '';
                    
                    // Try multiple possible property names for ingredient full name
                    const ingredientName = ing.full_name || ing.ingredient_name || ing.name || 'Unknown ingredient';
                    
                    return `<li>${ing.amount} ${unitDisplay}${ingredientName}</li>`;
                }).join('')}
            </ul>
        </div>
        <div class="instructions">
            <h5>Instructions</h5>
            <p>${recipe.instructions}</p>
        </div>
        ${shouldShowActions ? `
        <div class="card-actions">
            <button class="edit-recipe" data-id="${recipe.id}">Edit</button>
            <button class="delete-recipe" data-id="${recipe.id}">Delete</button>
        </div>
        ` : ''}
    `;

    // Add event listeners for action buttons if they exist
    if (shouldShowActions) {
        const deleteBtn = card.querySelector('.delete-recipe');
        const editBtn = card.querySelector('.edit-recipe');
        
        if (deleteBtn) {
            deleteBtn.addEventListener('click', async () => {
                await deleteRecipe(recipe.id, onRecipeDeleted);
            });
        }
        
        if (editBtn) {
            editBtn.addEventListener('click', () => {
                if (window.editRecipe) {
                    window.editRecipe(recipe.id);
                } else {
                    console.error('editRecipe function not found');
                }
            });
        }
    }

    return card;
}

/**
 * Displays recipes in the specified container
 * @param {Array} recipes - Array of recipe objects
 * @param {HTMLElement} container - Container element to display recipes in
 * @param {boolean} showActions - Whether to show edit/delete buttons
 * @param {Function} onRecipeDeleted - Callback when recipe is deleted
 */
export function displayRecipes(recipes, container, showActions = true, onRecipeDeleted = null) {
    container.innerHTML = '';

    if (!recipes || recipes.length === 0) {
        container.innerHTML = '<p>No recipes found.</p>';
        return;
    }

    recipes.forEach(recipe => {
        const card = createRecipeCard(recipe, showActions, onRecipeDeleted);
        container.appendChild(card);
    });
}

/**
 * Deletes a recipe by ID
 * @param {number} id - Recipe ID to delete
 * @param {Function} onRecipeDeleted - Callback after deletion
 */
async function deleteRecipe(id, onRecipeDeleted = null) {
    // Check authentication first
    if (!isAuthenticated()) {
        alert('Please log in to delete recipes.');
        return;
    }

    if (!confirm('Are you sure you want to delete this recipe?')) {
        return;
    }

    try {
        await api.deleteRecipe(id);
        alert('Recipe deleted successfully!');
        
        // Call the callback if provided, or use window.loadRecipes if available
        if (typeof onRecipeDeleted === 'function') {
            onRecipeDeleted();
        } else if (window.loadRecipes) {
            window.loadRecipes();
        }
    } catch (error) {
        console.error('Error deleting recipe:', error);
        alert(`Failed to delete recipe: ${error.message || 'Please try again.'}`);
    }
} 