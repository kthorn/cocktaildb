// Recipe card component for displaying cocktail recipes
import { api } from './api.js';
import { isAuthenticated, getUserInfo } from './auth.js';
import { generateStarRating, createInteractiveRating } from './common.js';

/**
 * Formats a number into a string, converting decimals to common fractions if close.
 * @param {number} amount - The numeric amount to format
 * @returns {string} The formatted amount string
 */
function formatAmount(amount) {
    if (typeof amount !== 'number' || isNaN(amount)) {
        return String(amount); // Return as string if not a valid number
    }

    const tolerance = 0.01;
    const integerPart = Math.floor(amount);
    const fractionalPart = amount - integerPart;

    if (fractionalPart < tolerance) {
        return String(integerPart); // Whole number
    }

    const fractions = {
        '1/8': 1/8, '1/4': 1/4, '1/3': 1/3, '3/8': 3/8, '1/2': 1/2, 
        '5/8': 5/8, '2/3': 2/3, '3/4': 3/4, '7/8': 7/8
    };

    let bestMatch = null;
    let minDiff = tolerance;

    for (const [fractionStr, fractionVal] of Object.entries(fractions)) {
        const diff = Math.abs(fractionalPart - fractionVal);
        if (diff < minDiff) {
            minDiff = diff;
            bestMatch = fractionStr;
        }
    }
    
    // Check if the remainder is close to 1 (e.g. 0.995 should be next integer)
    if (1 - fractionalPart < tolerance) {
        return String(integerPart + 1);
    }

    if (bestMatch) {
        if (integerPart > 0) {
            return `${integerPart} ${bestMatch}`; // Mixed number
        } else {
            return bestMatch; // Just the fraction
        }
    } else {
        // Fallback: Round to 2 decimal places if no close fraction found
        return amount.toFixed(2).replace(/\.?0+$/, ''); // Remove trailing zeros
    }
}

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
    card.dataset.id = recipe.id; // Add recipe ID to card for easier refresh
    
    // Only show action buttons if user is authenticated and showActions is true
    const shouldShowActions = showActions && isAuthenticated();
    
    const tagsExist = recipe.tags && recipe.tags.length > 0;
    const tagsHTML = tagsExist
        ? `<span class="existing-tags">${recipe.tags.join(', ')}</span>`
        : '<span class="no-tags-placeholder">No tags yet</span>';
    
    // Start with the basic recipe details
    card.innerHTML = `
        <h4 class="recipe-title">${recipe.name}</h4>
        <div class="recipe-meta">
            <div class="recipe-tags">
                ${tagsHTML}
                <button class="add-tag-btn" 
                        data-recipe-id="${recipe.id}" 
                        data-recipe-name="${encodeURIComponent(recipe.name)}" 
                        data-recipe-tags='${JSON.stringify(recipe.tags || [])}' 
                        title="Add or edit tags">(+) Tag</button>
            </div>
            <div id="rating-container-${recipe.id}" class="recipe-rating"></div>
        </div>
        <p>${recipe.description || 'No description'}</p>
        <div class="ingredients">
            <h5>Ingredients</h5>
            <ul>
                ${recipe.ingredients.map(ing => {
                    // Format with proper spaces between amount, unit and ingredient name
                    const unitDisplay = ing.unit_name ? `${ing.unit_name} ` : '';
                    
                    // Try multiple possible property names for ingredient full name
                    const ingredientName = ing.full_name || ing.ingredient_name || ing.name || 'Unknown ingredient';
                    
                    return `<li>${formatAmount(ing.amount)} ${unitDisplay}${ingredientName}</li>`;
                }).join('')}
            </ul>
        </div>
        <div class="instructions">
            <h5>Instructions</h5>
            <p>${recipe.instructions}</p>
        </div>
        ${recipe.source ? `
        <div class="recipe-source">
            <h5>Source</h5>
            <p>${recipe.source_url ? `<a href="${recipe.source_url}" target="_blank" rel="noopener noreferrer">${recipe.source}</a>` : recipe.source}</p>
        </div>
        ` : ''}
        ${shouldShowActions ? `
        <div class="card-actions">
            <button class="edit-recipe" data-id="${recipe.id}">Edit</button>
            <button class="delete-recipe" data-id="${recipe.id}">Delete</button>
        </div>
        ` : ''}
    `;

    // Add rating component
    const ratingContainer = card.querySelector(`#rating-container-${recipe.id}`);
    if (ratingContainer) {
        if (isAuthenticated()) {
            // Add interactive rating for logged in users
            // First, check if user has already rated this recipe
            try {
                fetchUserRating(recipe.id).then(userRating => {
                    const interactiveRating = createInteractiveRating(
                        recipe.id,
                        userRating ? userRating.rating : 0,
                        recipe.avg_rating || 0,
                        recipe.rating_count || 0,
                        submitRating
                    );
                    ratingContainer.appendChild(interactiveRating);
                }).catch(error => {
                    // Fallback to just showing the average if there's an error
                    console.error('Error fetching user rating:', error);
                    const staticRating = generateStarRating(recipe.avg_rating || 0, recipe.rating_count || 0);
                    ratingContainer.innerHTML = staticRating;
                });
            } catch (error) {
                console.error('Error setting up rating component:', error);
                const staticRating = generateStarRating(recipe.avg_rating || 0, recipe.rating_count || 0);
                ratingContainer.innerHTML = staticRating;
            }
        } else {
            // Show static rating for non-logged in users
            const staticRating = generateStarRating(recipe.avg_rating || 0, recipe.rating_count || 0);
            ratingContainer.innerHTML = staticRating;
        }
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
 * Fetch the user's rating for a recipe
 * @param {number} recipeId - The recipe ID
 * @returns {Promise<Object|null>} The user's rating or null if not rated
 */
async function fetchUserRating(recipeId) {
    try {
        console.log(`Fetching ratings for recipe ID: ${recipeId}`);
        const ratings = await api.getRatings(recipeId);
        console.log(`Received ratings:`, ratings);
        
        const userInfo = getUserInfo();
        console.log(`User info:`, userInfo);
        
        if (!userInfo || !userInfo.token || !userInfo.cognitoUserId) {
            console.log('No valid user info found, cannot fetch rating');
            return null;
        }
        
        // If ratings is empty or not an array, return null
        if (!ratings || !Array.isArray(ratings) || ratings.length === 0) {
            console.log('No ratings found for this recipe');
            return null;
        }
        
        // Find the rating by this user
        const userRating = ratings.find(r => r.cognito_user_id === userInfo.cognitoUserId);
        console.log(`User rating found:`, userRating || 'None');
        return userRating || null;
    } catch (error) {
        console.error('Error fetching user rating:', error);
        return null;
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
            comment: '' // Optional comment field
        };
        
        console.log(`Submitting rating ${rating} for recipe ${recipeId}`);
        const response = await api.setRating(recipeId, ratingData);
        console.log('Rating submitted successfully:', response);
        
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
            console.log(`Recipe card for ID ${recipeId} not found for refresh`);
            return;
        }
        
        // Re-render just the rating component
        const ratingContainer = recipeCard.querySelector(`#rating-container-${recipeId}`);
        if (ratingContainer) {
            // Use the submitted rating as the user's current rating
            const interactiveRating = createInteractiveRating(
                recipeId,
                ratingResponse?.rating || 0,
                recipe.avg_rating || 0,
                recipe.rating_count || 0,
                submitRating
            );
            
            // Clear and replace
            ratingContainer.innerHTML = '';
            ratingContainer.appendChild(interactiveRating);
        }
        
        console.log(`Recipe ${recipeId} refreshed with new rating data`);
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

// --- Tag Editor Modal Logic (Moved from recipes.js) ---
let tagEditorModalElement = null;
let tagEditorRecipeNameEl = null;
let tagEditorRecipeIdInput = null;
let tagInputEl = null;
let tagChipsContainerEl = null;
let saveTagsBtnEl = null;
let cancelTagsBtnEl = null;
let closeTagModalBtnEl = null;

let currentRecipeTags = [];
let originalRecipeTagsForEdit = [];

const modalHtml = `
    <div id="tag-editor-modal" class="modal" style="display:none;">
        <div class="modal-content">
            <span class="close-tag-modal-btn">&times;</span>
            <h3>Edit Tags for <span id="tag-editor-recipe-name">Recipe</span></h3>
            <input type="hidden" id="tag-editor-recipe-id">
            <div class="form-group">
                <label for="tag-input">Add tags (comma-separated):</label>
                <input type="text" id="tag-input" placeholder="e.g., easy, quick, my favorite">
                <small>Default: Public (&#x1F30D;). Click a tag chip to toggle its privacy (&#x1F512;). Type a new tag and press Enter or comma.</small>
            </div>
            <div id="tag-chips-container" class="tag-chips-container">
                <!-- Tag chips will be dynamically added here -->
            </div>
            <div class="form-actions">
                <button id="save-tags-btn" class="btn-primary">Save</button>
                <button id="cancel-tags-btn" class="btn-secondary">Cancel</button>
            </div>
        </div>
    </div>
`;

function ensureTagModal() {
    if (!document.getElementById('tag-editor-modal')) {
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        tagEditorModalElement = document.getElementById('tag-editor-modal');
        tagEditorRecipeNameEl = document.getElementById('tag-editor-recipe-name');
        tagEditorRecipeIdInput = document.getElementById('tag-editor-recipe-id');
        tagInputEl = document.getElementById('tag-input');
        tagChipsContainerEl = document.getElementById('tag-chips-container');
        saveTagsBtnEl = document.getElementById('save-tags-btn');
        cancelTagsBtnEl = document.getElementById('cancel-tags-btn');
        closeTagModalBtnEl = tagEditorModalElement.querySelector('.close-tag-modal-btn');

        // Attach internal modal event listeners
        closeTagModalBtnEl.addEventListener('click', closeTagEditorModal);
        cancelTagsBtnEl.addEventListener('click', closeTagEditorModal);
        saveTagsBtnEl.addEventListener('click', handleSaveTags);

        tagInputEl.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                const tags = tagInputEl.value.split(',').map(t => t.trim()).filter(t => t);
                tags.forEach(addTagToModal);
                tagInputEl.value = '';
            }
        });
        tagInputEl.addEventListener('blur', () => {
            const tags = tagInputEl.value.split(',').map(t => t.trim()).filter(t => t);
            if (tags.length > 0) {
                tags.forEach(addTagToModal);
                tagInputEl.value = '';
            }
        });
    }
}

