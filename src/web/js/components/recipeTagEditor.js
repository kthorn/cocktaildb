import { deduplicateRecipeTags } from './recipeTags.js';

const modalHtml = `
    <div id="tag-editor-modal" class="modal is-hidden">
        <div class="modal-content">
            <span class="close-tag-modal-btn">&times;</span>
            <h3>Edit Tags for <span id="tag-editor-recipe-name">Recipe</span></h3>
            <input type="hidden" id="tag-editor-recipe-id">
            <div class="form-group">
                <label>Select from existing tags:</label>
                <div id="existing-tags-section">
                    <div id="public-tags-section">
                        <h5>&#x1F30D; Public Tags</h5>
                        <div id="public-tags-list" class="existing-tags-list"></div>
                    </div>
                    <div id="private-tags-section">
                        <h5>&#x1F512; Private Tags</h5>
                        <div id="private-tags-list" class="existing-tags-list"></div>
                    </div>
                </div>
            </div>
            <div class="form-group">
                <label for="tag-input">Or create new tags (comma-separated):</label>
                <input type="text" id="tag-input" placeholder="e.g., easy, quick, my favorite">
                <small>Default: Public (&#x1F30D;). Click a tag chip to toggle its privacy (&#x1F512;). Type a new tag and press Enter or comma.</small>
            </div>
            <div id="tag-chips-container" class="tag-chips-container"></div>
            <div class="form-actions">
                <button id="save-tags-btn" class="btn-primary">Save</button>
                <button id="cancel-tags-btn" class="btn-secondary">Cancel</button>
            </div>
        </div>
    </div>
`;

/**
 * Install the recipe tag editor and its delegated card trigger.
 * @param {{api: Object, isAuthenticated: Function, onTagsUpdated?: Function}} dependencies
 */
