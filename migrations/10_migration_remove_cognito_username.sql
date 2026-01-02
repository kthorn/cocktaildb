-- Migration: Remove cognito_username column from ratings table
-- 
-- The cognito_username column is not used anywhere in the application.
-- Ratings are identified by cognito_user_id (UUID) which is sufficient.
-- Removing this column improves privacy for public database exports.

-- Drop the column
ALTER TABLE ratings DROP COLUMN IF EXISTS cognito_username;



