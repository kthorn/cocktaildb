CREATE TABLE IF NOT EXISTS analytics_refresh_state (
    id INTEGER PRIMARY KEY,
    dirty_at TIMESTAMP,
    last_run_at TIMESTAMP
);

INSERT INTO analytics_refresh_state (id, dirty_at, last_run_at)
VALUES (1, NULL, NULL)
ON CONFLICT (id) DO NOTHING;

CREATE OR REPLACE FUNCTION mark_analytics_dirty()
RETURNS trigger AS $$
BEGIN
    UPDATE analytics_refresh_state
    SET dirty_at = CURRENT_TIMESTAMP
    WHERE id = 1;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS analytics_recipes_dirty ON recipes;
CREATE TRIGGER analytics_recipes_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipes
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_ingredients_dirty ON ingredients;
CREATE TRIGGER analytics_ingredients_dirty
AFTER INSERT OR UPDATE OR DELETE ON ingredients
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_recipe_ingredients_dirty ON recipe_ingredients;
CREATE TRIGGER analytics_recipe_ingredients_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipe_ingredients
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_units_dirty ON units;
CREATE TRIGGER analytics_units_dirty
AFTER INSERT OR UPDATE OR DELETE ON units
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_ratings_dirty ON ratings;
CREATE TRIGGER analytics_ratings_dirty
AFTER INSERT OR UPDATE OR DELETE ON ratings
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_tags_dirty ON tags;
CREATE TRIGGER analytics_tags_dirty
AFTER INSERT OR UPDATE OR DELETE ON tags
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();

DROP TRIGGER IF EXISTS analytics_recipe_tags_dirty ON recipe_tags;
CREATE TRIGGER analytics_recipe_tags_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipe_tags
FOR EACH STATEMENT EXECUTE FUNCTION mark_analytics_dirty();
