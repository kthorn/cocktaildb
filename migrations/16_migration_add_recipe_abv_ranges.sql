-- Add live ingredient ABV ranges and clear stale former-parent rollups.
BEGIN;

CREATE OR REPLACE VIEW ingredient_abv_ranges AS
WITH RECURSIVE observations(leaf_id, ingredient_id, percent_abv) AS (
  SELECT i.id, i.id, i.percent_abv
  FROM ingredients i
  WHERE i.percent_abv IS NOT NULL
    AND i.percent_abv <> 'NaN'::numeric
    AND i.percent_abv BETWEEN 0 AND 100
    AND NOT EXISTS (
      SELECT 1 FROM ingredients child WHERE child.parent_id = i.id
    )
  UNION
  SELECT o.leaf_id, parent.id, o.percent_abv
  FROM observations o
  JOIN ingredients current ON current.id = o.ingredient_id
  JOIN ingredients parent ON parent.id = current.parent_id
)
SELECT i.id AS ingredient_id,
       MIN(o.percent_abv) AS min_percent_abv,
       MAX(o.percent_abv) AS max_percent_abv,
       COUNT(o.leaf_id) AS observation_count
FROM ingredients i
LEFT JOIN observations o ON o.ingredient_id = i.id
GROUP BY i.id;

CREATE OR REPLACE FUNCTION clear_empty_ingredient_parent_abv()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    UPDATE ingredients p SET percent_abv = NULL
    WHERE p.id = OLD.parent_id
      AND p.percent_abv IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM ingredients c WHERE c.parent_id = p.id);
  ELSIF OLD.parent_id IS DISTINCT FROM NEW.parent_id THEN
    UPDATE ingredients p SET percent_abv = NULL
    WHERE p.id = OLD.parent_id
      AND p.percent_abv IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM ingredients c WHERE c.parent_id = p.id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS clear_empty_ingredient_parent_abv_after_change ON ingredients;

CREATE TRIGGER clear_empty_ingredient_parent_abv_after_change
AFTER DELETE OR UPDATE OF parent_id ON ingredients
FOR EACH ROW
EXECUTE FUNCTION clear_empty_ingredient_parent_abv();

COMMIT;
