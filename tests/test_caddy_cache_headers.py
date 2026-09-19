"""Deployment cache contracts for the served Caddy configuration."""

from pathlib import Path

CADDYFILE = "infrastructure/caddy/Caddyfile"


def test_cocktail_space_is_excluded_from_public_api_cache():
    source = Path(CADDYFILE).read_text(encoding="utf-8")
    stable_matcher = source.split("@api_stable", 1)[1].split("}", 1)[0]

    assert "/api/v1/analytics/cocktail-space " not in stable_matcher
    assert "/api/v1/analytics/cocktail-space-em " not in stable_matcher


def test_frontend_revalidates_and_missing_assets_do_not_fall_back():
    source = Path(CADDYFILE).read_text(encoding="utf-8")
    policy = source.split("(frontend_cache) {", 1)[-1].split("\n}", 1)[0]
    assert "@mutable path / *.html *.js *.css /recipe/* /ingredient/*" in policy
    assert 'header @mutable Cache-Control "no-cache"' in policy
    assert source.count("import frontend_cache") == 2
    assert "try_files" not in source
    assert "@static path *.js" not in source
    assert (
        "@immutable_media path *.png *.jpg *.jpeg *.gif *.svg *.woff *.woff2" in policy
    )
    assert 'header @immutable_media Cache-Control "public, max-age=3600"' in policy
