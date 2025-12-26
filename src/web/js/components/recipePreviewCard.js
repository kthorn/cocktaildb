/**
 * Recipe Preview Card Component
 *
 * Displays a lightweight preview of a recipe on hover, showing recipe name
 * and ingredient list. Designed for use in the Cocktail Space visualization.
 */

// Configuration constants
const MAX_PREVIEW_INGREDIENTS = 6;
const HOVER_DELAY_MS = 250;
const PREVIEW_OFFSET_X = 15;
const PREVIEW_OFFSET_Y = 15;

/**
 * Creates and manages a recipe preview card
 * @param {HTMLElement} container - Container element for the preview
 * @returns {Object} Preview card controller
 */
export function createRecipePreviewCard(container) {
    let previewElement = null;
    let hoverTimer = null;
    let currentRecipe = null;

    /**
     * Build the preview card element using DOM methods (XSS-safe)
     * @param {Object} recipe - Recipe data with name and ingredients array
     * @returns {HTMLElement} The preview card element
     */
    function buildPreviewHTML(recipe) {
        const card = document.createElement('div');
        card.className = 'recipe-preview-card';

        // Recipe name (safe - uses textContent)
        const nameDiv = document.createElement('div');
        nameDiv.className = 'recipe-name';
        nameDiv.textContent = recipe.recipe_name;
        card.appendChild(nameDiv);

        // Ingredients list (safe - uses textContent)
        const ingredientsDiv = document.createElement('div');
        ingredientsDiv.className = 'ingredients';

        const ingredientsList = recipe.ingredients || [];
        const displayIngredients = ingredientsList.slice(0, MAX_PREVIEW_INGREDIENTS);
        const hasMore = ingredientsList.length > MAX_PREVIEW_INGREDIENTS;

        ingredientsDiv.textContent = displayIngredients.join(' • ') + (hasMore ? ' • ...' : '');
        card.appendChild(ingredientsDiv);

        return card;
    }

    /**
     * Position the preview card relative to a point, with edge detection
     * @param {number} x - X coordinate in viewport
     * @param {number} y - Y coordinate in viewport
     */
    function positionPreview(x, y) {
        if (!previewElement) return;

        const rect = previewElement.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        // Default: right and below the point
        let left = x + PREVIEW_OFFSET_X;
        let top = y + PREVIEW_OFFSET_Y;

        // Flip left if would go off right edge
        if (left + rect.width > viewportWidth - 10) {
            left = x - rect.width - PREVIEW_OFFSET_X;
        }

        // Flip up if would go off bottom edge
        if (top + rect.height > viewportHeight - 10) {
            top = y - rect.height - PREVIEW_OFFSET_Y;
        }

        // Ensure doesn't go off left or top edges
        left = Math.max(10, left);
        top = Math.max(10, top);

        previewElement.style.left = `${left}px`;
        previewElement.style.top = `${top}px`;
    }

    /**
     * Show the preview card for a recipe
     * @param {Object} recipe - Recipe data
     * @param {number} x - X coordinate in viewport
     * @param {number} y - Y coordinate in viewport
     */
    function show(recipe, x, y) {
        // Remove existing preview if any
        hide();

        currentRecipe = recipe;

        // Create preview element (buildPreviewHTML now returns element, not HTML string)
        previewElement = buildPreviewHTML(recipe);

        // Add to container
        container.appendChild(previewElement);

        // Position it (need to append first to get dimensions)
        positionPreview(x, y);
    }

    /**
     * Hide the preview card
     */
    function hide() {
        if (previewElement) {
            previewElement.remove();
            previewElement = null;
        }
        currentRecipe = null;
    }

    /**
     * Start hover timer for a recipe
     * @param {Object} recipe - Recipe data
     * @param {number} x - X coordinate in viewport
     * @param {number} y - Y coordinate in viewport
     */
    function startHover(recipe, x, y) {
        // Cancel any existing timer
        cancelHover();

        // Start new timer
        hoverTimer = setTimeout(() => {
            show(recipe, x, y);
        }, HOVER_DELAY_MS);
    }

    /**
     * Cancel pending hover timer
     */
    function cancelHover() {
        if (hoverTimer) {
            clearTimeout(hoverTimer);
            hoverTimer = null;
        }
        hide();
    }

    // Public API
    return {
        show,           // Direct show without delay (for touch)
        startHover,
        cancelHover,
        hide,
        isVisible: () => previewElement !== null
    };
}
