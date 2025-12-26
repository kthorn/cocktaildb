# Analytics Mobile Touch & Proportions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix analytics visualizations on mobile - responsive sizing for bar chart, tap/double-tap interactions for all charts, two-finger pan/zoom for UMAP and tree charts.

**Architecture:** Create shared touch utility for tap detection, apply to all three chart types. Use D3 zoom filter + CSS touch-action for two-finger gestures. Add responsive breakpoints for ingredient usage chart sizing.

**Tech Stack:** D3.js v7, vanilla JavaScript ES6 modules, CSS

---

## Task 1: Create Touch Interaction Utility

**Files:**
- Create: `src/web/js/utils/touchInteraction.js`

**Step 1: Create the utility module**

```javascript
/**
 * Touch Interaction Utility
 * Provides tap and double-tap detection for D3 chart elements
 */

const DOUBLE_TAP_THRESHOLD_MS = 300;
const TOOLTIP_TIMEOUT_MS = 3000;

/**
 * Creates touch handlers for a D3 selection
 * @param {Object} options
 * @param {Function} options.onTap - Called on single tap with (event, datum)
 * @param {Function} options.onDoubleTap - Called on double tap with (event, datum)
 * @returns {Object} Handler functions to attach to D3 selection
 */
export function createTouchHandlers(options = {}) {
    let lastTapTime = 0;
    let tapTimeout = null;
    let pendingTapData = null;

    function handleTouchStart(event, d) {
        // Prevent default to avoid 300ms click delay on mobile
        // But don't prevent if it's a two-finger gesture (for pan/zoom)
        if (event.touches && event.touches.length === 1) {
            const now = Date.now();
            const timeSinceLastTap = now - lastTapTime;

            if (timeSinceLastTap < DOUBLE_TAP_THRESHOLD_MS && pendingTapData === d) {
                // Double tap detected
                clearTimeout(tapTimeout);
                tapTimeout = null;
                pendingTapData = null;
                lastTapTime = 0;

                if (options.onDoubleTap) {
                    options.onDoubleTap(event, d);
                }
            } else {
                // Potential single tap - wait to see if double tap follows
                lastTapTime = now;
                pendingTapData = d;

                clearTimeout(tapTimeout);
                tapTimeout = setTimeout(() => {
                    if (options.onTap) {
                        options.onTap(event, d);
                    }
                    pendingTapData = null;
                }, DOUBLE_TAP_THRESHOLD_MS);
            }
        }
    }

    function handleTouchEnd(event) {
        // No-op for now, keeping for potential future use
    }

    return {
        touchstart: handleTouchStart,
        touchend: handleTouchEnd
    };
}

/**
 * Detect if device supports touch
 * @returns {boolean}
 */
export function isTouchDevice() {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

/**
 * Detect if viewport is mobile-sized
 * @returns {boolean}
 */
export function isMobileViewport() {
    return window.innerWidth < 768;
}

/**
 * Create a tooltip manager for mobile
 * Handles showing/hiding tooltips with timeout
 * @param {HTMLElement} tooltipElement - The tooltip DOM element
 * @returns {Object} Tooltip controller
 */
export function createMobileTooltipManager(tooltipElement) {
    let hideTimeout = null;

    function show(html, x, y) {
        clearTimeout(hideTimeout);

        tooltipElement.innerHTML = html;
        tooltipElement.style.left = `${x}px`;
        tooltipElement.style.top = `${y}px`;
        tooltipElement.style.opacity = '1';
        tooltipElement.style.visibility = 'visible';

        // Auto-hide after timeout on mobile
        if (isTouchDevice()) {
            hideTimeout = setTimeout(hide, TOOLTIP_TIMEOUT_MS);
        }
    }

    function hide() {
        clearTimeout(hideTimeout);
        tooltipElement.style.opacity = '0';
        tooltipElement.style.visibility = 'hidden';
    }

    // Hide tooltip when tapping elsewhere
    function setupDismissHandler() {
        document.addEventListener('touchstart', (event) => {
            if (!tooltipElement.contains(event.target)) {
                hide();
            }
        }, { passive: true });
    }

    return { show, hide, setupDismissHandler };
}
```

