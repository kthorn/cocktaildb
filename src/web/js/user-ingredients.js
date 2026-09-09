import { api } from './api.js';
import { getUserInfo, isAuthenticated } from './auth.js';

function currentUserId() {
    try {
        return getUserInfo()?.cognitoUserId || null;
    } catch {
        return null;
    }
}

class UserIngredientsManager {
    constructor() {
        this.allIngredients = [];
        this.userIngredients = [];
        this.userIngredientIds = new Set();
        this.filteredIngredients = [];
        this.selectedToAdd = new Set();
        this.selectedToRemove = new Set();

        // Private tag management
        this.privateTags = [];

        // Ingredient recommendations
        this.recommendations = [];
        this.recommendationsLimit = 10; // Number of recommendations to display
        this.authGeneration = 0;
        this.authenticated = false;
        this.principalId = null;

        this.initPromise = this.init();
    }

    async init() {
        this.principalId = currentUserId();
        this.bindEvents();
        document.addEventListener('auth-state-changed', (event) => {
            this.handleAuthChange(event.detail || {});
        });

        // Check authentication and show appropriate content
        if (!isAuthenticated()) {
            this.authenticated = false;
            this.showAuthRequired();
            return;
        }

        this.authenticated = true;
        this.showAuthenticatedContent();
        // The banner is informational. Its request must not hold up inventory loading.
        void this.loadGroupBanner();
        await this.loadData();
        await this.loadPrivateTags();
        await this.loadRecommendations();
    }

    showAuthRequired() {
        const content = document.querySelector('.auth-required-content');
        if (content) content.style.display = 'none';
        document.querySelector('.auth-required-message').classList.remove('hidden');

        // Bind login prompt
        const loginPrompt = document.getElementById('login-prompt-btn');
        if (loginPrompt && !loginPrompt.dataset.bound) {
            loginPrompt.dataset.bound = 'true';
            loginPrompt.addEventListener('click', () => {
                const headerLogin = document.getElementById('login-btn');
                if (headerLogin) headerLogin.click();
                else window.location.href = '#login';
            });
        }
    }

    showAuthenticatedContent() {
        const content = document.querySelector('.auth-required-content');
        if (content) content.style.display = 'block';
        document.querySelector('.auth-required-message').classList.add('hidden');
    }

    handleAuthChange({ isAuthenticated: authenticated } = {}) {
        const loggedIn = authenticated ?? isAuthenticated();
        const nextPrincipalId = currentUserId();
        const principalChanged = this.principalId !== nextPrincipalId;
        if (!loggedIn) {
            if (!this.authenticated) return;
            this.authenticated = false;
            this.principalId = null;
            this.authGeneration += 1;
            this.clearInventoryState();
            this.showAuthRequired();
            const banner = document.getElementById('group-banner-status');
            if (banner) banner.textContent = 'Log in to view your shared bar inventory.';
            return;
        }

        if (this.authenticated && !principalChanged) return;
        this.principalId = nextPrincipalId;
        this.authGeneration += 1;
        this.authenticated = true;
        this.clearInventoryState();
        this.showAuthenticatedContent();
        void this.loadGroupBanner();
        void this.loadData();
        void this.loadPrivateTags();
        void this.loadRecommendations();
    }

    clearInventoryState() {
        this.allIngredients = [];
        this.userIngredients = [];
        this.userIngredientIds.clear();
        this.filteredIngredients = [];
        this.selectedToAdd.clear();
        this.selectedToRemove.clear();
        this.privateTags = [];
        this.recommendations = [];

        const current = document.getElementById('current-ingredients-list');
        const available = document.getElementById('available-ingredients-list');
        const tags = document.getElementById('private-tags-list');
        const recommendations = document.getElementById('recommendations-list');
        const banner = document.getElementById('group-banner-status');
        if (current) current.textContent = 'Loading your ingredients...';
        if (available) available.textContent = 'Loading available ingredients...';
        if (tags) tags.textContent = 'Loading your private tags...';
        if (recommendations) recommendations.textContent = 'Loading recommendations...';
        if (banner) banner.textContent = 'Loading your shared bar inventory...';
        this.updateAddButton();
        this.updateRemoveButton();
    }

