import assert from 'node:assert/strict';

import {
    formatAmount,
    formatIngredient,
    formatIngredientMarkup,
    formatIngredientParts,
} from '../src/web/js/utils/recipeIngredients.js';
import { deduplicateRecipeTags, generateTagChips } from '../src/web/js/components/recipeTags.js';
import { buildRecipeShareUrl } from '../src/web/js/components/recipeShare.js';

assert.equal(formatAmount(1.5), '1 1/2');
assert.equal(
    formatIngredient({ ingredient_name: 'Gin', amount: 1.5, unit_name: 'oz' }),
    '1 1/2 oz Gin',
);
assert.equal(
    formatIngredient({ ingredient_name: 'Lemon', amount: 0, unit_name: 'to top' }),
    'Lemon, to top',
);
assert.deepEqual(
    formatIngredientParts({ ingredient_name: 'Lemon', amount: 0, unit_name: 'to rinse' }),
    { prefix: '', name: 'Lemon', suffix: ', to rinse' },
);
assert.equal(
    formatIngredientMarkup({ ingredient_name: 'Lemon', amount: 0, unit_name: 'to top' }),
    '<li><span class="ingredient-name" data-ingredient-path="">Lemon</span>, to top</li>',
);
assert.equal(
    formatIngredientMarkup({ ingredient_name: 'Bitters', amount: null, unit_name: 'as needed' }),
    '<li>as needed <span class="ingredient-name" data-ingredient-path="">Bitters</span></li>',
);

const tags = deduplicateRecipeTags([
    { id: 1, name: 'classic', type: 'public' },
    { id: 1, name: 'classic', type: 'public' },
    { id: 2, name: 'personal', type: 'private' },
    { id: 3, name: ' ', type: 'public' },
]);
assert.deepEqual(
    tags.map((tag) => tag.id),
    [1, 2],
);
assert.match(
    generateTagChips(tags, { recipeId: 9, shouldShowActions: true }),
    /data-recipe-id="9"/,
);
assert.doesNotMatch(
    generateTagChips(tags, { recipeId: 9, shouldShowActions: false }),
    /tag-remove-btn/,
);

assert.equal(
    buildRecipeShareUrl('Gin Fizz', 42, 'https://example.test'),
    'https://example.test/recipe/42',
);
assert.equal(
    buildRecipeShareUrl('Gin Fizz', null, 'https://example.test'),
    'https://example.test/recipe/by-name?name=Gin%20Fizz',
);

// Exercise card refresh wiring with an authenticated non-editor, not just the chip helper.
const { readFileSync } = await import('node:fs');
const { default: vm } = await import('node:vm');
const { splitRecipeTags, updateTagVisibility } =
    await import('../src/web/js/components/recipeTags.js');
const makeElement = () => ({
    innerHTML: '',
    dataset: {},
    classList: { toggle() {} },
});
const tagsContainer = makeElement();
const placeholder = makeElement();
const addButton = makeElement();
let onTagsUpdated;
const card = {
    querySelector(selector) {
        if (selector.includes('tags-container')) return tagsContainer;
        if (selector.includes('no-tags-placeholder')) return placeholder;
        return addButton;
    },
};
const context = vm.createContext({
    document: { querySelector: () => card, addEventListener() {} },
    api: { isEditor: () => false },
    isAuthenticated: () => true,
    generateTagChips,
    splitRecipeTags,
    updateTagVisibility,
    initializeRecipeTagEditor(options) {
        onTagsUpdated = options.onTagsUpdated;
    },
});
const cardSource = readFileSync(new URL('../src/web/js/recipeCard.js', import.meta.url), 'utf8')
    .replace(/^import[\s\S]*?from ['"][^'"]+['"];\n/gm, '')
    .replace(/^export /gm, '');
vm.runInContext(cardSource, context);
onTagsUpdated(42, [{ id: 1, name: 'classic', type: 'public' }]);
assert.match(tagsContainer.innerHTML, /tag-remove-btn/);
assert.deepEqual(JSON.parse(addButton.dataset.recipeTags), [
    { id: 1, name: 'classic', type: 'public' },
]);

console.log('Recipe card module contracts passed');
