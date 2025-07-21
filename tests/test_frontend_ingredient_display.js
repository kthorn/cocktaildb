/**
 * Frontend Ingredient Display Tests
 * Tests for formatAmount function and ingredient display logic
 * 
 * To run these tests, you'll need Node.js and a testing framework like Jest.
 * You can run them with: node test_frontend_ingredient_display.js
 */

// Mock DOM and console for Node.js environment
if (typeof document === 'undefined') {
    global.document = {
        createElement: () => ({ className: '', innerHTML: '', style: {}, appendChild: () => {} }),
        querySelector: () => null,
        addEventListener: () => {}
    };
    global.console = { log: () => {}, error: () => {} };
}

// Import or copy the formatAmount function from recipeCard.js
function formatAmount(amount) {
    if (amount === null || amount === undefined) {
        return ''; // Return empty string for null/undefined amounts
    }
    if (typeof amount !== 'number' || isNaN(amount)) {
        return String(amount); // Return as string if not a valid number
    }

    const tolerance = 0.01;
    const integerPart = Math.floor(amount);
    const fractionalPart = amount - integerPart;

    if (fractionalPart < tolerance) {
        return String(integerPart); // Whole number
    }

    const fractions = {
        '1/8': 1/8, '1/4': 1/4, '1/3': 1/3, '3/8': 3/8, '1/2': 1/2, 
        '5/8': 5/8, '2/3': 2/3, '3/4': 3/4, '7/8': 7/8
    };

    let bestMatch = null;
    let minDiff = tolerance;

    for (const [fractionStr, fractionVal] of Object.entries(fractions)) {
        const diff = Math.abs(fractionalPart - fractionVal);
        if (diff < minDiff) {
            minDiff = diff;
            bestMatch = fractionStr;
        }
    }
    
    // Check if the remainder is close to 1 (e.g. 0.995 should be next integer)
    if (1 - fractionalPart < tolerance) {
        return String(integerPart + 1);
    }

    if (bestMatch) {
        if (integerPart > 0) {
            return `${integerPart} ${bestMatch}`; // Mixed number
        } else {
            return bestMatch; // Just the fraction
        }
    } else {
        // Fallback: Round to 2 decimal places if no close fraction found
        return amount.toFixed(2).replace(/\\.?0+$/, ''); // Remove trailing zeros
    }
}

// Test function to format ingredients like the recipeCard.js logic
function formatIngredientDisplay(ingredient) {
    const ingredientName = ingredient.full_name || ingredient.ingredient_name || ingredient.name || 'Unknown ingredient';
    
    // Special handling for specific units
    if (ingredient.unit_name === 'to top' && (ingredient.amount === null || ingredient.amount === undefined)) {
        return `${ingredientName}, to top`;
    }
    if (ingredient.unit_name === 'to rinse' && (ingredient.amount === null || ingredient.amount === undefined)) {
        return `${ingredientName}, to rinse`;
    }
    if (ingredient.unit_name === 'each') {
        // For 'each' unit, don't display the unit name
        const formattedAmount = formatAmount(ingredient.amount);
        return `${formattedAmount ? formattedAmount + ' ' : ''}${ingredientName}`;
    }
    
    // Default handling for all other units
    const formattedAmount = formatAmount(ingredient.amount);
    const unitDisplay = ingredient.unit_name ? ` ${ingredient.unit_name}` : '';
    
    return `${formattedAmount}${unitDisplay} ${ingredientName}`;
}

// Test suite
class TestRunner {
    constructor() {
        this.tests = [];
        this.passed = 0;
        this.failed = 0;
    }

    test(name, testFn) {
        this.tests.push({ name, testFn });
    }

    assert(condition, message) {
        if (!condition) {
            throw new Error(message || 'Assertion failed');
        }
    }

    assertEqual(actual, expected, message) {
        if (actual !== expected) {
            throw new Error(`${message || 'Values not equal'}: expected "${expected}", got "${actual}"`);
        }
    }

    run() {
        console.log(`Running ${this.tests.length} tests...\\n`);
        
        for (const { name, testFn } of this.tests) {
            try {
                testFn.call(this);
                console.log(`✓ ${name}`);
                this.passed++;
            } catch (error) {
                console.log(`✗ ${name}: ${error.message}`);
                this.failed++;
            }
        }
        
        console.log(`\\nResults: ${this.passed} passed, ${this.failed} failed`);
        return this.failed === 0;
    }
}

// Create test runner
const runner = new TestRunner();

// Tests for formatAmount function
runner.test('formatAmount handles null', function() {
    this.assertEqual(formatAmount(null), '');
});

runner.test('formatAmount handles undefined', function() {
    this.assertEqual(formatAmount(undefined), '');
});

runner.test('formatAmount handles zero', function() {
    this.assertEqual(formatAmount(0), '0');
});

runner.test('formatAmount handles whole numbers', function() {
    this.assertEqual(formatAmount(1), '1');
    this.assertEqual(formatAmount(2), '2');
    this.assertEqual(formatAmount(10), '10');
});

