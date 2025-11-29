import { api } from './api.js';
import { createIngredientUsageChart } from './charts/ingredientUsageChart.js';
import { createIngredientTreeChart } from './charts/ingredientTreeChart.js';
import { createRecipeComplexityChart } from './charts/recipeComplexityChart.js';
import { createCocktailSpaceChart } from './charts/cocktailSpaceChart.js';
import { createRecipeCard } from './recipeCard.js';

// State management
const state = {
    currentTab: 'ingredients',
    ingredientHierarchy: [],
    currentParentId: null,
    lastUpdated: null
};

/**
 * Initialize the analytics page
 */
async function initAnalytics() {
    console.log('Initializing analytics page');

    // Setup tab navigation
    setupTabNavigation();

    // Load initial data for active tab
    await loadTabData(state.currentTab);

    // Highlight active nav item
    highlightActiveNav();
}

/**
 * Setup tab navigation event listeners
 */
function setupTabNavigation() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', async () => {
            const tabName = button.dataset.tab;

            // Update active states
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            button.classList.add('active');
            document.getElementById(`tab-${tabName}`).classList.add('active');

            // Update state and load data
            state.currentTab = tabName;
            await loadTabData(tabName);

            // Sync mobile view selector
            syncMobileViewSelector(tabName);
        });
    });

    // Setup mobile view selector
    setupMobileViewSelector(tabButtons, tabContents);
}

/**
 * Setup mobile view selector event listener
 */
function setupMobileViewSelector(tabButtons, tabContents) {
    const mobileViewSelect = document.getElementById('mobile-view-select');
    if (!mobileViewSelect) return;

    mobileViewSelect.addEventListener('change', async (e) => {
        const selectedTab = e.target.value;

        // Update active states
        tabButtons.forEach(btn => btn.classList.remove('active'));
        tabContents.forEach(content => content.classList.remove('active'));

        // Find and activate the corresponding tab button and content
        const tabButton = document.querySelector(`.tab-button[data-tab="${selectedTab}"]`);
        if (tabButton) {
            tabButton.classList.add('active');
        }

        const tabContent = document.getElementById(`tab-${selectedTab}`);
        if (tabContent) {
            tabContent.classList.add('active');
        }

        // Update state and load data
        state.currentTab = selectedTab;
        await loadTabData(selectedTab);
    });
}

/**
 * Sync mobile view selector with current tab
 */
function syncMobileViewSelector(tabName) {
    const mobileViewSelect = document.getElementById('mobile-view-select');
    if (mobileViewSelect) {
        mobileViewSelect.value = tabName;
    }
}

/**
 * Load data for specific tab
 * @param {string} tabName - Name of the tab to load
 */
async function loadTabData(tabName) {
    console.log(`Loading data for tab: ${tabName}`);

    switch (tabName) {
        case 'ingredients':
            await loadIngredientUsageData();
            break;
        case 'ingredient-tree':
            await loadIngredientTreeData();
            break;
        case 'complexity':
            await loadRecipeComplexityData();
            break;
        case 'cocktail-space':
            await loadCocktailSpaceData();
            break;
    }
}

/**
 * Load and render ingredient usage analytics
 */
