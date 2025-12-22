# Cocktail Space Visualization Implementation Plan

> **For Claude:** Use `${CLAUDE_PLUGIN_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Add interactive UMAP visualization showing recipes positioned by ingredient similarity, with clickable points that open recipe details in a modal.

**Architecture:** Pre-compute UMAP embeddings using Manhattan distance on normalized ingredient proportions. Store coordinates in S3 via existing analytics infrastructure. Frontend renders D3.js scatter plot with hover tooltips and click-to-modal interactions. Modal fetches full recipe data and displays using existing recipeCard component.

**Tech Stack:** Python (UMAP, scikit-learn, pandas, numpy), FastAPI, AWS Lambda, S3, D3.js v7, Vanilla JavaScript ES6 modules

---

## Task 1: Add UMAP Dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Add UMAP dependency**

Add to `requirements.txt`:
```
umap-learn==0.5.5
```

**Step 2: Verify scikit-learn is present**

Check that `requirements.txt` contains `scikit-learn`. If not, add:
```
scikit-learn>=1.3.0
```

**Step 3: Verify numpy and pandas are present**

Check that `requirements.txt` contains `numpy` and `pandas`. These are likely already present from other analytics code.

**Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add umap-learn dependency for cocktail space visualization"
```

---

## Task 2: Implement Recipe Matrix Building

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add recipe ingredient matrix method**

Add this method to the `AnalyticsQueries` class in `api/db/db_analytics.py` after the existing methods:

```python
def get_recipe_ingredient_matrix(self) -> tuple[Dict[int, str], Any, Any]:
    """Build normalized recipe-ingredient matrix for distance calculations

    Returns:
        Tuple of (recipe_id_map, normalized_matrix, recipe_names)
        - recipe_id_map: Dict mapping matrix row index to recipe ID
        - normalized_matrix: pandas DataFrame with normalized ingredient proportions
        - recipe_names: List of recipe names corresponding to matrix rows
    """
    import pandas as pd
    import numpy as np

    try:
        # Load all recipes with ingredients and amounts
        sql = """
        SELECT
            r.id as recipe_id,
            r.name as recipe_name,
            i.id as ingredient_id,
            i.name as ingredient_name,
            ri.amount,
            ri.unit_id,
            u.conversion_to_ml
        FROM recipes r
        JOIN recipe_ingredients ri ON r.id = ri.recipe_id
        JOIN ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN units u ON ri.unit_id = u.id
        ORDER BY r.id, i.id
        """

        rows = self.db.execute_query(sql)
        if not rows:
            logger.warning("No recipe data found for matrix building")
            return {}, pd.DataFrame(), []

        df = pd.DataFrame(rows)

        # Convert amounts to ml where possible
        df['amount_ml'] = df.apply(
            lambda row: row['amount'] * row['conversion_to_ml']
            if pd.notna(row['conversion_to_ml']) and pd.notna(row['amount'])
            else row['amount']
            if pd.notna(row['amount'])
            else 1.0,  # Default to 1 if no amount
            axis=1
        )

        # Create pivot table for amounts
        amount_matrix = df.pivot_table(
            index='recipe_name',
            columns='ingredient_name',
            values='amount_ml',
            aggfunc='sum',
            fill_value=0
        )

        # Normalize each recipe to sum to 1 (proportions)
        normalized_matrix = amount_matrix.div(amount_matrix.sum(axis=1), axis=0)
        normalized_matrix = normalized_matrix.fillna(0)

        # Remove recipes/ingredients that are all zeros
        normalized_matrix = normalized_matrix.loc[(normalized_matrix != 0).any(axis=1), :]
        normalized_matrix = normalized_matrix.loc[:, (normalized_matrix != 0).any(axis=0)]

        # Create mapping from matrix row index to recipe ID
        recipe_id_map = {}
        recipe_names = []
        for idx, recipe_name in enumerate(normalized_matrix.index):
            # Find the recipe ID for this name
            recipe_row = df[df['recipe_name'] == recipe_name].iloc[0]
            recipe_id_map[idx] = int(recipe_row['recipe_id'])
            recipe_names.append(recipe_name)

        logger.info(f"Built recipe matrix: {normalized_matrix.shape[0]} recipes x {normalized_matrix.shape[1]} ingredients")
        return recipe_id_map, normalized_matrix, recipe_names

    except Exception as e:
        logger.error(f"Error building recipe ingredient matrix: {str(e)}")
        raise
```

