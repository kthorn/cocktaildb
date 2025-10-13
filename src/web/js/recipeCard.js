// Recipe card component for displaying cocktail recipes
import { api } from './api.js';
import { isAuthenticated, getUserInfo } from './auth.js';
import { generateStarRating, createInteractiveStars } from './common.js';

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
    
    // Only show action buttons if user is an editor/admin and showActions is true
    const shouldShowActions = showActions && api.isEditor();
    const shouldShowAddTagButton = isAuthenticated(); // Check if user is authenticated for add tag button
    
    // Deduplicate tags by ID to handle any backend duplicates
    const uniqueTagsMap = new Map();
    if (recipe.tags && Array.isArray(recipe.tags)) {
        recipe.tags.forEach(tag => {
            if (tag && tag.id && tag.name && tag.name.trim() !== '') {
                uniqueTagsMap.set(tag.id, tag);
            }
        });
    }
    const deduplicatedTags = Array.from(uniqueTagsMap.values());
    
    const publicTags = deduplicatedTags.filter(tag => tag.type === 'public');
    const privateTags = deduplicatedTags.filter(tag => tag.type === 'private');
    const hasAnyTags = publicTags.length > 0 || privateTags.length > 0;
    
    // Helper function to generate tag chips
    function generateTagChips(tags, isPrivate = false) {
        return tags.map(tag => `
            <span class="tag-chip ${isPrivate ? 'tag-private' : 'tag-public'}" data-tag-id="${tag.id}" data-tag-type="${tag.type}">
                ${tag.name}
                ${shouldShowActions ? `<button class="tag-remove-btn" data-recipe-id="${recipe.id}" data-tag-id="${tag.id}" data-tag-type="${tag.type}" title="Remove from recipe">×</button>` : ''}
            </span>
        `).join('');
    }
    
    // Start with the basic recipe details
    card.innerHTML = `
        <h4 class="recipe-title">${recipe.name}</h4>
        <div class="recipe-meta">
            <div class="recipe-tags">
                <div class="tags-container" style="display: ${hasAnyTags ? 'inline' : 'none'};">
                    ${generateTagChips(publicTags, false)}
                    ${generateTagChips(privateTags, true)}
                </div>
                <span class="no-tags-placeholder" style="display: ${hasAnyTags ? 'none' : 'inline'};">No tags yet</span>
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
                        return `<li><span class="ingredient-name" data-ingredient-path="${ing.ingredient_path || ''}">${ingredientName}</span>, to top</li>`;
                    }
                    if (ing.unit_name === 'to rinse' && (ing.amount === null || ing.amount === undefined || ing.amount === 0)) {
                        return `<li><span class="ingredient-name" data-ingredient-path="${ing.ingredient_path || ''}">${ingredientName}</span>, to rinse</li>`;
                    }
                    if (ing.unit_name === 'each' || ing.unit_name === 'Each') {
                        // For 'each' unit, don't display the unit name
                        const formattedAmount = formatAmount(ing.amount);
                        return `<li>${formattedAmount ? formattedAmount + ' ' : ''}<span class="ingredient-name" data-ingredient-path="${ing.ingredient_path || ''}">${ingredientName}</span></li>`;
                    }
                    
                    // Default handling for all other units
                    const formattedAmount = formatAmount(ing.amount);
                    const unitDisplay = ing.unit_name ? ` ${ing.unit_name}` : '';
                    
                    return `<li>${formattedAmount}${unitDisplay} <span class="ingredient-name" data-ingredient-path="${ing.ingredient_path || ''}">${ingredientName}</span></li>`;
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
        <div class="card-actions">
            <button class="share-recipe-btn" data-recipe-name="${encodeURIComponent(recipe.name)}" title="Share recipe link" style="font-size: 0.8em; padding: 4px 8px;">🔗</button>
            ${shouldShowActions ? `
            <button class="edit-recipe" data-id="${recipe.id}">Edit</button>
            <button class="delete-recipe" data-id="${recipe.id}">Delete</button>
            ` : ''}
        </div>
    `;

    // Add rating component
    const ratingContainer = card.querySelector(`#rating-container-${recipe.id}`);
    if (ratingContainer) {
        if (isAuthenticated()) {
            // Create wrapper for interactive rating
            const wrapper = document.createElement('div');
            wrapper.className = 'star-rating interactive';
            wrapper.dataset.recipeId = recipe.id;
            
            // Add interactive rating for logged in users
            const starComponent = createInteractiveStars({
                initialRating: recipe.user_rating, // Use user_rating from the recipe object
                allowToggle: false,
                showDifferentStates: true,
                onClick: async (rating) => {
                    await submitRating(recipe.id, rating);
                }
            });
            wrapper.appendChild(starComponent);
            
            // Add user rating indicator
            const userIndicator = document.createElement('span');
            userIndicator.className = 'user-rating-indicator';
            const hasRating = recipe.user_rating !== null && recipe.user_rating !== undefined;
            const ratingValue = recipe.user_rating ?? 0;
            
            if (!hasRating) {
                userIndicator.textContent = ' (not rated)';
                userIndicator.style.color = '#999';
                userIndicator.style.fontSize = '0.8em';
            } else if (ratingValue === 0) {
                userIndicator.textContent = ' (0 stars)';
                userIndicator.style.color = '#666';
                userIndicator.style.fontSize = '0.8em';
            } else {
                userIndicator.textContent = ` (${ratingValue})`;
                userIndicator.style.color = '#666';
                userIndicator.style.fontSize = '0.8em';
            }
            wrapper.appendChild(userIndicator);
            
            // Add rating stats
            const stats = document.createElement('span');
            stats.className = 'rating-stats';
            stats.textContent = ` - Avg: ${(recipe.avg_rating || 0).toFixed(1)} (${recipe.rating_count || 0})`;
            wrapper.appendChild(stats);
            
            ratingContainer.appendChild(wrapper);
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

    // Add event listener for share button (always present)
    const shareBtn = card.querySelector('.share-recipe-btn');
    if (shareBtn) {
        shareBtn.addEventListener('click', async () => {
            await handleShareRecipe(recipe.name);
        });
    }

    // Add hover functionality for ingredient hierarchy
    setupIngredientHover(card, recipe);

    return card;
}

/**
 * Handle sharing a recipe by copying the search URL to clipboard
 * @param {string} recipeName - The name of the recipe to share
 */
async function handleShareRecipe(recipeName) {
    try {
        const shareUrl = `${window.location.origin}/recipe.html?name=${encodeURIComponent(recipeName)}`;

        // Try to copy to clipboard
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(shareUrl);
        } else {
            // Fallback for older browsers or non-HTTPS
            const textArea = document.createElement('textarea');
            textArea.value = shareUrl;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
        }

        // Show success feedback
        showShareFeedback('Recipe link copied to clipboard!');
    } catch (error) {
        console.error('Error copying to clipboard:', error);
        showShareFeedback('Failed to copy link. Please try again.');
    }
}

