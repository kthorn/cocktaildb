from typing import List

# Shared SQL fragments for ingredient queries
INGREDIENT_SELECT_FIELDS = """
    ri.id as recipe_ingredient_id, ri.amount, ri.ingredient_id, i.name as ingredient_name,
    ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation,
    i.path as ingredient_path, u.conversion_to_ml
"""


get_recipe_by_id_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url, 
        r.source, r.source_url, r.avg_rating, r.rating_count,
        GROUP_CONCAT(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
        GROUP_CONCAT(CASE WHEN t.created_by = :cognito_user_id THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
        ur.rating AS user_rating
    FROM
        recipes r
    LEFT JOIN
        recipe_tags rt ON r.id = rt.recipe_id
    LEFT JOIN
        tags t ON rt.tag_id = t.id
    LEFT JOIN
        ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = :cognito_user_id
    WHERE r.id = :recipe_id
    GROUP BY
        r.id, r.name, r.instructions, r.description, r.image_url, 
        r.source, r.source_url, r.avg_rating, r.rating_count,
        ur.rating;
"""

get_all_recipes_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url, 
        r.source, r.source_url, r.avg_rating, r.rating_count,
        GROUP_CONCAT(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
        GROUP_CONCAT(CASE WHEN t.created_by = :cognito_user_id THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data
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
    recipe_ids_str = ",".join("?" for _ in recipe_ids)
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
            GROUP_CONCAT(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
            GROUP_CONCAT(CASE WHEN t.created_by = :cognito_user_id THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
            ur.rating AS user_rating
        FROM
            recipes r
        LEFT JOIN
            recipe_tags rt ON r.id = rt.recipe_id
        LEFT JOIN
            tags t ON rt.tag_id = t.id
        LEFT JOIN
            ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = :cognito_user_id
        GROUP BY
            r.id, r.name, r.instructions, r.description, r.image_url, 
            r.source, r.source_url, r.avg_rating, r.rating_count,
            ur.rating
        ORDER BY
            CASE 
                WHEN :sort_by = 'name' AND :sort_order = 'asc' THEN r.name
                WHEN :sort_by = 'avg_rating' AND :sort_order = 'asc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN :sort_by = 'created_at' AND :sort_order = 'asc' THEN r.id
            END ASC,
            CASE 
                WHEN :sort_by = 'name' AND :sort_order = 'desc' THEN r.name
                WHEN :sort_by = 'avg_rating' AND :sort_order = 'desc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN :sort_by = 'created_at' AND :sort_order = 'desc' THEN r.id
            END DESC
        LIMIT :limit OFFSET :offset
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
            GROUP_CONCAT(CASE WHEN t.created_by IS NULL THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS public_tags_data,
            GROUP_CONCAT(CASE WHEN t.created_by = :cognito_user_id THEN t.id || '|||' || t.name ELSE NULL END, ':::') AS private_tags_data,
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
             LOWER(r.name) LIKE LOWER(:search_query_with_wildcards))
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
                        -- Get effective substitution levels by walking up the hierarchy (max 3 levels deep to prevent infinite loops)
                        WITH resolved_levels AS (
                            -- For recipe ingredient: resolve its effective substitution_level
                            SELECT 
                                i_recipe.id as recipe_ingredient_id,
                                COALESCE(
                                    i_recipe.substitution_level,
                                    i_recipe_p1.substitution_level,
                                    i_recipe_p2.substitution_level,
                                    i_recipe_p3.substitution_level,
                                    0  -- Default to 0 if not found in hierarchy
                                ) as recipe_effective_level,
                                -- For user ingredient: resolve its effective substitution_level  
                                i_user.id as user_ingredient_id,
                                COALESCE(
                                    i_user.substitution_level,
                                    i_user_p1.substitution_level,
                                    i_user_p2.substitution_level,
                                    i_user_p3.substitution_level,
                                    0  -- Default to 0 if not found in hierarchy
                                ) as user_effective_level
                            FROM ingredients i_recipe
                            CROSS JOIN ingredients i_user
                            -- Recipe ingredient parent chain
                            LEFT JOIN ingredients i_recipe_p1 ON i_recipe.parent_id = i_recipe_p1.id
                            LEFT JOIN ingredients i_recipe_p2 ON i_recipe_p1.parent_id = i_recipe_p2.id  
                            LEFT JOIN ingredients i_recipe_p3 ON i_recipe_p2.parent_id = i_recipe_p3.id
                            -- User ingredient parent chain
                            LEFT JOIN ingredients i_user_p1 ON i_user.parent_id = i_user_p1.id
                            LEFT JOIN ingredients i_user_p2 ON i_user_p1.parent_id = i_user_p2.id
                            LEFT JOIN ingredients i_user_p3 ON i_user_p2.parent_id = i_user_p3.id
                            WHERE i_recipe.id = i_recipe.id AND i_user.id = i_user.id
                        )
                        SELECT 1 FROM resolved_levels rl
                        WHERE rl.recipe_ingredient_id = i_recipe.id 
                          AND rl.user_ingredient_id = i_user.id
                          AND (
                            -- Level 0: Exact match only
                            (rl.recipe_effective_level = 0 AND i_recipe.id = i_user.id)
                            OR
                            -- Level 1: Parent-level substitution
                            (rl.recipe_effective_level = 1 AND rl.user_effective_level = 1
                             AND (i_recipe.parent_id = i_user.parent_id AND i_recipe.parent_id IS NOT NULL
                                  OR i_user.path LIKE i_recipe.path || '%'))
                            OR  
                            -- Level 2: Grandparent-level substitution
                            (rl.recipe_effective_level = 2 AND rl.user_effective_level = 2
                             AND (EXISTS (
                                SELECT 1 FROM ingredients i_recipe_parent
                                WHERE i_recipe_parent.id = i_recipe.parent_id
                                AND EXISTS (
                                    SELECT 1 FROM ingredients i_user_parent  
                                    WHERE i_user_parent.id = i_user.parent_id
                                    AND i_recipe_parent.parent_id = i_user_parent.parent_id
                                    AND i_recipe_parent.parent_id IS NOT NULL
                                )
                             ) OR (
                                i_user.path LIKE i_recipe.path || '%'
                                OR (i_recipe.parent_id IS NOT NULL AND EXISTS (
                                    SELECT 1 FROM ingredients i_recipe_parent
                                    WHERE i_recipe_parent.id = i_recipe.parent_id
                                    AND i_user.path LIKE i_recipe_parent.path || '%'
                                ))
                             )))
                          )
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
                WHEN :sort_by = 'created_at' AND :sort_order = 'asc' THEN r.id
            END ASC,
            CASE
                WHEN :sort_by = 'name' AND :sort_order = 'desc' THEN r.name
                WHEN :sort_by = 'avg_rating' AND :sort_order = 'desc' THEN CAST(COALESCE(r.avg_rating, 0) AS TEXT)
                WHEN :sort_by = 'created_at' AND :sort_order = 'desc' THEN r.id
            END DESC
        LIMIT :limit OFFSET :offset
    ),"""
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
                WHEN :sort_by = 'created_at' AND :sort_order = 'asc' THEN sr.id
            END ASC,
            CASE
                WHEN :sort_by = 'name' AND :sort_order = 'desc' THEN sr.name
                WHEN :sort_by = 'avg_rating' AND :sort_order = 'desc' THEN CAST(COALESCE(sr.avg_rating, 0) AS TEXT)
                WHEN :sort_by = 'created_at' AND :sort_order = 'desc' THEN sr.id
            END DESC,
            COALESCE(ri.amount * u.conversion_to_ml, 0) DESC,
            ri.id ASC
    )
    SELECT * FROM paginated_with_ingredients
    """
    return base_sql
