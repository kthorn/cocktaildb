const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto, createHash } = require('node:crypto');
const { test } = require('node:test');
const jwt = (exp) =>
    `e30.${Buffer.from(JSON.stringify({ exp, sub: 'user', email: 'user@example.test' })).toString('base64url')}.sig`;
const future = () => Math.floor(Date.now() / 1000) + 3600;
function harness() {
    const storage = () => {
        const values = new Map();
        return {
            getItem: (key) => values.get(key) ?? null,
            setItem: (key, value) => values.set(key, String(value)),
            removeItem: (key) => values.delete(key),
        };
    };
    const calls = [];
    const context = vm.createContext({
        config: { cognitoDomain: 'https://auth.example.test', clientId: 'client' },
        localStorage: storage(),
        sessionStorage: storage(),
        crypto: webcrypto,
        TextEncoder,
        URLSearchParams,
        URL,
        atob,
        btoa,
        console,
        window: {
            location: { origin: 'https://example.test', pathname: '/callback.html', search: '' },
            history: { replaceState() {} },
        },
        document: { dispatchEvent() {} },
        CustomEvent: class {},
        fetch: async (url, options) => {
            calls.push({ url, options });
            return {
                ok: true,
                json: async () => ({
                    access_token: jwt(future()),
                    id_token: jwt(future()),
                    refresh_token: 'refresh',
                }),
            };
        },
    });
    for (const file of ['auth.js', 'api.js']) {
        const source = fs
            .readFileSync(`src/web/js/${file}`, 'utf8')
            .replace(/^import .*;\n/gm, '')
            .replace(/^export /gm, '');
        vm.runInContext(source, context);
    }
    const seed = () => {
        context.localStorage.setItem('token', jwt(1));
        context.localStorage.setItem('id_token', jwt(1));
        context.localStorage.setItem('refresh_token', 'refresh');
    };
    return { c: context, calls, seed };
}
test('login requests code with S256 PKCE and callback persists refresh token', async () => {
    const { c, calls } = harness();
    assert.equal(typeof c.startLogin, 'function');
    await c.startLogin();
    const url = new URL(c.window.location.href);
    assert.equal(url.searchParams.get('response_type'), 'code');
    assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
    c.window.location.search = `?code=authorization-code&state=${url.searchParams.get('state')}`;
    await c.completeLogin();
    const body = new URLSearchParams(calls[0].options.body);
    assert.equal(body.get('grant_type'), 'authorization_code');
    assert.equal(
        createHash('sha256').update(body.get('code_verifier')).digest('base64url'),
        url.searchParams.get('code_challenge'),
    );
    assert.equal(c.localStorage.getItem('refresh_token'), 'refresh');
    await assert.rejects(c.completeLogin());
});
test('callback rejects incorrect state without exchanging code', async () => {
    const { c, calls } = harness();
    await c.startLogin('signup');
    assert.equal(new URL(c.window.location.href).pathname, '/signup');
    c.window.location.search = '?code=code&state=wrong';
    await assert.rejects(c.completeLogin());
    assert.equal(calls.length, 0);
});
test('expired session remains refreshable and concurrent requests refresh once', async () => {
    const { c, calls, seed } = harness();
    seed();
    assert.equal(c.isAuthenticated(), true);
    await Promise.all([c.ensureSession(), c.ensureSession()]);
    assert.equal(calls.length, 1);
    assert.equal(new URLSearchParams(calls[0].options.body).get('grant_type'), 'refresh_token');
    assert.equal(c.isAuthenticated(), true);
});
test('temporary failure preserves refresh token; invalid grant clears session', async () => {
    const { c, seed } = harness();
    seed();
    c.fetch = async () => {
        throw new Error('offline');
    };
    await assert.rejects(c.ensureSession());
    assert.equal(c.localStorage.getItem('refresh_token'), 'refresh');
    c.fetch = async () => ({ ok: false, json: async () => ({ error: 'invalid_grant' }) });
    assert.equal(await c.ensureSession(), false);
    assert.equal(c.localStorage.getItem('refresh_token'), null);
    assert.equal(c.isAuthenticated(), false);
});
test('logout during refresh cannot restore session', async () => {
    const { c, seed } = harness();
    seed();
    let finish;
    c.fetch = () =>
        new Promise((resolve) => {
            finish = resolve;
        });
    const pending = c.ensureSession();
    c.logout();
    finish({
        ok: true,
        json: async () => ({ access_token: jwt(future()), id_token: jwt(future()) }),
    });
    await pending;
    assert.equal(c.localStorage.getItem('token'), null);
    assert.equal(c.localStorage.getItem('refresh_token'), null);
});
test('API refreshes before sending authenticated request', async () => {
    const { c, seed } = harness();
    seed();
    const requests = [];
    const renewed = jwt(future());
    c.fetch = async (url, options) => {
        requests.push({ url, options });
        return {
            ok: true,
            status: 200,
            json: async () =>
                url.includes('/oauth2/token') ? { access_token: renewed, id_token: renewed } : {},
        };
    };
    await vm.runInContext(
        "new CocktailAPI('https://api.example.test')._request('/test', 'POST', {})",
        c,
    );
    assert.equal(requests.length, 2);
    assert.equal(requests[1].options.headers.Authorization, `Bearer ${renewed}`);
});
test('malformed and expired legacy tokens are not authenticated', () => {
    const { c } = harness();
    c.localStorage.setItem('token', 'malformed');
    c.localStorage.setItem('id_token', 'malformed');
    assert.equal(c.isAuthenticated(), false);
    c.localStorage.setItem('token', jwt(1));
    c.localStorage.setItem('id_token', jwt(1));
    assert.equal(c.isAuthenticated(), false);
});
test('auth UI refresh notifies navigation after renewing the session', async () => {
    const { c, seed } = harness();
    seed();
    const handlers = {};
    c.document.getElementById = () => ({
        classList: { add() {}, remove() {} },
        addEventListener() {},
    });
    c.document.addEventListener = (event, handler) => {
        handlers[event] = handler;
    };
    c.setInterval = () => {};
    let notified = 0;
    c.initAuth(() => {
        notified++;
    });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(notified, 1);
});
test('valid tokens need no refresh and refresh responses can omit refresh_token', async () => {
    const { c, calls, seed } = harness();
    c.localStorage.setItem('token', jwt(future()));
    c.localStorage.setItem('id_token', jwt(future()));
    assert.equal(await c.ensureSession(), true);
    assert.equal(calls.length, 0);
    seed();
    c.fetch = async () => ({
        ok: true,
        json: async () => ({ access_token: jwt(future()), id_token: jwt(future()) }),
    });
    assert.equal(await c.ensureSession(), true);
    assert.equal(c.localStorage.getItem('refresh_token'), 'refresh');
});

