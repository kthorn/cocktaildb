import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

// The ingredients page reports save results through the shared notification
// helper (#152): errors persist until the next submit, successes confirm.

class Element {
    constructor() {
        this.children = [];
        this.dataset = {};
        this.style = {};
        this.value = '';
        this.checked = false;
        this.className = '';
        this.textContent = '';
        this._listeners = new Map();
        this.classList = { add() {}, remove() {}, toggle() {} };
    }

    addEventListener(type, handler) {
        this._listeners.set(type, handler);
    }

    querySelector() {
        return null;
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    removeAttribute() {}

    closest() {
        return null;
    }

    reset() {}

    scrollIntoView() {}
}

function loadPage(api) {
    const ids = [
        'ingredient-form',
        'ingredients-container',
        'ingredient-search',
        'ingredient-parent-search',
        'ingredient-parent',
        'parent-autocomplete-dropdown',
        'parent-search-status',
        'parent-loading-indicator',
        'ingredients-title',
        'ingredient-name',
        'ingredient-description',
        'ingredient-url',
        'ingredient-percent-abv',
        'ingredient-sugar-g-per-l',
        'ingredient-acid-g-per-l',
        'ingredient-allow-substitution',
    ];
    const elements = new Map(ids.map((id) => [id, new Element()]));
    const shown = [];
    const dismissed = [];
    const context = vm.createContext({
        api: { isEditor: () => true, getIngredients: async () => [], ...api },
        document: {
            getElementById: (id) => elements.get(id) ?? null,
            querySelector: () => null,
            querySelectorAll: () => [],
            createElement: () => new Element(),
            addEventListener: (type, handler) => {
                if (type === 'DOMContentLoaded') handler();
            },
        },
        window: {},
        showNotification: (message, type) => {
            const notification = { message, type };
            shown.push(notification);
            return notification;
        },
        dismissNotification: (notification) => dismissed.push(notification),
        console: { ...console, error: () => {} },
        setTimeout,
    });
    const source = readFileSync(
        new URL('../src/web/js/ingredients.js', import.meta.url),
        'utf8',
    ).replace(/^import .*;\n/gm, '');
    vm.runInContext(source, context);

    const submit = () =>
        elements.get('ingredient-form')._listeners.get('submit')({ preventDefault() {} });
    return { elements, shown, dismissed, submit };
}

test('a failed save shows the backend error, cleared by the next submit', async () => {
    let fail = true;
    const page = loadPage({
        createIngredient: async () => {
            if (fail) throw new Error('Ingredient "Gin" already exists');
            return { id: 9, name: 'Gin' };
        },
    });
    page.elements.get('ingredient-name').value = 'Gin';

    await page.submit();
    const error = page.shown.at(-1);
    assert.deepEqual(error, { message: 'Ingredient "Gin" already exists', type: 'error' });

    fail = false;
    await page.submit();
    assert.ok(page.dismissed.includes(error), 'resubmitting clears the earlier error');
    assert.deepEqual(page.shown.at(-1), { message: 'Added "Gin".', type: 'success' });
});

test('updating an ingredient confirms the save', async () => {
    const updates = [];
    const page = loadPage({ updateIngredient: async (...args) => updates.push(args) });
    const form = page.elements.get('ingredient-form');
    form.dataset.mode = 'edit';
    form.dataset.id = '4';
    page.elements.get('ingredient-name').value = 'London Dry Gin';

    await page.submit();

    assert.equal(updates.length, 1);
    assert.deepEqual(page.shown.at(-1), { message: 'Updated "London Dry Gin".', type: 'success' });
});