**Step 2: Commit**

```bash
git add src/web/js/utils/touchInteraction.js
git commit -m "feat: add touch interaction utility for mobile charts"
```

---

## Task 2: Add CSS Touch-Action Rules

**Files:**
- Modify: `src/web/styles.css` (append to analytics section around line 2810)

**Step 1: Add touch-action CSS rules**

Find the `#cocktail-space-chart` section (around line 2795) and add after it:

```css
/* Touch behavior for chart SVGs - allow native scroll, require two fingers for pan/zoom */
#cocktail-space-chart svg,
#cocktail-space-em-chart svg,
#ingredient-tree-chart svg {
    touch-action: pan-y pinch-zoom;
}

/* Mobile touch hint overlay */
.touch-hint {
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0, 0, 0, 0.7);
    color: white;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 12px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.3s ease;
    z-index: 100;
    white-space: nowrap;
}

.touch-hint.visible {
    opacity: 1;
}
```

**Step 2: Commit**

```bash
git add src/web/styles.css
git commit -m "feat: add touch-action CSS for mobile chart pan/zoom"
```

---

## Task 3: Update Ingredient Usage Chart - Responsive Sizing

**Files:**
- Modify: `src/web/js/charts/ingredientUsageChart.js`

**Step 1: Replace the entire file with responsive version**

