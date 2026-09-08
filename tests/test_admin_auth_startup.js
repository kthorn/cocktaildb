const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeElement {
    constructor(tagName = 'div', id = '', className = '') {
        this.tagName = tagName.toUpperCase();
        this.id = id;
        this.className = className;
        this.children = [];
        this.parentNode = null;
        this._textContent = '';
        this._listeners = new Map();
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

    insertAdjacentHTML() {}

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

    replaceChildren(...children) {
        this.children = [];
        children.forEach((child) => this.appendChild(child));
    }

    replaceWith(replacement) {
        if (!this.parentNode) return;
        const index = this.parentNode.children.indexOf(this);
        this.parentNode.children.splice(index, 1, replacement);
        replacement.parentNode = this.parentNode;
    }

    addEventListener(type, handler) {
        const handlers = this._listeners.get(type) || [];
        handlers.push(handler);
        this._listeners.set(type, handlers);
    }

    listenerCount(type) {
        return (this._listeners.get(type) || []).length;
    }
}

function loadScript(context, filename, replacements = {}) {
    let source = fs.readFileSync(filename, 'utf8');
    source = source.replace(/^import .*;\n/gm, '').replace(/^export /gm, '');
    for (const [pattern, replacement] of Object.entries(replacements)) {
        source = source.replace(new RegExp(pattern, 'm'), replacement);
    }
    vm.runInContext(source, context, { filename });
}

function buildHarness() {
    const elements = {};
    const register = (tagName, id = '', className = '') => {
        const element = new FakeElement(tagName, id, className);
        if (id) elements[id] = element;
        return element;
    };

    const body = register('body');
    const head = register('head');
    const adminTools = register('section', '', 'admin-tools');
    const refreshTagsButton = register('button', 'refresh-tags-btn');
    const authElements = [
        register('button', 'login-btn'),
        register('button', 'signup-btn'),
        register('button', 'logout-btn'),
        register('span', 'user-info'),
    ];
    body.append(adminTools, refreshTagsButton, ...authElements);

    const domReadyHandlers = [];
    const visibilityHandlers = [];
    const document = {
        body,
        head,
        hidden: false,
        createElement: (tagName) => register(tagName),
        getElementById: (id) => elements[id] || null,
        querySelector: (selector) => {
            if (selector === 'header')
                return body.children.find((child) => child.tagName === 'HEADER') || null;
            if (selector === '.admin-tools') return adminTools;
            return null;
        },
        addEventListener: (type, handler) => {
            if (type === 'DOMContentLoaded') domReadyHandlers.push(handler);
            if (type === 'visibilitychange') visibilityHandlers.push(handler);
        },
        dispatchEvent: () => {},
    };

    const localStorageData = new Map();
    const context = vm.createContext({
        document,
        window: { location: { origin: 'https://example.test' } },
        localStorage: {
            getItem: (key) => localStorageData.get(key) ?? null,
            removeItem: (key) => localStorageData.delete(key),
        },
        config: { cognitoDomain: 'https://auth.example.test', clientId: 'client-id' },
        setInterval: () => intervalCalls.push(true),
        setTimeout: () => {},
        console: { ...console, error: () => {} },
        api: { isEditor: () => false },
        getMobileBottomNav: () => ({ updateAuthState: () => {} }),
        getMobileHamburgerMenu: () => ({ updateAuthState: () => {} }),
        getDesktopNav: () => ({ container: null, updateAuthState: () => {} }),
        CustomEvent: class CustomEvent {},
    });
    const intervalCalls = [];

    const jsDir = path.join(__dirname, '..', 'src', 'web', 'js');
    loadScript(context, path.join(jsDir, 'auth.js'));
    loadScript(context, path.join(jsDir, 'common.js'));
    loadScript(context, path.join(jsDir, 'admin.js'));

    return {
        adminTools,
        domReadyHandlers,
        intervalCalls,
        refreshTagsButton,
        visibilityHandlers,
    };
}

(async () => {
    const harness = buildHarness();
    for (const handler of harness.domReadyHandlers) {
        await handler();
    }
    await Promise.resolve();

    assert.equal(
        harness.intervalCalls.length,
        1,
        'auth startup should install one token refresh interval',
    );
    assert.equal(
        harness.visibilityHandlers.length,
        1,
        'auth startup should install one visibility listener',
    );
    assert.equal(
        harness.refreshTagsButton.listenerCount('click'),
        1,
        'admin startup should initialize the tag refresh control',
    );
    assert.match(
        harness.adminTools.textContent,
        /Please log in to access admin tools\./,
        'admin startup should apply the permission UI',
    );

    console.log('Admin auth startup contract passed');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
