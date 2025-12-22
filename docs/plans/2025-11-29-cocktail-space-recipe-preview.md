# Cocktail Space Recipe Preview Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add lightweight recipe preview card on hover in Cocktail Space visualization showing recipe name and ingredients.

**Architecture:** Extend cocktail-space analytics to include sorted ingredient lists, create new RecipePreviewCard component with debounced hover behavior, integrate into existing chart with smart positioning.

**Tech Stack:** Python (backend analytics), JavaScript (vanilla), D3.js (existing chart), CSS

---

## Task 1: Backend - Add Ingredient Query Helper

**Files:**
- Modify: `api/db/db_analytics.py`
- Reference design: `docs/plans/2025-11-29-cocktail-space-recipe-preview-design.md`

**Step 1: Add ingredient sorting helper function**

Add this function to `db_analytics.py` after the existing cocktail space query:

```python
def _convert_amount_to_ml(amount: float, unit_name: str) -> float:
    """Convert ingredient amount to mL for consistent sorting.

    Special handling:
    - "to top" -> 90 mL (3 oz equivalent)
    - "to rinse" -> 5 mL
    - "each" -> -1 (sort to end)
    - Standard conversions: oz, tbsp, tsp, dash to mL
    """
    if unit_name == "to top":
        return 90.0
    elif unit_name == "to rinse":
        return 5.0
    elif unit_name == "each" or unit_name == "Each":
        return -1.0

    # Handle None/null amounts
    if amount is None or amount == 0:
        if unit_name in ["to top", "to rinse"]:
            return _convert_amount_to_ml(0, unit_name)
        return 0.0

    # Unit conversions to mL
    conversions = {
        "oz": 29.5735,
        "ml": 1.0,
        "mL": 1.0,
        "tbsp": 14.7868,
        "tsp": 4.92892,
        "dash": 0.616115,
        "drop": 0.05,
        "bar spoon": 5.0,
        "barspoon": 5.0,
    }

    multiplier = conversions.get(unit_name, 1.0)
    return amount * multiplier
```

**Step 2: Update cocktail space query to include ingredients**

In `db_analytics.py`, find the `get_cocktail_space_analytics()` method. Replace the existing query with:

```python
def get_cocktail_space_analytics(self) -> dict:
    """Get UMAP embedding of recipe space with ingredient lists.

    Returns recipes with x/y coordinates and sorted ingredient names.
    Ingredients sorted by volume (DESC), with special handling for
    "to top", "to rinse", and "each" units.
    """
    query = """
        SELECT
            cs.recipe_id,
            r.name as recipe_name,
            cs.x,
            cs.y,
            ri.amount,
            u.name as unit_name,
            i.name as ingredient_name
        FROM cocktail_space cs
        JOIN recipes r ON cs.recipe_id = r.id
        LEFT JOIN recipe_ingredients ri ON r.id = ri.recipe_id
        LEFT JOIN ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN units u ON ri.unit_id = u.id
        ORDER BY cs.recipe_id, ri.amount DESC NULLS LAST
    """

    rows = self.db.execute_query(query)

    # Group by recipe and build ingredient lists
    recipes_dict = {}
    for row in rows:
        recipe_id = row['recipe_id']
        if recipe_id not in recipes_dict:
            recipes_dict[recipe_id] = {
                'recipe_id': recipe_id,
                'recipe_name': row['recipe_name'],
                'x': row['x'],
                'y': row['y'],
                'ingredients_with_amounts': []
            }

        # Add ingredient with amount for sorting
        if row['ingredient_name']:
            amount_ml = self._convert_amount_to_ml(
                row['amount'],
                row['unit_name'] or ''
            )
            recipes_dict[recipe_id]['ingredients_with_amounts'].append({
                'name': row['ingredient_name'],
                'amount_ml': amount_ml
            })

    # Sort ingredients and extract names only
    result = []
    for recipe in recipes_dict.values():
        # Sort by amount (DESC), with "each" units (-1) at end
        sorted_ingredients = sorted(
            recipe['ingredients_with_amounts'],
            key=lambda x: x['amount_ml'],
            reverse=True
        )

        result.append({
            'recipe_id': recipe['recipe_id'],
            'recipe_name': recipe['recipe_name'],
            'x': recipe['x'],
            'y': recipe['y'],
            'ingredients': [ing['name'] for ing in sorted_ingredients]
        })

    return {'data': result}
```

