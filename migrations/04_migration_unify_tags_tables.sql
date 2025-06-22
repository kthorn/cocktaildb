-- Migration: Convert separate public/private tag tables to unified tags table
-- This migration preserves all existing data while fixing ID collision issues

-- 1. Create new unified tags table
CREATE TABLE tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT COLLATE NOCASE NOT NULL,
  created_by TEXT NULL, -- NULL for public tags, user_id for private tags
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Migrate existing public tags (preserve IDs and data)
INSERT INTO tags (id, name, created_by, created_at)
SELECT id, name, NULL, CURRENT_TIMESTAMP FROM public_tags;

-- 3. Create new unified junction table
CREATE TABLE recipe_tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
  UNIQUE(recipe_id, tag_id)
);

-- 4. Migrate existing recipe-tag associations from public tags
INSERT INTO recipe_tags (recipe_id, tag_id)
SELECT recipe_id, tag_id FROM recipe_public_tags;

-- 5. Migrate existing recipe-tag associations from private tags (if any exist)
-- Note: Currently no private tags exist, but include for completeness
INSERT INTO recipe_tags (recipe_id, tag_id)
SELECT rpt.recipe_id, pt.id 
FROM recipe_private_tags rpt
JOIN private_tags pt ON rpt.tag_id = pt.id
WHERE EXISTS (
    SELECT 1 FROM tags t 
    WHERE t.name = pt.name 
    AND t.created_by = pt.cognito_user_id
);

-- 6. Clean up old tables
DROP TABLE IF EXISTS recipe_public_tags;
DROP TABLE IF EXISTS recipe_private_tags;
DROP TABLE IF EXISTS public_tags;
DROP TABLE IF EXISTS private_tags;

-- 7. Add indexes for performance
CREATE UNIQUE INDEX idx_public_tags ON tags(name) WHERE created_by IS NULL;
CREATE UNIQUE INDEX idx_private_tags ON tags(name, created_by) WHERE created_by IS NOT NULL;
CREATE INDEX idx_recipe_tags_recipe_id ON recipe_tags(recipe_id);
CREATE INDEX idx_recipe_tags_tag_id ON recipe_tags(tag_id);
CREATE INDEX idx_tags_created_by ON tags(created_by);

-- Verify migration
-- SELECT 'Migration completed. Tag counts:' as status;
-- SELECT 
--   COUNT(*) as total_tags,
--   SUM(CASE WHEN created_by IS NULL THEN 1 ELSE 0 END) as public_tags,
--   SUM(CASE WHEN created_by IS NOT NULL THEN 1 ELSE 0 END) as private_tags
-- FROM tags;