# Design: Recipe Card → Cocktail Space Link

**Status:** Refined

## Summary

Add a link from recipe cards to the recipe's location in the UMAP Cocktail Space visualization. Clicking the link navigates to the analytics page, switches to the Cocktail Space tab, auto-zooms to the recipe's dot, and highlights it with a pulsing ring that fades after 10 seconds.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Navigation target | Analytics page, Cocktail Space tab | Full-page view lets user explore the neighborhood |
| Link placement | Below Similar Cocktails section | Natural "explore further" progression |
| Visibility | Shown when `showSimilar` is true | Practically all recipes have UMAP data; recently uploaded ones may not |
| Deep-link mechanism | URL hash: `analytics.html#cocktail-space?highlight={id}` | Shareable, bookmarkable, no side-channel state |
| Highlight style | Pulsing ring + auto-zoom | Eye-catching without altering the dot's normal appearance |
| Ring duration | 10 seconds, then fade out | Enough time to orient without being permanent |

## Components

### 1. Recipe Card Link (`recipeCard.js`)

Add an `<a>` tag as an independent sibling `<div>` after the Similar Cocktails `<div>` when `showSimilar` is true:

```html
<div class="cocktail-space-link">
  <a href="analytics.html#cocktail-space?highlight={recipe_id}">
    📍 View in Cocktail Space →
  </a>
</div>
```

This is a plain anchor tag — no JavaScript click handler on the card side. The recipe card already has `recipe.id` available in scope.

**Important**: The `.cocktail-space-link` div must be a sibling of `.similar-cocktails`, not a child. The `loadSimilarCocktails()` function calls `container.remove()` when there are no neighbors or on API error, which would destroy a child element. As an independent sibling, the link survives regardless of whether similar cocktails load successfully.

