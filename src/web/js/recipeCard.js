// Recipe card component for displaying cocktail recipes
import { api } from './api.js';
import { isAuthenticated, getUserInfo } from './auth.js';
import { generateStarRating, createInteractiveStars } from './common.js';
import { formatIngredientMarkup } from './utils/recipeIngredients.js';
import { generateTagChips, splitRecipeTags, updateTagVisibility } from './components/recipeTags.js';
import { copyRecipeLink, showShareFeedback } from './components/recipeShare.js';
import { renderRecipeRating } from './components/recipeRatings.js';
import { initializeRecipeTagEditor } from './components/recipeTagEditor.js';

/**
 * Creates and returns a recipe card element for the given recipe
 * @param {Object} recipe - Recipe data
 * @param {boolean} showActions - Whether to show edit/delete buttons
 * @param {Function} onRecipeDeleted - Callback when recipe is deleted
 * @param {Object} options - Optional behavior flags
 * @param {boolean} options.showSimilar - Whether to load similar cocktails
 * @param {boolean} options.compact - Whether to use a compact display
 * @param {boolean} options.linkCard - Whether clicking the card navigates to the full recipe page
 * @returns {HTMLElement} The recipe card element
 */
export function createRecipeCard(recipe, showActions = true, onRecipeDeleted = null, options = {}) {
    const showSimilar = options.showSimilar === true;
    const useCompactLayout = options.compact === true;
    const linkCard = options.linkCard === true;
    const card = document.createElement('div');
    card.className = 'recipe-card';
    card.dataset.id = recipe.id; // Add recipe ID to card for easier refresh
    if (useCompactLayout && linkCard) {
        card.classList.add('recipe-card-compact-link');
    }

    // Only show action buttons if user is an editor/admin and showActions is true
    const shouldShowActions = showActions && api.isEditor();
    const shouldShowAddTagButton = isAuthenticated(); // Check if user is authenticated for add tag button

    const { publicTags, privateTags, hasAnyTags } = splitRecipeTags(recipe.tags);

    // Start with the basic recipe details
    card.innerHTML = `
        <h4 class="recipe-title">${recipe.name}</h4>
        <div class="recipe-meta">
            <div class="recipe-tags">
                <div class="tags-container ${hasAnyTags ? '' : 'is-hidden'}">
                    ${generateTagChips(publicTags, { recipeId: recipe.id, shouldShowActions })}
                    ${generateTagChips(privateTags, { recipeId: recipe.id, shouldShowActions })}
                </div>
                <span class="no-tags-placeholder ${hasAnyTags ? 'is-hidden' : ''}">No tags yet</span>
                ${
                    shouldShowAddTagButton
                        ? `
                <button class="add-tag-btn" 
                        data-recipe-id="${recipe.id}" 
                        data-recipe-name="${encodeURIComponent(recipe.name)}" 
                        data-recipe-tags='${JSON.stringify(recipe.tags || [])}' 
                        title="Add or edit tags">(+) Tag</button>
                `
                        : ''
                }
            </div>
            <div id="rating-container-${recipe.id}" class="recipe-rating"></div>
        </div>
        ${recipe.description ? `<p class="recipe-description">${recipe.description}</p>` : ''}
        <div class="ingredients">
            <h5>Ingredients</h5>
            <ul>
                ${(recipe.ingredients || []).map(formatIngredientMarkup).join('')}
            </ul>
        </div>
        ${
            useCompactLayout
                ? ''
                : `
        <div class="instructions">
            <h5>Instructions</h5>
            <p>${recipe.instructions}</p>
        </div>
        ${
            recipe.source || recipe.source_url
                ? `
        <div class="recipe-source">
            <h5>Source</h5>
            <p>${recipe.source_url ? `<a href="${recipe.source_url}" target="_blank" rel="noopener noreferrer">${recipe.source || recipe.source_url}</a>` : recipe.source}</p>
        </div>
        `
                : ''
        }
        `
        }
        ${
            showSimilar
                ? `
        <div class="similar-cocktails" data-recipe-id="${recipe.id}">
            <h5>Similar Cocktails</h5>
            <div class="similar-loading">Loading similar cocktails...</div>
        </div>
        <div class="cocktail-space-link">
            <a href="/analytics.html#cocktail-space-em?highlight=${recipe.id}">📍 View in Cocktail Space →</a>
        </div>
        `
                : ''
        }
        ${
            useCompactLayout && linkCard
                ? `
        <div class="recipe-card-cta">Click for details</div>
        `
                : ''
        }
        <div class="card-actions">
            <button class="share-recipe-btn" data-recipe-name="${encodeURIComponent(recipe.name)}" data-recipe-id="${recipe.id}" title="Share recipe link">🔗</button>
            ${
                shouldShowActions
                    ? `
            <button class="edit-recipe" data-id="${recipe.id}">Edit</button>
            <button class="delete-recipe" data-id="${recipe.id}">Delete</button>
            `
                    : ''
            }
        </div>
    `;

    // Add rating component
    const ratingContainer = card.querySelector(`#rating-container-${recipe.id}`);
    if (ratingContainer) {
        renderRecipeRating(ratingContainer, recipe, {
            authenticated: isAuthenticated(),
            createInteractiveStars,
            generateStarRating,
            onRate: async (rating) => submitRating(recipe.id, rating),
        });
    }

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
                // Navigate to recipes page with edit parameter
                window.location.href = `recipes.html?edit=${recipe.id}`;
            });
        }
    }

    // Add event listener for share button (always present)
    const shareBtn = card.querySelector('.share-recipe-btn');
    if (shareBtn) {
        shareBtn.addEventListener('click', async () => {
            try {
                await copyRecipeLink(recipe.name, recipe.id);
            } catch (error) {
                console.error('Error copying to clipboard:', error);
                showShareFeedback('Failed to copy link. Please try again.');
            }
        });
    }

    // Add hover functionality for ingredient hierarchy
    setupIngredientHover(card, recipe);
    if (showSimilar && recipe.id) {
        loadSimilarCocktails(card, recipe.id);
    }

    if (linkCard && recipe.id) {
        card.addEventListener('click', (event) => {
            if (event.defaultPrevented) {
                return;
            }
            const interactiveTarget = event.target.closest(
                'a, button, input, textarea, select, .tag-chip',
            );
            if (interactiveTarget) {
                return;
            }
            window.location.href = `/recipe/${recipe.id}`;
        });
    }

    return card;
}