**Step 3: Test the query manually**

Run Python to test the query:

```bash
cd api
python3 << 'EOF'
from db.database import get_database
from db.db_analytics import AnalyticsQueries

db = get_database()
analytics = AnalyticsQueries(db)
result = analytics.get_cocktail_space_analytics()

# Check first recipe
first = result['data'][0]
print(f"Recipe: {first['recipe_name']}")
print(f"Ingredients: {', '.join(first['ingredients'][:6])}")
print(f"Total recipes: {len(result['data'])}")
EOF
```

Expected output: Recipe name, ingredients list, total count

**Step 4: Commit backend changes**

```bash
git add api/db/db_analytics.py
git commit -m "feat: add ingredient lists to cocktail space analytics

- Add _convert_amount_to_ml() helper for consistent sorting
- Handle special cases: to top (90mL), to rinse (5mL), each (-1)
- Update get_cocktail_space_analytics() to include sorted ingredients
- Return ingredient names as array per recipe"
```

---

## Task 2: Backend - Update Analytics Refresh Lambda

**Files:**
- Modify: `api/analytics/analytics_refresh.py`

**Step 1: Verify analytics refresh uses updated query**

Check that `analytics_refresh.py` calls `get_cocktail_space_analytics()`. The existing code should automatically pick up the new ingredient data.

Find this section in `analytics_refresh.py`:

```python
# Cocktail Space Analytics
cocktail_space_data = analytics.get_cocktail_space_analytics()
storage.save_analytics("cocktail-space", cocktail_space_data)
```

This should already work with the updated query. No changes needed here.

**Step 2: Test analytics generation locally**

Trigger analytics refresh to verify:

```bash
./scripts/trigger-analytics-refresh.sh dev
```

Wait 30-60 seconds, then check the output:

```bash
curl -s "https://6kukiw1dxg.execute-api.us-east-1.amazonaws.com/api/analytics/cocktail-space" | python3 -m json.tool | head -50
```

Expected: Should see `"ingredients": ["Gin", "Vermouth", ...]` in the output

**Step 3: Commit (no code changes, just verification)**

No commit needed - analytics refresh already uses the updated query.

---

## Task 3: Frontend - Create Recipe Preview Card Component

**Files:**
- Create: `src/web/js/components/recipePreviewCard.js`

**Step 1: Create component file with constants and structure**

Create the new file:

