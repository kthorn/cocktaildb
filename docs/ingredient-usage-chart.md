# Hierarchical Ingredient Usage Chart with D3.js

## Overview
This document specifies the implementation of an interactive hierarchical bar chart using D3.js to visualize ingredient usage across recipes. The chart supports click-to-drilldown functionality, allowing users to explore ingredient hierarchies by expanding parent ingredients to view their subtypes.

## Objectives
- Display ingredient usage statistics as horizontal bar charts
- Support interactive drilldown by clicking on ingredients with children
- Maintain navigation context with breadcrumb trail
- Provide smooth animations for transitions
- Show detailed information via tooltips
- Handle responsive layout for different screen sizes
- Aggregate recipe counts hierarchically (parent includes children)

## Visualization Design

### Chart Type
**Horizontal Bar Chart** - Chosen because:
- Better for displaying long ingredient names
- Easier to read on mobile devices
- Natural left-to-right reading pattern
- More space for labels

### Visual Encoding

#### Bar Encoding
- **X-axis (horizontal)**: Recipe count (hierarchical usage)
- **Y-axis (vertical)**: Ingredient names
- **Color coding**:
  - **Blue (#1f77b4)**: Ingredients with children (clickable)
  - **Light Blue (#aec7e8)**: Leaf ingredients (not clickable)
  - **Hover state**: Darker shade with slight opacity
- **Bar height**: Fixed height (30px) with 5px spacing
- **Interactive cursor**: Pointer cursor for clickable ingredients

#### Text Labels
- **Ingredient name**: Left-aligned on bar (white text with shadow for readability)
- **Recipe count**: Right side of bar, inside or outside depending on bar length
- **Hierarchy indicator**: "▶" arrow icon for ingredients with children

### Interactions

1. **Click**: Drill down to child ingredients (if has_children is true)
2. **Hover**: Show tooltip with detailed information
3. **Breadcrumb navigation**: Click breadcrumb items to navigate up the hierarchy
4. **Transitions**: Smooth fade-out/fade-in when changing hierarchy level

### Tooltip Content
```
[Ingredient Name]
━━━━━━━━━━━━━━━━━
Direct usage: [count] recipes
Including subtypes: [hierarchical_count] recipes
[Has X child ingredients] (if applicable)
Click to explore →
```

## Technical Implementation

### File Structure

```
src/web/js/charts/
└── ingredientUsageChart.js
```

### D3.js Version
Use **D3.js v7** (loaded via CDN in analytics.html)

### Chart Configuration

```javascript
const DEFAULT_CONFIG = {
    margin: { top: 20, right: 60, bottom: 30, left: 200 },
    barHeight: 30,
    barSpacing: 5,
    transitionDuration: 750,
    colors: {
        hasChildren: '#1f77b4',      // Blue for parents
        leaf: '#aec7e8',              // Light blue for leaves
        hover: '#1565c0'              // Darker blue on hover
    },
    minBarWidth: 5,                   // Minimum bar width in pixels
    maxBars: 20,                      // Maximum bars to show at once
    tooltipOffset: { x: 10, y: -20 }
};
```

### Component API

```javascript
/**
 * Create and render ingredient usage chart
 * @param {HTMLElement} container - DOM element to render chart in
 * @param {Array<Object>} data - Ingredient usage data
 * @param {Object} options - Chart options
 * @param {Function} options.onIngredientClick - Callback when ingredient is clicked
 * @param {Object} options.config - Override default configuration
 */
export function createIngredientUsageChart(container, data, options = {}) {
    // Implementation
}
```

### Implementation Code

Create `src/web/js/charts/ingredientUsageChart.js`:

```javascript
/**
 * Hierarchical Ingredient Usage Chart Component
 * Interactive horizontal bar chart with drilldown functionality using D3.js
 */

const DEFAULT_CONFIG = {
    margin: { top: 20, right: 60, bottom: 30, left: 200 },
    barHeight: 30,
    barSpacing: 5,
    transitionDuration: 750,
    colors: {
        hasChildren: '#1f77b4',
        leaf: '#aec7e8',
        hover: '#1565c0'
    },
    minBarWidth: 5,
    maxBars: 20,
    tooltipOffset: { x: 10, y: -20 }
};

/**
 * Create and render ingredient usage chart
 */
export function createIngredientUsageChart(container, data, options = {}) {
    // Clear existing chart
    d3.select(container).selectAll('*').remove();

    // Merge config
    const config = { ...DEFAULT_CONFIG, ...(options.config || {}) };
    const { onIngredientClick } = options;

    // Sort data by hierarchical usage (descending)
    const sortedData = [...data].sort((a, b) =>
        b.hierarchical_usage - a.hierarchical_usage
    );

    // Limit to top N items
    const displayData = sortedData.slice(0, config.maxBars);

    // Calculate dimensions
    const containerRect = container.getBoundingClientRect();
    const width = containerRect.width;
    const chartHeight = (config.barHeight + config.barSpacing) * displayData.length;
    const height = chartHeight + config.margin.top + config.margin.bottom;

    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .attr('class', 'ingredient-chart');

    // Create chart group
    const chart = svg.append('g')
        .attr('transform', `translate(${config.margin.left},${config.margin.top})`);

    // Calculate inner width
    const innerWidth = width - config.margin.left - config.margin.right;

    // Create scales
    const maxValue = d3.max(displayData, d => d.hierarchical_usage) || 1;

    const xScale = d3.scaleLinear()
        .domain([0, maxValue])
        .range([0, innerWidth])
        .nice();

    const yScale = d3.scaleBand()
        .domain(displayData.map((d, i) => i))
        .range([0, chartHeight])
        .padding(0.1);

    // Create axes
    const xAxis = d3.axisBottom(xScale)
        .ticks(5)
        .tickFormat(d => Math.floor(d));

    chart.append('g')
        .attr('class', 'x-axis')
        .attr('transform', `translate(0,${chartHeight})`)
        .call(xAxis)
        .selectAll('text')
        .style('font-size', '12px');

    // Add axis label
    chart.append('text')
        .attr('class', 'axis-label')
        .attr('x', innerWidth / 2)
        .attr('y', chartHeight + config.margin.bottom - 5)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', '#666')
        .text('Number of Recipes');

    // Create tooltip
    const tooltip = d3.select('body')
        .append('div')
        .attr('class', 'chart-tooltip')
        .style('position', 'absolute')
        .style('visibility', 'hidden')
        .style('background-color', 'rgba(0, 0, 0, 0.9)')
        .style('color', 'white')
        .style('padding', '12px')
        .style('border-radius', '6px')
        .style('font-size', '13px')
        .style('line-height', '1.6')
        .style('pointer-events', 'none')
        .style('z-index', '1000')
        .style('box-shadow', '0 2px 8px rgba(0,0,0,0.3)');

    // Create bar groups
    const bars = chart.selectAll('.bar-group')
        .data(displayData)
        .enter()
        .append('g')
        .attr('class', 'bar-group')
        .attr('transform', (d, i) => `translate(0,${yScale(i)})`);

    // Add bars
    bars.append('rect')
        .attr('class', 'bar')
        .attr('x', 0)
        .attr('y', 0)
        .attr('width', 0) // Start at 0 for animation
        .attr('height', yScale.bandwidth())
        .attr('fill', d => d.has_children ? config.colors.hasChildren : config.colors.leaf)
        .attr('rx', 3) // Rounded corners
        .style('cursor', d => d.has_children ? 'pointer' : 'default')
        .style('transition', 'fill 0.2s')
        // Animate bar width
        .transition()
        .duration(config.transitionDuration)
        .attr('width', d => Math.max(xScale(d.hierarchical_usage), config.minBarWidth));

    // Add ingredient name labels (on the left side)
    bars.append('text')
        .attr('class', 'ingredient-label')
        .attr('x', -10)
        .attr('y', yScale.bandwidth() / 2)
        .attr('dy', '0.35em')
        .attr('text-anchor', 'end')
        .style('font-size', '13px')
        .style('fill', '#333')
        .style('font-weight', '500')
        .text(d => {
            const maxLabelLength = 25;
            const name = d.ingredient_name;
            const arrow = d.has_children ? ' ▶' : '';
            if (name.length > maxLabelLength) {
                return name.substring(0, maxLabelLength - 3) + '...' + arrow;
            }
            return name + arrow;
        })
        .style('opacity', 0)
        .transition()
        .duration(config.transitionDuration)
        .delay(200)
        .style('opacity', 1);

    // Add count labels (on or near the bars)
    bars.append('text')
        .attr('class', 'count-label')
        .attr('x', d => {
            const barWidth = xScale(d.hierarchical_usage);
            // If bar is wide enough, place inside; otherwise outside
            return barWidth > 40 ? barWidth - 5 : barWidth + 5;
        })
        .attr('y', yScale.bandwidth() / 2)
        .attr('dy', '0.35em')
        .attr('text-anchor', d => {
            const barWidth = xScale(d.hierarchical_usage);
            return barWidth > 40 ? 'end' : 'start';
        })
        .style('font-size', '12px')
        .style('fill', d => {
            const barWidth = xScale(d.hierarchical_usage);
            return barWidth > 40 ? 'white' : '#333';
        })
        .style('font-weight', '600')
        .text(d => d.hierarchical_usage)
        .style('opacity', 0)
        .transition()
        .duration(config.transitionDuration)
        .delay(300)
        .style('opacity', 1);

    // Add hover and click interactions
    bars.on('mouseenter', function(event, d) {
        // Highlight bar
        d3.select(this).select('.bar')
            .transition()
            .duration(150)
            .attr('fill', config.colors.hover);

        // Show tooltip
        const tooltipContent = createTooltipContent(d);
        tooltip.html(tooltipContent)
            .style('visibility', 'visible');
    })
    .on('mousemove', function(event) {
        tooltip
            .style('top', (event.pageY + config.tooltipOffset.y) + 'px')
            .style('left', (event.pageX + config.tooltipOffset.x) + 'px');
    })
    .on('mouseleave', function(event, d) {
        // Restore original color
        d3.select(this).select('.bar')
            .transition()
            .duration(150)
            .attr('fill', d.has_children ? config.colors.hasChildren : config.colors.leaf);

        // Hide tooltip
        tooltip.style('visibility', 'hidden');
    })
    .on('click', function(event, d) {
        if (d.has_children && onIngredientClick) {
            // Add visual feedback
            d3.select(this).select('.bar')
                .transition()
                .duration(100)
                .attr('opacity', 0.7)
                .transition()
                .duration(100)
                .attr('opacity', 1);

            // Trigger callback
            onIngredientClick(d);
        }
    });

    // Add "showing X of Y" text if data was truncated
    if (data.length > config.maxBars) {
        svg.append('text')
            .attr('class', 'truncation-note')
            .attr('x', config.margin.left)
            .attr('y', height - 5)
            .style('font-size', '11px')
            .style('fill', '#888')
            .style('font-style', 'italic')
            .text(`Showing top ${config.maxBars} of ${data.length} ingredients`);
    }

    // Cleanup function
    return () => {
        tooltip.remove();
    };
}

/**
 * Create tooltip content HTML
 */
function createTooltipContent(data) {
    const childrenInfo = data.has_children
        ? `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.2);">
             Has child ingredients<br/>
             <span style="color: #81c784;">Click to explore →</span>
           </div>`
        : '';

    const directInfo = data.direct_usage > 0
        ? `<div>Direct usage: <strong>${data.direct_usage}</strong> ${pluralize('recipe', data.direct_usage)}</div>`
        : '<div style="color: #999;">No direct usage</div>';

    return `
        <div style="font-weight: 600; margin-bottom: 8px; font-size: 14px;">
            ${escapeHtml(data.ingredient_name)}
        </div>
        <div style="border-left: 3px solid #1f77b4; padding-left: 8px;">
            ${directInfo}
            <div>Including subtypes: <strong>${data.hierarchical_usage}</strong> ${pluralize('recipe', data.hierarchical_usage)}</div>
        </div>
        ${childrenInfo}
    `;
}

/**
 * Pluralize word based on count
 */
function pluralize(word, count) {
    return count === 1 ? word : word + 's';
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

/**
 * Responsive chart resize handler
 */
export function createResponsiveChart(container, data, options = {}) {
    let cleanup = null;

    function render() {
        if (cleanup) cleanup();
        cleanup = createIngredientUsageChart(container, data, options);
    }

    // Initial render
    render();

    // Re-render on window resize with debouncing
    let resizeTimer;
    const handleResize = () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(render, 250);
    };

    window.addEventListener('resize', handleResize);

    // Return cleanup function
    return () => {
        if (cleanup) cleanup();
        window.removeEventListener('resize', handleResize);
    };
}
```

### Alternative: Collapsible Tree View

For a different UX approach, D3.js also supports collapsible tree diagrams. Here's a basic implementation pattern:

```javascript
/**
 * Alternative: Collapsible tree diagram (NOT bar chart)
 * This shows the full hierarchy at once with expand/collapse nodes
 */
export function createCollapsibleTree(container, data, options = {}) {
    // Convert flat data to hierarchical structure
    const root = d3.stratify()
        .id(d => d.ingredient_id)
        .parentId(d => d.parent_id)
        (data);

    // Create tree layout
    const treeLayout = d3.tree()
        .size([height, width]);

    // Generate tree structure
    const treeData = treeLayout(root);

    // Render nodes and links
    // ... (implementation details)
}
```

**Note**: The bar chart approach is recommended for this use case as it better emphasizes the quantitative aspect (recipe counts) and is more familiar to users.

## Data Requirements

### Input Data Format

The chart expects an array of ingredient objects with the following structure:

```typescript
interface IngredientUsageData {
    ingredient_id: number;
    ingredient_name: string;
    recipe_count?: number;           // Deprecated, use direct_usage
    direct_usage: number;            // Recipes using this exact ingredient
    hierarchical_usage: number;      // Recipes using this or child ingredients
    has_children: boolean;
    path: string;                    // e.g., "/1/23/"
    parent_id?: number | null;
    children_preview?: string[];     // Optional: preview of child names
}
```

### Example Data

```json
[
    {
        "ingredient_id": 1,
        "ingredient_name": "Whiskey",
        "direct_usage": 12,
        "hierarchical_usage": 45,
        "has_children": true,
        "path": "/1/",
        "parent_id": null,
        "children_preview": ["Bourbon", "Rye", "Scotch", "Irish Whiskey"]
    },
    {
        "ingredient_id": 23,
        "ingredient_name": "Bourbon",
        "direct_usage": 18,
        "hierarchical_usage": 18,
        "has_children": false,
        "path": "/1/23/",
        "parent_id": 1
    }
]
```

## Performance Considerations

### Optimization Strategies

1. **Data Limiting**: Show only top N ingredients (default 20) to prevent overcrowding
2. **Virtualization**: For very long lists, implement virtual scrolling (not needed for 20 items)
3. **Debounced Resize**: Debounce window resize events (250ms delay)
4. **Transition Performance**: Use D3 transitions sparingly, disable for large datasets
5. **Tooltip Cleanup**: Ensure tooltips are properly removed when chart is destroyed

### Large Dataset Handling

If displaying more than 50 items:
- Implement pagination or "show more" button
- Add search/filter capability
- Consider switching to a different visualization (treemap, sunburst)

### Memory Management

```javascript
// Proper cleanup when destroying chart
function destroyChart() {
    // Remove tooltip from DOM
    d3.selectAll('.chart-tooltip').remove();

    // Remove event listeners
    window.removeEventListener('resize', handleResize);

    // Clear SVG
    d3.select(container).selectAll('*').remove();
}
```

## Accessibility

### Keyboard Navigation

Add keyboard support for accessibility:

```javascript
bars.attr('tabindex', 0)
    .on('keydown', function(event, d) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            if (d.has_children && onIngredientClick) {
                onIngredientClick(d);
            }
        }
    });
```

### ARIA Labels

```javascript
svg.attr('role', 'img')
   .attr('aria-label', 'Ingredient usage chart showing recipe counts for each ingredient');

bars.attr('role', 'button')
    .attr('aria-label', d =>
        `${d.ingredient_name}, ${d.hierarchical_usage} recipes${
            d.has_children ? ', click to expand' : ''
        }`
    );
```

### Screen Reader Support

Add visually hidden text descriptions:

```html
<div class="sr-only">
    Chart showing ingredient usage across recipes.
    Ingredients with children can be clicked to explore subtypes.
</div>
```

## Testing Approach

### Unit Tests

```javascript
describe('IngredientUsageChart', () => {
    it('should render bars for all ingredients', () => {
        const data = [...]; // test data
        const container = document.createElement('div');
        createIngredientUsageChart(container, data);

        const bars = container.querySelectorAll('.bar');
        expect(bars.length).toBe(data.length);
    });

    it('should call onIngredientClick when clicking ingredient with children', () => {
        const mockCallback = jest.fn();
        const data = [{ ingredient_id: 1, has_children: true, ... }];

        createIngredientUsageChart(container, data, {
            onIngredientClick: mockCallback
        });

        // Simulate click
        const bar = container.querySelector('.bar-group');
        bar.dispatchEvent(new Event('click'));

        expect(mockCallback).toHaveBeenCalledWith(data[0]);
    });

    it('should not exceed maxBars limit', () => {
        const data = Array(50).fill({...}); // 50 items
        const config = { maxBars: 20 };

        createIngredientUsageChart(container, data, { config });

        const bars = container.querySelectorAll('.bar');
        expect(bars.length).toBeLessThanOrEqual(20);
    });
});
```

### Visual Regression Tests

- Capture screenshots of rendered charts
- Compare against baseline images
- Test different screen sizes (desktop, tablet, mobile)
- Test with varying data sizes

### Integration Tests

- Test with real API data
- Test drilldown navigation flow
- Test breadcrumb navigation
- Test error handling when data is invalid

## Browser Compatibility

### Supported Browsers
- Chrome 90+ ✓
- Firefox 88+ ✓
- Safari 14+ ✓
- Edge 90+ ✓

### Polyfills Needed
None - D3.js v7 handles cross-browser compatibility

### Known Issues
- IE11: Not supported (D3.js v7 requires modern browsers)
- Safari < 14: May need CSS prefix for some transitions

## Examples and Use Cases

### Example 1: Basic Usage

```javascript
import { createIngredientUsageChart } from './charts/ingredientUsageChart.js';

const container = document.getElementById('chart-container');
const data = await api.getIngredientUsageAnalytics();

createIngredientUsageChart(container, data.data, {
    onIngredientClick: (ingredient) => {
        console.log('Clicked:', ingredient.ingredient_name);
        // Load child ingredients
        loadChildIngredients(ingredient.ingredient_id);
    }
});
```

### Example 2: Custom Configuration

```javascript
createIngredientUsageChart(container, data, {
    config: {
        maxBars: 30,
        barHeight: 40,
        colors: {
            hasChildren: '#2196f3',
            leaf: '#90caf9',
            hover: '#1565c0'
        }
    },
    onIngredientClick: handleDrilldown
});
```

### Example 3: Responsive Chart

```javascript
import { createResponsiveChart } from './charts/ingredientUsageChart.js';

const cleanup = createResponsiveChart(container, data, {
    onIngredientClick: handleDrilldown
});

// Later, when component unmounts:
cleanup();
```

## Future Enhancements

1. **Animated Transitions**: Smooth transitions when drilling down/up
2. **Zoom and Pan**: For very large hierarchies
3. **Search Highlight**: Highlight bars matching search query
4. **Comparison Mode**: Compare ingredient usage across different time periods
5. **Export**: Export chart as PNG/SVG
6. **Stacked Bars**: Show direct vs. child usage as stacked segments
7. **Sorting Options**: Allow user to sort by different criteria
8. **Filtering**: Filter by minimum usage threshold

## References

- [D3.js Bar Chart Documentation](https://d3js.org/d3-scale/band)
- [D3.js Hierarchy Module](https://d3js.org/d3-hierarchy)
- [D3.js Transitions](https://d3js.org/d3-transition)
- [Observable D3 Gallery](https://observablehq.com/@d3/gallery)
