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

    // Load recipes and units on page load
    loadRecipes();
    loadUnits();

    // Handle form submission
    recipeForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const ingredients = [];
        const ingredientInputs = ingredientsList.querySelectorAll('.ingredient-input');

        ingredientInputs.forEach(input => {
            ingredients.push({
                name: input.querySelector('.ingredient-name').value,
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
                await api.createRecipe(recipeData);
            }
            recipeForm.reset();
            ingredientsList.innerHTML = '';
            delete recipeForm.dataset.mode;
            delete recipeForm.dataset.id;
            loadRecipes();
        } catch (error) {
            console.error('Error saving recipe:', error);
            alert('Failed to save recipe. Please try again.');
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
            <div class="form-group">
                <input type="text" class="ingredient-name" placeholder="Ingredient name" required>
            </div>
            <div class="form-group">
                <input type="number" class="ingredient-amount" placeholder="Amount" step="0.1" required>
            </div>
            <div class="form-group">
                <select class="ingredient-unit" required>
                    <option value="">Select unit</option>
                    ${window.availableUnits?.map(unit =>
            `<option value="${unit.name}">${unit.name} (${unit.abbreviation})</option>`
        ).join('')}
                </select>
            </div>
            <button type="button" class="remove-ingredient">Remove</button>
        `;

        // Add remove button functionality
        div.querySelector('.remove-ingredient').addEventListener('click', () => {
            div.remove();
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
        loadRecipes();
    } catch (error) {
        console.error('Error deleting recipe:', error);
        alert('Failed to delete recipe. Please try again.');
    }
} 