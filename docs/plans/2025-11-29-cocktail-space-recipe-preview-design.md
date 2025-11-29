# Cocktail Space Recipe Preview Card

**Date:** 2025-11-29
**Status:** Approved
**Author:** Design brainstorming session

## Overview

Add a lightweight recipe preview card that appears on hover in the Cocktail Space visualization. The preview shows recipe name and ingredient list, providing quick context without requiring a click to open the full modal.

## Design Decisions

### Scope
- **Target:** Cocktail Space view only
- **Content:** Recipe name + ingredient names (no amounts/units)
- **Interaction:** Two-level detail system
  - Hover → lightweight preview
  - Click → full modal (unchanged)

### User Experience

**Hover Behavior:**
- 250ms delay before preview appears
- Prevents popups during casual mouse movement
- Cancels if mouse leaves before delay completes

**Visual Design:**
- White background with red `--accent-color` border
- Matches recipe card styling
- No animations (instant show/hide)
- `pointer-events: none` for click-through

**Positioning:**
- Anchored to data point (not cursor)
- Smart edge detection:
  - Near right edge → flip left
  - Near bottom → flip top
  - 10-15px offset from circle

**Ingredient Display:**
- Show first 6 ingredients with bullet separators
- Format: "Gin • Vodka • Lime Juice • ..."
- If more than 6: append "..."
- `MAX_PREVIEW_INGREDIENTS = 6` (configurable constant)

### Data Architecture

**Single File Approach:**
- Extend existing `cocktail-space.json` analytics file
- Add `ingredients` array to each recipe object
- File size: ~400KB raw → ~120KB gzipped (acceptable)

**Data Structure:**
```json
{
  "data": [
    {
      "recipe_id": 123,
      "recipe_name": "Martini",
      "x": 5.7,
      "y": 2.3,
      "ingredients": ["Gin", "Dry Vermouth", "Orange Bitters"]
    }
  ]
}
```

**Why One File:**
- Single HTTP request (faster than two sequential)
- Data always in sync
- Simpler code, no race conditions
- Gzipped size is acceptable for modern web

## Implementation Plan

### Backend Changes

**File:** `api/analytics/analytics_refresh.py`
- Modify cocktail-space data generation to include ingredients

**File:** `api/db/db_analytics.py`
- Extend cocktail-space query to join ingredients
- **Critical: Ingredient Sorting Logic**
  - Convert all amounts to mL for consistent ordering
  - Special cases:
    - "to top" → 90 mL (3 oz equivalent)
    - "to rinse" → 5 mL
    - "each" units → sort to end (use -1 as sort value)
  - Apply unit conversion (oz/tbsp/tsp/dash → mL)
  - Sort DESC by converted amount
  - Return as simple string array

### Frontend Changes

**New File:** `src/web/js/components/recipePreviewCard.js`
- Export `createRecipePreviewCard()` function
- Constants:
  - `MAX_PREVIEW_INGREDIENTS = 6`
  - `HOVER_DELAY_MS = 250`
- Features:
  - Debounced hover detection
  - Smart positioning with edge detection
  - Ingredient truncation with "..."
  - Auto-hide on modal open

**Update File:** `src/web/js/charts/cocktailSpaceChart.js`
- Remove existing simple tooltip (lines 82-93, 118-144)
- Import and integrate `RecipePreviewCard` component
- Wire up hover handlers with debounce
- Handle preview visibility during zoom/pan

**Update File:** `src/web/styles.css`
- Add `.recipe-preview-card` styles:
  ```css
  .recipe-preview-card {
    position: absolute;
    background: white;
    border: 2px solid var(--accent-color);
    border-radius: 8px;
    padding: 12px 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    pointer-events: none;
    max-width: 300px;
    font-size: 14px;
  }

  .recipe-preview-card .recipe-name {
    font-weight: bold;
    margin-bottom: 8px;
    color: var(--text-color);
  }

  .recipe-preview-card .ingredients {
    color: var(--text-color-secondary);
    line-height: 1.5;
  }
  ```

