import { api } from './api.js';
import { isAuthenticated, initAuth } from './auth.js';

document.addEventListener('DOMContentLoaded', async () => {
    // Ensure authentication is initialized before checking permissions
    await initAuth();
    setupAdminPage();
});

const MAX_UPLOAD_MB = 5;
const MAX_RECIPES = 100;
const MAX_INGREDIENTS = 200;

function setupAdminPage() {
    const downloadTemplateBtn = document.getElementById('download-template-btn');
    const fileInput = document.getElementById('recipe-file-input');
    const uploadBtn = document.getElementById('upload-recipes-btn');
    
    // Ingredient upload elements
    const downloadIngredientTemplateBtn = document.getElementById('download-ingredient-template-btn');
    const ingredientFileInput = document.getElementById('ingredient-file-input');
    const uploadIngredientsBtn = document.getElementById('upload-ingredients-btn');
    
    if (downloadTemplateBtn) {
        downloadTemplateBtn.addEventListener('click', downloadTemplate);
    }
    
    if (fileInput) {
        fileInput.addEventListener('change', (event) => {
            handleFileSelection(event, getRecipeUploadConfig());
        });
    }
    
    if (uploadBtn) {
        uploadBtn.addEventListener('click', () => handleBulkUpload(getRecipeUploadConfig()));
    }
    
    // Ingredient upload event listeners
    if (downloadIngredientTemplateBtn) {
        downloadIngredientTemplateBtn.addEventListener('click', downloadIngredientTemplate);
    }
    
    if (ingredientFileInput) {
        ingredientFileInput.addEventListener('change', (event) => {
            handleFileSelection(event, getIngredientUploadConfig());
        });
    }
    
    if (uploadIngredientsBtn) {
        uploadIngredientsBtn.addEventListener('click', () => handleBulkUpload(getIngredientUploadConfig()));
    }
    
    // Tag management elements
    const refreshTagsBtn = document.getElementById('refresh-tags-btn');
    if (refreshTagsBtn) {
        refreshTagsBtn.addEventListener('click', loadPublicTags);
    }
    
    // Check authentication and show/hide admin tools accordingly
    updateUIBasedOnAuth();
    
    // Load initial data if user has editor permissions
    if (api.isEditor()) {
        loadPublicTags();
    }
}

function updateUIBasedOnAuth() {
    const adminTools = document.querySelector('.admin-tools');
    
    if (!adminTools) {
        console.error('Admin tools container not found');
        return;
    }
    
    if (!isAuthenticated()) {
        adminTools.innerHTML = `
            <div class="card-container">
                <p>Please log in to access admin tools.</p>
            </div>
        `;
        return;
    }
    
    if (!api.isEditor()) {
        adminTools.innerHTML = `
            <div class="card-container">
                <p>Editor access required. Only editors and admins can access admin tools.</p>
            </div>
        `;
        return;
    }
    
    // User has editor permissions, admin tools are already visible in HTML
    // No need to hide/show since the HTML contains the admin tools by default
}


