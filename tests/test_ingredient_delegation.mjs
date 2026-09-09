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
        this.className = '';
        this._listeners = new Map();
        this.classList = {
            add: (...names) => names.forEach((name) => (this.className += ` ${name}`)),
            remove: (...names) => {
                this.className = this.className
                    .split(/\s+/)
                    .filter((name) => name && !names.includes(name))
                    .join(' ');
            },
            toggle: (name) => {
                const present = this.className.split(/\s+/).includes(name);
                if (present) this.classList.remove(name);
                else this.classList.add(name);
                return !present;
            },
        };
    }

    addEventListener(type, handler) {
        this._listeners.set(type, handler);
    }

    querySelector() {
        return new Element();
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    contains() {
        return true;
    }
}

test('ingredient tree delegation invokes the local edit action for a rendered button', () => {
    const ids = [
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
    const elements = new Map(ids.map((id) => [id, new Element()]));
    const container = elements.get('ingredients-container');
    const alerts = [];
    const document = {
        getElementById: (id) => elements.get(id),
        querySelector: (selector) =>
            selector === '.ingredient-form' ? elements.get('ingredient-form') : null,
        addEventListener: (type, handler) => {
            if (type === 'DOMContentLoaded') handler();
        },
        body: new Element(),
    };
    const context = vm.createContext({
        api: {
            isEditor: () => false,
            getIngredients: async () => [],
        },
        document,
        window: {},
        alert: (message) => alerts.push(message),
        confirm: () => true,
        console,
        setTimeout,
    });
    const source = readFileSync(
        new URL('../src/web/js/ingredients.js', import.meta.url),
        'utf8',
    ).replace(/^import .*;\n/gm, '');
    vm.runInContext(source, context);

    const target = {
        dataset: { action: 'edit', ingredientId: '42' },
        closest: () => target,
    };
    container._listeners.get('click')({ target });

    assert.deepEqual(alerts, [
        'Editor access required. Only editors and admins can edit ingredients.',
    ]);
});