async function loadIngredientUsageData() {
    const chartContainer = document.getElementById('ingredient-usage-chart');
    const loadingState = document.getElementById('ingredient-chart-loading');
    const errorState = document.getElementById('ingredient-chart-error');

    // Show loading state
    chartContainer.innerHTML = '';
    loadingState.classList.remove('hidden');
    errorState.classList.add('hidden');

    try {
        // Only include parent_id if it's not null
        const options = {};
        if (state.currentParentId !== null) {
            options.parent_id = state.currentParentId;
        }
        const response = await api.getIngredientUsageAnalytics(options);

        // Update last updated time (present when served from cache)
        if (response.metadata?.generated_at) {
            updateLastUpdatedTime(response.metadata.generated_at);
        } else {
            // On-the-fly computation - show current time
            updateLastUpdatedTime(new Date().toISOString());
        }

        // Hide loading
        loadingState.classList.add('hidden');

        // Check for empty data
        if (!response.data || response.data.length === 0) {
            chartContainer.innerHTML = '<div class="no-data"><p>No ingredient usage data available.</p></div>';
            document.getElementById('ingredients-shown-count').textContent = '0';
            return;
        }

        // Render chart
        createIngredientUsageChart(chartContainer, response.data, {
            onIngredientClick: handleIngredientClick
        });

        // Update stats
        document.getElementById('ingredients-shown-count').textContent = response.data.length;

    } catch (error) {
        console.error('Error loading ingredient usage data:', error);
        loadingState.classList.add('hidden');
        errorState.classList.remove('hidden');
        errorState.querySelector('.error-message').textContent =
            `Failed to load ingredient usage data: ${error.message}`;

        // Setup retry button
        errorState.querySelector('.retry-btn').onclick = () => loadIngredientUsageData();
    }
}

/**
 * Handle ingredient click for drilldown
 */
async function handleIngredientClick(ingredientData) {
    if (!ingredientData.has_children) {
        console.log('Ingredient has no children, ignoring click');
        return;
    }

    console.log('Drilling down into ingredient:', ingredientData.ingredient_name);

    // Add to breadcrumb navigation
    state.ingredientHierarchy.push({
        id: ingredientData.ingredient_id,
        name: ingredientData.ingredient_name
    });

    // Update current parent
    state.currentParentId = ingredientData.ingredient_id;

    // Update breadcrumb UI
    updateBreadcrumb();

    // Load child ingredients
    await loadIngredientUsageData();
}

/**
 * Update breadcrumb navigation
 */
function updateBreadcrumb() {
    const breadcrumb = document.getElementById('ingredient-breadcrumb');

    if (state.ingredientHierarchy.length === 0) {
        breadcrumb.classList.add('hidden');
        return;
    }

    breadcrumb.classList.remove('hidden');

    // Build breadcrumb HTML
    let html = '<button class="breadcrumb-item" data-level="root">All Ingredients</button>';

    state.ingredientHierarchy.forEach((item, index) => {
        html += `<span class="breadcrumb-separator">›</span>`;
        html += `<button class="breadcrumb-item" data-level="${index}">${item.name}</button>`;
    });

    breadcrumb.innerHTML = html;

    // Add click handlers
    breadcrumb.querySelectorAll('.breadcrumb-item').forEach(button => {
        button.addEventListener('click', () => {
            const level = button.dataset.level;
            navigateToBreadcrumbLevel(level);
        });
    });
}

/**
 * Navigate to specific breadcrumb level
 */
async function navigateToBreadcrumbLevel(level) {
    if (level === 'root') {
        state.ingredientHierarchy = [];
        state.currentParentId = null;
    } else {
        const levelIndex = parseInt(level);
        state.ingredientHierarchy = state.ingredientHierarchy.slice(0, levelIndex + 1);
        state.currentParentId = state.ingredientHierarchy[levelIndex].id;
    }

    updateBreadcrumb();
    await loadIngredientUsageData();
}

/**
 * Load and render ingredient tree analytics
 */
