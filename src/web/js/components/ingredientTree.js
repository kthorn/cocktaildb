/**
 * Shared helpers for rendering ingredient parent/child trees.
 *
 * The admin and inventory pages intentionally provide different row content,
 * so this module owns the data structure and recursive list traversal only.
 */

/**
 * Return the identifier used by either public ingredient records or user
 * inventory records.
 *
 * @param {Object} ingredient
 * @returns {number|string|undefined}
 */
export function getIngredientId(ingredient) {
    return ingredient?.ingredient_id ?? ingredient?.id;
}

/**
 * Build a sorted hierarchy from flat ingredient records.
 *
 * Records whose parent is absent from the supplied collection remain roots.
 * Each node is copied, including its children array, so sorting and adding
 * hierarchy metadata never mutate API response objects.
 *
 * @param {Array<Object>} ingredients
 * @returns {Array<Object>}
 */
export function buildHierarchy(ingredients = []) {
    const ingredientMap = new Map();

    ingredients.forEach((ingredient) => {
        const id = getIngredientId(ingredient);
        if (id === undefined || id === null) return;
        ingredientMap.set(id, { ...ingredient, children: [] });
    });

    const roots = [];
    ingredients.forEach((ingredient) => {
        const id = getIngredientId(ingredient);
        const node = ingredientMap.get(id);
        if (!node) return;

        const parentId = ingredient.parent_id;
        if (
            parentId !== undefined &&
            parentId !== null &&
            parentId !== id &&
            ingredientMap.has(parentId)
        ) {
            ingredientMap.get(parentId).children.push(node);
        } else {
            roots.push(node);
        }
    });

    sortHierarchy(roots);
    return roots;
}

function sortHierarchy(nodes) {
    nodes.sort((left, right) => String(left.name ?? '').localeCompare(String(right.name ?? '')));
    nodes.forEach((node) => sortHierarchy(node.children));
}

/**
 * Render a hierarchy's nested list structure while delegating row markup to
 * the page that owns the tree. The callback receives the node and its level.
 *
 * @param {Array<Object>} hierarchy
 * @param {(ingredient: Object, context: {childrenHTML: string, hasChildren: boolean, level: number}) => string} renderNode
 * @param {Object} options
 * @param {string} [options.rootClass='hierarchy-root']
 * @param {string} [options.childrenClass='hierarchy-children']
 * @returns {string}
 */
export function renderHierarchyHTML(hierarchy, renderNode, options = {}) {
    if (!Array.isArray(hierarchy) || hierarchy.length === 0) return '';

    const rootClass = options.rootClass || 'hierarchy-root';
    const childrenClass = options.childrenClass || 'hierarchy-children';

    const renderLevel = (nodes, level) => {
        const listClass = level === 0 ? rootClass : childrenClass;
        const items = nodes
            .map((ingredient) => {
                const children = ingredient.children || [];
                const childrenHTML = children.length ? renderLevel(children, level + 1) : '';
                return renderNode(ingredient, {
                    childrenHTML,
                    hasChildren: children.length > 0,
                    level,
                });
            })
            .join('');
        return `<ul class="${listClass}">${items}</ul>`;
    };

    return renderLevel(hierarchy, 0);
}
