from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "infrastructure" / "scripts" / "frontend-release.py"


@pytest.fixture
def release_module():
    spec = importlib.util.spec_from_file_location("frontend_release", HELPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_release(
    app_home: Path,
    release_id: str,
    files: dict[str, str],
    *,
    include_assets: bool = True,
) -> Path:
    release = app_home / "releases" / release_id
    assets = release / "web" / "assets"
    (release / "web" / "js").mkdir(parents=True)
    (release / "web" / "js" / "config.js").write_text(
        "export default { apiUrl: 'https://api.example.test' };\n"
    )
    if include_assets:
        assets.mkdir()
        for name, value in files.items():
            path = assets / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "index.html": {
                    "file": f"assets/{next(iter(files))}"
                    if files
                    else "assets/empty.js"
                }
            }
        )
    )
    (release / "asset-inventory.json").write_text(
        json.dumps({"version": 1, "files": sorted(files)})
    )
    return release


def _write_record(app_home: Path, record: dict, files: list[str]) -> None:
    web = app_home / record["web"]
    web.mkdir(parents=True)
    (web / "index.html").write_text(record["id"])
    if record.get("inventory"):
        inventory = app_home / record["inventory"]
        inventory.parent.mkdir(parents=True, exist_ok=True)
        inventory.write_text(json.dumps({"version": 1, "files": sorted(files)}))


def test_shared_asset_survives_two_generation_prune(tmp_path, release_module):
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ["old.js", "shared.js", "current.js"]:
        (assets / name).write_text(name)
    release_module.prune_assets(assets, {"shared.js", "current.js"})
    assert sorted(p.name for p in assets.iterdir()) == ["current.js", "shared.js"]


def test_inventory_rejects_path_escape(tmp_path, release_module):
    release = _write_release(tmp_path / "app", "A", {"safe.js": "safe"})
    (release / "asset-inventory.json").write_text(
        json.dumps({"version": 1, "files": ["../escape.js"]})
    )
    with pytest.raises(release_module.FrontendReleaseError, match="safe relative"):
        release_module.validate_release(release)


def test_asset_symlink_is_rejected(tmp_path, release_module):
    app_home = tmp_path / "app"
    release = _write_release(app_home, "A", {"safe.js": "safe"})
    (release / "web" / "assets" / "link.js").symlink_to("safe.js")
    (release / "asset-inventory.json").write_text(
        json.dumps({"version": 1, "files": ["link.js", "safe.js"]})
    )
    with pytest.raises(release_module.FrontendReleaseError, match="symlink"):
        release_module.publish_assets(release, app_home)


def test_conflicting_immutable_asset_fails_without_overwrite(tmp_path, release_module):
    app_home = tmp_path / "app"
    release = _write_release(app_home, "A", {"same.js": "new"})
    shared = app_home / "frontend-assets"
    shared.mkdir(parents=True)
    (shared / "same.js").write_text("old")
    with pytest.raises(release_module.FrontendReleaseError, match="different bytes"):
        release_module.publish_assets(release, app_home)
    assert (shared / "same.js").read_text() == "old"
    assert (release / "web" / "assets" / "same.js").exists()


def test_failed_copy_leaves_release_assets_intact(
    tmp_path, release_module, monkeypatch
):
    app_home = tmp_path / "app"
    release = _write_release(app_home, "A", {"one.js": "one"})

    def fail_copy(*_args, **_kwargs):
        raise OSError("injected copy failure")

    monkeypatch.setattr(release_module.shutil, "copyfileobj", fail_copy)
    with pytest.raises(OSError, match="injected copy failure"):
        release_module.publish_assets(release, app_home)
    assert (release / "web" / "assets" / "one.js").exists()
    assert not (app_home / "frontend-assets" / "one.js").exists()