    isCurrentMutation(generation, principalId) {
        return (
            generation === this.authGeneration &&
            principalId === this.principalId &&
            principalId === currentUserId() &&
            isAuthenticated()
        );
    }

    async loadGroupBanner() {
        const banner = document.getElementById('group-banner-status');
        if (!banner || !api.getMyGroup) return;
        const generation = this.authGeneration;

        try {
            const group = await api.getMyGroup();
            if (generation !== this.authGeneration || !isAuthenticated()) return;
            if (group?.name) {
                banner.textContent = `Your ingredients are shared with “${group.name}”. Personal private tags remain visible only to you.`;
            }
        } catch {
            // The banner is supplementary; inventory loading continues independently.
            if (generation !== this.authGeneration || !isAuthenticated()) return;
            banner.textContent =
                'Your shared bar inventory is available below. Personal private tags remain visible only to you.';
        }
    }

    bindEvents() {
        // Search functionality
        document.getElementById('ingredient-search').addEventListener('input', (e) => {
            this.filterIngredients(e.target.value);
        });

        // Bulk action buttons
        document.getElementById('add-selected-btn').addEventListener('click', () => {
            this.addSelectedIngredients();
        });

        document.getElementById('remove-selected-btn').addEventListener('click', () => {
            this.removeSelectedIngredients();
        });

        // Private tag management
        document.getElementById('refresh-private-tags-btn').addEventListener('click', () => {
            this.loadPrivateTags();
        });

        // Ingredient recommendations
        document.getElementById('refresh-recommendations-btn').addEventListener('click', () => {
            this.loadRecommendations();
        });
    }

    async loadData() {
        const generation = this.authGeneration;
        try {
            // Load both user ingredients and all available ingredients
            const [userIngredientsData, allIngredientsData] = await Promise.all([
                api.getUserIngredients(),
                api.getIngredients(),
            ]);
            if (generation !== this.authGeneration || !isAuthenticated()) return;

            this.userIngredients = userIngredientsData.ingredients || [];
            this.userIngredientIds = new Set(this.userIngredients.map((ing) => ing.ingredient_id));
            this.allIngredients = allIngredientsData || [];
            this.filteredIngredients = this.allIngredients.filter(
                (ing) => !this.userIngredientIds.has(ing.id),
            );

            this.renderCurrentIngredients();
            this.renderAvailableIngredients();
        } catch (error) {
            if (generation !== this.authGeneration || !isAuthenticated()) return;
            console.error('Error loading ingredients:', error);
            const errorMessage = error.message || 'Failed to load ingredients';
            this.showError(errorMessage);
        }
    }

    renderCurrentIngredients() {
        const container = document.getElementById('current-ingredients-list');

        if (this.userIngredients.length === 0) {
            container.innerHTML =
                '<p class="empty-state">No ingredients in your inventory yet.</p>';
            return;
        }

        // Build hierarchy structure
        const hierarchy = this.buildHierarchy(this.userIngredients);
        container.innerHTML = this.renderHierarchyHTML(hierarchy, 'current');

        // Bind checkbox events for removal
        this.bindCheckboxEvents(container, 'current');
    }

    renderAvailableIngredients() {
        const container = document.getElementById('available-ingredients-list');

        if (this.filteredIngredients.length === 0) {
            container.innerHTML =
                '<p class="empty-state">All ingredients are already in your inventory.</p>';
            return;
        }

        // Build hierarchy structure
        const hierarchy = this.buildHierarchy(this.filteredIngredients);
        container.innerHTML = this.renderHierarchyHTML(hierarchy, 'available');

        // Bind checkbox events for adding
        this.bindCheckboxEvents(container, 'available');
    }

    buildHierarchy(ingredients) {
        const ingredientMap = new Map();
        const rootIngredients = [];

        // First pass: create map of all ingredients
        ingredients.forEach((ingredient) => {
            ingredientMap.set(ingredient.ingredient_id || ingredient.id, {
                ...ingredient,
                children: [],
            });
        });

        // Second pass: build parent-child relationships
        ingredients.forEach((ingredient) => {
            const id = ingredient.ingredient_id || ingredient.id;
            const parentId = ingredient.parent_id;

            if (parentId && ingredientMap.has(parentId)) {
                ingredientMap.get(parentId).children.push(ingredientMap.get(id));
            } else {
                rootIngredients.push(ingredientMap.get(id));
            }
        });

        // Sort each level by name
        const sortHierarchy = (items) => {
            items.sort((a, b) => a.name.localeCompare(b.name));
            items.forEach((item) => {
                if (item.children.length > 0) {
                    sortHierarchy(item.children);
                }
            });
        };

        sortHierarchy(rootIngredients);
        return rootIngredients;
    }

