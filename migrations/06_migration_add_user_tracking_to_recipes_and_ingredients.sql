-- Migration: Add user tracking and timestamps to recipes and ingredients tables
-- This migration adds created_by, created_at, and updated_at columns to enable user-based edit permissions

-- 1. Add user tracking columns to recipes table
ALTER TABLE recipes ADD COLUMN created_by TEXT;
ALTER TABLE recipes ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE recipes ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 2. Add user tracking columns to ingredients table
ALTER TABLE ingredients ADD COLUMN created_by TEXT;
ALTER TABLE ingredients ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE ingredients ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 3. Create trigger to automatically update updated_at for recipes
CREATE TRIGGER update_recipes_updated_at
AFTER UPDATE ON recipes
BEGIN
  UPDATE recipes SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- 4. Create trigger to automatically update updated_at for ingredients
CREATE TRIGGER update_ingredients_updated_at
AFTER UPDATE ON ingredients
BEGIN
  UPDATE ingredients SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- 5. Add indexes for performance
CREATE INDEX idx_recipes_created_by ON recipes(created_by);
CREATE INDEX idx_ingredients_created_by ON ingredients(created_by);

PRAGMA user_version = 6;

COMMIT;