const CALLOUT_HEIGHT = 13;
const CALLOUT_CANDIDATES = [10, 22, 34, 46, 58, 70].flatMap(distance => [
    { dx: distance, dy: 4, anchor: 'start', distance },
    { dx: distance, dy: -distance, anchor: 'start', distance },
    { dx: 0, dy: -distance, anchor: 'middle', distance },
    { dx: -distance, dy: -distance, anchor: 'end', distance },
    { dx: -distance, dy: 4, anchor: 'end', distance },
    { dx: -distance, dy: distance + CALLOUT_HEIGHT, anchor: 'end', distance },
    { dx: 0, dy: distance + CALLOUT_HEIGHT, anchor: 'middle', distance },
    { dx: distance, dy: distance + CALLOUT_HEIGHT, anchor: 'start', distance },
]);

export function placeCallouts(points, width, height, getTextWidth) {
    const occupied = [];
    const positioned = [];

    for (const point of points) {
        const textWidth = getTextWidth(point.recipe_name);
        for (const candidate of CALLOUT_CANDIDATES) {
            const labelX = point.calloutX + candidate.dx;
            const labelY = point.calloutY + candidate.dy;
            const left = candidate.anchor === 'start'
                ? labelX
                : candidate.anchor === 'end'
                    ? labelX - textWidth
                    : labelX - textWidth / 2;
            const box = {
                left,
                right: left + textWidth,
                top: labelY - CALLOUT_HEIGHT,
                bottom: labelY + 2,
            };
            const inside = box.left >= 2 && box.right <= width - 2 &&
                box.top >= 2 && box.bottom <= height - 2;
            const overlaps = occupied.some(other =>
                box.left < other.right + 3 && box.right + 3 > other.left &&
                box.top < other.bottom + 3 && box.bottom + 3 > other.top
            );
            if (inside && !overlaps) {
                const placement = { ...point, ...candidate, labelX, labelY, box };
                occupied.push(box);
                positioned.push(placement);
                break;
            }
        }
    }

    return positioned;
}
