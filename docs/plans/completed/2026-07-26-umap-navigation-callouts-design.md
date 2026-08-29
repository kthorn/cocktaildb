# UMAP Navigation and Recipe Callouts

## Goal

Improve navigation in both cocktail-space UMAP charts and make recipe names readable when zooming into a small region.

## Approved behavior

- Increase the D3 zoom maximum from `10` to `50`.
- A point is visible when its transformed position is inside the chart plot area (the same clipped area used by the existing circles).
- During initial render and every zoom/pan update, count visible points.
- When 20 or fewer points are visible, show one SVG callout containing each point's `recipe_name`.
- When more than 20 points are visible, remove all callouts.
- Callouts remain attached to their points as the user zooms and pans.
- Callouts are non-interactive (`pointer-events: none`) so existing hover, touch, and click behavior is unchanged.
- Existing hover preview cards and click-to-open recipe modal remain unchanged.

## Implementation

Change `src/web/js/charts/cocktailSpaceChart.js`:

1. Add a dedicated SVG text layer in the chart's clipped group for callouts.
2. Add a small helper to calculate transformed point positions and render/remove callouts based on the 20-point threshold.
3. Invoke that helper after initial point positioning and from the existing `zoom` handler.
4. Change the zoom scale extent to `[0.5, 50]`.
5. Keep the existing circle and highlight-ring coordinate updates intact.

Change `src/web/styles.css` only as needed for readable callout text (font size, fill, weight, and a contrasting text outline/background treatment). Avoid introducing an HTML overlay or a new dependency.

## Data flow

The chart already receives `{ recipe_id, recipe_name, x, y }` objects. The chart's existing x/y scales convert UMAP coordinates to plot coordinates, and the D3 zoom transform converts those positions into current viewport positions. The callout helper uses those same transformed coordinates, filters to the plot bounds, and binds the visible data to SVG text elements. Re-rendering the small selection on each zoom event keeps labels synchronized without changing API data.

## Testing

Add a focused test under `tests/` that checks the chart source/behavior contract:

- zoom maximum is 50;
- callouts use the visible-point threshold of 20;
- callouts are updated on zoom and removed when the visible count exceeds 20.

Run the focused test first in red before implementation, then run it green and execute the applicable repository test suite. Run diagnostics on edited JavaScript/CSS files before final verification.

## Out of scope

- Backend/API changes.
- Changes to UMAP coordinates or data generation.
- New label collision-avoidance algorithms.
- Changes to existing hover previews, recipe modal behavior, or touch gesture semantics.
