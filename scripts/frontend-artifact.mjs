import { spawn } from 'node:child_process';
import {
    access,
    cp,
    lstat,
    mkdir,
    mkdtemp,
    readdir,
    readFile,
    rm,
    writeFile,
} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const metadataNames = new Set(['manifest.json', 'asset-inventory.json']);

function fail(message) {
    throw new Error(message);
}

async function requireDirectory(directory, label) {
    let stat;
    try {
        stat = await lstat(directory);
    } catch (error) {
        fail(`${label} is missing: ${directory}`);
    }
    if (stat.isSymbolicLink()) fail(`${label} must not be a symlink: ${directory}`);
    if (!stat.isDirectory()) fail(`${label} must be a directory: ${directory}`);
}

async function requireRegularFile(file, label) {
    let stat;
    try {
        stat = await lstat(file);
    } catch (error) {
        fail(`${label} is missing: ${file}`);
    }
    if (stat.isSymbolicLink()) fail(`${label} must not be a symlink: ${file}`);
    if (!stat.isFile()) fail(`${label} must be a regular file: ${file}`);
}

function validateRelativePath(value, label) {
    if (typeof value !== 'string' || value.length === 0)
        fail(`${label} must be a non-empty string`);
    if (value.includes('\\') || value.startsWith('/') || path.posix.isAbsolute(value)) {
        fail(`${label} is not a safe relative path: ${value}`);
    }
    const parts = value.split('/');
    if (parts.some((part) => part.length === 0 || part === '.' || part === '..')) {
        fail(`${label} contains an invalid path component: ${value}`);
    }
    if (parts.join('/') !== value || path.posix.normalize(value) !== value) {
        fail(`${label} is not normalized: ${value}`);
    }
    return value;
}

async function enumerateFiles(directory, relative = '') {
    await requireDirectory(directory, 'asset directory');
    const entries = await readdir(directory, { withFileTypes: true });
    const files = [];
    for (const entry of entries) {
        const fullPath = path.join(directory, entry.name);
        const relativePath = relative ? `${relative}/${entry.name}` : entry.name;
        const stat = await lstat(fullPath);
        if (stat.isSymbolicLink()) fail(`symlinks are not allowed in artifacts: ${relativePath}`);
        if (entry.isDirectory()) {
            files.push(...(await enumerateFiles(fullPath, relativePath)));
        } else if (entry.isFile()) {
            files.push(validateRelativePath(relativePath, 'asset path'));
        } else {
            fail(`artifact entry is not a regular file or directory: ${relativePath}`);
        }
    }
    return files;
}

async function scanWeb(directory, relative = '') {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
        const relativePath = relative ? `${relative}/${entry.name}` : entry.name;
        const fullPath = path.join(directory, entry.name);
        const stat = await lstat(fullPath);
        if (stat.isSymbolicLink()) fail(`symlinks are not allowed in artifacts: ${relativePath}`);
        if (metadataNames.has(entry.name)) {
            fail(`artifact metadata must remain outside web/: ${relativePath}`);
        }
        if (entry.isDirectory()) {
            await scanWeb(fullPath, relativePath);
        } else if (!entry.isFile()) {
            fail(`web entry is not a regular file or directory: ${relativePath}`);
        }
    }
}

function parseInventory(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        fail('asset inventory must be an object');
    }
    if (value.version !== 1) fail('asset inventory version must be 1');
    if (!Array.isArray(value.files)) fail('asset inventory files must be an array');
    const files = value.files.map((file, index) =>
        validateRelativePath(file, `inventory files[${index}]`),
    );
    if (new Set(files).size !== files.length) fail('asset inventory contains duplicate files');
    if (JSON.stringify(files) !== JSON.stringify([...files].sort())) {
        fail('asset inventory files must be sorted');
    }
    return { version: 1, files };
}

function manifestAssetPath(value, label) {
    validateRelativePath(value, label);
    if (!value.startsWith('assets/')) fail(`${label} must be beneath assets/: ${value}`);
    const relative = value.slice('assets/'.length);
    if (!relative) fail(`${label} cannot refer to the assets directory`);
    return relative;
}

function assertManifestReference(value, label, inventoryFiles, assetsDirectory) {
    const relative = manifestAssetPath(value, label);
    if (!inventoryFiles.has(relative)) fail(`${label} is absent from asset inventory: ${value}`);
    return requireRegularFile(path.join(assetsDirectory, ...relative.split('/')), label);
}

async function readJson(file, label) {
    try {
        return JSON.parse(await readFile(file, 'utf8'));
    } catch (error) {
        fail(`${label} is not valid JSON: ${error.message}`);
    }
}

