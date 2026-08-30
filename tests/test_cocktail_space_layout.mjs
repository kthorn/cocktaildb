import assert from 'node:assert/strict';
import { placeCallouts } from '../src/web/js/charts/calloutLayout.mjs';

const points = Array.from({ length: 10 }, (_, index) => ({
    recipe_id: index + 1,
    recipe_name: `Label ${index + 1}`,
    calloutX: 100,
    calloutY: 100,
}));
const labels = placeCallouts(points, 200, 200, (name) => name.length * 7);

assert.equal(labels.length, points.length);
assert.ok(
    labels.some((label) => label.distance > 10),
    'crowded labels must move away from the point',
);
for (let index = 0; index < labels.length; index += 1) {
    for (let other = index + 1; other < labels.length; other += 1) {
        assert.ok(
            labels[index].box.right + 3 <= labels[other].box.left ||
                labels[other].box.right + 3 <= labels[index].box.left ||
                labels[index].box.bottom + 3 <= labels[other].box.top ||
                labels[other].box.bottom + 3 <= labels[index].box.top,
            'placed labels must not overlap',
        );
    }
}
assert.ok(
    labels.every(
        (label) =>
            label.box.left >= 2 &&
            label.box.right <= 198 &&
            label.box.top >= 2 &&
            label.box.bottom <= 198,
    ),
);

console.log('UMAP callout layout passed');
