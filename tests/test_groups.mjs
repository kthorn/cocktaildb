import assert from 'node:assert/strict';
import { access, unlink, writeFile } from 'node:fs/promises';

const configUrl = new URL('../src/web/js/config.js', import.meta.url);
let createdConfig = false;

try {
    await access(configUrl);
} catch {
    await writeFile(configUrl, "export default { apiUrl: '' };\n");
    createdConfig = true;
}

try {
    const { CocktailAPI } = await import('../src/web/js/api.js');
    const makeToken = (subject) =>
        `eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.${Buffer.from(
            JSON.stringify({ exp: 41024448000000, sub: subject }),
        ).toString('base64url')}.x`;
    const storage = new Map([
        ['token', makeToken('account-a')],
        ['id_token', makeToken('account-a')],
    ]);
    globalThis.localStorage = {
        getItem: (key) => storage.get(key) ?? null,
        setItem: (key, value) => storage.set(key, value),
        removeItem: (key) => storage.delete(key),
    };
    const client = new CocktailAPI('/api/v1');
    client._request = async (...args) => args;

    assert.deepEqual(await client.getMyGroup(), ['/groups/mine', 'GET', null, true]);
    assert.deepEqual(await client.createGroup('The Bar', 'Shared ingredients'), [
        '/groups',
        'POST',
        { name: 'The Bar', description: 'Shared ingredients' },
    ]);
    assert.deepEqual(await client.updateGroup(4, { name: 'Renamed', description: null }), [
        '/groups/4',
        'PUT',
        { name: 'Renamed', description: null },
    ]);
    assert.deepEqual(await client.joinGroup('ABCDEF123456'), [
        '/groups/join',
        'POST',
        { invite_code: 'ABCDEF123456' },
    ]);
    assert.deepEqual(await client.leaveGroup(4, true), [
        '/groups/4/leave',
        'POST',
        { copy_inventory: true },
    ]);
    assert.deepEqual(await client.removeGroupMember(4, 'user/with spaces'), [
        '/groups/4/members/user%2Fwith%20spaces',
        'DELETE',
    ]);
    assert.deepEqual(await client.regenerateInviteCode(4), [
        '/groups/4/invite-code/regenerate',
        'POST',
    ]);
    assert.deepEqual(await client.getGroupIngredients(4), [
        '/groups/4/ingredients',
        'GET',
        null,
        true,
    ]);
    assert.deepEqual(await client.addGroupIngredient(4, 9), [
        '/groups/4/ingredients',
        'POST',
        { ingredient_id: 9 },
    ]);
    assert.deepEqual(await client.removeGroupIngredient(4, 9), [
        '/groups/4/ingredients/9',
        'DELETE',
    ]);
    assert.deepEqual(await client.bulkAddGroupIngredients(4, [9, 10]), [
        '/groups/4/ingredients/bulk',
        'POST',
        { ingredient_ids: [9, 10] },
    ]);
    assert.deepEqual(await client.bulkRemoveGroupIngredients(4, [9, 10]), [
        '/groups/4/ingredients/bulk',
        'DELETE',
        { ingredient_ids: [9, 10] },
    ]);
    assert.deepEqual(await client.getGroupIngredientRecommendations(4, 7), [
        '/groups/4/ingredients/recommendations?limit=7',
        'GET',
        null,
        true,
    ]);
    assert.deepEqual(await client.getGroupRecommendations(4, 7), [
        '/groups/4/ingredients/recommendations?limit=7',
        'GET',
        null,
        true,
    ]);

    let fetchedOptions;
    globalThis.fetch = async (url, options) => {
        fetchedOptions = { url, options };
        return {
            status: 200,
            url,
            json: async () => ({ id: 4 }),
        };
    };
    const authenticatedClient = new CocktailAPI('/api/v1');
    await authenticatedClient.getMyGroup();
    assert.equal(fetchedOptions.url, '/api/v1/groups/mine');
    assert.equal(fetchedOptions.options.headers.Authorization.startsWith('Bearer '), true);

    class FakeElement {
        constructor(tagName = 'div') {
            this.tagName = tagName.toUpperCase();
            this.children = [];
            this.parentElement = null;
            this.attributes = {};
            this.dataset = {};
            this.className = '';
            this.style = {};
            this.disabled = false;
            this.checked = false;
            this.value = '';
            this.listeners = {};
            this._textContent = '';
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
                toggle: (name, force) => {
                    const classes = new Set(this.className.split(/\s+/).filter(Boolean));
                    if (force) classes.add(name);
                    else classes.delete(name);
                    this.className = [...classes].join(' ');
                },
            };
        }

        set textContent(value) {
            this._textContent = String(value ?? '');
            this.children = [];
        }

        get textContent() {
            return this._textContent + this.children.map((child) => child.textContent).join('');
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
            this.parentElement.children = this.parentElement.children.filter(
                (child) => child !== this,
            );
        }

        setAttribute(name, value) {
            this.attributes[name] = String(value);
            if (name === 'id') this.id = String(value);
        }

        getAttribute(name) {
            return this.attributes[name] ?? null;
        }

        addEventListener(type, handler) {
            this.listeners[type] = handler;
        }

        click() {
            return this.listeners.click?.({
                currentTarget: this,
                target: this,
                preventDefault() {},
            });
        }

        querySelector(selector) {
            return this.querySelectorAll(selector)[0] ?? null;
        }

        closest(selector) {
            let element = this;
            while (element) {
                if (
                    selector.startsWith('.') &&
                    element.className.split(/\s+/).includes(selector.slice(1))
                )
                    return element;
                element = element.parentElement;
            }
            return null;
        }

        querySelectorAll(selector) {
            const matches = [];
            const visit = (element) => {
                element.children.forEach((child) => {
                    if (
                        (selector.startsWith('#') && child.id === selector.slice(1)) ||
                        (selector.startsWith('.') &&
                            child.className.split(/\s+/).includes(selector.slice(1))) ||
                        (!selector.startsWith('#') &&
                            !selector.startsWith('.') &&
                            child.tagName === selector.toUpperCase())
                    )
                        matches.push(child);
                    visit(child);
                });
            };
            visit(this);
            return matches;
        }
    }

    const elements = new Map();
    const document = {
        createElement: (tagName) => new FakeElement(tagName),
        getElementById: (id) => elements.get(id) ?? null,
        querySelector: (selector) => {
            if (selector === '.auth-required-content') return elements.get('groups-content');
            if (selector === '.auth-required-message')
                return elements.get('inventory-auth-message');
            return null;
        },
        querySelectorAll: (selector) => document.body.querySelectorAll(selector),
        addEventListener() {},
        body: new FakeElement('body'),
    };
    const register = (id, tagName = 'div') => {
        const element = new FakeElement(tagName);
        element.id = id;
        elements.set(id, element);
        document.body.appendChild(element);
        return element;
    };

    const content = register('groups-content');
    const authMessage = register('groups-auth-message');
    const headerLogin = register('login-btn', 'button');
    const groupsLogin = register('groups-login-btn', 'button');
    const status = register('groups-status');
    const retry = register('groups-retry', 'button');
    const name = register('group-name', 'input');
    const description = register('group-description', 'textarea');
    const save = register('save-group-btn', 'button');
    const inviteCode = register('group-invite-code', 'input');
    const copyInvite = register('copy-invite-btn', 'button');
    const rotateInvite = register('rotate-invite-btn', 'button');
    const joinForm = register('join-group-form', 'form');
    const joinCode = register('join-invite-code', 'input');
    const joinButton = register('join-group-btn', 'button');
    const members = register('group-members');
    const leaveSection = register('leave-group-section');
    const leaveCopy = register('leave-copy-inventory', 'input');
    leaveCopy.checked = true;
    const leaveButton = register('leave-group-btn', 'button');

    globalThis.document = document;
    const confirmMessages = [];
    globalThis.window = {
        location: { href: '' },
        confirm: (message) => {
            confirmMessages.push(message);
            return true;
        },
    };
    Object.defineProperty(globalThis, 'navigator', {
        configurable: true,
        value: { clipboard: { writeText: async () => {} } },
    });
    globalThis.CustomEvent = class CustomEvent {
        constructor(type, options = {}) {
            this.type = type;
            this.detail = options.detail;
        }
    };

    const { GroupPage } = await import('../src/web/js/groups.js');
    const group = {
        id: 4,
        name: '<script>bar</script>',
        description: 'Description & details',
        invite_code: 'ABCDEF123456',
        members: [{ cognito_user_id: 'self', joined_at: '2026-09-08T00:00:00Z' }],
        member_count: 1,
    };
    const calls = [];
    const fakeApi = {
        getMyGroup: async () => group,
        updateGroup: async (...args) => {
            calls.push(['update', ...args]);
            return group;
        },
        joinGroup: async (...args) => {
            calls.push(['join', ...args]);
            return group;
        },
        leaveGroup: async (...args) => {
            calls.push(['leave', ...args]);
            return group;
        },
        removeGroupMember: async (...args) => {
            calls.push(['remove', ...args]);
            return { message: 'Member removed' };
        },
        regenerateInviteCode: async (...args) => {
            calls.push(['rotate', ...args]);
            return { ...group, invite_code: '123456ABCDEF' };
        },
    };
    const page = new GroupPage({ api: fakeApi, userInfo: { cognitoUserId: 'self' } });
    const originalGetMyGroup = fakeApi.getMyGroup;
    fakeApi.getMyGroup = async () => {
        throw new Error('Unable to reach the shared bar');
    };
    await page.load();
    assert.match(status.textContent, /Unable to reach/);
    assert.equal(retry.className.includes('hidden'), false, 'load failures offer retry');
    fakeApi.getMyGroup = originalGetMyGroup;
    await page.load();

    assert.equal(name.value, '<script>bar</script>');
    assert.equal(description.value, 'Description & details');
    assert.equal(inviteCode.value, 'ABCDEF123456');
    assert.equal(members.textContent.includes('<script>bar</script>'), false);
    assert.equal(leaveSection.className.includes('hidden'), true);
    assert.equal(content.className.includes('hidden'), false);
    assert.equal(authMessage.className.includes('hidden'), true);

    await page.saveGroup();
    assert.deepEqual(calls[0], [
        'update',
        4,
        { name: '<script>bar</script>', description: 'Description & details' },
    ]);
    assert.equal(save.disabled, false);

    let releaseUpdate;
    fakeApi.updateGroup = () =>
        new Promise((resolve) => {
            releaseUpdate = resolve;
        });
    const pendingSave = page.saveGroup();
    assert.equal(save.disabled, true, 'mutation controls are disabled while saving');
    releaseUpdate(group);
    await pendingSave;
    assert.equal(save.disabled, false, 'mutation controls recover after saving');

    fakeApi.updateGroup = async () => {
        throw new Error('The shared bar is no longer available');
    };
    await page.saveGroup();
    assert.match(status.textContent, /no longer available/);
    assert.equal(save.disabled, false, 'mutation controls recover after a rejected action');

    fakeApi.updateGroup = async () => {
        const error = new Error('This bar is stale');
        error.status = 403;
        throw error;
    };
    await page.saveGroup();
    assert.match(status.textContent, /This bar is stale/);
    fakeApi.updateGroup = async (...args) => {
        calls.push(['update', ...args]);
        return group;
    };

    joinCode.value = 'JOINCODE1234';
    await page.joinGroup();
    assert.deepEqual(calls[1], ['join', 'JOINCODE1234']);
    assert.match(status.textContent, /joined/i);
    assert.match(confirmMessages.at(-1), /all ingredients.*current bar.*bar.*joining/i);

    page.group = {
        ...group,
        members: [
            ...group.members,
            { cognito_user_id: 'other-member', joined_at: '2026-09-08T00:00:00Z' },
            { cognito_user_id: 'second-member', joined_at: '2026-09-08T00:00:00Z' },
        ],
        member_count: 3,
    };
    page.renderGroup();
    const kickButtons = members.querySelectorAll('.kick-member-btn');
    const kickButton = kickButtons[0];
    assert.equal(kickButtons.length, 2, 'each non-self member has a remove control');
    assert.notEqual(
        kickButtons[0].getAttribute('aria-label'),
        kickButtons[1].getAttribute('aria-label'),
        'member remove controls have distinct accessible names',
    );
    await kickButton.click();
    assert.deepEqual(
        calls.find((call) => call[0] === 'remove'),
        ['remove', 4, 'other-member'],
    );
    assert.match(confirmMessages.at(-1), /other-member/);
    assert.match(kickButton.getAttribute('aria-label'), /other-member/);

    await page.leaveGroup();
    assert.deepEqual(
        calls.find((call) => call[0] === 'leave'),
        ['leave', 4, true],
    );

    page.handleAuthChange({ isAuthenticated: false });
    assert.equal(content.className.includes('hidden'), true);
    assert.equal(authMessage.className.includes('hidden'), false);
    assert.equal(inviteCode.value, '');

    let loginClicked = false;
    headerLogin.addEventListener('click', () => {
        loginClicked = true;
    });
    page.bindEvents();
    elements.get('groups-login-btn').click();
    assert.equal(loginClicked, true, 'auth fallback uses the header login button');

    storage.delete('token');
    storage.delete('id_token');
    const identityApi = {
        ...fakeApi,
        getMyGroup: async () => ({
            ...group,
            members: [{ cognito_user_id: 'account-b', joined_at: '2026-09-08T00:00:00Z' }],
            member_count: 1,
        }),
    };
    const signedOutPage = new GroupPage({
        api: identityApi,
        userInfo: { cognitoUserId: 'account-a' },
    });
    signedOutPage.init();
    assert.match(status.textContent, /log in/i, 'signed-out pages show an auth status');

    storage.set('token', makeToken('account-b'));
    storage.set('id_token', makeToken('account-b'));
    signedOutPage.handleAuthChange({ isAuthenticated: true });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(signedOutPage.userInfo.cognitoUserId, 'account-b');
    assert.ok(
        members.querySelector('.group-member-self'),
        'signed-out to signed-in refresh marks the new principal as self',
    );

    const switchingRequests = [];
    const switchingApi = {
        ...identityApi,
        getMyGroup: () =>
            new Promise((resolve) => {
                switchingRequests.push(resolve);
            }),
    };
    storage.set('token', makeToken('account-a'));
    storage.set('id_token', makeToken('account-a'));
    const switchingPage = new GroupPage({
        api: switchingApi,
        userInfo: { cognitoUserId: 'account-a' },
    });
    switchingPage.authenticated = true;
    switchingPage.group = {
        ...group,
        invite_code: 'ACCOUNT_A_CODE',
    };
    switchingPage.renderGroup();
    const oldLoad = switchingPage.load();
    storage.set('token', makeToken('account-b'));
    storage.set('id_token', makeToken('account-b'));
    switchingPage.handleAuthChange({ isAuthenticated: true });
    assert.equal(inviteCode.value, '', 'principal changes clear the old invite immediately');
    switchingRequests[0]({ ...group, invite_code: 'ACCOUNT_A_RESPONSE' });
    await oldLoad;
    assert.equal(inviteCode.value, '', 'an in-flight old-principal response is ignored');
    switchingRequests[1]({
        ...group,
        invite_code: 'ACCOUNT_B_CODE',
        members: [{ cognito_user_id: 'account-b', joined_at: '2026-09-08T00:00:00Z' }],
        member_count: 1,
    });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(switchingPage.userInfo.cognitoUserId, 'account-b');
    assert.equal(inviteCode.value, 'ACCOUNT_B_CODE');

    // Exercise the real inventory module: an account-scoped mutation must not
    // settle into the next account's selections or status after a principal switch.
    const inventoryElementIds = [
        'ingredient-search',
        'add-selected-btn',
        'remove-selected-btn',
        'refresh-private-tags-btn',
        'refresh-recommendations-btn',
        'current-ingredients-list',
        'available-ingredients-list',
        'private-tags-list',
        'recommendations-list',
        'inventory-auth-message',
    ];
    inventoryElementIds.forEach((id) => register(id, id.includes('btn') ? 'button' : 'div'));
    elements.get('inventory-auth-message').className = 'auth-required-message hidden';

    storage.set('token', makeToken('account-a'));
    storage.set('id_token', makeToken('account-a'));
    const { api: sharedApi } = await import('../src/web/js/api.js');
    const originalInventoryApi = {
        getMyGroup: sharedApi.getMyGroup,
        getUserIngredients: sharedApi.getUserIngredients,
        getIngredients: sharedApi.getIngredients,
        getPrivateTags: sharedApi.getPrivateTags,
        getIngredientRecommendations: sharedApi.getIngredientRecommendations,
        bulkAddUserIngredients: sharedApi.bulkAddUserIngredients,
    };
    sharedApi.getMyGroup = async () => ({ name: 'Account A bar' });
    sharedApi.getUserIngredients = async () => ({ ingredients: [] });
    sharedApi.getIngredients = async () => [];
    sharedApi.getPrivateTags = async () => [];
    sharedApi.getIngredientRecommendations = async () => ({ recommendations: [] });

    const { UserIngredientsManager } = await import('../src/web/js/user-ingredients.js');
    const inventoryManager = new UserIngredientsManager();
    await inventoryManager.initPromise;
    inventoryManager.selectedToAdd.add(7);
    let releaseInventoryAdd;
    sharedApi.bulkAddUserIngredients = () =>
        new Promise((resolve) => {
            releaseInventoryAdd = resolve;
        });
    const oldPrincipalAdd = inventoryManager.addSelectedIngredients();
    await new Promise((resolve) => setImmediate(resolve));

    storage.set('token', makeToken('account-b'));
    storage.set('id_token', makeToken('account-b'));
    inventoryManager.handleAuthChange({ isAuthenticated: true });
    await new Promise((resolve) => setImmediate(resolve));
    inventoryManager.selectedToAdd.add(99);
    releaseInventoryAdd({});
    await oldPrincipalAdd;
    assert.equal(inventoryManager.principalId, 'account-b');
    assert.equal(
        inventoryManager.selectedToAdd.has(99),
        true,
        'old account mutations do not clear the new account selection',
    );
    assert.equal(
        document.body.querySelectorAll('.toast-success').length,
        0,
        'old account mutations do not show success for the new account',
    );

    Object.assign(sharedApi, originalInventoryApi);

    console.log('Groups API and page behavior passed');
} finally {
    if (createdConfig) await unlink(configUrl);
}
