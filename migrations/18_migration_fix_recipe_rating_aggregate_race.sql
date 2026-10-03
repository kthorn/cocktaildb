-- Serialize recipe rating aggregate recomputes, and repair rows already left short.
--
-- The AFTER INSERT/UPDATE/DELETE trigger on ratings recomputed avg_rating and
-- rating_count with uncorrelated subqueries. Those subqueries are evaluated
-- before the UPDATE on recipes takes its row lock, under a snapshot that cannot
-- see another rater's uncommitted row, so two concurrent raters can both count
-- the pre-race total and both write it. The loser's increment is discarded and
-- the aggregate stays short until the next rating on that recipe.
--
-- The lock is FOR NO KEY UPDATE, not FOR UPDATE: inserting a rating takes the
-- ratings foreign key check's KEY SHARE lock on this same recipes row, and
-- FOR UPDATE conflicts with KEY SHARE, which deadlocks concurrent raters.
BEGIN;

CREATE OR REPLACE FUNCTION update_recipe_avg_rating()
RETURNS TRIGGER AS $$
BEGIN
  -- Handle INSERT and UPDATE
  IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
    -- Serialize the recompute per recipe. The subqueries below are evaluated
    -- before the UPDATE takes its row lock, so without this lock two concurrent
    -- raters can both count the pre-race total and both write it.
    -- FOR NO KEY UPDATE, not FOR UPDATE: the ratings foreign key check holds a
    -- KEY SHARE lock on this same row, and FOR UPDATE conflicts with KEY SHARE,
    -- which deadlocks concurrent raters.
    PERFORM 1 FROM recipes WHERE id = NEW.recipe_id FOR NO KEY UPDATE;
    UPDATE recipes
    SET
      avg_rating = (SELECT AVG(rating) FROM ratings WHERE recipe_id = NEW.recipe_id),
      rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = NEW.recipe_id)
    WHERE id = NEW.recipe_id;
    RETURN NEW;
  -- Handle DELETE
  ELSIF TG_OP = 'DELETE' THEN
    PERFORM 1 FROM recipes WHERE id = OLD.recipe_id FOR NO KEY UPDATE;
    UPDATE recipes
    SET
      avg_rating = COALESCE((SELECT AVG(rating) FROM ratings WHERE recipe_id = OLD.recipe_id), 0),
      rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = OLD.recipe_id)
    WHERE id = OLD.recipe_id;
    RETURN OLD;
  END IF;
END;
$$ LANGUAGE plpgsql;

-- Repair rows the race already corrupted. They never self-heal until the next
-- rating arrives on the affected recipe. Recipes with no ratings settle at
-- count 0 / avg 0, matching the DELETE branch above.
UPDATE recipes AS r
SET
  avg_rating = COALESCE((SELECT AVG(rating) FROM ratings WHERE recipe_id = r.id), 0),
  rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = r.id);

COMMIT;
