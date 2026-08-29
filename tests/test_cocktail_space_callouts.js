const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const chartPath = path.join(__dirname, '..', 'src', 'web', 'js', 'charts', 'cocktailSpaceChart.js');
const chartSource = fs.readFileSync(chartPath, 'utf8');
const stylesPath = path.join(__dirname, '..', 'src', 'web', 'styles.css');
const stylesSource = fs.readFileSync(stylesPath, 'utf8');
const apiSource = fs.readFileSync(path.join(__dirname, '..', 'src', 'web', 'js', 'api.js'), 'utf8');
const analyticsSource = fs.readFileSync(path.join(__dirname, '..', 'src', 'web', 'js', 'analytics.js'), 'utf8');
const layoutSource = fs.readFileSync(path.join(__dirname, '..', 'src', 'web', 'js', 'charts', 'calloutLayout.mjs'), 'utf8');

assert.match(apiSource, /getCocktailSpaceAnalytics[\s\S]*this\.isAuthenticated\(\)/);
assert.match(apiSource, /getCocktailSpaceEmAnalytics[\s\S]*this\.isAuthenticated\(\)/);
assert.ok(
    (analyticsSource.match(/ratingSource:\s*response\.metadata\?\.rating_source/g) || []).length === 2,
    'both UMAP charts must receive the server-selected rating source'
);
assert.match(chartSource, /const MAX_VISIBLE_CALLOUTS\s*=\s*20/);
assert.match(chartSource, /\.scaleExtent\(\[0\.5,\s*50\]\)/);
assert.match(chartSource, /visiblePoints\.length\s*<=\s*MAX_VISIBLE_CALLOUTS/);
assert.match(chartSource, /class',\s*'recipe-callouts'/);
assert.match(chartSource, /class',\s*'recipe-callout'/);
assert.ok(
    (chartSource.match(/updateCallouts\(currentTransform\)/g) || []).length >= 2,
    'callouts must update on initial render and zoom'
);
assert.match(chartSource, /\.text\(d\s*=>\s*d\.recipe_name\)/);
assert.match(chartSource, /Color by.*rating/);
assert.match(chartSource, /interpolateViridis/);
assert.match(layoutSource, /CALLOUT_CANDIDATES/);
assert.match(chartSource, /recipe-callout-line/);
assert.match(chartSource, /getComputedTextLength/);
assert.match(stylesSource, /\.recipe-callout/);
assert.match(stylesSource, /\.recipe-callout-line/);
assert.match(stylesSource, /pointer-events:\s*none/);

console.log('UMAP callout contract passed');
