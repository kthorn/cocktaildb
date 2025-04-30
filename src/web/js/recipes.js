import { api } from './api.js';
import { initAuth, isAuthenticated } from './auth.js';
import config from './config.js';

document.addEventListener('DOMContentLoaded', () => {
    // Initialize authentication
    initAuth();
    
    const recipeForm = document.getElementById('recipe-form');
    const recipesContainer = document.getElementById('recipes-container');
    const searchInput = document.getElementById('recipe-search');
    const addIngredientBtn = document.getElementById('add-ingredient');
    const ingredientsList = document.getElementById('ingredients-list');

    // Add debug button
    const debugSection = document.createElement('div');
    debugSection.innerHTML = `
        <div style="margin-top: 20px; padding: 10px; background: #f0f0f0; border-radius: 5px;">
            <h4>Debug Tools</h4>
            <div>
                <button id="check-token-btn">Check Authentication Token</button>
                <button id="test-api-btn" style="margin-left: 10px;">Test API Request</button>
                <button id="validate-token-btn" style="margin-left: 10px;">Validate Token Parameters</button>
                <button id="test-post-btn" style="margin-left: 10px;">Test POST Request</button>
                <button id="test-auth-btn" style="margin-left: 10px;">Test Auth Endpoint</button>
            </div>
            <div style="margin-top: 10px;">
                <button id="force-logout-btn">Force Logout & Re-Login</button>
            </div>
            <div id="token-info" style="margin-top: 10px; font-family: monospace; white-space: pre-wrap; word-break: break-all;"></div>
        </div>
    `;
    document.querySelector('main').appendChild(debugSection);

    // Add event listener for the debug button
    document.getElementById('check-token-btn').addEventListener('click', () => {
        const tokenInfo = document.getElementById('token-info');
        const token = localStorage.getItem('token');
        
        if (!token) {
            tokenInfo.innerHTML = 'No token found in localStorage';
            return;
        }
        
        try {
            // For JWT tokens, try to decode and check expiration
            const parts = token.split('.');
            if (parts.length === 3) {
                // It's likely a JWT token
                const payload = JSON.parse(atob(parts[1]));
                const expDate = payload.exp ? new Date(payload.exp * 1000) : 'Not found';
                const isExpired = payload.exp ? (payload.exp * 1000 < Date.now()) : 'Unknown';
                
                tokenInfo.innerHTML = `Token found!\nType: JWT\nExpires: ${expDate}\nExpired: ${isExpired}\n\nPayload: ${JSON.stringify(payload, null, 2)}`;
            } else {
                // Not a JWT token or can't be parsed
                tokenInfo.innerHTML = `Token found, but not a standard JWT format:\n${token}`;
            }
        } catch (error) {
            tokenInfo.innerHTML = `Token found, but error parsing it: ${error.message}\n${token}`;
        }
    });

    // Add test API request button
    document.getElementById('test-api-btn').addEventListener('click', async () => {
        const tokenInfo = document.getElementById('token-info');
        tokenInfo.innerHTML = 'Testing API request with different auth methods...';
        
        const token = localStorage.getItem('token');
        if (!token) {
            tokenInfo.innerHTML = 'No token found to test with';
            return;
        }
        
        // Try multiple authentication methods
        const results = [];
        const authMethods = [
            { name: "No auth", headers: {} },
            { name: "Bearer token", headers: { 'Authorization': `Bearer ${token}` } },
            { name: "Raw token", headers: { 'Authorization': token } },
            { name: "ID token instead", headers: { 'Authorization': `Bearer ${localStorage.getItem('id_token') || 'not-found'}` } }
        ];
        
        for (const method of authMethods) {
            try {
                // Make a simple API request with the specific auth method
                const options = {
                    method: 'GET',
                    mode: 'cors',
                    credentials: 'omit',  // Must be 'omit' for a server with wildcard CORS origin
                    headers: {
                        'Content-Type': 'application/json',
                        ...method.headers
                    }
                };
                
                const response = await fetch(`${config.apiUrl}/recipes`, options);
                let responseText = '';
                
                try {
                    const responseData = await response.json();
                    responseText = JSON.stringify(responseData).substring(0, 200) + 
                        (JSON.stringify(responseData).length > 200 ? '...' : '');
                } catch (e) {
                    responseText = 'Could not parse JSON response';
                }
                
                results.push(`Method: ${method.name}
Status: ${response.status}
Response: ${responseText}`);
            } catch (error) {
                results.push(`Method: ${method.name}
Error: ${error.message}`);
            }
        }
        
        tokenInfo.innerHTML = `API Test Results:\n\n${results.join('\n\n')}`;
    });

    // Add token validation button
    document.getElementById('validate-token-btn').addEventListener('click', () => {
        const tokenInfo = document.getElementById('token-info');
        const token = localStorage.getItem('token');
        
        if (!token) {
            tokenInfo.innerHTML = 'No token found in localStorage';
            return;
        }
        
        try {
            // Parse the token
            const parts = token.split('.');
            if (parts.length !== 3) {
                tokenInfo.innerHTML = 'Token is not a valid JWT format (need 3 parts)';
                return;
            }
            
            const payload = JSON.parse(atob(parts[1]));
            
            // Validate against expected Cognito parameters
            const errors = [];
            const warnings = [];
            
            // Check expiration
            if (payload.exp) {
                const expTime = payload.exp * 1000;
                const now = Date.now();
                const expDate = new Date(expTime);
                
                if (expTime < now) {
                    errors.push(`TOKEN EXPIRED: Expired on ${expDate}`);
                } else {
                    const minutesLeft = Math.round((expTime - now) / (60 * 1000));
                    if (minutesLeft < 30) {
                        warnings.push(`Token expires soon: ${minutesLeft} minutes left`);
                    }
                }
            } else {
                warnings.push('Token has no expiration claim');
            }
            
            // Check issuer
            const expectedIssuer = `https://cognito-idp.${config.region || 'us-east-1'}.amazonaws.com/${config.userPoolId}`;
            if (payload.iss !== expectedIssuer) {
                errors.push(`Issuer mismatch: Got "${payload.iss}", expected "${expectedIssuer}"`);
            }
            
            // Check client ID
            if (payload.client_id && payload.client_id !== config.clientId) {
                errors.push(`Client ID mismatch: Got "${payload.client_id}", expected "${config.clientId}"`);
            }
            if (payload.aud && payload.aud !== config.clientId) {
                errors.push(`Audience mismatch: Got "${payload.aud}", expected "${config.clientId}"`);
            }
            
            // Build results
            let results = `Token validation results:\n\n`;
            if (errors.length > 0) {
                results += `ERRORS (${errors.length}):\n${errors.map(e => `- ${e}`).join('\n')}\n\n`;
            }
            if (warnings.length > 0) {
                results += `WARNINGS (${warnings.length}):\n${warnings.map(w => `- ${w}`).join('\n')}\n\n`;
            }
            
            if (errors.length === 0 && warnings.length === 0) {
                results += `✅ Token appears valid based on basic checks\n\n`;
            }
            
            results += `Token payload:\n${JSON.stringify(payload, null, 2)}`;
            tokenInfo.innerHTML = results;
            
        } catch (error) {
            tokenInfo.innerHTML = `Error validating token: ${error.message}`;
        }
    });

    // Add event listener for the POST test button
    document.getElementById('test-post-btn').addEventListener('click', async () => {
        const tokenInfo = document.getElementById('token-info');
        tokenInfo.innerHTML = 'Testing POST request...';
        
        const token = localStorage.getItem('token');
        if (!token) {
            tokenInfo.innerHTML = 'No token found to test with';
            return;
        }
        
        // Try multiple authentication methods for POST
        const results = [];
        const authMethods = [
            { name: "Bearer token", headers: { 'Authorization': `Bearer ${token}` } },
            { name: "Bearer ID token", headers: { 'Authorization': `Bearer ${localStorage.getItem('id_token') || 'not-found'}` } }
        ];
        
        // Create a very simple recipe for testing
        const testRecipe = {
            name: "Test Recipe " + new Date().toISOString(),
            description: "Test recipe created via debug tool",
            instructions: "This is a test",
            ingredients: []
        };
        
        for (const method of authMethods) {
            try {
                // Make a POST request with the specific auth method
                const options = {
                    method: 'POST',
                    mode: 'cors',
                    credentials: 'omit',  // Must be 'omit' for a server with wildcard CORS origin
                    headers: {
                        'Content-Type': 'application/json',
                        ...method.headers
                    },
                    body: JSON.stringify(testRecipe)
                };
                
                // Show the exact request being sent
                console.log(`Testing POST with ${method.name}:`, options);
                
                const response = await fetch(`${config.apiUrl}/recipes`, options);
                let responseText = '';
                let statusText = `${response.status} ${response.statusText}`;
                
                try {
                    const responseData = await response.json();
                    responseText = JSON.stringify(responseData).substring(0, 200) + 
                        (JSON.stringify(responseData).length > 200 ? '...' : '');
                } catch (e) {
                    responseText = 'Could not parse JSON response';
                }
                
                results.push(`Method: ${method.name}
Status: ${statusText}
Response: ${responseText}`);
            } catch (error) {
                results.push(`Method: ${method.name}
Error: ${error.message}`);
            }
        }
        
        tokenInfo.innerHTML = `POST Test Results:\n\n${results.join('\n\n')}`;
    });

    // Add a test for auth endpoint
    document.getElementById('test-auth-btn').addEventListener('click', async () => {
        const tokenInfo = document.getElementById('token-info');
        tokenInfo.innerHTML = 'Testing Auth endpoint...';
        
        try {
            // Test with ID token
            const idToken = localStorage.getItem('id_token');
            const accessToken = localStorage.getItem('token');
            
            const results = [];
            
            // Test with ID token
            if (idToken) {
                try {
                    const options = {
                        method: 'GET',
                        mode: 'cors',
                        credentials: 'omit',
                        headers: {
                            'Authorization': `Bearer ${idToken}`
                        }
                    };
                    
                    const response = await fetch(`${config.apiUrl}/auth`, options);
                    const data = await response.json();
                    
                    results.push(`ID Token Test:
Status: ${response.status}
Response: ${JSON.stringify(data)}`);
                } catch (error) {
                    results.push(`ID Token Test Error: ${error.message}`);
                }
            }
            
            // Test with access token
            if (accessToken) {
                try {
                    const options = {
                        method: 'GET',
                        mode: 'cors',
                        credentials: 'omit',
                        headers: {
                            'Authorization': `Bearer ${accessToken}`
                        }
                    };
                    
                    const response = await fetch(`${config.apiUrl}/auth`, options);
                    const data = await response.json();
                    
                    results.push(`Access Token Test:
Status: ${response.status}
Response: ${JSON.stringify(data)}`);
                } catch (error) {
                    results.push(`Access Token Test Error: ${error.message}`);
                }
            }
            
            tokenInfo.innerHTML = `Auth Endpoint Test Results:\n\n${results.join('\n\n')}`;
            
        } catch (error) {
            tokenInfo.innerHTML = `Auth Test Error: ${error.message}`;
        }
    });

    // Force logout and re-login button
    document.getElementById('force-logout-btn').addEventListener('click', () => {
        // Clear token from localStorage
        localStorage.removeItem('token');
        localStorage.removeItem('id_token');
        localStorage.removeItem('username');
        
        // Redirect to login immediately
        window.location.href = `${config.cognitoDomain}/login?client_id=${config.clientId}&response_type=token&scope=email+openid+profile&redirect_uri=${encodeURIComponent(window.location.origin + '/callback.html')}`;
    });

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

        // Check authentication first
        if (!isAuthenticated()) {
            alert('Please log in to create or edit recipes.');
            return;
        }

        const ingredients = [];
        const ingredientInputs = ingredientsList.querySelectorAll('.ingredient-input');

        ingredientInputs.forEach(input => {
            const ingredientName = input.querySelector('.ingredient-name').value;
            const ingredientUnitName = input.querySelector('.ingredient-unit').value;
            const amountInput = input.querySelector('.ingredient-amount');
            const amount = parseFloat(amountInput.value);
            
            // Find the ingredient by name
            const ingredient = availableIngredients.find(ing => ing.name === ingredientName);
            if (!ingredient) {
                throw new Error(`Ingredient "${ingredientName}" not found`);
            }

            // Find the unit by name
            const unit = window.availableUnits.find(u => u.name === ingredientUnitName);
            if (!ingredientUnitName) {
                throw new Error(`Please select a unit for "${ingredientName}"`);
            }
            if (!unit) {
                throw new Error(`Unit "${ingredientUnitName}" not found`);
            }

            if (amount < 0) {
                throw new Error(`Amount for "${ingredientName}" cannot be negative`);
            }

            ingredients.push({
                ingredient_id: ingredient.id,
                amount: amount,
                unit_id: unit.id  // Send unit_id instead of unit name
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
                    <input type="number" class="ingredient-amount" name="ingredient-amount" placeholder="Amount" step="0.25" min="0" required>
                </div>
                <div class="form-group">
                    <select class="ingredient-unit" name="ingredient-unit" required>
                        <option value="">Select unit</option>
                        ${window.availableUnits?.map(unit =>
            `<option value="${unit.name}">${unit.name} (${unit.abbreviation})</option>`
        ).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <div class="ingredient-search-container">
                        <input type="text" class="ingredient-search" name="ingredient-search" placeholder="Search ingredients..." autocomplete="off">
                        <div class="autocomplete-dropdown"></div>
                        <select class="ingredient-name" name="ingredient-name" required>
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
            const matches = availableIngredients.filter(ingredient => 
                ingredient.name.toLowerCase().includes(searchTerm)
            );
            
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
            
            // For debugging - log recipe ingredients to console
            console.log('Recipe ingredients:', recipe.ingredients);
            
            card.innerHTML = `
                <h4>${recipe.name}</h4>
                <p>${recipe.description || 'No description'}</p>
                <div class="ingredients">
                    <h5>Ingredients</h5>
                    <ul>
                        ${recipe.ingredients.map(ing => {
                            // Format with proper spaces between amount, unit and ingredient name
                            const unitDisplay = ing.unit_name ? `${ing.unit_name} ` : '';
                            
                            // Try multiple possible property names for ingredient full name
                            // in order of preference
                            const ingredientName = ing.full_name || ing.ingredient_name || ing.name || 'Unknown ingredient';
                            
                            return `<li>${ing.amount} ${unitDisplay}${ingredientName}</li>`;
                        }).join('')}
                    </ul>
                </div>
                <div class="instructions">
                    <h5>Instructions</h5>
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
    // Check authentication first
    if (!isAuthenticated()) {
        alert('Please log in to edit recipes.');
        return;
    }

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
            
            // Set ingredient selection
            lastInput.querySelector('.ingredient-name').value = ingredient.ingredient_name;
            lastInput.querySelector('.ingredient-search').value = ingredient.ingredient_name;
            
            // Set amount and unit
            lastInput.querySelector('.ingredient-amount').value = ingredient.amount;
            
            // Set the unit by name if available
            if (ingredient.unit_name && window.availableUnits) {
                const unitSelect = lastInput.querySelector('.ingredient-unit');
                const matchingUnit = window.availableUnits.find(u => u.name === ingredient.unit_name);
                if (matchingUnit) {
                    unitSelect.value = matchingUnit.name;
                } else {
                    console.warn(`Unit "${ingredient.unit_name}" not found in available units`);
                }
            }
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
        window.loadRecipes();
    } catch (error) {
        console.error('Error deleting recipe:', error);
        alert('Failed to delete recipe. Please try again.');
    }
} 