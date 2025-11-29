import { createRecipePreviewCard } from '../components/recipePreviewCard.js';

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
        .attr('r', 6)
        .attr('fill', 'steelblue')
        .attr('stroke', 'white')
        .attr('stroke-width', 1)
        .attr('opacity', 0.7)
        .style('cursor', 'pointer')
        .on('mouseenter', function(event, d) {
            // Enlarge circle
            d3.select(this)
                .transition()
                .duration(200)
                .attr('r', 8)
                .attr('opacity', 1);

            // Start preview card hover timer
            previewCard.startHover(d, event.pageX, event.pageY);
        })
        .on('mouseleave', function() {
            // Restore circle size
            d3.select(this)
                .transition()
                .duration(200)
                .attr('r', 6)
                .attr('opacity', 0.7);

            // Cancel preview
            previewCard.cancelHover();
        })
        .on('click', function(event, d) {
            // Hide preview and trigger modal
            previewCard.hide();
            if (options.onRecipeClick) {
                options.onRecipeClick(d.recipe_id, d.recipe_name);
            }
        });

    // Add zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.5, 10])
        .on('zoom', (event) => {
            // Hide preview during zoom/pan
            previewCard.hide();

            const transform = event.transform;

            circles
                .attr('cx', d => transform.applyX(xScale(d.x)))
                .attr('cy', d => transform.applyY(yScale(d.y)));
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
}