function openTagEditorModal(recipeId, recipeName, currentTagsJson) {
    ensureTagModal(); // Ensure modal exists and listeners are attached

    console.log('openTagEditorModal called with:', { recipeId, recipeName, currentTagsJson });

    tagEditorRecipeIdInput.value = recipeId;
    tagEditorRecipeNameEl.textContent = decodeURIComponent(recipeName);
    try {
        const parsedTags = JSON.parse(currentTagsJson || '[]');
        currentRecipeTags = parsedTags.map(tag => {
            if (typeof tag === 'string') return { name: tag, type: 'public', id: undefined };
            return { id: tag.id, name: tag.name, type: tag.type || 'public' };
        });
        originalRecipeTagsForEdit = JSON.parse(JSON.stringify(currentRecipeTags));
    } catch (e) {
        console.error('Error parsing current tags:', e);
        currentRecipeTags = [];
        originalRecipeTagsForEdit = [];
    }
    renderTagChipsInModal();
    tagInputEl.value = '';
    tagEditorModalElement.style.display = 'block';
    tagInputEl.focus();
}

function closeTagEditorModal() {
    if (tagEditorModalElement) {
        tagEditorModalElement.style.display = 'none';
    }
    currentRecipeTags = [];
    originalRecipeTagsForEdit = [];
    if (tagInputEl) {
        tagInputEl.value = '';
    }
}

