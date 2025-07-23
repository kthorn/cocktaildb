// Recipe card component for displaying cocktail recipes
import { api } from './api.js';
import { isAuthenticated, getUserInfo } from './auth.js';
import { generateStarRating, createInteractiveRating } from './common.js';

/**
 * Formats a number into a string, converting decimals to common fractions if close.
 * @param {number|null|undefined} amount - The numeric amount to format
 * @returns {string} The formatted amount string, or empty string for null/undefined
 */
function formatAmount(amount) {
    if (amount === null || amount === undefined) {
        return ''; // Return empty string for null/undefined amounts
    }
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
    const shouldShowAddTagButton = isAuthenticated(); // Check if user is authenticated for add tag button
    
    const publicTags = recipe.tags && Array.isArray(recipe.tags) ? recipe.tags.filter(tag => tag.type === 'public') : [];
    const publicTagNames = (publicTags || []).map(tag => tag.name);
    const hasPublicTags = publicTagNames.length > 0;
    
    // Start with the basic recipe details
    card.innerHTML = `
        <h4 class="recipe-title">${recipe.name}</h4>
        <div class="recipe-meta">
            <div class="recipe-tags">
                <span class="existing-tags" style="display: ${hasPublicTags ? 'inline' : 'none'};">${publicTagNames.join(', ')}</span>
                <span class="no-tags-placeholder" style="display: ${hasPublicTags ? 'none' : 'inline'};">No tags yet</span>
                ${shouldShowAddTagButton ? `
                <button class="add-tag-btn" 
                        data-recipe-id="${recipe.id}" 
                        data-recipe-name="${encodeURIComponent(recipe.name)}" 
                        data-recipe-tags='${JSON.stringify(recipe.tags || [])}' 
                        title="Add or edit tags">(+) Tag</button>
                ` : ''}
            </div>
            <div id="rating-container-${recipe.id}" class="recipe-rating"></div>
        </div>
        <p>${recipe.description || 'No description'}</p>
        <div class="ingredients">
            <h5>Ingredients</h5>
            <ul>
                ${(recipe.ingredients || []).map(ing => {
                    // Try multiple possible property names for ingredient full name
                    const ingredientName = ing.full_name || ing.ingredient_name || ing.name || 'Unknown ingredient';
                    
                    // Special handling for specific units
                    if (ing.unit_name === 'to top' && (ing.amount === null || ing.amount === undefined || ing.amount === 0)) {
                        return `<li>${ingredientName}, to top</li>`;
                    }
                    if (ing.unit_name === 'to rinse' && (ing.amount === null || ing.amount === undefined || ing.amount === 0)) {
                        return `<li>${ingredientName}, to rinse</li>`;
                    }
                    if (ing.unit_name === 'each' || ing.unit_name === 'Each') {
                        // For 'each' unit, don't display the unit name
                        const formattedAmount = formatAmount(ing.amount);
                        return `<li>${formattedAmount ? formattedAmount + ' ' : ''}${ingredientName}</li>`;
                    }
                    
                    // Default handling for all other units
                    const formattedAmount = formatAmount(ing.amount);
                    const unitDisplay = ing.unit_name ? ` ${ing.unit_name}` : '';
                    
                    return `<li>${formattedAmount}${unitDisplay} ${ingredientName}</li>`;
                }).join('')}
            </ul>
        </div>
        <div class="instructions">
            <h5>Instructions</h5>
            <p>${recipe.instructions}</p>
        </div>
        ${recipe.source || recipe.source_url ? `
        <div class="recipe-source">
            <h5>Source</h5>
            <p>${recipe.source_url ? `<a href="${recipe.source_url}" target="_blank" rel="noopener noreferrer">${recipe.source || recipe.source_url}</a>` : recipe.source}</p>
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
            // The recipe object now directly contains user_rating if available
            const interactiveRating = createInteractiveRating(
                recipe.id,
                recipe.user_rating, // Use user_rating from the recipe object (don't default to 0)
                recipe.avg_rating || 0,
                recipe.rating_count || 0,
                submitRating
            );
            ratingContainer.appendChild(interactiveRating);
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
                // Navigate to recipes page with edit parameter
                window.location.href = `recipes.html?edit=${recipe.id}`;
            });
        }
    }

    return card;
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

/**
 * Appends recipe cards to the specified container (for progressive loading)
 * @param {Array} recipes - Array of recipe objects to append
 * @param {HTMLElement} container - Container element to append recipes to
 * @param {boolean} showActions - Whether to show edit/delete buttons
 * @param {Function} onRecipeDeleted - Callback when recipe is deleted
 */
export function appendRecipes(recipes, container, showActions = true, onRecipeDeleted = null) {
    if (!recipes || recipes.length === 0) {
        return;
    }

    recipes.forEach(recipe => {
        const card = createRecipeCard(recipe, showActions, onRecipeDeleted);
        container.appendChild(card);
    });
}

/**
 * Sets up progressive recipe loading for a container
 * @param {HTMLElement} container - Container element to display recipes in
 * @param {boolean} showActions - Whether to show edit/delete buttons
 * @param {Function} onRecipeDeleted - Callback when recipe is deleted
 * @returns {Object} Progressive loading controller with methods
 */
