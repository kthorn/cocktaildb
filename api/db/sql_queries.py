from typing import List

get_recipe_by_id_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url, 
        r.source, r.source_url, r.avg_rating, r.rating_count,
        GROUP_CONCAT(pt.id || '|||' || pt.name, ':::') AS public_tags_data,
        GROUP_CONCAT(pvt.id || '|||' || pvt.name, ':::') AS private_tags_data,
        ur.rating AS user_rating
    FROM
        recipes r
    LEFT JOIN
        recipe_public_tags rpt ON r.id = rpt.recipe_id
    LEFT JOIN
        public_tags pt ON rpt.tag_id = pt.id
    LEFT JOIN
        recipe_private_tags rpvt ON r.id = rpvt.recipe_id
    LEFT JOIN
        private_tags pvt ON rpvt.tag_id = pvt.id AND pvt.cognito_user_id = :cognito_user_id
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
        GROUP_CONCAT(pt.id || '|||' || pt.name, ':::') AS public_tags_data,
        GROUP_CONCAT(pvt.id || '|||' || pvt.name, ':::') AS private_tags_data
    FROM
        recipes r
    LEFT JOIN
        recipe_public_tags rpt ON r.id = rpt.recipe_id
    LEFT JOIN
        public_tags pt ON rpt.tag_id = pt.id
    LEFT JOIN
        recipe_private_tags rpvt ON r.id = rpvt.recipe_id
    LEFT JOIN
        private_tags pvt ON rpvt.tag_id = pvt.id AND pvt.cognito_user_id = :cognito_user_id
    GROUP BY
        r.id, r.name, r.instructions, r.description, r.image_url, 
        r.source, r.source_url, r.avg_rating, r.rating_count;
"""


def get_recipe_ingredients_by_recipe_id_sql_factory(recipe_ids: list[int]) -> str:
    recipe_ids_str = ",".join("?" for _ in recipe_ids)
    return f"""
        SELECT ri.recipe_id, ri.id as recipe_ingredient_id, ri.amount, ri.ingredient_id, i.name as ingredient_name,
                ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation,
                i.path as ingredient_path
        FROM recipe_ingredients ri
        JOIN ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN units u ON ri.unit_id = u.id
        WHERE ri.recipe_id IN ({recipe_ids_str})
    """


# Pagination SQL Queries

get_recipes_paginated_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url, 
        r.source, r.source_url, r.avg_rating, r.rating_count,
        GROUP_CONCAT(pt.id || '|||' || pt.name, ':::') AS public_tags_data,
        GROUP_CONCAT(pvt.id || '|||' || pvt.name, ':::') AS private_tags_data,
        ur.rating AS user_rating
    FROM
        recipes r
    LEFT JOIN
        recipe_public_tags rpt ON r.id = rpt.recipe_id
    LEFT JOIN
        public_tags pt ON rpt.tag_id = pt.id
    LEFT JOIN
        recipe_private_tags rpvt ON r.id = rpvt.recipe_id
    LEFT JOIN
        private_tags pvt ON rpvt.tag_id = pvt.id AND pvt.cognito_user_id = :cognito_user_id
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
"""

get_recipes_count_sql = """
    SELECT COUNT(DISTINCT r.id) as total_count
    FROM recipes r
"""