async function loadIngredientTreeData() {
    const chartContainer = document.getElementById('ingredient-tree-chart');
    const loadingState = document.getElementById('ingredient-tree-loading');
    const errorState = document.getElementById('ingredient-tree-error');

    // Show loading state
    chartContainer.innerHTML = '';
    loadingState.classList.remove('hidden');
    errorState.classList.add('hidden');

    try {
        const response = await api.getIngredientTreeAnalytics();

        // Update last updated time
        if (response.metadata?.generated_at) {
            updateLastUpdatedTime(response.metadata.generated_at);
        } else {
            updateLastUpdatedTime(new Date().toISOString());
        }

        // Hide loading
        loadingState.classList.add('hidden');

        // Extract tree data from response (stored in S3 with data/metadata wrapper)
        const treeData = response.data || response;

        // Check for empty data
        if (!treeData || !treeData.id) {
            chartContainer.innerHTML = '<div class="no-data"><p>No ingredient tree data available.</p></div>';
            document.getElementById('ingredient-tree-count').textContent = '0';
            return;
        }

        // Count total ingredients (recursive)
        function countIngredients(node) {
            let count = node.id === 'root' ? 0 : 1;
            if (node.children) {
                node.children.forEach(child => {
                    count += countIngredients(child);
                });
            }
            return count;
        }

        const totalIngredients = countIngredients(treeData);

        // Render tree
        createIngredientTreeChart(chartContainer, treeData);

        // Update stats
        document.getElementById('ingredient-tree-count').textContent = totalIngredients;

    } catch (error) {
        console.error('Error loading ingredient tree data:', error);
        loadingState.classList.add('hidden');
        errorState.classList.remove('hidden');
        errorState.querySelector('.error-message').textContent =
            `Failed to load ingredient tree data: ${error.message}`;

        // Setup retry button
        errorState.querySelector('.retry-btn').onclick = () => loadIngredientTreeData();
    }
}

/**
 * Load and render recipe complexity analytics
 */
async function loadRecipeComplexityData() {
    const chartContainer = document.getElementById('recipe-complexity-chart');
    const loadingState = document.getElementById('complexity-chart-loading');
    const errorState = document.getElementById('complexity-chart-error');

    chartContainer.innerHTML = '';
    loadingState.classList.remove('hidden');
    errorState.classList.add('hidden');

    try {
        const response = await api.getRecipeComplexityAnalytics();

        // Update last updated time (present when served from cache)
        if (response.metadata?.generated_at) {
            updateLastUpdatedTime(response.metadata.generated_at);
        } else {
            // On-the-fly computation - show current time
            updateLastUpdatedTime(new Date().toISOString());
        }

        loadingState.classList.add('hidden');

        // Check for empty data
        if (!response.data || response.data.length === 0) {
            chartContainer.innerHTML = '<div class="no-data"><p>No recipe complexity data available.</p></div>';
            document.getElementById('avg-ingredients').textContent = '-';
            document.getElementById('mode-ingredients').textContent = '-';
            return;
        }

        // Render chart
        createRecipeComplexityChart(chartContainer, response.data);

        // Calculate and display stats
        const avg = calculateAverage(response.data);
        const mode = findMode(response.data);

        document.getElementById('avg-ingredients').textContent = avg.toFixed(1);
        document.getElementById('mode-ingredients').textContent =
            `${mode.ingredient_count} ingredients (${mode.recipe_count} recipes)`;

    } catch (error) {
        console.error('Error loading complexity data:', error);
        loadingState.classList.add('hidden');
        errorState.classList.remove('hidden');
        errorState.querySelector('.error-message').textContent =
            `Failed to load complexity data: ${error.message}`;
        errorState.querySelector('.retry-btn').onclick = () => loadRecipeComplexityData();
    }
}

/**
 * Load and render cocktail space analytics
 */
