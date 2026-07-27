# UMAP Navigation and Recipe Callouts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow deeper UMAP zooming and show recipe-name callouts whenever 20 or fewer points are visible in the plot.

**Architecture:** Keep all behavior in the existing D3 chart. A small update helper will reuse the chart's scales and current zoom transform to filter visible points and bind their names to a clipped SVG text layer. The existing point interactions, preview card, highlight rings, and recipe modal remain unchanged.

**Tech Stack:** Vanilla JavaScript modules, D3.js v7 loaded by the analytics page, CSS, Node.js assertion-based frontend contract test.

## Global Constraints

- Use a maximum zoom scale of `50`.
- Show callouts only when the transformed visible-point count is `20` or fewer.
- Recalculate callouts on initial render and every zoom/pan update.
- Keep callouts non-interactive so existing point hover/touch/click behavior is unchanged.
- Do not change API data, UMAP generation, backend code, or add dependencies.
- Follow TDD: the focused test must fail before production changes and pass afterward.

---

## File map

- Modify: `src/web/js/charts/cocktailSpaceChart.js` — add the clipped SVG callout layer, visible-point filtering/update, and zoom limit.
- Modify: `src/web/styles.css` — style recipe-name callout text with a readable contrasting outline.
- Create: `tests/test_cocktail_space_callouts.js` — lightweight Node test for the frontend source contract because this repository has no browser test runner/package setup.

### Task 1: Add adaptive recipe callouts to the UMAP chart

**Files:**

- Create: `tests/test_cocktail_space_callouts.js`
- Modify: `src/web/js/charts/cocktailSpaceChart.js:8-182,` including the zoom setup and initial point render
- Modify: `src/web/styles.css:2938-2958`

**Interfaces:**

- Consumes: Existing `data` entries `{ recipe_id, recipe_name, x, y }`, `xScale`, `yScale`, `currentTransform`, `width`, and `height` inside `createCocktailSpaceChart`.
- Produces: The existing `createCocktailSpaceChart(container, data, options)` API with a maximum zoom scale of `50`; visible points receive `.recipe-callout` SVG text labels when the visible count is at most `20`.

- [ ] **Step 1: Write the failing source-contract test**

Create `tests/test_cocktail_space_callouts.js`:

```js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const chartPath = path.join(__dirname, '..', 'src', 'web', 'js', 'charts', 'cocktailSpaceChart.js');
const chartSource = fs.readFileSync(chartPath, 'utf8');
const stylesPath = path.join(__dirname, '..', 'src', 'web', 'styles.css');
const stylesSource = fs.readFileSync(stylesPath, 'utf8');

assert.match(chartSource, /const MAX_VISIBLE_CALLOUTS\s*=\s*20/);
assert.match(chartSource, /\.scaleExtent\(\[0\.5,\s*50\]\)/);
assert.match(chartSource, /visiblePoints\.length\s*<=\s*MAX_VISIBLE_CALLOUTS/);
assert.match(chartSource, /class',\s*'recipe-callouts'/);
assert.ok(
    (chartSource.match(/updateCallouts\(currentTransform\)/g) || []).length >= 2,
    'callouts must update on initial render and zoom'
);
assert.match(chartSource, /\.text\(d\s*=>\s*d\.recipe_name\)/);
assert.match(stylesSource, /\.recipe-callout/);
assert.match(stylesSource, /pointer-events:\s*none/);

console.log('UMAP callout contract passed');
```

- [ ] **Step 2: Run the focused test and verify it fails for the missing feature**

Run:

```bash
node tests/test_cocktail_space_callouts.js
```

Expected: FAIL because the current chart still uses `scaleExtent([0.5, 10])` and has no callout constants/layer/update logic. Do not change the test to match the current implementation.

- [ ] **Step 3: Add the minimal callout constants and SVG layer**

In `src/web/js/charts/cocktailSpaceChart.js`, add the threshold beside the existing visual constants:

```js
const MAX_VISIBLE_CALLOUTS = 20;
```

After the existing circle attributes are set, create the label layer inside the same clipped plot group:

```js
const calloutLayer = g.append('g')
    .attr('class', 'recipe-callouts')
    .attr('clip-path', 'url(#clip)');
```

- [ ] **Step 4: Implement visible-point calculation and callout binding**

Add this helper after `currentTransform` is declared and before the zoom behavior:

```js
function updateCallouts(transform) {
    const visiblePoints = data.map(d => ({
        ...d,
        calloutX: transform.applyX(xScale(d.x)),
        calloutY: transform.applyY(yScale(d.y))
    })).filter(d =>
        d.calloutX >= 0 && d.calloutX <= width &&
        d.calloutY >= 0 && d.calloutY <= height
    );

    const labels = visiblePoints.length <= MAX_VISIBLE_CALLOUTS ? visiblePoints : [];

    calloutLayer.selectAll('text')
        .data(labels, d => d.recipe_id)
        .join(
            enter => enter.append('text').attr('class', 'recipe-callout'),
            update => update,
            exit => exit.remove()
        )
        .attr('x', d => d.calloutX + 8)
        .attr('y', d => d.calloutY - 8)
        .text(d => d.recipe_name);
}
```

Update the zoom handler so it keeps the existing circle/ring behavior and then refreshes labels:

```js
.on('zoom', (event) => {
    previewCard.hide();
    currentTransform = event.transform;

    circles
        .attr('cx', d => currentTransform.applyX(xScale(d.x)))
        .attr('cy', d => currentTransform.applyY(yScale(d.y)));

    updateCallouts(currentTransform);

    if (highlightRings && highlightData) {
        highlightRings
            .attr('cx', currentTransform.applyX(xScale(highlightData.x)))
            .attr('cy', currentTransform.applyY(yScale(highlightData.y)));
    }
});
```

After `svg.call(zoom);`, initialize labels with the identity transform:

```js
svg.call(zoom);
updateCallouts(currentTransform);
```

Change only the scale extent line to:

```js
.scaleExtent([0.5, 50])
```

- [ ] **Step 5: Add minimal readable callout styling**

Add this immediately after the existing cocktail-space SVG font rule in `src/web/styles.css`:

```css
#cocktail-space-chart .recipe-callout,
#cocktail-space-em-chart .recipe-callout {
    fill: #1f2937;
    font-size: 11px;
    font-weight: 600;
    paint-order: stroke;
    pointer-events: none;
    stroke: #fff;
    stroke-linejoin: round;
    stroke-width: 3px;
}
```

The white stroke provides contrast without adding an HTML overlay or a label background element.

- [ ] **Step 6: Run the focused test and verify it passes**

Run:

```bash
node tests/test_cocktail_space_callouts.js
```

Expected: PASS with `UMAP callout contract passed`.

- [ ] **Step 7: Run diagnostics and the applicable test suite**

Run:

```bash
python -m pytest tests/ -v
```

Then run diagnostics for the changed frontend files using the repository tooling. Confirm there are no blocking diagnostics in:

- `src/web/js/charts/cocktailSpaceChart.js`
- `src/web/styles.css`
- `tests/test_cocktail_space_callouts.js`

- [ ] **Step 8: Review the diff and commit**

Run:

```bash
git diff --check
git diff -- src/web/js/charts/cocktailSpaceChart.js src/web/styles.css tests/test_cocktail_space_callouts.js
git status --short
```

Confirm unrelated existing worktree changes are not staged. Commit only the feature files:

```bash
git add src/web/js/charts/cocktailSpaceChart.js src/web/styles.css tests/test_cocktail_space_callouts.js
git commit -m "feat: improve UMAP zoom and recipe callouts"
```