```javascript
/**
 * Create an interactive ingredient usage bar chart using D3.js
 * Responsive design with mobile-optimized sizing and touch support
 *
 * @param {HTMLElement} container - DOM element to render chart into
 * @param {Array} data - Array of ingredient usage objects
 * @param {Object} options - Configuration options
 * @param {Function} options.onIngredientClick - Callback when ingredient is clicked
 */
import { createTouchHandlers, isTouchDevice, isMobileViewport } from '../utils/touchInteraction.js';

// Configuration constants
const CONFIG = {
    desktop: {
        marginLeft: 200,
        barHeight: 30,
        maxLabelLength: 20,
        maxIngredients: Infinity
    },
    mobile: {
        marginLeft: 120,
        barHeight: 24,
        maxLabelLength: 12,
        maxIngredients: 15
    }
};

export function createIngredientUsageChart(container, data, options = {}) {
    console.log('Creating ingredient usage chart with data:', data);

    // Clear container
    container.innerHTML = '';

    // Determine responsive settings
    const isMobile = isMobileViewport();
    const config = isMobile ? CONFIG.mobile : CONFIG.desktop;

    // Sort data by hierarchical_usage descending
    let sortedData = [...data].sort((a, b) => b.hierarchical_usage - a.hierarchical_usage);

    // Track if we're showing truncated data
    let isTruncated = false;
    let fullData = sortedData;

    // Truncate on mobile if too many ingredients
    if (isMobile && sortedData.length > config.maxIngredients) {
        isTruncated = true;
        sortedData = sortedData.slice(0, config.maxIngredients);
    }

    // Get dimensions
    const margin = { top: 20, right: 30, bottom: 40, left: config.marginLeft };
    const width = container.clientWidth - margin.left - margin.right;
    const height = Math.max(300, sortedData.length * config.barHeight) - margin.top - margin.bottom;

    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create scales
    const xScale = d3.scaleLinear()
        .domain([0, d3.max(sortedData, d => d.hierarchical_usage)])
        .range([0, width]);

    const yScale = d3.scaleBand()
        .domain(sortedData.map(d => d.ingredient_name))
        .range([0, height])
        .padding(0.1);

    // Create axes
    const xAxis = d3.axisBottom(xScale).ticks(5);
    const yAxis = d3.axisLeft(yScale)
        .tickFormat(name => truncateLabel(name, config.maxLabelLength));

    // Add X axis
    svg.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(xAxis)
        .append('text')
        .attr('x', width / 2)
        .attr('y', 35)
        .attr('fill', '#000')
        .attr('text-anchor', 'middle')
        .text('Number of Recipes');

    // Add Y axis
    svg.append('g')
        .call(yAxis);

    // Create tooltip
    const tooltip = d3.select(container)
        .append('div')
        .attr('class', 'chart-tooltip')
        .style('position', 'absolute')
        .style('visibility', 'hidden')
        .style('background-color', 'rgba(0, 0, 0, 0.8)')
        .style('color', 'white')
        .style('padding', '8px')
        .style('border-radius', '4px')
        .style('font-size', '12px')
        .style('pointer-events', 'none')
        .style('z-index', '1000');

    // Tooltip show/hide functions
    function showTooltip(event, d) {
        const containerRect = container.getBoundingClientRect();
        let x, y;

        if (event.touches) {
            // Touch event - position near the touch point
            x = event.touches[0].clientX - containerRect.left + 10;
            y = event.touches[0].clientY - containerRect.top - 10;
        } else {
            // Mouse event
            x = event.pageX - containerRect.left + 10;
            y = event.pageY - containerRect.top - 10;
        }

        tooltip.style('visibility', 'visible')
            .html(`
                <strong>${d.ingredient_name}</strong><br/>
                Direct usage: ${d.direct_usage}<br/>
                Total (with subtypes): ${d.hierarchical_usage}
            `)
            .style('left', x + 'px')
            .style('top', y + 'px');
    }

    function hideTooltip() {
        tooltip.style('visibility', 'hidden');
    }

    // Create touch handlers
    const touchHandlers = createTouchHandlers({
        onTap: (event, d) => {
            showTooltip(event, d);
            // Auto-hide after 3 seconds on touch
            setTimeout(hideTooltip, 3000);
        },
        onDoubleTap: (event, d) => {
            hideTooltip();
            if (d.has_children && options.onIngredientClick) {
                options.onIngredientClick(d);
            }
        }
    });

    // Create bars
    const bars = svg.selectAll('.bar')
        .data(sortedData)
        .enter()
        .append('rect')
        .attr('class', 'bar')
        .attr('x', 0)
        .attr('y', d => yScale(d.ingredient_name))
        .attr('width', d => xScale(d.hierarchical_usage))
        .attr('height', yScale.bandwidth())
        .attr('fill', d => d.has_children ? '#1f77b4' : '#aec7e8')
        .style('cursor', d => d.has_children ? 'pointer' : 'default');

    // Mouse events (desktop)
    if (!isTouchDevice()) {
        bars.on('mouseover', function(event, d) {
                d3.select(this).attr('fill', d.has_children ? '#1565c0' : '#90b8d8');
                showTooltip(event, d);
            })
            .on('mousemove', function(event, d) {
                showTooltip(event, d);
            })
            .on('mouseout', function(event, d) {
                d3.select(this).attr('fill', d.has_children ? '#1f77b4' : '#aec7e8');
                hideTooltip();
            })
            .on('click', function(event, d) {
                if (d.has_children && options.onIngredientClick) {
                    options.onIngredientClick(d);
                }
            });
    } else {
        // Touch events (mobile)
        bars.on('touchstart', function(event, d) {
                d3.select(this).attr('fill', d.has_children ? '#1565c0' : '#90b8d8');
                touchHandlers.touchstart(event, d);
            })
            .on('touchend', function(event, d) {
                d3.select(this).attr('fill', d.has_children ? '#1f77b4' : '#aec7e8');
            });
    }

    // Add "Show all" button if truncated
    if (isTruncated) {
        const showAllBtn = d3.select(container)
            .append('button')
            .attr('class', 'btn btn-secondary show-all-btn')
            .style('display', 'block')
            .style('margin', '16px auto')
            .text(`Show all ${fullData.length} ingredients`)
            .on('click', () => {
                // Re-render with full data
                const expandedConfig = { ...CONFIG.mobile, maxIngredients: Infinity };
                createIngredientUsageChart(container, data, options);
            });
    }

    // Hide tooltip when clicking elsewhere
    document.addEventListener('touchstart', (event) => {
        if (!container.contains(event.target)) {
            hideTooltip();
        }
    }, { passive: true });
}

/**
 * Truncate label text with ellipsis
 */
function truncateLabel(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 1) + '…';
}
```

