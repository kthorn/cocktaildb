-- Repair the imported Perfect BQE recipe: its barspoon quantity is one.
UPDATE recipe_ingredients AS ri
SET amount = 1
FROM units AS u
WHERE ri.recipe_id = 905
  AND ri.unit_id = u.id
  AND LOWER(u.abbreviation) = 'bsp'
  AND u.conversion_to_ml IS NOT NULL
  AND ri.amount IS NULL;

-- Keep rows with convertible units measurable on every SQL write path.
CREATE OR REPLACE FUNCTION require_convertible_recipe_ingredient_amount()
RETURNS TRIGGER AS $$
DECLARE
  unit_name TEXT;
BEGIN
  IF NEW.amount IS NULL AND NEW.unit_id IS NOT NULL THEN
    SELECT u.name INTO unit_name
    FROM units AS u
    WHERE u.id = NEW.unit_id
      AND u.conversion_to_ml IS NOT NULL;

    IF unit_name IS NOT NULL THEN
      RAISE EXCEPTION 'Recipe ingredient % requires an amount for unit %',
        NEW.ingredient_id, unit_name
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS require_convertible_recipe_ingredient_amount
  ON recipe_ingredients;
CREATE TRIGGER require_convertible_recipe_ingredient_amount
BEFORE INSERT OR UPDATE OF amount, unit_id ON recipe_ingredients
FOR EACH ROW
EXECUTE FUNCTION require_convertible_recipe_ingredient_amount();

COMMIT;
