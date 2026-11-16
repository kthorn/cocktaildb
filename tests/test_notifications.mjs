import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

class Element {
    constructor(tagName) {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.parentElement = null;
        this.attributes = {};
        this.dataset = {};
        this.className = '';
        this.textContent = '';
        this.listeners = {};
        this.classList = {
            add: (name) => {
                this.className = `${this.className} ${name}`.trim();
            },
            contains: (name) => this.className.split(/\s+/).includes(name),
        };
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    getAttribute(name) {
        return this.attributes[name] ?? null;
    }

    addEventListener(type, handler) {
        this.listeners[type] = handler;
    }

    append(...children) {
        children.forEach((child) => this.appendChild(child));
    }

    appendChild(child) {
        child.parentElement = this;
        this.children.push(child);
        return child;
    }

    remove() {
        if (!this.parentElement) return;
        this.parentElement.children = this.parentElement.children.filter((c) => c !== this);
        this.parentElement = null;
    }
}

function loadModule() {
    const body = new Element('body');
    const timers = new Map();
    let nextTimer = 1;
    const context = vm.createContext({
        document: { body, createElement: (tagName) => new Element(tagName) },
        setTimeout: (fn, ms) => {
            const id = nextTimer++;
            timers.set(id, { fn, ms });
            return id;
        },
        clearTimeout: (id) => timers.delete(id),
    });
    const source = readFileSync(
        new URL('../src/web/js/notifications.js', import.meta.url),
        'utf8',
    ).replace(/^export /gm, '');
    vm.runInContext(
        `${source}\nthis.notifications = { showNotification, dismissNotification };`,
        context,
    );

    const [region] = body.children;
    const [errors, statuses] = region.children;
    return {
        ...context.notifications,
        body,
        errors,
        statuses,
        pendingDelays: () => [...timers.values()].map((timer) => timer.ms),
        runTimers() {
            while (timers.size) {
                const [id, timer] = timers.entries().next().value;
                timers.delete(id);
                timer.fn();
            }
        },
    };
}

const messageOf = (notification) => notification.children[0].textContent;
const dismissButtonOf = (notification) => notification.children[1];

test('live regions exist before the first message', () => {
    const page = loadModule();

    assert.equal(page.body.children.length, 1);
    assert.equal(page.body.children[0].className, 'notification-region');
    assert.equal(page.errors.getAttribute('role'), 'alert');
    assert.equal(page.statuses.getAttribute('role'), 'status');
    assert.equal(page.errors.children.length, 0);
    assert.equal(page.statuses.children.length, 0);
});

test('errors are announced as alerts and stay until dismissed', () => {
    const page = loadModule();

    const error = page.showNotification('No ingredient named "Spirt".', 'error');

    assert.deepEqual(page.errors.children, [error]);
    assert.equal(error.className, 'notification error');
    assert.equal(messageOf(error), 'No ingredient named "Spirt".');
    assert.deepEqual(page.pendingDelays(), [], 'an error sets no auto-hide timer');

    const dismiss = dismissButtonOf(error);
    assert.equal(dismiss.getAttribute('aria-label'), 'Dismiss notification');
    dismiss.listeners.click();
    assert.ok(error.classList.contains('is-leaving'));
    page.runTimers();
    assert.deepEqual(page.errors.children, []);
});

test('success and info messages are statuses that hide themselves', () => {
    const page = loadModule();

    const success = page.showNotification('Added "Old Tom Gin".', 'success');
    const info = page.showNotification('Template downloaded');

    assert.deepEqual(page.statuses.children, [success, info]);
    assert.equal(success.className, 'notification success');
    assert.equal(info.className, 'notification info');
    assert.deepEqual(page.pendingDelays(), [5000, 5000]);

    page.runTimers();
    assert.deepEqual(page.statuses.children, []);
});

test('repeating a message replaces the earlier copy', () => {
    const page = loadModule();

    const first = page.showNotification('Name already exists', 'error');
    const second = page.showNotification('Name already exists', 'error');

    assert.notEqual(first, second);
    assert.deepEqual(page.errors.children, [second]);
});

test('each stack keeps at most four messages, dropping the oldest', () => {
    const page = loadModule();

    const shown = [1, 2, 3, 4, 5].map((n) => page.showNotification(`Error ${n}`, 'error'));
    page.runTimers();

    assert.deepEqual(page.errors.children, shown.slice(1));
});

test('dismissing twice, or dismissing nothing, is harmless', () => {
    const page = loadModule();
    const error = page.showNotification('Failed', 'error');

    page.dismissNotification(null);
    page.dismissNotification(error);
    page.dismissNotification(error);
    page.runTimers();

    assert.deepEqual(page.errors.children, []);
});

test('a status dismissed early does not leave its hide timer running', () => {
    const page = loadModule();
    const success = page.showNotification('Saved', 'success');

    page.dismissNotification(success);

    assert.deepEqual(page.pendingDelays(), [300]);
});
