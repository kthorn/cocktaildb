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
    const token = `eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.${Buffer.from(
        JSON.stringify({ exp: 41024448000000, sub: 'abv-user' }),
    ).toString('base64url')}.x`;
    const storage = new Map();
    globalThis.localStorage = {
        getItem: (key) => storage.get(key) ?? null,
        setItem: (key, value) => storage.set(key, value),
        removeItem: (key) => storage.delete(key),
    };

    const requested = [];
    globalThis.fetch = async (url) => {
        requested.push(new URL(url, 'http://test'));
        return {
            status: 200,
            url,
            json: async () => ({ recipes: [], pagination: {} }),
        };
    };
    const client = new CocktailAPI('/api/v1');

    async function lastSearch(query) {
        await client.searchRecipes(query);
        return requested.at(-1);
    }

    let url = await lastSearch({ min_abv: 0, max_abv: 15 });
    assert.equal(url.pathname, '/api/v1/recipes/search');
    assert.equal(url.searchParams.get('min_abv'), '0', 'anonymous search keeps a zero minimum');
    assert.equal(url.searchParams.get('max_abv'), '15');

    url = await lastSearch({ min_abv: null, max_abv: undefined });
    assert.equal(url.searchParams.has('min_abv'), false);
    assert.equal(url.searchParams.has('max_abv'), false);

    storage.set('token', token);
    storage.set('id_token', token);
    url = await lastSearch({ min_abv: 0, max_abv: 15 });
    assert.equal(url.pathname, '/api/v1/recipes/search/authenticated');
    assert.equal(url.searchParams.get('min_abv'), '0', 'signed-in search keeps a zero minimum');
    assert.equal(url.searchParams.get('max_abv'), '15');

    console.log('Search ABV parameters passed');
} finally {
    if (createdConfig) await unlink(configUrl);
}
