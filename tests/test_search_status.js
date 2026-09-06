const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const webRoot = path.join(__dirname, '..', 'src', 'web');
const htmlSource = fs.readFileSync(path.join(webRoot, 'search.html'), 'utf8');
const searchSource = fs.readFileSync(path.join(webRoot, 'js', 'search.js'), 'utf8');

const resultsSection = htmlSource.match(/<section class="results-section">([\s\S]*?)<\/section>/);
assert.ok(resultsSection, 'search page must have a results section');
assert.match(
    resultsSection[1],
    /<div id="search-results-list"[^>]*><\/div>/,
    'recipe cards need a child container separate from status messages',
);
assert.match(
    resultsSection[1],
    /loading-placeholder[\s\S]*empty-message[\s\S]*search-results-list/,
    'loading and empty status elements must remain siblings of the card container',
);

assert.match(
    searchSource,
    /const searchResults = document\.getElementById\('search-results-list'\);/,
    'search logic must target the dedicated recipe card container',
);

assert.match(
    searchSource,
    /displayRecipes\(allSearchResults, searchResults,/,
    'initial results must render into the dedicated recipe card container',
);
assert.match(
    searchSource,
    /displayRecipes\(result\.recipes, tempContainer,/,
    'paginated results should render through a temporary card container',
);
assert.match(
    searchSource,
    /searchResults\.appendChild\(card\)/,
    'paginated cards must be appended to the dedicated recipe card container',
);
assert.doesNotMatch(
    searchSource,
    /displayRecipes\([\s\S]*?searchResultsContainer,/,
    'displayRecipes must never receive the container holding status messages',
);
assert.match(
    searchSource,
    /if \(reset && allSearchResults\.length > 0\)/,
    'empty reset searches must not render a second generic no-results message',
);
assert.match(
    searchSource,
    /resetButton[\s\S]*?searchResults\.innerHTML = ''/,
    'reset must clear only recipe cards while keeping status elements attached',
);

class Element {
    constructor(tagName = 'div') {
        this.tagName = tagName;
        this.children = [];
        this.parentElement = null;
        this.className = '';
        this.dataset = {};
        this._innerHTML = '';
        this.classList = {
            add: (...names) => names.forEach((name) => this._addClass(name)),
            remove: (...names) => names.forEach((name) => this._removeClass(name)),
            contains: (name) => this.className.split(/\s+/).includes(name),
        };
    }

    _addClass(name) {
        if (!this.classList.contains(name)) this.className = `${this.className} ${name}`.trim();
    }

    _removeClass(name) {
        this.className = this.className
            .split(/\s+/)
            .filter((current) => current && current !== name)
            .join(' ');
    }

    set innerHTML(value) {
        this._innerHTML = value;
        this.children.forEach((child) => {
            child.parentElement = null;
        });
        this.children = [];
    }

    get innerHTML() {
        return this._innerHTML;
    }

    appendChild(child) {
        child.parentElement = this;
        this.children.push(child);
        return child;
    }

    querySelector(selector) {
        if (selector === 'p') return this.paragraph || null;
        return null;
    }
}

const displaySource = fs.readFileSync(path.join(webRoot, 'js', 'recipeCard.js'), 'utf8');
const displayStart = displaySource.indexOf('export function displayRecipes(');
const displayEnd = displaySource.indexOf('\n}\n\n// --- Tag Editor', displayStart) + 2;
const displayFunction = displaySource.slice(displayStart, displayEnd).replace(/^export /, '');
const performStart = searchSource.indexOf('    async function performSearch');
const performEnd = searchSource.indexOf('\n    // Setup infinite scroll', performStart);
const performFunction = searchSource.slice(performStart, performEnd).replace(/^    /gm, '');

const outer = new Element();
const loadingPlaceholder = new Element();
loadingPlaceholder.className = 'loading-placeholder hidden';
const emptyResults = new Element();
emptyResults.className = 'empty-message';
emptyResults.paragraph = { textContent: 'Enter search criteria and click Search to find recipes.' };
const searchResults = new Element();
outer.appendChild(loadingPlaceholder);
outer.appendChild(emptyResults);
outer.appendChild(searchResults);

let apiMode = 'success';
let pendingResolve;
const context = {
    allSearchResults: [],
    currentSearchQuery: null,
    currentSearchPage: 1,
    totalSearchPages: 1,
    searchResultsPerPage: 10,
    isSearching: false,
    currentSearchCursor: null,
    nextSearchCursor: null,
    useCursorPagination: true,
    currentSortBy: 'name',
    currentSortOrder: 'asc',
    searchQuery: {},
    searchResultsContainer: outer,
    searchResults,
    loadingPlaceholder,
    emptyResults,
    api: {
        searchRecipes: async () => {
            if (apiMode === 'error') throw new Error('network unavailable');
            if (apiMode === 'pending') {
                return new Promise((resolve) => {
                    pendingResolve = resolve;
                });
            }
            return {
                recipes: apiMode === 'empty' ? [] : [{ id: 1 }],
                pagination: { has_next: false, next_cursor: null },
            };
        },
    },
    buildSearchQuery: () => ({}),
    disableInfiniteScroll: () => {},
    setupInfiniteScroll: () => {},
    createRecipeCard: () => {
        const card = new Element();
        card.className = 'recipe-card';
        return card;
    },
    document: { createElement: (tagName) => new Element(tagName) },
    console: { log: () => {}, error: () => {} },
};

vm.runInNewContext(`${displayFunction}\n${performFunction}`, context);

(async () => {
    await vm.runInNewContext('performSearch(true)', context);
    assert.equal(searchResults.children.length, 1, 'successful searches render recipe cards');
    assert.equal(loadingPlaceholder.parentElement, outer, 'loading status remains attached');
    assert.equal(emptyResults.parentElement, outer, 'empty status remains attached');
    assert.equal(searchResults.parentElement, outer, 'card list remains attached');
    assert.ok(
        outer.children.includes(loadingPlaceholder),
        'loading status remains in the outer container',
    );
    assert.ok(outer.children.includes(emptyResults), 'empty status remains in the outer container');
    assert.ok(emptyResults.classList.contains('hidden'), 'empty status hides when cards load');

    apiMode = 'pending';
    const pendingSearch = vm.runInNewContext('performSearch(true)', context);
    await Promise.resolve();
    assert.ok(
        !loadingPlaceholder.classList.contains('hidden'),
        'loading status is visible while waiting',
    );
    assert.equal(searchResults.children.length, 0, 'new searches clear prior cards while waiting');
    assert.equal(emptyResults.parentElement, outer, 'empty status remains attached while waiting');
    pendingResolve({ recipes: [], pagination: { has_next: false, next_cursor: null } });
    await pendingSearch;
    assert.equal(
        searchResults.innerHTML,
        '',
        'empty searches do not leave generic no-results text',
    );
    assert.equal(
        emptyResults.paragraph.textContent,
        'No recipes found matching your criteria.',
        'empty searches show the search-specific status',
    );

    apiMode = 'error';
    await vm.runInNewContext('performSearch(true)', context);
    assert.equal(searchResults.children.length, 0, 'failed searches clear stale recipe cards');
    assert.equal(
        searchResults.innerHTML,
        '',
        'failed searches do not leave generic no-results text',
    );
    assert.equal(
        emptyResults.paragraph.textContent,
        'Error searching recipes. Please try again.',
        'failed searches show the error status',
    );
    assert.equal(emptyResults.parentElement, outer, 'error status remains attached after failure');
    assert.ok(!emptyResults.classList.contains('hidden'), 'error status is visible after failure');
    console.log('Search status behavior passed');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});

console.log('Search status preservation contract passed');
