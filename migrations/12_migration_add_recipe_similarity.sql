-- Migration: Add recipe_similarity table for pre-computed similar cocktails
-- This replaces the 47MB recipe-similar.json file with indexed PostgreSQL lookups

CREATE TABLE recipe_similarity (
    recipe_id INTEGER PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
    recipe_name TEXT NOT NULL,
    neighbors JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE recipe_similarity IS 'Pre-computed similar cocktails from EM distance analysis';
