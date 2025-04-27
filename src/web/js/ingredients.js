import { api } from './api.js';

document.addEventListener('DOMContentLoaded', () => {
    const ingredientForm = document.getElementById('ingredient-form');
    const ingredientsContainer = document.getElementById('ingredients-container');
    const searchInput = document.getElementById('ingredient-search');

    if (!ingredientForm || !ingredientsContainer || !searchInput) {
        console.error('Required elements not found in the DOM');
        return;
    }

    // Load ingredients on page load
    loadIngredients();

    // Handle form submission
    ingredientForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const ingredientData = {
            name: document.getElementById('ingredient-name').value,
            category: document.getElementById('ingredient-category').value,
            description: document.getElementById('ingredient-description').value
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
            delete ingredientForm.dataset.mode;
            delete ingredientForm.dataset.id;
            loadIngredients();
        } catch (error) {
            console.error('Error saving ingredient:', error);
            if (error.message.includes('already exists')) {
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

    // Load and display ingredients
    async function loadIngredients() {
        try {
            const ingredients = await api.getIngredients();
            displayIngredients(ingredients);
        } catch (error) {
            console.error('Error loading ingredients:', error);
            ingredientsContainer.innerHTML = '<p>Error loading ingredients. Please try again later.</p>';
        }
    }

    // Display ingredients in the container
    function displayIngredients(ingredients) {
        ingredientsContainer.innerHTML = '';

        if (ingredients.length === 0) {
            ingredientsContainer.innerHTML = '<p>No ingredients found.</p>';
            return;
        }

        ingredients.forEach(ingredient => {
            const card = document.createElement('div');
            card.className = 'ingredient-card';
            card.innerHTML = `
                <h4>${ingredient.name}</h4>
                <p><strong>Category:</strong> ${ingredient.category}</p>
                <p>${ingredient.description || 'No description'}</p>
                <div class="card-actions">
                    <button onclick="editIngredient(${ingredient.id})">Edit</button>
                    <button onclick="deleteIngredient(${ingredient.id})">Delete</button>
                </div>
            `;
            ingredientsContainer.appendChild(card);
        });
    }
});

// Edit ingredient
async function editIngredient(id) {
    const form = document.getElementById('ingredient-form');
    if (!form) {
        console.error('Ingredient form not found');
        return;
    }

    try {
        const ingredient = await api.getIngredient(id);

        // Populate form with ingredient data
        document.getElementById('ingredient-name').value = ingredient.name;
        document.getElementById('ingredient-category').value = ingredient.category;
        document.getElementById('ingredient-description').value = ingredient.description || '';

        // Change form to update mode
        form.dataset.mode = 'edit';
        form.dataset.id = id;

        // Scroll to form
        form.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error loading ingredient:', error);
        alert('Failed to load ingredient. Please try again.');
    }
}

// Delete ingredient
async function deleteIngredient(id) {
    if (!confirm('Are you sure you want to delete this ingredient?')) {
        return;
    }

    try {
        await api.deleteIngredient(id);
        loadIngredients();
    } catch (error) {
        console.error('Error deleting ingredient:', error);
        alert('Failed to delete ingredient. Please try again.');
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