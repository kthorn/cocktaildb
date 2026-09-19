import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import {
    buildHierarchy,
    getIngredientId,
    renderHierarchyHTML,
} from '../src/web/js/components/ingredientTree.js';

test('buildHierarchy sorts every level, keeps orphans at the root, and does not mutate input', () => {
    const ingredients = [
        { id: 3, name: 'Zest', parent_id: 1 },
        { id: 1, name: 'Citrus', parent_id: null },
        { id: 4, name: 'Orphan', parent_id: 999 },
        { id: 2, name: 'Apple', parent_id: 1 },
    ];
    const original = structuredClone(ingredients);

    const hierarchy = buildHierarchy(ingredients);

    assert.deepEqual(ingredients, original);
    assert.deepEqual(
        hierarchy.map(({ id }) => id),
        [1, 4],
    );
    assert.deepEqual(
        hierarchy[0].children.map(({ id }) => id),
        [2, 3],
    );
    assert.equal(hierarchy[0].children[0].children.length, 0);
});

test('buildHierarchy supports user ingredient records and returns stable IDs', () => {
    const ingredients = [
        { ingredient_id: 20, name: 'Child', parent_id: 10 },
        { ingredient_id: 10, id: 999, name: 'Parent', parent_id: null },
    ];

    const hierarchy = buildHierarchy(ingredients);

    assert.equal(getIngredientId(hierarchy[0]), 10);
    assert.equal(hierarchy[0].children[0].ingredient_id, 20);
    assert.equal(getIngredientId({ id: 0, ingredient_id: 0 }), 0);
});

test('renderHierarchyHTML shares recursive list traversal without inline styles', () => {
    const hierarchy = buildHierarchy([
        { id: 1, name: 'Parent', parent_id: null },
        { id: 2, name: 'Child', parent_id: 1 },
    ]);

    const html = renderHierarchyHTML(
        hierarchy,
        (ingredient, { childrenHTML, hasChildren, level }) => `
            <li data-id="${ingredient.id}" data-level="${level}">
                ${hasChildren ? 'parent' : 'leaf'}${childrenHTML}
            </li>
        `,
    );

    assert.match(html, /class="hierarchy-root"/);
    assert.match(html, /class="hierarchy-children"/);
    assert.match(html, /data-level="1"/);
    assert.doesNotMatch(html, /style=/);
});

test('ingredient pages delegate tree actions and do not expose inline handlers', () => {
    const ingredientsSource = readFileSync(
        new URL('../src/web/js/ingredients.js', import.meta.url),
        'utf8',
    );

    assert.doesNotMatch(ingredientsSource, /onclick=/);
    assert.doesNotMatch(
        ingredientsSource,
        /window\.(editIngredient|deleteIngredient|toggleHierarchyItem)\s*=/,
    );
    assert.match(ingredientsSource, /ingredientsContainer\.addEventListener\(['"]click['"]/);
});
