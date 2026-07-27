# Recipe Card → Cocktail Space Link — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "View in Cocktail Space" link on recipe cards that navigates to the analytics page, auto-zooms to the recipe's dot, and highlights it with a pulsing ring animation.

**Architecture:** Plain anchor link on recipe cards navigates to `analytics.html#cocktail-space?highlight={id}`. Analytics page parses the hash, loads the chart, and calls a new `highlightRecipe()` API on the chart object. The chart zooms to the dot, shows pulsing rings for 10 seconds, then calls an `onComplete` callback so analytics.js can clean up the URL hash. A `dispose()` method on the chart API handles cleanup on tab switch.

**Tech Stack:** Vanilla JS, D3.js (existing), CSS animations

**Design doc:** `docs/plans/2026-03-21-recipe-card-cocktail-space-link.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/web/js/charts/cocktailSpaceChart.js` | Add highlight/dispose API to chart return value |
| `src/web/js/analytics.js` | Hash parsing, chart reference storage, highlight wiring, dispose on tab switch |
| `src/web/js/recipeCard.js` | Add cocktail space link HTML to recipe card template |
| `src/web/styles.css` | Styles for `.cocktail-space-link` and `@keyframes` for pulsing rings |

---

### Task 1: Chart Highlight API — Return Value and `highlightRecipe()`

**Files:**
- Modify: `src/web/js/charts/cocktailSpaceChart.js:156-199` (zoom handler area and end of function)

This task changes `createCocktailSpaceChart()` from returning `undefined` to returning `{ highlightRecipe, dispose }`. The highlight logic zooms to a dot and shows pulsing rings. The dispose logic cleans up timers and ring elements.

- [ ] **Step 1: Add highlight state variables after zoom setup**

In `src/web/js/charts/cocktailSpaceChart.js`, after `svg.call(zoom);` (line 175), add the highlight state and ring-update hook inside the zoom handler:

```js
// After line 175: svg.call(zoom);

// --- Highlight state (closed over by returned API) ---
let highlightRings = null;      // d3 selection of ring <circle> elements
let highlightData = null;       // the {x, y} data point being highlighted
let highlightTimeoutIds = [];   // setTimeout IDs for cleanup
let highlightOnComplete = null; // callback when highlight finishes
let highlightCompleted = false; // ensures onComplete called exactly once
```

Also update the existing zoom handler (lines 166-173) to include ring position updates:

Replace the zoom handler `.on('zoom', ...)` block:

```js
    .on('zoom', (event) => {
        previewCard.hide();
        currentTransform = event.transform;

        circles
            .attr('cx', d => currentTransform.applyX(xScale(d.x)))
            .attr('cy', d => currentTransform.applyY(yScale(d.y)));

        // Update highlight ring positions if active
        if (highlightRings && highlightData) {
            highlightRings
                .attr('cx', currentTransform.applyX(xScale(highlightData.x)))
                .attr('cy', currentTransform.applyY(yScale(highlightData.y)));
        }
    });
```

- [ ] **Step 2: Add the `dispose()` function**

After the highlight state variables (added in step 1), add:

```js
function dispose() {
    // Clear all pending timeouts
    highlightTimeoutIds.forEach(id => clearTimeout(id));
    highlightTimeoutIds = [];

    // Remove ring elements
    if (highlightRings) {
        highlightRings.remove();
        highlightRings = null;
    }
    highlightData = null;
    highlightOnComplete = null;
    highlightCompleted = false;
}
```

- [ ] **Step 3: Add the `highlightRecipe()` function**

After `dispose()`, add:

```js
function highlightRecipe(recipeId, onComplete) {
    // Clean up any existing highlight first
    dispose();

    const noop = () => {};
    highlightOnComplete = onComplete || noop;
    highlightCompleted = false;

    function callOnCompleteOnce() {
        if (!highlightCompleted) {
            highlightCompleted = true;
            highlightOnComplete();
        }
    }

    // Find the data point
    const point = data.find(d => d.recipe_id === recipeId);
    if (!point) {
        callOnCompleteOnce();
        return;
    }
    highlightData = point;

    // Compute zoom transform to center on point at k=3
    const k = 3;
    const tx = width / 2 - xScale(point.x) * k;
    const ty = height / 2 - yScale(point.y) * k;
    const newTransform = d3.zoomIdentity.translate(tx, ty).scale(k);

    // Animate zoom
    const transition = svg.transition()
        .duration(750)
        .call(zoom.transform, newTransform);

    // After zoom completes (or is interrupted), show rings
    let zoomFinished = false;
    function onZoomDone() {
        if (zoomFinished) return;
        zoomFinished = true;
        showPulsingRings(point, callOnCompleteOnce);
    }

    transition.on('end', onZoomDone);
    transition.on('interrupt', onZoomDone);
}

function showPulsingRings(point, callOnCompleteOnce) {
    const cx = currentTransform.applyX(xScale(point.x));
    const cy = currentTransform.applyY(yScale(point.y));

    // Get the clipped group (first <g> child with clip-path)
    const clipGroup = g.select('g[clip-path]');

    // Two concentric rings with offset animation delays
    highlightRings = clipGroup.selectAll('.highlight-ring')
        .data([0, 1])
        .enter()
        .append('circle')
        .attr('class', 'highlight-ring')
        .attr('cx', cx)
        .attr('cy', cy)
        .attr('r', DOT_RADIUS)
        .attr('fill', 'none')
        .attr('stroke', '#e8a030')
        .attr('stroke-width', 2)
        .attr('pointer-events', 'none')
        .style('animation', (d, i) =>
            `cocktail-space-pulse 1.5s ease-out ${i * 0.5}s infinite`
        );

    // After 10 seconds, fade out and clean up
    const fadeId = setTimeout(() => {
        if (highlightRings) {
            highlightRings
                .transition()
                .duration(500)
                .style('opacity', 0)
                .on('end', function() {
                    dispose();
                    callOnCompleteOnce();
                });
        } else {
            callOnCompleteOnce();
        }
    }, 10000);
    highlightTimeoutIds.push(fadeId);
}
```

- [ ] **Step 4: Add the return statement**

The function currently ends at line 199 (closing `}`). Just before that closing brace, add:

```js
    return { highlightRecipe, dispose };
```

- [ ] **Step 5: Verify the file loads without errors**

Run: `npx live-server src/web --port=8000 --no-browser &`

Open `http://localhost:8000/analytics.html` in a browser. Open devtools console. Confirm no JavaScript errors on page load. The chart should render exactly as before (no visual changes yet).

Kill the server when done.

- [ ] **Step 6: Commit**

```bash
git add src/web/js/charts/cocktailSpaceChart.js
git commit -m "feat: add highlightRecipe/dispose API to cocktail space chart"
```

---

### Task 2: CSS for Pulsing Ring Animation

**Files:**
- Modify: `src/web/styles.css` (after `.similar-loading` block, ~line 841)

- [ ] **Step 1: Add the keyframes and ring styles**

In `src/web/styles.css`, after the `.recipe-card .similar-loading` block (line 841), add:

```css
/* Cocktail space highlight ring animation */
@keyframes cocktail-space-pulse {
    0% {
        r: 5;
        opacity: 0.6;
    }
    100% {
        r: 15;
        opacity: 0;
    }
}
```

Note: The `r` property in CSS animations works on SVG `<circle>` elements. The starting radius (`5`) matches `DOT_RADIUS` and expands to 3x (`15`).

- [ ] **Step 2: Commit**

```bash
git add src/web/styles.css
git commit -m "feat: add CSS keyframes for cocktail space highlight pulse"
```

---

### Task 3: Hash Parsing and Highlight Wiring in Analytics

**Files:**
- Modify: `src/web/js/analytics.js:9-14` (state object), `19-35` (initAnalytics), `67-96` (setupTabNavigation), `427-473` (loadCocktailSpaceData), `478-524` (loadCocktailSpaceEmData)

- [ ] **Step 1: Extend the state object**

In `src/web/js/analytics.js`, update the state object (lines 9-14):

```js
const state = {
    currentTab: 'ingredients',
    ingredientHierarchy: [],
    currentParentId: null,
    lastUpdated: null,
    highlightRecipeId: null,
    cocktailSpaceChart: null,
    cocktailSpaceEmChart: null
};
```

- [ ] **Step 2: Replace hash parsing in `initAnalytics()`**

Replace lines 25-30 of `initAnalytics()`:

```js
    // Check for URL hash to load specific tab
    const hash = window.location.hash.slice(1); // Remove '#'
    if (hash && isValidTab(hash)) {
        state.currentTab = hash;
        activateTab(hash);
    }
```

With:

```js
    // Check for URL hash to load specific tab (supports ?highlight=N params)
    const rawHash = window.location.hash.slice(1); // Remove '#'
    const [tabPart, queryPart] = rawHash.split('?', 2);
    if (tabPart && isValidTab(tabPart)) {
        state.currentTab = tabPart;
        activateTab(tabPart);

        // Parse highlight parameter
        if (queryPart) {
            const params = new URLSearchParams(queryPart);
            const highlightVal = params.get('highlight');
            if (highlightVal && /^\d+$/.test(highlightVal)) {
                const id = parseInt(highlightVal, 10);
                if (id > 0) {
                    state.highlightRecipeId = id;
                }
            }
        }
    }
```

- [ ] **Step 3: Store chart reference and trigger highlight in `loadCocktailSpaceData()`**

In `loadCocktailSpaceData()` (line 456), change:

```js
        // Render chart
        createCocktailSpaceChart(chartContainer, response.data, {
            onRecipeClick: handleRecipeClick
        });
```

To:

```js
        // Render chart
        state.cocktailSpaceChart = createCocktailSpaceChart(chartContainer, response.data, {
            onRecipeClick: handleRecipeClick
        });

        // Trigger highlight if requested via URL hash
        if (state.highlightRecipeId && state.cocktailSpaceChart) {
            const recipeId = state.highlightRecipeId;
            state.highlightRecipeId = null; // Consume once
            state.cocktailSpaceChart.highlightRecipe(recipeId, () => {
                history.replaceState(null, '', '#' + state.currentTab);
            });
        }
```

- [ ] **Step 4: Store chart reference in `loadCocktailSpaceEmData()`**

In `loadCocktailSpaceEmData()` (line 507), change:

```js
        // Render chart
        createCocktailSpaceChart(chartContainer, response.data, {
            onRecipeClick: handleRecipeClick
        });
```

To:

```js
        // Render chart
        state.cocktailSpaceEmChart = createCocktailSpaceChart(chartContainer, response.data, {
            onRecipeClick: handleRecipeClick
        });

        // Trigger highlight if requested via URL hash
        if (state.highlightRecipeId && state.cocktailSpaceEmChart) {
            const recipeId = state.highlightRecipeId;
            state.highlightRecipeId = null;
            state.cocktailSpaceEmChart.highlightRecipe(recipeId, () => {
                history.replaceState(null, '', '#' + state.currentTab);
            });
        }
```

- [ ] **Step 5: Add dispose calls on tab switch**

In `setupTabNavigation()`, inside the tab button click handler (line 72), add dispose calls after `state.currentTab = tabName;` (line 83):

```js
            // Update state and load data
            state.currentTab = tabName;

            // Dispose active chart highlights when switching tabs
            if (state.cocktailSpaceChart) {
                state.cocktailSpaceChart.dispose();
            }
            if (state.cocktailSpaceEmChart) {
                state.cocktailSpaceEmChart.dispose();
            }

            await loadTabData(tabName);
```

Also add the same dispose calls in `setupMobileViewSelector()`, in the change handler, after `state.currentTab = selectedTab;` (which is around line 125 in the existing code — find the line `state.currentTab = selectedTab;` and add the same block after it):

```js
        state.currentTab = selectedTab;

        // Dispose active chart highlights when switching tabs
        if (state.cocktailSpaceChart) {
            state.cocktailSpaceChart.dispose();
        }
        if (state.cocktailSpaceEmChart) {
            state.cocktailSpaceEmChart.dispose();
        }
```

- [ ] **Step 6: Verify hash parsing works**

Start local server: `npx live-server src/web --port=8000 --no-browser &`

1. Open `http://localhost:8000/analytics.html#cocktail-space?highlight=42` in a browser
2. Devtools console should show no errors
3. The Cocktail Space tab should be active
4. If recipe ID 42 exists in the UMAP data: the chart should zoom to the dot and show pulsing rings
5. After 10 seconds: rings fade out, URL becomes `#cocktail-space`
6. If recipe ID 42 doesn't exist: chart loads normally with no highlight, URL cleans up immediately

Test invalid hashes:
- `#cocktail-space?highlight=bogus` → no highlight, no errors
- `#cocktail-space?highlight=0` → no highlight, no errors
- `#cocktail-space?highlight=42abc` → no highlight, no errors

Kill the server when done.

- [ ] **Step 7: Commit**