**Step 2: Add required imports at top of file**

At the top of `api/db/db_analytics.py`, ensure these imports are present (add if missing):

```python
from typing import Dict, List, Any, Optional, cast
import logging
```

**Step 3: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat: add recipe ingredient matrix building for UMAP"
```

---

## Task 3: Implement UMAP Computation

**Files:**
- Modify: `api/db/db_analytics.py`

**Step 1: Add UMAP computation method**

Add this method to the `AnalyticsQueries` class in `api/db/db_analytics.py` after `get_recipe_ingredient_matrix()`:

```python
def compute_cocktail_space_umap(self) -> List[Dict[str, Any]]:
    """Compute UMAP embedding of recipe space based on ingredient similarity

    Uses Manhattan distance on normalized ingredient proportions, then UMAP
    for 2D visualization.

    Returns:
        List of dicts with {recipe_id, recipe_name, x, y}
    """
    import numpy as np
    from sklearn.metrics import pairwise_distances
    import umap

    try:
        # Get normalized recipe-ingredient matrix
        recipe_id_map, normalized_matrix, recipe_names = self.get_recipe_ingredient_matrix()

        if normalized_matrix.empty:
            logger.warning("Empty recipe matrix, returning empty UMAP")
            return []

        # Compute pairwise Manhattan distances
        logger.info("Computing pairwise Manhattan distances")
        distance_matrix = pairwise_distances(normalized_matrix, metric='manhattan')

        # Run UMAP dimensionality reduction
        logger.info("Running UMAP dimensionality reduction")
        reducer = umap.UMAP(
            n_neighbors=5,
            min_dist=0.05,
            n_components=2,
            metric='precomputed',
            random_state=42
        )

        embedding = reducer.fit_transform(distance_matrix)

        # Build result list
        result = []
        for idx in range(len(embedding)):
            result.append({
                'recipe_id': recipe_id_map[idx],
                'recipe_name': recipe_names[idx],
                'x': float(embedding[idx, 0]),
                'y': float(embedding[idx, 1])
            })

        logger.info(f"UMAP computation complete: {len(result)} recipes")
        return result

    except Exception as e:
        logger.error(f"Error computing cocktail space UMAP: {str(e)}")
        raise
```

**Step 2: Commit**

```bash
git add api/db/db_analytics.py
git commit -m "feat: add UMAP computation for cocktail space"
```

---

## Task 4: Add Cocktail Space API Endpoint

**Files:**
- Modify: `api/routes/analytics.py`

**Step 1: Add cocktail space endpoint**

Add this endpoint to `api/routes/analytics.py` after the existing `/recipe-complexity` endpoint:

```python
@router.get("/cocktail-space")
async def get_cocktail_space_analytics(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get UMAP embedding of recipe space based on ingredient similarity"""
    try:
        storage_key = "cocktail-space"

        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        stored_data = storage_manager.get_analytics(storage_key)
        if not stored_data:
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail="cocktail-space data not found in storage"
            )

        return stored_data
    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error getting cocktail space analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve cocktail space analytics", detail=str(e))
```

**Step 2: Commit**

```bash
git add api/routes/analytics.py
git commit -m "feat: add cocktail space analytics endpoint"
```

---

## Task 5: Update Analytics Endpoints to Require Cached Data

**Files:**
- Modify: `api/routes/analytics.py`

**Step 1: Update ingredient-usage endpoint**

Replace the `/ingredient-usage` endpoint in `api/routes/analytics.py` with:

```python
@router.get("/ingredient-usage")
async def get_ingredient_usage_analytics(
    level: Optional[int] = None,
    parent_id: Optional[int] = None,
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get ingredient usage statistics with hierarchical aggregation"""
    try:
        storage_key = f"ingredient-usage-{level}-{parent_id}"

        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        stored_data = storage_manager.get_analytics(storage_key)
        if not stored_data:
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail=f"{storage_key} data not found in storage"
            )

        return stored_data

    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error getting ingredient usage analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve ingredient usage analytics", detail=str(e))
