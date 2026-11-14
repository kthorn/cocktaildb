from .db_utils import build_recipe_sort_spec

# Shared SQL fragments for ingredient queries
INGREDIENT_SELECT_FIELDS = """
    ri.id as recipe_ingredient_id, ri.amount, ri.ingredient_id, i.name as ingredient_name,
    ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation,
    i.path as ingredient_path, u.conversion_to_ml
"""

RESOLVE_INGREDIENT_ABV_SQL = """
SELECT
    ingredient_id,
    min_percent_abv,
    max_percent_abv,
    observation_count,
    family_id,
    family_name,
    source
FROM ingredient_abv_resolution
WHERE ingredient_id = ANY(%(ingredient_ids)s::integer[])
ORDER BY ingredient_id;
"""

RECIPE_ABV_BOUNDS_SQL = """
SELECT * FROM recipe_abv WHERE recipe_id = ANY(%(recipe_ids)s)
"""

# Rows come back in ingredient display order so notes dedupe on first use.
RECIPE_ABV_ROWS_SQL = """
SELECT * FROM recipe_abv_ingredient_rows
WHERE recipe_id = ANY(%(recipe_ids)s)
ORDER BY recipe_id, sort_volume DESC, recipe_ingredient_id
"""

# Shared substitution matching logic
# This SQL fragment checks if a user's ingredient can satisfy a recipe's ingredient requirement
# Variables that must be available in context:
#   - i_user.id, i_user.path, i_user.allow_substitution (user's ingredient)
#   - i_recipe.id, i_recipe.path, i_recipe.parent_id, i_recipe.allow_substitution (recipe's ingredient)
# Uses STARTS_WITH() instead of LIKE with % wildcard to avoid psycopg2 parameter format conflicts
# An ingredient's ancestors-or-self are exactly the ids in its path ('/1/10/388/'),
# so ancestor lookups go through the primary key instead of scanning ingredients;
# STARTS_WITH stays as the defining condition.
INGREDIENT_SUBSTITUTION_MATCH = """
    -- Direct match
    i_user.id = i_recipe.id
    OR
    -- Recipe allows substitution AND user ingredient can substitute
    (i_recipe.allow_substitution = TRUE AND (
        -- User has ancestor of recipe ingredient (user has "Rum", recipe needs "Wray And Nephew")
        -- BUT: no blocking parents in between (e.g., "Pot Still Unaged Rum" with allow_sub=false)
        (STARTS_WITH(i_recipe.path, i_user.path)
         AND NOT EXISTS (
             SELECT 1 FROM ingredients blocking
             WHERE blocking.id = ANY(string_to_array(btrim(i_recipe.path, '/'), '/')::integer[])
             AND STARTS_WITH(i_recipe.path, blocking.path)    -- blocking is ancestor of recipe ingredient
             AND STARTS_WITH(blocking.path, i_user.path)      -- blocking is descendant of user ingredient
             AND blocking.id != i_user.id                     -- not the user ingredient itself
             AND blocking.allow_substitution = FALSE          -- blocks substitution
         ))
        OR
        -- Sibling match: same parent, both allow substitution
        (i_recipe.parent_id = i_user.parent_id
         AND i_recipe.parent_id IS NOT NULL
         AND i_user.allow_substitution = TRUE)
        OR
        -- User has parent of recipe ingredient
        (i_user.id = i_recipe.parent_id)
        OR
        -- Recursive: user has common ancestor with recipe ingredient
        EXISTS (
            SELECT 1 FROM ingredients anc
            WHERE anc.id = ANY(string_to_array(btrim(i_user.path, '/'), '/')::integer[])
            AND STARTS_WITH(i_user.path, anc.path)
            AND STARTS_WITH(i_recipe.path, anc.path)
            AND anc.allow_substitution = TRUE
            AND LENGTH(anc.path) - LENGTH(REPLACE(anc.path, '/', '')) <= 6
            -- Ensure no blocking parents between common ancestor and recipe ingredient
            AND NOT EXISTS (
                SELECT 1 FROM ingredients blocking
                WHERE blocking.id = ANY(string_to_array(btrim(i_recipe.path, '/'), '/')::integer[])
                AND STARTS_WITH(i_recipe.path, blocking.path)
                AND STARTS_WITH(blocking.path, anc.path)
                AND blocking.id != anc.id
                AND blocking.allow_substitution = FALSE
            )
        )
    ))
"""

# With ignore_minor, inventory search skips ingredients at or below this
# fraction of the recipe's measurable volume (e.g. a few dashes of bitters).
MINOR_INGREDIENT_MAX_FRACTION = 0.02


