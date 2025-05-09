import { api } from './api.js';
import { isAuthenticated } from './auth.js';
import { displayRecipes } from './recipeCard.js';


// Declare function in global scope
let addIngredientInput;

document.addEventListener('DOMContentLoaded', () => {  
    const recipeForm = document.getElementById('recipe-form');
    const recipesContainer = document.getElementById('recipes-container');
    const searchInput = document.getElementById('recipe-search');
    const addIngredientBtn = document.getElementById('add-ingredient');
    const ingredientsList = document.getElementById('ingredients-list');

    if (!recipeForm || !recipesContainer || !searchInput || !addIngredientBtn || !ingredientsList) {
        console.error('Required elements not found in the DOM');
        return;
    }

    let availableIngredients = [];

    // Load recipes, units, and ingredients on page load
    loadRecipes();
    Promise.all([loadUnits(), loadIngredients()]).then(() => {
        // Add one ingredient row by default
        addIngredientInput();
    });

    // Load available ingredients
    async function loadIngredients() {
        try {
            availableIngredients = await api.getIngredients();
        } catch (error) {
            console.error('Error loading ingredients:', error);
        }
    }

    // Handle form submission
    recipeForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Check authentication first
        if (!isAuthenticated()) {
            alert('Please log in to create or edit recipes.');
            return;
        }

        try {
            const ingredients = [];
            const ingredientInputs = ingredientsList.querySelectorAll('.ingredient-input');

            if (ingredientInputs.length === 0) {
                throw new Error('Please add at least one ingredient');
            }

            const recipeName = document.getElementById('recipe-name').value.trim();
            if (!recipeName) {
                throw new Error('Recipe name is required');
            }

            const recipeInstructions = document.getElementById('recipe-instructions').value.trim();
            if (!recipeInstructions) {
                throw new Error('Recipe instructions are required');
            }

            ingredientInputs.forEach(input => {
                const ingredientName = input.querySelector('.ingredient-name').value;
                const ingredientUnitName = input.querySelector('.ingredient-unit').value;
                const amountInput = input.querySelector('.ingredient-amount');
                const amount = parseFloat(amountInput.value);
                
                if (!ingredientName) {
                    throw new Error('Please select an ingredient');
                }

                if (!ingredientUnitName) {
                    throw new Error(`Please select a unit for "${ingredientName}"`);
                }

                if (isNaN(amount) || amount <= 0) {
                    throw new Error(`Amount for "${ingredientName}" must be a positive number`);
                }
                
                // Find the ingredient by name
                const ingredient = availableIngredients.find(ing => ing.name === ingredientName);
                if (!ingredient) {
                    throw new Error(`Ingredient "${ingredientName}" not found`);
                }

                // Find the unit by name
                const unit = window.availableUnits?.find(u => u.name === ingredientUnitName);
                if (!unit) {
                    throw new Error(`Unit "${ingredientUnitName}" not found`);
                }

                ingredients.push({
                    ingredient_id: ingredient.id,
                    amount: amount,
                    unit_id: unit.id  // Send unit_id instead of unit name
                });
            });

            const recipeData = {
                name: recipeName,
                description: document.getElementById('recipe-description').value.trim(),
                instructions: recipeInstructions,
                source: document.getElementById('recipe-source').value.trim(),
                source_url: formatSourceUrl(document.getElementById('recipe-source-url').value.trim()),
                ingredients: ingredients
            };

            if (recipeForm.dataset.mode === 'edit') {
                await api.updateRecipe(recipeForm.dataset.id, recipeData);
                alert('Recipe updated successfully!');
            } else {
                await api.createRecipe(recipeData);
                alert('Recipe created successfully!');
            }
            
            recipeForm.reset();
            ingredientsList.innerHTML = '';
            delete recipeForm.dataset.mode;
            delete recipeForm.dataset.id;
            // Add one ingredient row by default after reset
            addIngredientInput();
            loadRecipes();
        } catch (error) {
            console.error('Error saving recipe:', error);
            alert(`Failed to save recipe: ${error.message || 'Please try again.'}`);
        }
    });

    // Format source URL to ensure it has proper http/https prefix
    function formatSourceUrl(url) {
        if (!url) return '';
        
        // If URL already has http/https protocol, return it as is
        if (url.match(/^https?:\/\//i)) {
            return url;
        }
        
        // Otherwise, add https:// prefix
        return `https://${url}`;
    }

    // Handle adding new ingredient input
    addIngredientBtn.addEventListener('click', () => {
        addIngredientInput();
    });

    // Handle search
    searchInput.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        const recipeCards = document.querySelectorAll('.recipe-card');

        recipeCards.forEach(card => {
            const name = card.querySelector('h4').textContent.toLowerCase();
            const description = card.querySelector('p').textContent.toLowerCase();

            if (name.includes(searchTerm) || description.includes(searchTerm)) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    });

    // Load and display recipes
    async function loadRecipes() {
        try {
            const recipes = await api.getRecipes();
            displayRecipes(recipes, recipesContainer, true, loadRecipes);
        } catch (error) {
            console.error('Error loading recipes:', error);
            recipesContainer.innerHTML = '<p>Error loading recipes. Please try again later.</p>';
        }
    }

    // Load available units
    async function loadUnits() {
        try {
            const units = await api.getUnits();
            // Store units in a closure instead of global window object
            window.availableUnits = units;
        } catch (error) {
            console.error('Error loading units:', error);
        }
    }

    // Define addIngredientInput as a global function (assigned to the variable declared at the top)
    addIngredientInput = function() {
        const div = document.createElement('div');
        div.className = 'ingredient-input';
        div.innerHTML = `
            <div class="ingredient-fields">
                <div class="form-group">
                    <input type="number" class="ingredient-amount" name="ingredient-amount" placeholder="Amount" step="0.25" min="0" required>
                </div>
                <div class="form-group">
                    <select class="ingredient-unit" name="ingredient-unit" required>
                        <option value="">Select unit</option>
                        ${window.availableUnits ? window.availableUnits.map(unit =>
            `<option value="${unit.name}">${unit.name} (${unit.abbreviation})</option>`
        ).join('') : ''}
                    </select>
                </div>
                <div class="form-group">
                    <div class="ingredient-search-container">
                        <input type="text" class="ingredient-search" name="ingredient-search" placeholder="Search ingredients..." autocomplete="off">
                        <div class="autocomplete-dropdown"></div>
                        <select class="ingredient-name" name="ingredient-name" required>
                            <option value="">Select ingredient</option>
                            ${availableIngredients && availableIngredients.length > 0 ? availableIngredients.map(ingredient =>
            `<option value="${ingredient.name}">${ingredient.name}</option>`
        ).join('') : ''}
                        </select>
                    </div>
                </div>
                <button type="button" class="remove-ingredient">Remove</button>
            </div>
        `;

        // Add remove button functionality
        div.querySelector('.remove-ingredient').addEventListener('click', () => {
            div.remove();
        });

        // Add ingredient search functionality
        const searchInput = div.querySelector('.ingredient-search');
        const selectElement = div.querySelector('.ingredient-name');
        const autocompleteDropdown = div.querySelector('.autocomplete-dropdown');
        let activeIndex = -1; 
        
        // Function to update the autocomplete dropdown
        function updateAutocomplete() {
            const searchTerm = searchInput.value.toLowerCase();
            
            // Clear the dropdown
            autocompleteDropdown.innerHTML = '';
            
            if (searchTerm.length === 0) {
                autocompleteDropdown.style.display = 'none';
                return;
            }
            
            // Find matching ingredients
            const matches = availableIngredients ? availableIngredients.filter(ingredient => 
                ingredient.name.toLowerCase().includes(searchTerm)
            ) : [];
            
            if (matches.length === 0) {
                autocompleteDropdown.style.display = 'none';
                return;
            }
            
            // Add matches to dropdown
            matches.forEach((ingredient, index) => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item';
                item.textContent = ingredient.name;
                
                // Highlight the matching part
                const highlightedText = ingredient.name.replace(
                    new RegExp(searchTerm, 'gi'),
                    match => `<strong>${match}</strong>`
                );
                item.innerHTML = highlightedText;
                
                item.addEventListener('click', () => {
                    searchInput.value = ingredient.name;
                    selectElement.value = ingredient.name;
                    autocompleteDropdown.style.display = 'none';
                });
                
                item.addEventListener('mouseenter', () => {
                    setActiveItem(index);
                });
                
                autocompleteDropdown.appendChild(item);
            });
            
            // Show the dropdown
            autocompleteDropdown.style.display = 'block';
            activeIndex = -1;
        }
        
        // Function to set the active item
        function setActiveItem(index) {
            const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
            
            // Remove active class from all items
            items.forEach(item => item.classList.remove('active'));
            
            // Set active class on the selected item
            if (index >= 0 && index < items.length) {
                activeIndex = index;
                items[index].classList.add('active');
                // Ensure the active item is in view
                items[index].scrollIntoView({ block: 'nearest' });
            }
        }
        
        // Function to select the current active item
        function selectActiveItem() {
            const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
            if (activeIndex >= 0 && activeIndex < items.length) {
                const selectedValue = items[activeIndex].textContent;
                searchInput.value = selectedValue;
                selectElement.value = selectedValue;
                autocompleteDropdown.style.display = 'none';
            }
        }
        
        // Input event listener
        searchInput.addEventListener('input', updateAutocomplete);
        
        // Focus event listener
        searchInput.addEventListener('focus', updateAutocomplete);
        
        // Blur event listener
        searchInput.addEventListener('blur', (e) => {
            // Delay hiding to allow click events on dropdown items
            setTimeout(() => {
                autocompleteDropdown.style.display = 'none';
            }, 200);
        });
        
        // Keyboard navigation
        searchInput.addEventListener('keydown', (e) => {
            const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
            
            // Down arrow
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActiveItem(Math.min(activeIndex + 1, items.length - 1));
            }
            // Up arrow
            else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActiveItem(Math.max(activeIndex - 1, 0));
            }
            // Enter
            else if (e.key === 'Enter' && activeIndex >= 0) {
                e.preventDefault();
                selectActiveItem();
            }
            // Tab
            else if (e.key === 'Tab' && items.length > 0) {
                if (activeIndex === -1) {
                    setActiveItem(0);
                } else {
                    selectActiveItem();
                }
            }
            // Escape
            else if (e.key === 'Escape') {
                autocompleteDropdown.style.display = 'none';
            }
        });

        // Sync select value when changed manually
        selectElement.addEventListener('change', () => {
            searchInput.value = selectElement.options[selectElement.selectedIndex].text;
        });

        ingredientsList.appendChild(div);
    };

    // Make loadRecipes accessible to outside functions
    window.loadRecipes = loadRecipes;

    // --- Tag Editor Modal Logic ---
    const tagEditorModal = document.getElementById('tag-editor-modal');
    const tagEditorRecipeNameEl = document.getElementById('tag-editor-recipe-name');
    const tagEditorRecipeIdInput = document.getElementById('tag-editor-recipe-id');
    const tagInput = document.getElementById('tag-input');
    const tagChipsContainer = document.getElementById('tag-chips-container');
    const saveTagsBtn = document.getElementById('save-tags-btn');
    const cancelTagsBtn = document.getElementById('cancel-tags-btn');
    const closeTagModalBtn = tagEditorModal.querySelector('.close-tag-modal-btn');

    let currentRecipeTags = []; // Stores tags for the recipe being edited in the modal
    let originalRecipeTagsForEdit = []; // Stores the initial state of tags when modal opens

    function openTagEditorModal(recipeId, recipeName, currentTagsJson) {
        tagEditorRecipeIdInput.value = recipeId;
        tagEditorRecipeNameEl.textContent = decodeURIComponent(recipeName);
        try {
            const parsedTags = JSON.parse(currentTagsJson || '[]');
            currentRecipeTags = parsedTags.map(tag => {
                if (typeof tag === 'string') return { name: tag, type: 'public', id: undefined };
                // Ensure structure {id?, name, type}, default type to public if missing
                return { id: tag.id, name: tag.name, type: tag.type || 'public' };
            });
            // Deep copy for comparison on save
            originalRecipeTagsForEdit = JSON.parse(JSON.stringify(currentRecipeTags)); 
        } catch (e) {
            console.error('Error parsing current tags:', e);
            currentRecipeTags = [];
            originalRecipeTagsForEdit = [];
        }
        renderTagChipsInModal();
        tagInput.value = '';
        tagEditorModal.style.display = 'block';
        tagInput.focus();
    }

    function closeTagEditorModal() {
        tagEditorModal.style.display = 'none';
        currentRecipeTags = [];
        originalRecipeTagsForEdit = [];
        tagInput.value = '';
    }

    function renderTagChipsInModal() {
        tagChipsContainer.innerHTML = '';
        currentRecipeTags.forEach((tag, index) => {
            const chip = document.createElement('div');
            chip.classList.add('tag-chip', tag.type === 'private' ? 'tag-chip-private' : 'tag-chip-public');
            chip.dataset.index = index;
            chip.innerHTML = `
                <span class="tag-icon">${tag.type === 'private' ? '🔒' : '🌍'}</span>
                <span class="tag-name">${tag.name}</span>
                <button class="remove-tag-chip-btn" title="Remove tag">&times;</button>
            `;
            chip.addEventListener('click', (e) => {
                if (!e.target.classList.contains('remove-tag-chip-btn')) {
                    toggleTagPrivacy(index);
                }
            });
            chip.querySelector('.remove-tag-chip-btn').addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent chip click event
                removeTagFromModal(index);
            });
            tagChipsContainer.appendChild(chip);
        });
    }

    function addTagToModal(tagName) {
        const trimmedName = tagName.trim();
        if (trimmedName && !currentRecipeTags.some(t => t.name.toLowerCase() === trimmedName.toLowerCase())) {
            currentRecipeTags.push({ name: trimmedName, type: 'public' }); // Default to public
            renderTagChipsInModal();
        }
    }

    function removeTagFromModal(index) {
        currentRecipeTags.splice(index, 1);
        renderTagChipsInModal();
    }

    function toggleTagPrivacy(index) {
        const tag = currentRecipeTags[index];
        if (tag) {
            tag.type = tag.type === 'public' ? 'private' : 'public';
            renderTagChipsInModal();
        }
    }

    tagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            const tags = tagInput.value.split(',').map(t => t.trim()).filter(t => t);
            tags.forEach(addTagToModal);
            tagInput.value = '';
        }
    });
    tagInput.addEventListener('blur', () => { // Also add tags on blur if any input remains
        const tags = tagInput.value.split(',').map(t => t.trim()).filter(t => t);
        if (tags.length > 0) {
            tags.forEach(addTagToModal);
            tagInput.value = '';
        }
    });

    saveTagsBtn.addEventListener('click', async () => {
        const recipeId = tagEditorRecipeIdInput.value;
        const modalFinalTags = [...currentRecipeTags]; // Current state from modal

        saveTagsBtn.disabled = true;
        saveTagsBtn.textContent = 'Saving...';

        try {
            const tagsToActuallyRemove = [];
            const tagsToActuallyAdd = [];

            // Determine tags to remove their old association
            for (const originalTag of originalRecipeTagsForEdit) {
                const stillExistsWithSameType = modalFinalTags.some(finalTag => 
                    finalTag.id === originalTag.id && 
                    finalTag.name.toLowerCase() === originalTag.name.toLowerCase() &&
                    finalTag.type === originalTag.type
                );
                if (!stillExistsWithSameType && originalTag.id) {
                    // If it's not in the final list with the exact same id, name, and type,
                    // then its old association (originalTag.type) needs to be removed.
                    tagsToActuallyRemove.push(originalTag);
                }
            }

            // Determine tags to add their new association
            for (const finalTag of modalFinalTags) {
                const existedBeforeWithSameType = originalRecipeTagsForEdit.some(originalTag => 
                    (finalTag.id && originalTag.id === finalTag.id || 
                     !finalTag.id && originalTag.name.toLowerCase() === finalTag.name.toLowerCase()) &&
                    originalTag.type === finalTag.type
                );
                if (!existedBeforeWithSameType) {
                    // If it didn't exist before with the same type (or is brand new),
                    // then its new association (finalTag.type) needs to be added.
                    tagsToActuallyAdd.push(finalTag);
                }
            }

            console.log("Original Tags:", originalRecipeTagsForEdit);
            console.log("Final Modal Tags:", modalFinalTags);
            console.log("API - Tags to remove association for:", tagsToActuallyRemove);
            console.log("API - Tags to add association for:", tagsToActuallyAdd);

            // Perform removals
            for (const tag of tagsToActuallyRemove) {
                // `tag.id` must exist for removal as per previous logic
                await api.removeTagFromRecipe(recipeId, tag.id, tag.type); 
                console.log(`API: Removed association - Name: ${tag.name}, ID: ${tag.id}, Type: ${tag.type}`);
            }

            // Perform additions/updates
            for (const tag of tagsToActuallyAdd) {
                // Backend handles tag creation by name if it doesn't exist, then associates.
                await api.addTagToRecipe(recipeId, tag.name, tag.type);
                console.log(`API: Added/Ensured association - Name: ${tag.name}, Type: ${tag.type}`);
            }

            // Update the local recipe card UI
            const recipeCard = document.querySelector(`.recipe-card[data-id="${recipeId}"]`);
            if (recipeCard) {
                const tagsDisplay = recipeCard.querySelector('.recipe-tags .existing-tags');
                const noTagsPlaceholder = recipeCard.querySelector('.recipe-tags .no-tags-placeholder');
                const addTagButton = recipeCard.querySelector('.add-tag-btn');

                // Public tags are displayed on the card
                const publicTagsForDisplay = modalFinalTags.filter(t => t.type === 'public').map(t => t.name);
                if (tagsDisplay) {
                    tagsDisplay.textContent = publicTagsForDisplay.join(', ');
                    tagsDisplay.style.display = publicTagsForDisplay.length > 0 ? 'inline' : 'none';
                }
                if (noTagsPlaceholder) {
                    noTagsPlaceholder.style.display = publicTagsForDisplay.length > 0 ? 'none' : 'inline';
                }
                // Update the button's data-recipe-tags with the full state from the modal for re-opening
                if (addTagButton) {
                    // Fetch the latest full tag objects (with IDs for newly created tags) from server before updating data attribute
                    // For now, we use modalFinalTags, but ideally, we'd refresh this specific recipe's tags from the backend
                    // to get any new IDs assigned by the backend.
                    // This is a simplification for now.
                    const updatedRecipeData = await api.getRecipe(recipeId); // Re-fetch to get new tag IDs
                    if (updatedRecipeData && updatedRecipeData.tags) {
                         addTagButton.dataset.recipeTags = JSON.stringify(updatedRecipeData.tags);
                    } else {
                        // Fallback if re-fetch fails, use modal state (might lack new IDs)
                        addTagButton.dataset.recipeTags = JSON.stringify(modalFinalTags);
                    }
                }
            }
            
            alert('Tags saved successfully!');
            closeTagEditorModal();
            // Consider a more targeted refresh if window.loadRecipes() is too heavy
            // For example, if createRecipeCard could be called with updated recipe data for just this card.
            // window.loadRecipes(); // This will ensure everything is up-to-date, including new tag IDs.
        } catch (error) {
            console.error('Error saving tags:', error);
            alert(`Failed to save tags: ${error.message || 'An unexpected error occurred. Please check console.'} (Code: ${error.statusCode || 'N/A'})`);
        } finally {
            saveTagsBtn.disabled = false;
            saveTagsBtn.textContent = 'Save Tags';
        }
    });

    cancelTagsBtn.addEventListener('click', closeTagEditorModal);
    closeTagModalBtn.addEventListener('click', closeTagEditorModal);

    // Event delegation for opening the tag editor modal
    document.body.addEventListener('click', (e) => {
        const addTagButton = e.target.closest('.add-tag-btn');
        if (addTagButton) {
            const recipeId = addTagButton.dataset.recipeId;
            const recipeName = addTagButton.dataset.recipeName;
            const currentTagsJson = addTagButton.dataset.recipeTags;
            openTagEditorModal(recipeId, recipeName, currentTagsJson);
        }
    });
});

