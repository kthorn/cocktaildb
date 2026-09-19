-- Move legacy personal inventories into shared user groups.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM user_ingredients WHERE added_at IS NULL) THEN
        RAISE EXCEPTION 'Resolve null user_ingredients.added_at before group migration';
    END IF;
END
$$;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    invite_code TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    cognito_user_id TEXT NOT NULL UNIQUE,
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE group_ingredients (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL,
    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (group_id, ingredient_id)
);

CREATE INDEX idx_user_group_members_group_id ON user_group_members(group_id);
CREATE INDEX idx_group_ingredients_ingredient_id ON group_ingredients(ingredient_id);

CREATE TRIGGER update_user_groups_updated_at
    BEFORE UPDATE ON user_groups
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Deduplicate users before generating volatile invite codes.  A random code
-- is therefore generated once per user, even when their inventory has many rows.
CREATE TEMP TABLE user_group_mapping ON COMMIT DROP AS
SELECT cognito_user_id, encode(gen_random_bytes(6), 'hex') AS invite_code
FROM (SELECT DISTINCT cognito_user_id FROM user_ingredients) AS users;

INSERT INTO user_groups (name, invite_code)
SELECT 'My Bar', invite_code
FROM user_group_mapping;

INSERT INTO user_group_members (group_id, cognito_user_id)
SELECT g.id, m.cognito_user_id
FROM user_group_mapping AS m
JOIN user_groups AS g USING (invite_code);

INSERT INTO group_ingredients (group_id, ingredient_id, added_by, added_at)
SELECT m.group_id, ui.ingredient_id, ui.cognito_user_id, ui.added_at
FROM user_ingredients AS ui
JOIN user_group_members AS m USING (cognito_user_id);

COMMIT;
