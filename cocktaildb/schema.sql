-- Database Schema for CocktailDB
-- This file contains all table definitions and functions for the ingredient hierarchy

-- Table Definitions
CREATE TABLE ingredients (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  category VARCHAR(50),
  description TEXT,
  parent_id INTEGER REFERENCES ingredients(id),
  path VARCHAR(255)
);

CREATE TABLE units (
  id SERIAL PRIMARY KEY,
  name VARCHAR(50) NOT NULL UNIQUE,
  abbreviation VARCHAR(10)
);

CREATE TABLE recipes (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  instructions TEXT,
  description TEXT,
  image_url VARCHAR(255)
);

CREATE TABLE recipe_ingredients (
  id SERIAL PRIMARY KEY,
  recipe_id INTEGER NOT NULL REFERENCES recipes(id),
  ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
  unit_id INTEGER REFERENCES units(id),
  amount FLOAT
);

-- Create indexes for better performance
CREATE INDEX idx_ingredients_parent_id ON ingredients(parent_id);
CREATE INDEX idx_ingredients_path ON ingredients(path) WHERE path IS NOT NULL;
CREATE INDEX idx_recipe_ingredients_recipe_id ON recipe_ingredients(recipe_id);
CREATE INDEX idx_recipe_ingredients_ingredient_id ON recipe_ingredients(ingredient_id);

-- Function to add a new ingredient safely with path generation
CREATE OR REPLACE FUNCTION add_ingredient(
  p_name VARCHAR, 
  p_category VARCHAR DEFAULT NULL,
  p_description TEXT DEFAULT NULL,
  p_parent_id INTEGER DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
  new_id INTEGER;
  new_path VARCHAR;
BEGIN
  -- 1. Verify parent exists if specified
  IF p_parent_id IS NOT NULL THEN
    PERFORM id FROM ingredients WHERE id = p_parent_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Parent ingredient with ID % does not exist', p_parent_id;
    END IF;
  END IF;
  
  -- 2. Insert the ingredient with a temporary path
  INSERT INTO ingredients (name, category, description, parent_id, path)
  VALUES (p_name, p_category, p_description, p_parent_id, 'temp')
  RETURNING id INTO new_id;
  
  -- 3. Generate the materialized path based on ancestry
  IF p_parent_id IS NULL THEN
    -- Root level ingredient
    new_path := '/' || new_id || '/';
  ELSE
    -- Child ingredient - append to parent's path
    SELECT path || new_id || '/' INTO new_path 
    FROM ingredients WHERE id = p_parent_id;
  END IF;
  
  -- 4. Update with the correct path
  UPDATE ingredients SET path = new_path WHERE id = new_id;
  
  RETURN new_id;
END;
$$ LANGUAGE plpgsql;

-- Function to check for circular references
CREATE OR REPLACE FUNCTION check_circular_reference(
  p_id INTEGER, 
  p_parent_id INTEGER
) RETURNS BOOLEAN AS $$
DECLARE
  ancestor_id INTEGER := p_parent_id;
BEGIN
  -- Can't have circular reference with no parent
  IF p_parent_id IS NULL THEN
    RETURN FALSE;
  END IF;
  
  -- Direct self-reference check
  IF p_id = p_parent_id THEN
    RETURN TRUE;
  END IF;
  
  -- Check for indirect circular references by traversing up the hierarchy
  WHILE ancestor_id IS NOT NULL LOOP
    IF ancestor_id = p_id THEN
      RETURN TRUE;
    END IF;
    SELECT parent_id INTO ancestor_id FROM ingredients WHERE id = ancestor_id;
  END LOOP;
  
  RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Trigger to prevent circular references on updates
CREATE OR REPLACE FUNCTION prevent_circular_reference() RETURNS TRIGGER AS $$
BEGIN
  -- Only check if parent_id is changing
  IF OLD.parent_id IS NOT DISTINCT FROM NEW.parent_id THEN
    RETURN NEW;
  END IF;
  
  -- Check for circular reference
  IF check_circular_reference(NEW.id, NEW.parent_id) THEN
    RAISE EXCEPTION 'Cannot update: Would create circular reference in hierarchy';
  END IF;
  
  -- Calculate new path
  IF NEW.parent_id IS NULL THEN
    NEW.path := '/' || NEW.id || '/';
  ELSE
    SELECT path || NEW.id || '/' INTO NEW.path 
    FROM ingredients WHERE id = NEW.parent_id;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER check_ingredient_update
BEFORE UPDATE OF parent_id ON ingredients
FOR EACH ROW EXECUTE FUNCTION prevent_circular_reference();

-- Trigger to update paths for all descendants when a node's path changes
CREATE OR REPLACE FUNCTION update_descendants_paths() RETURNS TRIGGER AS $$
BEGIN
  -- Only proceed if path actually changed
  IF OLD.path IS NOT DISTINCT FROM NEW.path THEN
    RETURN NEW;
  END IF;
  
  -- Update all descendants with the new path prefix
  UPDATE ingredients 
  SET path = REPLACE(path, OLD.path, NEW.path)
  WHERE path LIKE OLD.path || '%' AND id != NEW.id;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER propagate_path_changes
AFTER UPDATE OF path ON ingredients
FOR EACH ROW
EXECUTE FUNCTION update_descendants_paths();

-- Get all descendants of an ingredient
CREATE OR REPLACE FUNCTION get_descendants(p_ingredient_id INTEGER)
RETURNS TABLE (id INTEGER, name VARCHAR, parent_id INTEGER, path VARCHAR, level INTEGER) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    i.id, 
    i.name, 
    i.parent_id, 
    i.path,
    (LENGTH(i.path) - LENGTH(REPLACE(i.path, '/', ''))) - 1 AS level
  FROM 
    ingredients i
  JOIN 
    ingredients parent ON i.path LIKE parent.path || '%'
  WHERE 
    parent.id = p_ingredient_id
    AND i.id != p_ingredient_id
  ORDER BY 
    i.path;
END;
$$ LANGUAGE plpgsql;

-- Get all ancestors of an ingredient
CREATE OR REPLACE FUNCTION get_ancestors(p_ingredient_id INTEGER)
RETURNS TABLE (id INTEGER, name VARCHAR, parent_id INTEGER, path VARCHAR, level INTEGER) AS $$
DECLARE
  ingredient_path VARCHAR;
BEGIN
  -- Get the path of the target ingredient
  SELECT path INTO ingredient_path FROM ingredients WHERE id = p_ingredient_id;
  
  IF ingredient_path IS NULL THEN
    RETURN;
  END IF;
  
  RETURN QUERY
  WITH path_parts AS (
    SELECT 
      regexp_split_to_table(TRIM(BOTH '/' FROM ingredient_path), '/') AS part
  ),
  ancestor_ids AS (
    SELECT part::INTEGER AS id FROM path_parts WHERE part ~ '^[0-9]+$'
  )
  SELECT 
    i.id, 
    i.name, 
    i.parent_id, 
    i.path,
    (LENGTH(i.path) - LENGTH(REPLACE(i.path, '/', ''))) - 1 AS level
  FROM 
    ingredients i
  JOIN 
    ancestor_ids a ON i.id = a.id
  WHERE 
    i.id != p_ingredient_id
  ORDER BY 
    i.path;
END;
$$ LANGUAGE plpgsql; 