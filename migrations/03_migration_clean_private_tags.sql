-- Migration script to clean up private tags schema
-- Removes redundant cognito_username column and adds proper validation

-- First, create a new table with the cleaned schema
CREATE TABLE private_tags_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT COLLATE NOCASE NOT NULL,
  cognito_user_id TEXT NOT NULL CHECK (cognito_user_id != '')
);

-- Copy data from old table, ensuring no empty user IDs
INSERT INTO private_tags_new (id, name, cognito_user_id)
SELECT id, name, cognito_user_id 
FROM private_tags 
WHERE cognito_user_id IS NOT NULL AND cognito_user_id != '';

-- Drop the old table
DROP TABLE private_tags;

-- Rename the new table
ALTER TABLE private_tags_new RENAME TO private_tags;

-- Recreate the unique index
CREATE UNIQUE INDEX idx_private_tags ON private_tags(name, cognito_user_id);

-- Recreate the index for recipe_private_tags table
CREATE INDEX idx_recipe_private_tags_recipe_id ON recipe_private_tags(recipe_id);
CREATE INDEX idx_recipe_private_tags_tag_id ON recipe_private_tags(tag_id);

-- Update pragma version to track this migration
PRAGMA user_version = 3;

COMMIT;