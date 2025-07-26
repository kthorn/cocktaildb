import { api } from './api.js';
import { displayRecipes, createProgressiveRecipeLoader, createRecipeCard } from './recipeCard.js';

// Keep a global reference to ingredients for type-ahead
let availableIngredients = [];
let activeRowIndex = null;
let activeIngredientIndex = -1;

// Tag autocomplete management
let selectedTags = [];
let tagSuggestions = [];
let activeSuggestionIndex = -1;
let tagSearchTimeout = null;

// Search pagination state
let currentSearchQuery = null;
let currentSearchPage = 1;
let totalSearchPages = 1;
let searchResultsPerPage = 10;
let isSearching = false;
let allSearchResults = [];
let isInfiniteScrollEnabled = false;
let scrollThreshold = 200; // pixels from bottom to trigger load

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

    // Setup tag autocomplete
    setupTagAutocomplete();

    // Check for URL query parameters
    const urlParams = new URLSearchParams(window.location.search);
    const tagFromUrl = urlParams.get('tag');

    if (tagFromUrl) {
        // Add the tag from URL as a selected tag
        addTagChip({ name: tagFromUrl, type: 'public', id: null });
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
        
        // Reset search pagination state
        currentSearchQuery = null;
        currentSearchPage = 1;
        totalSearchPages = 1;
        allSearchResults = [];
        
        // Disable infinite scroll and remove loading indicator
        disableInfiniteScroll();
        
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
            // No longer need to clear ingredient ID since we use names directly
        }
    });

    // Function to perform the search
    async function performSearch(reset = true) {
        if (isSearching) return;
        
        try {
            isSearching = true;
            
            // Build the search query
            const searchQuery = buildSearchQuery();
            console.log('Built search query:', searchQuery);
            
            if (reset) {
                // Reset pagination state for new search
                currentSearchQuery = searchQuery;
                currentSearchPage = 1;
                allSearchResults = [];
                
                // Show loading and hide results
                loadingPlaceholder.classList.remove('hidden');
                emptyResults.classList.add('hidden');
                
                // Remove existing results
                searchResultsContainer.querySelectorAll('.recipe-card').forEach(card => card.remove());
                
                // Disable existing infinite scroll
                disableInfiniteScroll();
            }
            
            // Call the API to search recipes with pagination
            const result = await api.searchRecipes(searchQuery, currentSearchPage, searchResultsPerPage);
            console.log('API result:', result);
            
            // Hide loading placeholder
            loadingPlaceholder.classList.add('hidden');
            
            if (result && result.recipes) {
                // Add results to our collection
                if (reset) {
                    allSearchResults = result.recipes;
                } else {
                    allSearchResults.push(...result.recipes);
                }
                
                // Update pagination state
                totalSearchPages = result.pagination.has_next ? currentSearchPage + 1 : currentSearchPage;
                
                // Display results
                if (reset) {
                    displayRecipes(allSearchResults, searchResultsContainer, true);
                } else {
                    // Append new results using consistent displayRecipes approach
                    const tempContainer = document.createElement('div');
                    displayRecipes(result.recipes, tempContainer, true);
                    Array.from(tempContainer.children).forEach(card => {
                        searchResultsContainer.appendChild(card);
                    });
                }
                
                // Setup infinite scroll if there are more pages
                setupInfiniteScroll(result.pagination.has_next);
                
                // Hide no results message if we have results
                if (allSearchResults.length > 0) {
                    emptyResults.classList.add('hidden');
                } else if (reset) {
                    emptyResults.classList.remove('hidden');
                    emptyResults.querySelector('p').textContent = 'No recipes found matching your criteria.';
                }
                
                console.log(`Search page ${currentSearchPage} loaded (${result.recipes.length} recipes), has_next: ${result.pagination.has_next}`);
                console.log('Pagination info:', result.pagination);
            } else if (reset) {
                // Show no results message
                emptyResults.classList.remove('hidden');
                emptyResults.querySelector('p').textContent = 'No recipes found matching your criteria.';
            }
        } catch (error) {
            console.error('Error searching recipes:', error);
            loadingPlaceholder.classList.add('hidden');
            if (reset) {
                emptyResults.classList.remove('hidden');
                emptyResults.querySelector('p').textContent = 'Error searching recipes. Please try again.';
            }
        } finally {
            isSearching = false;
        }
    }
    
    // Setup infinite scroll for search results
    function setupInfiniteScroll(hasNext) {
        console.log(`Setting up infinite scroll: page ${currentSearchPage}, has_next: ${hasNext}`);
        if (hasNext) {
            isInfiniteScrollEnabled = true;
            console.log('Infinite scroll enabled');
            
            // Add loading indicator at bottom
            addScrollLoadingIndicator();
            
            // Add scroll event listener
            window.addEventListener('scroll', handleScroll);
        } else {
            console.log('Infinite scroll disabled - no more pages');
            disableInfiniteScroll();
        }
    }
    
    // Disable infinite scroll
    function disableInfiniteScroll() {
        isInfiniteScrollEnabled = false;
        window.removeEventListener('scroll', handleScroll);
        
        // Remove loading indicator
        const loadingIndicator = document.getElementById('infinite-scroll-loading');
        if (loadingIndicator) {
            loadingIndicator.remove();
        }
    }
    
    // Add loading indicator for infinite scroll
    function addScrollLoadingIndicator() {
        // Remove existing indicator if present
        const existingIndicator = document.getElementById('infinite-scroll-loading');
        if (existingIndicator) {
            existingIndicator.remove();
        }
        
        // Add loading indicator
        const loadingIndicator = document.createElement('div');
        loadingIndicator.id = 'infinite-scroll-loading';
        loadingIndicator.className = 'infinite-scroll-loading hidden';
        loadingIndicator.innerHTML = '<p>Loading more results...</p>';
        
        // Add after the search results container
        searchResultsContainer.parentNode.insertBefore(loadingIndicator, searchResultsContainer.nextSibling);
    }
    
    // Handle scroll event for infinite scroll
    function handleScroll() {
        if (!isInfiniteScrollEnabled || isSearching) {
            return;
        }
        
        // Calculate distance from bottom
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const windowHeight = window.innerHeight;
        const documentHeight = document.documentElement.scrollHeight;
        const distanceFromBottom = documentHeight - (scrollTop + windowHeight);
        
        // Debug logging (only log occasionally to avoid spam)
        if (Math.random() < 0.01) { // Log ~1% of scroll events
            console.log(`Scroll: distance from bottom = ${distanceFromBottom}px, threshold = ${scrollThreshold}px`);
        }
        
        // Trigger load when within threshold of bottom
        if (distanceFromBottom <= scrollThreshold) {
            console.log('Triggering infinite scroll load');
            loadMoreSearchResults();
        }
    }
    
    // Load more search results (next page) for infinite scroll
    async function loadMoreSearchResults() {
        if (isSearching) return;
        
        // Show loading indicator
        const loadingIndicator = document.getElementById('infinite-scroll-loading');
        if (loadingIndicator) {
            loadingIndicator.classList.remove('hidden');
        }
        
        currentSearchPage++;
        await performSearch(false); // Don't reset, append to existing
        
        // Hide loading indicator after loading
        if (loadingIndicator) {
            loadingIndicator.classList.add('hidden');
        }
    }

    // Function to build the search query from form fields
    function buildSearchQuery() {
        const query = {};
        
        // Add name search if provided
        const nameValue = nameSearch.value.trim();
        console.log('Name search value:', nameValue);
        if (nameValue) {
            query.name = nameValue;
            console.log('Added name to query:', query.name);
        }
        
        // Add rating filter if selected (other than 'all')
        const selectedRatingElement = document.querySelector('input[name="rating-filter"]:checked');
        console.log('Selected rating element:', selectedRatingElement);
        if (selectedRatingElement) {
            const selectedRating = selectedRatingElement.value;
            console.log('Selected rating value:', selectedRating);
            if (selectedRating !== 'all') {
                query.rating = parseFloat(selectedRating);
            }
        } else {
            console.log('No rating filter selected, skipping rating filter');
        }
        
        // Add selected tags
        if (selectedTags.length > 0) {
            query.tags = selectedTags.map(tag => tag.name);
        }
        
        // Add inventory filter if checked
        const inventoryCheckbox = document.getElementById('inventory-search');
        if (inventoryCheckbox && inventoryCheckbox.checked) {
            query.inventory = true;
        }
        
        // Add ingredient conditions
        const ingredientRows = ingredientQueryBuilder.querySelectorAll('.item-row');
        if (ingredientRows.length > 0) {
            query.ingredients = [];
            
            ingredientRows.forEach(row => {
                const logicalOp = row.querySelector('.logical-operator').value;
                const ingredientName = row.querySelector('.ingredient-search').value.trim();
                
                // Only add if an ingredient name is provided
                if (ingredientName) {
                    // Create ingredient specification with operator if not MUST (default)
                    if (logicalOp === 'MUST') {
                        query.ingredients.push(ingredientName);
                    } else {
                        query.ingredients.push(`${ingredientName}:${logicalOp}`);
                    }
                }
            });
            
            // If no valid ingredients, delete the ingredients property
            if (query.ingredients.length === 0) {
                delete query.ingredients;
            }
        }
        
        console.log('Final search query object:', query);
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
            // No longer need to clear ingredient ID
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
                // No longer need to set ingredient ID since we use names directly
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
        const dropdown = row.querySelector('.autocomplete-dropdown');
        
        if (activeIngredientIndex >= 0 && activeIngredientIndex < items.length) {
            const selectedValue = items[activeIngredientIndex].textContent;
            searchInput.value = selectedValue;
            // No longer need to set ingredient ID since we use names directly
            dropdown.style.display = 'none';
        }
    }

    // Tag autocomplete functionality
    function setupTagAutocomplete() {
        const tagInput = document.getElementById('tags-search');
        const dropdown = document.getElementById('tag-suggestions-dropdown');
        
        if (!tagInput || !dropdown) return;
        
        // Input event for tag search
        tagInput.addEventListener('input', handleTagInput);
        
        // Keyboard navigation
        tagInput.addEventListener('keydown', handleTagKeydown);
        
        // Click outside to close dropdown
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.tag-search-container')) {
                hideTagDropdown();
            }
        });
        
        // Handle clicking on suggestions
        dropdown.addEventListener('click', handleTagSuggestionClick);
    }
    
    function handleTagInput(e) {
        const query = e.target.value.trim();
        
        // Clear previous timeout
        if (tagSearchTimeout) {
            clearTimeout(tagSearchTimeout);
        }
        
        if (query.length < 1) {
            hideTagDropdown();
            return;
        }
        
        // Debounce the search
        tagSearchTimeout = setTimeout(() => {
            searchTags(query);
        }, 300);
    }
    
    async function searchTags(query) {
        const dropdown = document.getElementById('tag-suggestions-dropdown');
        
        try {
            dropdown.innerHTML = '<div class="loading">Searching tags...</div>';
            showTagDropdown();
            
            const results = await api.searchTags(query);
            
            if (results.length === 0) {
                dropdown.innerHTML = '<div class="no-results">No tags found</div>';
                return;
            }
            
            // Filter out already selected tags
            const filteredResults = results.filter(tag => 
                !selectedTags.some(selected => selected.name === tag.name && selected.type === tag.type)
            );
            
            if (filteredResults.length === 0) {
                dropdown.innerHTML = '<div class="no-results">All matching tags already selected</div>';
                return;
            }
            
            // Generate suggestions HTML
            const html = filteredResults.map((tag, index) => `
                <div class="tag-suggestion-item" data-index="${index}" data-tag-id="${tag.id}" data-tag-name="${tag.name}" data-tag-type="${tag.type}">
                    <span class="tag-suggestion-name">${tag.name}</span>
                    <span class="tag-suggestion-type ${tag.type}">${tag.type}</span>
                </div>
            `).join('');
            
            dropdown.innerHTML = html;
            tagSuggestions = filteredResults;
            activeSuggestionIndex = -1;
            
        } catch (error) {
            console.error('Error searching tags:', error);
            dropdown.innerHTML = '<div class="no-results">Error loading suggestions</div>';
        }
    }
    
    function handleTagKeydown(e) {
        const dropdown = document.getElementById('tag-suggestions-dropdown');
        
        if (dropdown.classList.contains('hidden')) return;
        
        const items = dropdown.querySelectorAll('.tag-suggestion-item');
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                activeSuggestionIndex = Math.min(activeSuggestionIndex + 1, items.length - 1);
                updateSuggestionHighlight(items);
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                activeSuggestionIndex = Math.max(activeSuggestionIndex - 1, -1);
                updateSuggestionHighlight(items);
                break;
                
            case 'Enter':
                e.preventDefault();
                if (activeSuggestionIndex >= 0 && items[activeSuggestionIndex]) {
                    selectTagSuggestion(items[activeSuggestionIndex]);
                }
                break;
                
            case 'Escape':
                hideTagDropdown();
                break;
        }
    }
    
    function updateSuggestionHighlight(items) {
        items.forEach((item, index) => {
            item.classList.toggle('highlighted', index === activeSuggestionIndex);
        });
    }
    
    function handleTagSuggestionClick(e) {
        const item = e.target.closest('.tag-suggestion-item');
        if (item) {
            selectTagSuggestion(item);
        }
    }
    
    function selectTagSuggestion(item) {
        const tagId = item.dataset.tagId;
        const tagName = item.dataset.tagName;
        const tagType = item.dataset.tagType;
        
        addTagChip({ id: parseInt(tagId), name: tagName, type: tagType });
        
        // Clear input and hide dropdown
        document.getElementById('tags-search').value = '';
        hideTagDropdown();
    }
    
    function addTagChip(tag) {
        // Check if tag is already selected
        if (selectedTags.some(selected => selected.name === tag.name && selected.type === tag.type)) {
            return;
        }
        
        selectedTags.push(tag);
        renderTagChips();
    }
    
    function removeTagChip(index) {
        selectedTags.splice(index, 1);
        renderTagChips();
    }
    
    function renderTagChips() {
        const container = document.getElementById('selected-tags-chips');
        
        if (selectedTags.length === 0) {
            container.innerHTML = '';
            return;
        }
        
        const html = selectedTags.map((tag, index) => `
            <div class="search-tag-chip tag-${tag.type}" data-index="${index}">
                ${tag.name}
                <button class="search-tag-chip-remove" data-index="${index}" title="Remove tag">×</button>
            </div>
        `).join('');
        
        container.innerHTML = html;
        
        // Add event listeners to remove buttons
        container.querySelectorAll('.search-tag-chip-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const index = parseInt(e.target.dataset.index);
                removeTagChip(index);
            });
        });
    }
    
    function showTagDropdown() {
        document.getElementById('tag-suggestions-dropdown').classList.remove('hidden');
    }
    
    function hideTagDropdown() {
        const dropdown = document.getElementById('tag-suggestions-dropdown');
        dropdown.classList.add('hidden');
        activeSuggestionIndex = -1;
    }
}); 