function renderTagChipsInModal() {
    if (!tagChipsContainerEl) return;
    tagChipsContainerEl.innerHTML = '';
    currentRecipeTags.forEach((tag, index) => {
        const chip = document.createElement('div');
        chip.classList.add('tag-chip', tag.type === 'private' ? 'tag-chip-private' : 'tag-chip-public');
        chip.dataset.index = index;
        chip.innerHTML = `
            <span class="tag-icon">${tag.type === 'private' ? '&#x1F512;' : '&#x1F30D;'}</span>
            <span class="tag-name">${tag.name}</span>
            <button class="remove-tag-chip-btn" title="Remove tag">&times;</button>
        `;
        chip.addEventListener('click', (e) => {
            if (!e.target.classList.contains('remove-tag-chip-btn')) {
                toggleTagPrivacy(index);
            }
        });
        chip.querySelector('.remove-tag-chip-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            removeTagFromModal(index);
        });
        tagChipsContainerEl.appendChild(chip);
    });
}

function addTagToModal(tagName) {
    const trimmedName = tagName.trim();
    if (trimmedName && !currentRecipeTags.some(t => t.name.toLowerCase() === trimmedName.toLowerCase())) {
        currentRecipeTags.push({ name: trimmedName, type: 'public' });
        renderTagChipsInModal();
    }
}