def test_real_directory_conversion_restores_previous_web_on_replace_failure(
    tmp_path, release_module, monkeypatch
):
    app_home = tmp_path / "app"
    app_home.mkdir()
    served = app_home / "web"
    served.mkdir(parents=True)
    (served / "old.html").write_text("old")
    release = _write_release(app_home, "A", {"one.js": "one"})
    release_module.publish_assets(release, app_home)

    original_replace = release_module.os.replace
    calls = 0

    def fail_new_link(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected link replacement failure")
        return original_replace(source, destination)

    monkeypatch.setattr(release_module.os, "replace", fail_new_link)
    with pytest.raises(OSError, match="injected link replacement failure"):
        release_module.publish_web(release, served, app_home)
    assert served.is_dir() and not served.is_symlink()
    assert (served / "old.html").read_text() == "old"
    assert not (app_home / "releases" / "previous-web-A").exists()


def test_pending_marker_blocks_new_publication_and_prune(tmp_path, release_module):
    app_home = tmp_path / "app"
    release = _write_release(app_home, "A", {"one.js": "one"})
    release_module.begin(release, "cocktaildb-api:release-A", app_home)
    with pytest.raises(release_module.FrontendReleaseError, match="pending"):
        release_module.begin(release, "cocktaildb-api:release-A", app_home)
    with pytest.raises(release_module.FrontendReleaseError, match="pending"):
        release_module.prune(app_home)


def test_three_generation_prune_uses_current_previous_union(tmp_path, release_module):
    app_home = tmp_path / "app"
    asset_root = app_home / "frontend-assets"
    asset_root.mkdir(parents=True)
    for name in ["old.js", "shared.js", "current.js"]:
        (asset_root / name).write_text(name)
    records = {
        "current": {
            "id": "C",
            "web": "releases/C/web",
            "inventory": "releases/C/frontend-assets.json",
            "image": "cocktaildb-api:release-C",
            "legacy": False,
        },
        "previous": {
            "id": "B",
            "web": "releases/B/web",
            "inventory": "releases/B/frontend-assets.json",
            "image": "cocktaildb-api:release-B",
            "legacy": False,
        },
        "retired": [
            {
                "id": "A",
                "web": "releases/A/web",
                "inventory": "releases/A/frontend-assets.json",
                "image": "cocktaildb-api:release-A",
                "legacy": False,
            }
        ],
    }
    _write_record(app_home, records["current"], ["current.js", "shared.js"])
    _write_record(app_home, records["previous"], ["shared.js"])
    _write_record(app_home, records["retired"][0], ["old.js"])
    (app_home / "releases" / "A" / "api").mkdir()
    (app_home / "releases" / "A" / "api" / "keep.txt").write_text("api")
    (app_home / "frontend-state.json").write_text(json.dumps({"version": 1, **records}))
    release_module.prune(app_home)
    assert sorted(p.name for p in asset_root.iterdir()) == ["current.js", "shared.js"]
    assert not (app_home / "releases" / "A" / "web").exists()
    assert not (app_home / "releases" / "A" / "frontend-assets.json").exists()
    assert (app_home / "releases" / "A" / "api" / "keep.txt").exists()


def test_corrupt_retained_inventory_aborts_without_deleting_assets(
    tmp_path, release_module
):
    app_home = tmp_path / "app"
    asset_root = app_home / "frontend-assets"
    asset_root.mkdir(parents=True)
    (asset_root / "keep.js").write_text("keep")
    current = {
        "id": "B",
        "web": "releases/B/web",
        "inventory": "releases/B/frontend-assets.json",
        "image": "cocktaildb-api:release-B",
        "legacy": False,
    }
    _write_record(app_home, current, ["keep.js"])
    previous = {
        "id": "A",
        "web": "releases/A/web",
        "inventory": "releases/A/frontend-assets.json",
        "image": "cocktaildb-api:release-A",
        "legacy": False,
    }
    _write_record(app_home, previous, ["keep.js"])
    (app_home / previous["inventory"]).write_text("not json")
    (asset_root / "obsolete.js").write_text("obsolete")
    (app_home / "frontend-state.json").write_text(
        json.dumps(
            {"version": 1, "current": current, "previous": previous, "retired": []}
        )
    )
    with pytest.raises(release_module.FrontendReleaseError, match="inventory"):
        release_module.prune(app_home)
    assert (asset_root / "obsolete.js").exists()


def test_legacy_first_release_preserves_real_web_and_commits_record(
    tmp_path, release_module
):
    app_home = tmp_path / "app"
    app_home.mkdir()
    served = app_home / "web"
    served.mkdir(parents=True)
    (served / "old.html").write_text("old")
    release = _write_release(app_home, "A", {"one.js": "one"})
    release_module.begin(release, "cocktaildb-api:release-A", app_home)
    release_module.publish_assets(release, app_home)
    release_module.publish(release, served, app_home)
    release_module.commit(release, "cocktaildb-api:release-A", app_home)
    state = json.loads((app_home / "frontend-state.json").read_text())
    assert state["previous"]["legacy"] is True
    assert state["previous"]["inventory"] is None
    assert (app_home / state["previous"]["web"]).is_dir()
    assert served.is_symlink()


def _write_prune_sentinels(app_home: Path, release_module, retired_web: str):
    current = {
        "id": "current",
        "web": "releases/current/web",
        "inventory": "releases/current/frontend-assets.json",
        "image": "cocktaildb-api:release-current",
        "legacy": False,
    }
    previous = {
        "id": "previous",
        "web": "releases/previous/web",
        "inventory": "releases/previous/frontend-assets.json",
        "image": "cocktaildb-api:release-previous",
        "legacy": False,
    }
    retired = {
        "id": "retired",
        "web": retired_web,
        "inventory": "releases/retired/frontend-assets.json",
        "image": "cocktaildb-api:release-retired",
        "legacy": False,
    }
    for record, files in (
        (current, ["current.js", "shared.js"]),
        (previous, ["shared.js"]),
    ):
        _write_record(app_home, record, files)
    asset_root = app_home / "frontend-assets"
    asset_root.mkdir(parents=True, exist_ok=True)
    for name in ("current.js", "shared.js", "obsolete.js"):
        (asset_root / name).write_text(name)
    (app_home / current["web"] / "current-sentinel.txt").write_text("current")
    (app_home / previous["web"] / "previous-sentinel.txt").write_text("previous")
    old_root = app_home / "releases" / "retired"
    (old_root / "api").mkdir(parents=True, exist_ok=True)
    (old_root / "api" / "api-sentinel.txt").write_text("api")
    (old_root / "migrations").mkdir(parents=True, exist_ok=True)
    (old_root / "migrations" / "migration-sentinel.sql").write_text("migration")
    (app_home / retired["inventory"]).write_text(
        json.dumps({"version": 1, "files": ["obsolete.js"]})
    )
    outside = app_home.parent / "outside-target"
    outside.mkdir()
    (outside / "outside-sentinel.txt").write_text("outside")
    if retired_web.endswith("/web"):
        old_web = app_home / retired_web
        if not (old_web.exists() or old_web.is_symlink()):
            old_web.parent.mkdir(parents=True, exist_ok=True)
            old_web.symlink_to(outside, target_is_directory=True)
    state = {
        "version": 1,
        "current": current,
        "previous": previous,
        "retired": [retired],
    }
    (app_home / "frontend-state.json").write_text(json.dumps(state))
    return state, outside


@pytest.mark.parametrize(
    "retired_web",
    ["releases/retired", "releases/current/web", "releases/retired/web"],
)
def test_rejected_cleanup_preserves_all_frontend_and_release_sentinels(
    tmp_path, release_module, retired_web
):
    app_home = tmp_path / "app"
    app_home.mkdir()
    state, outside = _write_prune_sentinels(app_home, release_module, retired_web)

    with pytest.raises(release_module.FrontendReleaseError):
        release_module.prune(app_home)

    assert (app_home / "releases" / "retired" / "api" / "api-sentinel.txt").exists()
    assert (
        app_home / "releases" / "retired" / "migrations" / "migration-sentinel.sql"
    ).exists()
    assert (outside / "outside-sentinel.txt").exists()
    assert (app_home / state["current"]["web"] / "current-sentinel.txt").exists()
    assert (app_home / state["previous"]["web"] / "previous-sentinel.txt").exists()
    assert (app_home / "frontend-assets" / "obsolete.js").exists()
    assert json.loads((app_home / "frontend-state.json").read_text()) == state


def test_rejected_cleanup_does_not_follow_symlinked_release_ancestor(
    tmp_path, release_module
):
    app_home = tmp_path / "app"
    app_home.mkdir()
    outside_releases = tmp_path / "outside-releases"
    outside_releases.mkdir()
    (app_home / "releases").symlink_to(outside_releases, target_is_directory=True)
    state, _ = _write_prune_sentinels(app_home, release_module, "releases/retired/web")

    with pytest.raises(release_module.FrontendReleaseError, match="symlink"):
        release_module.prune(app_home)

    assert (outside_releases / "current" / "web" / "current-sentinel.txt").exists()
    assert (outside_releases / "retired" / "api" / "api-sentinel.txt").exists()
    assert (app_home / "frontend-assets" / "obsolete.js").exists()
    assert json.loads((app_home / "frontend-state.json").read_text()) == state


def test_prune_allows_missing_retired_paths_for_idempotent_retry(
    tmp_path, release_module
):
    app_home = tmp_path / "app"
    app_home.mkdir()
    current = {
        "id": "current",
        "web": "releases/current/web",
        "inventory": "releases/current/frontend-assets.json",
        "image": "cocktaildb-api:release-current",
        "legacy": False,
    }
    previous = {
        "id": "previous",
        "web": "releases/previous/web",
        "inventory": "releases/previous/frontend-assets.json",
        "image": "cocktaildb-api:release-previous",
        "legacy": False,
    }
    retired = {
        "id": "retired",
        "web": "releases/retired/web",
        "inventory": "releases/retired/frontend-assets.json",
        "image": "cocktaildb-api:release-retired",
        "legacy": False,
    }
    _write_record(app_home, current, ["current.js"])
    _write_record(app_home, previous, ["previous.js"])
    assets = app_home / "frontend-assets"
    assets.mkdir(parents=True)
    for name in ("current.js", "previous.js", "obsolete.js"):
        (assets / name).write_text(name)
    state = {
        "version": 1,
        "current": current,
        "previous": previous,
        "retired": [retired],
    }
    (app_home / "frontend-state.json").write_text(json.dumps(state))

    release_module.prune(app_home)

    assert sorted(path.name for path in assets.iterdir()) == [
        "current.js",
        "previous.js",
    ]
    assert json.loads((app_home / "frontend-state.json").read_text())["retired"] == []


def test_recover_clears_marker_when_state_already_committed(tmp_path, release_module):
    app_home = tmp_path / "app"
    app_home.mkdir()
    release = _write_release(app_home, "A", {"one.js": "one"})
    image = "cocktaildb-api:release-A"
    release_module.publish_assets(release, app_home)
    served = app_home / "web"
    served.symlink_to(release / "web", target_is_directory=True)
    record = release_module._record(release, app_home, image)
    (app_home / "frontend-state.json").write_text(
        json.dumps({"version": 1, "current": record, "previous": None, "retired": []})
    )
    (app_home / "frontend-pending.json").write_text(
        json.dumps(
            {
                "version": 1,
                "candidate": record,
                "previous": None,
                "legacy_previous_web": None,
            }
        )
    )

    result = release_module.recover(release, image, app_home)

    assert result["current"] == record
    assert not (app_home / "frontend-pending.json").exists()


def test_cleanup_retry_retains_retired_record_until_deletion_succeeds(
    tmp_path, release_module
):
    app_home = tmp_path / "app"
    app_home.mkdir()
    current = {
        "id": "B",
        "web": "releases/B/web",
        "inventory": "releases/B/frontend-assets.json",
        "image": "cocktaildb-api:release-B",
        "legacy": False,
    }
    previous = {
        "id": "A",
        "web": "releases/A/web",
        "inventory": "releases/A/frontend-assets.json",
        "image": "cocktaildb-api:release-A",
        "legacy": False,
    }
    retired = {
        "id": "old",
        "web": "releases/old/web",
        "inventory": "releases/old/frontend-assets.json",
        "image": "cocktaildb-api:release-old",
        "legacy": False,
    }
    for record in (current, previous):
        _write_record(app_home, record, ["keep.js"])
    old_web = app_home / retired["web"]
    old_web.parent.mkdir(parents=True, exist_ok=True)
    old_web.symlink_to(app_home / "outside", target_is_directory=True)
    (app_home / retired["inventory"]).parent.mkdir(parents=True, exist_ok=True)
    (app_home / retired["inventory"]).write_text(
        json.dumps({"version": 1, "files": ["old.js"]})
    )
    (app_home / "frontend-assets").mkdir(parents=True)
    (app_home / "frontend-assets" / "keep.js").write_text("keep")
    (app_home / "frontend-assets" / "obsolete.js").write_text("obsolete")
    state = {
        "version": 1,
        "current": current,
        "previous": previous,
        "retired": [retired],
    }
    (app_home / "frontend-state.json").write_text(json.dumps(state))
    with pytest.raises(release_module.FrontendReleaseError, match="symlink"):
        release_module.prune(app_home)
    assert (app_home / "frontend-assets" / "obsolete.js").exists()
    assert json.loads((app_home / "frontend-state.json").read_text())["retired"]
    old_web.unlink()
    old_web.mkdir()
    release_module.prune(app_home)
    assert json.loads((app_home / "frontend-state.json").read_text())["retired"] == []
