const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const chartPath = path.join(
    __dirname,
    '..',
    'src',
    'web',
    'js',
    'charts',
    'ingredientTreeChart.js',
);
const chartSource =
    fs
        .readFileSync(chartPath, 'utf8')
        .replace(/^import .*;\n/gm, '')
        .replace(/^export /gm, '') +
    '\nthis.testExports = { getTooltipHtml, bindTooltipHandlers };';
const stylesPath = path.join(__dirname, '..', 'src', 'web', 'ingredient-chart.css');

const context = vm.createContext({});
vm.runInContext(chartSource, context, { filename: chartPath });

class FakeSelection {
    constructor() {
        this.handlers = new Map();
    }

    on(eventName, handler) {
        this.handlers.set(eventName, handler);
        return this;
    }

    emit(eventName, event, data) {
        return this.handlers.get(eventName).call(null, event, data);
    }
}

class FakeTooltip {
    constructor() {
        this.htmlValue = null;
        this.styles = {};
    }

    html(value) {
        this.htmlValue = value;
        return this;
    }

    style(name, value) {
        this.styles[name] = value;
        return this;
    }
}

const { getTooltipHtml, bindTooltipHandlers } = context.testExports;
const collapsedNode = {
    data: { name: 'Gin', recipe_count: 1, hierarchical_recipe_count: 2 },
    children: null,
    _children: [{}],
};
const leafNode = {
    data: { name: 'Lime', recipe_count: 0, hierarchical_recipe_count: 0 },
    children: null,
    _children: null,
};

assert.equal(
    getTooltipHtml(collapsedNode),
    '<strong>Gin</strong><br/>Direct: 1 recipe<br/>With children: 2 recipes',
);
assert.equal(getTooltipHtml(leafNode), '<strong>Lime</strong><br/>Direct: 0 recipes');

const selection = new FakeSelection();
const tooltip = new FakeTooltip();
const container = { getBoundingClientRect: () => ({ left: 100, top: 50 }) };
bindTooltipHandlers(selection, tooltip, container);

selection.emit('mouseover', { clientX: 125, clientY: 80 }, collapsedNode);
assert.equal(tooltip.htmlValue, getTooltipHtml(collapsedNode));
assert.equal(tooltip.styles.left, '35px');
assert.equal(tooltip.styles.top, '20px');
assert.equal(tooltip.styles.opacity, '1');

selection.emit('mousemove', { clientX: 130, clientY: 90 }, collapsedNode);
assert.equal(tooltip.styles.left, '40px');
assert.equal(tooltip.styles.top, '30px');

selection.emit('mouseout', {}, collapsedNode);
assert.equal(tooltip.styles.opacity, '0');

const stylesSource = fs.existsSync(stylesPath) ? fs.readFileSync(stylesPath, 'utf8') : '';
assert.match(stylesSource, /\.tree-tooltip\s*\{/);
assert.match(stylesSource, /\.tree-tooltip\s*\{[\s\S]*?position:\s*absolute/);
assert.match(stylesSource, /\.tree-tooltip\s*\{[\s\S]*?transition:\s*opacity\s+0\.2s/);

console.log('Ingredient tree tooltip behavior passed');
