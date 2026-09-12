/**
 * Format a numeric recipe amount using common kitchen fractions.
 * @param {number|null|undefined} amount
 * @returns {string}
 */
export function formatAmount(amount) {
    if (amount === null || amount === undefined) {
        return '';
    }
    if (typeof amount !== 'number' || Number.isNaN(amount)) {
        return String(amount);
    }

    const tolerance = 0.01;
    const integerPart = Math.floor(amount);
    const fractionalPart = amount - integerPart;
    if (fractionalPart < tolerance) {
        return String(integerPart);
    }

    const fractions = {
        '1/8': 1 / 8,
        '1/4': 1 / 4,
        '1/3': 1 / 3,
        '3/8': 3 / 8,
        '1/2': 1 / 2,
        '5/8': 5 / 8,
        '2/3': 2 / 3,
        '3/4': 3 / 4,
        '7/8': 7 / 8,
    };

    let bestMatch = null;
    let minDiff = tolerance;
    for (const [fraction, value] of Object.entries(fractions)) {
        const difference = Math.abs(fractionalPart - value);
        if (difference < minDiff) {
            minDiff = difference;
            bestMatch = fraction;
        }
    }

    if (1 - fractionalPart < tolerance) {
        return String(integerPart + 1);
    }
    if (bestMatch) {
        return integerPart > 0 ? `${integerPart} ${bestMatch}` : bestMatch;
    }
    return amount.toFixed(2).replace(/\.?0+$/, '');
}

/**
 * Return the display name for an ingredient payload.
 * @param {Object} ingredient
 * @returns {string}
 */
export function getIngredientName(ingredient) {
    return (
        ingredient.ingredient_name ||
        ingredient.name ||
        ingredient.full_name ||
        'Unknown ingredient'
    ).trim();
}

/**
 * Split an ingredient into the text around its semantic ingredient-name span.
 * @param {Object} ingredient
 * @returns {{prefix: string, name: string, suffix: string}}
 */
export function formatIngredientParts(ingredient) {
    const name = getIngredientName(ingredient);
    const amount = ingredient.amount;
    const unit = ingredient.unit_name;
    if (
        (unit === 'to top' || unit === 'to rinse') &&
        (amount === null || amount === undefined || amount === 0)
    ) {
        return { prefix: '', name, suffix: `, ${unit}` };
    }
    if (unit === 'each' || unit === 'Each') {
        const formattedAmount = formatAmount(amount);
        return { prefix: formattedAmount, name, suffix: '' };
    }
    const formattedAmount = formatAmount(amount);
    return {
        prefix: `${formattedAmount}${unit ? ` ${unit}` : ''}`.trim(),
        name,
        suffix: '',
    };
}

/**
 * Format the quantity and unit portion of an ingredient for a recipe card.
 * @param {Object} ingredient
 * @returns {string}
 */
export function formatIngredient(ingredient) {
    const { prefix, name, suffix } = formatIngredientParts(ingredient);
    return `${prefix ? `${prefix} ` : ''}${name}${suffix}`;
}

/**
 * Render one ingredient list item while keeping the ingredient name span
 * available for hierarchy hover behavior.
 * @param {Object} ingredient
 * @returns {string}
 */
export function formatIngredientMarkup(ingredient) {
    const { prefix, name, suffix } = formatIngredientParts(ingredient);
    return `<li>${prefix ? `${prefix} ` : ''}<span class="ingredient-name" data-ingredient-path="${ingredient.ingredient_path || ''}">${name}</span>${suffix}</li>`;
}
