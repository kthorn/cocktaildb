/**
 * Render the authenticated or read-only rating view for a recipe.
 * @param {HTMLElement} container
 * @param {Object} recipe
 * @param {{authenticated: boolean, createInteractiveStars: Function, generateStarRating: Function, onRate: Function}} options
 */
export function renderRecipeRating(container, recipe, options) {
    const { authenticated, createInteractiveStars, generateStarRating, onRate } = options;
    if (!authenticated) {
        container.innerHTML = generateStarRating(recipe.avg_rating || 0, recipe.rating_count || 0);
        return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'star-rating interactive';
    wrapper.dataset.recipeId = recipe.id;
    wrapper.appendChild(
        createInteractiveStars({
            initialRating: recipe.user_rating,
            allowToggle: false,
            showDifferentStates: true,
            onClick: onRate,
        }),
    );

    const userIndicator = document.createElement('span');
    userIndicator.className = 'user-rating-indicator';
    const hasRating = recipe.user_rating !== null && recipe.user_rating !== undefined;
    const ratingValue = recipe.user_rating ?? 0;
    userIndicator.classList.add(hasRating ? 'has-rating' : 'not-rated');
    userIndicator.textContent = hasRating ? ` (${ratingValue})` : ' (not rated)';
    if (ratingValue === 0 && hasRating) {
        userIndicator.textContent = ' (0 stars)';
    }
    wrapper.appendChild(userIndicator);

    const stats = document.createElement('span');
    stats.className = 'rating-stats';
    stats.textContent = ` - Avg: ${(recipe.avg_rating || 0).toFixed(1)} (${recipe.rating_count || 0})`;
    wrapper.appendChild(stats);
    container.appendChild(wrapper);
}
