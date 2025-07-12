import { api } from './api.js';
import { isAuthenticated } from './auth.js';

document.addEventListener('DOMContentLoaded', () => {
    setupAdminPage();
});

function setupAdminPage() {
    const downloadBtn = document.getElementById('download-db-btn');
    const downloadTemplateBtn = document.getElementById('download-template-btn');
    const fileInput = document.getElementById('recipe-file-input');
    const uploadBtn = document.getElementById('upload-recipes-btn');
    
    // Ingredient upload elements
    const downloadIngredientTemplateBtn = document.getElementById('download-ingredient-template-btn');
    const ingredientFileInput = document.getElementById('ingredient-file-input');
    const uploadIngredientsBtn = document.getElementById('upload-ingredients-btn');
    
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadDatabase);
    }
    
    if (downloadTemplateBtn) {
        downloadTemplateBtn.addEventListener('click', downloadTemplate);
    }
    
    if (fileInput) {
        fileInput.addEventListener('change', handleFileSelection);
    }
    
    if (uploadBtn) {
        uploadBtn.addEventListener('click', handleBulkUpload);
    }
    
    // Ingredient upload event listeners
    if (downloadIngredientTemplateBtn) {
        downloadIngredientTemplateBtn.addEventListener('click', downloadIngredientTemplate);
    }
    
    if (ingredientFileInput) {
        ingredientFileInput.addEventListener('change', handleIngredientFileSelection);
    }
    
    if (uploadIngredientsBtn) {
        uploadIngredientsBtn.addEventListener('click', handleBulkIngredientUpload);
    }
    
    // Check authentication and show/hide admin tools accordingly
    updateUIBasedOnAuth();
}

function updateUIBasedOnAuth() {
    const adminTools = document.querySelector('.admin-tools');
    
    if (!isAuthenticated()) {
        adminTools.innerHTML = `
            <div class="card-container">
                <p>Please log in to access admin tools.</p>
            </div>
        `;
        return;
    }
    
    // User is authenticated, show admin tools
    adminTools.style.display = 'block';
}

