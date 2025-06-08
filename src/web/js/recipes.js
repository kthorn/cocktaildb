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
            // Use the centralized batching logic from api.js
            const fullRecipes = await api.getRecipesWithFullData();
            displayRecipes(fullRecipes, recipesContainer, true, loadRecipes);
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