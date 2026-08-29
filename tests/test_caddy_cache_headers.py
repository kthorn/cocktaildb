"""Caddy must not publicly cache personalized cocktail-space responses."""
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "config_path",
    [
        "infrastructure/caddy/Caddyfile",
        "infrastructure/ansible/files/Caddyfile.j2",
    ],
)
def test_cocktail_space_is_excluded_from_public_api_cache(config_path):
    source = Path(config_path).read_text(encoding="utf-8")
    stable_matcher = source.split("@api_stable", 1)[1].split("}", 1)[0]

    assert "/api/v1/analytics/cocktail-space " not in stable_matcher
    assert "/api/v1/analytics/cocktail-space-em " not in stable_matcher
