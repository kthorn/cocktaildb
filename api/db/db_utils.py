"""Database utility functions"""

from typing import Any, Dict, List


def extract_all_ingredient_ids(ingredients_list: List[Dict[str, Any]]) -> set[int]:
    """Extracts all unique ingredient IDs (direct and ancestors) from a list of ingredient data.

    Args:
        ingredients_list: List of dicts, each must contain 'ingredient_id' and 'ingredient_path'.

    Returns:
        A set of all unique integer ingredient IDs found.
    """
    all_needed_ids = set()
    unique_paths = set()  # Keep track of paths to avoid redundant parsing
    for ing in ingredients_list:
        # Add direct ID
        direct_id = ing.get("ingredient_id")
        if direct_id is not None:
            all_needed_ids.add(direct_id)

        # Collect unique paths containing ancestors
        path = ing.get("ingredient_path")
        if (
            path and path != f"/{direct_id}/"
        ):  # Only consider paths with actual ancestors
            unique_paths.add(path)

    # Parse unique paths to add ancestor IDs
    for path in unique_paths:
        parts = path.strip("/").split("/")
        # Add all numeric parts
        for part in parts:
            if part.isdigit():
                all_needed_ids.add(int(part))

    return all_needed_ids


def assemble_ingredient_full_names(
    ingredients_list: List[Dict[str, Any]], ingredient_names_map: Dict[int, str]
) -> None:
    """Helper to assemble the 'full_name' and 'hierarchy' for a list of ingredients.

    Modifies the dictionaries in ingredients_list in-place, adding two fields:
    - full_name: "Base Name [Parent;Grandparent]" (for inline display)
    - hierarchy: ["Grandparent", "Parent", "Base Name"] (for tooltips)
    """
    for ingredient in ingredients_list:
        ingredient_id = ingredient["ingredient_id"]
        ingredient_path = ingredient.get("ingredient_path")  # Use .get for safety
        # Fallback to ingredient_name field if base name isn't in the map (shouldn't happen ideally)
        base_name = ingredient_names_map.get(
            ingredient_id, ingredient.get("ingredient_name", "Unknown")
        )

        ancestor_names = []
        if ingredient_path:
            parts = ingredient_path.strip("/").split("/")
            # Iterate through ancestor IDs in the path (from root towards leaf)
            for part in parts[:-1]:
                if part.isdigit():
                    ancestor_id = int(part)
                    # Look up the name in our pre-fetched map
                    ancestor_name = ingredient_names_map.get(ancestor_id)
                    if ancestor_name:
                        ancestor_names.append(ancestor_name)

        # Set hierarchy array (root to leaf order)
        if ancestor_names:
            ingredient["hierarchy"] = ancestor_names + [base_name]
        else:
            ingredient["hierarchy"] = [base_name]

        # Construct full name (e.g., "Lime Juice [Lime;Citrus]")
        if ancestor_names:
            # Reverse the order to match original logic [parent; grandparent]
            ingredient["full_name"] = (
                f"{base_name} [{';'.join(reversed(ancestor_names))}]"
            )
        else:
            ingredient["full_name"] = base_name
