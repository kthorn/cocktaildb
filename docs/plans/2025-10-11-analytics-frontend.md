# Analytics Frontend Implementation Plan

> **For Claude:** Use `${CLAUDE_PLUGIN_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Build a public analytics dashboard page showing ingredient usage and recipe complexity visualizations with hierarchical drill-down navigation.

**Architecture:** Static HTML page with vanilla JavaScript, D3.js charts, tab navigation, and hierarchical breadcrumb drill-down. All data fetched from FastAPI backend analytics endpoints. No authentication required - fully public access.

**Tech Stack:** HTML5, Vanilla JavaScript (ES6 modules), D3.js v7, CSS3, FastAPI backend endpoints

---

## Task 1: Add Analytics Methods to API Client

**Files:**
- Modify: `src/web/js/api.js` (add methods after line 443, before closing brace)

**Step 1: Add getIngredientUsageAnalytics method**

Add this method to the `CocktailAPI` class:

```javascript
    // Analytics API
    async getIngredientUsageAnalytics(options = {}) {
        const params = new URLSearchParams();
        if (options.parent_id !== undefined) params.append('parent_id', options.parent_id);

        const queryString = params.toString();
        const url = `/api/v1/analytics/ingredient-usage${queryString ? '?' + queryString : ''}`;

        return this._request(url, 'GET', null, false);
    }
```

**Step 2: Add getRecipeComplexityAnalytics method**

Add this method immediately after the previous one:

```javascript
    async getRecipeComplexityAnalytics() {
        const url = `/api/v1/analytics/recipe-complexity`;
        return this._request(url, 'GET', null, false);
    }
```

**Step 3: Test API methods manually**

Open browser console on any page and run:
```javascript
import { api } from './js/api.js';
api.getIngredientUsageAnalytics().then(console.log);
api.getRecipeComplexityAnalytics().then(console.log);
```

Expected: Both return `{data: [...], metadata: {...}}` objects

**Step 4: Commit**

```bash
git add src/web/js/api.js
git commit -m "feat: add analytics API methods to client"
```

---

## Task 2: Update Navigation to Include Analytics Link

**Files:**
- Modify: `src/web/js/common.js:40-47` (navigation list)

**Step 1: Add analytics link to navigation**

In the `loadHeader()` function, update the navigation list to include the analytics link:

```javascript
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
```

**Step 2: Test navigation on existing pages**

Open any existing page (e.g., `index.html`) and verify:
- Analytics link appears in navigation
- Clicking it navigates to `analytics.html` (will 404 for now - expected)

**Step 3: Commit**

```bash
git add src/web/js/common.js
git commit -m "feat: add analytics link to navigation"
```

---

## Task 3: Add Analytics CSS Styles

**Files:**
- Modify: `src/web/styles.css` (append to end of file)

**Step 1: Add analytics page styles**

Append the following CSS to `styles.css`:

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

**Step 2: Verify CSS file syntax**

```bash
# CSS has no easy linter, but check file size to ensure it was written
ls -lh src/web/styles.css
```

Expected: File size increased by ~3-4KB

**Step 3: Commit**

```bash
git add src/web/styles.css
git commit -m "feat: add analytics page CSS styles"
```

---

## Task 4: Create Analytics HTML Page

**Files:**
- Create: `src/web/analytics.html`

**Step 1: Create analytics.html file**

Create `src/web/analytics.html` with this content:

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

**Step 2: Test HTML page loads**

Open `src/web/analytics.html` in browser:
- Header and footer should load from common.js
- Loading spinners should be visible (charts not implemented yet)
- Tab buttons should be visible
- No console errors (except 404s for chart JS files - expected)

**Step 3: Commit**

```bash
git add src/web/analytics.html
git commit -m "feat: create analytics HTML page structure"
```

---

## Task 5: Create Ingredient Usage Chart Component (Stub)

**Files:**
- Create: `src/web/js/charts/` directory
- Create: `src/web/js/charts/ingredientUsageChart.js`

**Step 1: Create charts directory**

```bash
mkdir -p src/web/js/charts
```

**Step 2: Create stub chart component**

Create `src/web/js/charts/ingredientUsageChart.js`:

```javascript
/**
 * Create an interactive ingredient usage bar chart using D3.js
 *
 * @param {HTMLElement} container - DOM element to render chart into
 * @param {Array} data - Array of ingredient usage objects
 * @param {Object} options - Configuration options
 * @param {Function} options.onIngredientClick - Callback when ingredient is clicked
 */