async function loadSimilarCocktails(card, recipeId) {
    const container = card.querySelector('.similar-cocktails');
    if (!container) {
        return;
    }

    try {
        const similar = await api.getRecipeSimilar(recipeId);
        const neighbors = similar && Array.isArray(similar.neighbors) ? similar.neighbors : [];

        if (neighbors.length === 0) {
            container.remove();
            return;
        }

        const listItems = neighbors
            .map((neighbor) => {
                const distance =
                    typeof neighbor.distance === 'number'
                        ? neighbor.distance.toFixed(3)
                        : String(neighbor.distance);
                const transportPairs = Array.isArray(neighbor.transport_plan)
                    ? neighbor.transport_plan.slice(0, 3).map((plan) => {
                          const from = plan.from_ingredient_name ?? plan.from_ingredient_id;
                          const to = plan.to_ingredient_name ?? plan.to_ingredient_id;
                          return `${from} → ${to}`;
                      })
                    : [];
                const transportText =
                    transportPairs.length > 0 ? ` — ${transportPairs.join('; ')}` : '';
                return `
                <li>
                    <span class="similar-distance">${distance}</span>
                    <a href="/recipe/${neighbor.neighbor_recipe_id}">${neighbor.neighbor_name}</a>
                    ${transportText ? `<span class="similar-transport">${transportText}</span>` : ''}
                </li>
            `;
            })
            .join('');

        container.innerHTML = `
            <h5>Similar Cocktails</h5>
            <ul class="similar-list">
                ${listItems}
            </ul>
        `;
    } catch (error) {
        if (!error || !error.message || !error.message.includes('Resource not found')) {
            console.error('Error loading similar cocktails:', error);
        }
        container.remove();
    }
}

/**
 * Submit a rating for a recipe
 * @param {number} recipeId - The recipe ID
 * @param {number} rating - The rating value (1-5)
 */