    renderHierarchyHTML(hierarchy, type, level = 0) {
        if (hierarchy.length === 0) return '';

        const isRoot = level === 0;
        const listClass = isRoot ? 'hierarchy-root' : 'hierarchy-children';

        let html = `<ul class="${listClass}" style="margin-left: ${level * 20}px;">`;

        hierarchy.forEach((ingredient) => {
            const id = ingredient.ingredient_id || ingredient.id;
            const hasChildren = ingredient.children && ingredient.children.length > 0;
            const checkboxId = `${type}-${id}`;

            html += `
                <li class="hierarchy-item ${hasChildren ? 'has-children' : ''}">
                    <div class="ingredient-row">
                        <input type="checkbox" id="${checkboxId}" value="${id}" class="ingredient-checkbox">
                        <label for="${checkboxId}" class="ingredient-label">
                            ${ingredient.name}
                        </label>
                    </div>
                    ${hasChildren ? this.renderHierarchyHTML(ingredient.children, type, level + 1) : ''}
                </li>
            `;
        });

        html += '</ul>';
        return html;
    }

    bindCheckboxEvents(container, type) {
        const checkboxes = container.querySelectorAll('.ingredient-checkbox');

        checkboxes.forEach((checkbox) => {
            checkbox.addEventListener('change', (e) => {
                const ingredientId = parseInt(e.target.value);

                if (type === 'available') {
                    if (e.target.checked) {
                        this.selectedToAdd.add(ingredientId);
                        // Auto-select parent categories
                        this.selectParentIngredients(ingredientId, container, type);
                    } else {
                        this.selectedToAdd.delete(ingredientId);
                        // Auto-deselect child categories
                        this.deselectChildIngredients(ingredientId, container, type);
                    }
                    this.updateAddButton();
                } else if (type === 'current') {
                    if (e.target.checked) {
                        this.selectedToRemove.add(ingredientId);
                    } else {
                        this.selectedToRemove.delete(ingredientId);
                        // Auto-deselect child categories
                        this.deselectChildIngredients(ingredientId, container, type);
                    }
                    this.updateRemoveButton();
                }
            });
        });
    }

    updateAddButton() {
        const button = document.getElementById('add-selected-btn');
        const count = this.selectedToAdd.size;
        button.disabled = count === 0;
        button.textContent = count === 0 ? 'Add Selected' : `Add Selected (${count})`;
    }

    updateRemoveButton() {
        const button = document.getElementById('remove-selected-btn');
        const count = this.selectedToRemove.size;
        button.disabled = count === 0;
        button.textContent = count === 0 ? 'Remove Selected' : `Remove Selected (${count})`;
    }

    selectParentIngredients(ingredientId, container, type) {
        // Find the ingredient and its parent
        const ingredient = this.findIngredientById(ingredientId);
        if (!ingredient || !ingredient.parent_id) return;

        const parentId = ingredient.parent_id;
        const parentCheckbox = container.querySelector(`#${type}-${parentId}`);

        if (parentCheckbox && !parentCheckbox.checked) {
            parentCheckbox.checked = true;

            // Add parent to selected set
            if (type === 'available') {
                this.selectedToAdd.add(parentId);
            } else if (type === 'current') {
                this.selectedToRemove.add(parentId);
            }

            // Recursively select parent's parents
            this.selectParentIngredients(parentId, container, type);
        }
    }

    deselectChildIngredients(ingredientId, container, type) {
        // Find all child ingredients and deselect them
        const childIds = this.findChildIngredientIds(ingredientId);

        childIds.forEach((childId) => {
            const childCheckbox = container.querySelector(`#${type}-${childId}`);
            if (childCheckbox && childCheckbox.checked) {
                childCheckbox.checked = false;

                // Remove child from selected set
                if (type === 'available') {
                    this.selectedToAdd.delete(childId);
                } else if (type === 'current') {
                    this.selectedToRemove.delete(childId);
                }

                // Recursively deselect child's children
                this.deselectChildIngredients(childId, container, type);
            }
        });
    }