```

**Step 2: Update recipe-complexity endpoint**

Replace the `/recipe-complexity` endpoint in `api/routes/analytics.py` with:

```python
@router.get("/recipe-complexity")
async def get_recipe_complexity_analytics(
    db: Database = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional),
):
    """Get recipe complexity distribution"""
    try:
        storage_key = "recipe-complexity"

        if not storage_manager:
            raise DatabaseException("Analytics storage not configured")

        stored_data = storage_manager.get_analytics(storage_key)
        if not stored_data:
            raise DatabaseException(
                "Analytics not generated. Please trigger analytics refresh.",
                detail=f"{storage_key} data not found in storage"
            )

        return stored_data

    except DatabaseException:
        raise
    except Exception as e:
        logger.error(f"Error getting recipe complexity analytics: {str(e)}")
        raise DatabaseException("Failed to retrieve recipe complexity analytics", detail=str(e))
```

**Step 3: Commit**

```bash
git add api/routes/analytics.py
git commit -m "refactor: require cached data for all analytics endpoints"
```

---

## Task 6: Update Analytics Refresh Lambda

**Files:**
- Modify: `api/analytics_refresh.py`

**Step 1: Add cocktail space generation to Lambda handler**

In `api/analytics_refresh.py`, add this code after the complexity stats generation (around line 48):

```python
        # Generate cocktail space UMAP
        logger.info("Generating cocktail space UMAP embedding")
        cocktail_space = analytics_queries.compute_cocktail_space_umap()
```

**Step 2: Add cocktail space storage**

Add this code after storing the complexity stats (around line 53):

```python
        storage.put_analytics('cocktail-space', cocktail_space)
```

**Step 3: Update success response**

Update the success response body to include cocktail space count (around line 60):

```python
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Analytics regenerated successfully",
                "ingredient_stats_count": len(ingredient_stats),
                "complexity_stats_count": len(complexity_stats),
                "cocktail_space_count": len(cocktail_space)
            })
        }
```

**Step 4: Commit**

```bash
git add api/analytics_refresh.py
git commit -m "feat: add cocktail space UMAP to analytics refresh"
```

---

## Task 7: Add API Gateway Event for Cocktail Space

**Files:**
- Modify: `template.yaml`

**Step 1: Add API Gateway event**

In `template.yaml`, find the `Events:` section under `CocktailLambda` function (around line 860). Add this event after the `GetRecipeComplexityAnalytics` event:

```yaml
          GetCocktailSpaceAnalytics:
            Type: Api
            Properties:
              RestApiId: !Ref CocktailAPI
              Path: /analytics/cocktail-space
              Method: get
```

**Step 2: Commit**

```bash
git add template.yaml
git commit -m "feat: add API Gateway event for cocktail space endpoint"
```

---

## Task 8: Add Frontend API Method

**Files:**
- Modify: `src/web/js/api.js`

**Step 1: Add getCocktailSpaceAnalytics method**

In `src/web/js/api.js`, add this method after the `getRecipeComplexityAnalytics()` method (around line 450):

```javascript
    async getCocktailSpaceAnalytics() {
        const url = `/analytics/cocktail-space`;
        return this._request(url, 'GET', null, false);
    }
```

**Step 2: Commit**

```bash
git add src/web/js/api.js
git commit -m "feat: add cocktail space analytics API method"
```

---

## Task 9: Create D3.js Cocktail Space Chart Component

**Files:**
- Create: `src/web/js/charts/cocktailSpaceChart.js`

**Step 1: Create chart component file**

Create `src/web/js/charts/cocktailSpaceChart.js` with this complete implementation:

```javascript
/**
 * Creates an interactive D3.js scatter plot for cocktail space UMAP visualization
 * @param {HTMLElement} container - Container element for the chart
 * @param {Array} data - Array of {recipe_id, recipe_name, x, y} objects
 * @param {Object} options - Configuration options
 * @param {Function} options.onRecipeClick - Callback when recipe point is clicked: (recipeId, recipeName) => {}
 */
