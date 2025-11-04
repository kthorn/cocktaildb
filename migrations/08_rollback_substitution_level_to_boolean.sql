-- Rollback: Revert allow_substitution (BOOLEAN) back to substitution_level (INTEGER)
-- Date: 2025-11-03
-- Issue: bd-53

BEGIN TRANSACTION;

ALTER TABLE ingredients ADD COLUMN substitution_level INTEGER DEFAULT 0;

UPDATE ingredients
SET substitution_level = CASE
  WHEN allow_substitution = 1 THEN 1
  ELSE 0
END;

ALTER TABLE ingredients DROP COLUMN allow_substitution;

COMMIT;
