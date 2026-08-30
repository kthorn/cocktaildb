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
    const client = new CocktailAPI('/api');
    client.isEditor = () => true;
    client._request = async (...args) => args;

    assert.deepEqual(
        await client.bulkUploadIngredientValues('ingredient_id,ingredient_name,field,value\n'),
        ['/ingredients/bulk-values', 'POST', 'ingredient_id,ingredient_name,field,value\n'],
    );

    const options = client.getFetchOptions('GET', 'a,b\n1,2\n');
    assert.equal(options.headers['Content-Type'], 'text/csv');
    assert.equal(options.body, 'a,b\n1,2\n');

    await assert.rejects(
        client.handleResponse({
            status: 409,
            url: '/ingredients/bulk-values',
            json: async () => ({
                error: 'Ingredient values conflict with curated data',
                detail: ['Campari (53): percent_abv is 25, CSV requested 28'],
            }),
        }),
        (error) =>
            error.message === 'Ingredient values conflict with curated data' &&
            error.detail.length === 1 &&
            error.detail[0] === 'Campari (53): percent_abv is 25, CSV requested 28',
    );

    console.log('bulk ingredient value API test passed');
} finally {
    if (createdConfig) await unlink(configUrl);
}