**Styling**: Text link using `var(--text-sm)` / `var(--accent-color)` (matching recipe card section headings). Sits below the Similar Cocktails section with a `1px solid var(--border-light)` top border and `var(--space-sm)` padding-top (matching the card's visual rhythm).

### 2. Hash Parsing (`analytics.js`)

The existing `initAnalytics()` already reads `window.location.hash` to determine which tab to activate (line 26). Currently it only supports plain tab names like `#cocktail-space`.

**Change**: Extend hash parsing to support query parameters after the tab name:

```
#cocktail-space?highlight=42
```

Parsing logic (replaces the existing hash parsing block at lines 26-30 of `initAnalytics()`):
1. Split hash on first `?` → tab name + query string
2. Validate tab name with existing `isValidTab()` — this split **must** happen before the `isValidTab()` check, since the current code passes the raw hash (including query string) to `isValidTab()` which would fail
3. Parse query string with `new URLSearchParams(queryString)`, take first `highlight` value via `.get('highlight')`
4. Validate the value with `/^\d+$/` — reject anything that isn't a pure digit string, then `parseInt(value, 10)`, and verify the result is `> 0`
5. Store highlight recipe ID in module state

The highlight parameter is consumed once. After the ring animation fades (10 seconds), the URL hash is updated via `replaceState` to `#${state.currentTab}` (i.e., whichever tab is currently active). This way, if the user copies the URL during the animation to share the highlight link, it still works — and if the user has switched tabs in the meantime, the cleaned-up URL reflects their actual location rather than hardcoding `#cocktail-space`.

### 3. Chart Highlight API (`cocktailSpaceChart.js`)

`createCocktailSpaceChart()` currently returns nothing. Add a return value — an object with a `highlightRecipe(recipeId)` method:

```js
const chart = createCocktailSpaceChart(container, data, options);
// Returns: { highlightRecipe(recipeId, onComplete), dispose() }
```

**`highlightRecipe(recipeId, onComplete)`** does:
1. Find the data point matching `recipeId` in the bound data
2. If not found, call `onComplete()` immediately and return (so the caller can clean up the hash)
3. Compute a zoom transform that centers the point at scale `k = 3` (clamped to the zoom behavior's `scaleExtent`) using the captured `zoom` behavior and `svg` selection (both are local variables inside `createCocktailSpaceChart` — the returned API closes over them)
4. Animate the zoom transition via `svg.transition().duration(750).call(zoom.transform, newTransform)`
5. After zoom completes (listen for both `end` and `interrupt` events on the transition — `interrupt` fires if the user manually zooms/pans during the animated transition), append pulsing ring SVG elements at the dot's position. Use a `called` flag to guarantee `onComplete` is invoked exactly once regardless of which event fires.
6. After 10 seconds, fade out the rings, remove them from the DOM, and call `onComplete()`

The chart code never touches `window.history` or `window.location` — all URL/hash management stays in `analytics.js` via the `onComplete` callback. This keeps the chart module view-only.

**Zoom transform note**: The existing chart applies zoom by manually recomputing each circle's `cx`/`cy` via `currentTransform.applyX(xScale(d.x))` rather than using a group-level `transform` attribute. This means appended ring elements will **not** automatically move with zoom. The ring positions must be updated inside the existing zoom event handler. The implementation should:
- Store a reference to the ring elements (if active)
- In the zoom handler, update ring `cx`/`cy` the same way circles are updated
- When rings are removed (after 10s fade), clear the reference so the zoom handler skips the update

**`dispose()`** is a separate method on the returned chart API object. It clears all pending timeouts and removes ring elements. This is called:
- Before a new `highlightRecipe()` call (idempotent re-highlight)
- When the chart container is cleared/reloaded (e.g., data refresh)
- On tab switch away from the cocktail space tab (analytics.js should call `dispose()` in the tab-switch handler)

Store the active timeout IDs in the closure so `dispose()` can `clearTimeout` them.

**Pulsing ring implementation**:
- Two concentric `<circle>` elements with `fill: none`, `stroke: #e8a030`, `pointer-events: none`, offset animation (`0s` and `0.5s` delay)
- CSS `@keyframes` animation: radius expands from dot size to ~3x, opacity fades from 0.6 to 0
- Animation duration: ~1.5s per pulse, repeating
- At 10 seconds: transition ring opacity to 0 over 500ms, then remove elements

### 4. Wiring (`analytics.js`)

After `loadCocktailSpaceData()` (and `loadCocktailSpaceEmData()`), the chart object is available. If a highlight recipe ID is in state:

1. Call `chart.highlightRecipe(recipeId, onComplete)` where `onComplete` does `history.replaceState(null, '', '#' + state.currentTab)`
2. Clear the highlight ID from state (so it isn't re-triggered on tab revisit)
3. URL hash cleanup happens via the `onComplete` callback — either after the 10-second fade, or immediately if the recipe wasn't found in the data

The chart reference needs to be stored — add a `cocktailSpaceChart` (and `cocktailSpaceEmChart`) field to the `state` object.

### 5. Which Tab to Target

The link always points to `#cocktail-space` (Manhattan distance). This is the primary/default UMAP view. The EM variant is a secondary view — linking to it would require the user to know the distinction, which adds no value.

If in the future we want to support both, the link format already supports it: `#cocktail-space-em?highlight=42`.

## Data Flow

```
Recipe Card                    Analytics Page
-----------                    --------------
<a href="analytics.html        initAnalytics()
  #cocktail-space                ├── parseHash() → tab="cocktail-space", highlight=42
  ?highlight=42">                ├── activateTab("cocktail-space")
                                 └── loadCocktailSpaceData()
                                      ├── fetch UMAP data from API
                                      ├── chart = createCocktailSpaceChart(...)
                                      ├── state.cocktailSpaceChart = chart
                                      └── if highlight:
                                           ├── chart.highlightRecipe(42, onComplete)
                                           │    ├── if not found → onComplete() immediately
                                           │    ├── zoom to dot (750ms)
                                           │    ├── show pulsing rings
                                           │    └── after 10s: fade rings → onComplete()
                                           ├── onComplete: replaceState → #${state.currentTab}
                                           └── clear highlight from state
```

## Edge Cases

- **Recipe not in UMAP data**: `highlightRecipe()` calls `onComplete()` immediately and returns without zooming or showing rings. The user lands on the Cocktail Space tab and sees the full chart. The URL hash is cleaned up via the callback. This handles recently-uploaded recipes that haven't been included in the next analytics refresh.
- **User zooms/pans before ring fades**: The zoom handler updates ring positions alongside circle positions, so rings stay attached to the dot.
- **Hash with invalid recipe ID**: Validated with `/^\d+$/` test before `parseInt`, plus `> 0` check. Strings like `42abc` (which `parseInt` would accept as `42`), `0`, and negative values are all rejected.
- **Direct URL access** (e.g., shared link): Works — the full page load path handles it identically.
- **Recipe card in modal context** (e.g., clicking a dot in cocktail space opens a modal with a recipe card): The "View in Cocktail Space" link would navigate away from the modal to the full analytics page. This is correct behavior — the modal recipe card already has a "View Full Recipe" link that navigates away too.

## Verification

Manual testing checklist (no automated tests — this is pure frontend DOM/D3 work):

1. **Link appears**: Open a recipe page → "View in Cocktail Space" link visible below Similar Cocktails
2. **Link navigates**: Click link → lands on analytics page, Cocktail Space tab active
3. **Highlight + zoom**: Dot zooms in and pulsing rings appear at the correct position
4. **Ring tracks zoom**: While rings are pulsing, manually zoom/pan → rings stay attached to the dot
5. **Ring fades**: After 10 seconds, rings fade out and are removed from the DOM
6. **URL cleanup**: After fade, URL hash reflects current tab without `?highlight=` parameter
7. **Tab switch during highlight**: Click to another tab while rings are pulsing → rings/timers cleaned up, no console errors
8. **Invalid ID**: Navigate to `analytics.html#cocktail-space?highlight=bogus` → no errors, chart loads normally
9. **Missing recipe**: Navigate with a valid-format ID that doesn't exist in UMAP data → chart loads, no highlight, no errors
10. **Shared link**: Copy the URL during the 10-second highlight window, open in new tab → highlight replays

## Files Changed

| File | Change |
|------|--------|
| `src/web/js/recipeCard.js` | Add cocktail space link after Similar Cocktails div |
| `src/web/js/analytics.js` | Extend hash parsing, store chart reference, trigger highlight |
| `src/web/js/charts/cocktailSpaceChart.js` | Return chart API with `highlightRecipe()` method |
| `src/web/styles.css` | Style for `.cocktail-space-link` |

No backend changes required. No new API endpoints. No new dependencies.
