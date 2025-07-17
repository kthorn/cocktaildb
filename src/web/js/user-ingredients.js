import { api } from './api.js';
import { isAuthenticated } from './auth.js';

class UserIngredientsManager {
    constructor() {
        this.allIngredients = [];
        this.userIngredients = [];
        this.userIngredientIds = new Set();
        this.filteredIngredients = [];
        this.selectedToAdd = new Set();
        this.selectedToRemove = new Set();
        
        this.init();
    }

    async init() {
        // Check authentication and show appropriate content
        if (!isAuthenticated()) {
            this.showAuthRequired();
            return;
        }

        this.showAuthenticatedContent();
        this.bindEvents();
        await this.loadData();
    }

    showAuthRequired() {
        document.querySelector('.auth-required-content').style.display = 'none';
        document.querySelector('.auth-required-message').classList.remove('hidden');
        
        // Bind login prompt
        document.getElementById('login-prompt-btn').addEventListener('click', () => {
            // Trigger login (this would be handled by auth.js)
            window.location.href = '#login';
        });
    }

    showAuthenticatedContent() {
        document.querySelector('.auth-required-content').style.display = 'block';
        document.querySelector('.auth-required-message').classList.add('hidden');
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
    }

    async loadData() {
        try {
            // Load both user ingredients and all available ingredients
            const [userIngredientsData, allIngredientsData] = await Promise.all([
                api.getUserIngredients(),
                api.getIngredients()
            ]);

            this.userIngredients = userIngredientsData.ingredients || [];
            this.userIngredientIds = new Set(this.userIngredients.map(ing => ing.ingredient_id));
            this.allIngredients = allIngredientsData || [];
            this.filteredIngredients = this.allIngredients.filter(ing => !this.userIngredientIds.has(ing.id));

            this.renderCurrentIngredients();
            this.renderAvailableIngredients();
        } catch (error) {
            console.error('Error loading ingredients:', error);
            const errorMessage = error.message || 'Failed to load ingredients';
            this.showError(errorMessage);
        }
    }

    renderCurrentIngredients() {
        const container = document.getElementById('current-ingredients-list');
        
        if (this.userIngredients.length === 0) {
            container.innerHTML = '<p class="empty-state">No ingredients in your inventory yet.</p>';
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
            container.innerHTML = '<p class="empty-state">All ingredients are already in your inventory.</p>';
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
        ingredients.forEach(ingredient => {
            ingredientMap.set(ingredient.ingredient_id || ingredient.id, {
                ...ingredient,
                children: []
            });
        });

        // Second pass: build parent-child relationships
        ingredients.forEach(ingredient => {
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
            items.forEach(item => {
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
        
        hierarchy.forEach(ingredient => {
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
        
        checkboxes.forEach(checkbox => {
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
                        // Auto-select parent categories
                        this.selectParentIngredients(ingredientId, container, type);
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
        
        childIds.forEach(childId => {
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
        return this.allIngredients.find(ing => ing.id === ingredientId) || 
               this.userIngredients.find(ing => (ing.ingredient_id || ing.id) === ingredientId);
    }

    findChildIngredientIds(parentId) {
        // Find all ingredients that have this ingredient as parent
        const childIds = [];
        
        // Check in all available ingredients
        this.allIngredients.forEach(ing => {
            if (ing.parent_id === parentId) {
                childIds.push(ing.id);
            }
        });
        
        // Check in user ingredients
        this.userIngredients.forEach(ing => {
            if (ing.parent_id === parentId) {
                childIds.push(ing.ingredient_id || ing.id);
            }
        });
        
        return childIds;
    }

    async addSelectedIngredients() {
        if (this.selectedToAdd.size === 0) return;

        try {
            const ingredientIds = Array.from(this.selectedToAdd);
            await api.bulkAddUserIngredients(ingredientIds);
            
            // Reset selection
            this.selectedToAdd.clear();
            this.updateAddButton();
            
            // Reload data
            await this.loadData();
            
            this.showSuccess(`Added ${ingredientIds.length} ingredient(s) to your inventory`);
        } catch (error) {
            console.error('Error adding ingredients:', error);
            const errorMessage = error.message || 'Failed to add ingredients';
            this.showError(errorMessage);
        }
    }

    async removeSelectedIngredients() {
        if (this.selectedToRemove.size === 0) return;

        try {
            const ingredientIds = Array.from(this.selectedToRemove);
            await api.bulkRemoveUserIngredients(ingredientIds);
            
            // Reset selection
            this.selectedToRemove.clear();
            this.updateRemoveButton();
            
            // Reload data
            await this.loadData();
            
            this.showSuccess(`Removed ${ingredientIds.length} ingredient(s) from your inventory`);
        } catch (error) {
            console.error('Error removing ingredients:', error);
            const errorMessage = error.message || 'Failed to remove ingredients';
            this.showError(errorMessage);
        }
    }

    filterIngredients(searchTerm) {
        if (!searchTerm.trim()) {
            this.filteredIngredients = this.allIngredients.filter(ing => !this.userIngredientIds.has(ing.id));
        } else {
            const term = searchTerm.toLowerCase();
            this.filteredIngredients = this.allIngredients.filter(ing => 
                !this.userIngredientIds.has(ing.id) && 
                ing.name.toLowerCase().includes(term)
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
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new UserIngredientsManager();
});