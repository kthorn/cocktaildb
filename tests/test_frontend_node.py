"""Run dependency-free frontend contract tests under pytest."""

import subprocess

import pytest


@pytest.mark.parametrize(
    "script",
    [
        "tests/test_cocktail_space_callouts.js",
        "tests/test_cocktail_space_layout.mjs",
        "tests/test_admin_public_tags.js",
        "tests/test_search_pagination.js",
        "tests/test_static_frontend_head.mjs",
        "tests/test_ingredient_tree.mjs",
        "tests/test_ingredient_delegation.mjs",
        "tests/test_ingredient_tree_chart_tooltip.js",
        "tests/test_recipe_card_modules.mjs",
    ],
)
def test_frontend_contract(script):
    subprocess.run(["node", script], check=True)
