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
     * Build the preview card HTML
     * @param {Object} recipe - Recipe data with name and ingredients array
     * @returns {string} HTML string for preview card
     */
    function buildPreviewHTML(recipe) {
        const ingredientsList = recipe.ingredients || [];
        const displayIngredients = ingredientsList.slice(0, MAX_PREVIEW_INGREDIENTS);
        const hasMore = ingredientsList.length > MAX_PREVIEW_INGREDIENTS;

        const ingredientsText = displayIngredients.join(' • ') + (hasMore ? ' • ...' : '');

        return `
            <div class="recipe-preview-card">
                <div class="recipe-name">${recipe.recipe_name}</div>
                <div class="ingredients">${ingredientsText}</div>
            </div>
        `;
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

        // Create preview element
        const div = document.createElement('div');
        div.innerHTML = buildPreviewHTML(recipe);
        previewElement = div.firstElementChild;

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
        startHover,
        cancelHover,
        hide,
        isVisible: () => previewElement !== null
    };
}