async function validateManifest(file, inventoryFiles, assetsDirectory) {
    const manifest = await readJson(file, 'Vite manifest');
    if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
        fail('Vite manifest must be an object');
    }
    for (const [entryName, entry] of Object.entries(manifest)) {
        if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
            fail(`Vite manifest entry is invalid: ${entryName}`);
        }
        if ('file' in entry) {
            if (typeof entry.file !== 'string') fail(`Vite manifest file is invalid: ${entryName}`);
            await assertManifestReference(
                entry.file,
                `Vite manifest ${entryName}.file`,
                inventoryFiles,
                assetsDirectory,
            );
        }
        for (const field of ['css', 'assets']) {
            if (!(field in entry)) continue;
            if (!Array.isArray(entry[field]))
                fail(`Vite manifest ${entryName}.${field} must be an array`);
            for (const [index, reference] of entry[field].entries()) {
                if (typeof reference !== 'string') {
                    fail(`Vite manifest ${entryName}.${field}[${index}] is invalid`);
                }
                await assertManifestReference(
                    reference,
                    `Vite manifest ${entryName}.${field}[${index}]`,
                    inventoryFiles,
                    assetsDirectory,
                );
            }
        }
        for (const field of ['imports', 'dynamicImports']) {
            if (!(field in entry)) continue;
            if (!Array.isArray(entry[field]))
                fail(`Vite manifest ${entryName}.${field} must be an array`);
            for (const [index, reference] of entry[field].entries()) {
                if (typeof reference !== 'string') {
                    fail(`Vite manifest ${entryName}.${field}[${index}] is invalid`);
                }
                if (!Object.hasOwn(manifest, reference)) {
                    fail(
                        `Vite manifest ${entryName}.${field}[${index}] references missing manifest entry: ${reference}`,
                    );
                }
            }
        }
    }
}

export async function validateArtifact(directory) {
    const artifact = path.resolve(directory);
    await requireDirectory(artifact, 'artifact directory');
    const web = path.join(artifact, 'web');
    const assets = path.join(web, 'assets');
    await requireDirectory(web, 'artifact web directory');
    await scanWeb(web);
    await requireDirectory(assets, 'artifact assets directory');

    const actualFiles = (await enumerateFiles(assets)).sort();
    const inventoryPath = path.join(artifact, 'asset-inventory.json');
    await requireRegularFile(inventoryPath, 'asset inventory');
    const inventory = parseInventory(await readJson(inventoryPath, 'asset inventory'));
    if (JSON.stringify(inventory.files) !== JSON.stringify(actualFiles)) {
        fail('asset inventory does not match regular files under web/assets');
    }
    if (inventory.files.some((file) => file.endsWith('/config.js') || file === 'config.js')) {
        fail('runtime config must not be included in the asset inventory');
    }
    await requireRegularFile(path.join(artifact, 'manifest.json'), 'Vite manifest');
    await validateManifest(path.join(artifact, 'manifest.json'), new Set(inventory.files), assets);
    const config = path.join(web, 'js', 'config.js');
    if (await pathExists(config)) fail('runtime config must remain outside the reusable artifact');
    return inventory;
}

async function pathExists(file) {
    try {
        await access(file);
        return true;
    } catch {
        return false;
    }
}

export async function writeInventory(directory) {
    const artifact = path.resolve(directory);
    await requireDirectory(artifact, 'artifact directory');
    await requireDirectory(path.join(artifact, 'web'), 'artifact web directory');
    const assets = path.join(artifact, 'web', 'assets');
    await requireDirectory(assets, 'artifact assets directory');
    const files = (await enumerateFiles(assets)).sort();
    const inventory = { version: 1, files };
    await writeFile(
        path.join(artifact, 'asset-inventory.json'),
        `${JSON.stringify(inventory)}\n`,
        'utf8',
    );
    return inventory;
}

async function runPreview(directory, configArgument) {
    const artifact = path.resolve(directory);
    await validateArtifact(artifact);
    const config = path.resolve(
        configArgument ??
            process.env.FRONTEND_PREVIEW_CONFIG ??
            path.join(projectRoot, 'src', 'web', 'js', 'config.js'),
    );
    await requireRegularFile(config, 'preview config');

    const staging = await mkdtemp(path.join(os.tmpdir(), 'cocktaildb-preview-'));
    const stagedWeb = path.join(staging, 'web');
    try {
        await cp(path.join(artifact, 'web'), stagedWeb, { recursive: true });
        await mkdir(path.join(stagedWeb, 'js'), { recursive: true });
        await cp(config, path.join(stagedWeb, 'js', 'config.js'));

        const viteCli = path.join(projectRoot, 'node_modules', 'vite', 'bin', 'vite.js');
        await requireRegularFile(viteCli, 'installed Vite CLI');
        const child = spawn(process.execPath, [viteCli, 'preview', '--outDir', stagedWeb], {
            cwd: projectRoot,
            stdio: 'inherit',
        });
        const signals = ['SIGINT', 'SIGTERM'];
        const forwarders = new Map(
            signals.map((signal) => {
                const handler = () => child.kill(signal);
                process.once(signal, handler);
                return [signal, handler];
            }),
        );
        try {
            const result = await new Promise((resolve, reject) => {
                child.once('error', reject);
                child.once('exit', (code, signal) => resolve({ code, signal }));
            });
            if (result.code !== 0) {
                fail(`Vite preview exited with ${result.signal ?? `status ${result.code}`}`);
            }
        } finally {
            for (const [signal, handler] of forwarders) process.removeListener(signal, handler);
        }
    } finally {
        await rm(staging, { recursive: true, force: true });
    }
}

async function main(args) {
    const [command, directory, config] = args;
    if (!command || !directory)
        fail('usage: frontend-artifact.mjs <inventory|validate|preview> DIRECTORY [CONFIG]');
    if (command === 'inventory') {
        await writeInventory(directory);
        await validateArtifact(directory);
        return;
    }
    if (command === 'validate') {
        await validateArtifact(directory);
        return;
    }
    if (command === 'preview') {
        await runPreview(directory, config);
        return;
    }
    fail(`unknown frontend artifact command: ${command}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    main(process.argv.slice(2)).catch((error) => {
        console.error(`frontend artifact error: ${error.message}`);
        process.exitCode = 1;
    });
}
