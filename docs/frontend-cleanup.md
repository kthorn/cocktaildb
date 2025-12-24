# Frontend Cleanup and Refactoring Notes

## Scope
These notes capture cleanup/refactor opportunities in `src/web/` for later execution. The focus is on duplication, maintainability, and production polish.

## Opportunities
- `src/web/js/ingredients.js` and `src/web/js/user-ingredients.js`: both implement `buildHierarchy` and `renderHierarchyHTML` with near-identical logic. Extract a shared hierarchy utility (for example, `src/web/js/components/ingredientTree.js`) and share the rendering helpers. Move indentation styling out of inline `style=` and into CSS classes.
- `src/web/js/recipeCard.js`: this file handles card rendering, ratings, tag editor modal, share logic, and API updates. Split into smaller modules (ratings, tags, share, ingredient formatting). The `generateTagChips` helper is duplicated inside `openTagEditorModal`; move it to a shared function and reuse.
- `src/web/js/charts/ingredientTreeChart.js`: tooltip styling and mouse handlers are duplicated for `nodeEnter` and `node`. Extract a `bindTooltipHandlers` helper and move tooltip styling to CSS instead of `.style()` chains.
- `src/web/js/common.js` plus HTML pages (`src/web/index.html`, `src/web/search.html`, etc.): `loadCommonHead()` injects `<meta>` and CSS after `DOMContentLoaded`, and `loadFooter()` injects a style override. Consider moving head content to static HTML (or a build-time template) and use a single FOUC strategy in CSS.
- Inline styles across HTML/JS (`src/web/admin.html`, `src/web/analytics.html`, `src/web/js/admin.js`, `src/web/js/recipeCard.js`, `src/web/js/ingredients.js`, `src/web/js/user-ingredients.js`) should be replaced with named CSS classes for consistency.
- Debug logging is noisy (`src/web/js/search.js`, `src/web/js/api.js`, `src/web/js/recipeCard.js`, `src/web/js/analytics.js`, `src/web/js/index.js`). Add a small logging helper (e.g., `debugLog()` gated by a flag) or remove logs for production.
- `src/web/js/ingredients.js`: relies on inline `onclick` handlers and assigns functions to `window`. Prefer event delegation on a container to avoid global namespace pollution.

## Suggested Sequencing
1. Extract shared ingredient tree utilities and remove inline styles.
2. Modularize `src/web/js/recipeCard.js` by feature (ratings, tags, share).
3. Consolidate tooltip styling/handlers in charts and move styles to CSS.
4. Clean up inline styles in HTML/JS and introduce reusable CSS utility classes.
5. Replace ad-hoc `console.log` with a gated logger.
6. Remove global `window` functions and use delegated event handlers.
