CREATE EXTENSION IF NOT EXISTS citext;

ALTER TABLE recipes
    ALTER COLUMN name TYPE citext;

ALTER TABLE ingredients
    ALTER COLUMN name TYPE citext,
    ADD COLUMN IF NOT EXISTS percent_abv NUMERIC CHECK (percent_abv >= 0 AND percent_abv <= 100),
    ADD COLUMN IF NOT EXISTS sugar_g_per_l NUMERIC CHECK (sugar_g_per_l >= 0 AND sugar_g_per_l <= 1000),
    ADD COLUMN IF NOT EXISTS titratable_acidity_g_per_l NUMERIC CHECK (titratable_acidity_g_per_l >= 0 AND titratable_acidity_g_per_l <= 100),
    ADD COLUMN IF NOT EXISTS url TEXT;

CREATE INDEX IF NOT EXISTS idx_recipes_name_id ON recipes (name, id);
CREATE INDEX IF NOT EXISTS idx_recipes_avg_rating_id ON recipes (avg_rating, id);
CREATE INDEX IF NOT EXISTS idx_recipes_created_at_id ON recipes (created_at, id);
CREATE INDEX IF NOT EXISTS idx_recipes_rating_count_id ON recipes (rating_count, id);