// Edit recipe
async function editRecipe(id) {
    // Check authentication first
    if (!isAuthenticated()) {
        alert('Please log in to edit recipes.');
        return;
    }

    const form = document.getElementById('recipe-form');
    const ingredientsList = document.getElementById('ingredients-list');
    if (!form || !ingredientsList) {
        console.error('Required form elements not found');
        return;
    }

    try {
        // Show loading state
        form.classList.add('loading');
        
        const recipe = await api.getRecipe(id);
        if (!recipe) {
            throw new Error('Recipe not found');
        }

        // Populate form with recipe data
        document.getElementById('recipe-name').value = recipe.name || '';
        document.getElementById('recipe-description').value = recipe.description || '';
        document.getElementById('recipe-instructions').value = recipe.instructions || '';
        document.getElementById('recipe-source').value = recipe.source || '';
        document.getElementById('recipe-source-url').value = recipe.source_url || '';

        // Clear and repopulate ingredients
        ingredientsList.innerHTML = '';

        // Check if ingredients exist
        if (!recipe.ingredients || recipe.ingredients.length === 0) {
            // Add at least one empty ingredient row
            addIngredientInput();
        } else {
            recipe.ingredients.forEach(ingredient => {
                addIngredientInput();
                const lastInput = ingredientsList.lastElementChild;
                
                if (!lastInput) {
                    console.error('Failed to add ingredient input');
                    return;
                }
                
                // Set ingredient selection
                const nameSelect = lastInput.querySelector('.ingredient-name');
                const searchInput = lastInput.querySelector('.ingredient-search');
                
                if (nameSelect && ingredient.ingredient_name) {
                    nameSelect.value = ingredient.ingredient_name;
                }
                
                if (searchInput && ingredient.ingredient_name) {
                    searchInput.value = ingredient.ingredient_name;
                }
                
                // Set amount and unit
                const amountInput = lastInput.querySelector('.ingredient-amount');
                if (amountInput && ingredient.amount !== undefined) {
                    amountInput.value = ingredient.amount;
                }
                
                // Set the unit by name if available
                if (ingredient.unit_name && window.availableUnits) {
                    const unitSelect = lastInput.querySelector('.ingredient-unit');
                    if (unitSelect) {
                        const matchingUnit = window.availableUnits.find(u => u.name === ingredient.unit_name);
                        if (matchingUnit) {
                            unitSelect.value = matchingUnit.name;
                        } else {
                            console.warn(`Unit "${ingredient.unit_name}" not found in available units`);
                        }
                    }
                }
            });
        }

        // Change form to update mode
        form.dataset.mode = 'edit';
        form.dataset.id = id;

        // Scroll to form
        form.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error loading recipe:', error);
        alert(`Failed to load recipe: ${error.message || 'Please try again.'}`);
    } finally {
        // Remove loading state
        form.classList.remove('loading');
    }
}

// Make the editRecipe function globally available
window.editRecipe = editRecipe;

// Delete recipe
async function deleteRecipe(id) {
    // Check authentication first
    if (!isAuthenticated()) {
        alert('Please log in to delete recipes.');
        return;
    }

    if (!confirm('Are you sure you want to delete this recipe?')) {
        return;
    }

    try {
        await api.deleteRecipe(id);
        alert('Recipe deleted successfully!');
        window.loadRecipes();
    } catch (error) {
        console.error('Error deleting recipe:', error);
        alert(`Failed to delete recipe: ${error.message || 'Please try again.'}`);
    }
} 