get_recipes_paginated_with_ingredients_sql = """
    WITH paginated_recipes AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url, 
            r.source, r.source_url, r.avg_rating, r.rating_count,
            GROUP_CONCAT(pt.id || '|||' || pt.name, ':::') AS public_tags_data,
            GROUP_CONCAT(pvt.id || '|||' || pvt.name, ':::') AS private_tags_data,
            ur.rating AS user_rating
        FROM
            recipes r
        LEFT JOIN
            recipe_public_tags rpt ON r.id = rpt.recipe_id
        LEFT JOIN
            public_tags pt ON rpt.tag_id = pt.id
        LEFT JOIN
            recipe_private_tags rpvt ON r.id = rpvt.recipe_id
        LEFT JOIN
            private_tags pvt ON rpvt.tag_id = pvt.id AND pvt.cognito_user_id = :cognito_user_id
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
        ri.id as recipe_ingredient_id, ri.amount,
        ri.ingredient_id, i.name as ingredient_name, i.path as ingredient_path,
        ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation
    FROM 
        paginated_recipes pr
    LEFT JOIN
        recipe_ingredients ri ON pr.id = ri.recipe_id
    LEFT JOIN
        ingredients i ON ri.ingredient_id = i.id
    LEFT JOIN
        units u ON ri.unit_id = u.id
    ORDER BY
        pr.id, ri.id
"""

# Search SQL Queries with Pagination

search_recipes_paginated_sql = """
    SELECT
        r.id, r.name, r.instructions, r.description, r.image_url, 
        r.source, r.source_url, r.avg_rating, r.rating_count,
        GROUP_CONCAT(DISTINCT pt.id || '|||' || pt.name, ':::') AS public_tags_data,
        GROUP_CONCAT(DISTINCT pvt.id || '|||' || pvt.name, ':::') AS private_tags_data,
        ur.rating AS user_rating
    FROM
        recipes r
    LEFT JOIN
        recipe_public_tags rpt ON r.id = rpt.recipe_id
    LEFT JOIN
        public_tags pt ON rpt.tag_id = pt.id
    LEFT JOIN
        recipe_private_tags rpvt ON r.id = rpvt.recipe_id
    LEFT JOIN
        private_tags pvt ON rpvt.tag_id = pvt.id AND pvt.cognito_user_id = :cognito_user_id
    LEFT JOIN
        ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = :cognito_user_id
    LEFT JOIN
        recipe_ingredients ri ON r.id = ri.recipe_id
    LEFT JOIN
        ingredients i ON ri.ingredient_id = i.id
    WHERE
        (:search_query IS NULL OR 
         remove_accents(LOWER(r.name)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%' OR 
         remove_accents(LOWER(r.description)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%' OR 
         remove_accents(LOWER(r.instructions)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%')
    AND
        (:min_rating IS NULL OR COALESCE(r.avg_rating, 0) >= :min_rating)
    AND
        (:max_rating IS NULL OR COALESCE(r.avg_rating, 0) <= :max_rating)
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
"""

search_recipes_count_sql = """
    SELECT COUNT(DISTINCT r.id) as total_count
    FROM
        recipes r
    LEFT JOIN
        recipe_ingredients ri ON r.id = ri.recipe_id
    LEFT JOIN
        ingredients i ON ri.ingredient_id = i.id
    WHERE
        (:search_query IS NULL OR 
         remove_accents(LOWER(r.name)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%' OR 
         remove_accents(LOWER(r.description)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%' OR 
         remove_accents(LOWER(r.instructions)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%')
    AND
        (:min_rating IS NULL OR COALESCE(r.avg_rating, 0) >= :min_rating)
    AND
        (:max_rating IS NULL OR COALESCE(r.avg_rating, 0) <= :max_rating)
"""

