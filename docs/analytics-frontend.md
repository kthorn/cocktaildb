# Analytics Frontend Page Structure

## Overview
This document specifies the frontend structure for the cocktail database analytics page, including HTML layout, navigation integration, API client methods, and user interface components.

## Objectives
- Create a dedicated analytics page accessible from main navigation
- Implement clean, responsive layout for multiple analytics visualizations
- Integrate with backend analytics API endpoints
- Provide loading states and error handling
- All analytics are publicly accessible (no authentication required)

## File Structure

```
src/web/
├── analytics.html           # Main analytics page
├── js/
│   ├── analytics.js         # Page controller and orchestration
│   ├── api.js              # API client (add analytics methods)
│   ├── common.js           # Navigation update
│   └── charts/             # New directory for chart components
│       ├── ingredientUsageChart.js
│       └── recipeComplexityChart.js
└── styles.css              # Add analytics-specific styles
```

## Backend API Notes

### Analytics Endpoints
The backend provides two analytics endpoints:
- `GET /api/v1/analytics/ingredient-usage?parent_id={id}` - Hierarchical ingredient usage
- `GET /api/v1/analytics/recipe-complexity` - Recipe complexity distribution

### Response Format
All analytics endpoints return:
```json
{
  "data": [...],
  "metadata": {
    "generated_at": "2025-01-15T10:30:00.000Z",  // Present when served from S3 cache
    "total_recipes": 123,                         // Present when computed on-the-fly
    "storage_version": "v1",                      // S3 cache version
    "analytics_type": "ingredient-usage"          // Type identifier
  }
}
```

### Caching Behavior
- Backend attempts to serve pre-generated analytics from S3 first
- If cache miss, computes analytics on-the-fly from database
- Cached responses include `generated_at` timestamp
- On-the-fly responses may include additional fields like `total_recipes`
- Analytics automatically refresh after recipe/ingredient mutations

### Ingredient Usage Hierarchy
- `parent_id` parameter filters to children of specific ingredient
- Omit `parent_id` to get root-level ingredients
- `level` parameter is NOT currently used by backend (reserved for future use)
- Response includes `has_children` boolean to enable drill-down UI

### Data Fields
**Ingredient Usage Response:**
- `ingredient_id`: Unique ingredient ID
- `ingredient_name`: Display name
- `path`: Hierarchical path (e.g., `/1/23/45/`)
- `parent_id`: Parent ingredient ID or null for root
- `direct_usage`: Count of recipes using this ingredient directly
- `hierarchical_usage`: Count including all child ingredients
- `has_children`: Boolean indicating if drill-down is possible

**Recipe Complexity Response:**
- `ingredient_count`: Number of ingredients in recipe
- `recipe_count`: Number of recipes with that ingredient count

## Technical Specifications

### 1. HTML Page Structure

Create `src/web/analytics.html`:

