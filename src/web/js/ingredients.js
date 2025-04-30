import { api } from './api.js';

// Define these functions in the global scope so they can be accessed from HTML
window.editIngredient = async function(id) {
    // Check authentication first
    if (!api.isAuthenticated()) {
        alert('Please log in to edit ingredients.');
        return;
    }

    const form = document.getElementById('ingredient-form');
    if (!form) {
        console.error('Ingredient form not found');
        return;
    }

    try {
        const ingredient = await api.getIngredient(id);

        // Populate form with ingredient data
        document.getElementById('ingredient-name').value = ingredient.name;
        document.getElementById('ingredient-description').value = ingredient.description || '';
        
        // Set parent ingredient if it exists
        if (ingredient.parent_id) {
            try {
                const parentIngredient = await api.getIngredient(ingredient.parent_id);
                document.getElementById('ingredient-parent').value = parentIngredient.id;
                document.getElementById('ingredient-parent-search').value = parentIngredient.name;
            } catch (error) {
                console.error('Error loading parent ingredient:', error);
            }
        } else {
            document.getElementById('ingredient-parent').value = '';
            document.getElementById('ingredient-parent-search').value = '';
        }

        // Change form to update mode
        form.dataset.mode = 'edit';
        form.dataset.id = id;

        // Scroll to form
        form.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error loading ingredient:', error);
        alert('Failed to load ingredient. Please try again.');
    }
};

window.deleteIngredient = async function(id) {
    // Check authentication first
    if (!api.isAuthenticated()) {
        alert('Please log in to delete ingredients.');
        return;
    }

    if (!confirm('Are you sure you want to delete this ingredient?')) {
        return;
    }

    try {
        await api.deleteIngredient(id);
        window.loadIngredients(); // Making sure loadIngredients is accessible
    } catch (error) {
        console.error('Error deleting ingredient:', error);
        alert('Failed to delete ingredient. Please try again.');
    }
};

