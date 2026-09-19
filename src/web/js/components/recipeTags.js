/**
 * Remove malformed and duplicate tags while retaining the last occurrence, as the
 * existing card renderer did when normalizing backend responses.
 * @param {Array} tags
 * @returns {Array}
 */
export function deduplicateRecipeTags(tags) {
    const uniqueTags = new Map();
    if (!Array.isArray(tags)) {
        return [];
    }
    tags.forEach((tag) => {
        if (tag && tag.id && tag.name && tag.name.trim() !== '') {
            uniqueTags.set(tag.id, tag);
        }
    });
    return Array.from(uniqueTags.values());
}

/**
 * Split recipe tags into the public/private groups used by the card.
 * @param {Array} tags
 * @returns {{publicTags: Array, privateTags: Array, hasAnyTags: boolean}}
 */
export function splitRecipeTags(tags) {
    const deduplicatedTags = deduplicateRecipeTags(tags);
    const publicTags = deduplicatedTags.filter((tag) => tag.type === 'public');
    const privateTags = deduplicatedTags.filter((tag) => tag.type === 'private');
    return {
        publicTags,
        privateTags,
        hasAnyTags: publicTags.length > 0 || privateTags.length > 0,
    };
}

/**
 * Render tag chips for a recipe card.
 * @param {Array} tags
 * @param {{recipeId?: number|string, shouldShowActions?: boolean}} options
 * @returns {string}
 */
export function generateTagChips(tags, options = {}) {
    const { recipeId, shouldShowActions = false } = options;
    return (tags || [])
        .map(
            (tag) => `
            <span class="tag-chip ${tag.type === 'private' ? 'tag-private' : 'tag-public'}" data-tag-id="${tag.id}" data-tag-type="${tag.type}">
                ${tag.name}
                ${shouldShowActions ? `<button class="tag-remove-btn" data-recipe-id="${recipeId}" data-tag-id="${tag.id}" data-tag-type="${tag.type}" title="Remove from recipe">×</button>` : ''}
            </span>
        `,
        )
        .join('');
}

/**
 * Apply tag visibility state without encoding presentation details in markup.
 * @param {HTMLElement} tagsContainer
 * @param {HTMLElement} noTagsPlaceholder
 * @param {boolean} hasAnyTags
 */
export function updateTagVisibility(tagsContainer, noTagsPlaceholder, hasAnyTags) {
    tagsContainer?.classList.toggle('is-hidden', !hasAnyTags);
    noTagsPlaceholder?.classList.toggle('is-hidden', hasAnyTags);
}