search_recipes_paginated_with_ingredients_sql = """
    WITH search_results AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url, 
            r.source, r.source_url, r.avg_rating, r.rating_count,
            GROUP_CONCAT(pt.id || '|||' || pt.name, ':::') AS public_tags_data,
            GROUP_CONCAT(pvt.id || '|||' || pvt.name, ':::') AS private_tags_data,
            ur.rating AS user_rating
        FROM
            recipes r
        LEFT JOIN
            recipe_public_tags rpt ON r.id = rpt.recipe_id
        LEFT JOIN
            public_tags pt ON rpt.tag_id = pt.id
        LEFT JOIN
            recipe_private_tags rpvt ON r.id = rpvt.recipe_id
        LEFT JOIN
            private_tags pvt ON rpvt.tag_id = pvt.id AND pvt.cognito_user_id = :cognito_user_id
        LEFT JOIN
            ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = :cognito_user_id
        LEFT JOIN
            recipe_ingredients ri ON r.id = ri.recipe_id
        LEFT JOIN
            ingredients i ON ri.ingredient_id = i.id
        WHERE
            (:search_query IS NULL OR 
             r.name LIKE '%' || :search_query || '%' OR 
             r.description LIKE '%' || :search_query || '%' OR 
             r.instructions LIKE '%' || :search_query || '%')
        AND
            (:min_rating IS NULL OR COALESCE(r.avg_rating, 0) >= :min_rating)
        AND
            (:max_rating IS NULL OR COALESCE(r.avg_rating, 0) <= :max_rating)
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
    ),
    paginated_with_ingredients AS (
        SELECT
            sr.id, sr.name, sr.instructions, sr.description, sr.image_url,
            sr.source, sr.source_url, sr.avg_rating, sr.rating_count,
            sr.public_tags_data, sr.private_tags_data, sr.user_rating,
            ri.id as recipe_ingredient_id, ri.amount,
            ri.ingredient_id, i.name as ingredient_name, i.path as ingredient_path,
            ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation
        FROM 
            search_results sr
        LEFT JOIN
            recipe_ingredients ri ON sr.id = ri.recipe_id
        LEFT JOIN
            ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN
            units u ON ri.unit_id = u.id
        ORDER BY
            sr.id, ri.id
    )
    SELECT * FROM paginated_with_ingredients
"""

# Dynamic SQL generation function for ingredient filtering
def build_search_recipes_count_sql(must_conditions: List[str], must_not_conditions: List[str], tag_conditions: List[str] = None) -> str:
    """Build the count SQL with optional ingredient and tag filtering"""
    if tag_conditions is None:
        tag_conditions = []
    
    base_sql = """
    SELECT COUNT(DISTINCT r.id) as total_count
    FROM
        recipes r
    LEFT JOIN
        recipe_ingredients ri ON r.id = ri.recipe_id
    LEFT JOIN
        ingredients i ON ri.ingredient_id = i.id"""
    
    # Add tag joins if needed
    if tag_conditions:
        base_sql += """
    LEFT JOIN
        recipe_public_tags rpt2 ON r.id = rpt2.recipe_id
    LEFT JOIN
        public_tags pt2 ON rpt2.tag_id = pt2.id
    LEFT JOIN
        recipe_private_tags rpvt2 ON r.id = rpvt2.recipe_id
    LEFT JOIN
        private_tags pvt2 ON rpvt2.tag_id = pvt2.id"""
    
    base_sql += """
    WHERE
        (:search_query IS NULL OR 
         remove_accents(LOWER(r.name)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%' OR 
         remove_accents(LOWER(r.description)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%' OR 
         remove_accents(LOWER(r.instructions)) LIKE '%' || remove_accents(LOWER(:search_query)) || '%')
    AND
        (:min_rating IS NULL OR COALESCE(r.avg_rating, 0) >= :min_rating)
    AND
        (:max_rating IS NULL OR COALESCE(r.avg_rating, 0) <= :max_rating)"""
    
    # Add MUST ingredient filtering - recipe must contain ALL of the specified ingredients
    for condition in must_conditions:
        base_sql += f" AND r.id IN (SELECT DISTINCT ri2.recipe_id FROM recipe_ingredients ri2 JOIN ingredients i2 ON ri2.ingredient_id = i2.id WHERE {condition})"
    
    # Add MUST_NOT ingredient filtering - recipe must NOT contain ANY of the specified ingredients
    for condition in must_not_conditions:
        base_sql += f" AND r.id NOT IN (SELECT DISTINCT ri2.recipe_id FROM recipe_ingredients ri2 JOIN ingredients i2 ON ri2.ingredient_id = i2.id WHERE {condition})"
    
    # Add tag filtering - recipe must have ALL of the specified tags
    for condition in tag_conditions:
        base_sql += f" AND r.id IN (SELECT DISTINCT rpt3.recipe_id FROM recipe_public_tags rpt3 JOIN public_tags pt3 ON rpt3.tag_id = pt3.id WHERE {condition} UNION SELECT DISTINCT rpvt3.recipe_id FROM recipe_private_tags rpvt3 JOIN private_tags pvt3 ON rpvt3.tag_id = pvt3.id WHERE {condition})"
    
    return base_sql

