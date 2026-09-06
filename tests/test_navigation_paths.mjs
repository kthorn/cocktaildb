import assert from 'node:assert/strict';
import { NAV_CONFIG, getCurrentPageId, isNavItemActive } from '../src/web/js/navigation.js';

const items = [...NAV_CONFIG.primary, ...NAV_CONFIG.secondary, ...NAV_CONFIG.admin];
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
