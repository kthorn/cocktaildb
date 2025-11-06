import { api } from './api.js';
import { isAuthenticated } from './auth.js';

// Error display utilities
function showFieldError(element, message) {
    // Clear any existing error
    clearFieldError(element);

    // Add error class to parent form-group or ingredient-input
    const container = element.closest('.form-group') || element.closest('.ingredient-input');
    if (container) {
        container.classList.add('has-error');
    }

    // Create and add error message
    const errorDiv = document.createElement('div');
    errorDiv.className = 'field-error';
    errorDiv.textContent = message;
    element.parentElement.appendChild(errorDiv);

    // Scroll to first error if not visible
    if (element === document.querySelector('.has-error input, .has-error select, .has-error textarea')) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function clearFieldError(element) {
    const container = element.closest('.form-group') || element.closest('.ingredient-input');
    if (container) {
        container.classList.remove('has-error');
        const errorDiv = container.querySelector('.field-error');
        if (errorDiv) {
            errorDiv.remove();
        }
    }
}

function clearAllErrors() {
    document.querySelectorAll('.has-error').forEach(el => el.classList.remove('has-error'));
    document.querySelectorAll('.field-error').forEach(el => el.remove());
}

// Shared utility functions for recipe management
function isSpecialUnit(unitName) {
    return unitName === 'to top' || unitName === 'to rinse';
}

function validateIngredientAmount(ingredientName, ingredientUnitName, amount) {
    const unit = window.availableUnits?.find(u => u.name === ingredientUnitName);
    const isSpecial = unit && isSpecialUnit(unit.name);
    
    // For special units, allow empty/null amounts, otherwise require positive numbers
    if (!isSpecial && (isNaN(amount) || amount <= 0)) {
        throw new Error(`Amount for "${ingredientName}" must be a positive number`);
    }
    
    // Set amount to null for special units if empty or 0
    return isSpecial && (isNaN(amount) || amount === 0) ? null : amount;
}

function setupAmountInputForUnit(amountInput, unitSelect) {
    const updateAmountField = () => {
        const selectedUnitName = unitSelect.value;
        const isSpecial = isSpecialUnit(selectedUnitName);
        
        if (isSpecial) {
            amountInput.removeAttribute('required');
            amountInput.placeholder = 'Leave empty for special units';
            amountInput.title = 'Amount not needed for this unit type';
        } else {
            amountInput.setAttribute('required', 'required');
            amountInput.placeholder = 'Amount';
            amountInput.title = '';
        }
    };
    
    unitSelect.addEventListener('change', updateAmountField);
    return updateAmountField; // Return function so it can be called immediately for edit mode
}

// Check for duplicate ingredients by ingredient_id
function checkDuplicateIngredients(ingredients, availableIngredients) {
    const ingredientIdCounts = {};
    const duplicates = [];

    ingredients.forEach(ing => {
        const ingredientId = ing.ingredient_id;
        if (ingredientIdCounts[ingredientId]) {
            ingredientIdCounts[ingredientId]++;
        } else {
            ingredientIdCounts[ingredientId] = 1;
        }
    });

    // Find ingredient names for duplicates
    for (const [ingredientId, count] of Object.entries(ingredientIdCounts)) {
        if (count > 1) {
            const ingredient = availableIngredients.find(ing => ing.id === parseInt(ingredientId));
            if (ingredient) {
                duplicates.push(ingredient.name);
            }
        }
    }

    return duplicates;
}

// Clear all duplicate errors and re-validate
function clearAndRevalidateDuplicates(ingredientsList, availableIngredients) {
    // Clear all duplicate errors first
    const allIngredientInputs = ingredientsList.querySelectorAll('.ingredient-input');
    allIngredientInputs.forEach(input => {
        const ingredientNameSelect = input.querySelector('.ingredient-name');
        if (ingredientNameSelect) {
            // Only clear if it's a duplicate error (not other validation errors)
            const container = ingredientNameSelect.closest('.ingredient-input');
            const errorDiv = container?.querySelector('.field-error');
            if (errorDiv && errorDiv.textContent.includes('Duplicate ingredient')) {
                clearFieldError(ingredientNameSelect);
            }
        }
    });

    // Re-validate to check if duplicates still exist
    const currentIngredients = [];
    allIngredientInputs.forEach(input => {
        const ingredientNameSelect = input.querySelector('.ingredient-name');
        const ingredientName = ingredientNameSelect?.value;

        if (ingredientName) {
            const ingredient = availableIngredients.find(ing => ing.name === ingredientName);
            if (ingredient) {
                currentIngredients.push({ ingredient_id: ingredient.id, name: ingredientName });
            }
        }
    });

    // Check if duplicates still exist
    const duplicateNames = checkDuplicateIngredients(currentIngredients, availableIngredients);

    // If duplicates still exist, show errors on those fields
    if (duplicateNames.length > 0) {
        allIngredientInputs.forEach(input => {
            const ingredientNameSelect = input.querySelector('.ingredient-name');
            const ingredientName = ingredientNameSelect?.value;

            if (duplicateNames.includes(ingredientName)) {
                showFieldError(ingredientNameSelect, `Duplicate ingredient: "${ingredientName}" appears multiple times`);
            }
        });
    }
}

function processIngredientData(ingredientInputs, availableIngredients) {
    const ingredients = [];
    let firstError = null;

    ingredientInputs.forEach(input => {
        const ingredientNameSelect = input.querySelector('.ingredient-name');
        const ingredientUnitSelect = input.querySelector('.ingredient-unit');
        const amountInput = input.querySelector('.ingredient-amount');

        const ingredientName = ingredientNameSelect.value;
        const ingredientUnitName = ingredientUnitSelect.value;
        const amount = parseFloat(amountInput.value);

        // Validate and show errors inline
        if (!ingredientName) {
            showFieldError(ingredientNameSelect, 'Please select an ingredient');
            if (!firstError) firstError = ingredientNameSelect;
            return;
        }
        if (!ingredientUnitName) {
            showFieldError(ingredientUnitSelect, `Please select a unit for "${ingredientName}"`);
            if (!firstError) firstError = ingredientUnitSelect;
            return;
        }

        try {
            const finalAmount = validateIngredientAmount(ingredientName, ingredientUnitName, amount);

            const ingredient = availableIngredients.find(ing => ing.name === ingredientName);
            const unit = window.availableUnits?.find(u => u.name === ingredientUnitName);

            if (!ingredient) {
                showFieldError(ingredientNameSelect, `Ingredient "${ingredientName}" not found`);
                if (!firstError) firstError = ingredientNameSelect;
                return;
            }
            if (!unit) {
                showFieldError(ingredientUnitSelect, `Unit "${ingredientUnitName}" not found`);
                if (!firstError) firstError = ingredientUnitSelect;
                return;
            }

            ingredients.push({
                ingredient_id: ingredient.id,
                amount: finalAmount,
                unit_id: unit.id
            });
        } catch (error) {
            showFieldError(amountInput, error.message);
            if (!firstError) firstError = amountInput;
        }
    });

    // If there were errors, scroll to first error and throw
    if (firstError) {
        firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
        throw new Error('Please fix the ingredient errors above');
    }

    // Check for duplicate ingredients
    const duplicateNames = checkDuplicateIngredients(ingredients, availableIngredients);
    if (duplicateNames.length > 0) {
        // Show error on all inputs that have duplicate ingredients
        ingredientInputs.forEach(input => {
            const ingredientNameSelect = input.querySelector('.ingredient-name');
            const ingredientName = ingredientNameSelect.value;

            if (duplicateNames.includes(ingredientName)) {
                showFieldError(ingredientNameSelect, `Duplicate ingredient: "${ingredientName}" appears multiple times`);
                if (!firstError) firstError = ingredientNameSelect;
            }
        });

        if (firstError) {
            firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        throw new Error(`Recipe cannot have duplicate ingredients: ${duplicateNames.join(', ')}`);
    }

    return ingredients;
}

// Declare function in global scope
let addIngredientInput;

document.addEventListener('DOMContentLoaded', () => {  
    const recipeForm = document.getElementById('recipe-form');
    const addIngredientBtn = document.getElementById('add-ingredient');
    const ingredientsList = document.getElementById('ingredients-list');

    if (!recipeForm || !addIngredientBtn || !ingredientsList) {
        console.error('Required elements not found in the DOM');
        return;
    }

    let availableIngredients = [];

    // Add event listeners to clear errors on main form fields
    const recipeNameInput = document.getElementById('recipe-name');
    const recipeInstructionsInput = document.getElementById('recipe-instructions');
    [recipeNameInput, recipeInstructionsInput].forEach(element => {
        if (element) {
            element.addEventListener('input', () => clearFieldError(element));
        }
    });

    // Load units and ingredients on page load
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

        // Clear any existing errors
        clearAllErrors();

        // Check editor permissions first
        if (!api.isEditor()) {
            alert('Editor access required. Only editors and admins can create or edit recipes.');
            return;
        }

        try {
            const ingredientInputs = ingredientsList.querySelectorAll('.ingredient-input');

            if (ingredientInputs.length === 0) {
                throw new Error('Please add at least one ingredient');
            }

            const recipeNameInput = document.getElementById('recipe-name');
            const recipeName = recipeNameInput.value.trim();
            if (!recipeName) {
                showFieldError(recipeNameInput, 'Recipe name is required');
                throw new Error('Please complete all required fields');
            }

            const recipeInstructionsInput = document.getElementById('recipe-instructions');
            const recipeInstructions = recipeInstructionsInput.value.trim();
            if (!recipeInstructions) {
                showFieldError(recipeInstructionsInput, 'Recipe instructions are required');
                throw new Error('Please complete all required fields');
            }

            // Use the shared function to process ingredient data
            const ingredients = processIngredientData(ingredientInputs, availableIngredients);

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

            // Reset button text and page title to add mode
            const submitButton = document.getElementById('submit-button');
            const pageTitle = document.querySelector('.section-title h2');
            if (submitButton) {
                submitButton.textContent = 'Add Recipe';
            }
            if (pageTitle) {
                pageTitle.textContent = 'Add Recipe';
            }
            document.title = 'Add Recipe - Mixology Tools';

            // Add one ingredient row by default after reset
            addIngredientInput();
        } catch (error) {
            console.error('Error saving recipe:', error);
            // Don't show alert for validation errors since they're shown inline
            if (!error.message.includes('Please fix') && !error.message.includes('Please complete')) {
                alert(`Failed to save recipe: ${error.message || 'Please try again.'}`);
            }
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
                    <input type="number" class="ingredient-amount" name="ingredient-amount" placeholder="Amount" step="0.25" min="0">
                </div>
                <div class="form-group">
                    <select class="ingredient-unit" name="ingredient-unit">
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
                        <select class="ingredient-name" name="ingredient-name">
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
            // Re-validate duplicates after removing an ingredient
            clearAndRevalidateDuplicates(ingredientsList, availableIngredients);
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
                    // Trigger change event to validate duplicates
                    selectElement.dispatchEvent(new Event('change', { bubbles: true }));
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
                // Trigger change event to validate duplicates
                selectElement.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
        
        // Input event listener
        searchInput.addEventListener('input', updateAutocomplete);
        
        // Focus event listener
        searchInput.addEventListener('focus', updateAutocomplete);
        
        // Blur event listener
        searchInput.addEventListener('blur', () => {
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

        // Use shared function to set up amount input behavior
        const unitSelect = div.querySelector('.ingredient-unit');
        const amountInput = div.querySelector('.ingredient-amount');
        setupAmountInputForUnit(amountInput, unitSelect);

        // Add event listeners to clear errors on input
        const ingredientNameSelect = div.querySelector('.ingredient-name');
        [amountInput, unitSelect, ingredientNameSelect].forEach(element => {
            if (element) {
                element.addEventListener('input', () => clearFieldError(element));
                element.addEventListener('change', () => {
                    clearFieldError(element);
                    // Re-validate duplicates when ingredient changes
                    if (element === ingredientNameSelect) {
                        clearAndRevalidateDuplicates(ingredientsList, availableIngredients);
                    }
                });
            }
        });

        ingredientsList.appendChild(div);
    };

    // Check for edit parameter in URL
    const urlParams = new URLSearchParams(window.location.search);
    const editRecipeId = urlParams.get('edit');
    if (editRecipeId) {
        console.log('Edit recipe ID found:', editRecipeId);
        // Wait for ingredients and units to load, then edit the recipe
        Promise.all([loadUnits(), loadIngredients()]).then(() => {
            console.log('Units and ingredients loaded, calling editRecipe');
            editRecipe(editRecipeId);
        }).catch(error => {
            console.error('Error loading units/ingredients:', error);
        });
    }
});

// Edit recipe
async function editRecipe(id) {
    console.log('editRecipe called with ID:', id);
    
    // Check editor permissions first
    if (!api.isEditor()) {
        alert('Editor access required. Only editors and admins can edit recipes.');
        return;
    }

    const form = document.getElementById('recipe-form');
    const ingredientsList = document.getElementById('ingredients-list');
    if (!form || !ingredientsList) {
        console.error('Required form elements not found', { form, ingredientsList });
        return;
    }

    try {
        // Show loading state
        form.classList.add('loading');
        
        console.log('Fetching recipe data for ID:', id);
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
                
                // Set the unit first, then amount (order matters for proper field setup)
                const unitSelect = lastInput.querySelector('.ingredient-unit');
                const amountInput = lastInput.querySelector('.ingredient-amount');
                
                if (ingredient.unit_name && window.availableUnits && unitSelect) {
                    const matchingUnit = window.availableUnits.find(u => u.name === ingredient.unit_name);
                    if (matchingUnit) {
                        unitSelect.value = matchingUnit.name;
                        // Trigger change event to update amount field properties
                        unitSelect.dispatchEvent(new Event('change'));
                    } else {
                        console.warn(`Unit "${ingredient.unit_name}" not found in available units`);
                    }
                }
                
                // Set amount after unit is set (so special unit logic applies)
                if (amountInput) {
                    if (ingredient.amount !== undefined && ingredient.amount !== null) {
                        amountInput.value = ingredient.amount;
                    } else {
                        amountInput.value = ''; // Clear for null amounts
                    }
                }
            });
        }

        // Change form to update mode
        form.dataset.mode = 'edit';
        form.dataset.id = id;

        // Update button text and page title for edit mode
        const submitButton = document.getElementById('submit-button');
        const pageTitle = document.querySelector('.section-title h2');
        if (submitButton) {
            submitButton.textContent = 'Update Recipe';
        }
        if (pageTitle) {
            pageTitle.textContent = 'Edit Recipe';
        }
        // Update page title in browser tab
        document.title = 'Edit Recipe - Mixology Tools';

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