function removeTagFromModal(index) {
    currentRecipeTags.splice(index, 1);
    renderTagChipsInModal();
}

function toggleTagPrivacy(index) {
    const tag = currentRecipeTags[index];
    if (tag) {
        tag.type = tag.type === 'public' ? 'private' : 'public';
        renderTagChipsInModal();
    }
}

async function handleSaveTags() {
    if (!saveTagsBtnEl || !tagEditorRecipeIdInput) return;

    const recipeId = tagEditorRecipeIdInput.value;
    const modalFinalTags = [...currentRecipeTags];

    saveTagsBtnEl.disabled = true;
    saveTagsBtnEl.textContent = 'Saving...';

    try {
        const tagsToActuallyRemove = [];
        const tagsToActuallyAdd = [];

        for (const originalTag of originalRecipeTagsForEdit) {
            const stillExistsWithSameType = modalFinalTags.some(finalTag =>
                finalTag.id === originalTag.id &&
                finalTag.name.toLowerCase() === originalTag.name.toLowerCase() &&
                finalTag.type === originalTag.type
            );
            if (!stillExistsWithSameType && originalTag.id) {
                tagsToActuallyRemove.push(originalTag);
            }
        }

        for (const finalTag of modalFinalTags) {
            const existedBeforeWithSameType = originalRecipeTagsForEdit.some(originalTag =>
                (finalTag.id && originalTag.id === finalTag.id ||
                 !finalTag.id && originalTag.name.toLowerCase() === finalTag.name.toLowerCase()) &&
                originalTag.type === finalTag.type
            );
            if (!existedBeforeWithSameType) {
                tagsToActuallyAdd.push(finalTag);
            }
        }

        for (const tag of tagsToActuallyRemove) {
            await api.removeTagFromRecipe(recipeId, tag.id, tag.type);
        }
        for (const tag of tagsToActuallyAdd) {
            await api.addTagToRecipe(recipeId, tag.name, tag.type);
        }

        // Update the specific recipe card UI
        const recipeCardElement = document.querySelector(`.recipe-card[data-id="${recipeId}"]`);
        if (recipeCardElement) {
            const tagsDisplay = recipeCardElement.querySelector('.recipe-tags .existing-tags');
            const noTagsPlaceholder = recipeCardElement.querySelector('.recipe-tags .no-tags-placeholder');
            const addTagButtonOnCard = recipeCardElement.querySelector('.add-tag-btn');

            const publicTagsForDisplay = modalFinalTags.filter(t => t.type === 'public').map(t => t.name);
            if (tagsDisplay) {
                tagsDisplay.textContent = publicTagsForDisplay.join(', ');
                tagsDisplay.style.display = publicTagsForDisplay.length > 0 ? 'inline' : 'none';
            }
            if (noTagsPlaceholder) {
                noTagsPlaceholder.style.display = publicTagsForDisplay.length > 0 ? 'none' : 'inline';
            }
            if (addTagButtonOnCard) {
                const updatedRecipeData = await api.getRecipe(recipeId);
                if (updatedRecipeData && updatedRecipeData.tags) {
                    addTagButtonOnCard.dataset.recipeTags = JSON.stringify(updatedRecipeData.tags);
                } else {
                    addTagButtonOnCard.dataset.recipeTags = JSON.stringify(modalFinalTags);
                }
            }
        }

        alert('Tags saved successfully!');
        closeTagEditorModal();
    } catch (error) {
        console.error('Error saving tags:', error);
        alert(`Failed to save tags: ${error.message || 'An unexpected error occurred.'}`);
    } finally {
        saveTagsBtnEl.disabled = false;
        saveTagsBtnEl.textContent = 'Save';
    }
}

// Delegated event listener for opening the tag editor modal
document.addEventListener('click', (e) => {
    const addTagButton = e.target.closest('.add-tag-btn');
    if (addTagButton) {
        const recipeId = addTagButton.dataset.recipeId;
        const recipeName = addTagButton.dataset.recipeName;
        const currentTagsJson = addTagButton.dataset.recipeTags;
        openTagEditorModal(recipeId, recipeName, currentTagsJson);
    }
});

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