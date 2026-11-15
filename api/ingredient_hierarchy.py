"""Rules for the ingredient hierarchy."""

# Maximum number of levels in the ingredient hierarchy, counting a top-level
# ingredient as level 1. The deepest chain today is about 4.
MAX_INGREDIENT_DEPTH = 10


def path_depth(path: str | None) -> int:
    """Number of levels in a materialized path such as '/1/5/12/'."""
    return len([segment for segment in (path or "").split("/") if segment])


def depth_exceeded_message(depth: int) -> str:
    return (
        f"Ingredient would be at hierarchy level {depth}; "
        f"the maximum is {MAX_INGREDIENT_DEPTH}"
    )