    findIngredientById(ingredientId) {
        // Search in both filtered and all ingredients
        return (
            this.allIngredients.find((ing) => ing.id === ingredientId) ||
            this.userIngredients.find((ing) => (ing.ingredient_id || ing.id) === ingredientId)
        );
    }

    findChildIngredientIds(parentId) {
        // Find all ingredients that have this ingredient as parent
        const childIds = [];

        // Check in all available ingredients
        this.allIngredients.forEach((ing) => {
            if (ing.parent_id === parentId) {
                childIds.push(ing.id);
            }
        });

        // Check in user ingredients
        this.userIngredients.forEach((ing) => {
            if (ing.parent_id === parentId) {
                childIds.push(ing.ingredient_id || ing.id);
            }
        });

        return childIds;
    }

    async addSelectedIngredients() {
        if (this.selectedToAdd.size === 0) return;
        const generation = this.authGeneration;
        const principalId = this.principalId;

        try {
            const ingredientIds = Array.from(this.selectedToAdd);
            await api.bulkAddUserIngredients(ingredientIds);
            if (!this.isCurrentMutation(generation, principalId)) return;

            // Reset selection
            this.selectedToAdd.clear();
            this.updateAddButton();

            // Reload data and recommendations
            await this.loadData();
            if (!this.isCurrentMutation(generation, principalId)) return;
            await this.loadRecommendations();
            if (!this.isCurrentMutation(generation, principalId)) return;

            this.showSuccess(`Added ${ingredientIds.length} ingredient(s) to your inventory`);
        } catch (error) {
            if (!this.isCurrentMutation(generation, principalId)) return;
            console.error('Error adding ingredients:', error);
            const errorMessage = error.message || 'Failed to add ingredients';
            this.showError(errorMessage);
        }
    }

    async removeSelectedIngredients() {
        if (this.selectedToRemove.size === 0) return;
        const generation = this.authGeneration;
        const principalId = this.principalId;

        try {
            const ingredientIds = Array.from(this.selectedToRemove);
            await api.bulkRemoveUserIngredients(ingredientIds);
            if (!this.isCurrentMutation(generation, principalId)) return;

            // Reset selection
            this.selectedToRemove.clear();
            this.updateRemoveButton();

            // Reload data and recommendations
            await this.loadData();
            if (!this.isCurrentMutation(generation, principalId)) return;
            await this.loadRecommendations();
            if (!this.isCurrentMutation(generation, principalId)) return;

            this.showSuccess(`Removed ${ingredientIds.length} ingredient(s) from your inventory`);
        } catch (error) {
            if (!this.isCurrentMutation(generation, principalId)) return;
            console.error('Error removing ingredients:', error);

            // Extract specific error message from the response
            let errorMessage = error.message || 'Failed to remove ingredients from inventory';

            // Check if this is a parent-child validation error
            if (
                errorMessage.includes('Cannot remove ingredient') &&
                errorMessage.includes('child ingredients')
            ) {
                // This is already a specific parent-child error message, use it as-is
                this.showError(errorMessage);
            } else if (errorMessage.includes('Validation failed')) {
                // This might be a validation error with multiple issues
                this.showError(errorMessage);
            } else {
                // Generic error with more helpful context
                this.showError(`Unable to remove selected ingredients: ${errorMessage}`);
            }
        }
    }

    filterIngredients(searchTerm) {
        if (!searchTerm.trim()) {
            this.filteredIngredients = this.allIngredients.filter(
                (ing) => !this.userIngredientIds.has(ing.id),
            );
        } else {
            const term = searchTerm.toLowerCase();
            this.filteredIngredients = this.allIngredients.filter(
                (ing) =>
                    !this.userIngredientIds.has(ing.id) && ing.name.toLowerCase().includes(term),
            );
        }
        this.renderAvailableIngredients();
    }

    showSuccess(message) {
        // Create a simple toast notification
        const toast = document.createElement('div');
        toast.className = 'toast toast-success';
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    showError(message) {
        // Create a simple toast notification
        const toast = document.createElement('div');
        toast.className = 'toast toast-error';
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 5000);
    }

