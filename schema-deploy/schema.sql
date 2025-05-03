-- Database Schema for CocktailDB
-- This file contains all table definitions and functions for the ingredient hierarchy

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Table Definitions
CREATE TABLE ingredients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  description TEXT,
  parent_id INTEGER,
  path VARCHAR(255),
  FOREIGN KEY (parent_id) REFERENCES ingredients(id)
);

CREATE TABLE units (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(50) NOT NULL UNIQUE,
  abbreviation VARCHAR(10)
);

CREATE TABLE recipes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL,
  instructions TEXT,
  description TEXT,
  image_url VARCHAR(255),
  source VARCHAR(255),
  source_url VARCHAR(255),
  avg_rating REAL DEFAULT 0,
  rating_count INTEGER DEFAULT 0
);

CREATE TABLE ratings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cognito_user_id VARCHAR(36) NOT NULL,
  cognito_username VARCHAR(128) NOT NULL,
  recipe_id INTEGER NOT NULL,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  comment TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id),
  UNIQUE(cognito_user_id, recipe_id)
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE recipe_tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id),
  FOREIGN KEY (tag_id) REFERENCES tags(id),
  UNIQUE(recipe_id, tag_id)
);

CREATE TABLE recipe_ingredients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id INTEGER NOT NULL,
  ingredient_id INTEGER NOT NULL,
  unit_id INTEGER,
  amount REAL,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id),
  FOREIGN KEY (ingredient_id) REFERENCES ingredients(id),
  FOREIGN KEY (unit_id) REFERENCES units(id)
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

-- Create trigger to update average rating when a new rating is added
CREATE TRIGGER update_avg_rating_insert 
AFTER INSERT ON ratings
BEGIN
  UPDATE recipes
  SET 
    avg_rating = (SELECT AVG(rating) FROM ratings WHERE recipe_id = NEW.recipe_id),
    rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = NEW.recipe_id)
  WHERE id = NEW.recipe_id;
END;

-- Create trigger to update average rating when a rating is updated
CREATE TRIGGER update_avg_rating_update 
AFTER UPDATE ON ratings
WHEN OLD.rating <> NEW.rating
BEGIN
  UPDATE recipes
  SET 
    avg_rating = (SELECT AVG(rating) FROM ratings WHERE recipe_id = NEW.recipe_id),
    rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = NEW.recipe_id)
  WHERE id = NEW.recipe_id;
END;

-- Create trigger to update average rating when a rating is deleted
CREATE TRIGGER update_avg_rating_delete 
AFTER DELETE ON ratings
BEGIN
  UPDATE recipes
  SET 
    avg_rating = COALESCE((SELECT AVG(rating) FROM ratings WHERE recipe_id = OLD.recipe_id), 0),
    rating_count = (SELECT COUNT(*) FROM ratings WHERE recipe_id = OLD.recipe_id)
  WHERE id = OLD.recipe_id;
END;


-- Insert common measurement units
INSERT INTO units (name, abbreviation) VALUES
  ('Ounce', 'oz'),
  ('Tablespoon', 'tbsp'),
  ('Teaspoon', 'tsp'),
  ('Barspoon', 'bsp'),
  ('Dash', 'dash'),
  ('Each', 'each'),
  ('Drop', 'drop');

-- Insert base ingredients
INSERT INTO ingredients (name, description, path) VALUES
  ('Whiskey', 'A spirit distilled from fermented grain mash', '/1/'),
  ('Rum', 'A spirit distilled from sugarcane byproducts', '/2/'),
  ('Vodka', 'A spirit distilled from fermented grains or potatoes', '/3/'),
  ('Gin', 'A spirit distilled from juniper berries', '/4/'),
  ('Brandy', 'A spirit distilled from wine or fruit', '/5/'),
  ('Tequila', 'A spirit distilled from agave', '/6/'),
  ('Juice', '', '/7/');

-- Insert common tags
INSERT INTO tags (name) VALUES
  ('Tiki'),
  ('Fruity'),
  ('Classic'),
  ('Modern'),
  ('Bitter');