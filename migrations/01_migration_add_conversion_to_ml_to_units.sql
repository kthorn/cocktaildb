-- Migration script to add conversion_to_ml column to the units table

-- Add the new column to the units table, allowing NULL values initially
ALTER TABLE units ADD COLUMN conversion_to_ml REAL;

-- Update existing units with their approximate conversion to milliliters
-- Note: These are common approximations and might need adjustment based on specific standards
UPDATE units SET conversion_to_ml = 29.5735 WHERE name = 'Ounce';          -- 1 fl oz (US)
UPDATE units SET conversion_to_ml = 14.7868 WHERE name = 'Tablespoon';    -- 1 tbsp (US)
UPDATE units SET conversion_to_ml = 4.92892 WHERE name = 'Teaspoon';      -- 1 tsp (US)
UPDATE units SET conversion_to_ml = 2.46446 WHERE name = 'Barspoon';      -- Approx 0.5 tsp, can vary
UPDATE units SET conversion_to_ml = 0.616115 WHERE name = 'Dash';         -- Approx 1/8 tsp, can vary significantly
UPDATE units SET conversion_to_ml = 0.05 WHERE name = 'Drop'; -- A common medicinal drop approximation
UPDATE units SET conversion_to_ml = NULL WHERE name = 'Each'; -- Or leave as NULL if no standard conversion

PRAGMA user_version = 1;

COMMIT; 