**Step 2: Commit**

```bash
git add src/web/js/charts/ingredientUsageChart.js
git commit -m "feat: add responsive sizing and touch support to ingredient usage chart"
```

---

## Task 4: Update Cocktail Space Chart - Two-Finger Zoom + Touch

**Files:**
- Modify: `src/web/js/charts/cocktailSpaceChart.js`

**Step 1: Replace the entire file with touch-enabled version**

```javascript
import { createRecipePreviewCard } from '../components/recipePreviewCard.js';
import { createTouchHandlers, isTouchDevice, isMobileViewport } from '../utils/touchInteraction.js';

// =============================================================================
// Visual Configuration - Tweak these values to adjust appearance
// =============================================================================
const DOT_RADIUS = 5;
const DOT_RADIUS_HOVER = 7;
const DOT_FILL = 'steelblue';
const DOT_OPACITY = 0.4;
const DOT_OPACITY_HOVER = 0.8;
const DOT_STROKE = 'none';
const DOT_STROKE_WIDTH = 0;

const TOUCH_HINT_KEY = 'cocktailSpaceTouchHintShown';

/**
 * Creates an interactive D3.js scatter plot for cocktail space UMAP visualization
 * @param {HTMLElement} container - Container element for the chart
 * @param {Array} data - Array of {recipe_id, recipe_name, x, y} objects
 * @param {Object} options - Configuration options
 * @param {Function} options.onRecipeClick - Callback when recipe point is clicked: (recipeId, recipeName) => {}
 */
export function createCocktailSpaceChart(container, data, options = {}) {
    // Clear container
    container.innerHTML = '';

    const isMobile = isMobileViewport();
    const isTouch = isTouchDevice();

    // Set up dimensions
    const margin = { top: 60, right: 40, bottom: 60, left: 60 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = 600 - margin.top - margin.bottom;

    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom);

    const g = svg.append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Get data extents with padding
    const xExtent = d3.extent(data, d => d.x);
    const yExtent = d3.extent(data, d => d.y);
    const xPadding = (xExtent[1] - xExtent[0]) * 0.1;
    const yPadding = (yExtent[1] - yExtent[0]) * 0.1;

    // Create scales
    const xScale = d3.scaleLinear()
        .domain([xExtent[0] - xPadding, xExtent[1] + xPadding])
        .range([0, width]);

    const yScale = d3.scaleLinear()
        .domain([yExtent[0] - yPadding, yExtent[1] + yPadding])
        .range([height, 0]);

    // Create clip path for zoom
    svg.append('defs')
        .append('clipPath')
        .attr('id', 'clip')
        .append('rect')
        .attr('width', width)
        .attr('height', height);

    // Create recipe preview card
    const previewCard = createRecipePreviewCard(document.body);

    // Add circles for data points
    const circles = g.append('g')
        .attr('clip-path', 'url(#clip)')
        .selectAll('circle')
        .data(data)
        .enter()
        .append('circle');

    circles
        .attr('cx', d => xScale(d.x))
        .attr('cy', d => yScale(d.y))
        .attr('r', DOT_RADIUS)
        .attr('fill', DOT_FILL)
        .attr('stroke', DOT_STROKE)
        .attr('stroke-width', DOT_STROKE_WIDTH)
        .attr('opacity', DOT_OPACITY)
        .style('cursor', 'pointer');

    // Track current zoom transform for touch handlers
    let currentTransform = d3.zoomIdentity;

    // Create touch handlers for tap/double-tap
    const touchHandlers = createTouchHandlers({
        onTap: (event, d) => {
            // Show preview card at touch position
            const touch = event.changedTouches ? event.changedTouches[0] : event.touches[0];
            previewCard.show(d, touch.pageX, touch.pageY);

            // Highlight the circle
            circles.attr('opacity', DOT_OPACITY);
            d3.select(event.target)
                .attr('r', DOT_RADIUS_HOVER)
                .attr('opacity', DOT_OPACITY_HOVER);
        },
        onDoubleTap: (event, d) => {
            previewCard.hide();
            if (options.onRecipeClick) {
                options.onRecipeClick(d.recipe_id, d.recipe_name);
            }
        }
    });

    if (!isTouch) {
        // Mouse events (desktop)
        circles
            .on('mouseenter', function(event, d) {
                d3.select(this)
                    .transition()
                    .duration(200)
                    .attr('r', DOT_RADIUS_HOVER)
                    .attr('opacity', DOT_OPACITY_HOVER);

                previewCard.startHover(d, event.pageX, event.pageY);
            })
            .on('mouseleave', function() {
                d3.select(this)
                    .transition()
                    .duration(200)
                    .attr('r', DOT_RADIUS)
                    .attr('opacity', DOT_OPACITY);

                previewCard.cancelHover();
            })
            .on('click', function(event, d) {
                previewCard.hide();
                if (options.onRecipeClick) {
                    options.onRecipeClick(d.recipe_id, d.recipe_name);
                }
            });
    } else {
        // Touch events (mobile)
        circles
            .on('touchstart', function(event, d) {
                // Only handle single-finger touch for tap detection
                if (event.touches.length === 1) {
                    event.preventDefault(); // Prevent scroll on single tap
                    touchHandlers.touchstart(event, d);
                }
            })
            .on('touchend', function(event, d) {
                touchHandlers.touchend(event, d);
            });
    }

    // Add zoom behavior with two-finger filter for touch
    const zoom = d3.zoom()
        .scaleExtent([0.5, 10])
        .filter((event) => {
            // On touch devices, only allow zoom with 2+ fingers
            if (event.type.startsWith('touch')) {
                return event.touches.length >= 2;
            }
            // Allow all mouse events
            return true;
        })
        .on('zoom', (event) => {
            previewCard.hide();
            currentTransform = event.transform;

            circles
                .attr('cx', d => currentTransform.applyX(xScale(d.x)))
                .attr('cy', d => currentTransform.applyY(yScale(d.y)));
        });

    svg.call(zoom);

    // Add title
    svg.append('text')
        .attr('x', (width + margin.left + margin.right) / 2)
        .attr('y', margin.top / 2)
        .attr('text-anchor', 'middle')
        .attr('font-size', '18px')
        .attr('font-weight', 'bold')
        .text('Cocktail Space - Recipe Similarity Map');

    // Show touch hint on mobile (first time only)
    if (isTouch && !localStorage.getItem(TOUCH_HINT_KEY)) {
        showTouchHint(container);
        localStorage.setItem(TOUCH_HINT_KEY, 'true');
    }

    // Hide preview when tapping outside
    document.addEventListener('touchstart', (event) => {
        if (!container.contains(event.target)) {
            previewCard.hide();
            circles.attr('r', DOT_RADIUS).attr('opacity', DOT_OPACITY);
        }
    }, { passive: true });
}

/**
 * Show a hint overlay for touch gestures
 */
function showTouchHint(container) {
    const hint = document.createElement('div');
    hint.className = 'touch-hint';
    hint.textContent = 'Pinch to zoom · Two fingers to pan';
    container.style.position = 'relative';
    container.appendChild(hint);

    // Fade in
    requestAnimationFrame(() => {
        hint.classList.add('visible');
    });

    // Fade out after 3 seconds
    setTimeout(() => {
        hint.classList.remove('visible');
        setTimeout(() => hint.remove(), 300);
    }, 3000);
}
```