function showMessage(message, type = 'info') {
    // Create message element using existing notification styles
    const messageDiv = document.createElement('div');
    messageDiv.className = `notification ${type}`;
    messageDiv.textContent = message;
    
    // Insert at top of main section
    const mainSection = document.querySelector('main section') || document.body;
    if (mainSection.firstChild) {
        mainSection.insertBefore(messageDiv, mainSection.firstChild);
    } else {
        mainSection.appendChild(messageDiv);
    }
    
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

function getRecipeUploadConfig() {
    return {
        fileInputId: 'recipe-file-input',
        uploadBtnId: 'upload-recipes-btn',
        progressId: 'upload-progress',
        resultsId: 'upload-results',
        maxItems: MAX_RECIPES,
        itemsKey: 'recipes',
        itemLabel: 'recipe',
        apiCall: (payload) => api.bulkUploadRecipes(payload),
        validateStructure: validateJsonStructure,
        successKey: 'uploaded_recipes',
        buildSuccessText: (recipe) => recipe.name,
        buildErrorText: (error) => (
            `${error.recipe_name} (Recipe ${error.recipe_index + 1}): ${error.error_message}`
        )
    };
}

function getIngredientUploadConfig() {
    return {
        fileInputId: 'ingredient-file-input',
        uploadBtnId: 'upload-ingredients-btn',
        progressId: 'ingredient-upload-progress',
        resultsId: 'ingredient-upload-results',
        maxItems: MAX_INGREDIENTS,
        itemsKey: 'ingredients',
        itemLabel: 'ingredient',
        apiCall: (payload) => api.bulkUploadIngredients(payload),
        validateStructure: validateIngredientJsonStructure,
        successKey: 'uploaded_ingredients',
        buildSuccessText: (ingredient) => (
            `${ingredient.name}${ingredient.description ? ` - ${ingredient.description}` : ''}`
        ),
        buildErrorText: (error) => (
            `${error.ingredient_name} (Ingredient ${error.ingredient_index + 1}): ${error.error_message}`
        )
    };
}

function handleFileSelection(event, config) {
    const file = event.target.files[0];
    const uploadBtn = document.getElementById(config.uploadBtnId);
    
    if (file) {
        // Validate file type
        const isJson = file.type.includes('json') || file.name.toLowerCase().endsWith('.json');
        if (!isJson) {
            showMessage('Please select a JSON file', 'error');
            event.target.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        // Validate file size (limit to 5MB)
        if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
            showMessage(`File too large. Please select a file smaller than ${MAX_UPLOAD_MB}MB`, 'error');
            event.target.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        uploadBtn.disabled = false;
    } else {
        uploadBtn.disabled = true;
    }
}

async function handleBulkUpload(config) {
    const fileInput = document.getElementById(config.fileInputId);
    if (!fileInput) {
        showMessage('Upload input not found.', 'error');
        return;
    }
    const file = fileInput.files[0];

    if (!file) {
        showMessage('Please select a file first', 'error');
        return;
    }

    try {
        // Read and parse the JSON file
        const fileText = await readFile(file);
        let uploadData;

        try {
            uploadData = JSON.parse(fileText);
        } catch (error) {
            showMessage('Invalid JSON file. Please check the file format.', 'error');
            return;
        }

        // Validate JSON structure
        if (!config.validateStructure(uploadData)) {
            return; // Error message already shown in validation
        }

        const items = uploadData[config.itemsKey];
        if (items.length > config.maxItems) {
            showMessage(
                `Upload limit is ${config.maxItems} ${pluralize(config.maxItems, config.itemLabel)} per file.`,
                'error'
            );
            return;
        }

        // Show progress
        showUploadProgress(true, `Uploading ${items.length} ${pluralize(items.length, config.itemLabel)}...`, config);

        const result = await config.apiCall({ [config.itemsKey]: items });

        // Hide progress
        showUploadProgress(false, '', config);

        // Display results
        displayUploadResults(result, config);

        // Clear file input
        fileInput.value = '';
        const uploadBtn = document.getElementById(config.uploadBtnId);
        if (uploadBtn) {
            uploadBtn.disabled = true;
        }

    } catch (error) {
        showUploadProgress(false, '', config);
        console.error(`Error uploading ${config.itemLabel}s:`, error);
        showMessage(`Error uploading ${config.itemLabel}s: ${error.message}`, 'error');
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

            if (ingredient.amount === undefined || ingredient.amount === null || ingredient.amount === '') {
                showMessage(`Recipe "${recipe.name}" ingredient "${ingredient.ingredient_name}" is missing an "amount" field`, 'error');
                return false;
            }

            if (typeof ingredient.amount !== 'number' || isNaN(ingredient.amount)) {
                showMessage(`Recipe "${recipe.name}" ingredient "${ingredient.ingredient_name}" must have a numeric "amount" value`, 'error');
                return false;
            }

            if (!ingredient.unit_name || typeof ingredient.unit_name !== 'string') {
                showMessage(`Recipe "${recipe.name}" ingredient "${ingredient.ingredient_name}" is missing a "unit_name" field`, 'error');
                return false;
            }
        }

        // Check for duplicate ingredients in this recipe
        const seenIngredients = new Set();
        const duplicates = new Set();
        recipe.ingredients.forEach((ing) => {
            const normalized = ing.ingredient_name.toLowerCase().trim();
            if (seenIngredients.has(normalized)) {
                duplicates.add(normalized);
            } else {
                seenIngredients.add(normalized);
            }
        });
        if (duplicates.size > 0) {
            showMessage(
                `Recipe "${recipe.name}" has duplicate ingredients: ${Array.from(duplicates).join(', ')}`,
                'error'
            );
            return false;
        }
    }
    
    return true;
}

function showUploadProgress(show, message, config) {
    const progressDiv = document.getElementById(config.progressId);
    const progressText = progressDiv ? progressDiv.querySelector('p') : null;
    const uploadBtn = document.getElementById(config.uploadBtnId);

    if (show) {
        if (progressDiv) {
            progressDiv.style.display = 'block';
        }
        if (uploadBtn) {
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Uploading...';
        }
        if (progressText) {
            progressText.textContent = message;
        }
    } else {
        if (progressDiv) {
            progressDiv.style.display = 'none';
        }
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.textContent = config.itemLabel === 'recipe' ? 'Upload Recipes' : 'Upload Ingredients';
        }
    }
}

