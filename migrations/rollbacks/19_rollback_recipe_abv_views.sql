-- Remove the recipe ABV views, dependents first.
BEGIN;

DROP VIEW IF EXISTS recipe_abv;
DROP VIEW IF EXISTS recipe_abv_ingredient_rows;
DROP VIEW IF EXISTS recipe_ingredient_volumes;
DROP VIEW IF EXISTS ingredient_abv_resolution;

COMMIT;