export function createIngredientUsageChart(container, data, options = {}) {
    console.log('Creating ingredient usage chart with data:', data);

    // Clear container
    container.innerHTML = '';

    // Get dimensions
    const margin = { top: 20, right: 30, bottom: 40, left: 200 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = Math.max(400, data.length * 30) - margin.top - margin.bottom;

    // Sort data by hierarchical_usage descending
    const sortedData = [...data].sort((a, b) => b.hierarchical_usage - a.hierarchical_usage);

    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create scales
    const xScale = d3.scaleLinear()
        .domain([0, d3.max(sortedData, d => d.hierarchical_usage)])
        .range([0, width]);

    const yScale = d3.scaleBand()
        .domain(sortedData.map(d => d.ingredient_name))
        .range([0, height])
        .padding(0.1);

    // Create axes
    const xAxis = d3.axisBottom(xScale).ticks(5);
    const yAxis = d3.axisLeft(yScale);

    // Add X axis
    svg.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(xAxis)
        .append('text')
        .attr('x', width / 2)
        .attr('y', 35)
        .attr('fill', '#000')
        .attr('text-anchor', 'middle')
        .text('Number of Recipes');

    // Add Y axis
    svg.append('g')
        .call(yAxis);

    // Create tooltip
    const tooltip = d3.select(container)
        .append('div')
        .style('position', 'absolute')
        .style('visibility', 'hidden')
        .style('background-color', 'rgba(0, 0, 0, 0.8)')
        .style('color', 'white')
        .style('padding', '8px')
        .style('border-radius', '4px')
        .style('font-size', '12px')
        .style('pointer-events', 'none')
        .style('z-index', '1000');

    // Create bars
    svg.selectAll('.bar')
        .data(sortedData)
        .enter()
        .append('rect')
        .attr('class', 'bar')
        .attr('x', 0)
        .attr('y', d => yScale(d.ingredient_name))
        .attr('width', d => xScale(d.hierarchical_usage))
        .attr('height', yScale.bandwidth())
        .attr('fill', d => d.has_children ? '#1f77b4' : '#aec7e8')
        .style('cursor', d => d.has_children ? 'pointer' : 'default')
        .on('mouseover', function(event, d) {
            d3.select(this).attr('fill', d => d.has_children ? '#1565c0' : '#90b8d8');
            tooltip.style('visibility', 'visible')
                .html(`
                    <strong>${d.ingredient_name}</strong><br/>
                    Direct usage: ${d.direct_usage}<br/>
                    Total (with subtypes): ${d.hierarchical_usage}
                `);
        })
        .on('mousemove', function(event) {
            tooltip.style('top', (event.pageY - 10) + 'px')
                .style('left', (event.pageX + 10) + 'px');
        })
        .on('mouseout', function(event, d) {
            d3.select(this).attr('fill', d => d.has_children ? '#1f77b4' : '#aec7e8');
            tooltip.style('visibility', 'hidden');
        })
        .on('click', function(event, d) {
            if (d.has_children && options.onIngredientClick) {
                options.onIngredientClick(d);
            }
        });
}
```

**Step 3: Test chart renders**

Open `analytics.html` in browser and check:
- Ingredient Usage tab shows a bar chart (if data available)
- Bars are colored correctly (darker = has children)
- Tooltip shows on hover
- Clicking bars with children triggers callback (will see console log)

**Step 4: Commit**

```bash
git add src/web/js/charts/ingredientUsageChart.js
git commit -m "feat: implement ingredient usage chart with D3.js"
```

---

## Task 6: Create Recipe Complexity Chart Component

**Files:**
- Create: `src/web/js/charts/recipeComplexityChart.js`

**Step 1: Create chart component**

Create `src/web/js/charts/recipeComplexityChart.js`:

```javascript
/**
 * Create a recipe complexity distribution chart using D3.js
 *
 * @param {HTMLElement} container - DOM element to render chart into
 * @param {Array} data - Array of complexity distribution objects
 */
export function createRecipeComplexityChart(container, data) {
    console.log('Creating recipe complexity chart with data:', data);

    // Clear container
    container.innerHTML = '';

    // Get dimensions
    const margin = { top: 20, right: 30, bottom: 60, left: 60 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = 400 - margin.top - margin.bottom;

    // Sort data by ingredient_count ascending
    const sortedData = [...data].sort((a, b) => a.ingredient_count - b.ingredient_count);

    // Find mode (most common)
    const mode = sortedData.reduce((max, item) =>
        item.recipe_count > max.recipe_count ? item : max
    );

    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create scales
    const xScale = d3.scaleBand()
        .domain(sortedData.map(d => d.ingredient_count))
        .range([0, width])
        .padding(0.2);

    const yScale = d3.scaleLinear()
        .domain([0, d3.max(sortedData, d => d.recipe_count)])
        .range([height, 0]);

    // Create axes
    const xAxis = d3.axisBottom(xScale);
    const yAxis = d3.axisLeft(yScale).ticks(5);

    // Add X axis
    svg.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(xAxis)
        .append('text')
        .attr('x', width / 2)
        .attr('y', 40)
        .attr('fill', '#000')
        .attr('text-anchor', 'middle')
        .text('Number of Ingredients');

    // Add Y axis
    svg.append('g')
        .call(yAxis)
        .append('text')
        .attr('transform', 'rotate(-90)')
        .attr('x', -height / 2)
        .attr('y', -45)
        .attr('fill', '#000')
        .attr('text-anchor', 'middle')
        .text('Number of Recipes');

    // Create tooltip
    const tooltip = d3.select(container)
        .append('div')
        .style('position', 'absolute')
        .style('visibility', 'hidden')
        .style('background-color', 'rgba(0, 0, 0, 0.8)')
        .style('color', 'white')
        .style('padding', '8px')
        .style('border-radius', '4px')
        .style('font-size', '12px')
        .style('pointer-events', 'none')
        .style('z-index', '1000');

    // Create bars
    svg.selectAll('.bar')
        .data(sortedData)
        .enter()
        .append('rect')
        .attr('class', 'bar')
        .attr('x', d => xScale(d.ingredient_count))
        .attr('y', d => yScale(d.recipe_count))
        .attr('width', xScale.bandwidth())
        .attr('height', d => height - yScale(d.recipe_count))
        .attr('fill', d => d.ingredient_count === mode.ingredient_count ? '#ff7f0e' : '#1f77b4')
        .on('mouseover', function(event, d) {
            d3.select(this).attr('opacity', 0.7);
            tooltip.style('visibility', 'visible')
                .html(`
                    <strong>${d.ingredient_count} ingredients</strong><br/>
                    ${d.recipe_count} recipes
                `);
        })
        .on('mousemove', function(event) {
            tooltip.style('top', (event.pageY - 10) + 'px')
                .style('left', (event.pageX + 10) + 'px');
        })
        .on('mouseout', function() {
            d3.select(this).attr('opacity', 1);
            tooltip.style('visibility', 'hidden');
        });

    // Add value labels on bars
    svg.selectAll('.label')
        .data(sortedData)
        .enter()
        .append('text')
        .attr('class', 'label')
        .attr('x', d => xScale(d.ingredient_count) + xScale.bandwidth() / 2)
        .attr('y', d => yScale(d.recipe_count) - 5)
        .attr('text-anchor', 'middle')
        .attr('font-size', '12px')
        .attr('fill', '#666')
        .text(d => d.recipe_count);
}
```

**Step 2: Test chart renders**

Open `analytics.html` in browser and:
- Switch to "Recipe Complexity" tab
- Chart should render with vertical bars
- Mode (most common) should be highlighted in orange
- Tooltip shows on hover
- Value labels appear on bars

**Step 3: Commit**

```bash
git add src/web/js/charts/recipeComplexityChart.js
git commit -m "feat: implement recipe complexity chart with D3.js"
```

---

## Task 7: Create Analytics Page Controller

**Files:**
- Create: `src/web/js/analytics.js`

**Step 1: Create analytics.js with imports and state**

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

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initAnalytics);
```

**Step 2: Add ingredient usage data loading function**

Add to `analytics.js`:

```javascript
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
```

**Step 3: Add recipe complexity data loading function**

Add to `analytics.js`:

```javascript
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
```

**Step 4: Add helper functions**

Add to `analytics.js`:

```javascript
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
```

**Step 5: Test full analytics page**

Open `analytics.html` in browser and verify:
- Ingredient Usage tab loads and displays chart
- Click on ingredient with children drills down
- Breadcrumb navigation appears
- Click breadcrumb to navigate back
- Switch to Recipe Complexity tab
- Chart displays with stats
- Error states work (disconnect network and retry)
- Empty states work (if no data)

**Step 6: Commit**

```bash
git add src/web/js/analytics.js
git commit -m "feat: implement analytics page controller with tab navigation and drill-down"
```

---

## Task 8: Test Full Analytics Page Flow

**Files:**
- Test: `src/web/analytics.html` (manual testing)

**Step 1: Test ingredient usage tab**

Open `analytics.html` and verify:
- [ ] Page loads without errors
- [ ] Ingredient Usage tab is active by default
- [ ] Chart renders with data
- [ ] Bars are colored correctly (darker for parents)
- [ ] Tooltip shows on hover with direct and hierarchical counts
- [ ] Clicking parent ingredient shows children
- [ ] Breadcrumb appears and shows hierarchy
- [ ] Clicking breadcrumb navigates back
- [ ] "X ingredients displayed" count updates
- [ ] "Last updated" timestamp shows

**Step 2: Test recipe complexity tab**

- [ ] Click "Recipe Complexity" tab
- [ ] Chart renders with vertical bars
- [ ] Mode (most common) is highlighted in orange
- [ ] Value labels appear on bars
- [ ] Tooltip shows on hover
- [ ] Average and mode stats display correctly
- [ ] "Last updated" timestamp shows

**Step 3: Test error handling**

- [ ] Disconnect network
- [ ] Refresh page
- [ ] Error state displays with message
- [ ] Click "Retry" button
- [ ] Reconnect network
- [ ] Retry loads data successfully

**Step 4: Test responsive design**

- [ ] Resize browser window to mobile size
- [ ] Navigation tabs remain accessible
- [ ] Charts adjust to container width
- [ ] Stats layout stacks vertically on mobile

**Step 5: Test browser compatibility**

Test in multiple browsers:
- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)

**Step 6: Document any issues found**

If issues found, create todos for fixes. Otherwise, proceed to commit.

**Step 7: Final commit**

```bash
git add -A
git commit -m "test: verify analytics page functionality across browsers"
```

---

## Task 9: Deploy and Test on Dev Environment

**Files:**
- Deploy: All analytics frontend files

**Step 1: Build and deploy to dev**

```bash
# Run deployment script
scripts/deploy.bat dev
```

Expected: Deployment succeeds, CloudFront cache invalidated

**Step 2: Test deployed analytics page**

Open deployed dev URL and append `/analytics.html`:
- [ ] Page loads from CloudFront
- [ ] API calls work (CORS configured)
- [ ] D3.js loads from CDN
- [ ] Charts render correctly
- [ ] All interactive features work
- [ ] Analytics link in navigation works

**Step 3: Test analytics API endpoints**

Open browser console on deployed page:
```javascript
// Test ingredient usage
fetch('https://your-api.execute-api.region.amazonaws.com/api/v1/analytics/ingredient-usage')
  .then(r => r.json())
  .then(console.log);

// Test recipe complexity
fetch('https://your-api.execute-api.region.amazonaws.com/api/v1/analytics/recipe-complexity')
  .then(r => r.json())
  .then(console.log);
```

Expected: Both return data with correct structure

**Step 4: Test drill-down on deployed environment**

- [ ] Click ingredient with children
- [ ] Verify API call includes `parent_id` parameter
- [ ] Verify children load correctly
- [ ] Test breadcrumb navigation

**Step 5: Document deployment success**

Create deployment notes:
```bash
echo "Analytics frontend deployed to dev on $(date)" >> docs/deployment-log.txt
```

**Step 6: Commit deployment notes**

```bash
git add docs/deployment-log.txt
git commit -m "docs: record analytics frontend deployment to dev"
```

---

## Completion Checklist

**Functionality:**
- [x] Analytics API methods added to client
- [x] Navigation includes analytics link
- [x] Analytics page HTML created
- [x] CSS styles added
- [x] Ingredient usage chart implemented
- [x] Recipe complexity chart implemented
- [x] Tab navigation works
- [x] Drill-down navigation works
- [x] Breadcrumb navigation works
- [x] Error handling implemented
- [x] Empty state handling implemented
- [x] Loading states work

**Testing:**
- [ ] Manual testing passed
- [ ] Browser compatibility verified
- [ ] Responsive design tested
- [ ] Deployed to dev environment
- [ ] API integration verified

**Documentation:**
- [x] Implementation plan followed
- [ ] Deployment logged
- [x] Code commented appropriately

---

## Known Limitations

1. **Breadcrumb state not persisted**: Drill-down state lost on page refresh
2. **No URL state management**: Cannot deep link to specific hierarchy level
3. **Cache behavior**: Drill-down queries always on-the-fly (only root cached)
4. **No window resize handler**: Charts don't redraw on window resize (page refresh required)

These are acceptable limitations for MVP. Future enhancements can address these.

---

## Next Steps

After implementation is complete:
1. Monitor analytics usage in production logs
2. Gather user feedback on chart designs
3. Consider adding more analytics views (tags, ratings, etc.)
4. Implement URL state management for deep linking
5. Add window resize handlers for responsive charts
6. Cache drill-down results in S3