export function createCocktailSpaceChart(container, data, options = {}) {
    // Clear container
    container.innerHTML = '';

    // Set up dimensions
    const margin = { top: 60, right: 40, bottom: 60, left: 60 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = 600 - margin.top - margin.bottom;

    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom);

    const g = svg.append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Get data extents with padding
    const xExtent = d3.extent(data, d => d.x);
    const yExtent = d3.extent(data, d => d.y);
    const xPadding = (xExtent[1] - xExtent[0]) * 0.1;
    const yPadding = (yExtent[1] - yExtent[0]) * 0.1;

    // Create scales
    const xScale = d3.scaleLinear()
        .domain([xExtent[0] - xPadding, xExtent[1] + xPadding])
        .range([0, width]);

    const yScale = d3.scaleLinear()
        .domain([yExtent[0] - yPadding, yExtent[1] + yPadding])
        .range([height, 0]);

    // Add grid lines
    g.append('g')
        .attr('class', 'grid')
        .attr('opacity', 0.1)
        .call(d3.axisLeft(yScale)
            .tickSize(-width)
            .tickFormat(''));

    g.append('g')
        .attr('class', 'grid')
        .attr('opacity', 0.1)
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(xScale)
            .tickSize(-height)
            .tickFormat(''));

    // Add X axis
    g.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(xScale))
        .append('text')
        .attr('x', width / 2)
        .attr('y', 45)
        .attr('fill', 'black')
        .attr('font-size', '14px')
        .attr('font-weight', 'bold')
        .text('UMAP Dimension 1');

    // Add Y axis
    g.append('g')
        .call(d3.axisLeft(yScale))
        .append('text')
        .attr('transform', 'rotate(-90)')
        .attr('x', -height / 2)
        .attr('y', -45)
        .attr('fill', 'black')
        .attr('font-size', '14px')
        .attr('font-weight', 'bold')
        .attr('text-anchor', 'middle')
        .text('UMAP Dimension 2');

    // Create tooltip
    const tooltip = d3.select('body')
        .append('div')
        .style('position', 'absolute')
        .style('background', 'rgba(0, 0, 0, 0.8)')
        .style('color', 'white')
        .style('padding', '8px 12px')
        .style('border-radius', '4px')
        .style('font-size', '12px')
        .style('pointer-events', 'none')
        .style('opacity', 0)
        .style('z-index', 1000);

    // Create clip path for zoom
    svg.append('defs')
        .append('clipPath')
        .attr('id', 'clip')
        .append('rect')
        .attr('width', width)
        .attr('height', height);

    // Add circles for data points
    const circles = g.append('g')
        .attr('clip-path', 'url(#clip)')
        .selectAll('circle')
        .data(data)
        .enter()
        .append('circle')
        .attr('cx', d => xScale(d.x))
        .attr('cy', d => yScale(d.y))
        .attr('r', 6)
        .attr('fill', 'steelblue')
        .attr('stroke', 'white')
        .attr('stroke-width', 1)
        .attr('opacity', 0.7)
        .style('cursor', 'pointer')
        .on('mouseover', function(event, d) {
            d3.select(this)
                .transition()
                .duration(200)
                .attr('r', 8)
                .attr('opacity', 1);

            tooltip
                .style('opacity', 1)
                .html(`<strong>${d.recipe_name}</strong>`)
                .style('left', (event.pageX + 10) + 'px')
                .style('top', (event.pageY - 10) + 'px');
        })
        .on('mousemove', function(event) {
            tooltip
                .style('left', (event.pageX + 10) + 'px')
                .style('top', (event.pageY - 10) + 'px');
        })
        .on('mouseout', function() {
            d3.select(this)
                .transition()
                .duration(200)
                .attr('r', 6)
                .attr('opacity', 0.7);

            tooltip.style('opacity', 0);
        })
        .on('click', function(event, d) {
            if (options.onRecipeClick) {
                options.onRecipeClick(d.recipe_id, d.recipe_name);
            }
        });

    // Add zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.5, 10])
        .on('zoom', (event) => {
            const transform = event.transform;

            circles
                .attr('cx', d => transform.applyX(xScale(d.x)))
                .attr('cy', d => transform.applyY(yScale(d.y)));

            g.select('.x-axis')
                .call(d3.axisBottom(xScale).scale(transform.rescaleX(xScale)));

            g.select('.y-axis')
                .call(d3.axisLeft(yScale).scale(transform.rescaleY(yScale)));
        });

    svg.call(zoom);

    // Add title
    svg.append('text')
        .attr('x', (width + margin.left + margin.right) / 2)
        .attr('y', margin.top / 2)
        .attr('text-anchor', 'middle')
        .attr('font-size', '18px')
        .attr('font-weight', 'bold')
        .text('Cocktail Space - Recipe Similarity Map');
}
```

**Step 2: Commit**

```bash
git add src/web/js/charts/cocktailSpaceChart.js
git commit -m "feat: add D3.js cocktail space chart component"
```

---

## Task 10: Add Cocktail Space Tab to Analytics Page

**Files:**
- Modify: `src/web/analytics.html`

**Step 1: Add cocktail space tab button**

In `src/web/analytics.html`, find the tab navigation (around line 20). Add this tab button after the "Recipe Complexity" button:

```html
            <button class="tab-button" data-tab="cocktail-space">
                Cocktail Space
            </button>