**Step 2: Update recipePreviewCard.js to add show() method**

The preview card needs a direct `show()` method (currently only has `startHover()`). Add this method to `src/web/js/components/recipePreviewCard.js` after the existing `show` function (around line 93):

Find and verify the existing `show` function is available in the public API. Looking at the file, `show` is already defined but not exported. Update the return object at the end (around line 148):

```javascript
    // Public API
    return {
        show,           // Add this - direct show without delay
        startHover,
        cancelHover,
        hide,
        isVisible: () => previewElement !== null
    };
```

**Step 3: Commit**

```bash
git add src/web/js/charts/cocktailSpaceChart.js src/web/js/components/recipePreviewCard.js
git commit -m "feat: add two-finger zoom and touch support to cocktail space chart"
```

---

## Task 5: Update Ingredient Tree Chart - Two-Finger Zoom + Touch

**Files:**
- Modify: `src/web/js/charts/ingredientTreeChart.js`

**Step 1: Add imports at the top of the file (after line 1)**

```javascript
import { createTouchHandlers, isTouchDevice, isMobileViewport } from '../utils/touchInteraction.js';
```

**Step 2: Add touch hint constant after getColors function (around line 45)**

```javascript
const TOUCH_HINT_KEY = 'ingredientTreeTouchHintShown';
```

