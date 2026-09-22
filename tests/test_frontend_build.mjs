import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import {
    access,
    appendFile,
    cp,
    mkdir,
    mkdtemp,
    readFile,
    readdir,
    rm,
    symlink,
    writeFile,
} from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { validateArtifact } from '../scripts/frontend-artifact.mjs';

const execFileAsync = promisify(execFile);
const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sentinelValues = ['https://sentinel.invalid', 'sentinel-client-id'];
const runtimeConfigs = [
    {
        apiUrl: 'https://dev.example/api',
        userPoolId: 'dev-pool',
        clientId: 'dev-client',
        cognitoDomain: 'https://dev.example.auth',
        appUrl: 'http://localhost:8000',
        appName: 'Cocktail Database (dev)',
    },
    {
        apiUrl: 'https://prod.example/api',
        userPoolId: 'prod-pool',
        clientId: 'prod-client',
        cognitoDomain: 'https://prod.example.auth',
        appUrl: 'https://prod.example',
        appName: 'Cocktail Database (prod)',
    },
];

async function exists(file) {
    try {
        await access(file);
        return true;
    } catch {
        return false;
    }
}

async function copyIfPresent(source, destination, options = {}) {
    if (await exists(source)) await cp(source, destination, options);
}

async function assertManifestReferenceValidation() {
    const artifact = await mkdtemp(path.join(tmpdir(), 'cocktaildb-artifact-'));
    try {
        const assets = path.join(artifact, 'web', 'assets');
        await mkdir(assets, { recursive: true });
        await writeFile(path.join(assets, 'main.js'), '');
        await writeFile(
            path.join(artifact, 'asset-inventory.json'),
            JSON.stringify({ version: 1, files: ['main.js'] }),
        );
        const invalidEntries = [
            { field: 'imports', value: 'entry', message: /must be an array/ },
            { field: 'dynamicImports', value: 'entry', message: /must be an array/ },
            { field: 'imports', value: [42], message: /is invalid/ },
            { field: 'dynamicImports', value: [42], message: /is invalid/ },
            {
                field: 'imports',
                value: ['missing'],
                message: /references missing manifest entry/,
            },
            {
                field: 'dynamicImports',
                value: ['missing'],
                message: /references missing manifest entry/,
            },
        ];
        for (const { field, value, message } of invalidEntries) {
            await writeFile(
                path.join(artifact, 'manifest.json'),
                JSON.stringify({ entry: { file: 'assets/main.js', [field]: value } }),
            );
            await assert.rejects(() => validateArtifact(artifact), message);
        }
    } finally {
        await rm(artifact, { recursive: true, force: true });
    }
}

async function createFixture() {
    const fixture = await mkdtemp(path.join(tmpdir(), 'cocktaildb-vite-'));
    await cp(path.join(repository, 'src'), path.join(fixture, 'src'), {
        recursive: true,
        filter: (source) => !source.endsWith(path.join('js', 'config.js')),
    });
    await copyIfPresent(path.join(repository, 'package.json'), path.join(fixture, 'package.json'));
    await copyIfPresent(
        path.join(repository, 'package-lock.json'),
        path.join(fixture, 'package-lock.json'),
    );
    await copyIfPresent(
        path.join(repository, 'vite.config.mjs'),
        path.join(fixture, 'vite.config.mjs'),
    );
    await copyIfPresent(
        path.join(repository, 'scripts', 'frontend-artifact.mjs'),
        path.join(fixture, 'scripts', 'frontend-artifact.mjs'),
    );
    if (await exists(path.join(repository, 'node_modules'))) {
        await symlink(path.join(repository, 'node_modules'), path.join(fixture, 'node_modules'));
    }
    return fixture;
}

async function runBuild(fixture) {
    try {
        await execFileAsync('npm', ['run', 'build'], { cwd: fixture, maxBuffer: 10 * 1024 * 1024 });
    } catch (error) {
        throw new Error(`fixture build failed\n${error.stdout ?? ''}${error.stderr ?? ''}`, {
            cause: error,
        });
    }
}

async function listFiles(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    const files = [];
    for (const entry of entries) {
        const fullPath = path.join(directory, entry.name);
        if (entry.isDirectory()) {
            files.push(...(await listFiles(fullPath)).map((name) => path.join(entry.name, name)));
        } else if (entry.isFile()) {
            files.push(entry.name);
        } else {
            throw new Error(`unexpected non-regular asset: ${fullPath}`);
        }
    }
    return files.sort();
}

async function snapshotTree(directory) {
    const names = await listFiles(directory);
    const bytes = new Map();
    for (const name of names) bytes.set(name, await readFile(path.join(directory, name)));
    return { names, bytes };
}

