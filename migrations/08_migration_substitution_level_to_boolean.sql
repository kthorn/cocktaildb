-- Migration: Convert substitution_level (INTEGER) to allow_substitution (BOOLEAN)
-- Date: 2025-11-03
-- Issue: bd-53

BEGIN TRANSACTION;

-- Add new column with default false
ALTER TABLE ingredients ADD COLUMN allow_substitution BOOLEAN NOT NULL DEFAULT 0;

-- Populate: Conservative mapping (only explicit 1 or 2 → true)
UPDATE ingredients
SET allow_substitution = CASE
  WHEN substitution_level IN (1, 2) THEN 1
  ELSE 0
END;

-- Drop both indexes on substitution_level before dropping the column
DROP INDEX IF EXISTS idx_ingredients_substitution_level;
DROP INDEX IF EXISTS idx_ingredients_parent_substitution;

-- Drop old column
ALTER TABLE ingredients DROP COLUMN substitution_level;

COMMIT;