test('another tab replacing the session prevents a stale refresh from overwriting it', async () => {
    const { c, seed } = harness();
    seed();
    let finish;
    c.fetch = () =>
        new Promise((resolve) => {
            finish = resolve;
        });
    const pending = c.ensureSession();
    c.localStorage.setItem('refresh_token', 'other-session');
    c.localStorage.setItem('id_token', 'other-identity');
    finish({
        ok: true,
        json: async () => ({ access_token: jwt(future()), id_token: jwt(future()) }),
    });
    assert.equal(await pending, false);
    assert.equal(c.localStorage.getItem('id_token'), 'other-identity');
    assert.equal(c.localStorage.getItem('refresh_token'), 'other-session');
});

test('expired login transactions are rejected before exchanging the code', async () => {
    const { c, calls } = harness();
    await c.startLogin();
    const transaction = JSON.parse(c.sessionStorage.getItem('oauth_transaction'));
    transaction.createdAt = Date.now() - 11 * 60 * 1000;
    c.sessionStorage.setItem('oauth_transaction', JSON.stringify(transaction));
    c.window.location.search = `?code=code&state=${transaction.state}`;
    await assert.rejects(c.completeLogin());
    assert.equal(calls.length, 0);
});

test('authenticated search refreshes before choosing its endpoint', async () => {
    const { c, seed } = harness();
    seed();
    const requests = [];
    c.fetch = async (url, options) => {
        requests.push({ url, options });
        return {
            ok: true,
            status: 200,
            json: async () =>
                url.includes('/oauth2/token')
                    ? { access_token: jwt(future()), id_token: jwt(future()) }
                    : [],
        };
    };
    await vm.runInContext("new CocktailAPI('https://api.example.test').searchRecipes({})", c);
    assert.equal(requests.length, 2);
    assert.match(requests[1].url, /\/recipes\/search\/authenticated/);
    assert.match(requests[1].options.headers.Authorization, /^Bearer /);
});