```

**Step 2: Add cocktail space tab content**

In `src/web/analytics.html`, find the tab content sections (around line 80). Add this tab content after the recipe complexity tab:

```html
        <!-- Cocktail Space Tab -->
        <div id="tab-cocktail-space" class="tab-content">
            <div class="analytics-card">
                <h2>Cocktail Space Visualization</h2>
                <p class="card-description">
                    Interactive map showing recipes positioned by ingredient similarity.
                    Hover over points to see recipe names. Click to view details.
                </p>

                <!-- Loading state -->
                <div id="cocktail-space-loading" class="loading-state">
                    <div class="spinner"></div>
                    <p>Loading cocktail space...</p>
                </div>

                <!-- Error state -->
                <div id="cocktail-space-error" class="error-state hidden">
                    <p class="error-message"></p>
                    <button class="retry-btn">Retry</button>
                </div>

                <!-- Chart container -->
                <div id="cocktail-space-chart" class="chart-container"></div>

                <div class="analytics-stats">
                    <div class="stat-item">
                        <span class="stat-label">Recipes:</span>
                        <span id="cocktail-space-count" class="stat-value">-</span>
                    </div>
                </div>
            </div>
        </div>
```

**Step 3: Add recipe modal HTML**

Add this modal HTML at the end of the `<main>` section (before `</main>`):

```html
        <!-- Recipe Detail Modal -->
        <div id="recipe-modal" class="modal hidden">
            <div class="modal-backdrop"></div>
            <div class="modal-content">
                <button class="modal-close">&times;</button>
                <div id="recipe-modal-body">
                    <!-- Loading state -->
                    <div id="recipe-modal-loading" class="modal-loading">
                        <div class="spinner"></div>
                        <p>Loading recipe...</p>
                    </div>
                    <!-- Recipe card will be inserted here -->
                    <div id="recipe-modal-card"></div>
                </div>
                <div class="modal-footer">
                    <a id="recipe-modal-link" href="#" target="_blank" class="btn-primary">View Full Recipe</a>
                </div>
            </div>
        </div>
```

**Step 4: Commit**

```bash
git add src/web/analytics.html
git commit -m "feat: add cocktail space tab and recipe modal to analytics page"
```

---

## Task 11: Add Cocktail Space Controller Logic

**Files:**
- Modify: `src/web/js/analytics.js`

**Step 1: Import cocktail space chart at top of file**

At the top of `src/web/js/analytics.js`, add this import after the existing chart imports:

```javascript
import { createCocktailSpaceChart } from './charts/cocktailSpaceChart.js';
```

**Step 2: Import recipeCard module**

Add this import after the chart imports:

```javascript
import { createRecipeCard } from './recipeCard.js';
```

**Step 3: Add cocktail-space case to loadTabData**

In the `loadTabData()` function, add this case to the switch statement:

```javascript
        case 'cocktail-space':
            await loadCocktailSpaceData();
            break;
```

**Step 4: Add loadCocktailSpaceData function**

Add this function after the `loadRecipeComplexityData()` function (around line 258):

```javascript
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
```

**Step 5: Add recipe modal handler functions**

Add these functions at the end of the file (before the DOMContentLoaded listener):

```javascript
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
}

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
```

**Step 6: Commit**

```bash
git add src/web/js/analytics.js
git commit -m "feat: add cocktail space controller and modal logic"
```

---

## Task 12: Add Modal and Chart Styles

**Files:**
- Modify: `src/web/styles.css`

**Step 1: Add recipe modal styles**

Add these styles at the end of `src/web/styles.css`:

```css
/* Recipe Modal */
.modal {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
}

.modal.hidden {
    display: none;
}

.modal-backdrop {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.7);
}

.modal-content {
    position: relative;
    background: white;
    max-width: 600px;
    max-height: 90vh;
    overflow-y: auto;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    z-index: 2001;
}

.modal-close {
    position: absolute;
    top: 12px;
    right: 12px;
    background: none;
    border: none;
    font-size: 28px;
    line-height: 1;
    cursor: pointer;
    color: #666;
    z-index: 2002;
    padding: 0;
    width: 32px;
    height: 32px;
}

.modal-close:hover {
    color: #333;
}

#recipe-modal-body {
    padding: 20px;
    min-height: 200px;
}

.modal-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
}

