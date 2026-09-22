-- PostgreSQL Schema for CocktailDB
-- Converted from SQLite schema at schema-deploy/schema.sql
-- This file contains all table definitions and functions for the ingredient hierarchy

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text search and similarity
CREATE EXTENSION IF NOT EXISTS citext;   -- For case-insensitive text
CREATE EXTENSION IF NOT EXISTS unaccent; -- For accent-insensitive search
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- For invite-code generation

-- Table Definitions

CREATE TABLE ingredients (
  id SERIAL PRIMARY KEY,
  name CITEXT NOT NULL UNIQUE,
  description TEXT,
  parent_id INTEGER,
  path TEXT,
  allow_substitution BOOLEAN NOT NULL DEFAULT FALSE,
  percent_abv NUMERIC CHECK (percent_abv >= 0 AND percent_abv <= 100),
  sugar_g_per_l NUMERIC CHECK (sugar_g_per_l >= 0 AND sugar_g_per_l <= 1000),
  titratable_acidity_g_per_l NUMERIC CHECK (titratable_acidity_g_per_l >= 0 AND titratable_acidity_g_per_l <= 100),
  url TEXT,
  created_by TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (parent_id) REFERENCES ingredients(id)
);

CREATE TABLE units (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  abbreviation TEXT,
  conversion_to_ml REAL
);