function displayUploadResults(result, config) {
    const resultsDiv = document.getElementById(config.resultsId);
    if (!resultsDiv) {
        return;
    }

    resultsDiv.innerHTML = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'upload-results';

    const heading = document.createElement('h4');
    heading.textContent = 'Upload Results';
    wrapper.appendChild(heading);

    const uploadedCount = result.uploaded_count || 0;
    const failedCount = result.failed_count || 0;

    const successSummary = document.createElement('p');
    const successLabel = document.createElement('strong');
    successLabel.textContent = 'Successfully uploaded:';
    successSummary.appendChild(successLabel);
    successSummary.append(
        ` ${uploadedCount} ${pluralize(uploadedCount, config.itemLabel)}`
    );
    wrapper.appendChild(successSummary);

    if (failedCount > 0) {
        const failedSummary = document.createElement('p');
        const failedLabel = document.createElement('strong');
        failedLabel.textContent = 'Failed:';
        failedSummary.appendChild(failedLabel);
        failedSummary.append(` ${failedCount} ${pluralize(failedCount, config.itemLabel)}`);
        wrapper.appendChild(failedSummary);
    }

    const successes = result[config.successKey] || [];
    if (successes.length > 0) {
        const successBlock = document.createElement('div');
        successBlock.className = 'success-results';
        successBlock.style.marginTop = 'var(--space-md)';

        const successTitle = document.createElement('h5');
        successTitle.style.color = 'var(--success-color, #28a745)';
        successTitle.textContent = 'Successfully Uploaded:';
        successBlock.appendChild(successTitle);

        const successList = document.createElement('ul');
        successes.forEach((item) => {
            const listItem = document.createElement('li');
            listItem.textContent = config.buildSuccessText(item);
            successList.appendChild(listItem);
        });
        successBlock.appendChild(successList);
        wrapper.appendChild(successBlock);
    }

    const validationErrors = result.validation_errors || [];
    if (validationErrors.length > 0) {
        const errorBlock = document.createElement('div');
        errorBlock.className = 'error-results';
        errorBlock.style.marginTop = 'var(--space-md)';

        const errorTitle = document.createElement('h5');
        errorTitle.style.color = 'var(--error-color, #dc3545)';
        errorTitle.textContent = 'Validation Errors:';
        errorBlock.appendChild(errorTitle);

        const errorList = document.createElement('ul');
        validationErrors.forEach((error) => {
            const listItem = document.createElement('li');
            listItem.textContent = config.buildErrorText(error);
            errorList.appendChild(listItem);
        });
        errorBlock.appendChild(errorList);
        wrapper.appendChild(errorBlock);
    }

    resultsDiv.appendChild(wrapper);

    // Show appropriate message
    if (uploadedCount > 0) {
        showMessage(
            `Successfully uploaded ${uploadedCount} ${pluralize(uploadedCount, config.itemLabel)}!`,
            'success'
        );
    }

    if (failedCount > 0) {
        showMessage(
            `${failedCount} ${pluralize(failedCount, config.itemLabel)} failed validation. See details below.`,
            'error'
        );
    }
}

