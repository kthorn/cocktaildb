import { api } from './api.js';
import { displayRecipes } from './recipeCard.js';

// Keep a global reference to ingredients for type-ahead
let availableIngredients = [];
let activeRowIndex = null;
let activeIngredientIndex = -1;

document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const searchForm = document.getElementById('recipe-search-form');
    const nameSearch = document.getElementById('name-search');
    const tagsSearch = document.getElementById('tags-search');
    const searchButton = document.getElementById('search-button');
    const resetButton = document.getElementById('reset-button');
    const searchResultsContainer = document.getElementById('search-results-container');
    const loadingPlaceholder = document.querySelector('.loading-placeholder');
    const emptyResults = document.querySelector('.empty-message');
    const ingredientQueryBuilder = document.getElementById('ingredient-query-builder');
    const addIngredientRowBtn = document.getElementById('add-ingredient-row');

    // Load ingredients for type-ahead
    loadIngredients();

    // Setup add/remove ingredient rows
    addIngredientRowBtn.addEventListener('click', addIngredientRow);
    setupInitialIngredientRow();

    // Check for URL query parameters
    const urlParams = new URLSearchParams(window.location.search);
    const tagFromUrl = urlParams.get('tag');

    if (tagFromUrl) {
        tagsSearch.value = tagFromUrl;
        performSearch(); // Auto-search if tag is in URL
    }

    // Form submit event
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await performSearch();
    });

    // Reset button event
    resetButton.addEventListener('click', () => {
        searchForm.reset();
        emptyResults.classList.remove('hidden');
        searchResultsContainer.querySelectorAll('.recipe-card').forEach(card => card.remove());
        
        // Reset ingredient rows to initial state
        const rows = ingredientQueryBuilder.querySelectorAll('.item-row');
        rows.forEach((row, index) => {
            if (index > 0) row.remove();
        });
        
        // Clear the first row inputs
        const firstRow = ingredientQueryBuilder.querySelector('.item-row');
        if (firstRow) {
            firstRow.querySelector('.logical-operator').value = 'MUST';
            firstRow.querySelector('.ingredient-search').value = '';
            firstRow.querySelector('.ingredient-id').value = '';
        }
    });

    // Function to perform the search
    async function performSearch() {
        try {
            loadingPlaceholder.classList.remove('hidden');
            emptyResults.classList.add('hidden');
            
            // Remove existing results
            searchResultsContainer.querySelectorAll('.recipe-card').forEach(card => card.remove());
            
            // Build the search query
            const searchQuery = buildSearchQuery();
            
            // Call the API to search recipes
            const results = await api.searchRecipes(searchQuery);
            
            // Hide loading
            loadingPlaceholder.classList.add('hidden');
            
            if (results.length === 0) {
                // Show no results message
                emptyResults.classList.remove('hidden');
                emptyResults.querySelector('p').textContent = 'No recipes found matching your criteria.';
            } else {
                // Hide no results message and show recipes
                emptyResults.classList.add('hidden');
                displayRecipes(results, searchResultsContainer, false);
            }
        } catch (error) {
            console.error('Error searching recipes:', error);
            loadingPlaceholder.classList.add('hidden');
            emptyResults.classList.remove('hidden');
            emptyResults.querySelector('p').textContent = 'Error searching recipes. Please try again.';
        }
    }

    // Function to build the search query from form fields
    function buildSearchQuery() {
        const query = {};
        
        // Add name search if provided
        const nameValue = nameSearch.value.trim();
        if (nameValue) {
            query.name = nameValue;
        }
        
        // Add rating filter if selected (other than 'all')
        const selectedRating = document.querySelector('input[name="rating-filter"]:checked').value;
        if (selectedRating !== 'all') {
            query.rating = parseFloat(selectedRating);
        }
        
        // Add tags if provided
        const tagsValue = tagsSearch.value.trim();
        if (tagsValue) {
            query.tags = tagsValue.split(',').map(tag => tag.trim());
        }
        
        // Add ingredient conditions
        const ingredientRows = ingredientQueryBuilder.querySelectorAll('.item-row');
        if (ingredientRows.length > 0) {
            query.ingredients = [];
            
            ingredientRows.forEach(row => {
                const logicalOp = row.querySelector('.logical-operator').value;
                const ingredientId = row.querySelector('.ingredient-id').value;
                const ingredientName = row.querySelector('.ingredient-search').value.trim();
                
                // Only add if an ingredient is selected
                if (ingredientId && ingredientName) {
                    query.ingredients.push({
                        id: parseInt(ingredientId),
                        operator: logicalOp
                    });
                }
            });
            
            // If no valid ingredients, delete the ingredients property
            if (query.ingredients.length === 0) {
                delete query.ingredients;
            }
        }
        
        return query;
    }

    // Function to load all ingredients for type-ahead
    async function loadIngredients() {
        try {
            availableIngredients = await api.getIngredients();
            console.log('Loaded ingredients for search:', availableIngredients.length);
            
            // Hide loading status in all ingredient search rows
            document.querySelectorAll('.search-status').forEach(status => {
                status.classList.remove('active');
            });
        } catch (error) {
            console.error('Error loading ingredients:', error);
        }
    }

    // Function to setup the initial ingredient row
    function setupInitialIngredientRow() {
        let firstRow = ingredientQueryBuilder.querySelector('.item-row');
        
        // If no ingredient row exists, add one
        if (!firstRow) {
            addIngredientRow();
            firstRow = ingredientQueryBuilder.querySelector('.item-row'); // Get the newly added row
        }
        
        // Now, firstRow is guaranteed to exist (either pre-existing or newly added)
        if (firstRow) {
            // The setupIngredientRow is already called by addIngredientRow if it was invoked.
            // If the row was pre-existing (though we removed it from HTML, good to be defensive),
            // we might need to call it. However, addIngredientRow calls it.
            // So, we primarily need to ensure the remove button is hidden.
            
            const removeButton = firstRow.querySelector('.remove-row');
            if (removeButton) {
                removeButton.style.display = 'none';
            }
        }
    }

    // Function to add a new ingredient row
    function addIngredientRow() {
        const newRow = document.createElement('div');
        newRow.className = 'item-row';
        newRow.innerHTML = `
            <select class="logical-operator item-row-field-fixed">
                <option value="MUST">Must contain</option>
                <option value="MUST_NOT">Must NOT contain</option>
            </select>
            <div class="ingredient-search-wrapper item-row-field-expand">
                <input type="text" class="ingredient-search" placeholder="Search for ingredient">
                <input type="hidden" class="ingredient-id">
                <div class="autocomplete-dropdown"></div>
                <div class="search-status">Loading ingredients...</div>
            </div>
            <button type="button" class="remove-row btn-circle btn-danger">✕</button>
        `;
        
        // Insert before the add button wrapper
        const addButtonWrapper = ingredientQueryBuilder.querySelector('.add-row-wrapper');
        ingredientQueryBuilder.insertBefore(newRow, addButtonWrapper);
        
        // Setup autocomplete and remove button
        setupIngredientRow(newRow);
    }

    // Function to setup ingredient row functionality
    function setupIngredientRow(row) {
        const ingredientSearchInput = row.querySelector('.ingredient-search');
        const autocompleteDropdown = row.querySelector('.autocomplete-dropdown');
        const ingredientIdInput = row.querySelector('.ingredient-id');
        const removeButton = row.querySelector('.remove-row');
        const searchStatus = row.querySelector('.search-status');
        
        // Hide search status if ingredients are loaded
        if (availableIngredients.length > 0) {
            searchStatus.classList.remove('active');
        } else {
            searchStatus.classList.add('active');
        }
        
        // Remove row event
        removeButton.addEventListener('click', () => {
            row.remove();
        });
        
        // Ingredient search input events
        ingredientSearchInput.addEventListener('input', () => updateAutocomplete(row));
        ingredientSearchInput.addEventListener('focus', () => updateAutocomplete(row));
        ingredientSearchInput.addEventListener('blur', () => {
            // Delay hiding to allow click events on dropdown items
            setTimeout(() => {
                autocompleteDropdown.style.display = 'none';
            }, 200);
        });
        
        // Keyboard navigation
        ingredientSearchInput.addEventListener('keydown', (e) => {
            // Set the active row for keyboard navigation
            activeRowIndex = Array.from(ingredientQueryBuilder.querySelectorAll('.item-row')).indexOf(row);
            
            const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
            
            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    setActiveIngredientItem(Math.min(activeIngredientIndex + 1, items.length - 1));
                    break;
                    
                case 'ArrowUp':
                    e.preventDefault();
                    setActiveIngredientItem(Math.max(activeIngredientIndex - 1, 0));
                    break;
                    
                case 'Enter':
                    if (activeIngredientIndex >= 0) {
                        e.preventDefault();
                        selectActiveIngredientItem();
                    }
                    break;
                    
                case 'Tab':
                    if (items.length > 0) {
                        e.preventDefault();
                        if (activeIngredientIndex === -1) {
                            setActiveIngredientItem(0);
                        } else {
                            selectActiveIngredientItem();
                        }
                    }
                    break;
                    
                case 'Escape':
                    autocompleteDropdown.style.display = 'none';
                    break;
            }
        });
        
        // Clear on double-click
        ingredientSearchInput.addEventListener('dblclick', () => {
            ingredientSearchInput.value = '';
            ingredientIdInput.value = '';
        });
    }

    // Update autocomplete dropdown for ingredient search
    function updateAutocomplete(row) {
        const searchInput = row.querySelector('.ingredient-search');
        const searchTerm = searchInput.value.toLowerCase();
        const dropdown = row.querySelector('.autocomplete-dropdown');
        const searchStatus = row.querySelector('.search-status');
        
        // Clear the dropdown
        dropdown.innerHTML = '';
        
        if (searchTerm.length === 0) {
            dropdown.style.display = 'none';
            return;
        }
        
        // Ensure ingredients are loaded
        if (!availableIngredients || !Array.isArray(availableIngredients) || availableIngredients.length === 0) {
            searchStatus.classList.add('active');
            return;
        }
        
        searchStatus.classList.remove('active');
        
        // Find matching ingredients
        const matches = availableIngredients.filter(ingredient => 
            ingredient.name.toLowerCase().includes(searchTerm)
        );
        
        if (matches.length === 0) {
            dropdown.style.display = 'none';
            return;
        }
        
        // Add matches to dropdown
        matches.forEach((ingredient, index) => {
            const item = document.createElement('div');
            item.className = 'autocomplete-item';
            
            // Highlight matching part
            const highlightedText = ingredient.name.replace(
                new RegExp(searchTerm, 'gi'),
                match => `<strong>${match}</strong>`
            );
            item.innerHTML = highlightedText;
            
            item.addEventListener('click', () => {
                searchInput.value = ingredient.name;
                row.querySelector('.ingredient-id').value = ingredient.id;
                dropdown.style.display = 'none';
            });
            
            item.addEventListener('mouseenter', () => {
                // Update active row index when hovering
                activeRowIndex = Array.from(ingredientQueryBuilder.querySelectorAll('.item-row')).indexOf(row);
                setActiveIngredientItem(index);
            });
            
            dropdown.appendChild(item);
        });
        
        // Show the dropdown
        dropdown.style.display = 'block';
        activeIngredientIndex = -1;
    }

    // Function to set the active autocomplete item
    function setActiveIngredientItem(index) {
        if (activeRowIndex === null) return;
        
        const row = ingredientQueryBuilder.querySelectorAll('.item-row')[activeRowIndex];
        if (!row) return;
        
        const items = row.querySelectorAll('.autocomplete-item');
        
        // Remove active class from all items
        items.forEach(item => item.classList.remove('active'));
        
        // Set active class on the selected item
        if (index >= 0 && index < items.length) {
            activeIngredientIndex = index;
            items[index].classList.add('active');
            // Ensure the active item is in view
            items[index].scrollIntoView({ block: 'nearest' });
        }
    }

    // Function to select the current active item
    function selectActiveIngredientItem() {
        if (activeRowIndex === null) return;
        
        const row = ingredientQueryBuilder.querySelectorAll('.item-row')[activeRowIndex];
        if (!row) return;
        
        const items = row.querySelectorAll('.autocomplete-item');
        const searchInput = row.querySelector('.ingredient-search');
        const idInput = row.querySelector('.ingredient-id');
        const dropdown = row.querySelector('.autocomplete-dropdown');
        
        if (activeIngredientIndex >= 0 && activeIngredientIndex < items.length) {
            const selectedValue = items[activeIngredientIndex].textContent;
            searchInput.value = selectedValue;
            
            // Find and set the corresponding ingredient ID
            const ingredient = availableIngredients.find(ing => ing.name === selectedValue);
            if (ingredient) {
                idInput.value = ingredient.id;
            }
            
            dropdown.style.display = 'none';
        }
    }
}); 