// The ingredient form sends parent_id: null to move an ingredient to the top
// level (#146), so a parent name that matches nothing must not be sent as null.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

class Element {
    constructor() {
        this.children = [];
        this.dataset = {};
        this.style = {};
        this.value = '';
        this.checked = false;
        this.className = '';
        this.textContent = '';
        this.attributes = {};
        this.focused = false;
        this._listeners = new Map();
        this.classList = {
            add: () => {},
            remove: () => {},
        };
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    removeAttribute(name) {
        delete this.attributes[name];
    }

    closest() {
        return this.group ?? null;
    }

    focus() {
        this.focused = true;
    }

    addEventListener(type, handler) {
        this._listeners.set(type, handler);
    }

    querySelector() {
        return new Element();
    }

    appendChild(child) {
        child.parent = this;
        this.children.push(child);
        return child;
    }

    insertBefore(child) {
        this.children.unshift(child);
        return child;
    }

    contains() {
        return true;
    }

    remove() {
        if (!this.parent) return;
        this.parent.children = this.parent.children.filter((child) => child !== this);
        this.parent = null;
    }

    reset() {}

    scrollIntoView() {}
}

const IDS = [
    'ingredient-form',
    'ingredients-container',
    'ingredient-search',
    'ingredient-parent-search',
    'ingredient-parent',
    'parent-autocomplete-dropdown',
    'parent-search-status',
    'ingredients-title',
    'ingredient-name',
    'ingredient-description',
    'ingredient-url',
    'ingredient-percent-abv',
    'ingredient-sugar-g-per-l',
    'ingredient-acid-g-per-l',
    'ingredient-allow-substitution',
];

const SPIRIT = { id: 1, name: 'Spirit', parent_id: null };
const GIN = { id: 2, name: 'Gin', parent_id: 1 };

function loadPage(api) {
    const elements = new Map(IDS.map((id) => [id, new Element()]));
    const parentGroup = new Element();
    elements.get('ingredient-parent-search').group = parentGroup;
    const notifications = [];
    const document = {
        getElementById: (id) =>
            elements.get(id) ?? parentGroup.children.find((child) => child.id === id) ?? null,
        querySelector: (selector) =>
            selector === '.ingredient-form' ? elements.get('ingredient-form') : null,
        querySelectorAll: () => [],
        createElement: () => new Element(),
        addEventListener: (type, handler) => {
            if (type === 'DOMContentLoaded') handler();
        },
        body: new Element(),
    };
    const context = vm.createContext({
        api: {
            isEditor: () => true,
            getIngredients: async () => [SPIRIT, GIN],
            ...api,
        },
        buildHierarchy: () => [],
        renderHierarchyHTML: () => '',
        document,
        window: {},
        showNotification: (message, type) => notifications.push({ message, type }),
        dismissNotification: () => {},
        confirm: () => true,
        console: { ...console, error: () => {} },
        setTimeout: () => {},
    });
    const source = readFileSync(
        new URL('../src/web/js/ingredients.js', import.meta.url),
        'utf8',
    ).replace(/^import .*;\n/gm, '');
    vm.runInContext(source, context);

    return { elements, parentGroup, notifications };
}

async function flush() {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setImmediate(resolve));
}

async function submitEdit(page, parentName) {
    const form = page.elements.get('ingredient-form');
    form.dataset.mode = 'edit';
    form.dataset.id = String(GIN.id);
    page.elements.get('ingredient-name').value = GIN.name;
    page.elements.get('ingredient-parent-search').value = parentName;
    await form._listeners.get('submit')({ preventDefault() {} });
}

test('editing with an unknown parent name flags the field and sends nothing', async () => {
    const updates = [];
    const page = loadPage({ updateIngredient: async (...args) => updates.push(args) });
    await flush();

    await submitEdit(page, 'Spirt');

    assert.deepEqual(updates, []);
    const parentInput = page.elements.get('ingredient-parent-search');
    const [error] = page.parentGroup.children;
    assert.match(error.textContent, /No ingredient named "Spirt"/);
    assert.equal(error.className, 'field-error');
    assert.equal(parentInput.attributes['aria-invalid'], 'true');
    assert.equal(parentInput.attributes['aria-describedby'], error.id);
    assert.ok(parentInput.focused, 'the parent field is focused');
    assert.deepEqual(page.notifications, [], 'reported at the field, not as a notification');
});

test('changing the parent name clears the field error', async () => {
    const page = loadPage({ updateIngredient: async () => {} });
    await flush();
    await submitEdit(page, 'Spirt');
    const parentInput = page.elements.get('ingredient-parent-search');

    parentInput.value = 'Spirit';
    parentInput._listeners.get('input')();

    assert.deepEqual(page.parentGroup.children, []);
    assert.equal(parentInput.attributes['aria-invalid'], undefined);
    assert.equal(parentInput.attributes['aria-describedby'], undefined);
});

test('creating with an unknown parent name sends nothing', async () => {
    const creates = [];
    const page = loadPage({ createIngredient: async (data) => creates.push(data) });
    await flush();
    page.elements.get('ingredient-name').value = 'Old Tom Gin';
    page.elements.get('ingredient-parent-search').value = 'Spirt';

    await page.elements.get('ingredient-form')._listeners.get('submit')({
        preventDefault() {},
    });

    assert.deepEqual(creates, []);
});

test('editing with a known parent name sends its id', async () => {
    const updates = [];
    const page = loadPage({ updateIngredient: async (...args) => updates.push(args) });
    await flush();

    await submitEdit(page, 'spirit');

    assert.equal(updates.length, 1);
    assert.equal(updates[0][1].parent_id, SPIRIT.id);
});

test('editing with an empty parent sends null to move to the top level', async () => {
    const updates = [];
    const page = loadPage({ updateIngredient: async (...args) => updates.push(args) });
    await flush();

    await submitEdit(page, '  ');

    assert.equal(updates.length, 1);
    assert.equal(updates[0][1].parent_id, null);
});

test('a parent that fails to load does not open the form in edit mode', async () => {
    const page = loadPage({
        getIngredient: async (id) => {
            if (Number(id) === GIN.id) return GIN;
            throw new Error('network down');
        },
    });
    await flush();
    const target = {
        dataset: { action: 'edit', ingredientId: String(GIN.id) },
        closest: () => target,
    };

    page.elements.get('ingredients-container')._listeners.get('click')({ target });
    await flush();

    assert.equal(page.elements.get('ingredient-form').dataset.mode, undefined);
    assert.equal(page.elements.get('ingredient-name').value, '');
    assert.deepEqual(page.notifications, [
        { message: 'Failed to load ingredient. Please try again.', type: 'error' },
    ]);
});