async function submitRating(recipeId, rating) {
    try {
        // Check authentication
        if (!isAuthenticated()) {
            alert('Please log in to rate recipes.');
            return;
        }

        // Get user info
        const userInfo = getUserInfo();
        if (!userInfo || !userInfo.cognitoUserId) {
            console.error('Unable to get user information');
            return;
        }

        // Submit the rating with required fields
        const ratingData = {
            rating: rating,
            comment: '', // Optional comment field
        };

        const response = await api.setRating(recipeId, ratingData);

        // Show success notification
        const container = document.querySelector(`.star-rating[data-recipe-id="${recipeId}"]`);
        if (container) {
            const notification = document.createElement('span');
            notification.className = 'rating-notification';
            notification.textContent = 'Rating saved!';
            container.appendChild(notification);

            // Remove notification after animation
            setTimeout(() => {
                notification.remove();
            }, 2500);
        }

        // Refresh the recipe to show updated average rating
        refreshRecipeAfterRating(recipeId, response);
    } catch (error) {
        console.error('Error submitting rating:', error);
        alert(`Failed to submit rating: ${error.message || 'Please try again.'}`);
    }
}

/**
 * Refresh a recipe card after a rating is submitted
 * @param {number} recipeId - The recipe ID
 * @param {Object} ratingResponse - The API response from submitting the rating
 */
async function refreshRecipeAfterRating(recipeId, ratingResponse) {
    try {
        // Fetch the latest recipe data to get updated avg_rating
        const recipe = await api.getRecipe(recipeId);

        // Find the recipe card using the data-id attribute
        const recipeCard = document.querySelector(`.recipe-card[data-id="${recipeId}"]`);
        if (!recipeCard) {
            return;
        }

        // Re-render just the rating component
        const ratingContainer = recipeCard.querySelector(`#rating-container-${recipeId}`);
        if (ratingContainer) {
            recipe.user_rating = ratingResponse?.rating || 0;
            ratingContainer.innerHTML = '';
            renderRecipeRating(ratingContainer, recipe, {
                authenticated: true,
                createInteractiveStars,
                generateStarRating,
                onRate: async (rating) => submitRating(recipeId, rating),
            });
        }
    } catch (error) {
        console.error('Error refreshing recipe after rating:', error);
    }
}

/**
 * Displays recipes in the specified container
 * @param {Array} recipes - Array of recipe objects
 * @param {HTMLElement} container - Container element to display recipes in
 * @param {boolean} showActions - Whether to show edit/delete buttons
 * @param {Function} onRecipeDeleted - Callback when recipe is deleted
 */
export function displayRecipes(
    recipes,
    container,
    showActions = true,
    onRecipeDeleted = null,
    options = {},
) {
    container.innerHTML = '';

    if (!recipes || recipes.length === 0) {
        container.innerHTML = '<p>No recipes found.</p>';
        return;
    }

    recipes.forEach((recipe) => {
        const card = createRecipeCard(recipe, showActions, onRecipeDeleted, options);
        container.appendChild(card);
    });
}

// --- Tag Editor Modal Logic (extracted to components/recipeTagEditor.js) ---

function updateRecipeCardTags(recipeId, tags) {
    const recipeCard = document.querySelector(`.recipe-card[data-id="${recipeId}"]`);
    if (!recipeCard) return;
    const tagsContainer = recipeCard.querySelector('.recipe-tags .tags-container');
    const noTagsPlaceholder = recipeCard.querySelector('.recipe-tags .no-tags-placeholder');
    const addTagButton = recipeCard.querySelector('.add-tag-btn');
    const { publicTags, privateTags, hasAnyTags } = splitRecipeTags(tags);
    if (tagsContainer) {
        tagsContainer.innerHTML =
            generateTagChips(publicTags, {
                recipeId,
                shouldShowActions: isAuthenticated(),
            }) +
            generateTagChips(privateTags, {
                recipeId,
                shouldShowActions: isAuthenticated(),
            });
        updateTagVisibility(tagsContainer, noTagsPlaceholder, hasAnyTags);
    }
    if (addTagButton) addTagButton.dataset.recipeTags = JSON.stringify(tags);
}

initializeRecipeTagEditor({
    api,
    isAuthenticated,
    onTagsUpdated: updateRecipeCardTags,
});