```javascript
/**
 * Recipe Preview Card Component
 *
 * Displays a lightweight preview of a recipe on hover, showing recipe name
 * and ingredient list. Designed for use in the Cocktail Space visualization.
 */

// Configuration constants
const MAX_PREVIEW_INGREDIENTS = 6;
const HOVER_DELAY_MS = 250;
const PREVIEW_OFFSET_X = 15;
const PREVIEW_OFFSET_Y = 15;

/**
 * Creates and manages a recipe preview card
 * @param {HTMLElement} container - Container element for the preview
 * @returns {Object} Preview card controller
 */
export function createRecipePreviewCard(container) {
    let previewElement = null;
    let hoverTimer = null;
    let currentRecipe = null;

    /**
     * Build the preview card HTML
     * @param {Object} recipe - Recipe data with name and ingredients array
     * @returns {string} HTML string for preview card
     */
    function buildPreviewHTML(recipe) {
        const ingredientsList = recipe.ingredients || [];
        const displayIngredients = ingredientsList.slice(0, MAX_PREVIEW_INGREDIENTS);
        const hasMore = ingredientsList.length > MAX_PREVIEW_INGREDIENTS;

        const ingredientsText = displayIngredients.join(' • ') + (hasMore ? ' • ...' : '');

        return `
            <div class="recipe-preview-card">
                <div class="recipe-name">${recipe.recipe_name}</div>
                <div class="ingredients">${ingredientsText}</div>
            </div>
        `;
    }

    /**
     * Position the preview card relative to a point, with edge detection
     * @param {number} x - X coordinate in viewport
     * @param {number} y - Y coordinate in viewport
     */
    function positionPreview(x, y) {
        if (!previewElement) return;

        const rect = previewElement.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        // Default: right and below the point
        let left = x + PREVIEW_OFFSET_X;
        let top = y + PREVIEW_OFFSET_Y;

        // Flip left if would go off right edge
        if (left + rect.width > viewportWidth - 10) {
            left = x - rect.width - PREVIEW_OFFSET_X;
        }

        // Flip up if would go off bottom edge
        if (top + rect.height > viewportHeight - 10) {
            top = y - rect.height - PREVIEW_OFFSET_Y;
        }

        // Ensure doesn't go off left or top edges
        left = Math.max(10, left);
        top = Math.max(10, top);

        previewElement.style.left = `${left}px`;
        previewElement.style.top = `${top}px`;
    }

    /**
     * Show the preview card for a recipe
     * @param {Object} recipe - Recipe data
     * @param {number} x - X coordinate in viewport
     * @param {number} y - Y coordinate in viewport
     */
    function show(recipe, x, y) {
        // Remove existing preview if any
        hide();

        currentRecipe = recipe;

        // Create preview element
        const div = document.createElement('div');
        div.innerHTML = buildPreviewHTML(recipe);
        previewElement = div.firstElementChild;

        // Add to container
        container.appendChild(previewElement);

        // Position it (need to append first to get dimensions)
        positionPreview(x, y);
    }

    /**
     * Hide the preview card
     */
    function hide() {
        if (previewElement) {
            previewElement.remove();
            previewElement = null;
        }
        currentRecipe = null;
    }

    /**
     * Start hover timer for a recipe
     * @param {Object} recipe - Recipe data
     * @param {number} x - X coordinate in viewport
     * @param {number} y - Y coordinate in viewport
     */
    function startHover(recipe, x, y) {
        // Cancel any existing timer
        cancelHover();

        // Start new timer
        hoverTimer = setTimeout(() => {
            show(recipe, x, y);
        }, HOVER_DELAY_MS);
    }

    /**
     * Cancel pending hover timer
     */
    function cancelHover() {
        if (hoverTimer) {
            clearTimeout(hoverTimer);
            hoverTimer = null;
        }
        hide();
    }

    // Public API
    return {
        startHover,
        cancelHover,
        hide,
        isVisible: () => previewElement !== null
    };
}
```

**Step 2: Commit component**

```bash
git add src/web/js/components/recipePreviewCard.js
git commit -m "feat: add recipe preview card component

- Create RecipePreviewCard with debounced hover (250ms)
- Smart positioning with edge detection
- Show recipe name + first 6 ingredients with bullets
- Configurable MAX_PREVIEW_INGREDIENTS constant"
```

---

## Task 4: Frontend - Add Preview Card Styles

**Files:**
- Modify: `src/web/styles.css`

**Step 1: Add preview card CSS**

Add this after the existing modal styles (around line 2180):

```css
/* Recipe Preview Card (Cocktail Space hover)
   ========================================================================== */

.recipe-preview-card {
    position: absolute;
    background: white;
    border: 2px solid var(--accent-color);
    border-radius: 8px;
    padding: 12px 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    pointer-events: none; /* Click-through to data point */
    max-width: 300px;
    font-size: 14px;
}

.recipe-preview-card .recipe-name {
    font-weight: bold;
    margin-bottom: 8px;
    color: var(--text-color, #2c3e50);
    font-size: 15px;
}

.recipe-preview-card .ingredients {
    color: var(--text-color-secondary, #666);
    line-height: 1.5;
    font-size: 13px;
}
```

