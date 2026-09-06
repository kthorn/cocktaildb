const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeElement {
    constructor(tagName = 'div', id = '') {
        this.tagName = tagName.toUpperCase();
        this.id = id;
        this.children = [];
        this.parentNode = null;
        this.className = '';
        this.style = {};
        this.value = '';
        this.checked = false;
        this.disabled = false;
        this._textContent = '';
        this._listeners = new Map();
        this.dataset = {};
        this.classList = {
            add: (...names) => {
                const classes = new Set(this.className.split(/\s+/).filter(Boolean));
                names.forEach((name) => classes.add(name));
                this.className = [...classes].join(' ');
            },
            remove: (...names) => {
                const classes = new Set(this.className.split(/\s+/).filter(Boolean));
                names.forEach((name) => classes.delete(name));
                this.className = [...classes].join(' ');
            },
            contains: (name) => this.className.split(/\s+/).includes(name),
            toggle: (name, force) => {
                const shouldAdd = force === undefined ? !this.classList.contains(name) : force;
                if (shouldAdd) this.classList.add(name);
                else this.classList.remove(name);
                return shouldAdd;
            },
        };
    }

    get firstChild() {
        return this.children[0] || null;
    }

    get textContent() {
        return this._textContent + this.children.map((child) => child.textContent).join('');
    }

    set textContent(value) {
        this._textContent = String(value);
        this.children = [];
    }

    set innerHTML(value) {
        this._textContent = String(value);
        this.children = [];
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    append(...children) {
        children.forEach((child) => this.appendChild(child));
    }

    insertBefore(child, reference) {
        child.parentNode = this;
        const index = this.children.indexOf(reference);
        this.children.splice(index < 0 ? this.children.length : index, 0, child);
        return child;
    }

    remove() {
        if (this.parentNode) {
            this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
        }
    }

    addEventListener(type, handler) {
        this._listeners.set(type, handler);
    }

    dispatchEvent(event) {
        const handler = this._listeners.get(event.type);
        if (handler) return handler(event);
        return undefined;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }

    querySelectorAll(selector) {
        const matches = [];
        const visit = (element) => {
            element.children.forEach((child) => {
                if (matchesSelector(child, selector)) matches.push(child);
                visit(child);
            });
        };
        visit(this);
        return matches;
    }

    closest(selector) {
        let current = this;
        while (current) {
            if (matchesSelector(current, selector)) return current;
            current = current.parentNode;
        }
        return null;
    }

    scrollIntoView() {}
}

function matchesSelector(element, selector) {
    if (selector.startsWith('#')) return element.id === selector.slice(1);
    if (selector.startsWith('.')) {
        return element.className.split(/\s+/).includes(selector.slice(1));
    }
    return element.tagName === selector.toUpperCase();
}

function buildHarness() {
    const elements = {};
    const register = (tagName, id, className = '') => {
        const element = new FakeElement(tagName, id);
        element.className = className;
        if (id) elements[id] = element;
        return element;
    };

    const body = register('body', 'body');
    const form = register('form', 'recipe-search-form');
    const nameSearch = register('input', 'name-search');
    const tagsSearch = register('input', 'tags-search');
    const searchButton = register('button', 'search-button');
    const resetButton = register('button', 'reset-button');
    const results = register('div', 'search-results-container');
    // Include card containers declared by the page so this pagination fixture
    // also works when result rendering is isolated from its status messages.
    const html = fs.readFileSync(path.join(__dirname, '..', 'src', 'web', 'search.html'), 'utf8');
    for (const [, id] of html.matchAll(/<div id="(search-results-[^"]+)"/g)) {
        if (!elements[id]) results.appendChild(register('div', id));
    }
    const loading = register('div', '', 'loading-placeholder');
    const empty = register('div', '', 'empty-message');
    empty.appendChild(register('p'));
    const ingredientBuilder = register('div', 'ingredient-query-builder');
    const initialRow = register('div', '', 'item-row');
    const logicalOperator = register('select');
    logicalOperator.value = 'MUST';
    const ingredientInput = register('input');
    ingredientInput.value = '';
    initialRow.querySelector = (selector) =>
        selector === '.logical-operator' ? logicalOperator : ingredientInput;
    const addRowWrapper = register('div', '', 'add-row-wrapper');
    ingredientBuilder.appendChild(initialRow);
    ingredientBuilder.appendChild(addRowWrapper);
    const addIngredient = register('button', 'add-ingredient-row');
    const sortSelect = register('select', 'sort-select');
    sortSelect.value = 'name:asc';
    const tagDropdown = register('div', 'tag-suggestions-dropdown', 'hidden');
    const selectedTags = register('div', 'selected-tags-chips');
    const nameDropdown = register('div', 'name-suggestions-dropdown', 'hidden');
    const useUserRating = register('input', 'use-user-rating');
    const inventory = register('input', 'inventory-search');
    const ratingContainer = register('div', 'star-rating-filter-container');

    form.append(nameSearch, tagsSearch, searchButton, resetButton, ingredientBuilder, sortSelect);
    body.append(
        form,
        results,
        loading,
        empty,
        addIngredient,
        tagDropdown,
        selectedTags,
        nameDropdown,
        useUserRating,
        inventory,
        ratingContainer,
    );

    let domReadyHandler;
    const document = {
        body,
        createElement: (tagName) => register(tagName),
        getElementById: (id) => elements[id] || null,
        querySelector: (selector) => {
            if (selector === '.loading-placeholder') return loading;
            if (selector === '.empty-message') return empty;
            return body.querySelector(selector);
        },
        querySelectorAll: (selector) => body.querySelectorAll(selector),
        addEventListener: (type, handler) => {
            if (type === 'DOMContentLoaded') domReadyHandler = handler;
        },
    };

    const calls = [];
    let resolveFirstSearch;
    const firstSearchPending = new Promise((resolve) => {
        resolveFirstSearch = resolve;
    });
    const api = {
        getIngredients: async () => [],
        getPublicTags: async () => [],
        isAuthenticated: () => false,
        searchRecipes: async (...args) => {
            calls.push(args);
            if (calls.length === 1) {
                await firstSearchPending;
                return {
                    recipes: [{ id: 1 }],
                    pagination: { has_next: true, next_cursor: 'cursor-1' },
                };
            }
            return {
                recipes: [{ id: 2 }],
                pagination: { has_next: false, next_cursor: null },
            };
        },
    };

    const sourcePath = path.join(__dirname, '..', 'src', 'web', 'js', 'search.js');
    const source = fs
        .readFileSync(sourcePath, 'utf8')
        .replace(/^import .*;\n/gm, '')
        .replace(
            /\n}\);\s*$/,
            '\n    this.testExports = { performSearch, loadMoreSearchResults };\n});\n',
        );
    const context = vm.createContext({
        document,
        window: {
            addEventListener: () => {},
            removeEventListener: () => {},
            pageYOffset: 0,
            innerHeight: 800,
            location: { search: '' },
        },
        documentElement: { scrollTop: 0, scrollHeight: 1000 },
        api,
        displayRecipes: () => {},
        createInteractiveStars: () => register('div'),
        isAuthenticated: () => false,
        console: { ...console, log: () => {}, error: () => {}, warn: () => {} },
        setTimeout,
        clearTimeout,
        Math,
        URLSearchParams,
    });
    vm.runInContext(source, context, { filename: sourcePath });
    domReadyHandler();

    return {
        calls,
        firstSearchPending,
        resolveFirstSearch,
        performSearch: context.testExports.performSearch,
        loadMoreSearchResults: context.testExports.loadMoreSearchResults,
        nameSearch,
        sortSelect,
    };
}

