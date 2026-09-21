import json
from pathlib import Path

import pytest

from api.core.frontend_assets import FrontendAssets


def write_manifest(tmp_path: Path, data: dict) -> Path:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    return manifest


def test_styles_follow_imports_and_dedupe(tmp_path):
    manifest = write_manifest(
        tmp_path,
        {
            "js/recipe.js": {
                "file": "assets/recipe-A.js",
                "imports": ["_shared"],
                "css": ["assets/recipe-A.css"],
            },
            "_shared": {
                "file": "assets/shared-B.js",
                "css": ["assets/base-B.css"],
            },
        },
    )
    assets = FrontendAssets("built", manifest)

    assert assets.script("js/recipe.js") == "/assets/recipe-A.js"
    assert assets.styles(["js/recipe.js"]) == [
        "/assets/base-B.css",
        "/assets/recipe-A.css",
    ]


def test_styles_include_css_entries_but_not_javascript_files(tmp_path):
    manifest = write_manifest(
        tmp_path,
        {
            "styles.css": {"file": "assets/styles-A.css"},
            "js/common.js": {
                "file": "assets/common-B.js",
                "css": ["assets/common-B.css"],
            },
        },
    )
    assets = FrontendAssets("built", manifest)

    assert assets.styles(["styles.css", "js/common.js"]) == [
        "/assets/styles-A.css",
        "/assets/common-B.css",
    ]


def test_styles_deduplicate_css_from_multiple_entries(tmp_path):
    manifest = write_manifest(
        tmp_path,
        {
            "first.js": {
                "file": "assets/first.js",
                "css": ["assets/shared.css", "assets/first.css"],
            },
            "second.js": {
                "file": "assets/second.js",
                "css": ["assets/shared.css", "assets/second.css"],
            },
        },
    )
    assets = FrontendAssets("built", manifest)

    assert assets.styles(["first.js", "second.js"]) == [
        "/assets/shared.css",
        "/assets/first.css",
        "/assets/second.css",
    ]


def test_styles_handle_import_cycles_once(tmp_path):
    manifest = write_manifest(
        tmp_path,
        {
            "a.js": {
                "file": "assets/a.js",
                "imports": ["b.js"],
                "css": ["assets/a.css"],
            },
            "b.js": {
                "file": "assets/b.js",
                "imports": ["a.js"],
                "css": ["assets/b.css"],
            },
        },
    )
    assets = FrontendAssets("built", manifest)

    assert assets.styles(["a.js"]) == ["/assets/b.css", "/assets/a.css"]


@pytest.mark.parametrize(
    "data",
    [
        {"entry.js": {"file": "../outside.js"}},
        {"entry.js": {"file": "/absolute.js"}},
        {"entry.js": {"file": "assets\\outside.js"}},
        {"entry.js": {"file": "assets/ok.js", "css": ["assets/../outside.css"]}},
    ],
)
def test_validate_rejects_unsafe_manifest_paths(tmp_path, data):
    assets = FrontendAssets("built", write_manifest(tmp_path, data))

    with pytest.raises(ValueError, match="path"):
        assets.script("entry.js")


def test_missing_entry_fails_clearly(tmp_path):
    assets = FrontendAssets(
        "built", write_manifest(tmp_path, {"entry.js": {"file": "assets/entry.js"}})
    )

    with pytest.raises(ValueError, match="Missing manifest entry"):
        assets.script("missing.js")


def test_malformed_manifest_fails_without_development_fallback(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")
    assets = FrontendAssets("built", manifest)

    with pytest.raises(ValueError, match="manifest"):
        assets.validate()


def test_required_entries_are_validated_at_startup(tmp_path):
    assets = FrontendAssets(
        "built",
        write_manifest(
            tmp_path,
            {"normalize.css": {"file": "assets/normalize.css"}},
        ),
    )

    with pytest.raises(ValueError, match="Missing required manifest entry"):
        assets.validate()


def test_development_mode_uses_root_absolute_source_urls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assets = FrontendAssets("development", tmp_path / "does-not-exist.json")

    assets.validate()

    assert assets.script("js/recipe.js") == "/js/recipe.js"
    assert assets.styles(["normalize.css", "styles.css"]) == [
        "/normalize.css",
        "/styles.css",
    ]


def test_default_manifest_path_is_relative_to_module_not_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assets = FrontendAssets("built")

    assert (
        assets.manifest_path
        == Path(__file__).parents[1] / "api" / "frontend-manifest.json"
    )


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        FrontendAssets("source")


def test_frontend_asset_mode_setting_is_explicit(monkeypatch):
    from api.core.config import Settings

    monkeypatch.setenv("FRONTEND_ASSET_MODE", "development")

    assert Settings().frontend_asset_mode == "development"


@pytest.mark.asyncio
async def test_application_lifespan_validates_frontend_assets(monkeypatch):
    from api import main

    calls = []

    class AssetProbe:
        def validate(self):
            calls.append("validated")

    monkeypatch.setattr(main.pages, "frontend_assets", AssetProbe())

    async with main.lifespan(main.app):
        pass

    assert calls == ["validated"]
