-- Migration: Add substitution_level to ingredients table
-- This migration adds substitution_level column to enable configurable brand substitutability rules

-- 1. Add substitution_level column to ingredients table
-- substitution_level values:
--   0: No substitution allowed (exact match required) - for unique ingredients like "Aperol"
--   1: Allow substitution within immediate parent category - for brands within a rum type  
--   2: Allow substitution at grandparent level - for broader categories
--   NULL or higher: Use parent's substitution level (inherit upward)
ALTER TABLE ingredients ADD COLUMN substitution_level INTEGER DEFAULT 0;

-- 2. Set substitution levels for existing base categories
-- Base spirit categories should allow substitution at brand level (level 1)
UPDATE ingredients SET substitution_level = 1 
WHERE parent_id IS NULL AND name IN ('Whiskey', 'Rum', 'Vodka', 'Gin', 'Brandy', 'Tequila');

-- 3. Set substitution levels for juice category (allow substitution)
UPDATE ingredients SET substitution_level = 1 
WHERE parent_id IS NULL AND name = 'Juice';

-- 4. For existing sub-categories, set appropriate substitution levels
-- This will be populated based on the ingredient hierarchy as brands are added
-- Sub-categories that should allow brand substitution get level 1
-- Unique items that require exact match get level 0

-- 5. Add index for performance on substitution_level queries
CREATE INDEX idx_ingredients_substitution_level ON ingredients(substitution_level);

-- 6. Add index on parent_id and substitution_level combination for hierarchy queries
CREATE INDEX idx_ingredients_parent_substitution ON ingredients(parent_id, substitution_level);

PRAGMA user_version = 7;

COMMIT;