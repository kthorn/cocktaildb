# Search & Recipe Creator UX Improvements — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three user-reported UX issues: support 1/8 measures in recipe creator, fix Enter-to-search in Safari, and add name autosuggest dropdown on the search page.

**Architecture:** All changes are frontend-only (vanilla JS + HTML + CSS). No API or backend changes needed. The autosuggest reuses the existing search API endpoint and follows the established tag autocomplete pattern.

**Tech Stack:** Vanilla JavaScript, HTML, CSS. No new dependencies.

**Design doc:** `docs/plans/2026-03-21-search-recipe-ux-design.md`

---

### Task 1: Support 1/8 Measures in Recipe Creator

**Files:**
- Modify: `src/web/js/recipes.js:392`

**Step 1: Change the step attribute**

In `src/web/js/recipes.js`, line 392, change the `step` value from `"0.25"` to `"0.125"`:

```javascript
// Before:
<input type="number" class="ingredient-amount" name="ingredient-amount" placeholder="Amount" step="0.25" min="0">

// After:
<input type="number" class="ingredient-amount" name="ingredient-amount" placeholder="Amount" step="0.125" min="0">
```

**Step 2: Manual verification**

Run: `npx live-server src/web --port=8000`

Verify:
1. Open recipe creator (click "Add Recipe" or edit an existing recipe)
2. In the amount field, use the +/- stepper arrows
3. Confirm it increments by 0.125 (each click: 0.125, 0.25, 0.375, 0.5, etc.)
4. Type `0.125` directly — confirm it's accepted without validation error
5. Confirm the display function already renders 0.125 as "1/8" on recipe view (this is handled by `formatAmount()` in `recipeCard.js:28`)

**Step 3: Commit**

```bash
git add src/web/js/recipes.js
git commit -m "fix: support 1/8 measure increments in recipe creator"
```

---

### Task 2: Fix Enter-to-Search in Safari

**Files:**
- Modify: `src/web/js/search.js:103` (after the form submit listener)

**Step 1: Add explicit keydown handler on name input**

In `src/web/js/search.js`, after the form submit listener (line 103), add a `keydown` listener on `nameSearch`:

```javascript
    // Form submit event
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await performSearch();
    });

    // Explicit Enter key handler for Safari compatibility
    nameSearch.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            performSearch();
        }
    });
```

**Why this works:** Safari sometimes doesn't fire the form `submit` event on Enter when other inputs in the form have `keydown` handlers that call `e.preventDefault()` (the tag autocomplete at line 830-831 does this). This explicit handler ensures Enter always triggers search regardless of browser quirks. The `e.preventDefault()` prevents double-firing in browsers where form submit already works.

**Step 2: Manual verification**

Run: `npx live-server src/web --port=8000`

Verify on the search page:
1. Type a recipe name in the Name field
2. Press Enter — confirm search triggers
3. Confirm clicking the "Search" button still works
4. Confirm the tag autocomplete still works (type in tags field, use Enter to select a suggestion)

**Step 3: Commit**

```bash
git add src/web/js/search.js
git commit -m "fix: add explicit Enter key handler on search for Safari compatibility"
```

---

### Task 3: Add Name Suggestions Dropdown — HTML Structure

**Files:**
- Modify: `src/web/search.html:21-26`

**Step 1: Wrap name input and add dropdown div**

In `src/web/search.html`, modify the name search form group (lines 21-26) to wrap the input in a container with `position: relative` and add the dropdown div:

```html
<!-- Before (lines 21-26): -->
<div class="form-group form-group-inline">
    <label for="name-search">Name</label>
    <input type="text" id="name-search"
        name="name-search"
        placeholder="Search by recipe name">
</div>

<!-- After: -->
<div class="form-group form-group-inline">
    <label for="name-search">Name</label>
    <div class="name-search-wrapper">
        <input type="text" id="name-search"
            name="name-search"
            placeholder="Search by recipe name"
            autocomplete="off">
        <div id="name-suggestions-dropdown" class="name-suggestions-dropdown hidden"></div>
    </div>
</div>
```

Key details:
- `autocomplete="off"` prevents the browser's built-in autocomplete from competing with our dropdown
- The `.name-search-wrapper` div provides the `position: relative` anchor for the absolutely-positioned dropdown
- The dropdown div follows the same pattern as `#tag-suggestions-dropdown` in the tag search section (line 52)

**Step 2: Commit**

```bash
git add src/web/search.html
git commit -m "feat: add name suggestions dropdown HTML structure"
```

---

### Task 4: Add Name Suggestions Dropdown — CSS Styles

**Files:**
- Modify: `src/web/styles.css` (insert after the tag suggestions block, ~line 1825)

**Step 1: Add styles for name suggestions**