(async () => {
    const harness = buildHarness();
    harness.nameSearch.value = 'gin';

    const firstSearch = harness.performSearch();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(harness.calls.length, 1);

    harness.nameSearch.value = 'vodka';
    harness.sortSelect.value = 'rating:desc';
    harness.sortSelect.dispatchEvent({ type: 'change', target: harness.sortSelect });
    harness.resolveFirstSearch();
    await firstSearch;

    await harness.loadMoreSearchResults();

    assert.equal(harness.calls.length, 2);
    assert.deepEqual(JSON.parse(JSON.stringify(harness.calls[1][0])), {
        name: 'gin',
        rating_type: 'average',
    });
    assert.equal(harness.calls[1][3], 'name');
    assert.equal(harness.calls[1][4], 'asc');
    assert.equal(harness.calls[1][5], 'cursor-1');

    await harness.performSearch();
    assert.equal(harness.calls.length, 3);
    assert.deepEqual(JSON.parse(JSON.stringify(harness.calls[2][0])), {
        name: 'vodka',
        rating_type: 'average',
    });
    assert.equal(harness.calls[2][1], 1);
    assert.equal(harness.calls[2][3], 'rating');
    assert.equal(harness.calls[2][4], 'desc');
    assert.equal(harness.calls[2][5], null);

    console.log('Search pagination snapshot contract passed');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