def build_inventory_filter_sql(ignore_minor: bool = False) -> str:
    """Clause keeping recipes whose ingredients the user's group can cover.

    Whether a group ingredient satisfies a recipe ingredient depends only on the
    pair of ingredients, so the covered ingredients are found once per query
    (an uncorrelated subquery) rather than re-matched for every recipe row.

    Leaves the {substitution_match} placeholder for the caller's format().
    """
    minor_skip = ""
    if ignore_minor:
        minor_skip = f"""
            AND NOT COALESCE(
                (
                    SELECT v_missing.volume_ml
                    FROM recipe_ingredient_volumes v_missing
                    WHERE v_missing.recipe_ingredient_id = ri_missing.id
                ) <= {MINOR_INGREDIENT_MAX_FRACTION} * (
                    SELECT SUM(v_total.volume_ml)
                    FROM recipe_ingredient_volumes v_total
                    WHERE v_total.recipe_id = r.id
                ),
                FALSE
            )"""
    return (
        """ AND NOT EXISTS (
            SELECT 1 FROM recipe_ingredients ri_missing
            WHERE ri_missing.recipe_id = r.id"""
        + minor_skip
        + """
            AND ri_missing.ingredient_id NOT IN (
                SELECT i_recipe.id FROM ingredients i_recipe
                WHERE EXISTS (
                    SELECT 1 FROM group_ingredients ui_check
                    JOIN ingredients i_user ON ui_check.ingredient_id = i_user.id
                    WHERE ui_check.group_id = %(group_id)s
                    AND (
                        {substitution_match}
                    )
                )
            )
        )"""
    )


