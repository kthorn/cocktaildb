/**
 * Build the canonical URL shared by a recipe card.
 * @param {string} recipeName
 * @param {number|string|null|undefined} recipeId
 * @param {string} origin
 * @returns {string}
 */
export function buildRecipeShareUrl(recipeName, recipeId, origin) {
    return recipeId
        ? `${origin}/recipe/${encodeURIComponent(recipeId)}`
        : `${origin}/recipe/by-name?name=${encodeURIComponent(recipeName)}`;
}

/**
 * Copy a recipe URL and display feedback using the browser's available API.
 * @param {string} recipeName
 * @param {number|string|null|undefined} recipeId
 * @returns {Promise<void>}
 */
export async function copyRecipeLink(recipeName, recipeId) {
    const shareUrl = buildRecipeShareUrl(recipeName, recipeId, window.location.origin);
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(shareUrl);
    } else {
        const textArea = document.createElement('textarea');
        textArea.value = shareUrl;
        textArea.className = 'share-copy-fallback';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        document.execCommand('copy');
        textArea.remove();
    }
    showShareFeedback('Recipe link copied to clipboard!');
}

export function showShareFeedback(message) {
    let feedback = document.getElementById('share-feedback');
    if (!feedback) {
        feedback = document.createElement('div');
        feedback.id = 'share-feedback';
        feedback.className = 'share-feedback';
        document.body.appendChild(feedback);
    }

    feedback.textContent = message;
    feedback.classList.add('is-visible');
    feedback.classList.remove('is-hidden');
    setTimeout(() => {
        feedback.classList.remove('is-visible');
        setTimeout(() => feedback.classList.add('is-hidden'), 300);
    }, 2000);
}