```html
<!DOCTYPE html>
<html lang="en">

<head>
    <title>Analytics - Cocktail Database</title>
    <!-- Prevent FOUC (Flash of Unstyled Content) with common.js fallback -->
</head>

<body>
    <!-- Header will be loaded by common.js -->

    <main class="analytics-container">
        <section class="analytics-header">
            <h2>Database Analytics</h2>
            <p class="analytics-description">
                Explore insights and statistics about cocktail recipes and ingredients in the database.
            </p>
            <div class="analytics-meta">
                <span id="last-updated"></span>
            </div>
        </section>

        <!-- Navigation tabs for different analytics views -->
        <nav class="analytics-tabs">
            <button class="tab-button active" data-tab="ingredients">
                Ingredient Usage
            </button>
            <button class="tab-button" data-tab="complexity">
                Recipe Complexity
            </button>
        </nav>

        <!-- Tab content containers -->
        <div class="analytics-content">
            <!-- Ingredient Usage Tab -->
            <section id="tab-ingredients" class="tab-content active">
                <div class="analytics-card">
                    <div class="card-header">
                        <h3>Ingredient Usage by Recipe Count</h3>
                        <p class="card-description">
                            Click on an ingredient to explore its subtypes.
                            Usage counts include all child ingredients.
                        </p>
                    </div>

                    <!-- Breadcrumb navigation for hierarchy -->
                    <div id="ingredient-breadcrumb" class="breadcrumb-nav hidden">
                        <button class="breadcrumb-item" data-level="root">
                            All Ingredients
                        </button>
                    </div>

                    <div class="chart-container">
                        <div id="ingredient-usage-chart" class="chart-area">
                            <!-- D3.js chart will be rendered here -->
                        </div>
                        <div id="ingredient-chart-loading" class="loading-state">
                            <div class="spinner"></div>
                            <p>Loading ingredient data...</p>
                        </div>
                        <div id="ingredient-chart-error" class="error-state hidden">
                            <p class="error-message"></p>
                            <button class="btn-primary retry-btn">Retry</button>
                        </div>
                    </div>

                    <!-- Chart legend and info -->
                    <div class="chart-info">
                        <div class="legend">
                            <span class="legend-item">
                                <span class="legend-color" style="background: #1f77b4;"></span>
                                Has subtypes (click to expand)
                            </span>
                            <span class="legend-item">
                                <span class="legend-color" style="background: #aec7e8;"></span>
                                Leaf ingredient
                            </span>
                        </div>
                        <div class="chart-stats">
                            <span id="ingredients-shown-count">-</span> ingredients displayed
                        </div>
                    </div>
                </div>
            </section>

            <!-- Recipe Complexity Tab -->
            <section id="tab-complexity" class="tab-content">
                <div class="analytics-card">
                    <div class="card-header">
                        <h3>Recipe Complexity Distribution</h3>
                        <p class="card-description">
                            Distribution of recipes by number of ingredients.
                        </p>
                    </div>

                    <div class="chart-container">
                        <div id="recipe-complexity-chart" class="chart-area">
                            <!-- Chart will be rendered here -->
                        </div>
                        <div id="complexity-chart-loading" class="loading-state">
                            <div class="spinner"></div>
                            <p>Loading complexity data...</p>
                        </div>
                        <div id="complexity-chart-error" class="error-state hidden">
                            <p class="error-message"></p>
                            <button class="btn-primary retry-btn">Retry</button>
                        </div>
                    </div>

                    <div class="chart-info">
                        <div class="stats-summary">
                            <div class="stat-item">
                                <span class="stat-label">Average ingredients:</span>
                                <span id="avg-ingredients" class="stat-value">-</span>
                            </div>
                            <div class="stat-item">
                                <span class="stat-label">Most common:</span>
                                <span id="mode-ingredients" class="stat-value">-</span>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
        </div>

        <!-- Info footer -->
        <section class="analytics-footer">
            <p class="info-text">
                Analytics are updated automatically when recipes or ingredients are modified.
            </p>
        </section>
    </main>

    <!-- Footer will be loaded by common.js -->

    <!-- Load D3.js library -->
    <script src="https://d3js.org/d3.v7.min.js"></script>

    <!-- Load application scripts -->
    <script type="module" src="js/common.js"></script>
    <script type="module" src="js/api.js"></script>
    <script type="module" src="js/charts/ingredientUsageChart.js"></script>
    <script type="module" src="js/charts/recipeComplexityChart.js"></script>
    <script type="module" src="js/analytics.js"></script>
</body>

</html>
```

### 2. Navigation Integration

Update `src/web/js/common.js` to add analytics link to header navigation:

```javascript
export function loadHeader() {
  const header = document.createElement('header');
  header.innerHTML = `
    <h1>Cocktail Database</h1>
    <nav>
      <ul>
        <li><a href="index.html">Home</a></li>
        <li><a href="ingredients.html">All Ingredients</a></li>
        <li><a href="user-ingredients.html">My Ingredients</a></li>
        <li><a href="recipes.html">Add Recipes</a></li>
        <li><a href="search.html">Search Recipes</a></li>
        <li><a href="analytics.html">Analytics</a></li>
        <li><a href="about.html">About</a></li>
        <li><a href="admin.html">Admin</a></li>
      </ul>
      <div class="auth-controls">
        <span id="user-info" class="hidden">
          <button id="logout-btn">Logout</button>
        </span>
        <button id="login-btn">Login</button>
        <button id="signup-btn">Sign Up</button>
      </div>
    </nav>
  `;

  // ... rest of function unchanged
}
```

### 3. API Client Extensions

Add analytics methods to `src/web/js/api.js`:

```javascript
class CocktailAPI {
    // ... existing methods ...

    /**
     * Get ingredient usage analytics
     * @param {Object} options - Query options
     * @param {number} options.parent_id - Parent ingredient ID (optional, omit for root level)
     * @returns {Promise<Object>} Analytics data with metadata
     *
     * Response format:
     * {
     *   data: [{
     *     ingredient_id: number,
     *     ingredient_name: string,
     *     path: string,
     *     parent_id: number|null,
     *     direct_usage: number,
     *     hierarchical_usage: number,
     *     has_children: boolean
     *   }],
     *   metadata: {
     *     generated_at?: string,  // ISO timestamp if from cache
     *     total_recipes?: number,  // Present if computed on-the-fly
     *     storage_version?: string,
     *     analytics_type?: string
     *   }
     * }
     */
    async getIngredientUsageAnalytics(options = {}) {
        const params = new URLSearchParams();
        if (options.parent_id !== undefined) params.append('parent_id', options.parent_id);

        const queryString = params.toString();
        const url = `${this.baseUrl}/api/v1/analytics/ingredient-usage${queryString ? '?' + queryString : ''}`;

        const response = await fetch(url, this.getFetchOptions('GET', null, false));
        return this.handleResponse(response);
    }

    /**
     * Get recipe complexity distribution analytics
     * @returns {Promise<Object>} Complexity distribution data
     *
     * Response format:
     * {
     *   data: [{
     *     ingredient_count: number,
     *     recipe_count: number
     *   }],
     *   metadata: {
     *     generated_at?: string,  // ISO timestamp if from cache
     *     storage_version?: string,
     *     analytics_type?: string
     *   }
     * }
     */
    async getRecipeComplexityAnalytics() {
        const url = `${this.baseUrl}/api/v1/analytics/recipe-complexity`;
        const response = await fetch(url, this.getFetchOptions('GET', null, false));
        return this.handleResponse(response);
    }

}
```

### 4. Main Analytics Page Controller

Create `src/web/js/analytics.js`:

```javascript
import { api } from './api.js';
import { createIngredientUsageChart } from './charts/ingredientUsageChart.js';
import { createRecipeComplexityChart } from './charts/recipeComplexityChart.js';

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
        });
    });
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
        case 'complexity':
            await loadRecipeComplexityData();
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
        const response = await api.getIngredientUsageAnalytics({
            parent_id: state.currentParentId
        });

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

function showNotification(message, type = 'info') {
    // Simple notification - could be enhanced with a toast library
    alert(message);
}

function highlightActiveNav() {
    const navLinks = document.querySelectorAll('nav a');
    navLinks.forEach(link => {
        if (link.href.includes('analytics.html')) {
            link.classList.add('active');
        }
    });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initAnalytics);
```

### 5. CSS Styling

Add to `src/web/styles.css`:

