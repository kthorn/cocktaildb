from typing import List

# Shared SQL fragments for ingredient queries
INGREDIENT_SELECT_FIELDS = """
    ri.id as recipe_ingredient_id, ri.amount, ri.ingredient_id, i.name as ingredient_name,
    ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation,
    i.path as ingredient_path, u.conversion_to_ml
"""

# Shared substitution matching logic
# This SQL fragment checks if a user's ingredient can satisfy a recipe's ingredient requirement
# Variables that must be available in context:
#   - i_user.id, i_user.path, i_user.allow_substitution (user's ingredient)
#   - i_recipe.id, i_recipe.path, i_recipe.parent_id, i_recipe.allow_substitution (recipe's ingredient)
# Uses STARTS_WITH() instead of LIKE with % wildcard to avoid psycopg2 parameter format conflicts
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
             WHERE STARTS_WITH(i_recipe.path, blocking.path)  -- blocking is ancestor of recipe ingredient
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
            WHERE STARTS_WITH(i_user.path, anc.path)
            AND STARTS_WITH(i_recipe.path, anc.path)
            AND anc.allow_substitution = TRUE
            AND LENGTH(anc.path) - LENGTH(REPLACE(anc.path, '/', '')) <= 6
            -- Ensure no blocking parents between common ancestor and recipe ingredient
            AND NOT EXISTS (
                SELECT 1 FROM ingredients blocking
                WHERE STARTS_WITH(i_recipe.path, blocking.path)
                AND STARTS_WITH(blocking.path, anc.path)
                AND blocking.id != anc.id
                AND blocking.allow_substitution = FALSE
            )
        )
    ))
"""


get_recipe_by_id_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count,
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
        r.source, r.source_url, r.avg_rating, r.rating_count,
        ur.rating;
"""

get_all_recipes_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count,
        STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
        STRING_AGG(CASE WHEN t.created_by = %(cognito_user_id)s THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data
    FROM
        recipes r
    LEFT JOIN
        recipe_tags rt ON r.id = rt.recipe_id
    LEFT JOIN
        tags t ON rt.tag_id = t.id
    GROUP BY
        r.id, r.name, r.instructions, r.description, r.image_url,
        r.source, r.source_url, r.avg_rating, r.rating_count;
"""


def get_recipe_ingredients_by_recipe_id_sql_factory(recipe_ids: list[int]) -> str:
    recipe_ids_str = ",".join("%s" for _ in recipe_ids)
    return f"""
        SELECT ri.recipe_id, {INGREDIENT_SELECT_FIELDS}
        FROM recipe_ingredients ri
        JOIN ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN units u ON ri.unit_id = u.id
        WHERE ri.recipe_id IN ({recipe_ids_str})
        ORDER BY ri.recipe_id ASC,
        COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
        ri.id ASC
    """


get_recipes_count_sql = """
    SELECT COUNT(DISTINCT r.id) as total_count
    FROM recipes r
"""

get_ingredients_count_sql = """
    SELECT COUNT(DISTINCT i.id) as total_count
    FROM ingredients i
"""

get_recipes_paginated_with_ingredients_sql = """
    WITH paginated_recipes AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count,
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
        GROUP BY
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count,
            ur.rating
        ORDER BY
            CASE
                WHEN %(sort_by)s = 'name' AND %(sort_order)s = 'asc' THEN r.name
                WHEN %(sort_by)s = 'avg_rating' AND %(sort_order)s = 'asc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN %(sort_by)s = 'created_at' AND %(sort_order)s = 'asc' THEN CAST(r.id AS TEXT)
            END ASC,
            CASE
                WHEN %(sort_by)s = 'name' AND %(sort_order)s = 'desc' THEN r.name
                WHEN %(sort_by)s = 'avg_rating' AND %(sort_order)s = 'desc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN %(sort_by)s = 'created_at' AND %(sort_order)s = 'desc' THEN CAST(r.id AS TEXT)
            END DESC
        LIMIT %(limit)s OFFSET %(offset)s
    )
    SELECT
        pr.id, pr.name, pr.instructions, pr.description, pr.image_url,
        pr.source, pr.source_url, pr.avg_rating, pr.rating_count,
        pr.public_tags_data, pr.private_tags_data, pr.user_rating,
        {INGREDIENT_SELECT_FIELDS}
    FROM
        paginated_recipes pr
    LEFT JOIN
        recipe_ingredients ri ON pr.id = ri.recipe_id
    LEFT JOIN
        ingredients i ON ri.ingredient_id = i.id
    LEFT JOIN
        units u ON ri.unit_id = u.id
    ORDER BY
        pr.id ASC,
        COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
        ri.id ASC
