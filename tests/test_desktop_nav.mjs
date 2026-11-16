import assert from 'node:assert/strict';

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.parentNode = null;
        this.attributes = {};
        this.style = {};
        this.className = '';
        this.textContent = '';
        this.classList = { add: (name) => (this.className += ` ${name}`) };
    }
    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }
    addEventListener() {}
    appendChild(child) {
        child.remove();
        child.parentNode = this;
        this.children.push(child);
        return child;
    }
    remove() {
        if (this.parentNode) {
            const siblings = this.parentNode.children;
            siblings.splice(siblings.indexOf(this), 1);
            this.parentNode = null;
        }
    }
    replaceWith(node) {
        const parent = this.parentNode;
        if (!parent) return;
        node.remove();
        parent.children[parent.children.indexOf(this)] = node;
        node.parentNode = parent;
        this.parentNode = null;
    }
    labels() {
        const own = this.className.includes('nav-label') ? [this.textContent] : [];
        return own.concat(...this.children.map((child) => child.labels()));
    }
}

globalThis.window = { location: { pathname: '/index.html' } };
globalThis.document = {
    createElement: (tagName) => new FakeElement(tagName),
    addEventListener() {},
};

const { DesktopNav } = await import('../src/web/js/desktopNav.js');

// common.js inserts the nav into the header once, then auth checks that finish
// later (token refresh, the 30s interval, tab focus) call updateAuthState.
const header = new FakeElement('nav');
const nav = new DesktopNav();
nav.init({ isAuthenticated: false, isAdmin: false });
header.appendChild(nav.container);
assert.ok(!header.labels().includes('My Bar'));

nav.updateAuthState({ isAuthenticated: true, isAdmin: true });
assert.equal(header.children.length, 1, 'desktop nav must stay in the header after re-render');
assert.equal(header.children[0], nav.container);
for (const label of ['Home', 'Search', 'My Ingredients', 'My Bar', 'Add Recipe', 'Admin']) {
    assert.ok(header.labels().includes(label), `${label} must be shown after login`);
}

nav.updateAuthState({ isAuthenticated: true, isAdmin: true });
assert.equal(header.children.length, 1, 'repeated re-renders must not duplicate the nav');
console.log('Desktop nav re-render passed');
