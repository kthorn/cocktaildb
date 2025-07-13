-- Migration: Add user ingredient tracking to enable filtering recipes by available ingredients
-- This migration creates a user_ingredients table to track which ingredients each user has available

-- 1. Create user_ingredients table
CREATE TABLE user_ingredients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cognito_user_id TEXT NOT NULL,
  ingredient_id INTEGER NOT NULL,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
  UNIQUE(cognito_user_id, ingredient_id)
);

-- 2. Add indexes for performance
CREATE INDEX idx_user_ingredients_cognito_user_id ON user_ingredients(cognito_user_id);
CREATE INDEX idx_user_ingredients_ingredient_id ON user_ingredients(ingredient_id);

PRAGMA user_version = 5;

COMMIT;