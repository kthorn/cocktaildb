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
