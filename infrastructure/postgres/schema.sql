-- PostgreSQL Schema for CocktailDB
-- Converted from SQLite schema at schema-deploy/schema.sql
-- This file contains all table definitions and functions for the ingredient hierarchy

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text search and similarity

-- Table Definitions

CREATE TABLE ingredients (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  parent_id INTEGER,
  path TEXT,
  allow_substitution BOOLEAN NOT NULL DEFAULT FALSE,
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
  name TEXT NOT NULL UNIQUE,
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
  cognito_username TEXT NOT NULL,
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
CREATE INDEX idx_recipes_created_by ON recipes(created_by);
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

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create Triggers

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