    // Private tag management methods
    async loadPrivateTags() {
        const tagsList = document.getElementById('private-tags-list');
        const refreshBtn = document.getElementById('refresh-private-tags-btn');
        const generation = this.authGeneration;

        if (!tagsList) return;

        try {
            // Show loading state
            tagsList.innerHTML =
                '<div class="loading-message"><p>Loading your private tags...</p></div>';
            if (refreshBtn) {
                refreshBtn.disabled = true;
                refreshBtn.textContent = 'Loading...';
            }

            this.privateTags = await api.getPrivateTags();
            if (generation !== this.authGeneration || !isAuthenticated()) return;

            if (this.privateTags.length === 0) {
                tagsList.innerHTML =
                    '<div class="empty-message"><p>No private tags found. Create tags when adding them to recipes.</p></div>';
                return;
            }

            // Generate tag list HTML
            let html = '';
            this.privateTags.forEach((tag) => {
                html += `
                    <div class="tag-management-item" data-tag-id="${tag.id}">
                        <div class="tag-management-info">
                            <div class="tag-management-name">${tag.name}</div>
                            <div class="tag-management-usage">Private tag - only visible to you</div>
                        </div>
                        <div class="tag-management-actions">
                            <button class="btn btn-danger btn-small delete-tag-btn" data-tag-id="${tag.id}" data-tag-name="${tag.name}">
                                Delete
                            </button>
                        </div>
                    </div>
                `;
            });

            tagsList.innerHTML = html;

            // Add event listeners for delete buttons
            const deleteButtons = tagsList.querySelectorAll('.delete-tag-btn');
            deleteButtons.forEach((btn) => {
                btn.addEventListener('click', (e) => this.handleDeletePrivateTag(e));
            });
        } catch (error) {
            if (generation !== this.authGeneration || !isAuthenticated()) return;
            console.error('Error loading private tags:', error);
            tagsList.innerHTML =
                '<div class="error-message"><p>Error loading tags. Please try again.</p></div>';
            this.showError('Error loading private tags');
        } finally {
            if (refreshBtn && generation === this.authGeneration) {
                refreshBtn.disabled = false;
                refreshBtn.textContent = 'Refresh';
            }
        }
    }

    async handleDeletePrivateTag(event) {
        const button = event.target;
        const tagId = parseInt(button.dataset.tagId);
        const tagName = button.dataset.tagName;

        // Confirm deletion
        const confirmMessage = `Are you sure you want to delete your private tag "${tagName}"?\n\nThis will remove it from all your recipes that use this tag. This action cannot be undone.`;
        if (!confirm(confirmMessage)) {
            return;
        }

        const originalText = button.textContent;
        const generation = this.authGeneration;
        const principalId = this.principalId;

        try {
            // Show loading state
            button.disabled = true;
            button.textContent = 'Deleting...';

            await api.deletePrivateTag(tagId);
            if (!this.isCurrentMutation(generation, principalId)) return;

            // Remove the tag item from the UI
            const tagItem = button.closest('.tag-management-item');
            if (tagItem) {
                tagItem.remove();
            }

            // Update local data
            this.privateTags = this.privateTags.filter((tag) => tag.id !== tagId);

            this.showSuccess(`Private tag "${tagName}" deleted successfully`);

            // Check if list is now empty
            const tagsList = document.getElementById('private-tags-list');
            if (tagsList && tagsList.children.length === 0) {
                tagsList.innerHTML =
                    '<div class="empty-message"><p>No private tags found. Create tags when adding them to recipes.</p></div>';
            }
        } catch (error) {
            if (!this.isCurrentMutation(generation, principalId)) return;
            console.error('Error deleting private tag:', error);
            this.showError(
                `Error deleting tag "${tagName}": ${error.message || 'Please try again'}`,
            );

            // Restore button state
            button.disabled = false;
            button.textContent = originalText;
        }
    }

