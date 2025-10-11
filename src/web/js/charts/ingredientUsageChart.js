/**
 * Create an interactive ingredient usage bar chart using D3.js
 *
 * @param {HTMLElement} container - DOM element to render chart into
 * @param {Array} data - Array of ingredient usage objects
 * @param {Object} options - Configuration options
 * @param {Function} options.onIngredientClick - Callback when ingredient is clicked
 */
export function createIngredientUsageChart(container, data, options = {}) {
    console.log('Creating ingredient usage chart with data:', data);

    // Clear container
    container.innerHTML = '';

    // Get dimensions
    const margin = { top: 20, right: 30, bottom: 40, left: 200 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = Math.max(400, data.length * 30) - margin.top - margin.bottom;

    // Sort data by hierarchical_usage descending
    const sortedData = [...data].sort((a, b) => b.hierarchical_usage - a.hierarchical_usage);

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
    const yAxis = d3.axisLeft(yScale);

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
        .style('position', 'absolute')
        .style('visibility', 'hidden')
        .style('background-color', 'rgba(0, 0, 0, 0.8)')
        .style('color', 'white')
        .style('padding', '8px')
        .style('border-radius', '4px')
        .style('font-size', '12px')
        .style('pointer-events', 'none')
        .style('z-index', '1000');

    // Create bars
    svg.selectAll('.bar')
        .data(sortedData)
        .enter()
        .append('rect')
        .attr('class', 'bar')
        .attr('x', 0)
        .attr('y', d => yScale(d.ingredient_name))
        .attr('width', d => xScale(d.hierarchical_usage))
        .attr('height', yScale.bandwidth())
        .attr('fill', d => d.has_children ? '#1f77b4' : '#aec7e8')
        .style('cursor', d => d.has_children ? 'pointer' : 'default')
        .on('mouseover', function(event, d) {
            d3.select(this).attr('fill', d => d.has_children ? '#1565c0' : '#90b8d8');
            tooltip.style('visibility', 'visible')
                .html(`
                    <strong>${d.ingredient_name}</strong><br/>
                    Direct usage: ${d.direct_usage}<br/>
                    Total (with subtypes): ${d.hierarchical_usage}
                `);
        })
        .on('mousemove', function(event) {
            tooltip.style('top', (event.pageY - 10) + 'px')
                .style('left', (event.pageX + 10) + 'px');
        })
        .on('mouseout', function(event, d) {
            d3.select(this).attr('fill', d => d.has_children ? '#1f77b4' : '#aec7e8');
            tooltip.style('visibility', 'hidden');
        })
        .on('click', function(event, d) {
            if (d.has_children && options.onIngredientClick) {
                options.onIngredientClick(d);
            }
        });
}