In `src/web/styles.css`, after the `.tag-suggestions-dropdown` block (after line 1824), add:

```css
/* Name search autosuggest dropdown */
.name-search-wrapper {
    position: relative;
    flex: 1;
}

.name-search-wrapper input {
    width: 100%;
}

.name-suggestions-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: var(--bg-white);
    border: 1px solid var(--border-light);
    border-top: none;
    border-radius: 0 0 var(--radius-md) var(--radius-md);
    max-height: 250px;
    overflow-y: auto;
    z-index: 1000;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.name-suggestions-dropdown.hidden {
    display: none;
}

.name-suggestion-item {
    padding: var(--space-sm) var(--space-md);
    cursor: pointer;
    transition: background-color 0.2s ease;
    border-bottom: 1px solid var(--border-lighter);
}

.name-suggestion-item:last-child {
    border-bottom: none;
}

.name-suggestion-item:hover,
.name-suggestion-item.highlighted {
    background-color: var(--bg-light);
}

.name-suggestions-dropdown .no-results,
.name-suggestions-dropdown .loading {
    padding: var(--space-md);
    text-align: center;
    color: var(--text-light);
    font-style: italic;
}
```

This mirrors the `.tag-suggestions-dropdown` styles (lines 1757-1824) with minor adjustments:
- No `display: flex` on items (recipe names are single-line, not name+type pairs)
- `max-height: 250px` slightly taller since recipe names can be longer

**Step 2: Commit**

```bash
git add src/web/styles.css
git commit -m "feat: add CSS styles for name suggestions dropdown"
```

---

### Task 5: Add Name Suggestions Dropdown — JavaScript (State & Setup)

**Files:**
- Modify: `src/web/js/search.js`

**Step 1: Add state variables**

In `src/web/js/search.js`, after the tag autocomplete state variables (after line 18), add:

```javascript
// Name autocomplete management
let nameSearchTimeout = null;
let nameSuggestions = [];
let activeNameSuggestionIndex = -1;
```

**Step 2: Add setup call in DOMContentLoaded**

In the `DOMContentLoaded` handler, after the `setupTagAutocomplete()` call (line 66), add:

```javascript
    // Setup name search autocomplete
    setupNameAutocomplete();
```

**Step 3: Update the Enter keydown handler from Task 2**

Replace the Enter keydown handler added in Task 2 with a version that respects the autosuggest dropdown state:

```javascript
    // Explicit Enter key handler for Safari compatibility
    // (defers to autosuggest keyboard navigation when dropdown is open)
    nameSearch.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const dropdown = document.getElementById('name-suggestions-dropdown');
            if (dropdown && !dropdown.classList.contains('hidden')) {
                // Let the autosuggest keydown handler deal with it
                return;
            }
            e.preventDefault();
            performSearch();
        }
    });
```

**Step 4: Commit**

```bash
git add src/web/js/search.js
git commit -m "feat: add name autosuggest state variables and setup wiring"
```

---

### Task 6: Add Name Suggestions Dropdown — JavaScript (Core Functions)

**Files:**
- Modify: `src/web/js/search.js`

**Step 1: Add the autosuggest functions**

In `src/web/js/search.js`, after the `hideTagDropdown()` function (~line 918), add the name autocomplete functions. These follow the same pattern as `setupTagAutocomplete()` (lines 716-918):

