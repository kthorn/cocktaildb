import assert from 'node:assert/strict';
import { execFile, spawn } from 'node:child_process';
import { once } from 'node:events';
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
import { promisify } from 'node:util';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
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

async function assertRequiredManifestValidation() {
    const artifact = await mkdtemp(path.join(tmpdir(), 'cocktaildb-required-manifest-'));
    try {
        const assets = path.join(artifact, 'web', 'assets');
        await mkdir(assets, { recursive: true });
        const files = ['normalize.css', 'styles.css', 'recipe-card.css', 'common.js', 'recipe.js'];
        for (const file of files) await writeFile(path.join(assets, file), file);
        await writeFile(
            path.join(artifact, 'asset-inventory.json'),
            JSON.stringify({ version: 1, files: [...files].sort() }),
        );
        const manifest = {
            'normalize.css': { file: 'assets/normalize.css' },
            'styles.css': { file: 'assets/styles.css' },
            'recipe-card.css': { file: 'assets/recipe-card.css' },
            'js/common.js': { file: 'assets/common.js' },
            'js/recipe.js': { file: 'assets/recipe.js' },
        };
        for (const [label, mutate, message] of [
            [
                'missing required entry',
                (value) => delete value['normalize.css'],
                /required manifest entry/,
            ],
            [
                'missing required file',
                (value) => {
                    value['styles.css'].file = '';
                },
                /must be a non-empty string/,
            ],
            [
                'missing required asset',
                (value) => {
                    value['styles.css'].file = 'assets/not-in-inventory.css';
                },
                /absent from asset inventory/,
            ],
            [
                'wrong required type',
                (value) => {
                    value['recipe-card.css'].file = 'assets/common.js';
                },
                /must reference CSS/,
            ],
        ]) {
            const candidate = structuredClone(manifest);
            mutate(candidate);
            await writeFile(path.join(artifact, 'manifest.json'), JSON.stringify(candidate));
            await assert.rejects(() => validateArtifact(artifact), message, label);
        }
    } finally {
        await rm(artifact, { recursive: true, force: true });
    }
}

async function assertManifestReferenceValidation() {
    const artifact = await mkdtemp(path.join(tmpdir(), 'cocktaildb-artifact-'));
    try {
        const assets = path.join(artifact, 'web', 'assets');
        await mkdir(assets, { recursive: true });
        const requiredFiles = [
            'normalize.css',
            'styles.css',
            'recipe-card.css',
            'common.js',
            'recipe.js',
        ];
        for (const file of [...requiredFiles, 'main.js'])
            await writeFile(path.join(assets, file), '');
        await writeFile(
            path.join(artifact, 'asset-inventory.json'),
            JSON.stringify({ version: 1, files: [...requiredFiles, 'main.js'].sort() }),
        );
        const requiredManifest = {
            'normalize.css': { file: 'assets/normalize.css' },
            'styles.css': { file: 'assets/styles.css' },
            'recipe-card.css': { file: 'assets/recipe-card.css' },
            'js/common.js': { file: 'assets/common.js' },
            'js/recipe.js': { file: 'assets/recipe.js' },
        };
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
                JSON.stringify({
                    ...requiredManifest,
                    entry: { file: 'assets/main.js', [field]: value },
                }),
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

async function serveDirectory(directory) {
    const server = createServer(async (request, response) => {
        const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
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

async function reservePort() {
    const server = createServer();
    await new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(0, '127.0.0.1', resolve);
    });
    const address = server.address();
    assert(address && typeof address === 'object');
    const port = address.port;
    await new Promise((resolve) => server.close(resolve));
    return port;
}

function captureProcess(child) {
    let output = '';
    for (const stream of [child.stdout, child.stderr]) {
        stream?.setEncoding('utf8');
        stream?.on('data', (chunk) => {
            output += chunk;
        });
    }
    child.once('error', () => {});
    return () => output;
}

async function waitForExit(child, timeout = 10_000) {
    if (child.exitCode !== null || child.signalCode !== null)
        return { code: child.exitCode, signal: child.signalCode };
    const exit = once(child, 'exit').then(([code, signal]) => ({ code, signal }));
    const timer = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('child process did not exit in time')), timeout).unref();
    });
    return Promise.race([exit, timer]);
}

