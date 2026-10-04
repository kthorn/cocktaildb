import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { splitRecipeTags } from '../src/web/js/components/recipeTags.js';
import { formatIngredientMarkup } from '../src/web/js/utils/recipeIngredients.js';

// Minimal DOM boundary, following test_recipe_card_modules.mjs. Execute the actual
// card builder; keep the newly created ABV subtree and its event targets intact.
class Element {
    constructor(tagName) {
        this.tagName = tagName;
        this.className = '';
        this.dataset = {};
        this.children = [];
        this.listeners = {};
        this.classList = { add() {} };
        this.textContent = '';
    }
    set innerHTML(value) {
        this.markup = value;
        this.children = [];
        if (this.className === 'recipe-card') {
            const meta = new Element('div');
            meta.className = 'recipe-meta';
            this.append(meta);
        }
    }
    append(...nodes) {
        for (const node of nodes) {
            node.parentElement = this;
            this.children.push(node);
        }
    }
    after(node) {
        node.parentElement = this.parentElement;
        const siblings = this.parentElement.children;
        siblings.splice(siblings.indexOf(this) + 1, 0, node);
    }
    matches(selector) {
        return selector.startsWith('.')
            ? this.className.split(' ').includes(selector.slice(1))
            : this.tagName === selector;
    }
    closest(selectors) {
        if (selectors.split(',').some((selector) => this.matches(selector.trim()))) return this;
        return this.parentElement?.closest(selectors) ?? null;
    }
    querySelectorAll(selector) {
        return this.children.flatMap((child) => [
            ...(child.matches(selector) ? [child] : []),
            ...child.querySelectorAll(selector),
        ]);
    }
    querySelector(selector) {
        return this.querySelectorAll(selector)[0] ?? null;
    }
    addEventListener(type, callback) {
        this.listeners[type] = callback;
    }
}

const window = { location: { href: '' } };
const context = vm.createContext({
    document: { createElement: (tag) => new Element(tag), addEventListener() {} },
    window,
    api: { isEditor: () => false },
    isAuthenticated: () => false,
    splitRecipeTags,
    formatIngredientMarkup,
    generateTagChips: () => '',
    initializeRecipeTagEditor() {},
});
const source = readFileSync(new URL('../src/web/js/recipeCard.js', import.meta.url), 'utf8')
    .replace(/^import[\s\S]*?from ['"][^'"]+['"];\n/gm, '')
    .replace(/^export /gm, '');
vm.runInContext(source, context);

const note = '<script>alert(1)</script>: assumed 1 mL rinse';
for (const compact of [false, true]) {
    for (const [status, display, notes] of [
        ['calculated', '27%', []],
        ['estimated', '20–30%', ['Blanc Vermouth: 15–16%', note]],
        ['unknown', 'Unknown', ['Ingredient volume unavailable']],
        ['estimated', '<1%', []],
        ['estimated', '31%', []],
    ]) {
        const card = context.createRecipeCard(
            { id: 42, name: 'Test drink', ingredients: [], abv: { status, display, notes } },
            false,
            null,
            { compact, linkCard: compact },
        );
        const block = card.querySelector('.recipe-abv');
        assert.ok(block, 'ABV block is visible on both layouts');
        assert.equal(block.querySelector('strong').textContent, 'ABV before dilution: ');
        assert.equal(block.querySelector('span').textContent, display);
        assert.equal(
            card.children.indexOf(block),
            card.children.indexOf(card.querySelector('.recipe-meta')) + 1,
        );
        assert.equal(block.querySelector('details') !== null, notes.length > 0);
        assert.deepEqual(
            block.querySelectorAll('li').map((li) => li.textContent),
            notes,
        );
        assert.equal(block.querySelector('script'), null);
        for (const li of block.querySelectorAll('li')) assert.equal(li.markup, undefined);
        if (compact && notes.length) {
            for (const target of [block.querySelector('summary'), block.querySelector('li')]) {
                window.location.href = '';
                card.listeners.click({ target, defaultPrevented: false });
                assert.equal(window.location.href, '', 'Calculation notes must not navigate');
            }
            card.listeners.click({ target: card, defaultPrevented: false });
            assert.equal(
                window.location.href,
                '/recipe/42',
                'Rest of compact card still navigates',
            );
        }
    }
    for (const abv of [undefined, null]) {
        const card = context.createRecipeCard(
            { id: 42, name: 'Legacy', ingredients: [], abv },
            false,
            null,
            { compact },
        );
        assert.equal(card.querySelector('.recipe-abv'), null);
    }
}
console.log('Recipe ABV display contracts passed');