**Step 3: Modify the createIngredientTreeChart function**

After the line `const isMobile = window.innerWidth < 768;` (around line 61), add:

```javascript
    const isTouch = isTouchDevice();
```

**Step 4: Update the node event handlers**

Find the `nodeEnter` creation (around line 144) and replace the event handlers. Replace from `.on('click', clicked)` through `.on('mousemove', ...)` with:

```javascript
            .on('click', function(event, d) {
                // Desktop click - expand/collapse
                if (!isTouch) {
                    clicked(event, d);
                }
            });

        // Add touch handlers for mobile
        if (isTouch) {
            const touchHandlers = createTouchHandlers({
                onTap: (event, d) => {
                    // Show tooltip
                    const directCount = d.data.recipe_count || 0;
                    const hierarchicalCount = d.data.hierarchical_recipe_count || 0;
                    const hasChildren = d.children || d._children;

                    let tooltipHtml = `<strong>${d.data.name}</strong><br/>`;
                    tooltipHtml += `Direct: ${directCount} recipe${directCount !== 1 ? 's' : ''}`;
                    if (hasChildren) {
                        tooltipHtml += `<br/>With children: ${hierarchicalCount} recipe${hierarchicalCount !== 1 ? 's' : ''}`;
                    }

                    // Position tooltip near the node, not the finger
                    const [nodeX, nodeY] = radialPoint(d.x, d.y);
                    const svgRect = svg.node().getBoundingClientRect();
                    const transform = g.attr('transform');
                    // Parse transform to get current translation
                    const match = transform.match(/translate\(([^,]+),([^)]+)\)/);
                    const tx = match ? parseFloat(match[1]) : width / 2;
                    const ty = match ? parseFloat(match[2]) : height / 2;

                    const tooltipX = nodeX + tx + 10;
                    const tooltipY = nodeY + ty - 10;

                    tooltip
                        .html(tooltipHtml)
                        .style('left', tooltipX + 'px')
                        .style('top', tooltipY + 'px')
                        .style('opacity', '1');

                    // Auto-hide after 3 seconds
                    setTimeout(() => tooltip.style('opacity', '0'), 3000);
                },
                onDoubleTap: (event, d) => {
                    tooltip.style('opacity', '0');
                    clicked(event, d);
                }
            });

            nodeEnter
                .on('touchstart', function(event, d) {
                    if (event.touches.length === 1) {
                        event.preventDefault();
                        touchHandlers.touchstart(event, d);
                    }
                });
        } else {
            // Mouse hover handlers for desktop
            nodeEnter
                .on('mouseover', function(event, d) {
                    const directCount = d.data.recipe_count || 0;
                    const hierarchicalCount = d.data.hierarchical_recipe_count || 0;
                    const hasChildren = d.children || d._children;

                    let tooltipHtml = `<strong>${d.data.name}</strong><br/>`;
                    tooltipHtml += `Direct: ${directCount} recipe${directCount !== 1 ? 's' : ''}`;
                    if (hasChildren) {
                        tooltipHtml += `<br/>With children: ${hierarchicalCount} recipe${hierarchicalCount !== 1 ? 's' : ''}`;
                    }

                    const rect = container.getBoundingClientRect();
                    tooltip
                        .html(tooltipHtml)
                        .style('left', (event.clientX - rect.left + 10) + 'px')
                        .style('top', (event.clientY - rect.top - 10) + 'px')
                        .style('opacity', '1');
                })
                .on('mouseout', function() {
                    tooltip.style('opacity', '0');
                })
                .on('mousemove', function(event) {
                    const rect = container.getBoundingClientRect();
                    tooltip
                        .style('left', (event.clientX - rect.left + 10) + 'px')
                        .style('top', (event.clientY - rect.top - 10) + 'px');
                });
        }
```