```css
/* Analytics Page Styles */

.analytics-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

.analytics-header {
    margin-bottom: 2rem;
}

.analytics-header h2 {
    margin-bottom: 0.5rem;
}

.analytics-description {
    color: #666;
    margin-bottom: 0.5rem;
}

.analytics-meta {
    color: #888;
    font-size: 0.9rem;
    margin-top: 0.5rem;
}

/* Tabs */

.analytics-tabs {
    display: flex;
    gap: 0.5rem;
    border-bottom: 2px solid #ddd;
    margin-bottom: 2rem;
}

.tab-button {
    padding: 0.75rem 1.5rem;
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    cursor: pointer;
    font-size: 1rem;
    color: #666;
    transition: all 0.2s;
}

.tab-button:hover {
    color: #333;
    background-color: #f5f5f5;
}

.tab-button.active {
    color: #1f77b4;
    border-bottom-color: #1f77b4;
    font-weight: 500;
}

.tab-content {
    display: none;
}

.tab-content.active {
    display: block;
}

/* Analytics Cards */

.analytics-card {
    background: white;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 2rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.card-header {
    margin-bottom: 1.5rem;
}

.card-header h3 {
    margin-bottom: 0.5rem;
}

.card-description {
    color: #666;
    font-size: 0.95rem;
}

/* Charts */

.chart-container {
    position: relative;
    min-height: 400px;
}

.chart-area {
    width: 100%;
    min-height: 400px;
}

/* Loading and Error States */

.loading-state, .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 300px;
    text-align: center;
}

.loading-state.hidden, .error-state.hidden {
    display: none;
}

.spinner {
    width: 40px;
    height: 40px;
    border: 4px solid #f3f3f3;
    border-top: 4px solid #1f77b4;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

.error-message {
    color: #d32f2f;
    margin-bottom: 1rem;
}

.retry-btn {
    padding: 0.5rem 1rem;
    background: #1f77b4;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

.retry-btn:hover {
    background: #1565c0;
}

/* Breadcrumb Navigation */

.breadcrumb-nav {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
    padding: 0.75rem;
    background: #f5f5f5;
    border-radius: 4px;
    flex-wrap: wrap;
}

.breadcrumb-nav.hidden {
    display: none;
}

.breadcrumb-item {
    background: white;
    border: 1px solid #ddd;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.9rem;
    transition: all 0.2s;
}

.breadcrumb-item:hover {
    background: #1f77b4;
    color: white;
    border-color: #1f77b4;
}

.breadcrumb-separator {
    color: #999;
}

/* Chart Info */

.chart-info {
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid #eee;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.legend {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
}

.legend-color {
    width: 20px;
    height: 12px;
    border-radius: 2px;
}

.chart-stats {
    color: #666;
    font-size: 0.9rem;
}

/* Stats Summary */

.stats-summary {
    display: flex;
    gap: 2rem;
}

.stat-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.stat-label {
    color: #666;
    font-size: 0.85rem;
}

.stat-value {
    font-size: 1.25rem;
    font-weight: 600;
    color: #1f77b4;
}

.no-data {
    text-align: center;
    color: #888;
    padding: 2rem;
}

/* Footer */

.analytics-footer {
    margin-top: 3rem;
    padding-top: 2rem;
    border-top: 1px solid #ddd;
    text-align: center;
}

.info-text {
    color: #666;
    font-size: 0.9rem;
}


/* Responsive Design */

@media (max-width: 768px) {
    .analytics-container {
        padding: 1rem;
    }

    .analytics-tabs {
        overflow-x: auto;
    }

    .tab-button {
        white-space: nowrap;
    }

    .chart-info {
        flex-direction: column;
        gap: 1rem;
        align-items: flex-start;
    }

    .stats-summary {
        flex-direction: column;
        gap: 1rem;
    }
}
```

## Chart Component Specifications

The analytics page requires two chart components that will be implemented separately. This section defines their interfaces and responsibilities.

### 6. Ingredient Usage Chart Component

Create `src/web/js/charts/ingredientUsageChart.js`:

```javascript
/**
 * Create an interactive ingredient usage bar chart using D3.js
 *
 * @param {HTMLElement} container - DOM element to render chart into
 * @param {Array} data - Array of ingredient usage objects
 * @param {Object} options - Configuration options
 * @param {Function} options.onIngredientClick - Callback when ingredient is clicked: (ingredientData) => {}
 *
 * Data format:
 * [{
 *   ingredient_id: number,
 *   ingredient_name: string,
 *   path: string,
 *   parent_id: number|null,
 *   direct_usage: number,
 *   hierarchical_usage: number,
 *   has_children: boolean
 * }]
 *
 * Expected behavior:
 * - Render horizontal bar chart sorted by hierarchical_usage descending
 * - Use hierarchical_usage for bar length
 * - Color bars differently based on has_children (darker = clickable, lighter = leaf)
 * - Add click handlers to bars with has_children=true
 * - Show tooltip on hover with both direct and hierarchical counts
 * - Handle empty data gracefully (caller handles this)
 * - Responsive design (adjust to container width)
 *
 * @returns {void}
 */
export function createIngredientUsageChart(container, data, options = {}) {
    // Implementation will use D3.js to create horizontal bar chart
    // Details to be implemented in next phase
}
```

### 7. Recipe Complexity Chart Component

Create `src/web/js/charts/recipeComplexityChart.js`:

```javascript
/**
 * Create a recipe complexity distribution chart using D3.js
 *
 * @param {HTMLElement} container - DOM element to render chart into
 * @param {Array} data - Array of complexity distribution objects
 *
 * Data format:
 * [{
 *   ingredient_count: number,
 *   recipe_count: number
 * }]
 *
 * Expected behavior:
 * - Render vertical bar chart showing distribution
 * - X-axis: ingredient_count (number of ingredients)
 * - Y-axis: recipe_count (number of recipes)
 * - Sort by ingredient_count ascending
 * - Show value labels on bars
 * - Highlight mode (most common) with different color
 * - Handle empty data gracefully (caller handles this)
 * - Responsive design (adjust to container width)
 *
 * @returns {void}
 */
export function createRecipeComplexityChart(container, data) {
    // Implementation will use D3.js to create vertical bar chart
    // Details to be implemented in next phase
}
```