/**
 * Show temporary feedback message for share action
 * @param {string} message - The message to display
 */
function showShareFeedback(message) {
    // Create or update existing feedback element
    let feedback = document.getElementById('share-feedback');
    if (!feedback) {
        feedback = document.createElement('div');
        feedback.id = 'share-feedback';
        feedback.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 12px 16px;
            border-radius: 4px;
            z-index: 1000;
            font-size: 14px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            transition: opacity 0.3s ease;
        `;
        document.body.appendChild(feedback);
    }
    
    feedback.textContent = message;
    feedback.style.display = 'block';
    feedback.style.opacity = '1';
    
    // Hide after 2 seconds
    setTimeout(() => {
        feedback.style.opacity = '0';
        setTimeout(() => {
            feedback.style.display = 'none';
        }, 300);
    }, 2000);
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
            // Create wrapper for interactive rating
            const wrapper = document.createElement('div');
            wrapper.className = 'star-rating interactive';
            wrapper.dataset.recipeId = recipeId;
            
            // Create star component with submitted rating
            const starComponent = createInteractiveStars({
                initialRating: ratingResponse?.rating || 0,
                allowToggle: false,
                showDifferentStates: true,
                onClick: async (rating) => {
                    await submitRating(recipeId, rating);
                }
            });
            wrapper.appendChild(starComponent);
            
            // Add user rating indicator
            const userIndicator = document.createElement('span');
            userIndicator.className = 'user-rating-indicator';
            const submittedRating = ratingResponse?.rating || 0;
            
            if (submittedRating === 0) {
                userIndicator.textContent = ' (0 stars)';
                userIndicator.style.color = '#666';
                userIndicator.style.fontSize = '0.8em';
            } else {
                userIndicator.textContent = ` (${submittedRating})`;
                userIndicator.style.color = '#666';
                userIndicator.style.fontSize = '0.8em';
            }
            wrapper.appendChild(userIndicator);
            
            // Add rating stats
            const stats = document.createElement('span');
            stats.className = 'rating-stats';
            stats.textContent = ` - Avg: ${(recipe.avg_rating || 0).toFixed(1)} (${recipe.rating_count || 0})`;
            wrapper.appendChild(stats);
            
            // Clear and replace
            ratingContainer.innerHTML = '';
            ratingContainer.appendChild(wrapper);
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
            return { 
                id: tag.id ? parseInt(tag.id) : undefined, 
                name: tag.name, 
                type: tag.type || 'public' 
            };
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
            <button class="tag-remove-btn" title="Remove tag">&times;</button>
        `;
        chip.addEventListener('click', (e) => {
            if (!e.target.classList.contains('tag-remove-btn')) {
                toggleTagPrivacy(index);
            }
        });
        chip.querySelector('.tag-remove-btn').addEventListener('click', (e) => {
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
        console.log('Save tags process started');
        console.log('Original recipe tags:', originalRecipeTagsForEdit);
        console.log('Current recipe tags (in modal):', currentRecipeTags);
        
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

        console.log('Tags to remove:', tagsToActuallyRemove);
        console.log('Tags to add:', tagsToActuallyAdd);

        for (const tag of tagsToActuallyRemove) {
            // Ensure tag ID is a valid integer
            if (!tag.id || isNaN(parseInt(tag.id))) {
                console.error('Invalid tag ID for removal:', tag);
                continue;
            }
            console.log('Removing tag from recipe:', { recipeId, tag });
            const removeResult = await api.removeTagFromRecipe(recipeId, parseInt(tag.id), tag.type);
            console.log('Remove tag result:', removeResult);
        }
        // Deduplicate tags to add to prevent race conditions
        const uniqueTagsToAdd = [];
        const seenTags = new Set();
        
        for (const tag of tagsToActuallyAdd) {
            const tagKey = `${tag.name.toLowerCase()}-${tag.type}`;
            if (!seenTags.has(tagKey)) {
                seenTags.add(tagKey);
                uniqueTagsToAdd.push(tag);
            }
        }
        
        console.log('Original tags to add:', tagsToActuallyAdd);
        console.log('Deduplicated tags to add:', uniqueTagsToAdd);
        
        for (const tag of uniqueTagsToAdd) {
            console.log('Adding tag to recipe:', { recipeId, tag });
            const addResult = await api.addTagToRecipe(recipeId, tag.name, tag.type);
            console.log('Add tag result:', addResult);
        }

        // Update the specific recipe card UI with fresh data from API
        const recipeCardElement = document.querySelector(`.recipe-card[data-id="${recipeId}"]`);
        if (recipeCardElement) {
            const tagsContainer = recipeCardElement.querySelector('.recipe-tags .tags-container');
            const noTagsPlaceholder = recipeCardElement.querySelector('.recipe-tags .no-tags-placeholder');
            const addTagButtonOnCard = recipeCardElement.querySelector('.add-tag-btn');

            // Get fresh data from API to ensure consistency
            const updatedRecipeData = await api.getRecipe(recipeId);
            console.log('Fresh recipe data from API:', updatedRecipeData);
            
            // The API returns tags in the main 'tags' array, not separate public_tags/private_tags
            const freshTags = updatedRecipeData && updatedRecipeData.tags ? updatedRecipeData.tags : [];
            console.log('Fresh tags from API:', freshTags);
            
            // Log each tag structure for debugging
            freshTags.forEach((tag, index) => {
                console.log(`Tag ${index}:`, tag);
            });

            // Deduplicate tags by ID to handle any backend duplicates
            const uniqueTagsMap = new Map();
            freshTags.forEach(tag => {
                if (tag && tag.id && tag.name && tag.name.trim() !== '') {
                    uniqueTagsMap.set(tag.id, tag);
                }
            });
            const deduplicatedTags = Array.from(uniqueTagsMap.values());
            console.log('Deduplicated tags:', deduplicatedTags);

            // Separate public and private tags from deduplicated data
            const publicTags = deduplicatedTags.filter(t => t.type === 'public');
            const privateTags = deduplicatedTags.filter(t => t.type === 'private');
            
            console.log('Filtered public tags:', publicTags);
            console.log('Filtered private tags:', privateTags);
            const hasAnyTags = publicTags.length > 0 || privateTags.length > 0;

            if (tagsContainer) {
                // Helper function to generate tag chips (same as in createRecipeCard)
                const shouldShowActions = isAuthenticated(); // For tag removal buttons
                function generateTagChips(tags, isPrivate = false) {
                    return tags.map(tag => `
                        <span class="tag-chip ${isPrivate ? 'tag-private' : 'tag-public'}" data-tag-id="${tag.id}" data-tag-type="${tag.type}">
                            ${tag.name}
                            ${shouldShowActions ? `<button class="tag-remove-btn" data-recipe-id="${recipeId}" data-tag-id="${tag.id}" data-tag-type="${tag.type}" title="Remove from recipe">×</button>` : ''}
                        </span>
                    `).join('');
                }
                
                // Update the tags container with fresh data from API
                tagsContainer.innerHTML = generateTagChips(publicTags, false) + generateTagChips(privateTags, true);
                tagsContainer.style.display = hasAnyTags ? 'inline' : 'none';
            }
            if (noTagsPlaceholder) {
                noTagsPlaceholder.style.display = hasAnyTags ? 'none' : 'inline';
            }
            if (addTagButtonOnCard) {
                addTagButtonOnCard.dataset.recipeTags = JSON.stringify(freshTags);
            }
        }

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

// Delegated event listener for removing tags from recipes
document.addEventListener('click', async (e) => {
    const removeTagButton = e.target.closest('.tag-remove-btn');
    if (removeTagButton) {
        e.preventDefault();
        e.stopPropagation(); // Prevent triggering other click handlers
        
        const recipeId = parseInt(removeTagButton.dataset.recipeId);
        const tagId = parseInt(removeTagButton.dataset.tagId);
        const tagType = removeTagButton.dataset.tagType;
        const tagName = removeTagButton.parentElement.textContent.replace('×', '').trim();
        
        // Validate that we have valid integer IDs
        if (isNaN(recipeId) || isNaN(tagId)) {
            alert('Invalid recipe or tag ID. Please refresh the page and try again.');
            return;
        }
        
        // Confirm removal
        if (!confirm(`Remove "${tagName}" from this recipe?`)) {
            return;
        }
        
        try {
            removeTagButton.disabled = true;
            removeTagButton.textContent = '...';
            
            // Call the API to remove the tag from the recipe
            const response = await api.removeTagFromRecipe(recipeId, tagId, tagType);
            
            if (response.success !== false) {
                // Find elements before removing the tag chip
                const tagChip = removeTagButton.parentElement;
                const recipeCard = removeTagButton.closest('.recipe-card');
                const tagsContainer = recipeCard ? recipeCard.querySelector('.tags-container') : null;
                const noTagsPlaceholder = recipeCard ? recipeCard.querySelector('.no-tags-placeholder') : null;
                
                // Remove the tag chip from the UI
                tagChip.remove();
                
                if (tagsContainer && tagsContainer.children.length === 0) {
                    tagsContainer.style.display = 'none';
                    if (noTagsPlaceholder) {
                        noTagsPlaceholder.style.display = 'inline';
                    }
                }
                
                // Show success feedback
                console.log(`Tag "${tagName}" removed from recipe`);
            } else {
                throw new Error(response.error || 'Failed to remove tag');
            }
        } catch (error) {
            console.error('Error removing tag:', error);
            alert(`Failed to remove tag: ${error.message}`);
            
            // Restore button state
            removeTagButton.disabled = false;
            removeTagButton.textContent = '×';
        }
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

        // Set normal font weight
        ingredientElement.style.fontWeight = 'normal';

        // Get hierarchy from ingredient data (no API call needed!)
        const hierarchy = ingredient.hierarchy;

        // Skip ingredients without hierarchy (single-level)
        if (!hierarchy || hierarchy.length <= 1) {
            return;
        }

        // Add visual indication that ingredient has hierarchy
        ingredientElement.style.cursor = 'help';
        ingredientElement.style.textDecoration = 'underline';
        ingredientElement.style.textDecorationStyle = 'dotted';

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
            currentTooltip.style.cssText = `
                position: absolute;
                background: rgba(0, 0, 0, 0.9);
                color: white;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 12px;
                white-space: nowrap;
                z-index: 9999;
                pointer-events: none;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                max-width: 300px;
                word-wrap: break-word;
                white-space: normal;
            `;

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