**Step 5: Update the zoom behavior**

Find the zoom behavior creation (around line 348) and replace with:

```javascript
    // Add zoom behavior with two-finger filter for touch
    const zoom = d3.zoom()
        .scaleExtent([0.5, 3])
        .filter((event) => {
            // On touch devices, only allow zoom with 2+ fingers
            if (event.type.startsWith('touch')) {
                return event.touches.length >= 2;
            }
            return true;
        })
        .on('zoom', (event) => {
            tooltip.style('opacity', '0'); // Hide tooltip during zoom
            g.attr('transform', event.transform);
        });
```

**Step 6: Add touch hint after initial render**

After the line `svg.call(zoom).call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2));` (around line 356), add:

```javascript
    // Show touch hint on mobile (first time only)
    if (isTouch && !localStorage.getItem(TOUCH_HINT_KEY)) {
        showTouchHint(container);
        localStorage.setItem(TOUCH_HINT_KEY, 'true');
    }
```

**Step 7: Add showTouchHint function before addTreeStyles function**

```javascript
/**
 * Show a hint overlay for touch gestures
 */
function showTouchHint(container) {
    const hint = document.createElement('div');
    hint.className = 'touch-hint';
    hint.textContent = 'Pinch to zoom · Two fingers to pan';
    container.style.position = 'relative';
    container.appendChild(hint);

    requestAnimationFrame(() => {
        hint.classList.add('visible');
    });

    setTimeout(() => {
        hint.classList.remove('visible');
        setTimeout(() => hint.remove(), 300);
    }, 3000);
}
```

**Step 8: Commit**

```bash
git add src/web/js/charts/ingredientTreeChart.js
git commit -m "feat: add two-finger zoom and touch support to ingredient tree chart"
```

---

## Task 6: Manual Testing

**Step 1: Test on desktop browser**

1. Open analytics page
2. Verify ingredient usage chart hover tooltips work
3. Verify click drills down on items with children
4. Verify cocktail space hover preview appears after delay
5. Verify cocktail space click opens recipe modal
6. Verify ingredient tree hover tooltips work
7. Verify tree node click expands/collapses

**Step 2: Test on iOS Safari (or use Chrome DevTools mobile emulation)**

1. Enable touch emulation in Chrome DevTools (Toggle device toolbar)
2. Test ingredient usage chart:
   - Tap shows tooltip
   - Double-tap drills down
   - Chart fits viewport width
   - "Show all" appears if >15 ingredients
3. Test cocktail space:
   - Single-finger scroll scrolls the page (not the chart)
   - Tap on dot shows recipe preview
   - Double-tap opens recipe modal
   - Two-finger pinch zooms the chart
   - Two-finger drag pans the chart
   - Touch hint appears on first visit
4. Test ingredient tree:
   - Same touch behaviors as cocktail space

**Step 3: Update issue status**

```bash
bd update bd-23 --status closed --notes "Implementation complete. Responsive sizing, tap/double-tap touch, two-finger pan/zoom all working."
```

**Step 4: Final commit with all changes verified**

```bash
git status
# Verify no uncommitted changes
```

---

## Summary

| Task | Files | Purpose |
|------|-------|---------|
| 1 | `utils/touchInteraction.js` | Shared tap/double-tap detection |
| 2 | `styles.css` | CSS touch-action rules |
| 3 | `ingredientUsageChart.js` | Responsive sizing + touch |
| 4 | `cocktailSpaceChart.js` | Two-finger zoom + touch |
| 5 | `ingredientTreeChart.js` | Two-finger zoom + touch |
| 6 | Manual testing | Verify all behaviors |
