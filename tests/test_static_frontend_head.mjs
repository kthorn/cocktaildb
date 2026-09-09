import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { test } from 'node:test';

const webRoot = new URL('../src/web/', import.meta.url);
for (const file of readdirSync(webRoot).filter((name) => name.endsWith('.html'))) {
    test(`${file} provides metadata and styles before JavaScript runs`, () => {
        const html = readFileSync(new URL(file, webRoot), 'utf8');
        const head = html.match(/<head>([\s\S]*?)<\/head>/)[1];
        assert.equal((head.match(/<meta charset=/g) || []).length, 1);
        assert.equal((head.match(/name="viewport"/g) || []).length, 1);
        for (const href of [
            '/normalize.css',
            '/styles.css',
            '/img/favicon.svg',
            '/site.webmanifest',
        ]) {
            assert.ok(head.includes(`href="${href}"`), `missing ${href}`);
        }
        assert.ok(head.indexOf('/normalize.css') < head.indexOf('/styles.css'));
        assert.doesNotMatch(head, /visibility\s*:\s*hidden|onload=|onerror=/);
    });
}
