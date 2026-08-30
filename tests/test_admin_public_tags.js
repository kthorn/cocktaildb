const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeElement {
    constructor(tagName = 'div') {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.className = '';
        this._textContent = '';
        this.innerHTMLAssignments = [];
        this.dataset = new Proxy(
            {},
            {
                set: (target, property, value) => {
                    target[property] = String(value);
                    return true;
                },
            },
        );
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
        this.innerHTMLAssignments.push(value);
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    addEventListener() {}

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }

    querySelectorAll(selector) {
        const matches = [];
        const visit = (element) => {
            element.children.forEach((child) => {
                if (matchesSelector(child, selector)) matches.push(child);
                visit(child);
            });
        };
        visit(this);
        return matches;
    }
}

function matchesSelector(element, selector) {
    if (selector.startsWith('.')) {
        return element.className.split(/\s+/).includes(selector.slice(1));
    }
    return element.tagName === selector.toUpperCase();
}

const sourcePath = path.join(__dirname, '..', 'src', 'web', 'js', 'admin.js');
const source =
    fs.readFileSync(sourcePath, 'utf8').replace(/^import .*;\n/gm, '') +
    `
this.testExports = { loadPublicTags };
`;

const tagsList = new FakeElement('div');
const refreshButton = new FakeElement('button');
const document = {
    body: new FakeElement('body'),
    createElement: (tagName) => new FakeElement(tagName),
    getElementById: (id) =>
        ({
            'public-tags-list': tagsList,
            'refresh-tags-btn': refreshButton,
        })[id] || null,
    querySelector: () => null,
    addEventListener: () => {},
};

const context = vm.createContext({
    document,
    api: {
        getPublicTags: async () => [
            {
                id: 7,
                name: '<img src=x onerror=alert(1)>',
                usage_count: 1,
            },
        ],
    },
    setTimeout: () => {},
});
vm.runInContext(source, context, { filename: sourcePath });

(async () => {
    await context.testExports.loadPublicTags();

    assert.equal(
        tagsList.innerHTMLAssignments.length,
        0,
        'public tags must render without innerHTML',
    );
    const item = tagsList.querySelector('.tag-management-item');
    assert.ok(item, 'a tag row should be rendered');
    const name = item.querySelector('.tag-management-name');
    assert.equal(name.textContent, '<img src=x onerror=alert(1)>');
    assert.equal(
        name.querySelector('img'),
        null,
        'markup in a tag name must not become an element',
    );

    const deleteButton = item.querySelector('.delete-tag-btn');
    assert.equal(deleteButton.dataset.tagId, '7');
    assert.equal(deleteButton.dataset.tagName, '<img src=x onerror=alert(1)>');
    assert.equal(item.querySelector('.tag-management-usage').textContent, 'Used in 1 recipe');

    console.log('Public tag rendering contract passed');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