export function initializeRecipeTagEditor({ api, isAuthenticated, onTagsUpdated = () => {} }) {
    let modal;
    let recipeNameElement;
    let recipeIdInput;
    let tagInput;
    let chipsContainer;
    let saveButton;
    let currentTags = [];
    let originalTags = [];

    function ensureModal() {
        if (modal) return;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modal = document.getElementById('tag-editor-modal');
        recipeNameElement = document.getElementById('tag-editor-recipe-name');
        recipeIdInput = document.getElementById('tag-editor-recipe-id');
        tagInput = document.getElementById('tag-input');
        chipsContainer = document.getElementById('tag-chips-container');
        saveButton = document.getElementById('save-tags-btn');
        const close = () => closeEditor();
        modal.querySelector('.close-tag-modal-btn').addEventListener('click', close);
        document.getElementById('cancel-tags-btn').addEventListener('click', close);
        saveButton.addEventListener('click', saveTags);
        tagInput.addEventListener('keypress', handleTagInput);
        tagInput.addEventListener('blur', handleTagInput);
    }

    function handleTagInput(event) {
        if (event.type === 'keypress' && event.key !== 'Enter' && event.key !== ',') return;
        if (event.type === 'keypress') event.preventDefault();
        tagInput.value
            .split(',')
            .map((tag) => tag.trim())
            .filter(Boolean)
            .forEach((name) => addTag(name));
        tagInput.value = '';
    }

    function openEditor(button) {
        ensureModal();
        recipeIdInput.value = button.dataset.recipeId;
        recipeNameElement.textContent = decodeURIComponent(button.dataset.recipeName || 'Recipe');
        try {
            const parsed = JSON.parse(button.dataset.recipeTags || '[]');
            currentTags = parsed.map((tag) =>
                typeof tag === 'string'
                    ? { name: tag, type: 'public' }
                    : {
                          id: tag.id ? parseInt(tag.id) : undefined,
                          name: tag.name,
                          type: tag.type || 'public',
                      },
            );
            originalTags = JSON.parse(JSON.stringify(currentTags));
        } catch (error) {
            console.error('Error parsing current tags:', error);
            currentTags = [];
            originalTags = [];
        }
        renderChips();
        tagInput.value = '';
        loadExistingTags();
        modal.classList.remove('is-hidden');
        tagInput.focus();
    }

    function closeEditor() {
        modal?.classList.add('is-hidden');
        currentTags = [];
        originalTags = [];
        if (tagInput) tagInput.value = '';
    }

    function renderChips() {
        chipsContainer.innerHTML = '';
        currentTags.forEach((tag, index) => {
            const chip = document.createElement('div');
            chip.className = `tag-chip ${tag.type === 'private' ? 'tag-chip-private' : 'tag-chip-public'}`;
            chip.innerHTML = `
                <span class="tag-icon">${tag.type === 'private' ? '&#x1F512;' : '&#x1F30D;'}</span>
                <span class="tag-name">${tag.name}</span>
                <button class="tag-editor-remove-btn" title="Remove tag">&times;</button>
            `;
            chip.addEventListener('click', (event) => {
                if (!event.target.classList.contains('tag-editor-remove-btn')) {
                    currentTags[index].type = tag.type === 'private' ? 'public' : 'private';
                    renderChips();
                }
            });
            chip.querySelector('.tag-editor-remove-btn').addEventListener('click', (event) => {
                event.stopPropagation();
                currentTags.splice(index, 1);
                renderChips();
                refreshExistingTags();
            });
            chipsContainer.appendChild(chip);
        });
    }

    function addTag(name, type = 'public') {
        const trimmed = name.trim();
        if (
            !trimmed ||
            currentTags.some(
                (tag) => tag.name.toLowerCase() === trimmed.toLowerCase() && tag.type === type,
            )
        )
            return;
        currentTags.push({ name: trimmed, type });
        renderChips();
        refreshExistingTags();
    }

    function refreshExistingTags() {
        document.querySelectorAll('.existing-tag-btn').forEach((button) => {
            const added = currentTags.some(
                (tag) =>
                    tag.name.toLowerCase() === button.dataset.tagName.toLowerCase() &&
                    tag.type === button.dataset.tagType,
            );
            button.classList.toggle('tag-already-added', added);
            button.disabled = added;
        });
    }

    function displayExistingTags(tags, container, type) {
        if (!tags || tags.length === 0) {
            container.innerHTML = `<p class="no-tags">No ${type} tags available</p>`;
            return;
        }
        container.innerHTML = '';
        tags.forEach((tag) => {
            const button = document.createElement('button');
            button.className = 'existing-tag-btn';
            button.dataset.tagName = tag.name;
            button.dataset.tagType = type;
            button.innerHTML = `<span class="tag-icon">${type === 'private' ? '&#x1F512;' : '&#x1F30D;'}</span><span class="tag-name">${tag.name}</span>`;
            button.addEventListener('click', () => {
                addTag(tag.name, type);
                button.classList.add('tag-already-added');
                button.disabled = true;
            });
            container.appendChild(button);
        });
        refreshExistingTags();
    }

    async function loadExistingTags() {
        const publicList = document.getElementById('public-tags-list');
        const privateList = document.getElementById('private-tags-list');
        try {
            displayExistingTags(await api.getPublicTags(), publicList, 'public');
            if (isAuthenticated()) {
                displayExistingTags(await api.getPrivateTags(), privateList, 'private');
            } else {
                privateList.innerHTML =
                    '<p class="auth-required">Login required to view private tags</p>';
            }
        } catch (error) {
            console.error('Error loading existing tags:', error);
            publicList.innerHTML = '<p class="error">Error loading public tags</p>';
            privateList.innerHTML = '<p class="error">Error loading private tags</p>';
        }
    }

    async function saveTags() {
        const recipeId = recipeIdInput.value;
        saveButton.disabled = true;
        saveButton.textContent = 'Saving...';
        try {
            const removals = originalTags.filter(
                (original) =>
                    original.id &&
                    !currentTags.some(
                        (tag) =>
                            tag.id === original.id &&
                            tag.name.toLowerCase() === original.name.toLowerCase() &&
                            tag.type === original.type,
                    ),
            );
            const additions = currentTags.filter(
                (tag) =>
                    !originalTags.some(
                        (original) =>
                            ((tag.id && original.id === tag.id) ||
                                (!tag.id &&
                                    original.name.toLowerCase() === tag.name.toLowerCase())) &&
                            original.type === tag.type,
                    ),
            );
            for (const tag of removals) {
                if (!tag.id || Number.isNaN(parseInt(tag.id))) {
                    console.error('Invalid tag ID for removal:', tag);
                    continue;
                }
                await api.removeTagFromRecipe(recipeId, parseInt(tag.id), tag.type);
            }
            const seen = new Set();
            for (const tag of additions) {
                const key = `${tag.name.toLowerCase()}-${tag.type}`;
                if (!seen.has(key)) {
                    seen.add(key);
                    await api.addTagToRecipe(recipeId, tag.name, tag.type);
                }
            }
            const updatedRecipe = await api.getRecipe(recipeId);
            onTagsUpdated(recipeId, deduplicateRecipeTags(updatedRecipe?.tags || []));
            closeEditor();
        } catch (error) {
            console.error('Error saving tags:', error);
            alert(`Failed to save tags: ${error.message || 'An unexpected error occurred.'}`);
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = 'Save';
        }
    }

    document.addEventListener('click', (event) => {
        const button = event.target.closest('.add-tag-btn');
        if (button) openEditor(button);
    });
}