```javascript
    // Name search autocomplete functionality
    function setupNameAutocomplete() {
        const nameInput = document.getElementById('name-search');
        const dropdown = document.getElementById('name-suggestions-dropdown');

        if (!nameInput || !dropdown) return;

        // Input event for name search (debounced)
        nameInput.addEventListener('input', handleNameInput);

        // Keyboard navigation for suggestions
        nameInput.addEventListener('keydown', handleNameSuggestKeydown);

        // Click outside to close dropdown
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.name-search-wrapper')) {
                hideNameDropdown();
            }
        });

        // Click on a suggestion
        dropdown.addEventListener('click', handleNameSuggestionClick);
    }

    function handleNameInput(e) {
        const query = e.target.value.trim();

        if (nameSearchTimeout) {
            clearTimeout(nameSearchTimeout);
        }

        if (query.length < 2) {
            hideNameDropdown();
            return;
        }

        // Debounce the search
        nameSearchTimeout = setTimeout(() => {
            searchRecipeNames(query);
        }, 300);
    }

    async function searchRecipeNames(query) {
        const dropdown = document.getElementById('name-suggestions-dropdown');

        try {
            dropdown.innerHTML = '<div class="loading">Searching...</div>';
            showNameDropdown();

            // Use the existing search API with a small limit for suggestions
            const result = await api.searchRecipes(
                { name: query },
                1,    // page
                5,    // limit — only need a few suggestions
                'name',
                'asc'
            );

            if (!result || !result.recipes || result.recipes.length === 0) {
                dropdown.innerHTML = '<div class="no-results">No recipes found</div>';
                nameSuggestions = [];
                return;
            }

            nameSuggestions = result.recipes;

            const queryLower = query.toLowerCase();
            const html = nameSuggestions.map((recipe, index) => {
                // Highlight matching portion of the name
                const name = recipe.name;
                const matchIndex = name.toLowerCase().indexOf(queryLower);
                let displayName;
                if (matchIndex >= 0) {
                    displayName = name.substring(0, matchIndex)
                        + '<strong>' + name.substring(matchIndex, matchIndex + query.length) + '</strong>'
                        + name.substring(matchIndex + query.length);
                } else {
                    displayName = name;
                }

                return `<div class="name-suggestion-item" data-index="${index}" data-recipe-id="${recipe.id}">${displayName}</div>`;
            }).join('');

            dropdown.innerHTML = html;
            activeNameSuggestionIndex = -1;

        } catch (error) {
            console.error('Error searching recipe names:', error);
            dropdown.innerHTML = '<div class="no-results">Error loading suggestions</div>';
        }
    }

    function handleNameSuggestKeydown(e) {
        const dropdown = document.getElementById('name-suggestions-dropdown');

        if (dropdown.classList.contains('hidden')) return;

        const items = dropdown.querySelectorAll('.name-suggestion-item');

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                activeNameSuggestionIndex = Math.min(activeNameSuggestionIndex + 1, items.length - 1);
                updateNameSuggestionHighlight(items);
                break;

            case 'ArrowUp':
                e.preventDefault();
                activeNameSuggestionIndex = Math.max(activeNameSuggestionIndex - 1, -1);
                updateNameSuggestionHighlight(items);
                break;

            case 'Enter':
                e.preventDefault();
                if (activeNameSuggestionIndex >= 0 && items[activeNameSuggestionIndex]) {
                    navigateToRecipe(items[activeNameSuggestionIndex]);
                } else {
                    // No suggestion highlighted — run full search
                    hideNameDropdown();
                    performSearch();
                }
                break;

            case 'Escape':
                hideNameDropdown();
                break;
        }
    }

    function updateNameSuggestionHighlight(items) {
        items.forEach((item, index) => {
            item.classList.toggle('highlighted', index === activeNameSuggestionIndex);
        });
    }

    function handleNameSuggestionClick(e) {
        const item = e.target.closest('.name-suggestion-item');
        if (item) {
            navigateToRecipe(item);
        }
    }

    function navigateToRecipe(item) {
        const recipeId = item.dataset.recipeId;
        window.location.href = `/recipe.html?id=${recipeId}`;
    }

    function showNameDropdown() {
        document.getElementById('name-suggestions-dropdown').classList.remove('hidden');
    }

    function hideNameDropdown() {
        const dropdown = document.getElementById('name-suggestions-dropdown');
        dropdown.classList.add('hidden');
        activeNameSuggestionIndex = -1;
    }
```

**Step 2: Manual verification**

Run: `npx live-server src/web --port=8000`

Verify on the search page:
1. Type "mar" in the Name field — dropdown appears after 300ms with matching recipes (e.g., "Margarita")
2. Type one character — no dropdown (minimum 2 chars)
3. Arrow down/up — items highlight in dropdown
4. Enter with a highlighted item — navigates to that recipe page
5. Enter with no highlight — runs full search (existing behavior)
6. Escape — closes dropdown
7. Click a suggestion — navigates to recipe page
8. Click outside — closes dropdown
9. Clear input — dropdown disappears
10. Full search with filters still works (click Search button, tag filters, ingredient filters)

**Step 3: Commit**

```bash
git add src/web/js/search.js
git commit -m "feat: add recipe name autosuggest dropdown on search page"
```

---

### Task 7: Final Review and Cleanup

**Step 1: Full smoke test**

Run: `npx live-server src/web --port=8000`

Test all three features together:
1. **Recipe creator:** Add ingredient with 1/8 oz amount using stepper arrows → shows 0.125
2. **Search page — Enter:** Type name, press Enter → search executes
3. **Search page — Autosuggest:** Type 2+ chars → dropdown appears → click or Enter to navigate
4. **Search page — filters:** Use tag, ingredient, rating filters with Search button → all still work
5. **Search page — reset:** Click Reset → form clears, dropdown hidden

**Step 2: Run existing tests**

```bash
python -m pytest tests/ -v
```

Expected: All existing tests pass (changes are frontend-only, no backend impact).

**Step 3: Final commit if any cleanup needed, then squash or leave as granular commits per preference**
