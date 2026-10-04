import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { NAV_CONFIG, getCurrentPageId, isNavItemActive } from '../src/web/js/navigation.js';

const recipeCardSource = readFileSync(
    new URL('../src/web/js/recipeCard.js', import.meta.url),
    'utf8',
);
assert.match(
    recipeCardSource,
    /window\.location\.href = `\/recipes\.html\?edit=\$\{recipe\.id\}`;/,
    'recipe edit navigation must target the root recipes page',
);

const items = [...NAV_CONFIG.primary, ...NAV_CONFIG.secondary, ...NAV_CONFIG.admin];
assert.equal(NAV_CONFIG.primary.filter((item) => item.mobileBottom).length, 5);
assert.equal(NAV_CONFIG.primary.find((item) => item.id === 'my-bar').href, '/groups.html');
assert.equal(
    NAV_CONFIG.primary.find((item) => item.id === 'my-ingredients').shortLabel,
    'Ingredients',
);
for (const base of ['/search.html', '/recipe/42', '/ingredient/7']) {
    for (const item of items) {
        const destination = new URL(item.href, `https://example.com${base}`);
        assert.equal(
            destination.pathname,
            `/${item.href.split('/').pop()}`,
            `${item.id} navigation from ${base} must reach the root page`,
        );
    }
}
for (const item of items) {
    globalThis.window = {
        location: { pathname: new URL(item.href, 'https://example.com').pathname },
    };
    assert.equal(getCurrentPageId(), item.id);
    assert.equal(isNavItemActive(item), true);
}
globalThis.window.location.pathname = '/';
assert.equal(getCurrentPageId(), 'home');
globalThis.window.location.pathname = '/recipe/42';
assert.equal(getCurrentPageId(), null);
console.log('Navigation paths and active states passed');
