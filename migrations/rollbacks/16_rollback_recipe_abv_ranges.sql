-- Remove the ingredient ABV range view and stale-parent correction.
BEGIN;

DROP TRIGGER IF EXISTS clear_empty_ingredient_parent_abv_after_change ON ingredients;
DROP FUNCTION IF EXISTS clear_empty_ingredient_parent_abv();
DROP VIEW IF EXISTS ingredient_abv_ranges;

COMMIT;
