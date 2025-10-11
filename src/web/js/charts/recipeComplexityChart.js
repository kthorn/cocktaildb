/**
 * Create a recipe complexity distribution chart using D3.js
 *
 * @param {HTMLElement} container - DOM element to render chart into
 * @param {Array} data - Array of complexity distribution objects
 */
export function createRecipeComplexityChart(container, data) {
    console.log('Creating recipe complexity chart with data:', data);

    // Clear container
    container.innerHTML = '';

    // Get dimensions
    const margin = { top: 20, right: 30, bottom: 60, left: 60 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = 400 - margin.top - margin.bottom;

    // Sort data by ingredient_count ascending
    const sortedData = [...data].sort((a, b) => a.ingredient_count - b.ingredient_count);

    // Find mode (most common)
    const mode = sortedData.reduce((max, item) =>
        item.recipe_count > max.recipe_count ? item : max
    );

    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create scales
    const xScale = d3.scaleBand()
        .domain(sortedData.map(d => d.ingredient_count))
        .range([0, width])
        .padding(0.2);

    const yScale = d3.scaleLinear()
        .domain([0, d3.max(sortedData, d => d.recipe_count)])
        .range([height, 0]);

    // Create axes
    const xAxis = d3.axisBottom(xScale);
    const yAxis = d3.axisLeft(yScale).ticks(5);

    // Add X axis
    svg.append('g')
        .attr('transform', `translate(0,${height})`)
        .call(xAxis)
        .append('text')
        .attr('x', width / 2)
        .attr('y', 40)
        .attr('fill', '#000')
        .attr('text-anchor', 'middle')
        .text('Number of Ingredients');

    // Add Y axis
    svg.append('g')
        .call(yAxis)
        .append('text')
        .attr('transform', 'rotate(-90)')
        .attr('x', -height / 2)
        .attr('y', -45)
        .attr('fill', '#000')
        .attr('text-anchor', 'middle')
        .text('Number of Recipes');

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
        .attr('x', d => xScale(d.ingredient_count))
        .attr('y', d => yScale(d.recipe_count))
        .attr('width', xScale.bandwidth())
        .attr('height', d => height - yScale(d.recipe_count))
        .attr('fill', d => d.ingredient_count === mode.ingredient_count ? '#ff7f0e' : '#1f77b4')
        .on('mouseover', function(event, d) {
            d3.select(this).attr('opacity', 0.7);
            tooltip.style('visibility', 'visible')
                .html(`
                    <strong>${d.ingredient_count} ingredients</strong><br/>
                    ${d.recipe_count} recipes
                `);
        })
        .on('mousemove', function(event) {
            tooltip.style('top', (event.pageY - 10) + 'px')
                .style('left', (event.pageX + 10) + 'px');
        })
        .on('mouseout', function() {
            d3.select(this).attr('opacity', 1);
            tooltip.style('visibility', 'hidden');
        });

    // Add value labels on bars
    svg.selectAll('.label')
        .data(sortedData)
        .enter()
        .append('text')
        .attr('class', 'label')
        .attr('x', d => xScale(d.ingredient_count) + xScale.bandwidth() / 2)
        .attr('y', d => yScale(d.recipe_count) - 5)
        .attr('text-anchor', 'middle')
        .attr('font-size', '12px')
        .attr('fill', '#666')
        .text(d => d.recipe_count);
}