    // Ingredient recommendation methods
    async loadRecommendations() {
        const recommendationsList = document.getElementById('recommendations-list');
        const refreshBtn = document.getElementById('refresh-recommendations-btn');
        const generation = this.authGeneration;

        if (!recommendationsList) return;

        try {
            // Show loading state
            recommendationsList.innerHTML =
                '<div class="loading-message"><p>Loading recommendations...</p></div>';
            if (refreshBtn) {
                refreshBtn.disabled = true;
                refreshBtn.textContent = 'Loading...';
            }

            const response = await api.getIngredientRecommendations(this.recommendationsLimit);
            if (generation !== this.authGeneration || !isAuthenticated()) return;
            this.recommendations = response.recommendations || [];

            if (this.recommendations.length === 0) {
                recommendationsList.innerHTML =
                    '<div class="empty-message"><p>No recommendations available. You may already be able to make most recipes!</p></div>';
                return;
            }

            this.renderRecommendations();
        } catch (error) {
            if (generation !== this.authGeneration || !isAuthenticated()) return;
            console.error('Error loading ingredient recommendations:', error);
            recommendationsList.innerHTML =
                '<div class="error-message"><p>Error loading recommendations. Please try again.</p></div>';
            this.showError('Error loading ingredient recommendations');
        } finally {
            if (refreshBtn && generation === this.authGeneration) {
                refreshBtn.disabled = false;
                refreshBtn.textContent = 'Refresh';
            }
        }
    }

    renderRecommendations() {
        const recommendationsList = document.getElementById('recommendations-list');

        if (!recommendationsList || this.recommendations.length === 0) return;

        let html = '<div class="recommendations-container">';

        this.recommendations.forEach((rec) => {
            const recipeList = rec.recipe_names.map((name) => `<li>${name}</li>`).join('');

            html += `
                <div class="recommendation-item" data-ingredient-id="${rec.id}">
                    <div class="recommendation-header">
                        <div class="recommendation-info">
                            <span class="recommendation-name">${rec.name}</span>
                            <span class="recommendation-badge">${rec.recipes_unlocked} recipe${rec.recipes_unlocked !== 1 ? 's' : ''}</span>
                        </div>
                        <div class="recommendation-actions">
                            <button class="btn btn-small btn-primary quick-add-btn" data-ingredient-id="${rec.id}">
                                Add to Inventory
                            </button>
                            <button class="btn btn-small btn-link expand-btn" data-ingredient-id="${rec.id}">
                                <span class="expand-icon">▼</span>
                            </button>
                        </div>
                    </div>
                    <div class="recommendation-recipes hidden" data-ingredient-id="${rec.id}">
                        <p class="recipes-label">Would enable:</p>
                        <ul class="recipe-list">${recipeList}</ul>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        recommendationsList.innerHTML = html;

        // Bind event listeners
        this.bindRecommendationEvents(recommendationsList);
    }

    bindRecommendationEvents(container) {
        // Expand/collapse buttons
        const expandButtons = container.querySelectorAll('.expand-btn');
        expandButtons.forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const ingredientId = e.currentTarget.dataset.ingredientId;
                const recipesDiv = container.querySelector(
                    `.recommendation-recipes[data-ingredient-id="${ingredientId}"]`,
                );
                const icon = e.currentTarget.querySelector('.expand-icon');

                if (recipesDiv) {
                    recipesDiv.classList.toggle('hidden');
                    icon.textContent = recipesDiv.classList.contains('hidden') ? '▼' : '▲';
                }
            });
        });

        // Quick-add buttons
        const quickAddButtons = container.querySelectorAll('.quick-add-btn');
        quickAddButtons.forEach((btn) => {
            btn.addEventListener('click', async (e) => {
                const button = e.currentTarget;
                const ingredientId = parseInt(button.dataset.ingredientId);
                const originalText = button.textContent;
                const generation = this.authGeneration;
                const principalId = this.principalId;

                try {
                    button.disabled = true;
                    button.textContent = 'Adding...';

                    await api.bulkAddUserIngredients([ingredientId]);
                    if (!this.isCurrentMutation(generation, principalId)) return;

                    // Reload data and recommendations
                    await this.loadData();
                    if (!this.isCurrentMutation(generation, principalId)) return;
                    await this.loadRecommendations();
                    if (!this.isCurrentMutation(generation, principalId)) return;

                    this.showSuccess(`Added ingredient to your inventory`);
                } catch (error) {
                    if (!this.isCurrentMutation(generation, principalId)) return;
                    console.error('Error adding ingredient from recommendations:', error);
                    this.showError(error.message || 'Failed to add ingredient');

                    // Restore button state
                    button.disabled = false;
                    button.textContent = originalText;
                }
            });
        });
    }
}

export { UserIngredientsManager };

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new UserIngredientsManager();
});