def build_search_recipes_paginated_sql(must_conditions: List[str], must_not_conditions: List[str], tag_conditions: List[str] = None) -> str:
    """Build the paginated search SQL with optional ingredient filtering"""
    base_sql = """
    WITH search_results AS (
        SELECT
            r.id, r.name, r.instructions, r.description, r.image_url, 
            r.source, r.source_url, r.avg_rating, r.rating_count,
            GROUP_CONCAT(pt.id || '|||' || pt.name, ':::') AS public_tags_data,
            GROUP_CONCAT(pvt.id || '|||' || pvt.name, ':::') AS private_tags_data,
            ur.rating AS user_rating
        FROM
            recipes r
        LEFT JOIN
            recipe_public_tags rpt ON r.id = rpt.recipe_id
        LEFT JOIN
            public_tags pt ON rpt.tag_id = pt.id
        LEFT JOIN
            recipe_private_tags rpvt ON r.id = rpvt.recipe_id
        LEFT JOIN
            private_tags pvt ON rpvt.tag_id = pvt.id AND pvt.cognito_user_id = :cognito_user_id
        LEFT JOIN
            ratings ur ON r.id = ur.recipe_id AND ur.cognito_user_id = :cognito_user_id
        LEFT JOIN
            recipe_ingredients ri ON r.id = ri.recipe_id
        LEFT JOIN
            ingredients i ON ri.ingredient_id = i.id
        WHERE
            (:search_query IS NULL OR 
             r.name LIKE '%' || :search_query || '%' OR 
             r.description LIKE '%' || :search_query || '%' OR 
             r.instructions LIKE '%' || :search_query || '%')
        AND
            (:min_rating IS NULL OR COALESCE(r.avg_rating, 0) >= :min_rating)
        AND
            (:max_rating IS NULL OR COALESCE(r.avg_rating, 0) <= :max_rating)"""

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
        base_sql += f" AND r.id IN (SELECT DISTINCT rpt3.recipe_id FROM recipe_public_tags rpt3 JOIN public_tags pt3 ON rpt3.tag_id = pt3.id WHERE {condition} UNION SELECT DISTINCT rpvt3.recipe_id FROM recipe_private_tags rpvt3 JOIN private_tags pvt3 ON rpvt3.tag_id = pvt3.id WHERE {condition})"

    base_sql += """
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
    ),
    paginated_with_ingredients AS (
        SELECT
            sr.id, sr.name, sr.instructions, sr.description, sr.image_url,
            sr.source, sr.source_url, sr.avg_rating, sr.rating_count,
            sr.public_tags_data, sr.private_tags_data, sr.user_rating,
            ri.id as recipe_ingredient_id, ri.amount,
            ri.ingredient_id, i.name as ingredient_name, i.path as ingredient_path,
            ri.unit_id, u.name as unit_name, u.abbreviation as unit_abbreviation
        FROM 
            search_results sr
        LEFT JOIN
            recipe_ingredients ri ON sr.id = ri.recipe_id
        LEFT JOIN
            ingredients i ON ri.ingredient_id = i.id
        LEFT JOIN
            units u ON ri.unit_id = u.id
        ORDER BY
            sr.id, ri.id
    )
    SELECT * FROM paginated_with_ingredients
    """
    return base_sql
