-- Migration: Enable unaccent extension for accent-insensitive recipe search
-- This allows searches like "pina" to match "piña" and vice versa

CREATE EXTENSION IF NOT EXISTS unaccent;