## Edge Cases

1. **Very long ingredient names:** Use CSS `text-overflow: ellipsis` if needed
2. **Chart zoom/pan:** Hide preview during interactions, show on next hover
3. **Modal interaction:** Auto-hide preview when modal opens
4. **Empty ingredient list:** Not possible (recipes require ingredients)

## Testing Plan

1. **Backend:** Verify ingredient sorting handles all special cases
2. **Frontend:** Test with:
   - Recipes with 2-3 ingredients (no truncation)
   - Recipes with 10+ ingredients (with "...")
   - Hovering near edges (positioning logic)
   - Quick mouse movements (debounce behavior)
   - Zoom/pan interactions
   - Opening modal (preview hides)

## Performance

- **File size:** 400KB → 120KB gzipped
- **Network:** Single request, loaded once per session
- **Rendering:** No API calls on hover (data already available)
- **Memory:** Negligible (~400KB additional data in memory)

## Future Enhancements (Out of Scope)

- Extend to other analytics views (ingredient charts)
- Add visual indicators for ingredient categories
- Progressive disclosure (show more on longer hover)
- Keyboard navigation support

## Implementation Notes

**Completed:** 2025-11-29

**Changes from Design:**

1. **Conversion Logic Moved to SQL** (Major Improvement)
   - Original design: Python helper function `_convert_amount_to_ml()` in `db_analytics.py`
   - Actual implementation: SQL CASE statement directly in the ingredient query
   - Rationale: More efficient to compute conversions in database rather than Python
   - Impact: Cleaner code, better performance, easier to maintain
   - Location: `compute_cocktail_space_umap()` method, lines 251-259

2. **Modified Existing Method Instead of Separate Query**
   - Original design: New `get_cocktail_space_analytics()` method in `db_analytics.py`
   - Actual implementation: Extended existing `compute_cocktail_space_umap()` method
   - Rationale: Method already computed UMAP embeddings, natural place to add ingredient data
   - Impact: No duplicate code, single source of truth for cocktail space data

3. **Batch Ingredient Query**
   - Implementation added efficient batch query using `IN` clause with placeholders
   - Fetches all recipe ingredients in one query instead of per-recipe queries
   - Significantly better performance for large recipe collections

**Technical Details:**

- SQL CASE statement handles all special unit conversions:
  - "to top" → 90.0 mL (3 oz equivalent)
  - "to rinse" → 5.0 mL
  - "each" → -1.0 (sorts to end)
  - Standard units use `conversion_to_ml` from units table
- Ingredient sorting: DESC by volume_ml, with negative values at end
- Frontend component matches design spec exactly (no changes)

**Performance Observations:**

- Analytics file size: ~400KB raw JSON (as predicted)
- Gzipped size: ~120KB (matches design estimate)
- Hover delay (250ms): Feels natural, prevents accidental popups
- No noticeable performance impact on chart rendering or interactions
- Preview positioning works smoothly at all screen edges

**Known Issues:**

- None identified during testing
- All edge cases handled correctly:
  - Short ingredient lists (2-3 items) display without truncation
  - Long lists (10+ items) properly truncated with "..."
  - Smart positioning prevents off-screen rendering
  - Preview correctly hides during zoom/pan
  - Modal interaction properly dismisses preview

**Testing Completed:**

- ✅ Backend ingredient query returns sorted lists correctly
- ✅ Special unit conversions ("to top", "to rinse", "each") work as expected
- ✅ Analytics refresh generates new data format
- ✅ Preview appears after 250ms hover delay
- ✅ Smart edge detection prevents off-screen positioning
- ✅ Click-to-open-modal behavior preserved
- ✅ Zoom/pan interactions hide preview appropriately
- ✅ No console errors or warnings

**Commits:**

- `59c1dc5` - Backend: Add ingredient lists to cocktail space UMAP
- `1bbba77` - Frontend: Add recipe preview card component
- `b862440` - Frontend: Add recipe preview card styles
- `16e9d3d` - Frontend: Integrate recipe preview into cocktail space chart