export function createProgressiveRecipeLoader(container, showActions = true, onRecipeDeleted = null) {
    let hasStarted = false;
    
    return {
        // Initialize the container (clear existing content, show loading state)
        start: () => {
            if (!hasStarted) {
                container.innerHTML = '<p class="loading-recipes">Loading recipes...</p>';
                hasStarted = true;
            }
        },
        
        // Add a batch of recipes to the container
        addBatch: (recipes) => {
            if (!hasStarted) {
                return;
            }
            
            // Remove loading message on first batch
            const loadingMsg = container.querySelector('.loading-recipes');
            if (loadingMsg) {
                loadingMsg.remove();
            }
            
            appendRecipes(recipes, container, showActions, onRecipeDeleted);
        },
        
        // Finish loading (handle empty results)
        finish: (totalCount = 0) => {
            const loadingMsg = container.querySelector('.loading-recipes');
            if (loadingMsg) {
                loadingMsg.remove();
            }
            
            if (totalCount === 0) {
                container.innerHTML = '<p>No recipes found.</p>';
            }
        }
    };
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
let publicTagsListEl = null;
let privateTagsListEl = null;

let currentRecipeTags = [];
let originalRecipeTagsForEdit = [];

const modalHtml = `
    <div id="tag-editor-modal" class="modal" style="display:none;">
        <div class="modal-content">
            <span class="close-tag-modal-btn">&times;</span>
            <h3>Edit Tags for <span id="tag-editor-recipe-name">Recipe</span></h3>
            <input type="hidden" id="tag-editor-recipe-id">
            
            <div class="form-group">
                <label>Select from existing tags:</label>
                <div id="existing-tags-section">
                    <div id="public-tags-section">
                        <h5>&#x1F30D; Public Tags</h5>
                        <div id="public-tags-list" class="existing-tags-list">
                            <!-- Public tags will be loaded here -->
                        </div>
                    </div>
                    <div id="private-tags-section">
                        <h5>&#x1F512; Private Tags</h5>
                        <div id="private-tags-list" class="existing-tags-list">
                            <!-- Private tags will be loaded here -->
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="form-group">
                <label for="tag-input">Or create new tags (comma-separated):</label>
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
        publicTagsListEl = document.getElementById('public-tags-list');
        privateTagsListEl = document.getElementById('private-tags-list');

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

async function loadExistingTags() {
    try {
        // Load public tags
        const publicTags = await api.getPublicTags();
        displayExistingTags(publicTags, publicTagsListEl, 'public');
        
        // Load private tags if user is authenticated
        if (isAuthenticated()) {
            const privateTags = await api.getPrivateTags();
            displayExistingTags(privateTags, privateTagsListEl, 'private');
        } else {
            privateTagsListEl.innerHTML = '<p class="auth-required">Login required to view private tags</p>';
        }
    } catch (error) {
        console.error('Error loading existing tags:', error);
        publicTagsListEl.innerHTML = '<p class="error">Error loading public tags</p>';
        privateTagsListEl.innerHTML = '<p class="error">Error loading private tags</p>';
    }
}

function displayExistingTags(tags, containerEl, tagType) {
    if (!tags || tags.length === 0) {
        containerEl.innerHTML = `<p class="no-tags">No ${tagType} tags available</p>`;
        return;
    }
    
    containerEl.innerHTML = '';
    tags.forEach(tag => {
        const tagElement = document.createElement('button');
        tagElement.className = 'existing-tag-btn';
        tagElement.dataset.tagName = tag.name;
        tagElement.dataset.tagType = tagType;
        tagElement.innerHTML = `
            <span class="tag-icon">${tagType === 'private' ? '&#x1F512;' : '&#x1F30D;'}</span>
            <span class="tag-name">${tag.name}</span>
        `;
        
        // Check if tag is already added to current recipe
        const isAlreadyAdded = currentRecipeTags.some(t => 
            t.name.toLowerCase() === tag.name.toLowerCase() && t.type === tagType
        );
        
        if (isAlreadyAdded) {
            tagElement.classList.add('tag-already-added');
            tagElement.disabled = true;
        } else {
            tagElement.addEventListener('click', () => {
                addTagToModal(tag.name, tagType);
                tagElement.classList.add('tag-already-added');
                tagElement.disabled = true;
            });
        }
        
        containerEl.appendChild(tagElement);
    });
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
    
    // Load existing tags for selection
    loadExistingTags();
    
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

function addTagToModal(tagName, tagType = 'public') {
    const trimmedName = tagName.trim();
    if (trimmedName && !currentRecipeTags.some(t => t.name.toLowerCase() === trimmedName.toLowerCase() && t.type === tagType)) {
        currentRecipeTags.push({ name: trimmedName, type: tagType });
        renderTagChipsInModal();
        // Refresh existing tags display to show updated state
        refreshExistingTagsDisplay();
    }
}

function removeTagFromModal(index) {
    currentRecipeTags.splice(index, 1);
    renderTagChipsInModal();
    // Refresh existing tags display to show updated state
    refreshExistingTagsDisplay();
}

function refreshExistingTagsDisplay() {
    // Re-enable buttons for tags that are no longer in currentRecipeTags
    const existingTagBtns = document.querySelectorAll('.existing-tag-btn');
    existingTagBtns.forEach(btn => {
        const tagName = btn.dataset.tagName;
        const tagType = btn.dataset.tagType;
        const isCurrentlyAdded = currentRecipeTags.some(t => 
            t.name.toLowerCase() === tagName.toLowerCase() && t.type === tagType
        );
        
        if (isCurrentlyAdded) {
            btn.classList.add('tag-already-added');
            btn.disabled = true;
        } else {
            btn.classList.remove('tag-already-added');
            btn.disabled = false;
        }
    });
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

            // Filter for public tags and ensure names are usable
            const namesToDisplay = modalFinalTags
                .filter(t => t.type === 'public' && t.name && t.name.trim() !== '')
                .map(t => t.name.trim());

            if (tagsDisplay) {
                tagsDisplay.textContent = namesToDisplay.join(', ');
                tagsDisplay.style.display = namesToDisplay.length > 0 ? 'inline' : 'none';
            }
            if (noTagsPlaceholder) {
                noTagsPlaceholder.style.display = namesToDisplay.length > 0 ? 'none' : 'inline';
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