-- Store ingredient_abv_resolution so recipe ABV reads skip its recursive walk.
BEGIN;

-- Snapshot of ingredient_abv_resolution, which stays the definition of the rule.
-- Refreshed by the statement triggers below whenever an input column changes.
CREATE TABLE IF NOT EXISTS ingredient_abv_resolution_store (
    ingredient_id INTEGER PRIMARY KEY,
    min_percent_abv NUMERIC NOT NULL,
    max_percent_abv NUMERIC NOT NULL,
    observation_count BIGINT NOT NULL,
    family_id INTEGER,
    family_name TEXT,
    source TEXT NOT NULL,
    has_observations BOOLEAN NOT NULL
);

CREATE OR REPLACE FUNCTION refresh_ingredient_abv_resolution_store()
RETURNS TRIGGER AS $$
BEGIN
  -- Nested writes (the value roll-up) are covered by the outer statement's refresh.
  IF pg_trigger_depth() > 1 THEN
    RETURN NULL;
  END IF;

  IF TG_WHEN = 'BEFORE' THEN
    -- Serialize writers so each refresh sees every committed change. Shares the
    -- value roll-up's key: one lock per writer cannot be taken out of order.
    PERFORM pg_advisory_xact_lock(hashtext('roll_up_ingredient_values'));
    RETURN NULL;
  END IF;

  DELETE FROM ingredient_abv_resolution_store;
  INSERT INTO ingredient_abv_resolution_store
  SELECT ingredient_id, min_percent_abv, max_percent_abv, observation_count,
         family_id, family_name, source, has_observations
  FROM ingredient_abv_resolution;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS lock_ingredient_abv_resolution_before_change ON ingredients;
DROP TRIGGER IF EXISTS store_ingredient_abv_resolution_after_change ON ingredients;

CREATE TRIGGER lock_ingredient_abv_resolution_before_change
BEFORE INSERT OR DELETE OR TRUNCATE OR UPDATE OF name, parent_id, percent_abv
ON ingredients
FOR EACH STATEMENT
EXECUTE FUNCTION refresh_ingredient_abv_resolution_store();

-- Named to sort after roll_up_ingredient_values_after_change, so the refresh
-- sees rolled-up parent values.
CREATE TRIGGER store_ingredient_abv_resolution_after_change
AFTER INSERT OR DELETE OR TRUNCATE OR UPDATE OF name, parent_id, percent_abv
ON ingredients
FOR EACH STATEMENT
EXECUTE FUNCTION refresh_ingredient_abv_resolution_store();

-- Same definition as before; strengths now come from the store.
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
JOIN ingredient_abv_resolution_store s ON s.ingredient_id = v.ingredient_id;

DELETE FROM ingredient_abv_resolution_store;
INSERT INTO ingredient_abv_resolution_store
SELECT ingredient_id, min_percent_abv, max_percent_abv, observation_count,
       family_id, family_name, source, has_observations
FROM ingredient_abv_resolution;

COMMIT;