async function stopProcess(child) {
    if (!child || child.exitCode !== null || child.signalCode !== null) return;
    const signal = (name) => {
        try {
            if (child.processGroup) process.kill(-child.pid, name);
            else child.kill(name);
        } catch (error) {
            if (error.code !== 'ESRCH') throw error;
        }
    };
    signal('SIGTERM');
    try {
        await waitForExit(child, 5_000);
    } catch {
        signal('SIGKILL');
        await waitForExit(child, 5_000);
    }
}

async function waitForHttp(url, child, output, label) {
    let lastError;
    for (let attempt = 0; attempt < 200; attempt += 1) {
        if (child.exitCode !== null || child.signalCode !== null) {
            throw new Error(`${label} exited before serving ${url}\n${output()}`);
        }
        try {
            return await fetch(url, { signal: AbortSignal.timeout(250) });
        } catch (error) {
            lastError = error;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(`${label} did not serve ${url}: ${lastError?.message}\n${output()}`);
}

async function assertViteProxyBoundaries() {
    const fixture = await mkdtemp(path.join(tmpdir(), 'cocktaildb-vite-proxy-'));
    const upstreamRequests = [];
    const upstream = createServer((request, response) => {
        const pathname = new URL(request.url ?? '/', 'http://127.0.0.1').pathname;
        upstreamRequests.push(pathname);
        response.writeHead(200, { 'content-type': 'text/plain' });
        response.end(`stub:${pathname}`);
    });
    let vite;
    try {
        await cp(path.join(repository, 'src'), path.join(fixture, 'src'), {
            recursive: true,
            filter: (source) => !source.endsWith(path.join('js', 'config.js')),
        });
        await symlink(path.join(repository, 'node_modules'), path.join(fixture, 'node_modules'));
        const upstreamPort = await new Promise((resolve, reject) => {
            upstream.once('error', reject);
            upstream.listen(0, '127.0.0.1', () => resolve(upstream.address().port));
        });
        const viteConfig = await readFile(path.join(repository, 'vite.config.mjs'), 'utf8');
        assert(viteConfig.includes('http://localhost:8001'));
        await writeFile(
            path.join(fixture, 'vite.config.mjs'),
            viteConfig.replace('http://localhost:8001', `http://127.0.0.1:${upstreamPort}`),
        );
        const port = await reservePort();
        vite = spawn(
            process.execPath,
            [
                path.join(fixture, 'node_modules', 'vite', 'bin', 'vite.js'),
                '--host',
                '127.0.0.1',
                '--port',
                String(port),
                '--strictPort',
            ],
            { cwd: fixture, stdio: ['ignore', 'pipe', 'pipe'] },
        );
        const output = captureProcess(vite);
        await waitForHttp(`http://127.0.0.1:${port}/recipes.html`, vite, output, 'Vite dev server');

        const staticFiles = [
            ['/recipes.html', 'recipes.html'],
            ['/ingredients.html', 'ingredients.html'],
            ['/recipe-card.css', 'recipe-card.css'],
            ['/ingredient-chart.css', 'ingredient-chart.css'],
            ['/ingredient-tree.css', 'ingredient-tree.css'],
        ];
        for (const [urlPath, sourceName] of staticFiles) {
            const response = await fetch(`http://127.0.0.1:${port}${urlPath}`);
            assert.equal(response.status, 200, urlPath);
            const body = await response.text();
            const source = await readFile(path.join(fixture, 'src', 'web', sourceName), 'utf8');
            const marker = source
                .split(/\r?\n/)
                .find((line) => line.trim())
                ?.trim();
            assert(marker && body.includes(marker), `${urlPath} was not served from source`);
            assert(!body.includes('stub:'), `${urlPath} was forwarded to the SSR stub`);
        }

        const proxiedPaths = ['/recipe/test-slug', '/ingredient/test-slug'];
        for (const urlPath of proxiedPaths) {
            const response = await fetch(`http://127.0.0.1:${port}${urlPath}`);
            assert.equal(response.status, 200, urlPath);
            assert.equal(await response.text(), `stub:${urlPath}`);
        }
        assert.deepEqual(upstreamRequests.sort(), proxiedPaths.sort());
    } finally {
        await stopProcess(vite);
        await new Promise((resolve) => upstream.close(resolve));
        await rm(fixture, { recursive: true, force: true });
    }
}

const previewFiles = ['normalize.css', 'styles.css', 'recipe-card.css', 'common.js', 'recipe.js'];

async function createPreviewFixture(port) {
    const fixture = await mkdtemp(path.join(tmpdir(), 'cocktaildb-preview-'));
    const assets = path.join(fixture, 'dist', 'web', 'assets');
    await mkdir(assets, { recursive: true });
    await mkdir(path.join(fixture, 'scripts'), { recursive: true });
    await cp(
        path.join(repository, 'scripts', 'frontend-artifact.mjs'),
        path.join(fixture, 'scripts', 'frontend-artifact.mjs'),
    );
    await symlink(path.join(repository, 'node_modules'), path.join(fixture, 'node_modules'));
    await writeFile(
        path.join(fixture, 'package.json'),
        JSON.stringify({
            private: true,
            scripts: { preview: 'node scripts/frontend-artifact.mjs preview dist' },
        }),
    );
    await writeFile(
        path.join(fixture, 'vite.config.mjs'),
        `export default { preview: { host: '127.0.0.1', port: ${port}, strictPort: true } };\n`,
    );
    await writeFile(
        path.join(fixture, 'dist', 'web', 'index.html'),
        '<!doctype html><h1>preview</h1>\n',
    );
    for (const file of previewFiles) await writeFile(path.join(assets, file), file);
    await writeFile(
        path.join(fixture, 'dist', 'asset-inventory.json'),
        JSON.stringify({ version: 1, files: [...previewFiles].sort() }),
    );
    const manifest = Object.fromEntries(
        [
            ['normalize.css', 'normalize.css'],
            ['styles.css', 'styles.css'],
            ['recipe-card.css', 'recipe-card.css'],
            ['js/common.js', 'common.js'],
            ['js/recipe.js', 'recipe.js'],
        ].map(([name, file]) => [name, { file: `assets/${file}` }]),
    );
    await writeFile(path.join(fixture, 'dist', 'manifest.json'), JSON.stringify(manifest));
    await writeFile(
        path.join(fixture, 'config.js'),
        'export default { apiUrl: "https://positional.invalid" };\n',
    );
    await writeFile(
        path.join(fixture, 'env-config.js'),
        'export default { apiUrl: "https://environment.invalid" };\n',
    );
    return fixture;
}

function spawnPreview(fixture, args, extraEnv = {}) {
    const npmArgs = ['run', 'preview'];
    if (args.length > 0) npmArgs.push('--', ...args);
    const child = spawn('npm', npmArgs, {
        cwd: fixture,
        env: { ...process.env, ...extraEnv },
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: true,
    });
    child.processGroup = true;
    const output = captureProcess(child);
    return { child, output };
}

async function assertPreviewConfigSelection(args, extraEnv, expectedText) {
    const port = await reservePort();
    const fixture = await createPreviewFixture(port);
    let preview;
    try {
        preview = spawnPreview(fixture, args, extraEnv);
        const response = await waitForHttp(
            `http://127.0.0.1:${port}/js/config.js`,
            preview.child,
            preview.output,
            'Vite preview',
        );
        assert.equal(response.status, 200);
        assert.match(await response.text(), new RegExp(expectedText));
    } finally {
        if (preview) await stopProcess(preview.child);
        await rm(fixture, { recursive: true, force: true });
    }
}

async function assertPreviewArgumentContract() {
    await assertPreviewConfigSelection(['config.js'], {}, 'positional\\.invalid');
    await assertPreviewConfigSelection(
        [],
        { FRONTEND_PREVIEW_CONFIG: 'env-config.js' },
        'environment\\.invalid',
    );

    const port = await reservePort();
    const fixture = await createPreviewFixture(port);
    try {
        const preview = spawnPreview(fixture, ['dist']);
        const result = await waitForExit(preview.child);
        assert.notEqual(result.code, 0);
        assert.match(preview.output(), /preview config must be a regular file/);
    } finally {
        await rm(fixture, { recursive: true, force: true });
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

function assertRuntimeConfigValues(source, config) {
    const match = source.match(/^export default (\{[\s\S]*\});\s*$/);
    assert(match, 'runtime config must be a JSON default export');
    const actual = JSON.parse(match[1]);
    for (const field of ['apiUrl', 'userPoolId', 'clientId', 'cognitoDomain'])
        assert.equal(actual[field], config[field], `runtime config ${field}`);
}

function assertSuccessfulArtifactFetch(response, reference) {
    assert.equal(response.status, 200, `built artifact reference ${reference}`);
}

function artifactReferences(html) {
    return [
        ...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi),
        ...html.matchAll(/<link\b[^>]*\b(?:href|src)=["']([^"']+)["'][^>]*>/gi),
    ].map((match) => match[1]);
}

async function assertConfiguredCopiesArtifactFetch(fixture, baseline) {
    const copies = await mkdtemp(path.join(tmpdir(), 'cocktaildb-artifact-copies-'));
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

            const running = await serveDirectory(served);
            servers.push(running.server);
            const configResponse = await fetch(`${running.url}/js/config.js`);
            assertSuccessfulArtifactFetch(configResponse, '/js/config.js');
            assertRuntimeConfigValues(await configResponse.text(), config);

            for (const pagePath of [
                '/',
                '/search.html',
                '/analytics.html',
                '/login.html',
                '/callback.html',
                '/logout.html',
            ]) {
                const response = await fetch(`${running.url}${pagePath}`);
                assertSuccessfulArtifactFetch(response, pagePath);
                const html = await response.text();
                if (pagePath === '/analytics.html')
                    assert.equal(html.split('https://d3js.org/d3.v7.min.js').length - 1, 1);
                for (const reference of artifactReferences(html)) {
                    if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(reference)) continue;
                    const assetResponse = await fetch(new URL(reference, `${running.url}/`).href);
                    assertSuccessfulArtifactFetch(assetResponse, `${pagePath} ${reference}`);
                }
            }
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

async function assertArtifactAssertionMutations(fixture, baseline) {
    const copies = await mkdtemp(path.join(tmpdir(), 'cocktaildb-artifact-mutations-'));
    const config = runtimeConfigs[0];
    const served = path.join(copies, 'copy');
    let server;
    try {
        await cp(path.join(fixture, 'dist', 'web'), served, { recursive: true });
        await mkdir(path.join(served, 'js'), { recursive: true });
        await writeFile(
            path.join(served, 'js', 'config.js'),
            `export default ${JSON.stringify(config)};\n`,
        );
        assertStableSnapshots(baseline, await snapshotTree(path.join(served, 'assets')));
        const running = await serveDirectory(served);
        server = running.server;
        const configSource = await (await fetch(`${running.url}/js/config.js`)).text();

        for (const [field, replacement] of [
            ['apiUrl', 'https://wrong-api.invalid'],
            ['clientId', 'wrong-client-id'],
        ]) {
            const mutatedSource = configSource.replace(config[field], replacement);
            assert.notEqual(mutatedSource, configSource, `${field} mutation applied`);
            assert.throws(
                () => assertRuntimeConfigValues(mutatedSource, config),
                new RegExp(`runtime config ${field}`),
            );
        }

        const missingReference = `/assets/missing-${baseline.names[0]}`;
        const missingResponse = await fetch(`${running.url}${missingReference}`);
        assert.throws(
            () => assertSuccessfulArtifactFetch(missingResponse, missingReference),
            /built artifact reference/,
        );
    } finally {
        if (server) await new Promise((resolve) => server.close(resolve));
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
    await assertRequiredManifestValidation();
    await assertManifestReferenceValidation();
    await assertNodeModuleModes();
    await assertViteProxyBoundaries();
    await assertPreviewArgumentContract();
    const fixture = await createFixture();
    try {
        const originalCss = await readFile(path.join(fixture, 'src', 'web', 'styles.css'));
        const originalJs = await readFile(path.join(fixture, 'src', 'web', 'js', 'common.js'));
        const baseline = await buildTwiceAndCheck(fixture);
        await assertConfiguredCopiesArtifactFetch(fixture, baseline);
        await assertArtifactAssertionMutations(fixture, baseline);
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