// Tag removal remains delegated so dynamically refreshed cards behave consistently.
document.addEventListener('click', async (event) => {
    const removeTagButton = event.target.closest('.tag-remove-btn');
    if (!removeTagButton) return;
    event.preventDefault();
    event.stopPropagation();
    const recipeId = parseInt(removeTagButton.dataset.recipeId);
    const tagId = parseInt(removeTagButton.dataset.tagId);
    const tagType = removeTagButton.dataset.tagType;
    const tagName = removeTagButton.parentElement.textContent.replace('×', '').trim();
    if (Number.isNaN(recipeId) || Number.isNaN(tagId)) {
        alert('Invalid recipe or tag ID. Please refresh the page and try again.');
        return;
    }
    if (!confirm(`Remove "${tagName}" from this recipe?`)) return;
    try {
        removeTagButton.disabled = true;
        removeTagButton.textContent = '...';
        const response = await api.removeTagFromRecipe(recipeId, tagId, tagType);
        if (response.success === false) throw new Error(response.error || 'Failed to remove tag');
        const recipeCard = removeTagButton.closest('.recipe-card');
        const tagsContainer = recipeCard?.querySelector('.tags-container');
        const noTagsPlaceholder = recipeCard?.querySelector('.no-tags-placeholder');
        removeTagButton.parentElement.remove();
        if (tagsContainer)
            updateTagVisibility(
                tagsContainer,
                noTagsPlaceholder,
                tagsContainer.children.length > 0,
            );
    } catch (error) {
        console.error('Error removing tag:', error);
        alert(`Failed to remove tag: ${error.message}`);
        removeTagButton.disabled = false;
        removeTagButton.textContent = '×';
    }
});

/**
 * Deletes a recipe by ID
 * @param {number} id - Recipe ID to delete
 * @param {Function} onRecipeDeleted - Callback after deletion
 */
async function deleteRecipe(id, onRecipeDeleted = null) {
    // Check editor permissions first
    if (!api.isEditor()) {
        alert('Editor access required. Only editors and admins can delete recipes.');
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

/**
 * Sets up ingredient hierarchy hover functionality for a recipe card
 * @param {HTMLElement} card - The recipe card element
 * @param {Object} recipe - The recipe object containing ingredient data
 */
function setupIngredientHover(card, recipe) {
    const ingredientElements = card.querySelectorAll('.ingredient-name');
    let currentTooltip = null;

    ingredientElements.forEach((ingredientElement, index) => {
        const ingredient = recipe.ingredients[index];
        if (!ingredient) return;

        // Get hierarchy from ingredient data (no API call needed!)
        const hierarchy = ingredient.hierarchy;

        // Skip ingredients without hierarchy (single-level)
        if (!hierarchy || hierarchy.length <= 1) {
            return;
        }

        // Add visual indication that ingredient has hierarchy.
        ingredientElement.classList.add('has-hierarchy');

        ingredientElement.addEventListener('mouseenter', () => {
            // Remove any existing tooltip
            if (currentTooltip) {
                currentTooltip.remove();
                currentTooltip = null;
            }

            // Create hierarchy display (root to leaf)
            const hierarchyText = hierarchy.join(' → ');

            // Create tooltip
            currentTooltip = document.createElement('div');
            currentTooltip.className = 'ingredient-hierarchy-tooltip';
            currentTooltip.textContent = hierarchyText;

            // Position tooltip
            const rect = ingredientElement.getBoundingClientRect();
            currentTooltip.style.left = `${rect.left + window.scrollX}px`;
            currentTooltip.style.top = `${rect.bottom + window.scrollY + 5}px`;

            document.body.appendChild(currentTooltip);

            // Adjust position if tooltip goes off screen
            const tooltipRect = currentTooltip.getBoundingClientRect();
            if (tooltipRect.right > window.innerWidth) {
                currentTooltip.style.left = `${window.innerWidth - tooltipRect.width - 10 + window.scrollX}px`;
            }
            if (tooltipRect.bottom > window.innerHeight) {
                currentTooltip.style.top = `${rect.top + window.scrollY - tooltipRect.height - 5}px`;
            }
        });

        ingredientElement.addEventListener('mouseleave', () => {
            if (currentTooltip) {
                currentTooltip.remove();
                currentTooltip = null;
            }
        });
    });
}
