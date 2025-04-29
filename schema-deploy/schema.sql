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
  image_url VARCHAR(255)
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

-- Insert common measurement units
INSERT INTO units (name, abbreviation) VALUES
  ('Ounce', 'oz'),
  ('Tablespoon', 'tbsp'),
  ('Teaspoon', 'tsp'),
  ('Barspoon', 'bsp'),
  ('Dash', 'dash');

-- Insert base ingredients
INSERT INTO ingredients (name, description, path) VALUES
  ('Whiskey', 'A spirit distilled from fermented grain mash', 'Whiskey'),
  ('Rum', 'A spirit distilled from sugarcane byproducts', 'Rum'),
  ('Vodka', 'A spirit distilled from fermented grains or potatoes', 'Vodka'),
  ('Gin', 'A spirit distilled from juniper berries', 'Gin'),
  ('Brandy', 'A spirit distilled from wine or fruit', 'Brandy'),
  ('Juice', '', 'Juice');
