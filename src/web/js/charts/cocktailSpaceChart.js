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

    // Add grid lines
    g.append('g')
        .attr('class', 'grid')
        .attr('opacity', 0.1)
        .call(d3.axisLeft(yScale)
            .tickSize(-width)
            .tickFormat(''));

    g.append('g')
        .attr('class', 'grid')
        .attr('opacity', 0.1)
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(xScale)
            .tickSize(-height)
            .tickFormat(''));

    // Add X axis
    g.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(d3.axisBottom(xScale))
        .append('text')
        .attr('x', width / 2)
        .attr('y', 45)
        .attr('fill', 'black')
        .attr('font-size', '14px')
        .attr('font-weight', 'bold')
        .text('UMAP Dimension 1');

    // Add Y axis
    g.append('g')
        .call(d3.axisLeft(yScale))
        .append('text')
        .attr('transform', 'rotate(-90)')
        .attr('x', -height / 2)
        .attr('y', -45)
        .attr('fill', 'black')
        .attr('font-size', '14px')
        .attr('font-weight', 'bold')
        .attr('text-anchor', 'middle')
        .text('UMAP Dimension 2');

    // Create tooltip
    const tooltip = d3.select('body')
        .append('div')
        .style('position', 'absolute')
        .style('background', 'rgba(0, 0, 0, 0.8)')
        .style('color', 'white')
        .style('padding', '8px 12px')
        .style('border-radius', '4px')
        .style('font-size', '12px')
        .style('pointer-events', 'none')
        .style('opacity', 0)
        .style('z-index', 1000);

    // Create clip path for zoom
    svg.append('defs')
        .append('clipPath')
        .attr('id', 'clip')
        .append('rect')
        .attr('width', width)
        .attr('height', height);

    // Add circles for data points
    const circles = g.append('g')
        .attr('clip-path', 'url(#clip)')
        .selectAll('circle')
        .data(data)
        .enter()
        .append('circle')
        .attr('cx', d => xScale(d.x))
        .attr('cy', d => yScale(d.y))
        .attr('r', 6)
        .attr('fill', 'steelblue')
        .attr('stroke', 'white')
        .attr('stroke-width', 1)
        .attr('opacity', 0.7)
        .style('cursor', 'pointer')
        .on('mouseover', function(event, d) {
            d3.select(this)
                .transition()
                .duration(200)
                .attr('r', 8)
                .attr('opacity', 1);

            tooltip
                .style('opacity', 1)
                .html(`<strong>${d.recipe_name}</strong>`)
                .style('left', (event.pageX + 10) + 'px')
                .style('top', (event.pageY - 10) + 'px');
        })
        .on('mousemove', function(event) {
            tooltip
                .style('left', (event.pageX + 10) + 'px')
                .style('top', (event.pageY - 10) + 'px');
        })
        .on('mouseout', function() {
            d3.select(this)
                .transition()
                .duration(200)
                .attr('r', 6)
                .attr('opacity', 0.7);

            tooltip.style('opacity', 0);
        })
        .on('click', function(event, d) {
            if (options.onRecipeClick) {
                options.onRecipeClick(d.recipe_id, d.recipe_name);
            }
        });

    // Add zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.5, 10])
        .on('zoom', (event) => {
            const transform = event.transform;

            circles
                .attr('cx', d => transform.applyX(xScale(d.x)))
                .attr('cy', d => transform.applyY(yScale(d.y)));

            g.select('.x-axis')
                .call(d3.axisBottom(xScale).scale(transform.rescaleX(xScale)));

            g.select('.y-axis')
                .call(d3.axisLeft(yScale).scale(transform.rescaleY(yScale)));
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