.modal-loading .spinner {
    margin-bottom: 12px;
}

.modal-footer {
    padding: 16px 20px;
    border-top: 1px solid #e0e0e0;
    text-align: center;
}

.modal-footer .btn-primary {
    display: inline-block;
    padding: 10px 20px;
    background: #007bff;
    color: white;
    text-decoration: none;
    border-radius: 4px;
    font-weight: 500;
}

.modal-footer .btn-primary:hover {
    background: #0056b3;
}

/* Cocktail Space Chart */
#cocktail-space-chart {
    min-height: 650px;
}

#cocktail-space-chart svg {
    font-family: Arial, sans-serif;
}

#cocktail-space-chart .grid line {
    stroke: #ccc;
}

#cocktail-space-chart .grid path {
    stroke-width: 0;
}
```

**Step 2: Commit**

```bash
git add src/web/styles.css
git commit -m "feat: add modal and cocktail space chart styles"
```

---

## Task 13: Deploy and Test Backend

**Files:**
- None (deployment task)

**Step 1: Build SAM application**

```bash
sam build --template-file template.yaml
```

Expected: Build succeeds, shows "Build Succeeded"

**Step 2: Deploy to dev environment**

```bash
sam deploy --config-env dev --no-confirm-changeset
```

Expected: Deployment succeeds, shows stack outputs with API Gateway URL

**Step 3: Verify deployment**

Check CloudFormation console to confirm stack update completed successfully.

**Step 4: Note - do not commit yet**

Wait to commit until after analytics refresh is tested.

---

## Task 14: Trigger Analytics Refresh

**Files:**
- None (operational task)

**Step 1: Run analytics refresh script**

```bash
./scripts/trigger-analytics-refresh.sh dev
```

Expected: Lambda invokes successfully, returns 200 with success message including cocktail_space_count

**Step 2: Verify S3 storage**

Check S3 bucket for `analytics/v1/cocktail-space.json` file.

Expected: File exists with array of recipe coordinate data

**Step 3: Test API endpoint**

```bash
curl https://<api-gateway-url>/api/v1/analytics/cocktail-space
```

Expected: Returns JSON with data array containing recipe coordinates

**Step 4: Note - no commit for this task**

This is an operational verification task.

---

## Task 15: Deploy and Test Frontend

**Files:**
- None (deployment task)

**Step 1: Generate frontend config**

```bash
python scripts/generate_config.py dev
```

Expected: Creates `src/web/js/config.js` with correct API URL

**Step 2: Upload frontend files to S3**

```bash
aws s3 sync src/web/ s3://<website-bucket>/ --exclude "*.md"
```

Expected: Files uploaded successfully

**Step 3: Invalidate CloudFront cache**

```bash
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"
```

Expected: Invalidation created

**Step 4: Test in browser**

1. Navigate to analytics page
2. Click "Cocktail Space" tab
3. Verify scatter plot renders
4. Hover over points - verify tooltip shows recipe names
5. Click a point - verify modal opens with recipe card
6. Click "View Full Recipe" - verify opens in new tab
7. Close modal with X button
8. Close modal by clicking backdrop
9. Test zoom/pan on chart

Expected: All interactions work correctly

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: complete cocktail space visualization deployment"
```

---

## Post-Implementation Notes

### Testing Checklist
- [ ] Backend: UMAP computation completes within Lambda timeout
- [ ] Backend: Analytics refresh Lambda includes cocktail space data
- [ ] Backend: API endpoint returns cached data successfully
- [ ] Backend: API endpoint returns error if data not cached
- [ ] Frontend: Tab navigation works
- [ ] Frontend: Chart renders with correct data
- [ ] Frontend: Hover shows recipe names
- [ ] Frontend: Click opens modal
- [ ] Frontend: Modal displays recipe card
- [ ] Frontend: Modal link opens recipe page
- [ ] Frontend: Modal closes on X, backdrop, and Escape key
- [ ] Frontend: Zoom/pan works on chart

### Known Limitations
- UMAP computation requires at least ~10 recipes for meaningful visualization
- Chart may appear cluttered with >200 recipes (zoom helps)
- Recipe names with special characters must be properly encoded in URLs
- Analytics must be manually refreshed after recipe changes (via mutation triggers)

### Future Enhancements
- Add color coding by recipe type/category
- Add search/filter to highlight specific recipes
- Add comparison mode to show distance between selected recipes
- Add alternative distance metrics (Jaccard, NMF-based)
