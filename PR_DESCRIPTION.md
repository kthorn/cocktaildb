## Summary

Add lightweight recipe preview card that appears on hover in Cocktail Space visualization, showing recipe name and sorted ingredient list for quick context without requiring a click to open the full modal.

**Key Features:**
- 250ms hover delay prevents accidental popups during mouse movement
- Shows recipe name + first 6 ingredients sorted by volume (descending)
- Smart positioning with edge detection (never goes off-screen)
- Click-through behavior preserves ability to click data points and open modal
- Hides during zoom/pan for clean interactions

**Architecture:**
- Backend: Extended `compute_cocktail_space_umap()` to include sorted ingredient lists using SQL-based volume conversion
- Frontend: New `RecipePreviewCard` component with debounced hover and smart positioning
- Integration: Replaced simple tooltip in cocktail space chart with preview card

## Changes from Design

**Improvements made during implementation:**
- **SQL-based conversion**: Moved unit conversion logic from Python to SQL CASE statement for better performance and maintainability
- **Modified existing method**: Extended `compute_cocktail_space_umap()` directly instead of creating separate method
- **XSS protection**: Uses DOM methods (`textContent`) instead of `innerHTML` for safe rendering
- **Batch queries**: Single efficient query using `IN` clause to fetch all recipe ingredients

## Test Plan

- [x] Backend: SQL query correctly sorts ingredients by volume with special unit handling (to top, to rinse, each)
- [x] Frontend: Preview appears after 250ms hover delay
- [x] Frontend: Smart positioning works at all screen edges (flips to stay visible)
- [x] Frontend: Quick mouse movements don't trigger preview (debounce works)
- [x] Frontend: Click on points opens modal, preview hides
- [x] Frontend: Preview hides during zoom/pan interactions
- [x] Security: XSS vulnerability fixed (uses textContent not innerHTML)
- [ ] Integration: Deploy to dev and verify with real data (analytics needs refresh)

## Known Issues

- **Pre-existing test failures** (tracked in bd-67): 5 unrelated tests failing (substitution booleans, search) - not caused by this feature
- **First commit includes unrelated changes**: Mobile analytics and barcart UMAP changes were pre-existing uncommitted work that got picked up

## Files Changed

**Backend (2 files):**
- `api/db/db_analytics.py` - Added ingredient lists to UMAP analytics
- `api/analytics/analytics_refresh.py` - Handle new dict return format

**Frontend (4 files):**
- `src/web/js/components/recipePreviewCard.js` - New preview card component (147 lines)
- `src/web/js/charts/cocktailSpaceChart.js` - Integration with chart
- `src/web/styles.css` - Preview card styles
- `docs/plans/2025-11-29-cocktail-space-recipe-preview-design.md` - Implementation notes

## Deployment Notes

After merging:
1. Deploy backend changes
2. Trigger analytics refresh: `./scripts/trigger-analytics-refresh.sh [dev|prod]`
3. Wait ~60s for analytics to regenerate with ingredient data
4. Verify preview cards show ingredients in Cocktail Space tab

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
