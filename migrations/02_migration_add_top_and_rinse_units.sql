-- Migration script to add "to top" and "to rinse" units to the units table

-- Insert new units for common cocktail preparation methods
INSERT INTO units (name, abbreviation, conversion_to_ml) VALUES
  ('to top', 'top', NULL),      -- Amount varies greatly depending on glass size and desired level
  ('to rinse', 'rinse', NULL);  -- Amount varies based on glass size and desired coating

-- Update pragma version to track this migration
PRAGMA user_version = 2;

COMMIT; 