### D3.js Implementation Guidelines

Both chart components should follow these patterns:

**Basic Structure:**
```javascript
export function createChart(container, data, options = {}) {
    // 1. Clear container
    container.innerHTML = '';

    // 2. Set up dimensions
    const margin = { top: 20, right: 20, bottom: 40, left: 100 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = 400 - margin.top - margin.bottom;

    // 3. Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // 4. Create scales
    // 5. Create axes
    // 6. Draw chart elements
    // 7. Add interactivity
}
```

**Responsive Behavior:**
- Charts should resize to fit container width
- Consider adding window resize listener for dynamic resizing
- Or accept fixed container size and handle overflow

**Accessibility:**
- Add ARIA labels to SVG elements
- Ensure sufficient color contrast
- Add keyboard navigation for interactive elements

**Error Handling:**
- Empty data is handled by caller (displays "no data" message)
- Invalid data should log error and display placeholder
- D3.js errors should be caught and logged

## Testing Approach

### Manual Testing Checklist
- [ ] Page loads without errors
- [ ] Both tabs (Ingredient Usage, Recipe Complexity) are accessible and switch correctly
- [ ] Loading states display properly
- [ ] Error states show when API fails
- [ ] Retry buttons work
- [ ] Navigation link highlights correctly
- [ ] Responsive design works on mobile
- [ ] Charts render in each tab
- [ ] Breadcrumb navigation functions correctly
- [ ] Empty state displays when no data available
- [ ] Drill-down to child ingredients works
- [ ] Drill-up via breadcrumb navigation works

### Browser Testing
- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

### Accessibility Testing
- Keyboard navigation works
- Screen reader compatibility
- Color contrast meets WCAG standards
- Focus indicators visible

## Dependencies

### External Libraries
- **D3.js v7** - Loaded via CDN: `https://d3js.org/d3.v7.min.js`

### Internal Dependencies
- `common.js` - Navigation and page structure
- `api.js` - API client (singleton instance)
- Chart components (`charts/ingredientUsageChart.js`, `charts/recipeComplexityChart.js`)

### Known Limitations
- **Breadcrumb state not persisted**: Drill-down navigation state is lost on page refresh. Users must start from root level after reloading.
- **No URL state management**: Drill-down level not reflected in URL (no deep linking to specific hierarchy levels)
- **Cache behavior**: Drill-down queries (with `parent_id`) always compute on-the-fly; only root-level data is cached

## Backend Implementation Notes

### Current Caching Strategy
The backend uses a simple caching approach:
1. **Pre-generated data**: Root-level analytics stored in S3 by `AnalyticsRefreshFunction`
2. **On-demand computation**: Drill-down queries (with `parent_id`) computed on-the-fly
3. **Automatic refresh**: Mutations trigger async regeneration of root-level cache

### Storage Key Considerations
- `analytics_refresh.py` stores only root-level data: `ingredient-usage`, `recipe-complexity`
- `routes/analytics.py` attempts to fetch with keys like `ingredient-usage-None-None`
- **This creates a mismatch**: drill-down queries always compute on-the-fly
- **Future enhancement**: Store drill-down results in S3 with parent_id in key

### Performance Implications
- Root-level queries: Fast (served from S3 cache)
- Drill-down queries: Moderate (on-the-fly database query with hierarchical aggregation)
- Cache miss fallback: Graceful degradation to on-the-fly computation

### Metadata Differences
Frontend should handle both cache and on-the-fly responses:
```javascript
// Cached response
{
  data: [...],
  metadata: {
    generated_at: "2025-01-15T10:30:00.000Z",
    storage_version: "v1",
    analytics_type: "ingredient-usage"
  }
}

// On-the-fly response
{
  data: [...],
  metadata: {
    total_recipes: 123
  }
}
```

## Future Enhancements

### Short Term
- Store drill-down analytics in S3 (cache all `parent_id` combinations)
- Add cache warmup on deployment
- Implement cache TTL and manual invalidation

### Long Term
- Add date range filters for time-based analytics
- Implement data export (CSV/JSON download)
- Add comparison views (side-by-side analytics)
- User-specific analytics for authenticated users
- Real-time updates via WebSocket
- More advanced visualizations (network graphs, heatmaps)
- Dashboard customization (user can choose which analytics to display)