**Step 2: Commit styles**

```bash
git add src/web/styles.css
git commit -m "style: add recipe preview card styles

- White background with red accent border
- Smart pointer-events: none for click-through
- Matches recipe card typography and colors"
```

---

## Task 5: Frontend - Integrate Preview into Cocktail Space Chart

**Files:**
- Modify: `src/web/js/charts/cocktailSpaceChart.js`

**Step 1: Import the preview card component**

At the top of `cocktailSpaceChart.js`, add:

```javascript
import { createRecipePreviewCard } from '../components/recipePreviewCard.js';
```

**Step 2: Remove the existing simple tooltip**

Find and remove these lines (around lines 82-93):

```javascript
// REMOVE THIS BLOCK:
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
```

**Step 3: Create preview card instance**

After the clip path setup (around line 102), add:

```javascript
// Create recipe preview card
const previewCard = createRecipePreviewCard(document.body);
```

**Step 4: Update circle hover handlers**

Replace the existing mouseover/mousemove/mouseout handlers (lines 118-144) with:

```javascript
circles
    .attr('cx', d => xScale(d.x))
    .attr('cy', d => yScale(d.y))
    .attr('r', 6)
    .attr('fill', 'steelblue')
    .attr('stroke', 'white')
    .attr('stroke-width', 1)
    .attr('opacity', 0.7)
    .style('cursor', 'pointer')
    .on('mouseenter', function(event, d) {
        // Enlarge circle
        d3.select(this)
            .transition()
            .duration(200)
            .attr('r', 8)
            .attr('opacity', 1);

        // Start preview card hover timer
        previewCard.startHover(d, event.pageX, event.pageY);
    })
    .on('mousemove', function(event, d) {
        // Update preview position on move (if visible)
        if (previewCard.isVisible()) {
            previewCard.hide();
            previewCard.startHover(d, event.pageX, event.pageY);
        }
    })
    .on('mouseleave', function() {
        // Restore circle size
        d3.select(this)
            .transition()
            .duration(200)
            .attr('r', 6)
            .attr('opacity', 0.7);

        // Cancel preview
        previewCard.cancelHover();
    })
    .on('click', function(event, d) {
        // Hide preview and trigger modal
        previewCard.hide();
        if (options.onRecipeClick) {
            options.onRecipeClick(d.recipe_id, d.recipe_name);
        }
    });
```

**Step 5: Hide preview during zoom/pan**

In the zoom handler (around line 152), add preview hide at the start:

```javascript
const zoom = d3.zoom()
    .scaleExtent([0.5, 10])
    .on('zoom', (event) => {
        // Hide preview during zoom/pan
        previewCard.hide();

        const transform = event.transform;

        circles
            .attr('cx', d => transform.applyX(xScale(d.x)))
            .attr('cy', d => transform.applyY(yScale(d.y)));

        g.select('.x-axis')
            .call(d3.axisBottom(xScale).scale(transform.rescaleX(xScale)));

        g.select('.y-axis')
            .call(d3.axisLeft(yScale).scale(transform.rescaleY(yScale)));
    });
```

**Step 6: Test locally**

```bash
# Make sure local server is running
./scripts/serve.sh &

# Open browser to http://localhost:8000/analytics.html
# Go to Cocktail Space tab
# Hover over points - should see preview after 250ms
# Click points - modal should still open
# Zoom/pan - preview should hide
```