function downloadIngredientTemplate() {
    const template = {
        ingredients: [
            {
                name: "Vodka",
                description: "A clear distilled spirit with a neutral taste",
                parent_name: "Spirits",
                allow_substitution: false
            },
            {
                name: "Lime Juice",
                description: "Fresh lime juice for cocktails",
                allow_substitution: true
            },
            {
                name: "Premium Vodka",
                description: "High-quality vodka with exceptional purity",
                parent_name: "Vodka",
                allow_substitution: true
            }
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
        
        if (ingredient.allow_substitution !== undefined && ingredient.allow_substitution !== null) {
            if (typeof ingredient.allow_substitution !== 'boolean') {
                showMessage(`Ingredient "${ingredient.name}" allow_substitution must be a boolean (true or false)`, 'error');
                return false;
            }
        }
    }
    
    return true;
}

function pluralize(count, singular) {
    return count === 1 ? singular : `${singular}s`;
}

// Public tag management functionality
async function loadPublicTags() {
    const tagsList = document.getElementById('public-tags-list');
    const refreshBtn = document.getElementById('refresh-tags-btn');
    
    if (!tagsList) return;
    
    try {
        // Show loading state
        tagsList.innerHTML = '<div class="loading-message"><p>Loading public tags...</p></div>';
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.textContent = 'Loading...';
        }
        
        const tags = await api.getPublicTags();
        
        if (tags.length === 0) {
            tagsList.innerHTML = '<div class="empty-message"><p>No public tags found.</p></div>';
            return;
        }
        
        // Generate tag list HTML
        let html = '';
        tags.forEach(tag => {
            html += `
                <div class="tag-management-item" data-tag-id="${tag.id}">
                    <div class="tag-management-info">
                        <div class="tag-management-name">${tag.name}</div>
                        <div class="tag-management-usage">Used in ${tag.usage_count || 0} recipe${tag.usage_count === 1 ? '' : 's'}</div>
                    </div>
                    <div class="tag-management-actions">
                        <button class="btn btn-danger btn-small delete-tag-btn" data-tag-id="${tag.id}" data-tag-name="${tag.name}">
                            Delete
                        </button>
                    </div>
                </div>
            `;
        });
        
        tagsList.innerHTML = html;
        
        // Add event listeners for delete buttons
        const deleteButtons = tagsList.querySelectorAll('.delete-tag-btn');
        deleteButtons.forEach(btn => {
            btn.addEventListener('click', handleDeletePublicTag);
        });
        
    } catch (error) {
        console.error('Error loading public tags:', error);
        tagsList.innerHTML = '<div class="error-message"><p>Error loading tags. Please try again.</p></div>';
        showMessage('Error loading public tags', 'error');
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = 'Refresh Tags';
        }
    }
}

async function handleDeletePublicTag(event) {
    const button = event.target;
    const tagId = parseInt(button.dataset.tagId);
    const tagName = button.dataset.tagName;
    
    // Confirm deletion
    const confirmMessage = `Are you sure you want to delete the public tag "${tagName}"?\n\nThis will remove it from ALL recipes that use this tag. This action cannot be undone.`;
    if (!confirm(confirmMessage)) {
        return;
    }
    
    const originalText = button.textContent;
    
    try {
        // Show loading state
        button.disabled = true;
        button.textContent = 'Deleting...';
        
        await api.deletePublicTag(tagId);
        
        // Remove the tag item from the UI
        const tagItem = button.closest('.tag-management-item');
        if (tagItem) {
            tagItem.remove();
        }
        
        showMessage(`Public tag "${tagName}" deleted successfully`, 'success');
        
        // Check if list is now empty
        const tagsList = document.getElementById('public-tags-list');
        if (tagsList && tagsList.children.length === 0) {
            tagsList.innerHTML = '<div class="empty-message"><p>No public tags found.</p></div>';
        }
        
    } catch (error) {
        console.error('Error deleting public tag:', error);
        showMessage(`Error deleting tag "${tagName}": ${error.message || 'Please try again'}`, 'error');
        
        // Restore button state
        button.disabled = false;
        button.textContent = originalText;
    }
}
