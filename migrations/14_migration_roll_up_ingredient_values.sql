-- Derive non-leaf ingredient measurements from their immediate children.
BEGIN;

CREATE OR REPLACE FUNCTION roll_up_ingredient_values()
RETURNS TRIGGER AS $$
DECLARE
  remaining_levels INTEGER;
BEGIN
  IF pg_trigger_depth() > 1 THEN
    RETURN NULL;
  END IF;

  IF TG_WHEN = 'BEFORE' THEN
    -- Serialize before the write acquires row locks, preventing lock inversion.
    PERFORM pg_advisory_xact_lock(hashtext('roll_up_ingredient_values'));
    RETURN NULL;
  END IF;

  WITH RECURSIVE hierarchy AS (
    SELECT id, 0 AS depth
    FROM ingredients
    WHERE parent_id IS NULL
    UNION ALL
    SELECT child.id, parent.depth + 1
    FROM ingredients child
    JOIN hierarchy parent ON child.parent_id = parent.id
  )
  SELECT COALESCE(MAX(depth), 0) INTO remaining_levels FROM hierarchy;

  -- ponytail: recompute the small ingredient tree; track affected ancestors if it grows large.
  WHILE remaining_levels > 0 LOOP
    UPDATE ingredients parent
    SET percent_abv = children.percent_abv,
        sugar_g_per_l = children.sugar_g_per_l,
        titratable_acidity_g_per_l = children.titratable_acidity_g_per_l
    FROM (
      SELECT parent_id,
             AVG(percent_abv) AS percent_abv,
             AVG(sugar_g_per_l) AS sugar_g_per_l,
             AVG(titratable_acidity_g_per_l) AS titratable_acidity_g_per_l
      FROM ingredients
      WHERE parent_id IS NOT NULL
      GROUP BY parent_id
    ) children
    WHERE parent.id = children.parent_id;

    remaining_levels := remaining_levels - 1;
  END LOOP;

  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS lock_ingredient_value_rollup_before_change ON ingredients;
DROP TRIGGER IF EXISTS roll_up_ingredient_values_after_change ON ingredients;

CREATE TRIGGER lock_ingredient_value_rollup_before_change
BEFORE INSERT OR DELETE OR UPDATE OF parent_id, percent_abv, sugar_g_per_l,
  titratable_acidity_g_per_l ON ingredients
FOR EACH STATEMENT
EXECUTE FUNCTION roll_up_ingredient_values();

CREATE TRIGGER roll_up_ingredient_values_after_change
AFTER INSERT OR DELETE OR UPDATE OF parent_id, percent_abv, sugar_g_per_l,
  titratable_acidity_g_per_l ON ingredients
FOR EACH STATEMENT
EXECUTE FUNCTION roll_up_ingredient_values();

-- Statement triggers fire even when no rows match, initiating the backfill
-- without rewriting every ingredient first.
UPDATE ingredients SET percent_abv = percent_abv WHERE FALSE;

COMMIT;