CREATE TABLE recipes (
  id SERIAL PRIMARY KEY,
  name CITEXT NOT NULL UNIQUE,
  instructions TEXT,
  description TEXT,
  image_url TEXT,
  source TEXT,
  source_url TEXT,
  avg_rating REAL DEFAULT 0,
  rating_count INTEGER DEFAULT 0,
  created_by TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ratings (
  id SERIAL PRIMARY KEY,
  cognito_user_id TEXT NOT NULL,
  recipe_id INTEGER NOT NULL,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
  UNIQUE(cognito_user_id, recipe_id)
);

CREATE TABLE tags (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  created_by TEXT NULL, -- NULL for public tags, user_id for private tags
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE recipe_tags (
  id SERIAL PRIMARY KEY,
  recipe_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
  UNIQUE(recipe_id, tag_id)
);

CREATE TABLE recipe_ingredients (
  id SERIAL PRIMARY KEY,
  recipe_id INTEGER NOT NULL,
  ingredient_id INTEGER NOT NULL,
  unit_id INTEGER,
  amount REAL,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
  FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE RESTRICT,
  FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE SET NULL
);

CREATE TABLE user_ingredients (
  id SERIAL PRIMARY KEY,
  cognito_user_id TEXT NOT NULL,
  ingredient_id INTEGER NOT NULL,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
  UNIQUE(cognito_user_id, ingredient_id)
);

CREATE TABLE user_groups (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  invite_code TEXT NOT NULL UNIQUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_group_members (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
  cognito_user_id TEXT NOT NULL UNIQUE,
  joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE group_ingredients (
  id SERIAL PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
  ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
  added_by TEXT NOT NULL,
  added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(group_id, ingredient_id)
);

CREATE TABLE analytics_refresh_state (
  id INTEGER PRIMARY KEY,
  dirty_at TIMESTAMP,
  last_run_at TIMESTAMP
);

INSERT INTO analytics_refresh_state (id, dirty_at, last_run_at)
VALUES (1, NULL, NULL)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE recipe_similarity (
  recipe_id INTEGER PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
  recipe_name TEXT NOT NULL,
  neighbors JSONB NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE recipe_similarity IS 'Pre-computed similar cocktails from EM distance analysis';

-- Create indexes for better performance
CREATE INDEX idx_ingredients_parent_id ON ingredients(parent_id);
CREATE INDEX idx_ingredients_path ON ingredients(path);
CREATE INDEX idx_recipe_ingredients_recipe_id ON recipe_ingredients(recipe_id);
CREATE INDEX idx_recipe_ingredients_ingredient_id ON recipe_ingredients(ingredient_id);
CREATE INDEX idx_recipe_tags_recipe_id ON recipe_tags(recipe_id);
CREATE INDEX idx_recipe_tags_tag_id ON recipe_tags(tag_id);
CREATE INDEX idx_ratings_cognito_user_id ON ratings(cognito_user_id);
CREATE INDEX idx_ratings_recipe_id ON ratings(recipe_id);
CREATE INDEX idx_user_ingredients_cognito_user_id ON user_ingredients(cognito_user_id);
CREATE INDEX idx_user_ingredients_ingredient_id ON user_ingredients(ingredient_id);
CREATE INDEX idx_user_group_members_group_id ON user_group_members(group_id);
CREATE INDEX idx_group_ingredients_ingredient_id ON group_ingredients(ingredient_id);
CREATE INDEX idx_recipes_created_by ON recipes(created_by);
CREATE INDEX idx_recipes_name_id ON recipes(name, id);
CREATE INDEX idx_recipes_avg_rating_id ON recipes(avg_rating, id);
CREATE INDEX idx_recipes_created_at_id ON recipes(created_at, id);
CREATE INDEX idx_recipes_rating_count_id ON recipes(rating_count, id);
CREATE INDEX idx_ingredients_created_by ON ingredients(created_by);

-- Partial unique indexes for tags (PostgreSQL supports partial indexes)
CREATE UNIQUE INDEX idx_public_tags ON tags(name) WHERE created_by IS NULL;
CREATE UNIQUE INDEX idx_private_tags ON tags(name, created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_tags_created_by ON tags(created_by);

-- Add trigram indexes for text search
CREATE INDEX idx_recipes_name_trgm ON recipes USING gin(name gin_trgm_ops);
CREATE INDEX idx_ingredients_name_trgm ON ingredients USING gin(name gin_trgm_ops);

-- Trigger Functions (PostgreSQL requires separate function definitions)

-- Function to update average rating on ratings changes
CREATE OR REPLACE FUNCTION update_recipe_avg_rating()
RETURNS TRIGGER AS $$
BEGIN
  -- Handle INSERT and UPDATE
  IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
    UPDATE recipes
    SET
      avg_rating = (SELECT AVG(rating) FROM ratings WHERE recipe_id = NEW.recipe_id),
      rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = NEW.recipe_id)
    WHERE id = NEW.recipe_id;
    RETURN NEW;
  -- Handle DELETE
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE recipes
    SET
      avg_rating = COALESCE((SELECT AVG(rating) FROM ratings WHERE recipe_id = OLD.recipe_id), 0),
      rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = OLD.recipe_id)
    WHERE id = OLD.recipe_id;
    RETURN OLD;
  END IF;
END;
$$ LANGUAGE plpgsql;

-- Roll non-leaf ingredient measurements up from their immediate children.
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

-- Aggregate valid recorded leaf ABVs for every ingredient and its ancestors.
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

-- Clear an old derived ABV when its last child is deleted or reparented.
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

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to mark analytics refresh state as dirty
CREATE OR REPLACE FUNCTION mark_analytics_dirty()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE analytics_refresh_state
  SET dirty_at = CURRENT_TIMESTAMP
  WHERE id = 1;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Require a quantity whenever the selected unit has an mL conversion.
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

-- Create Triggers

-- Keep derived ingredient measurements current for every write path.
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

CREATE TRIGGER clear_empty_ingredient_parent_abv_after_change
AFTER DELETE OR UPDATE OF parent_id ON ingredients
FOR EACH ROW
EXECUTE FUNCTION clear_empty_ingredient_parent_abv();

-- Reject unmeasured ingredients when their unit can be converted to mL.
CREATE TRIGGER require_convertible_recipe_ingredient_amount
BEFORE INSERT OR UPDATE OF amount, unit_id ON recipe_ingredients
FOR EACH ROW
EXECUTE FUNCTION require_convertible_recipe_ingredient_amount();

-- Analytics refresh triggers
CREATE TRIGGER analytics_recipes_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipes
FOR EACH STATEMENT
EXECUTE FUNCTION mark_analytics_dirty();

CREATE TRIGGER analytics_ingredients_dirty
AFTER INSERT OR UPDATE OR DELETE ON ingredients
FOR EACH STATEMENT
EXECUTE FUNCTION mark_analytics_dirty();

CREATE TRIGGER analytics_recipe_ingredients_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipe_ingredients
FOR EACH STATEMENT
EXECUTE FUNCTION mark_analytics_dirty();

CREATE TRIGGER analytics_units_dirty
AFTER INSERT OR UPDATE OR DELETE ON units
FOR EACH STATEMENT
EXECUTE FUNCTION mark_analytics_dirty();

CREATE TRIGGER analytics_ratings_dirty
AFTER INSERT OR UPDATE OR DELETE ON ratings
FOR EACH STATEMENT
EXECUTE FUNCTION mark_analytics_dirty();

CREATE TRIGGER analytics_tags_dirty
AFTER INSERT OR UPDATE OR DELETE ON tags
FOR EACH STATEMENT
EXECUTE FUNCTION mark_analytics_dirty();

CREATE TRIGGER analytics_recipe_tags_dirty
AFTER INSERT OR UPDATE OR DELETE ON recipe_tags
FOR EACH STATEMENT
EXECUTE FUNCTION mark_analytics_dirty();

-- Trigger to update average rating when a new rating is added
CREATE TRIGGER update_avg_rating_insert
AFTER INSERT ON ratings
FOR EACH ROW
EXECUTE FUNCTION update_recipe_avg_rating();

-- Trigger to update average rating when a rating is updated
CREATE TRIGGER update_avg_rating_update
AFTER UPDATE ON ratings
FOR EACH ROW
WHEN (OLD.rating IS DISTINCT FROM NEW.rating)
EXECUTE FUNCTION update_recipe_avg_rating();

-- Trigger to update average rating when a rating is deleted
CREATE TRIGGER update_avg_rating_delete
AFTER DELETE ON ratings
FOR EACH ROW
EXECUTE FUNCTION update_recipe_avg_rating();

-- Trigger to automatically update updated_at for recipes
CREATE TRIGGER update_recipes_updated_at
BEFORE UPDATE ON recipes
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Trigger to automatically update updated_at for ingredients
CREATE TRIGGER update_ingredients_updated_at
BEFORE UPDATE ON ingredients
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Trigger to automatically update updated_at for user groups
CREATE TRIGGER update_user_groups_updated_at
BEFORE UPDATE ON user_groups
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
