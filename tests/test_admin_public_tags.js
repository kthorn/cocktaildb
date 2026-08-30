const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeElement {
    constructor(tagName = 'div') {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.parentNode = null;
        this.className = '';
        this.style = {};
        this.disabled = false;
        this.listeners = {};
        this._textContent = '';
        this.innerHTMLAssignments = [];
        this.dataset = new Proxy({}, {
            set: (target, property, value) => {
                target[property] = String(value);
                return true;
            },
        });
    }

    get firstChild() {
        return this.children[0] || null;
    }

    get textContent() {
        return this._textContent + this.children.map(child => child.textContent).join('');
    }

    set textContent(value) {
        this._textContent = String(value);
        this.children = [];
    }

    set innerHTML(value) {
        this.innerHTMLAssignments.push(value);
        this._textContent = '';
        this.children = [];
        parseMarkup(String(value), this);
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    append(...items) {
        items.forEach(item => {
            if (typeof item === 'string') {
                this._textContent += item;
            } else {
                this.appendChild(item);
            }
        });
    }

    insertBefore(child, before) {
        child.parentNode = this;
        const index = this.children.indexOf(before);
        this.children.splice(index === -1 ? this.children.length : index, 0, child);
        return child;
    }

    remove() {
        if (!this.parentNode) return;
        const index = this.parentNode.children.indexOf(this);
        if (index !== -1) this.parentNode.children.splice(index, 1);
        this.parentNode = null;
    }

    addEventListener(eventName, handler) {
        this.listeners[eventName] = handler;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }

    querySelectorAll(selector) {
        const matches = [];
        const visit = element => {
            element.children.forEach(child => {
                if (matchesSelector(child, selector)) matches.push(child);
                visit(child);
            });
        };
        visit(this);
        return matches;
    }

    closest(selector) {
        let element = this;
        while (element) {
            if (matchesSelector(element, selector)) return element;
            element = element.parentNode;
        }
        return null;
    }
}

function matchesSelector(element, selector) {
    if (selector.startsWith('.')) {
        return element.className.split(/\s+/).includes(selector.slice(1));
    }
    return element.tagName === selector.toUpperCase();
}

function parseMarkup(markup, parent) {
    const tokens = markup.match(/<[^>]+>|[^<]+/g) || [];
    const stack = [parent];
    for (const token of tokens) {
        if (token.startsWith('</')) {
            if (stack.length > 1) stack.pop();
            continue;
        }
        if (!token.startsWith('<')) {
            stack[stack.length - 1]._textContent += token;
            continue;
        }

        const match = token.match(/^<([a-z][\w-]*)([^>]*)>/i);
        if (!match) continue;
        const element = new FakeElement(match[1]);
        const attributes = match[2];
        const classMatch = attributes.match(/class="([^"]*)"/);
        if (classMatch) element.className = classMatch[1];
        for (const [, name, value] of attributes.matchAll(/(data-[\w-]+)="([^"]*)"/g)) {
            element.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = value;
        }
        stack[stack.length - 1].appendChild(element);
        if (!['IMG', 'INPUT', 'BR', 'HR', 'META', 'LINK'].includes(element.tagName)) {
            stack.push(element);
        }
    }
}

const sourcePath = path.join(__dirname, '..', 'src', 'web', 'js', 'admin.js');
const source = fs.readFileSync(sourcePath, 'utf8').replace(/^import .*;\n/gm, '') + `
this.testExports = { loadPublicTags, handleDeletePublicTag };
`;

const tagsList = new FakeElement('div');
const refreshButton = new FakeElement('button');
const document = {
    body: new FakeElement('body'),
    createElement: tagName => new FakeElement(tagName),
    getElementById: id => ({
        'public-tags-list': tagsList,
        'refresh-tags-btn': refreshButton,
    }[id] || null),
    querySelector: () => null,
    addEventListener: () => {},
};

const context = vm.createContext({
    document,
    api: {
        getPublicTags: async () => [{
            id: 7,
            name: '<img src=x onerror=alert(1)>',
            usage_count: 1,
        }],
    },
    isAuthenticated: () => true,
    initAuth: async () => {},
    console,
    setTimeout: () => {},
});
vm.runInContext(source, context, { filename: sourcePath });

(async () => {
    await context.testExports.loadPublicTags();

    assert.equal(tagsList.innerHTMLAssignments.length, 0, 'public tags must render without innerHTML');
    const item = tagsList.querySelector('.tag-management-item');
    assert.ok(item, 'a tag row should be rendered');
    const name = item.querySelector('.tag-management-name');
    assert.equal(name.textContent, '<img src=x onerror=alert(1)>');
    assert.equal(name.querySelector('img'), null, 'markup in a tag name must not become an element');

    const deleteButton = item.querySelector('.delete-tag-btn');
    assert.equal(deleteButton.dataset.tagId, '7');
    assert.equal(deleteButton.dataset.tagName, '<img src=x onerror=alert(1)>');
    assert.equal(item.querySelector('.tag-management-usage').textContent, 'Used in 1 recipe');

    console.log('Public tag rendering contract passed');
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
