-- Move recipe ABV rules into views: strength, volume, contribution rows, recipe ABV.
BEGIN;

-- Nearest populated family strength for every ingredient; unknown means 0-100%.
CREATE OR REPLACE VIEW ingredient_abv_resolution AS
WITH RECURSIVE walk(requested_id, candidate_id, depth, visited) AS (
    SELECT i.id, i.id, 0, ARRAY[i.id]::integer[]
    FROM ingredients i

    UNION ALL

    SELECT w.requested_id, parent.id, w.depth + 1, w.visited || parent.id
    FROM walk w
    JOIN ingredients current ON current.id = w.candidate_id
    JOIN ingredients parent ON parent.id = current.parent_id
    WHERE NOT parent.id = ANY(w.visited)
),
selected AS (
    SELECT DISTINCT ON (w.requested_id)
        w.requested_id,
        w.candidate_id,
        w.depth,
        ranges.min_percent_abv,
        ranges.max_percent_abv,
        ranges.observation_count,
        candidate.name::text AS family_name
    FROM walk w
    JOIN ingredient_abv_ranges ranges ON ranges.ingredient_id = w.candidate_id
    JOIN ingredients candidate ON candidate.id = w.candidate_id
    WHERE ranges.observation_count > 0
    ORDER BY w.requested_id, w.depth, w.candidate_id
)
SELECT
    ingredient.id AS ingredient_id,
    COALESCE(selected.min_percent_abv, 0::numeric) AS min_percent_abv,
    COALESCE(selected.max_percent_abv, 100::numeric) AS max_percent_abv,
    COALESCE(selected.observation_count, 0::bigint) AS observation_count,
    selected.candidate_id AS family_id,
    selected.family_name,
    CASE
        WHEN selected.requested_id IS NULL THEN 'unknown'
        WHEN selected.depth = 0
             AND ingredient.percent_abv IS NOT NULL
             AND ingredient.percent_abv <> 'NaN'::numeric
             AND ingredient.percent_abv BETWEEN 0 AND 100
             AND NOT EXISTS (
                 SELECT 1
                 FROM ingredients child
                 WHERE child.parent_id = ingredient.id
             )
            THEN 'recorded'
        ELSE 'family'
    END AS source,
    selected.requested_id IS NOT NULL AS has_observations
FROM ingredients ingredient
LEFT JOIN selected ON selected.requested_id = ingredient.id;

-- Modeled volume for every recipe_ingredients row; the only encoding of these rules.
-- REAL values convert through their text form so they match psycopg2's view of them.
CREATE OR REPLACE VIEW recipe_ingredient_volumes AS
WITH normalized AS (
    SELECT
        ri.id AS recipe_ingredient_id,
        ri.recipe_id,
        ri.ingredient_id,
        u.name AS unit_name,
        NULLIF(LOWER(BTRIM(u.name, E' \t\r\n')), '') AS unit_key,
        ri.amount,
        u.conversion_to_ml,
        COALESCE(ri.amount * u.conversion_to_ml, 0) AS sort_volume
    FROM recipe_ingredients ri
    LEFT JOIN units u ON u.id = ri.unit_id
),
classified AS (
    SELECT
        n.*,
        CASE
            WHEN n.amount IN ('NaN', 'Infinity', '-Infinity') THEN 'non_finite_amount'
            WHEN n.amount < 0 THEN 'negative_amount'
            WHEN n.amount = 0 THEN NULL
            WHEN n.unit_key IN ('each', 'to top', 'to rinse') THEN NULL
            WHEN n.unit_key IS NULL THEN 'missing_unit'
            WHEN n.amount IS NULL THEN 'missing_amount'
            WHEN n.conversion_to_ml IS NULL
                 OR n.conversion_to_ml IN ('NaN', 'Infinity', '-Infinity')
                 OR n.conversion_to_ml <= 0
                THEN 'invalid_conversion'
        END AS invalid_reason
    FROM normalized n
),
ruled AS (
    SELECT
        c.*,
        CASE
            WHEN c.invalid_reason IS NOT NULL THEN 'invalid'
            WHEN c.amount = 0 THEN 'zero'
            WHEN c.unit_key = 'each' THEN 'counted'
            WHEN c.unit_key = 'to top' THEN 'top'
            WHEN c.unit_key = 'to rinse' THEN 'rinse'
            ELSE 'measured'
        END AS volume_rule
    FROM classified c
)
SELECT
    recipe_ingredient_id,
    recipe_id,
    ingredient_id,
    unit_name,
    volume_rule,
    invalid_reason,
    CASE volume_rule
        WHEN 'zero' THEN 0::numeric
        WHEN 'top' THEN 88.7205::numeric
        WHEN 'rinse' THEN 1::numeric
        WHEN 'measured' THEN amount::text::numeric * conversion_to_ml::text::numeric
    END AS volume_ml,
    volume_rule IN ('counted', 'top', 'rinse') AS is_estimated,
    sort_volume
FROM ruled;

COMMIT;
