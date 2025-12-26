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
