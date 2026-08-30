const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeElement {
    constructor(tagName = 'div') {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.className = '';
        this.style = {};
        this.value = '';
        this.files = [];
        this.disabled = false;
        this._textContent = '';
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

    append(...children) {
        children.forEach((child) => {
            if (typeof child === 'string') {
                const text = new FakeElement('#text');
                text.textContent = child;
                child = text;
            }
            this.appendChild(child);
        });
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    insertBefore(child) {
        child.parentNode = this;
        this.children.unshift(child);
        return child;
    }

    replaceChildren(...children) {
        this.children = [];
        this._textContent = '';
        this.append(...children);
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

class FakeFileReader {
    readAsText() {
        this.onload({ target: { result: 'ingredient_id,ingredient_name,field,value\n' } });
    }
}

const sourcePath = path.join(__dirname, '..', 'src', 'web', 'js', 'admin.js');
const source =
    fs.readFileSync(sourcePath, 'utf8').replace(/^import .*;\n/gm, '') +
    `\nthis.testExports = { getIngredientValueUploadConfig, handleBulkValueUpload };\n`;

const fileInput = new FakeElement('input');
fileInput.files = [{ name: 'values.csv' }];
fileInput.value = 'values.csv';
const uploadButton = new FakeElement('button');
const progress = new FakeElement('div');
progress.appendChild(new FakeElement('p'));
const results = new FakeElement('div');
const mainSection = new FakeElement('section');

const elements = {
    'ingredient-value-file-input': fileInput,
    'upload-ingredient-values-btn': uploadButton,
    'ingredient-value-upload-progress': progress,
    'ingredient-value-upload-results': results,
};
const document = {
    body: new FakeElement('body'),
    createElement: (tagName) => new FakeElement(tagName),
    getElementById: (id) => elements[id] || null,
    querySelector: (selector) => (selector === 'main section' ? mainSection : null),
    addEventListener: () => {},
};
const conflict = new Error('Ingredient values conflict with curated data');
conflict.detail = [
    'Bitter; Orange (53): percent_abv is 25, CSV requested 28',
    'Aperol (42): sugar_g_per_l is 200, CSV requested 234',
];
const context = vm.createContext({
    document,
    FileReader: FakeFileReader,
    api: { bulkUploadIngredientValues: async () => Promise.reject(conflict) },
    console: { ...console, error: () => {} },
    setTimeout: () => {},
});
vm.runInContext(source, context, { filename: sourcePath });

(async () => {
    const config = context.testExports.getIngredientValueUploadConfig();
    await context.testExports.handleBulkValueUpload(config);

    const errorBlock = results.querySelector('.error-results');
    assert.ok(errorBlock, 'ingredient value conflicts use upload error result styling');
    assert.equal(errorBlock.querySelector('h5').textContent, 'Validation Errors:');
    assert.deepEqual(
        errorBlock.querySelectorAll('li').map((item) => item.textContent),
        [
            'Bitter; Orange (53): percent_abv is 25, CSV requested 28',
            'Aperol (42): sugar_g_per_l is 200, CSV requested 234',
        ],
    );

    console.log('Ingredient value conflict rendering contract passed');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