"""

# Dynamic SQL generation function for ingredient filtering


def build_search_recipes_paginated_sql(
    must_conditions: List[str],
    must_not_conditions: List[str],
    tag_conditions: List[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    inventory_filter: bool = False,
    rating_type: str = "average",
) -> str:
    """Build the paginated search SQL with optional ingredient filtering"""
    # Determine which rating field to use for filtering
    rating_field = "r.avg_rating" if rating_type == "average" else "ur.rating"

    base_sql = f"""
    WITH search_results AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count,
            STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
            STRING_AGG(CASE WHEN t.created_by = :cognito_user_id THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
            ur.rating AS user_rating
        FROM
            recipes r
        LEFT JOIN
            recipe_tags rt ON r.id = rt.recipe_id
        LEFT JOIN
            tags t ON rt.tag_id = t.id
        LEFT JOIN
            ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = :cognito_user_id
        LEFT JOIN
            recipe_ingredients ri ON r.id = ri.recipe_id
        LEFT JOIN
            ingredients i ON ri.ingredient_id = i.id
        WHERE
            (:search_query IS NULL OR
             r.name ILIKE :search_query_with_wildcards)
        AND
            (:min_rating IS NULL OR COALESCE({rating_field}, 0) >= :min_rating)
        AND
            (:max_rating IS NULL OR COALESCE({rating_field}, 0) <= :max_rating)"""

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
        base_sql += """ AND r.id IN (
            SELECT r_inv.id 
            FROM recipes r_inv
            WHERE r_inv.id = r.id
            AND NOT EXISTS (
                SELECT 1 FROM recipe_ingredients ri_missing
                LEFT JOIN ingredients i_recipe ON ri_missing.ingredient_id = i_recipe.id
                WHERE ri_missing.recipe_id = r_inv.id
                AND NOT EXISTS (
                    SELECT 1 FROM user_ingredients ui_check
                    LEFT JOIN ingredients i_user ON ui_check.ingredient_id = i_user.id
                    WHERE ui_check.cognito_user_id = :cognito_user_id
                    AND (
                        {substitution_match}
                    )
                )
            )
        )"""

    base_sql += """
        GROUP BY
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count,
            ur.rating"""

    # Handle random sorting separately
    if sort_by == 'random':
        base_sql += """
        ORDER BY RANDOM()
        LIMIT :limit OFFSET :offset
    ),"""
    else:
        base_sql += """
        ORDER BY
            CASE
                WHEN :sort_by = 'name' AND :sort_order = 'asc' THEN r.name
                WHEN :sort_by = 'avg_rating' AND :sort_order = 'asc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN :sort_by = 'created_at' AND :sort_order = 'asc' THEN CAST(r.id AS TEXT)
            END ASC,
            CASE
                WHEN :sort_by = 'name' AND :sort_order = 'desc' THEN r.name
                WHEN :sort_by = 'avg_rating' AND :sort_order = 'desc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN :sort_by = 'created_at' AND :sort_order = 'desc' THEN CAST(r.id AS TEXT)
            END DESC
        LIMIT :limit OFFSET :offset
    ),"""

    base_sql += """
    paginated_with_ingredients AS (
        SELECT
            sr.id, sr.name, sr.instructions, sr.description, sr.image_url,
            sr.source, sr.source_url, sr.avg_rating, sr.rating_count,
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
    if sort_by == 'random':
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
            CASE
                WHEN :sort_by = 'name' AND :sort_order = 'asc' THEN sr.name
                WHEN :sort_by = 'avg_rating' AND :sort_order = 'asc' THEN CAST(COALESCE(sr.avg_rating, 0) AS TEXT)
                WHEN :sort_by = 'created_at' AND :sort_order = 'asc' THEN CAST(sr.id AS TEXT)
            END ASC,
            CASE
                WHEN :sort_by = 'name' AND :sort_order = 'desc' THEN sr.name
                WHEN :sort_by = 'avg_rating' AND :sort_order = 'desc' THEN CAST(COALESCE(sr.avg_rating, 0) AS TEXT)
                WHEN :sort_by = 'created_at' AND :sort_order = 'desc' THEN CAST(sr.id AS TEXT)
            END DESC,
            COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
            ri.id ASC
    )
    SELECT * FROM paginated_with_ingredients
    """
    # Substitute the shared substitution matching logic
    return base_sql.format(substitution_match=INGREDIENT_SUBSTITUTION_MATCH)


def build_search_recipes_keyset_sql(
    must_conditions: List[str],
    must_not_conditions: List[str],
    tag_conditions: List[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    inventory_filter: bool = False,
    rating_type: str = "average",
) -> str:
    """Build the paginated search SQL using keyset (cursor) pagination."""
    rating_field = "r.avg_rating" if rating_type == "average" else "ur.rating"

    sort_expr_map = {
        "name": "r.name",
        "avg_rating": "COALESCE(r.avg_rating, 0)",
        "created_at": "r.created_at",
    }
    sort_expr = sort_expr_map.get(sort_by, "r.name")
    sort_direction = "DESC" if sort_order == "desc" else "ASC"
    cursor_operator = "<" if sort_order == "desc" else ">"

    base_sql = f"""
    WITH search_results AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count,
            r.created_at,
            STRING_AGG(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
            STRING_AGG(CASE WHEN t.created_by = :cognito_user_id THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
            ur.rating AS user_rating,
            {sort_expr} AS sort_value
        FROM
            recipes r
        LEFT JOIN
            recipe_tags rt ON r.id = rt.recipe_id
        LEFT JOIN
            tags t ON rt.tag_id = t.id
        LEFT JOIN
            ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = :cognito_user_id
        LEFT JOIN
            recipe_ingredients ri ON r.id = ri.recipe_id
        LEFT JOIN
            ingredients i ON ri.ingredient_id = i.id
        WHERE
            (:search_query IS NULL OR
             r.name ILIKE :search_query_with_wildcards)
        AND
            (:min_rating IS NULL OR COALESCE({rating_field}, 0) >= :min_rating)
        AND
            (:max_rating IS NULL OR COALESCE({rating_field}, 0) <= :max_rating)
        AND
            (
                :cursor_sort IS NULL
                OR ({sort_expr} {cursor_operator} :cursor_sort)
                OR ({sort_expr} = :cursor_sort AND r.id {cursor_operator} :cursor_id)
            )"""

    for condition in must_conditions:
        base_sql += f" AND r.id IN (SELECT DISTINCT ri2.recipe_id FROM recipe_ingredients ri2 JOIN ingredients i2 ON ri2.ingredient_id = i2.id WHERE {condition})"

    for condition in must_not_conditions:
        base_sql += f" AND r.id NOT IN (SELECT DISTINCT ri2.recipe_id FROM recipe_ingredients ri2 JOIN ingredients i2 ON ri2.ingredient_id = i2.id WHERE {condition})"

    if tag_conditions is None:
        tag_conditions = []
    for condition in tag_conditions:
        base_sql += f" AND r.id IN (SELECT DISTINCT rt3.recipe_id FROM recipe_tags rt3 JOIN tags t3 ON rt3.tag_id = t3.id WHERE {condition})"

    if inventory_filter:
        base_sql += """ AND r.id IN (
            SELECT r_inv.id 
            FROM recipes r_inv
            WHERE r_inv.id = r.id
            AND NOT EXISTS (
                SELECT 1 FROM recipe_ingredients ri_missing
                LEFT JOIN ingredients i_recipe ON ri_missing.ingredient_id = i_recipe.id
                WHERE ri_missing.recipe_id = r_inv.id
                AND NOT EXISTS (
                    SELECT 1 FROM user_ingredients ui_check
                    LEFT JOIN ingredients i_user ON ui_check.ingredient_id = i_user.id
                    WHERE ui_check.cognito_user_id = :cognito_user_id
                    AND (
                        {substitution_match}
                    )
                )
            )
        )"""

    base_sql += f"""
        GROUP BY
            r.id, r.name, r.instructions, r.description, r.image_url,
            r.source, r.source_url, r.avg_rating, r.rating_count,
            r.created_at,
            ur.rating
        ORDER BY
            sort_value {sort_direction},
            r.id {sort_direction}
        LIMIT :limit_plus_one
    ),
    paginated_with_ingredients AS (
        SELECT
            sr.id, sr.name, sr.instructions, sr.description, sr.image_url,
            sr.source, sr.source_url, sr.avg_rating, sr.rating_count,
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
    """Build SQL query for ingredient recommendations with substitution logic"""

    # Need to adapt variable names for the CTE context:
    # In recipe search: i_user and i_recipe
    # In recommendations CTE: ui (from user_inventory) and rr (from recipe_requirements)
    # We'll create a modified version of the substitution match for this context
    # IMPORTANT: Replace more specific patterns FIRST to avoid partial matches

    substitution_match_adapted = INGREDIENT_SUBSTITUTION_MATCH.replace(
        'i_user.allow_substitution', 'ui.user_allow_substitution'
    ).replace(
        'i_user.parent_id', 'ui.parent_id'
    ).replace(
        'i_user.path', 'ui.path'
    ).replace(
        'i_user.id', 'ui.ingredient_id'
    ).replace(
        'i_recipe.allow_substitution', 'rr.required_allow_substitution'
    ).replace(
        'i_recipe.parent_id', 'rr.required_parent_id'
    ).replace(
        'i_recipe.path', 'rr.required_ingredient_path'
    ).replace(
        'i_recipe.id', 'rr.required_ingredient_id'
    )

    query = f"""
    WITH
    -- Get user's ingredient IDs and their hierarchy info
    user_inventory AS (
        SELECT
            ui.ingredient_id,
            i.path,
            i.parent_id,
            COALESCE(i.allow_substitution, FALSE) as user_allow_substitution
        FROM user_ingredients ui
        JOIN ingredients i ON ui.ingredient_id = i.id
        WHERE ui.cognito_user_id = :user_id
    ),
    -- For each recipe, find all required ingredients
    recipe_requirements AS (
        SELECT
            ri.recipe_id,
            ri.ingredient_id as required_ingredient_id,
            i.name as required_ingredient_name,
            i.path as required_ingredient_path,
            i.parent_id as required_parent_id,
            COALESCE(i.allow_substitution, FALSE) as required_allow_substitution
        FROM recipe_ingredients ri
        JOIN ingredients i ON ri.ingredient_id = i.id
    ),
    -- Check each recipe requirement against user inventory
    requirement_satisfaction AS (
        SELECT
            rr.recipe_id,
            rr.required_ingredient_id,
            rr.required_ingredient_name,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM user_inventory ui
                    WHERE
                        {substitution_match_adapted}
                ) THEN 1
                ELSE 0
            END as is_satisfied
        FROM recipe_requirements rr
    ),
    -- Find recipes where user has all but exactly 1 ingredient
    almost_makeable_recipes AS (
        SELECT
            recipe_id,
            COUNT(*) as total_requirements,
            SUM(is_satisfied) as satisfied_count,
            COUNT(*) - SUM(is_satisfied) as missing_count
        FROM requirement_satisfaction
        GROUP BY recipe_id
        HAVING COUNT(*) - SUM(is_satisfied) = 1
    ),
    -- Find the missing ingredient for each almost-makeable recipe
    missing_ingredients AS (
        SELECT
            rs.recipe_id,
            rs.required_ingredient_id as missing_ingredient_id,
            rs.required_ingredient_name as missing_ingredient_name
        FROM requirement_satisfaction rs
        JOIN almost_makeable_recipes amr ON rs.recipe_id = amr.recipe_id
        WHERE rs.is_satisfied = 0
    ),
    -- Aggregate: count recipes unlocked by each missing ingredient
    ingredient_impact AS (
        SELECT
            mi.missing_ingredient_id,
            COUNT(*) as recipes_unlocked,
            STRING_AGG(r.name, '|||') as recipe_names
        FROM missing_ingredients mi
        JOIN recipes r ON mi.recipe_id = r.id
        GROUP BY mi.missing_ingredient_id
        ORDER BY recipes_unlocked DESC
        LIMIT :limit
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

    return query