async function snapshotAssets(fixture) {
    return snapshotTree(path.join(fixture, 'dist', 'web', 'assets'));
}

function assertStableSnapshots(first, second) {
    assert.deepEqual(second.names, first.names);
    for (const name of first.names)
        assert.deepEqual(second.bytes.get(name), first.bytes.get(name), name);
}

async function assertLocalReferencesExist(fixture) {
    const web = path.join(fixture, 'dist', 'web');
    const htmlFiles = (await readdir(web, { withFileTypes: true }))
        .filter((entry) => entry.isFile() && entry.name.endsWith('.html'))
        .map((entry) => entry.name);
    assert.notEqual(htmlFiles.length, 0);

    for (const htmlFile of htmlFiles) {
        const html = await readFile(path.join(web, htmlFile), 'utf8');
        const references = [
            ...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi),
            ...html.matchAll(/<link\b[^>]*\brel=["']stylesheet["'][^>]*\bhref=["']([^"']+)["']/gi),
            ...html.matchAll(/<link\b[^>]*\bhref=["']([^"']+)["'][^>]*\brel=["']stylesheet["']/gi),
        ].map((match) => match[1]);
        for (const reference of references) {
            if (reference === '/js/config.js') continue;
            if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(reference)) continue;
            const url = new URL(reference, 'http://fixture.invalid/');
            assert.equal(url.origin, 'http://fixture.invalid');
            const relative = decodeURIComponent(url.pathname).replace(/^\//, '');
            await access(path.join(web, relative));
        }
    }
}

async function assertPublicFiles(fixture) {
    const web = path.join(fixture, 'dist', 'web');
    for (const name of ['robots.txt', 'llms.txt', 'site.webmanifest']) {
        await access(path.join(web, name));
    }

    const manifest = JSON.parse(await readFile(path.join(web, 'site.webmanifest'), 'utf8'));
    assert(Array.isArray(manifest.icons));
    for (const icon of manifest.icons) {
        assert.equal(typeof icon.src, 'string');
        const iconUrl = new URL(icon.src, 'http://fixture.invalid/site.webmanifest');
        assert.equal(iconUrl.origin, 'http://fixture.invalid');
        await access(path.join(web, decodeURIComponent(iconUrl.pathname).replace(/^\//, '')));
    }
}

async function assertConfigExternalized(fixture) {
    const assets = await snapshotAssets(fixture);
    const javascript = assets.names.filter((name) => name.endsWith('.js'));
    assert.notEqual(javascript.length, 0);
    let configImportFound = false;
    for (const name of javascript) {
        const source = assets.bytes.get(name).toString('utf8');
        for (const match of source.matchAll(/["']([^"']*config\.js)["']/g)) {
            assert.equal(match[1], '/js/config.js', `${name} external config import`);
            configImportFound = true;
        }
        for (const sentinel of sentinelValues)
            assert(!source.includes(sentinel), `${name} embeds ${sentinel}`);
    }
    assert(configImportFound, 'built JavaScript has no external config import');
    await assert.rejects(access(path.join(fixture, 'dist', 'web', 'js', 'config.js')));
}

async function assertSentinelConfigExternalized(fixture) {
    const web = path.join(fixture, 'dist', 'web');
    const textFiles = (await listFiles(web)).filter((name) => /\.(?:html|js|css)$/i.test(name));
    let configImportFound = false;
    for (const name of textFiles) {
        const source = await readFile(path.join(web, name), 'utf8');
        for (const sentinel of sentinelValues)
            assert(!source.includes(sentinel), `${name} embeds ${sentinel}`);
        if (source.includes('/js/config.js')) configImportFound = true;
    }
    assert(configImportFound, 'sentinel build has no external config import');
    await assert.rejects(access(path.join(web, 'js', 'config.js')));
}

async function assertInventory(fixture) {
    const inventory = JSON.parse(
        await readFile(path.join(fixture, 'dist', 'asset-inventory.json'), 'utf8'),
    );
    assert.equal(inventory.version, 1);
    assert.deepEqual(inventory.files, [...inventory.files].sort());
    assert(inventory.files.some((name) => name.endsWith('.js')));
    assert(inventory.files.some((name) => name.endsWith('.css')));
    const assets = await snapshotAssets(fixture);
    assert.deepEqual(inventory.files, assets.names);
    return inventory;
}

function assertChangedAssetNames(before, after, extension) {
    const original = before.names.filter((name) => name.endsWith(extension));
    const changed = after.names.filter((name) => name.endsWith(extension));
    assert.notDeepEqual(changed, original, `${extension} asset names did not change`);
}

async function serveDirectory(directory, { routes = {} } = {}) {
    const server = createServer(async (request, response) => {
        const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
        const route = routes[pathname];
        if (route !== undefined) {
            response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
            response.end(route);
            return;
        }
        const relativePath = pathname.replace(/^\/+/, '') || 'index.html';
        const root = path.resolve(directory);
        const file = path.resolve(root, relativePath);
        if (file !== root && !file.startsWith(`${root}${path.sep}`)) {
            response.writeHead(403);
            response.end();
            return;
        }
        try {
            const content = await readFile(file);
            response.writeHead(200);
            response.end(content);
        } catch {
            response.writeHead(404);
            response.end();
        }
    });
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const address = server.address();
    return {
        server,
        url: `http://127.0.0.1:${address.port}`,
    };
}

async function assertRuntimeConfigCopies(fixture, baseline) {
    const copies = await mkdtemp(path.join(tmpdir(), 'cocktaildb-config-copies-'));
    const configs = runtimeConfigs;
    const servers = [];
    try {
        for (const [index, config] of configs.entries()) {
            const served = path.join(copies, `copy-${index}`);
            await cp(path.join(fixture, 'dist', 'web'), served, { recursive: true });
            await mkdir(path.join(served, 'js'), { recursive: true });
            await writeFile(
                path.join(served, 'js', 'config.js'),
                `export default ${JSON.stringify(config)};\n`,
            );
            assertStableSnapshots(baseline, await snapshotTree(path.join(served, 'assets')));

            const running = await serveDirectory(served);
            servers.push(running.server);
            const configResponse = await fetch(`${running.url}/js/config.js`);
            assert.equal(configResponse.status, 200);
            const configSource = await configResponse.text();
            assert(configSource.includes(config.apiUrl));
            assert(configSource.includes(config.userPoolId));
            assert(configSource.includes(config.clientId));
            assert(configSource.includes(config.cognitoDomain));

            const assetName = baseline.names[0];
            const assetResponse = await fetch(`${running.url}/assets/${assetName}`);
            assert.equal(assetResponse.status, 200);
            assert.deepEqual(
                Buffer.from(await assetResponse.arrayBuffer()),
                baseline.bytes.get(assetName),
            );
        }
    } finally {
        await Promise.all(
            servers.map(
                (server) =>
                    new Promise((resolve) => {
                        server.close(resolve);
                    }),
            ),
        );
        await rm(copies, { recursive: true, force: true });
    }
}

async function assertNodeModuleModes() {
    const packageJson = JSON.parse(await readFile(path.join(repository, 'package.json'), 'utf8'));
    assert.equal(packageJson.type, undefined, 'root package must remain typeless');
    await execFileAsync(process.execPath, ['tests/test_frontend_ingredient_display.js'], {
        cwd: repository,
    });
    await execFileAsync(process.execPath, ['tests/test_static_frontend_head.mjs'], {
        cwd: repository,
    });
}

function createStorage() {
    const values = new Map();
    return {
        getItem(key) {
            return values.has(key) ? values.get(key) : null;
        },
        setItem(key, value) {
            values.set(key, String(value));
        },
        removeItem(key) {
            values.delete(key);
        },
    };
}

function runtimeReferences(html) {
    return [
        ...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi),
        ...html.matchAll(/<link\b[^>]*\b(?:href|src)=["']([^"']+)["'][^>]*>/gi),
    ].map((match) => match[1]);
}

async function exerciseRuntimeModules(runtimeRoot, config, serverUrl, index) {
    const modules = path.join(runtimeRoot, 'runtime-modules');
    await mkdir(modules, { recursive: true });
    await cp(path.join(repository, 'src', 'web', 'js', 'api.js'), path.join(modules, 'api.js'));
    await cp(path.join(repository, 'src', 'web', 'js', 'auth.js'), path.join(modules, 'auth.js'));
    await writeFile(path.join(modules, 'config.js'), `export default ${JSON.stringify(config)};\n`);

    const requests = [];
    const globals = ['fetch', 'localStorage', 'sessionStorage', 'window', 'document'];
    const previous = new Map(
        globals.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]),
    );
    const localStorage = createStorage();
    const sessionStorage = createStorage();
    globalThis.fetch = async (url) => {
        requests.push(String(url));
        return new Response(
            JSON.stringify({
                recipes: [],
                pagination: { page: 1, limit: 20, total_count: 0, has_next: false },
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
        );
    };
    globalThis.localStorage = localStorage;
    globalThis.sessionStorage = sessionStorage;
    globalThis.window = {
        location: { origin: serverUrl, href: `${serverUrl}/index.html`, search: '' },
        history: { replaceState() {} },
    };
    globalThis.document = {};

    try {
        const suffix = `?copy=${index}`;
        const auth = await import(`${pathToFileURL(path.join(modules, 'auth.js')).href}${suffix}`);
        const { api } = await import(
            `${pathToFileURL(path.join(modules, 'api.js')).href}${suffix}`
        );

        await api.getStats();
        await api.searchRecipes({ name: 'negroni' });
        await api.getIngredientUsageAnalytics({ parent_id: 7 });
        assert.deepEqual(
            requests.map((url) => {
                const parsed = new URL(url);
                return `${parsed.pathname}${parsed.search}`;
            }),
            [
                '/api/stats',
                '/api/recipes/search?page=1&limit=20&sort_by=name&sort_order=asc&q=negroni',
                '/api/analytics/ingredient-usage?parent_id=7',
            ],
        );
        assert(requests.every((url) => url.startsWith(`${config.apiUrl}/`)));

        await auth.startLogin();
        const loginUrl = new URL(window.location.href);
        assert.equal(loginUrl.origin, config.cognitoDomain);
        assert.equal(loginUrl.pathname, '/login');
        assert.equal(loginUrl.searchParams.get('client_id'), config.clientId);
        assert.equal(loginUrl.searchParams.get('redirect_uri'), `${serverUrl}/callback.html`);

        window.location.search = '?code=invalid&state=wrong';
        await assert.rejects(auth.completeLogin(), /Invalid or expired login response/);

        auth.logout();
        const logoutUrl = new URL(window.location.href);
        assert.equal(logoutUrl.origin, config.cognitoDomain);
        assert.equal(logoutUrl.pathname, '/logout');
        assert.equal(logoutUrl.searchParams.get('client_id'), config.clientId);
        assert.equal(logoutUrl.searchParams.get('logout_uri'), `${serverUrl}/logout.html`);
    } finally {
        for (const [name, descriptor] of previous) {
            if (descriptor) Object.defineProperty(globalThis, name, descriptor);
            else delete globalThis[name];
        }
    }
}

async function assertConfiguredCopiesRuntimeContract(fixture, baseline) {
    const copies = await mkdtemp(path.join(tmpdir(), 'cocktaildb-runtime-copies-'));
    const manifest = JSON.parse(
        await readFile(path.join(fixture, 'dist', 'manifest.json'), 'utf8'),
    );
    const assetUrl = (key) => `/assets/${manifest[key].file.replace(/^assets\//, '')}`;
    const commonAssetName = manifest['js/common.js'].file.replace(/^assets\//, '');
    // The Python page suite covers real Jinja SSR; these proxy responses verify
    // the same built asset URLs remain valid from nested paths in both copies.
    const ssrRoutes = {
        '/recipe/42': `<link rel="stylesheet" href="${assetUrl('normalize.css')}"><script type="module" src="${assetUrl('js/common.js')}"></script><script type="module" src="${assetUrl('js/recipe.js')}"></script>`,
        '/ingredient/7': `<link rel="stylesheet" href="${assetUrl('normalize.css')}"><script type="module" src="${assetUrl('js/common.js')}"></script>`,
    };
    const servers = [];
    try {
        for (const [index, config] of runtimeConfigs.entries()) {
            const served = path.join(copies, `copy-${index}`);
            await cp(path.join(fixture, 'dist', 'web'), served, { recursive: true });
            await mkdir(path.join(served, 'js'), { recursive: true });
            await writeFile(
                path.join(served, 'js', 'config.js'),
                `export default ${JSON.stringify(config)};\n`,
            );
            assertStableSnapshots(baseline, await snapshotTree(path.join(served, 'assets')));

            const running = await serveDirectory(served, { routes: ssrRoutes });
            servers.push(running.server);
            const pagePaths = [
                '/',
                '/search.html',
                '/analytics.html',
                '/login.html',
                '/callback.html',
                '/logout.html',
            ];
            for (const pagePath of pagePaths) {
                const response = await fetch(`${running.url}${pagePath}`);
                assert.equal(response.status, 200, pagePath);
                const html = await response.text();
                const moduleScripts = [
                    ...html.matchAll(
                        /<script\b[^>]*\btype=["']module["'][^>]*\bsrc=["']([^"']+)["']/gi,
                    ),
                ].map((match) => match[1]);
                assert.equal(moduleScripts.length, 1, `${pagePath} module entry count`);
                assert(!/<script\b[^>]*type=["']module["'][^>]*>\s*import\b/i.test(html));
                for (const reference of runtimeReferences(html)) {
                    if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(reference)) continue;
                    const assetResponse = await fetch(new URL(reference, `${running.url}/`).href);
                    assert.equal(assetResponse.status, 200, `${pagePath} ${reference}`);
                }
                const entrySource = await (
                    await fetch(new URL(moduleScripts[0], `${running.url}/`))
                ).text();
                assert.equal(
                    entrySource.split(commonAssetName).length - 1,
                    1,
                    `${pagePath} common initialization import`,
                );
                if (pagePath === '/analytics.html') {
                    assert.equal(html.split('https://d3js.org/d3.v7.min.js').length - 1, 1);
                }
            }
            for (const nestedPath of Object.keys(ssrRoutes)) {
                const response = await fetch(`${running.url}${nestedPath}`);
                assert.equal(response.status, 200, nestedPath);
                for (const reference of runtimeReferences(await response.text())) {
                    const assetResponse = await fetch(new URL(reference, `${running.url}/`).href);
                    assert.equal(assetResponse.status, 200, `${nestedPath} ${reference}`);
                }
            }
            const configResponse = await fetch(`${running.url}/js/config.js`);
            assert.equal(configResponse.status, 200);
            const configSource = await configResponse.text();
            for (const value of [
                config.apiUrl,
                config.userPoolId,
                config.clientId,
                config.cognitoDomain,
            ])
                assert(configSource.includes(value));
            await exerciseRuntimeModules(served, config, running.url, index);
        }
    } finally {
        await Promise.all(
            servers.map(
                (server) =>
                    new Promise((resolve) => {
                        server.close(resolve);
                    }),
            ),
        );
        await rm(copies, { recursive: true, force: true });
    }
}

async function assertConfigIsNotStaged() {
    await execFileAsync('git', ['check-ignore', '--no-index', '-q', 'src/web/js/config.js'], {
        cwd: repository,
    });
    const { stdout } = await execFileAsync(
        'git',
        ['diff', '--cached', '--name-only', '--', 'src/web/js/config.js'],
        { cwd: repository },
    );
    assert.equal(stdout.trim(), '');
}

async function buildTwiceAndCheck(fixture) {
    await runBuild(fixture);
    const first = await snapshotAssets(fixture);
    const firstArtifact = await snapshotTree(path.join(fixture, 'dist'));
    const firstInventory = await assertInventory(fixture);
    await assertLocalReferencesExist(fixture);
    await assertPublicFiles(fixture);
    await assertConfigExternalized(fixture);

    await runBuild(fixture);
    const second = await snapshotAssets(fixture);
    const secondArtifact = await snapshotTree(path.join(fixture, 'dist'));
    const secondInventory = await assertInventory(fixture);
    assert.deepEqual(secondInventory, firstInventory);
    assertStableSnapshots(first, second);
    assertStableSnapshots(firstArtifact, secondArtifact);
    return first;
}

async function main() {
    await assertManifestReferenceValidation();
    await assertNodeModuleModes();
    const fixture = await createFixture();
    try {
        const originalCss = await readFile(path.join(fixture, 'src', 'web', 'styles.css'));
        const originalJs = await readFile(path.join(fixture, 'src', 'web', 'js', 'common.js'));
        const baseline = await buildTwiceAndCheck(fixture);
        await assertRuntimeConfigCopies(fixture, baseline);
        await assertConfiguredCopiesRuntimeContract(fixture, baseline);
        await assertConfigIsNotStaged();

        const sentinelConfig = path.join(fixture, 'src', 'web', 'js', 'config.js');
        await writeFile(
            sentinelConfig,
            `export default {
    apiUrl: '${sentinelValues[0]}',
    clientId: '${sentinelValues[1]}',
};
`,
        );
        await runBuild(fixture);
        await assertSentinelConfigExternalized(fixture);
        await rm(sentinelConfig, { force: true });

        await appendFile(
            path.join(fixture, 'src', 'web', 'styles.css'),
            '\n.fixture-build-change { color: rgb(1, 2, 3); }\n',
        );
        await runBuild(fixture);
        assertChangedAssetNames(baseline, await snapshotAssets(fixture), '.css');
        await writeFile(path.join(fixture, 'src', 'web', 'styles.css'), originalCss);

        await writeFile(
            path.join(fixture, 'src', 'web', 'js', 'common.js'),
            Buffer.concat([
                originalJs,
                Buffer.from("\ndocument.documentElement.dataset.fixtureBuildChange = 'changed';\n"),
            ]),
        );
        await runBuild(fixture);
        assertChangedAssetNames(baseline, await snapshotAssets(fixture), '.js');
    } finally {
        await rm(fixture, { recursive: true, force: true });
    }
}

await main();