// Make loadIngredients accessible globally
window.loadIngredients = async function() {
    const ingredientsContainer = document.getElementById('ingredients-container');
    const loadingIndicator = document.getElementById('parent-loading-indicator');
    const searchStatus = document.getElementById('parent-search-status');
    
    try {
        // Show loading state
        if (loadingIndicator) loadingIndicator.classList.add('active');
        if (searchStatus) searchStatus.classList.add('active');
        
        window.availableIngredients = await api.getIngredients();
        console.log('Loaded ingredients:', window.availableIngredients);
        
        // Call displayIngredients if it exists in window or current scope
        if (typeof window.displayIngredients === 'function') {
            window.displayIngredients(window.availableIngredients);
        } else if (typeof displayIngredients === 'function') {
            displayIngredients(window.availableIngredients);
        } else {
            // Fallback implementation if not yet defined
            ingredientsContainer.innerHTML = '';
            if (window.availableIngredients.length === 0) {
                ingredientsContainer.innerHTML = '<p>No ingredients found.</p>';
                return;
            }
            
            window.availableIngredients.forEach(ingredient => {
                const card = document.createElement('div');
                card.className = 'ingredient-card';
                card.innerHTML = `
                    <h4>${ingredient.name}</h4>
                    <p>${ingredient.description || 'No description'}</p>
                    <div class="card-actions">
                        <button onclick="editIngredient(${ingredient.id})">Edit</button>
                        <button onclick="deleteIngredient(${ingredient.id})">Delete</button>
                    </div>
                `;
                ingredientsContainer.appendChild(card);
            });
        }
        
        // Update parent options if the function exists
        if (typeof window.updateParentOptions === 'function') {
            window.updateParentOptions(window.availableIngredients);
        }
    } catch (error) {
        console.error('Error loading ingredients:', error);
        if (ingredientsContainer) {
            ingredientsContainer.innerHTML = '<p>Error loading ingredients. Please try again later.</p>';
        }
    } finally {
        // Hide loading state
        if (loadingIndicator) loadingIndicator.classList.remove('active');
        if (searchStatus) searchStatus.classList.remove('active');
    }
};

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
    const ingredientForm = document.getElementById('ingredient-form');
    const ingredientsContainer = document.getElementById('ingredients-container');
    const searchInput = document.getElementById('ingredient-search');
    const parentSearchInput = document.getElementById('ingredient-parent-search');
    const parentSelect = document.getElementById('ingredient-parent');
    const parentAutocompleteDropdown = document.getElementById('parent-autocomplete-dropdown');
    const loadingIndicator = document.getElementById('parent-loading-indicator');
    const searchStatus = document.getElementById('parent-search-status');

    if (!ingredientForm || !ingredientsContainer || !searchInput || !parentSearchInput || !parentSelect || !parentAutocompleteDropdown) {
        console.error('Required elements not found in the DOM');
        return;
    }

    // Load ingredients on page load
    loadIngredients();

    // Handle form submission
    ingredientForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Check authentication first
        if (!api.isAuthenticated()) {
            alert('Please log in to create or edit ingredients.');
            return;
        }

        const name = document.getElementById('ingredient-name').value;
        const description = document.getElementById('ingredient-description').value;
        
        // Find parent ingredient id based on the search input value
        let parentId = null;
        const parentName = parentSearchInput.value.trim();
        
        if (parentName) {
            const parentIngredient = window.availableIngredients.find(
                ing => ing.name.toLowerCase() === parentName.toLowerCase()
            );
            
            if (parentIngredient) {
                parentId = parentIngredient.id;
            }
        }

        const ingredientData = {
            name,
            description,
            parent_id: parentId
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
            delete ingredientForm.dataset.mode;
            delete ingredientForm.dataset.id;
            loadIngredients();
        } catch (error) {
            console.error('Error saving ingredient:', error);
            if (error.message && error.message.includes('already exists')) {
                showNotification(error.message, 'error');
            } else {
                showNotification('Failed to save ingredient. Please try again.', 'error');
            }
        }
    });

    // Handle search
    searchInput.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        const ingredientCards = document.querySelectorAll('.ingredient-card');

        ingredientCards.forEach(card => {
            const name = card.querySelector('h4').textContent.toLowerCase();
            const description = card.querySelector('p').textContent.toLowerCase();

            if (name.includes(searchTerm) || description.includes(searchTerm)) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    });

    // Setup parent ingredient autocomplete
    setupParentAutocomplete();

    // Function to update parent ingredient options in the select
    window.updateParentOptions = function(ingredients) {
        parentSelect.innerHTML = '<option value="">None</option>';
        ingredients.forEach(ingredient => {
            const option = document.createElement('option');
            option.value = ingredient.id;
            option.textContent = ingredient.name;
            parentSelect.appendChild(option);
        });
    };

    // Display ingredients in the container
    window.displayIngredients = function(ingredients) {
        ingredientsContainer.innerHTML = '';

        if (ingredients.length === 0) {
            ingredientsContainer.innerHTML = '<p>No ingredients found.</p>';
            return;
        }

        ingredients.forEach(ingredient => {
            const card = document.createElement('div');
            card.className = 'ingredient-card';
            
            // Get parent name if parent_id exists
            let parentInfo = '';
            if (ingredient.parent_id) {
                const parent = ingredients.find(ing => ing.id === ingredient.parent_id);
                if (parent) {
                    parentInfo = `<p><strong>Parent:</strong> ${parent.name}</p>`;
                }
            }
            
            card.innerHTML = `
                <h4>${ingredient.name}</h4>
                ${parentInfo}
                <p>${ingredient.description || 'No description'}</p>
                <div class="card-actions">
                    <button onclick="editIngredient(${ingredient.id})">Edit</button>
                    <button onclick="deleteIngredient(${ingredient.id})">Delete</button>
                </div>
            `;
            ingredientsContainer.appendChild(card);
        });
    };

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
            if (!window.availableIngredients || !Array.isArray(window.availableIngredients)) {
                console.log('Waiting for ingredients to load...');
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
            
            console.log('Searching for:', searchTerm, 'in', window.availableIngredients);
            
            // Find matching ingredients
            const matches = window.availableIngredients.filter(ingredient => 
                ingredient.name.toLowerCase().includes(searchTerm)
            );
            
            console.log('Matches found:', matches.length, matches);
            
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
                    match => `<strong>${match}</strong>`
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
            items.forEach(item => item.classList.remove('active'));
            
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
                const parent = window.availableIngredients.find(ing => ing.name === selectedValue);
                if (parent) {
                    parentSelect.value = parent.id;
                }
                
                parentAutocompleteDropdown.style.display = 'none';
            }
        }
        
        // Input event listener for parent search
        parentSearchInput.addEventListener('input', function() {
            console.log('Parent search input changed:', this.value);
            updateParentAutocomplete();
        });
        
        // Focus event listener for parent search
        parentSearchInput.addEventListener('focus', updateParentAutocomplete);
        
        // Blur event listener for parent search
        parentSearchInput.addEventListener('blur', (e) => {
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
                if (activeParentIndex === -1) {
                    setActiveParentItem(0);
                } else {
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
}); 