get_recipe_by_id_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count, r.created_by,
        STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
        STRING_AGG(CASE WHEN t.created_by = %(cognito_user_id)s THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
        ur.rating AS user_rating
    FROM
        recipes r
    LEFT JOIN
        recipe_tags rt ON r.id = rt.recipe_id
    LEFT JOIN
        tags t ON rt.tag_id = t.id
    LEFT JOIN
        ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = %(cognito_user_id)s
    WHERE r.id = %(recipe_id)s
    GROUP BY
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count, r.created_by,
        ur.rating;
"""

get_recipes_count_sql = """
    SELECT COUNT(DISTINCT r.id) as total_count
    FROM recipes r
"""

get_ingredients_count_sql = """
    SELECT COUNT(DISTINCT i.id) as total_count
    FROM ingredients i
"""

# Dynamic SQL generation function for ingredient filtering


# The ABV filter matches the whole percentages recipes display (recipe_abv's
# display_low/display_high), so search returns what users see. Emitted only when
# a bound is given; recipes whose ABV displays as Unknown never match.
ABV_FILTER_JOIN = """
        LEFT JOIN
            recipe_abv rab ON rab.recipe_id = r.id"""

ABV_FILTER_CONDITIONS = """
        AND rab.status <> 'unknown'
        AND (%(min_abv)s IS NULL OR rab.display_high >= %(min_abv)s)
        AND (%(max_abv)s IS NULL OR rab.display_low <= %(max_abv)s)"""


def build_search_recipes_paginated_sql(
    must_conditions: list[str],
    must_not_conditions: list[str],
    tag_conditions: list[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    inventory_filter: bool = False,
    rating_type: str = "average",
    ignore_minor: bool = False,
    abv_filter: bool = False,
) -> str:
    """Build the paginated search SQL with optional ingredient filtering"""
    # Determine which rating field to use for filtering
    rating_field = "r.avg_rating" if rating_type == "average" else "ur.rating"
    sort_spec = build_recipe_sort_spec(sort_by, sort_order)
    sort_expr = sort_spec.expression
    sort_direction = sort_spec.direction
    sort_expr_sr = sort_expr.replace("r.", "sr.")

    base_sql = """
    WITH search_results AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count, r.created_by,
            r.created_at,
            STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
            STRING_AGG(CASE WHEN t.created_by = %(cognito_user_id)s THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
            ur.rating AS user_rating
        FROM
            recipes r
        LEFT JOIN
            recipe_tags rt ON r.id = rt.recipe_id
        LEFT JOIN
            tags t ON rt.tag_id = t.id
        LEFT JOIN
            ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = %(cognito_user_id)s"""
    if abv_filter:
        base_sql += ABV_FILTER_JOIN
    base_sql += f"""
        WHERE
            (%(search_query)s IS NULL OR
             unaccent(r.name) ILIKE unaccent(%(search_query_with_wildcards)s))
        AND
            (%(min_rating)s IS NULL OR COALESCE({rating_field}, 0) >= %(min_rating)s)
        AND
            (%(max_rating)s IS NULL OR COALESCE({rating_field}, 0) <= %(max_rating)s)"""
    if abv_filter:
        base_sql += ABV_FILTER_CONDITIONS

    # Add MUST ingredient filtering - recipe must contain ALL of the specified ingredients
    for condition in must_conditions:
        base_sql += f" AND r.id IN (SELECT DISTINCT ri2.recipe_id FROM recipe_ingredients ri2 JOIN ingredients i2 ON ri2.ingredient_id = i2.id WHERE {condition})"

    # Add MUST_NOT ingredient filtering - recipe must NOT contain ANY of the specified ingredients
    for condition in must_not_conditions:
        base_sql += f" AND r.id NOT IN (SELECT DISTINCT ri2.recipe_id FROM recipe_ingredients ri2 JOIN ingredients i2 ON ri2.ingredient_id = i2.id WHERE {condition})"

    # Add tag filtering - recipe must have ALL of the specified tags
    if tag_conditions is None:
        tag_conditions = []
    for condition in tag_conditions:
        base_sql += f" AND r.id IN (SELECT DISTINCT rt3.recipe_id FROM recipe_tags rt3 JOIN tags t3 ON rt3.tag_id = t3.id WHERE {condition})"

    # Add inventory filtering - recipe can be made with user's inventory (substitution-aware)
    if inventory_filter:
        base_sql += build_inventory_filter_sql(ignore_minor)

    base_sql += """
        GROUP BY
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count, r.created_by,
            r.created_at,
            ur.rating"""

    # Handle random sorting separately
    if sort_by == "random":
        base_sql += """
        ORDER BY RANDOM()
        LIMIT %(limit)s OFFSET %(offset)s
    ),"""
    else:
        base_sql += """
        ORDER BY
            {sort_expr} {sort_direction},
            r.id {sort_direction}
        LIMIT %(limit)s OFFSET %(offset)s
    ),"""

    base_sql += """
    paginated_with_ingredients AS (
        SELECT
            sr.id, sr.name, sr.instructions, sr.description, sr.image_url,
            sr.source, sr.source_url, sr.avg_rating, sr.rating_count, sr.created_by,
            sr.public_tags_data, sr.private_tags_data, sr.user_rating,
            ri.id as recipe_ingredient_id, ri.amount, ri.ingredient_id, i.name as ingredient_name,
            ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation,
            i.path as ingredient_path, u.conversion_to_ml
        FROM
            search_results sr
        LEFT JOIN
            recipe_ingredients ri ON sr.id = ri.recipe_id
        LEFT JOIN
            ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN
            units u ON ri.unit_id = u.id"""

    # Handle random sorting for ingredient ordering
    if sort_by == "random":
        base_sql += """
        ORDER BY
            sr.id ASC,
            COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
            ri.id ASC
    )
    SELECT * FROM paginated_with_ingredients
    """
    else:
        base_sql += """
        ORDER BY
            {sort_expr_sr} {sort_direction},
            sr.id {sort_direction},
            COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
            ri.id ASC
    )
    SELECT * FROM paginated_with_ingredients
    """
    # Substitute the shared substitution matching logic
    return base_sql.format(
        substitution_match=INGREDIENT_SUBSTITUTION_MATCH,
        sort_expr=sort_expr,
        sort_direction=sort_direction,
        sort_expr_sr=sort_expr_sr,
    )


def build_search_recipes_keyset_sql(
    must_conditions: list[str],
    must_not_conditions: list[str],
    tag_conditions: list[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    inventory_filter: bool = False,
    rating_type: str = "average",
    ignore_minor: bool = False,
    abv_filter: bool = False,
) -> str:
    """Build the paginated search SQL using keyset (cursor) pagination."""
    rating_field = "r.avg_rating" if rating_type == "average" else "ur.rating"
    sort_spec = build_recipe_sort_spec(sort_by, sort_order)
    sort_expr = sort_spec.expression
    sort_direction = sort_spec.direction
    cursor_operator = "<" if sort_order == "desc" else ">"

    base_sql = f"""
    WITH search_results AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count, r.created_by,
            r.created_at,
            STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
            STRING_AGG(CASE WHEN t.created_by = %(cognito_user_id)s THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
            ur.rating AS user_rating,
            {sort_expr} AS sort_value
        FROM
            recipes r
        LEFT JOIN
            recipe_tags rt ON r.id = rt.recipe_id
        LEFT JOIN
            tags t ON rt.tag_id = t.id
        LEFT JOIN
            ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = %(cognito_user_id)s"""
    if abv_filter:
        base_sql += ABV_FILTER_JOIN
    base_sql += f"""
        WHERE
            (%(search_query)s IS NULL OR
             unaccent(r.name) ILIKE unaccent(%(search_query_with_wildcards)s))
        AND
            (%(min_rating)s IS NULL OR COALESCE({rating_field}, 0) >= %(min_rating)s)
        AND
            (%(max_rating)s IS NULL OR COALESCE({rating_field}, 0) <= %(max_rating)s)
        AND
            (
                %(cursor_sort)s IS NULL
                OR ({sort_expr} {cursor_operator} %(cursor_sort)s)
                OR ({sort_expr} = %(cursor_sort)s AND r.id {cursor_operator} %(cursor_id)s)
            )"""
    if abv_filter:
        base_sql += ABV_FILTER_CONDITIONS

    for condition in must_conditions:
        base_sql += f" AND r.id IN (SELECT DISTINCT ri2.recipe_id FROM recipe_ingredients ri2 JOIN ingredients i2 ON ri2.ingredient_id = i2.id WHERE {condition})"

    for condition in must_not_conditions:
        base_sql += f" AND r.id NOT IN (SELECT DISTINCT ri2.recipe_id FROM recipe_ingredients ri2 JOIN ingredients i2 ON ri2.ingredient_id = i2.id WHERE {condition})"

    if tag_conditions is None:
        tag_conditions = []
    for condition in tag_conditions:
        base_sql += f" AND r.id IN (SELECT DISTINCT rt3.recipe_id FROM recipe_tags rt3 JOIN tags t3 ON rt3.tag_id = t3.id WHERE {condition})"

    if inventory_filter:
        base_sql += build_inventory_filter_sql(ignore_minor)

    base_sql += f"""
        GROUP BY
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count, r.created_by,
            r.created_at,
            ur.rating
        ORDER BY
            sort_value {sort_direction},
            r.id {sort_direction}
        LIMIT %(limit_plus_one)s
    ),
    paginated_with_ingredients AS (
        SELECT
            sr.id, sr.name, sr.instructions, sr.description, sr.image_url,
            sr.source, sr.source_url, sr.avg_rating, sr.rating_count, sr.created_by,
            sr.public_tags_data, sr.private_tags_data, sr.user_rating,
            sr.sort_value,
            ri.id as recipe_ingredient_id, ri.amount, ri.ingredient_id, i.name as ingredient_name,
            ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation,
            i.path as ingredient_path, u.conversion_to_ml
        FROM
            search_results sr
        LEFT JOIN
            recipe_ingredients ri ON sr.id = ri.recipe_id
        LEFT JOIN
            ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN
            units u ON ri.unit_id = u.id
        ORDER BY
            sr.sort_value {sort_direction},
            sr.id {sort_direction},
            COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
            ri.id ASC
    )
    SELECT * FROM paginated_with_ingredients
    """

    return base_sql.format(substitution_match=INGREDIENT_SUBSTITUTION_MATCH)


# Ingredient Recommendations Query
# This query finds ingredients the user doesn't have that would unlock the most "almost makeable" recipes
# (recipes where user has all but one ingredient), respecting allow_substitution rules.
def get_ingredient_recommendations_sql() -> str:
    """Build SQL query for ingredient recommendations with substitution logic.

    Whether the group covers a recipe ingredient depends only on the ingredient,
    so each ingredient is matched against the inventory once, not once per
    recipe that uses it.
    """
    return f"""
    WITH
    -- Ingredients the group's inventory covers, directly or by substitution.
    -- MATERIALIZED: inlined, the match would rerun for every recipe row.
    satisfied_ingredients AS MATERIALIZED (
        SELECT i_recipe.id
        FROM ingredients i_recipe
        WHERE EXISTS (
            SELECT 1 FROM group_ingredients ui_check
            JOIN ingredients i_user ON ui_check.ingredient_id = i_user.id
            WHERE ui_check.group_id = %(group_id)s
            AND ({INGREDIENT_SUBSTITUTION_MATCH})
        )
    ),
    -- Recipes where exactly one required row is not covered, and that row
    almost_makeable_recipes AS (
        SELECT
            ri.recipe_id,
            MIN(ri.ingredient_id) FILTER (WHERE s.id IS NULL) AS missing_ingredient_id
        FROM recipe_ingredients ri
        JOIN ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN satisfied_ingredients s ON s.id = ri.ingredient_id
        GROUP BY ri.recipe_id
        HAVING COUNT(*) FILTER (WHERE s.id IS NULL) = 1
    ),
    -- Aggregate: count recipes unlocked by each missing ingredient
    ingredient_impact AS (
        SELECT
            amr.missing_ingredient_id,
            COUNT(*) as recipes_unlocked,
            STRING_AGG(r.name, '|||') as recipe_names
        FROM almost_makeable_recipes amr
        JOIN recipes r ON amr.recipe_id = r.id
        GROUP BY amr.missing_ingredient_id
        ORDER BY recipes_unlocked DESC
        LIMIT %(limit)s
    )
    -- Get full ingredient details for the recommendations
    SELECT
        i.id,
        i.name,
        i.description,
        i.parent_id,
        i.path,
        i.allow_substitution,
        ii.recipes_unlocked,
        ii.recipe_names
    FROM ingredient_impact ii
    JOIN ingredients i ON ii.missing_ingredient_id = i.id
    ORDER BY ii.recipes_unlocked DESC
    """
