/**
 * Ingredient Tree Chart - Radial tree visualization of ingredient hierarchy
 */

import { createTouchHandlers, isTouchDevice, isMobileViewport } from '../utils/touchInteraction.js';

/**
 * Get a CSS variable value from the document
 * @param {string} varName - CSS variable name (with or without --)
 * @param {string} fallback - Fallback value if variable not found
 * @returns {string} The CSS variable value or fallback
 */
function getCSSVariable(varName, fallback) {
    const name = varName.startsWith('--') ? varName : `--${varName}`;
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
}

/**
 * Color constants - reads from CSS variables for consistency across the website
 * Falls back to hardcoded values if CSS variables aren't available
 *
 * CSS Variables Used:
 * --primary-color: #2c3e50 (dark blue-gray, used for leaf nodes)
 * --accent-color: #A61816 (red, used for nodes with children)
 * --secondary-color: #7f8c8d (gray, used for strokes and links)
 *
 * Note: Update analytics.html legend colors if you change these values
 */
function getColors() {
    return {
        // Node fill colors
        leafFill: getCSSVariable('--primary-color', '#2c3e50'),     // Primary color for leaf nodes
        internalFill: getCSSVariable('--accent-color', '#A61816'),  // Accent color for nodes with children
        hoverFill: 'rgba(166, 24, 22, 0.8)',                        // Slightly transparent accent on hover

        // Stroke colors - same for all nodes
        stroke: getCSSVariable('--secondary-color', '#7f8c8d'),     // Gray stroke for all nodes
        hoverStroke: '#5a6163',                                      // Darker gray on hover

        // Other colors
        linkStroke: getCSSVariable('--secondary-color', '#7f8c8d'), // Gray for links
        textFill: getCSSVariable('--text-dark', '#333'),     // Dark text for visibility on light background
        tooltipBg: 'rgba(44, 62, 80, 0.95)',                        // Dark tooltip background
        svgBg: getCSSVariable('--bg-light', '#f5f5f5')                                         // Light gray background
    };
}

const TOUCH_HINT_KEY = 'ingredientTreeTouchHintShown';

/**
 * Create a radial tree chart showing ingredient hierarchy with recipe counts
 * @param {HTMLElement} container - Container element for the chart
 * @param {Object} data - Tree data from API
 * @param {Object} options - Chart options
 */
