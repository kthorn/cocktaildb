# Analytics Mobile Touch & Proportions Fix

**Date:** 2025-12-25
**Issue:** bd-23 - Analytics graph proportions not ideal on mobile

## Problem Statement

Three issues with analytics visualizations on mobile:
1. Ingredient usage bar chart is tall and skinny
2. Tap to select doesn't work on iOS for ingredient tree and UMAPs
3. Mouseover on UMAP doesn't work on iOS - conflicts with pan/zoom

## Design

### 1. Ingredient Usage Chart - Responsive Sizing

**Changes to `ingredientUsageChart.js`:**

1. **Detect mobile** at chart creation (`window.innerWidth < 768`)

2. **Responsive dimensions:**
   - Mobile: left margin 120px (truncate long names), bar height 24px
   - Desktop: keep current 200px margin, 30px bar height

3. **Smart truncation:**
   - If >20 ingredients on mobile, show top 15 with "Show all X ingredients" link below
   - Clicking expands to full list (re-renders chart)

4. **Label truncation:**
   - Mobile: max 12 characters + ellipsis
   - Desktop: max 20 characters + ellipsis
   - Full name shown in tooltip

### 2. Unified Touch Interaction Pattern

**Applies to:** All three chart types (ingredient usage, ingredient tree, UMAP/cocktail space)

**Touch gesture mapping:**

| Gesture | Action |
|---------|--------|
| Single tap | Show tooltip (ingredient info or recipe preview) |
| Double tap | Trigger action (drill-down, expand node, or open recipe modal) |
| Two-finger pan | Pan the chart (UMAP/tree only) |
| Pinch | Zoom in/out (UMAP/tree only) |

**Implementation approach:**

1. **Create shared touch handler utility** (`src/web/js/utils/touchInteraction.js`):
   - Tracks tap timing to distinguish single vs double tap
   - 300ms threshold for double-tap detection
   - Exposes `onTap(callback)` and `onDoubleTap(callback)` for each element

2. **Preserve mouse behavior on desktop:**
   - Keep existing `mouseenter/mouseleave` for hover tooltips
   - Keep existing `click` for actions
   - Touch handlers only active on touch devices

3. **Tooltip persistence on mobile:**
   - Tap shows tooltip, stays visible until tap elsewhere or 3 second timeout
   - Desktop: tooltip follows mouse / disappears on mouseout

### 3. Two-Finger Pan/Zoom for UMAP Charts

**Applies to:** Cocktail Space (Manhattan), Cocktail Space (EM), and Ingredient Tree charts

**Changes to `cocktailSpaceChart.js` and `ingredientTreeChart.js`:**

1. **D3 zoom filter** - only start zoom gestures on multi-touch:
   ```javascript
   const zoom = d3.zoom()
       .filter((event) => {
           if (event.type.startsWith('touch')) {
               return event.touches.length >= 2;
           }
           return true; // allow mouse events
       })
   ```

2. **CSS touch-action** - let browser handle single-finger scroll:
   ```css
   #cocktail-space-chart svg,
   #cocktail-space-em-chart svg,
   #ingredient-tree-chart svg {
       touch-action: pan-y pinch-zoom;
   }
   ```

3. **Visual hint on mobile** - small overlay text on first visit:
   - "Pinch to zoom - Two fingers to pan"
   - Fades out after 3 seconds or first interaction
   - Stored in localStorage so only shown once

### 4. Ingredient Tree Chart Adjustments

**Changes to `ingredientTreeChart.js`:**

1. **Apply same zoom filter** as UMAP charts (two-finger only on touch)

2. **Touch interaction for nodes:**
   - Single tap: show tooltip with recipe counts
   - Double tap: expand/collapse node (currently just `click`)

3. **Tooltip positioning on mobile:**
   - Currently positions relative to mouse cursor
   - On touch: position above/below the tapped node (not finger position)
   - Ensure tooltip doesn't overflow viewport

## Files to Modify

- `src/web/js/charts/ingredientUsageChart.js` - responsive sizing, label truncation, touch handlers
- `src/web/js/charts/cocktailSpaceChart.js` - two-finger zoom, touch handlers
- `src/web/js/charts/ingredientTreeChart.js` - two-finger zoom, touch handlers
- `src/web/styles.css` - touch-action CSS rules

## New Files

- `src/web/js/utils/touchInteraction.js` - shared tap/double-tap detection utility

## Testing

- Test on iOS Safari (primary target for touch issues)
- Test on Android Chrome
- Verify desktop mouse behavior unchanged
- Test with various ingredient counts (5, 20, 50+)