```bash
git add src/web/js/analytics.js
git commit -m "feat: add hash parsing and highlight wiring for cocktail space deep links"
```

---

### Task 4: Recipe Card Link

**Files:**
- Modify: `src/web/js/recipeCard.js:177-182` (similar-cocktails template block)

- [ ] **Step 1: Add the cocktail space link HTML to the template**

In `src/web/js/recipeCard.js`, find the `showSimilar` template block (lines 177-182):

```js
        ${showSimilar ? `
        <div class="similar-cocktails" data-recipe-id="${recipe.id}">
            <h5>Similar Cocktails</h5>
            <div class="similar-loading">Loading similar cocktails...</div>
        </div>
        ` : ''}
```

Replace with:

```js
        ${showSimilar ? `
        <div class="similar-cocktails" data-recipe-id="${recipe.id}">
            <h5>Similar Cocktails</h5>
            <div class="similar-loading">Loading similar cocktails...</div>
        </div>
        <div class="cocktail-space-link">
            <a href="analytics.html#cocktail-space?highlight=${recipe.id}">📍 View in Cocktail Space →</a>
        </div>
        ` : ''}
```

The `.cocktail-space-link` div is a sibling of `.similar-cocktails`, not a child. This is critical because `loadSimilarCocktails()` calls `container.remove()` on the `.similar-cocktails` div when there are no neighbors or on API error (lines 350, 389). As a sibling, the link survives regardless.

- [ ] **Step 2: Add CSS styles for the link**

In `src/web/styles.css`, after the `.recipe-card .similar-loading` block (line 841, right before the `/* Stat cards */` comment), add:

```css
.recipe-card .cocktail-space-link {
    margin-top: var(--space-sm);
    padding-top: var(--space-sm);
    border-top: 1px solid var(--border-light);
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.recipe-card .cocktail-space-link a {
    color: var(--accent-color);
    text-decoration: none;
    font-size: var(--text-sm);
}

.recipe-card .cocktail-space-link a:hover {
    text-decoration: underline;
}
```

- [ ] **Step 3: Verify the link appears on recipe cards**

Start local server: `npx live-server src/web --port=8000 --no-browser &`

1. Open `http://localhost:8000/recipe.html?id=1` (or any valid recipe ID)
2. Scroll to below the Similar Cocktails section
3. Confirm "📍 View in Cocktail Space →" link is visible with correct styling
4. Confirm the link's `href` is `analytics.html#cocktail-space?highlight=1`
5. Click the link → should navigate to analytics page, Cocktail Space tab, with highlight

Also verify on the home page (`index.html`) — recipe cards there also pass `showSimilar: true`, so the link should appear.

Kill the server when done.

- [ ] **Step 4: Commit**

```bash
git add src/web/js/recipeCard.js src/web/styles.css
git commit -m "feat: add 'View in Cocktail Space' link to recipe cards"
```

---

### Task 5: Manual Verification (Full Flow)

No code changes. Run through the complete verification checklist from the design doc.

- [ ] **Step 1: Start local server**

```bash
npx live-server src/web --port=8000 --no-browser &
```

- [ ] **Step 2: Run verification checklist**

Open `http://localhost:8000/` in a browser and test each item:

1. **Link appears**: Open a recipe page → "View in Cocktail Space" link visible below Similar Cocktails
2. **Link navigates**: Click link → lands on analytics page, Cocktail Space tab active
3. **Highlight + zoom**: Dot zooms in and pulsing rings appear at the correct position
4. **Ring tracks zoom**: While rings are pulsing, manually zoom/pan → rings stay attached to the dot
5. **Ring fades**: After 10 seconds, rings fade out and are removed from the DOM (check devtools Elements panel)
6. **URL cleanup**: After fade, URL hash reflects current tab without `?highlight=` parameter
7. **Tab switch during highlight**: Click to another tab while rings are pulsing → rings/timers cleaned up, no console errors
8. **Invalid ID**: Navigate to `analytics.html#cocktail-space?highlight=bogus` → no errors, chart loads normally
9. **Missing recipe**: Navigate with a valid-format ID that doesn't exist in UMAP data → chart loads, no highlight, no errors
10. **Shared link**: Copy the URL during the 10-second highlight window, open in new tab → highlight replays

- [ ] **Step 3: Kill server and clean up**

```bash
kill %1  # or however the background server was started
```

If any issues found, fix them and re-test before proceeding.
