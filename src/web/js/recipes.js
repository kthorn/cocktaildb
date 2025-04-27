import { api } from './api.js';

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
            console.log('Loaded ingredients:', availableIngredients);
        } catch (error) {
            console.error('Error loading ingredients:', error);
        }
    }

    // Handle form submission
    recipeForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const ingredients = [];
        const ingredientInputs = ingredientsList.querySelectorAll('.ingredient-input');

        ingredientInputs.forEach(input => {
            const ingredientName = input.querySelector('.ingredient-name').value;
            const ingredient = availableIngredients.find(ing => ing.name === ingredientName);
            
            if (!ingredient) {
                throw new Error(`Ingredient "${ingredientName}" not found`);
            }

            ingredients.push({
                ingredient_id: ingredient.id,
                amount: parseFloat(input.querySelector('.ingredient-amount').value),
                unit: input.querySelector('.ingredient-unit').value
            });
        });

        const recipeData = {
            name: document.getElementById('recipe-name').value,
            description: document.getElementById('recipe-description').value,
            instructions: document.getElementById('recipe-instructions').value,
            ingredients: ingredients
        };

        try {
            if (recipeForm.dataset.mode === 'edit') {
                await api.updateRecipe(recipeForm.dataset.id, recipeData);
            } else {
                const response = await api.createRecipe(recipeData);
                console.log('Recipe created:', response);
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
            displayRecipes(recipes);
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

    // Add new ingredient input to the form
    function addIngredientInput() {
        const div = document.createElement('div');
        div.className = 'ingredient-input';
        div.innerHTML = `
            <div class="ingredient-fields">
                <div class="form-group">
                    <input type="number" class="ingredient-amount" placeholder="Amount" step="1" required>
                </div>
                <div class="form-group">
                    <select class="ingredient-unit" required>
                        <option value="">Select unit</option>
                        ${window.availableUnits?.map(unit =>
            `<option value="${unit.name}">${unit.name} (${unit.abbreviation})</option>`
        ).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <div class="ingredient-search-container">
                        <input type="text" class="ingredient-search" placeholder="Search ingredients...">
                        <select class="ingredient-name" required>
                            <option value="">Select ingredient</option>
                            ${availableIngredients.map(ingredient =>
            `<option value="${ingredient.name}">${ingredient.name}</option>`
        ).join('')}
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
        
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            const options = selectElement.options;
            
            for (let i = 1; i < options.length; i++) {
                const optionText = options[i].text.toLowerCase();
                if (optionText.includes(searchTerm)) {
                    options[i].style.display = '';
                } else {
                    options[i].style.display = 'none';
                }
            }
            
            // If search term matches exactly one option, select it
            const visibleOptions = Array.from(options).slice(1).filter(opt => 
                opt.style.display !== 'none'
            );
            
            if (visibleOptions.length === 1) {
                selectElement.value = visibleOptions[0].value;
            }
        });

        // Sync select value to search input when changed manually
        selectElement.addEventListener('change', () => {
            searchInput.value = selectElement.options[selectElement.selectedIndex].text;
        });

        ingredientsList.appendChild(div);
    }

    // Display recipes in the container
    function displayRecipes(recipes) {
        recipesContainer.innerHTML = '';

        if (recipes.length === 0) {
            recipesContainer.innerHTML = '<p>No recipes found.</p>';
            return;
        }

        recipes.forEach(recipe => {
            const card = document.createElement('div');
            card.className = 'recipe-card';
            card.innerHTML = `
                <h4>${recipe.name}</h4>
                <p>${recipe.description || 'No description'}</p>
                <div class="ingredients">
                    <h5>Ingredients:</h5>
                    <ul>
                        ${recipe.ingredients.map(ing =>
                `<li>${ing.amount} ${ing.unit} ${ing.name}</li>`
            ).join('')}
                    </ul>
                </div>
                <div class="instructions">
                    <h5>Instructions:</h5>
                    <p>${recipe.instructions}</p>
                </div>
                <div class="card-actions">
                    <button onclick="editRecipe(${recipe.id})">Edit</button>
                    <button onclick="deleteRecipe(${recipe.id})">Delete</button>
                </div>
            `;
            recipesContainer.appendChild(card);
        });
    }

    // Make loadRecipes accessible to outside functions
    window.loadRecipes = loadRecipes;
});

// Edit recipe
async function editRecipe(id) {
    const form = document.getElementById('recipe-form');
    if (!form) {
        console.error('Recipe form not found');
        return;
    }

    try {
        const recipe = await api.getRecipe(id);

        // Populate form with recipe data
        document.getElementById('recipe-name').value = recipe.name;
        document.getElementById('recipe-description').value = recipe.description || '';
        document.getElementById('recipe-instructions').value = recipe.instructions;

        // Clear and repopulate ingredients
        const ingredientsList = document.getElementById('ingredients-list');
        ingredientsList.innerHTML = '';

        recipe.ingredients.forEach(ingredient => {
            addIngredientInput();
            const lastInput = ingredientsList.lastElementChild;
            lastInput.querySelector('.ingredient-name').value = ingredient.name;
            lastInput.querySelector('.ingredient-amount').value = ingredient.amount;
            lastInput.querySelector('.ingredient-unit').value = ingredient.unit;
            // Also set the search input value
            lastInput.querySelector('.ingredient-search').value = ingredient.name;
        });

        // Change form to update mode
        form.dataset.mode = 'edit';
        form.dataset.id = id;

        // Scroll to form
        form.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error loading recipe:', error);
        alert('Failed to load recipe. Please try again.');
    }
}

// Delete recipe
async function deleteRecipe(id) {
    if (!confirm('Are you sure you want to delete this recipe?')) {
        return;
    }

    try {
        await api.deleteRecipe(id);
        window.loadRecipes();
    } catch (error) {
        console.error('Error deleting recipe:', error);
        alert('Failed to delete recipe. Please try again.');
    }
} 