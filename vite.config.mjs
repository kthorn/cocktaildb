import { readdirSync } from 'node:fs';
import { rename } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const projectRoot = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.join(projectRoot, 'src', 'web');
const runtimeConfigSpecifier = './config.js';
const runtimeConfigImporters = new Set(
    ['js/api.js', 'js/auth.js'].map((entry) => path.join(webRoot, entry)),
);

const htmlEntries = readdirSync(webRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.html'))
    .map((entry) => [entry.name, path.join(webRoot, entry.name)]);
const explicitEntries = [
    'normalize.css',
    'styles.css',
    'recipe-card.css',
    'js/common.js',
    'js/recipe.js',
].map((entry) => [entry, path.join(webRoot, entry)]);
const outputDirectory = path.join(projectRoot, 'dist', 'web');
const ssrProxyTarget = 'http://localhost:8001';

export default defineConfig({
    server: {
        proxy: {
            '/recipe/': { target: ssrProxyTarget },
            '/ingredient/': { target: ssrProxyTarget },
            '/sitemap.xml': { target: ssrProxyTarget },
        },
    },
    plugins: [
        {
            name: 'move-frontend-manifest',
            async closeBundle() {
                await rename(
                    path.join(outputDirectory, 'manifest.json'),
                    path.join(projectRoot, 'dist', 'manifest.json'),
                );
            },
        },
    ],
    root: webRoot,
    appType: 'mpa',
    publicDir: path.join(webRoot, 'public'),
    build: {
        outDir: outputDirectory,
        emptyOutDir: true,
        manifest: 'manifest.json',
        rolldownOptions: {
            makeAbsoluteExternalsRelative: false,
            input: Object.fromEntries([...htmlEntries, ...explicitEntries]),
            external(source, importer) {
                return (
                    source === runtimeConfigSpecifier &&
                    importer !== undefined &&
                    runtimeConfigImporters.has(path.normalize(importer))
                );
            },
            output: {
                paths: {
                    [runtimeConfigSpecifier]: '/js/config.js',
                    [path.join(webRoot, 'js', 'config.js')]: '/js/config.js',
                },
            },
        },
    },
});
