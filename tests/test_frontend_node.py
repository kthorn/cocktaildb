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
    ],
)
def test_frontend_contract(script):
    subprocess.run(["node", script], check=True)