runner.test('formatAmount handles common fractions', function() {
    this.assertEqual(formatAmount(0.25), '1/4');
    this.assertEqual(formatAmount(0.5), '1/2');
    this.assertEqual(formatAmount(0.75), '3/4');
    this.assertEqual(formatAmount(0.33), '1/3');
});

runner.test('formatAmount handles mixed numbers', function() {
    this.assertEqual(formatAmount(1.5), '1 1/2');
    this.assertEqual(formatAmount(2.25), '2 1/4');
    this.assertEqual(formatAmount(3.75), '3 3/4');
});

runner.test('formatAmount handles non-numeric inputs', function() {
    this.assertEqual(formatAmount('abc'), 'abc');
    this.assertEqual(formatAmount(NaN), 'NaN');
});

// Tests for ingredient display formatting
runner.test('to top unit with null amount', function() {
    const ingredient = {
        name: 'Champagne',
        unit_name: 'to top',
        amount: null
    };
    this.assertEqual(formatIngredientDisplay(ingredient), 'Champagne, to top');
});

runner.test('to rinse unit with null amount', function() {
    const ingredient = {
        name: 'Absinthe',
        unit_name: 'to rinse',
        amount: null
    };
    this.assertEqual(formatIngredientDisplay(ingredient), 'Absinthe, to rinse');
});

runner.test('each unit with numeric amount', function() {
    const ingredient = {
        name: 'Maraschino Cherry',
        unit_name: 'each',
        amount: 1
    };
    this.assertEqual(formatIngredientDisplay(ingredient), '1 Maraschino Cherry');
});

runner.test('each unit with multiple items', function() {
    const ingredient = {
        name: 'Olives',
        unit_name: 'each',
        amount: 3
    };
    this.assertEqual(formatIngredientDisplay(ingredient), '3 Olives');
});

runner.test('each unit with fractional amount', function() {
    const ingredient = {
        name: 'Lime',
        unit_name: 'each',
        amount: 0.5
    };
    this.assertEqual(formatIngredientDisplay(ingredient), '1/2 Lime');
});

runner.test('normal unit with amount', function() {
    const ingredient = {
        name: 'Gin',
        unit_name: 'Ounce',
        amount: 2
    };
    this.assertEqual(formatIngredientDisplay(ingredient), '2 Ounce Gin');
});

runner.test('normal unit with fractional amount', function() {
    const ingredient = {
        name: 'Simple Syrup',
        unit_name: 'Ounce',
        amount: 0.5
    };
    this.assertEqual(formatIngredientDisplay(ingredient), '1/2 Ounce Simple Syrup');
});

runner.test('ingredient with no unit', function() {
    const ingredient = {
        name: 'Salt',
        unit_name: null,
        amount: 1
    };
    this.assertEqual(formatIngredientDisplay(ingredient), '1 Salt');
});

runner.test('ingredient with no amount and no unit', function() {
    const ingredient = {
        name: 'Garnish',
        unit_name: null,
        amount: null
    };
    this.assertEqual(formatIngredientDisplay(ingredient), ' Garnish');
});

runner.test('ingredient uses full_name when available', function() {
    const ingredient = {
        name: 'Gin',
        full_name: 'London Dry Gin',
        unit_name: 'Ounce',
        amount: 2
    };
    this.assertEqual(formatIngredientDisplay(ingredient), '2 Ounce London Dry Gin');
});

runner.test('to top with undefined amount', function() {
    const ingredient = {
        name: 'Soda Water',
        unit_name: 'to top',
        amount: undefined
    };
    this.assertEqual(formatIngredientDisplay(ingredient), 'Soda Water, to top');
});

runner.test('to rinse with undefined amount', function() {
    const ingredient = {
        name: 'Vermouth',
        unit_name: 'to rinse',
        amount: undefined
    };
    this.assertEqual(formatIngredientDisplay(ingredient), 'Vermouth, to rinse');
});

// Edge cases
runner.test('each unit with null amount', function() {
    const ingredient = {
        name: 'Cherry',
        unit_name: 'each',
        amount: null
    };
    this.assertEqual(formatIngredientDisplay(ingredient), 'Cherry');
});

runner.test('to top with numeric amount (should still show comma format)', function() {
    const ingredient = {
        name: 'Club Soda',
        unit_name: 'to top',
        amount: 2
    };
    // When amount is not null/undefined, should use default formatting
    this.assertEqual(formatIngredientDisplay(ingredient), '2 to top Club Soda');
});

// Run all tests
if (typeof module !== 'undefined' && module.exports) {
    // Node.js environment
    module.exports = { formatAmount, formatIngredientDisplay, TestRunner };
} else {
    // Browser environment - run tests immediately
    runner.run();
}

// If run directly with Node.js, run the tests
if (typeof require !== 'undefined' && require.main === module) {
    const success = runner.run();
    process.exit(success ? 0 : 1);
}