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

-- Per-row strength and display data for every recipe ingredient.
CREATE OR REPLACE VIEW recipe_abv_ingredient_rows AS
SELECT
    v.recipe_ingredient_id,
    v.recipe_id,
    v.ingredient_id,
    i.name::text AS ingredient_name,
    v.unit_name,
    v.volume_rule,
    v.invalid_reason,
    v.volume_ml,
    v.is_estimated,
    v.sort_volume,
    s.min_percent_abv,
    s.max_percent_abv,
    s.source AS strength_source,
    v.volume_rule IN ('top', 'rinse', 'measured') AS contributes,
    CASE
        WHEN s.min_percent_abv = s.max_percent_abv AND s.min_percent_abv > 0
             AND s.min_percent_abv < 1 THEN 0
        WHEN s.min_percent_abv = s.max_percent_abv THEN round(s.min_percent_abv)::integer
        ELSE floor(s.min_percent_abv)::integer
    END AS strength_display_low,
    CASE
        WHEN s.min_percent_abv = s.max_percent_abv AND s.min_percent_abv > 0
             AND s.min_percent_abv < 1 THEN 0
        WHEN s.min_percent_abv = s.max_percent_abv THEN round(s.min_percent_abv)::integer
        ELSE ceil(s.max_percent_abv)::integer
    END AS strength_display_high,
    s.min_percent_abv = s.max_percent_abv AND s.min_percent_abv > 0
        AND s.min_percent_abv < 1 AS strength_display_below_one
FROM recipe_ingredient_volumes v
JOIN ingredients i ON i.id = v.ingredient_id
JOIN ingredient_abv_resolution s ON s.ingredient_id = v.ingredient_id;

-- One row per recipe: volume-weighted ABV interval, status, and the displayed
-- whole percentages. Every decision is division-free over L = sum(v * low),
-- H = sum(v * high), and V = sum(v) across contributing rows.
CREATE OR REPLACE VIEW recipe_abv AS
WITH sums AS (
    SELECT
        r.id AS recipe_id,
        COALESCE(bool_or(rows.volume_rule = 'invalid'), FALSE) AS has_invalid,
        COALESCE(bool_or(rows.is_estimated), FALSE) AS any_estimated,
        COALESCE(
            bool_or(rows.contributes AND rows.strength_source <> 'recorded'), FALSE
        ) AS any_inferred,
        SUM(rows.volume_ml) FILTER (WHERE rows.contributes) AS v,
        SUM(rows.volume_ml * rows.min_percent_abv) FILTER (WHERE rows.contributes) AS l,
        SUM(rows.volume_ml * rows.max_percent_abv) FILTER (WHERE rows.contributes) AS h
    FROM recipes r
    LEFT JOIN recipe_abv_ingredient_rows rows ON rows.recipe_id = r.id
    GROUP BY r.id
),
classified AS (
    SELECT
        sums.*,
        CASE
            WHEN has_invalid THEN 'invalid_row'
            WHEN v IS NULL THEN 'no_volume'
            WHEN h - l > 20 * v THEN 'too_wide'
        END AS unknown_reason
    FROM sums
),
shaped AS (
    SELECT
        classified.*,
        CASE WHEN unknown_reason IS NULL THEN h - l <= v END AS narrow,
        CASE WHEN unknown_reason IS NULL THEN 0 < l + h AND l + h < 2 * v END
            AS below_one
    FROM classified
)
SELECT
    recipe_id,
    unknown_reason,
    CASE
        WHEN unknown_reason IS NOT NULL THEN 'unknown'
        WHEN any_estimated OR any_inferred THEN 'estimated'
        ELSE 'calculated'
    END AS status,
    CASE WHEN unknown_reason IS NULL OR unknown_reason = 'too_wide' THEN l / v END
        AS min_percent,
    CASE WHEN unknown_reason IS NULL OR unknown_reason = 'too_wide' THEN h / v END
        AS max_percent,
    narrow,
    CASE
        WHEN below_one THEN 0
        WHEN narrow THEN div(l + h + v, 2 * v)::integer
        WHEN NOT narrow THEN div(l, v)::integer
    END AS display_low,
    CASE
        WHEN below_one THEN 0
        WHEN narrow THEN div(l + h + v, 2 * v)::integer
        WHEN NOT narrow THEN (div(h, v) + (mod(h, v) > 0)::integer)::integer
    END AS display_high,
    narrow AND below_one AS display_below_one
FROM shaped;

COMMIT;
