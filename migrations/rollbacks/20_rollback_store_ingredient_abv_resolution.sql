-- Read strengths from ingredient_abv_resolution again and drop its stored copy.
BEGIN;

CREATE OR REPLACE VIEW recipe_abv_ingredient_rows AS
SELECT
    v.recipe_ingredient_id,
    v.recipe_id,
    v.ingredient_id,
    i.name::text AS ingredient_name,
    v.unit_name,
    v.volume_rule,
    v.invalid_reason,
    v.volume_ml,
    v.is_estimated,
    v.sort_volume,
    s.min_percent_abv,
    s.max_percent_abv,
    s.source AS strength_source,
    v.volume_rule IN ('top', 'rinse', 'measured') AS contributes,
    CASE
        WHEN s.min_percent_abv = s.max_percent_abv AND s.min_percent_abv > 0
             AND s.min_percent_abv < 1 THEN 0
        WHEN s.min_percent_abv = s.max_percent_abv THEN round(s.min_percent_abv)::integer
        ELSE floor(s.min_percent_abv)::integer
    END AS strength_display_low,
    CASE
        WHEN s.min_percent_abv = s.max_percent_abv AND s.min_percent_abv > 0
             AND s.min_percent_abv < 1 THEN 0
        WHEN s.min_percent_abv = s.max_percent_abv THEN round(s.min_percent_abv)::integer
        ELSE ceil(s.max_percent_abv)::integer
    END AS strength_display_high,
    s.min_percent_abv = s.max_percent_abv AND s.min_percent_abv > 0
        AND s.min_percent_abv < 1 AS strength_display_below_one
FROM recipe_ingredient_volumes v
JOIN ingredients i ON i.id = v.ingredient_id
JOIN ingredient_abv_resolution s ON s.ingredient_id = v.ingredient_id;

DROP TRIGGER IF EXISTS store_ingredient_abv_resolution_after_change ON ingredients;
DROP TRIGGER IF EXISTS lock_ingredient_abv_resolution_before_change ON ingredients;
DROP FUNCTION IF EXISTS refresh_ingredient_abv_resolution_store();
DROP TABLE IF EXISTS ingredient_abv_resolution_store;

COMMIT;
