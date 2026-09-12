import { api } from './api.js';
import { buildHierarchy, renderHierarchyHTML } from './components/ingredientTree.js';

// Update page elements based on authentication and editor status
function updatePageBasedOnAuth() {
    const titleElement = document.getElementById('ingredients-title');
    const formSection = document.querySelector('.ingredient-form');

    if (api.isEditor()) {
        if (titleElement) titleElement.textContent = 'Manage Ingredients';
        if (formSection) formSection.style.display = 'block';
    } else {
        if (titleElement) titleElement.textContent = 'Ingredients';
        if (formSection) formSection.style.display = 'none';
    }
}

// Display notification to the user
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    // Add to the DOM
    const container = document.querySelector('.container') || document.body;
    container.insertBefore(notification, container.firstChild);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => notification.remove(), 500);
    }, 5000);
}

document.addEventListener('DOMContentLoaded', () => {
    // Authentication is now initialized in common.js
    // initAuth(); // Remove this line

    // Update page title and form visibility based on authentication
    updatePageBasedOnAuth();

    const ingredientForm = document.getElementById('ingredient-form');
    const ingredientsContainer = document.getElementById('ingredients-container');
    const searchInput = document.getElementById('ingredient-search');
    const parentSearchInput = document.getElementById('ingredient-parent-search');
    const parentSelect = document.getElementById('ingredient-parent');
    const parentAutocompleteDropdown = document.getElementById('parent-autocomplete-dropdown');
    const searchStatus = document.getElementById('parent-search-status');

    if (
        !ingredientForm ||
        !ingredientsContainer ||
        !searchInput ||
        !parentSearchInput ||
        !parentSelect ||
        !parentAutocompleteDropdown
    ) {
        console.error('Required elements not found in the DOM');
        return;
    }

    let availableIngredients = [];

    async function editIngredient(id) {
        if (!api.isEditor()) {
            alert('Editor access required. Only editors and admins can edit ingredients.');
            return;
        }

        const form = document.getElementById('ingredient-form');
        if (!form) {
            console.error('Ingredient form not found');
            return;
        }
        const submitButton = form.querySelector('button[type="submit"]');

        try {
            const ingredient = await api.getIngredient(id);
            document.getElementById('ingredient-name').value = ingredient.name;
            document.getElementById('ingredient-description').value = ingredient.description || '';
            document.getElementById('ingredient-url').value = ingredient.url || '';
            document.getElementById('ingredient-percent-abv').value = ingredient.percent_abv ?? '';
            document.getElementById('ingredient-sugar-g-per-l').value =
                ingredient.sugar_g_per_l ?? '';
            document.getElementById('ingredient-acid-g-per-l').value =
                ingredient.titratable_acidity_g_per_l ?? '';

            const allowSubstitutionCheckbox = document.getElementById(
                'ingredient-allow-substitution',
            );
            if (allowSubstitutionCheckbox) {
                allowSubstitutionCheckbox.checked = ingredient.allow_substitution || false;
            }

            if (ingredient.parent_id) {
                try {
                    const parentIngredient = await api.getIngredient(ingredient.parent_id);
                    parentSelect.value = parentIngredient.id;
                    parentSearchInput.value = parentIngredient.name;
                } catch (error) {
                    console.error('Error loading parent ingredient:', error);
                }
            } else {
                parentSelect.value = '';
                parentSearchInput.value = '';
            }

            form.dataset.mode = 'edit';
            form.dataset.id = id;
            if (submitButton) submitButton.textContent = 'Update Ingredient';
            form.scrollIntoView({ behavior: 'smooth' });
        } catch (error) {
            console.error('Error loading ingredient:', error);
            alert('Failed to load ingredient. Please try again.');
        }
    }

    async function deleteIngredient(id) {
        if (!api.isEditor()) {
            alert('Editor access required. Only editors and admins can delete ingredients.');
            return;
        }

        if (!confirm('Are you sure you want to delete this ingredient?')) return;

        try {
            await api.deleteIngredient(id);
            await loadIngredients();
        } catch (error) {
            console.error('Error deleting ingredient:', error);
            alert('Failed to delete ingredient. Please try again.');
        }
    }

    async function loadIngredients() {
        const loadingIndicator = document.getElementById('parent-loading-indicator');

        try {
            if (loadingIndicator) loadingIndicator.classList.add('active');
            if (searchStatus) searchStatus.classList.add('active');

            availableIngredients = await api.getIngredients();
            displayIngredients(availableIngredients);
            updateParentOptions(availableIngredients);
        } catch (error) {
            console.error('Error loading ingredients:', error);
            ingredientsContainer.innerHTML =
                '<p>Error loading ingredients. Please try again later.</p>';
        } finally {
            if (loadingIndicator) loadingIndicator.classList.remove('active');
            if (searchStatus) searchStatus.classList.remove('active');
        }
    }

    function updateParentOptions(ingredients) {
        parentSelect.innerHTML = '<option value="">None</option>';
        ingredients.forEach((ingredient) => {
            const option = document.createElement('option');
            option.value = ingredient.id;
            option.textContent = ingredient.name;
            parentSelect.appendChild(option);
        });
    }

    function displayIngredients(ingredients) {
        ingredientsContainer.innerHTML = '';
        if (ingredients.length === 0) {
            ingredientsContainer.innerHTML = '<p>No ingredients found.</p>';
            return;
        }

        const hierarchy = buildHierarchy(ingredients);
        ingredientsContainer.innerHTML = renderHierarchyHTML(
            hierarchy,
            (ingredient, { childrenHTML, hasChildren }) => {
                const actionButtons = api.isEditor()
                    ? `
                        <div class="tree-actions">
                            <button class="btn-small btn-outline" data-action="edit" data-ingredient-id="${ingredient.id}">Edit</button>
                            <button class="btn-small btn-outline-danger" data-action="delete" data-ingredient-id="${ingredient.id}">Delete</button>
                        </div>
                    `
                    : '';

                return `
                    <li class="hierarchy-item ${hasChildren ? 'has-children' : ''}">
                        <div class="ingredient-tree-row">
                            ${hasChildren ? '<button class="tree-toggle" type="button" data-action="toggle" aria-expanded="false">▶</button>' : '<span class="tree-spacer">‣</span>'}
                            <div class="tree-content">
                                <div class="tree-info">
                                    <span class="tree-name">${ingredient.name}</span>
                                    ${ingredient.description ? `<span class="tree-description">${ingredient.description}</span>` : ''}
                                    <span class="tree-substitution">[Substitutable: ${ingredient.allow_substitution ? 'Yes' : 'No'}]</span>
                                </div>
                                ${actionButtons}
                            </div>
                        </div>
                        ${hasChildren ? `<div class="tree-children">${childrenHTML}</div>` : ''}
                    </li>
                `;
            },
        );
    }

    ingredientsContainer.addEventListener('click', (event) => {
        const actionTarget = event.target.closest('[data-action]');
        if (!actionTarget || !ingredientsContainer.contains(actionTarget)) return;

        const action = actionTarget.dataset.action;
        if (action === 'toggle') {
            const item = actionTarget.closest('.hierarchy-item');
            const children = item?.querySelector(':scope > .tree-children');
            if (!children) return;
            const expanded = children.classList.toggle('is-expanded');
            actionTarget.textContent = expanded ? '▼' : '▶';
            actionTarget.setAttribute('aria-expanded', String(expanded));
            item.classList.toggle('expanded', expanded);
        } else if (action === 'edit') {
            editIngredient(Number(actionTarget.dataset.ingredientId));
        } else if (action === 'delete') {
            deleteIngredient(Number(actionTarget.dataset.ingredientId));
        }
    });

    // Load ingredients on page load
    loadIngredients();

    // Handle form submission
    ingredientForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Check editor permissions first
        if (!api.isEditor()) {
            alert(
                'Editor access required. Only editors and admins can create or edit ingredients.',
            );
            return;
        }

        const name = document.getElementById('ingredient-name').value.trim();
        const description = document.getElementById('ingredient-description').value.trim();
        const url = document.getElementById('ingredient-url').value.trim();
        const percentAbv = parseNumberInput(
            document.getElementById('ingredient-percent-abv').value,
        );
        const sugarGPerL = parseNumberInput(
            document.getElementById('ingredient-sugar-g-per-l').value,
        );
        const acidGPerL = parseNumberInput(
            document.getElementById('ingredient-acid-g-per-l').value,
        );

        // Get allow_substitution checkbox value
        const allowSubstitutionCheckbox = document.getElementById('ingredient-allow-substitution');
        const allowSubstitution = allowSubstitutionCheckbox
            ? allowSubstitutionCheckbox.checked
            : false;

        // Find parent ingredient id based on the search input value
        let parentId = null;
        const parentName = parentSearchInput.value.trim();

        if (parentName) {
            const parentIngredient = availableIngredients.find(
                (ing) => ing.name.toLowerCase() === parentName.toLowerCase(),
            );

            if (parentIngredient) {
                parentId = parentIngredient.id;
            }
        }

        const ingredientData = {
            name,
            description,
            parent_id: parentId,
            allow_substitution: allowSubstitution,
            url: url || null,
            percent_abv: percentAbv,
            sugar_g_per_l: sugarGPerL,
            titratable_acidity_g_per_l: acidGPerL,
        };

        try {
            let response;
            if (ingredientForm.dataset.mode === 'edit') {
                response = await api.updateIngredient(ingredientForm.dataset.id, ingredientData);
            } else {
                response = await api.createIngredient(ingredientData);
                if (response.message) {
                    showNotification(response.message, 'success');
                }
            }
            ingredientForm.reset();
            parentSearchInput.value = '';
            // Reset checkbox to unchecked (false)
            const resetCheckbox = document.getElementById('ingredient-allow-substitution');
            if (resetCheckbox) {
                resetCheckbox.checked = false;
            }
            document.getElementById('ingredient-url').value = '';
            document.getElementById('ingredient-percent-abv').value = '';
            document.getElementById('ingredient-sugar-g-per-l').value = '';
            document.getElementById('ingredient-acid-g-per-l').value = '';
            delete ingredientForm.dataset.mode;
            delete ingredientForm.dataset.id;
            const submitButton = ingredientForm.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.textContent = 'Add Ingredient';
            }
            loadIngredients();
        } catch (error) {
            console.error('Error saving ingredient:', error);
            // Display the error message from the backend (now reliably user-friendly)
            const errorMsg = error.message || 'Failed to save ingredient. Please try again.';
            showNotification(errorMsg, 'error');
        }
    });

    // Handle search in hierarchical view
    searchInput.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        const hierarchyItems = document.querySelectorAll('.hierarchy-item');

        if (!searchTerm.trim()) {
            // Show all items when search is empty
            hierarchyItems.forEach((item) => {
                item.classList.remove('is-hidden');
            });
            return;
        }

        // Filter hierarchy items based on search term
        hierarchyItems.forEach((item) => {
            const nameElement = item.querySelector('.tree-name');
            const descriptionElement = item.querySelector('.tree-description');

            const name = nameElement ? nameElement.textContent.toLowerCase() : '';
            const description = descriptionElement
                ? descriptionElement.textContent.toLowerCase()
                : '';

            if (name.includes(searchTerm) || description.includes(searchTerm)) {
                item.classList.remove('is-hidden');
                // Show parent items when child matches
                let parent = item.parentElement.closest('.hierarchy-item');
                while (parent) {
                    parent.classList.remove('is-hidden');
                    // Expand parent to show matching child
                    const toggle = parent.querySelector('.tree-toggle');
                    const children = parent.querySelector('.tree-children');
                    if (toggle && children) {
                        children.classList.add('is-expanded');
                        toggle.textContent = '▼';
                        toggle.setAttribute('aria-expanded', 'true');
                        parent.classList.add('expanded');
                    }
                    parent = parent.parentElement.closest('.hierarchy-item');
                }
            } else {
                item.classList.add('is-hidden');
            }
        });
    });

    // Setup parent ingredient autocomplete
    setupParentAutocomplete();

    // Setup autocomplete for parent ingredient search
    function setupParentAutocomplete() {
        // Function to update the autocomplete dropdown for parent
        function updateParentAutocomplete() {
            const searchTerm = parentSearchInput.value.toLowerCase();

            // Clear the dropdown
            parentAutocompleteDropdown.innerHTML = '';

            if (searchTerm.length === 0) {
                parentAutocompleteDropdown.style.display = 'none';
                return;
            }

            // Ensure we have access to the ingredients
            if (!Array.isArray(availableIngredients)) {
                if (searchStatus) {
                    searchStatus.textContent = 'Loading ingredients...';
                    searchStatus.classList.add('active');
                }
                return;
            }

            // Hide loading status if ingredients are loaded
            if (searchStatus) {
                searchStatus.classList.remove('active');
            }

            // Find matching ingredients
            const matches = availableIngredients.filter((ingredient) =>
                ingredient.name.toLowerCase().includes(searchTerm),
            );

            if (matches.length === 0) {
                parentAutocompleteDropdown.style.display = 'none';
                return;
            }

            // Add matches to dropdown
            matches.forEach((ingredient, index) => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item';

                // Highlight the matching part
                const highlightedText = ingredient.name.replace(
                    new RegExp(searchTerm, 'gi'),
                    (match) => `<strong>${match}</strong>`,
                );
                item.innerHTML = highlightedText;

                item.addEventListener('click', () => {
                    parentSearchInput.value = ingredient.name;
                    parentSelect.value = ingredient.id;
                    parentAutocompleteDropdown.style.display = 'none';
                });

                item.addEventListener('mouseenter', () => {
                    setActiveParentItem(index);
                });

                parentAutocompleteDropdown.appendChild(item);
            });

            // Show the dropdown
            parentAutocompleteDropdown.style.display = 'block';
            activeParentIndex = -1;
        }

        // Function to set the active parent item
        function setActiveParentItem(index) {
            const items = parentAutocompleteDropdown.querySelectorAll('.autocomplete-item');

            // Remove active class from all items
            items.forEach((item) => item.classList.remove('active'));

            // Set active class on the selected item
            if (index >= 0 && index < items.length) {
                activeParentIndex = index;
                items[index].classList.add('active');
                // Ensure the active item is in view
                items[index].scrollIntoView({ block: 'nearest' });
            }
        }

        // Function to select the current active parent item
        function selectActiveParentItem() {
            const items = parentAutocompleteDropdown.querySelectorAll('.autocomplete-item');
            if (activeParentIndex >= 0 && activeParentIndex < items.length) {
                const selectedValue = items[activeParentIndex].textContent;
                parentSearchInput.value = selectedValue;

                // Find and set the corresponding parent ID
                const parent = availableIngredients.find((ing) => ing.name === selectedValue);
                if (parent) {
                    parentSelect.value = parent.id;
                }

                parentAutocompleteDropdown.style.display = 'none';
            }
        }

        // Input event listener for parent search
        parentSearchInput.addEventListener('input', function () {
            updateParentAutocomplete();
        });

        // Focus event listener for parent search
        parentSearchInput.addEventListener('focus', updateParentAutocomplete);

        // Blur event listener for parent search
        parentSearchInput.addEventListener('blur', () => {
            // Delay hiding to allow click events on dropdown items
            setTimeout(() => {
                parentAutocompleteDropdown.style.display = 'none';
            }, 200);
        });

        // Keyboard navigation for parent search
        parentSearchInput.addEventListener('keydown', (e) => {
            const items = parentAutocompleteDropdown.querySelectorAll('.autocomplete-item');

            // Down arrow
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActiveParentItem(Math.min(activeParentIndex + 1, items.length - 1));
            }
            // Up arrow
            else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActiveParentItem(Math.max(activeParentIndex - 1, 0));
            }
            // Enter
            else if (e.key === 'Enter' && activeParentIndex >= 0) {
                e.preventDefault();
                selectActiveParentItem();
            }
            // Tab
            else if (e.key === 'Tab' && items.length > 0) {
                e.preventDefault(); // Prevent default tab behavior
                if (activeParentIndex === -1) {
                    // If no item is selected, select the first one
                    setActiveParentItem(0);
                } else {
                    // If an item is already selected, select it
                    selectActiveParentItem();
                }
            }
            // Escape
            else if (e.key === 'Escape') {
                parentAutocompleteDropdown.style.display = 'none';
            }
        });

        // Clear button functionality
        parentSearchInput.addEventListener('dblclick', () => {
            parentSearchInput.value = '';
            parentSelect.value = '';
        });
    }

    // Define a global activeParentIndex variable for parent search navigation
    let activeParentIndex = -1;

    function parseNumberInput(value) {
        if (!value.trim()) {
            return null;
        }
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }
});