export function createIngredientTreeChart(container, data, options = {}) {
    // Clear container
    container.innerHTML = '';

    // Get colors from CSS variables
    const COLORS = getColors();

    // Detect mobile viewport
    const isMobile = window.innerWidth < 768;
    const isTouch = isTouchDevice();

    // Configuration constants - responsive sizing for mobile
    const FONT_SIZE_PARENT = isMobile ? '4px' : '8px';
    const FONT_SIZE_OUTERMOST = isMobile ? '6px' : '11px';
    const CIRCLE_RADIUS = isMobile ? 2 : 5;
    const STROKE_WIDTH = isMobile ? 1 : 2;
    const STROKE_WIDTH_HOVER = isMobile ? 1.5 : 3;
    const MAX_LENGTH_PARENT = 15;
    const MAX_LENGTH_OUTERMOST = Infinity;
    const RING_SPACING = 1.2;

    // Get container dimensions
    const containerRect = container.getBoundingClientRect();
    const width = containerRect.width || 800;
    const height = Math.max(containerRect.height || 600, 600);
    const radius = Math.min(width, height) / 2 - 120;

    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .attr('class', 'ingredient-tree-svg');

    const g = svg.append('g');

    // Make container position relative for tooltip positioning
    container.style.position = 'relative';

    // Create tooltip
    const tooltip = d3.select(container)
        .append('div')
        .attr('class', 'tree-tooltip')
        .style('position', 'absolute')
        .style('pointer-events', 'none')
        .style('background-color', COLORS.tooltipBg)
        .style('color', '#ffffff')
        .style('padding', '10px 14px')
        .style('border-radius', '6px')
        .style('font-size', '13px')
        .style('z-index', '1000')
        .style('opacity', '0')
        .style('transition', 'opacity 0.2s')
        .style('white-space', 'nowrap')
        .style('box-shadow', '0 2px 8px rgba(0,0,0,0.3)')
        .style('border', '1px solid rgba(166, 24, 22, 0.3)');

    // Create tree layout
    const tree = d3.tree()
        .size([2 * Math.PI, radius])
        .separation((a, b) => {
            const baseSep = a.parent == b.parent ? 1.5 : 3;
            return baseSep / Math.max(1, a.depth * 0.8);
        });

    // Create root hierarchy
    const root = d3.hierarchy(data);

    // Collapse all children except root
    root.children.forEach(collapse);

    function collapse(d) {
        if (d.children) {
            d._children = d.children;
            d._children.forEach(collapse);
            d.children = null;
        }
    }

    // Update function
    function update(source) {
        const duration = 500;

        // Compute the new tree layout
        const nodes = tree(root);
        const links = nodes.links();

        // Update nodes
        const node = g.selectAll('.node')
            .data(nodes.descendants(), d => d.data.id || d.data.name);

        // Enter new nodes
        const nodeEnter = node.enter().append('g')
            .attr('class', d => 'node' + (d.children || d._children ? ' node--internal' : ' node--leaf'))
            .attr('transform', d => `translate(${radialPoint(d.x, d.y)})`)
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

        nodeEnter.append('circle')
            .attr('r', 0);

        const textEnter = nodeEnter.append('text')
            .attr('dy', '0.31em')
            .attr('x', d => d.x < Math.PI === !d.children ? 6 : -6)
            .attr('text-anchor', d => d.x < Math.PI === !d.children ? 'start' : 'end')
            .attr('transform', d => `rotate(${(d.x < Math.PI ? d.x - Math.PI / 2 : d.x + Math.PI / 2) * 180 / Math.PI})`)
            .text(d => truncateText(d))
            .style('font-size', d => getFontSize(d))
            .style('opacity', 0)
            .style('display', d => shouldShowLabel(d) ? 'block' : 'none');

        // Update existing nodes with tooltip handlers (desktop only)
        if (!isTouch) {
            node.on('mouseover', function(event, d) {
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

        // Transition existing nodes
        node.transition()
            .duration(duration)
            .attr('transform', d => `translate(${radialPoint(d.x, d.y)})`);

        node.select('circle')
            .transition()
            .duration(duration)
            .attr('r', CIRCLE_RADIUS);

        node.select('text')
            .text(d => truncateText(d))
            .style('font-size', d => getFontSize(d))
            .style('display', d => shouldShowLabel(d) ? 'block' : 'none')
            .transition()
            .duration(duration)
            .style('opacity', 1)
            .attr('x', d => d.x < Math.PI === !d.children ? 6 : -6)
            .attr('text-anchor', d => d.x < Math.PI === !d.children ? 'start' : 'end')
            .attr('transform', d => `rotate(${(d.x < Math.PI ? d.x - Math.PI / 2 : d.x + Math.PI / 2) * 180 / Math.PI})`);

        // Transition new nodes with delay
        nodeEnter.transition()
            .delay(duration)
            .duration(duration)
            .attr('transform', d => `translate(${radialPoint(d.x, d.y)})`);

        nodeEnter.select('circle')
            .transition()
            .delay(duration)
            .duration(duration)
            .attr('r', CIRCLE_RADIUS);

        nodeEnter.select('text')
            .transition()
            .delay(duration)
            .duration(duration)
            .style('opacity', 1);

        // Exit old nodes
        const nodeExit = node.exit().transition()
            .duration(duration)
            .remove();

        nodeExit.select('circle')
            .attr('r', 0);

        nodeExit.select('text')
            .style('opacity', 0);

        // Update links
        const link = g.selectAll('.link')
            .data(links, d => d.target.data.id || d.target.data.name);

        // Enter new links
        const linkEnter = link.enter().insert('path', 'g')
            .attr('class', 'link')
            .attr('d', linkRadial)
            .style('opacity', 0);

        // Transition existing links
        link.transition()
            .duration(duration)
            .attr('d', linkRadial);

        // Transition new links
        linkEnter.transition()
            .delay(duration)
            .duration(duration)
            .style('opacity', 0.6)
            .attr('d', linkRadial);

        // Exit old links
        link.exit().transition()
            .duration(duration)
            .style('opacity', 0)
            .remove();
    }

    // Helper functions
    function radialPoint(x, y) {
        y = (+y) * RING_SPACING;
        return [y * Math.cos(x -= Math.PI / 2), y * Math.sin(x)];
    }

    function linkRadial(d) {
        return d3.linkRadial()
            .angle(d => d.x)
            .radius(d => d.y * RING_SPACING)
            (d);
    }

    function truncateText(d) {
        const hasSiblingWithExpandedChildren = d.parent && d.parent.children &&
            d.parent.children.some(sibling => sibling.children && sibling.children.length > 0);
        const shouldBeSmall = hasSiblingWithExpandedChildren;
        const maxLength = shouldBeSmall ? MAX_LENGTH_PARENT : MAX_LENGTH_OUTERMOST;
        return d.data.name.length > maxLength ? d.data.name.substring(0, maxLength) + '...' : d.data.name;
    }

    function getFontSize(d) {
        const hasSiblingWithExpandedChildren = d.parent && d.parent.children &&
            d.parent.children.some(sibling => sibling.children && sibling.children.length > 0);
        return hasSiblingWithExpandedChildren ? FONT_SIZE_PARENT : FONT_SIZE_OUTERMOST;
    }

    function shouldShowLabel(d) {
        if (d.depth === 0) return false; // Hide root
        return true; // Show all other labels
    }

    function clicked(event, d) {
        if (d.children) {
            d._children = d.children;
            d.children = null;
        } else {
            d.children = d._children;
            d._children = null;
        }
        update(d);
    }

    // Initial render
    update(root);

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

    // Initialize zoom with center translation
    svg.call(zoom)
        .call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2));

    // Show touch hint on mobile (first time only)
    if (isTouch && !localStorage.getItem(TOUCH_HINT_KEY)) {
        showTouchHint(container);
        localStorage.setItem(TOUCH_HINT_KEY, 'true');
    }

    // Add CSS styles
    addTreeStyles(COLORS, STROKE_WIDTH, STROKE_WIDTH_HOVER);
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

    requestAnimationFrame(() => {
        hint.classList.add('visible');
    });

    setTimeout(() => {
        hint.classList.remove('visible');
        setTimeout(() => hint.remove(), 300);
    }, 3000);
}

function addTreeStyles(COLORS, strokeWidth, strokeWidthHover) {
    // Check if styles already exist
    if (document.getElementById('ingredient-tree-styles')) {
        return;
    }

    const style = document.createElement('style');
    style.id = 'ingredient-tree-styles';
    style.textContent = `
        .ingredient-tree-svg {
            background-color: ${COLORS.svgBg};
        }

        /* Leaf nodes (no children) - use primary color */
        .node.node--leaf circle {
            fill: ${COLORS.leafFill};
            stroke: ${COLORS.stroke};
            stroke-width: ${strokeWidth}px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .node.node--leaf circle:hover {
            fill: ${COLORS.leafFill};
            stroke: ${COLORS.hoverStroke};
            stroke-width: ${strokeWidthHover}px;
        }

        /* Internal nodes (have children) - use accent color */
        .node.node--internal circle {
            fill: ${COLORS.internalFill};
            stroke: ${COLORS.stroke};
            stroke-width: ${strokeWidth}px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .node.node--internal circle:hover {
            fill: ${COLORS.hoverFill};
            stroke: ${COLORS.hoverStroke};
            stroke-width: ${strokeWidthHover}px;
        }

        .node text {
            font-size: 12px;
            fill: ${COLORS.textFill};
            pointer-events: none;
        }

        .link {
            fill: none;
            stroke: ${COLORS.linkStroke};
            stroke-width: 1.5px;
            stroke-opacity: 0.6;
        }
    `;
    document.head.appendChild(style);
}