async function downloadDatabase() {
    const downloadBtn = document.getElementById('download-db-btn');
    const originalText = downloadBtn.textContent;
    
    try {
        // Update button to show loading state
        downloadBtn.textContent = 'Downloading...';
        downloadBtn.disabled = true;
        
        // Make API call to download database
        const response = await fetch(`${api.baseUrl}/admin/database/download`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('id_token')}`
            }
        });
        
        if (!response.ok) {
            throw new Error(`Download failed: ${response.status} ${response.statusText}`);
        }
        
        // Get the blob from response
        const blob = await response.blob();
        
        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Generate filename with timestamp
        const now = new Date();
        const timestamp = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
        a.download = `cocktaildb-backup-${timestamp}.db`;
        
        // Trigger download
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        // Clean up the blob URL
        window.URL.revokeObjectURL(url);
        
        // Show success message
        showMessage('Database downloaded successfully!', 'success');
        
    } catch (error) {
        console.error('Error downloading database:', error);
        showMessage(`Error downloading database: ${error.message}`, 'error');
    } finally {
        // Restore button state
        downloadBtn.textContent = originalText;
        downloadBtn.disabled = false;
    }
}

function showMessage(message, type = 'info') {
    // Create message element using existing notification styles
    const messageDiv = document.createElement('div');
    messageDiv.className = `notification ${type}`;
    messageDiv.textContent = message;
    
    // Insert at top of main section
    const mainSection = document.querySelector('main section');
    mainSection.insertBefore(messageDiv, mainSection.firstChild);
    
    // Remove message after 5 seconds
    setTimeout(() => {
        if (messageDiv.parentNode) {
            messageDiv.parentNode.removeChild(messageDiv);
        }
    }, 5000);
}

// Bulk upload functionality
function downloadTemplate() {
    const template = {
        recipes: [
            {
                name: "Example Cocktail",
                description: "A delicious example cocktail",
                instructions: "1. Add ingredients to shaker\n2. Shake well with ice\n3. Strain into glass\n4. Garnish and serve",
                source: "Classic Cocktail Book",
                source_url: "https://example.com/cocktail-recipes",
                ingredients: [
                    {
                        ingredient_name: "Vodka",
                        amount: 2,
                        unit_name: "oz"
                    },
                    {
                        ingredient_name: "Lime Juice",
                        amount: 0.5,
                        unit_name: "oz"
                    },
                    {
                        ingredient_name: "Simple Syrup",
                        amount: 0.25,
                        unit_name: "oz"
                    }
                ]
            },
            {
                name: "Second Example",
                description: "Another example recipe",
                instructions: "1. Build ingredients in glass\n2. Stir gently\n3. Serve",
                source: "Bartender's Guide",
                source_url: "https://example.com/gin-tonic",
                ingredients: [
                    {
                        ingredient_name: "Gin",
                        amount: 2,
                        unit_name: "oz"
                    },
                    {
                        ingredient_name: "Tonic Water",
                        amount: 4,
                        unit_name: "oz"
                    }
                ]
            }
        ]
    };
    
    // Create and download the template
    const blob = new Blob([JSON.stringify(template, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cocktail-recipes-template.json';
    
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    
    showMessage('Template downloaded successfully!', 'success');
}

function handleFileSelection(event) {
    const file = event.target.files[0];
    const uploadBtn = document.getElementById('upload-recipes-btn');
    
    if (file) {
        // Validate file type
        if (!file.type.includes('json')) {
            showMessage('Please select a JSON file', 'error');
            event.target.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        // Validate file size (limit to 5MB)
        if (file.size > 5 * 1024 * 1024) {
            showMessage('File too large. Please select a file smaller than 5MB', 'error');
            event.target.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        uploadBtn.disabled = false;
    } else {
        uploadBtn.disabled = true;
    }
}

async function handleBulkUpload() {
    const fileInput = document.getElementById('recipe-file-input');
    const file = fileInput.files[0];
    
    if (!file) {
        showMessage('Please select a file first', 'error');
        return;
    }
    
    try {
        // Read and parse the JSON file
        const fileText = await readFile(file);
        let recipesData;
        
        try {
            recipesData = JSON.parse(fileText);
        } catch (error) {
            showMessage('Invalid JSON file. Please check the file format.', 'error');
            return;
        }
        
        // Validate JSON structure
        if (!validateJsonStructure(recipesData)) {
            return; // Error message already shown in validation
        }
        
        // Show progress
        showUploadProgress(true);
        
        // Upload recipes
        const result = await api.bulkUploadRecipes(recipesData);
        
        // Hide progress
        showUploadProgress(false);
        
        // Display results
        displayUploadResults(result);
        
        // Clear file input
        fileInput.value = '';
        document.getElementById('upload-recipes-btn').disabled = true;
        
    } catch (error) {
        showUploadProgress(false);
        console.error('Error uploading recipes:', error);
        showMessage(`Error uploading recipes: ${error.message}`, 'error');
    }
}

function readFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = reject;
        reader.readAsText(file);
    });
}

function validateJsonStructure(data) {
    // Check if it has the recipes array
    if (!data || !Array.isArray(data.recipes)) {
        showMessage('JSON file must contain a "recipes" array', 'error');
        return false;
    }
    
    if (data.recipes.length === 0) {
        showMessage('Recipes array cannot be empty', 'error');
        return false;
    }
    
    // Check each recipe has required fields
    for (let i = 0; i < data.recipes.length; i++) {
        const recipe = data.recipes[i];
        
        if (!recipe.name || typeof recipe.name !== 'string') {
            showMessage(`Recipe ${i + 1} must have a "name" field`, 'error');
            return false;
        }
        
        if (!Array.isArray(recipe.ingredients)) {
            showMessage(`Recipe "${recipe.name}" must have an "ingredients" array`, 'error');
            return false;
        }
        
        if (recipe.ingredients.length === 0) {
            showMessage(`Recipe "${recipe.name}" must have at least one ingredient`, 'error');
            return false;
        }
        
        // Check each ingredient
        for (let j = 0; j < recipe.ingredients.length; j++) {
            const ingredient = recipe.ingredients[j];
            
            if (!ingredient.ingredient_name || typeof ingredient.ingredient_name !== 'string') {
                showMessage(`Recipe "${recipe.name}" ingredient ${j + 1} must have an "ingredient_name" field`, 'error');
                return false;
            }
        }
    }
    
    return true;
}

function showUploadProgress(show) {
    const progressDiv = document.getElementById('upload-progress');
    const uploadBtn = document.getElementById('upload-recipes-btn');
    
    if (show) {
        progressDiv.style.display = 'block';
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Uploading...';
    } else {
        progressDiv.style.display = 'none';
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload Recipes';
    }
}

function displayUploadResults(result) {
    const resultsDiv = document.getElementById('upload-results');
    
    let html = '<div class="upload-results">';
    
    // Summary
    html += '<h4>Upload Results</h4>';
    html += `<p><strong>Successfully uploaded:</strong> ${result.uploaded_count} recipes</p>`;
    
    if (result.failed_count > 0) {
        html += `<p><strong>Failed:</strong> ${result.failed_count} recipes</p>`;
    }
    
    // Show successful recipes
    if (result.uploaded_recipes && result.uploaded_recipes.length > 0) {
        html += '<div class="success-results" style="margin-top: var(--space-md);">';
        html += '<h5 style="color: var(--success-color, #28a745);">Successfully Uploaded:</h5>';
        html += '<ul>';
        result.uploaded_recipes.forEach(recipe => {
            html += `<li>${recipe.name}</li>`;
        });
        html += '</ul>';
        html += '</div>';
    }
    
    // Show validation errors
    if (result.validation_errors && result.validation_errors.length > 0) {
        html += '<div class="error-results" style="margin-top: var(--space-md);">';
        html += '<h5 style="color: var(--error-color, #dc3545);">Validation Errors:</h5>';
        html += '<ul>';
        result.validation_errors.forEach(error => {
            html += `<li><strong>${error.recipe_name}</strong> (Recipe ${error.recipe_index + 1}): ${error.error_message}</li>`;
        });
        html += '</ul>';
        html += '</div>';
    }
    
    html += '</div>';
    
    resultsDiv.innerHTML = html;
    
    // Show appropriate message
    if (result.uploaded_count > 0) {
        showMessage(`Successfully uploaded ${result.uploaded_count} recipes!`, 'success');
    }
    
    if (result.failed_count > 0) {
        showMessage(`${result.failed_count} recipes failed validation. See details below.`, 'error');
    }
}

// Bulk ingredient upload functionality
function downloadIngredientTemplate() {
    const template = {
        ingredients: [
            {
                name: "Vodka",
                description: "A clear distilled spirit with a neutral taste",
                parent_name: "Spirits"
            },
            {
                name: "Lime Juice",
                description: "Fresh lime juice for cocktails",
            },
        ]
    };
    
    // Create and download the template
    const blob = new Blob([JSON.stringify(template, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cocktail-ingredients-template.json';
    
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    
    showMessage('Ingredient template downloaded successfully!', 'success');
}

function handleIngredientFileSelection(event) {
    const file = event.target.files[0];
    const uploadBtn = document.getElementById('upload-ingredients-btn');
    
    if (file) {
        // Validate file type
        if (!file.type.includes('json')) {
            showMessage('Please select a JSON file', 'error');
            event.target.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        // Validate file size (limit to 5MB)
        if (file.size > 5 * 1024 * 1024) {
            showMessage('File too large. Please select a file smaller than 5MB', 'error');
            event.target.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        uploadBtn.disabled = false;
    } else {
        uploadBtn.disabled = true;
    }
}

async function handleBulkIngredientUpload() {
    const fileInput = document.getElementById('ingredient-file-input');
    const file = fileInput.files[0];
    
    if (!file) {
        showMessage('Please select a file first', 'error');
        return;
    }
    
    try {
        // Read and parse the JSON file
        const fileText = await readFile(file);
        let ingredientsData;
        
        try {
            ingredientsData = JSON.parse(fileText);
        } catch (error) {
            showMessage('Invalid JSON file. Please check the file format.', 'error');
            return;
        }
        
        // Validate JSON structure
        if (!validateIngredientJsonStructure(ingredientsData)) {
            return; // Error message already shown in validation
        }
        
        // Show progress
        showIngredientUploadProgress(true);
        
        // Upload ingredients
        const result = await api.bulkUploadIngredients(ingredientsData);
        
        // Hide progress
        showIngredientUploadProgress(false);
        
        // Display results
        displayIngredientUploadResults(result);
        
        // Clear file input
        fileInput.value = '';
        document.getElementById('upload-ingredients-btn').disabled = true;
        
    } catch (error) {
        showIngredientUploadProgress(false);
        console.error('Error uploading ingredients:', error);
        showMessage(`Error uploading ingredients: ${error.message}`, 'error');
    }
}

function validateIngredientJsonStructure(data) {
    // Check if it has the ingredients array
    if (!data || !Array.isArray(data.ingredients)) {
        showMessage('JSON file must contain an "ingredients" array', 'error');
        return false;
    }
    
    if (data.ingredients.length === 0) {
        showMessage('Ingredients array cannot be empty', 'error');
        return false;
    }
    
    // Check each ingredient has required fields
    for (let i = 0; i < data.ingredients.length; i++) {
        const ingredient = data.ingredients[i];
        
        if (!ingredient.name || typeof ingredient.name !== 'string') {
            showMessage(`Ingredient ${i + 1} must have a "name" field`, 'error');
            return false;
        }
        
        // Optional fields validation
        if (ingredient.description && typeof ingredient.description !== 'string') {
            showMessage(`Ingredient "${ingredient.name}" description must be a string`, 'error');
            return false;
        }
        
        if (ingredient.parent_name && typeof ingredient.parent_name !== 'string') {
            showMessage(`Ingredient "${ingredient.name}" parent_name must be a string`, 'error');
            return false;
        }
    }
    
    return true;
}

function showIngredientUploadProgress(show) {
    const progressDiv = document.getElementById('ingredient-upload-progress');
    const uploadBtn = document.getElementById('upload-ingredients-btn');
    
    if (show) {
        progressDiv.style.display = 'block';
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Uploading...';
    } else {
        progressDiv.style.display = 'none';
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload Ingredients';
    }
}

function displayIngredientUploadResults(result) {
    const resultsDiv = document.getElementById('ingredient-upload-results');
    
    let html = '<div class="upload-results">';
    
    // Summary
    html += '<h4>Upload Results</h4>';
    html += `<p><strong>Successfully uploaded:</strong> ${result.uploaded_count} ingredients</p>`;
    
    if (result.failed_count > 0) {
        html += `<p><strong>Failed:</strong> ${result.failed_count} ingredients</p>`;
    }
    
    // Show successful ingredients
    if (result.uploaded_ingredients && result.uploaded_ingredients.length > 0) {
        html += '<div class="success-results" style="margin-top: var(--space-md);">';
        html += '<h5 style="color: var(--success-color, #28a745);">Successfully Uploaded:</h5>';
        html += '<ul>';
        result.uploaded_ingredients.forEach(ingredient => {
            html += `<li>${ingredient.name}${ingredient.description ? ` - ${ingredient.description}` : ''}</li>`;
        });
        html += '</ul>';
        html += '</div>';
    }
    
    // Show validation errors
    if (result.validation_errors && result.validation_errors.length > 0) {
        html += '<div class="error-results" style="margin-top: var(--space-md);">';
        html += '<h5 style="color: var(--error-color, #dc3545);">Validation Errors:</h5>';
        html += '<ul>';
        result.validation_errors.forEach(error => {
            html += `<li><strong>${error.ingredient_name}</strong> (Ingredient ${error.ingredient_index + 1}): ${error.error_message}</li>`;
        });
        html += '</ul>';
        html += '</div>';
    }
    
    html += '</div>';
    
    resultsDiv.innerHTML = html;
    
    // Show appropriate message
    if (result.uploaded_count > 0) {
        showMessage(`Successfully uploaded ${result.uploaded_count} ingredients!`, 'success');
    }
    
    if (result.failed_count > 0) {
        showMessage(`${result.failed_count} ingredients failed validation. See details below.`, 'error');
    }
}