Expected behavior:
- Hover shows preview after 250ms delay
- Preview shows recipe name + ingredients
- Preview positioned smartly (doesn't go off edges)
- Clicking still opens modal
- Zoom/pan hides preview

**Step 7: Commit integration**

```bash
git add src/web/js/charts/cocktailSpaceChart.js
git commit -m "feat: integrate recipe preview into cocktail space chart

- Import and create RecipePreviewCard instance
- Remove old simple tooltip
- Update hover handlers for preview with 250ms debounce
- Hide preview during zoom/pan interactions
- Preserve click-to-modal behavior"
```

---

## Task 6: Testing & Refinement

**Step 1: Test edge cases**

Manually test these scenarios:

1. **Short ingredient lists (2-3 items):**
   - Should show all ingredients, no "..."

2. **Long ingredient lists (10+ items):**
   - Should show first 6 + "..."

3. **Edge positioning:**
   - Hover near right edge → preview flips left
   - Hover near bottom → preview flips up
   - Should never go off screen

4. **Interaction:**
   - Quick mouse movement → no preview (canceled before 250ms)
   - Hover 250ms+ → preview appears
   - Click → modal opens, preview hides

5. **Zoom/pan:**
   - Preview should hide during zoom
   - Preview should reappear on next hover

**Step 2: Adjust MAX_PREVIEW_INGREDIENTS if needed**

If 6 ingredients feels too long/short, edit:

```javascript
// In src/web/js/components/recipePreviewCard.js
const MAX_PREVIEW_INGREDIENTS = 5; // or 7, etc.
```

**Step 3: Test with real data on dev**

Deploy to dev environment:

```bash
# Build and deploy
sam build --template-file template.yaml
sam deploy --config-env dev

# Trigger analytics refresh to get new data format
./scripts/trigger-analytics-refresh.sh dev

# Wait 60 seconds, then test in browser
```

**Step 4: Final commit if adjustments made**

```bash
git add -u
git commit -m "refine: adjust preview card based on testing"
```

---

## Task 7: Documentation Update

**Files:**
- Modify: `docs/plans/2025-11-29-cocktail-space-recipe-preview-design.md`

**Step 1: Add implementation notes section**

Add this section at the end of the design doc:

```markdown
## Implementation Notes

**Completed:** 2025-11-29

**Changes from design:**
- [List any deviations from the original design, or note "None"]

**Performance observations:**
- File size: [Actual gzipped size]
- Hover feel: [Too fast/slow? Adjusted delay?]

**Known issues:**
- [Any bugs or limitations discovered]
```

**Step 2: Commit documentation**

```bash
git add docs/plans/2025-11-29-cocktail-space-recipe-preview-design.md
git commit -m "docs: add implementation notes to design doc"
```

---

## Task 8: Cleanup & Merge

**Step 1: Verify all tests pass**

```bash
# Run backend tests
cd api
pytest tests/ -v

# Manual frontend testing checklist:
# [ ] Preview appears after 250ms hover
# [ ] Preview shows recipe name + ingredients
# [ ] Preview positioned correctly at edges
# [ ] Click still opens modal
# [ ] Zoom/pan hides preview
# [ ] No console errors
```

**Step 2: Push branch**

```bash
git push origin feature/cocktail-space-recipe-preview
```

**Step 3: Create pull request**

Use the GitHub CLI or web interface:

```bash
gh pr create --title "feat: add recipe preview card to cocktail space" --body "$(cat <<'EOF'
## Summary
Add lightweight recipe preview card on hover in Cocktail Space visualization.

## Changes
- Backend: Extend cocktail-space analytics to include sorted ingredient lists
- Frontend: New RecipePreviewCard component with debounced hover
- UI: Smart positioning, click-through behavior

## Testing
- [x] Manual testing of all hover scenarios
- [x] Edge detection works correctly
- [x] Modal still opens on click
- [x] No regressions in existing functionality

## Screenshots
[Add screenshot of preview card in action]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Summary

**Total tasks:** 8
**Estimated time:** 2-3 hours
**Key files modified:** 3 backend, 3 frontend, 1 new component

**Testing checklist:**
- [ ] Backend query returns ingredients in correct order
- [ ] Analytics refresh includes new data format
- [ ] Preview appears after hover delay
- [ ] Smart positioning works at all edges
- [ ] Click-to-modal still works
- [ ] Zoom/pan hides preview
- [ ] No console errors

**References:**
- Design doc: `docs/plans/2025-11-29-cocktail-space-recipe-preview-design.md`
- @superpowers:verification-before-completion - verify all functionality before claiming complete