async function loadCocktailSpaceData() {
    const chartContainer = document.getElementById('cocktail-space-chart');
    const loadingState = document.getElementById('cocktail-space-loading');
    const errorState = document.getElementById('cocktail-space-error');

    chartContainer.innerHTML = '';
    loadingState.classList.remove('hidden');
    errorState.classList.add('hidden');

    try {
        const response = await api.getCocktailSpaceAnalytics();

        // Update last updated time (present when served from cache)
        if (response.metadata?.generated_at) {
            updateLastUpdatedTime(response.metadata.generated_at);
        } else {
            updateLastUpdatedTime(new Date().toISOString());
        }

        loadingState.classList.add('hidden');

        // Check for empty data
        if (!response.data || response.data.length === 0) {
            chartContainer.innerHTML = '<div class="no-data"><p>No cocktail space data available.</p></div>';
            document.getElementById('cocktail-space-count').textContent = '0';
            return;
        }

        // Render chart
        createCocktailSpaceChart(chartContainer, response.data, {
            onRecipeClick: handleRecipeClick
        });

        // Update stats
        document.getElementById('cocktail-space-count').textContent = response.data.length;

    } catch (error) {
        console.error('Error loading cocktail space data:', error);
        loadingState.classList.add('hidden');
        errorState.classList.remove('hidden');
        errorState.querySelector('.error-message').textContent =
            `Failed to load cocktail space data: ${error.message}`;

        // Setup retry button
        errorState.querySelector('.retry-btn').onclick = () => loadCocktailSpaceData();
    }
}

// Helper functions

function updateLastUpdatedTime(timestamp) {
    const lastUpdatedEl = document.getElementById('last-updated');
    const date = new Date(timestamp);
    lastUpdatedEl.textContent = `Last updated: ${date.toLocaleString()}`;
}

function calculateAverage(data) {
    let totalIngredients = 0;
    let totalRecipes = 0;

    data.forEach(item => {
        totalIngredients += item.ingredient_count * item.recipe_count;
        totalRecipes += item.recipe_count;
    });

    return totalRecipes > 0 ? totalIngredients / totalRecipes : 0;
}

function findMode(data) {
    if (data.length === 0) return { ingredient_count: 0, recipe_count: 0 };

    return data.reduce((max, item) =>
        item.recipe_count > max.recipe_count ? item : max
    );
}

function highlightActiveNav() {
    const navLinks = document.querySelectorAll('nav a');
    navLinks.forEach(link => {
        if (link.href.includes('analytics.html')) {
            link.classList.add('active');
        }
    });
}

/**
 * Handle recipe click from cocktail space chart
 */
async function handleRecipeClick(recipeId, recipeName) {
    console.log('Recipe clicked:', recipeId, recipeName);

    const modal = document.getElementById('recipe-modal');
    const modalBody = document.getElementById('recipe-modal-card');
    const modalLoading = document.getElementById('recipe-modal-loading');
    const modalLink = document.getElementById('recipe-modal-link');

    // Show modal
    modal.classList.remove('hidden');
    modalBody.innerHTML = '';
    modalLoading.classList.remove('hidden');

    try {
        // Fetch full recipe data
        const recipe = await api.getRecipe(recipeId);

        // Hide loading
        modalLoading.classList.add('hidden');

        // Create recipe card
        const recipeCard = createRecipeCard(recipe, false);
        modalBody.appendChild(recipeCard);

        // Set up link to full recipe page
        modalLink.href = `/recipe.html?name=${encodeURIComponent(recipeName)}`;

    } catch (error) {
        console.error('Error loading recipe:', error);
        modalLoading.classList.add('hidden');
        modalBody.innerHTML = `<div class="error-state"><p class="error-message">Failed to load recipe: ${error.message}</p></div>`;
    }
}

/**
 * Close recipe modal
 */
function closeRecipeModal() {
    const modal = document.getElementById('recipe-modal');
    modal.classList.add('hidden');

    // Clean up any lingering ingredient hierarchy tooltips
    const tooltips = document.querySelectorAll('.ingredient-hierarchy-tooltip');
    tooltips.forEach(tooltip => tooltip.remove());
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initAnalytics);

// Set up modal close handlers
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('recipe-modal');
    const modalClose = modal?.querySelector('.modal-close');
    const modalBackdrop = modal?.querySelector('.modal-backdrop');

    if (modalClose) {
        modalClose.addEventListener('click', closeRecipeModal);
    }

    if (modalBackdrop) {
        modalBackdrop.addEventListener('click', closeRecipeModal);
    }

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeRecipeModal();
        }
    });
});
