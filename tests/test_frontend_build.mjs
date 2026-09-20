import assert from 'node:assert/strict';
import {
    access,
    appendFile,
    cp,
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
import { fileURLToPath } from 'node:url';

const execFileAsync = promisify(execFile);
const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sentinelValues = ['https://sentinel.invalid', 'sentinel-client-id'];

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
    const fixture = await createFixture();
    try {
        const originalCss = await readFile(path.join(fixture, 'src', 'web', 'styles.css'));
        const originalJs = await readFile(path.join(fixture, 'src', 'web', 'js', 'common.js'));
        const baseline = await buildTwiceAndCheck(fixture);

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
