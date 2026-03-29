# Search & Recipe Creator UX Improvements

**Date:** 2026-03-21
**Status:** Approved

## Overview

Three UX improvements based on user feedback:
1. Support 1/8 measures in recipe creator
2. Fix Enter-to-search in Safari
3. Add dropdown autosuggest on recipe name search

---

## 1. Support 1/8 Measures in Recipe Creator

**Problem:** The amount input uses `step="0.25"`, preventing 1/8 (0.125) increments via the stepper arrows. Users cannot input 0.125 via the +/- controls.

**Solution:** Change `step` from `"0.25"` to `"0.125"`.

**Files:**
- `src/web/js/recipes.js:392` — change `step="0.25"` to `step="0.125"`

**No other changes needed:** The display function `formatAmount()` in `recipeCard.js:11-57` already maps 1/8 fractions correctly (line 28: `'1/8': 1/8`). The API stores amounts as floats, so 0.125 works without backend changes.

---

## 2. Fix Enter-to-Search in Safari

**Problem:** Pressing Enter in the name search field doesn't trigger search on Safari/Mac, though it works on Edge/PC. The form uses a standard `submit` event listener (`search.js:100-103`), but Safari may not fire form `submit` on Enter when other inputs in the form have `keydown` handlers that call `e.preventDefault()` (the tag autocomplete handler at `search.js:830-831` prevents Enter default when the tag dropdown is open).

**Solution:** Add an explicit `keydown` listener on `#name-search` that triggers search on Enter.

**Files:**
- `src/web/js/search.js` — add `keydown` listener on `nameSearch` element after the form submit listener (~line 103):
  ```javascript
  nameSearch.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
          e.preventDefault();
          performSearch();
      }
  });
  ```

This is a belt-and-suspenders fix — the form submit handler stays for the button click path, and the explicit keydown ensures Enter works regardless of browser behavior.

---

## 3. Dropdown Autosuggest on Recipe Name Search

**Problem:** Users must finish typing and click "Search" to see any results. No live feedback as they type.

**Solution:** Add a dropdown autosuggest to `#name-search`, following the existing tag autocomplete pattern (`search.js:715-918`).

### Behavior
- Debounced `input` listener (300ms delay)
- Minimum 2 characters before triggering suggestions
- Call existing search API: `/recipes/search?q={term}&limit=5&sort_by=name&sort_order=asc`
- Show dropdown with matching recipe names below the input
- Clicking a suggestion navigates to `/recipe.html?id={id}`
- Keyboard navigation: Arrow keys to highlight, Enter to select, Escape to close
- Click outside closes dropdown

### Files

**`src/web/search.html`** (~line 25, after the name input):
- Add a suggestions dropdown div inside the `form-group` wrapper:
  ```html
  <div id="name-suggestions-dropdown" class="name-suggestions-dropdown hidden"></div>
  ```
- Add `position: relative` to the parent `.form-group` (or wrap in a container) so the dropdown positions correctly

**`src/web/js/search.js`**:
- Add state variables at top (~line 18): `nameSearchTimeout`, `nameSuggestions`, `activeNameSuggestionIndex`
- Add `setupNameAutocomplete()` function following the `setupTagAutocomplete()` pattern:
  - `input` event → debounced API call
  - `keydown` event → Arrow/Enter/Escape navigation
  - Click outside → close dropdown
  - Render suggestions with recipe names, highlight matching text
- Call `setupNameAutocomplete()` from `DOMContentLoaded` handler
- Update the existing Enter keydown handler (from fix #2) to only trigger search when the name suggestion dropdown is NOT open — if the dropdown is open and a suggestion is highlighted, Enter should navigate to that recipe instead

**`src/web/styles.css`**:
- Add `.name-suggestions-dropdown` styles, reusing the same pattern as `.tag-suggestions-dropdown` (lines 1757-1825):
  - Absolute positioning below input
  - Same border, shadow, z-index, background
  - `.name-suggestion-item` with hover/highlighted states
  - `.no-results` and `.loading` states

### API
No backend changes needed. The existing `/recipes/search` endpoint accepts `q` for name search and `limit` for result count.

---

## Implementation Order

1. **1/8 measures** — one-line change, no dependencies
2. **Enter-to-search Safari fix** — small change, needed before autosuggest (which also uses Enter)
3. **Name autosuggest** — largest change, builds on the Enter fix
