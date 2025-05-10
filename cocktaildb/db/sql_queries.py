get_recipe_by_id_sql = """
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
    WHERE r.id = :recipe_id
    GROUP BY
        r.id, r.name, r.instructions, r.description, r.image_url, 
        r.source, r.source_url, r.avg_rating, r.rating_count;
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
