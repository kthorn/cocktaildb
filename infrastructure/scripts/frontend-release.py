#!/usr/bin/env python3
"""Publish and retain the verified frontend generations.

The deployment shell owns ordering and the deployment lock.  This module owns
only JSON/path validation and filesystem publication so shell interpolation
cannot turn a release record into an arbitrary deletion.
"""

from __future__ import annotations

import json
import os
import posixpath
import shutil
import stat as stat_module
import sys
import tempfile
from pathlib import Path
from typing import Any

STATE_VERSION = 1
PENDING_VERSION = 2
ASSET_INVENTORY = "asset-inventory.json"
FRONTEND_INVENTORY = "frontend-assets.json"
PUBLIC_ASSET_MODE = 0o644
REQUIRED_MANIFEST_ENTRIES = {
    "normalize.css": "css",
    "styles.css": "css",
    "recipe-card.css": "css",
    "js/common.js": "js",
    "js/recipe.js": "js",
}


class FrontendReleaseError(RuntimeError):
    """A release failed a fail-closed validation or filesystem operation."""


def _error(message: str) -> FrontendReleaseError:
    return FrontendReleaseError(message)


def _lstat(path: Path, label: str):
    try:
        return path.lstat()
    except FileNotFoundError as exc:
        raise _error(f"{label} is missing: {path}") from exc


def _regular_file(path: Path, label: str) -> None:
    stat = _lstat(path, label)
    if stat_module.S_ISLNK(stat.st_mode):
        raise _error(f"{label} must not be a symlink: {path}")
    if not stat_module.S_ISREG(stat.st_mode):
        raise _error(f"{label} must be a regular file: {path}")


def _directory(path: Path, label: str, *, missing_ok: bool = False) -> None:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return
        raise _error(f"{label} is missing: {path}") from None
    if stat_module.S_ISLNK(stat.st_mode):
        raise _error(f"{label} must not be a symlink: {path}")
    if not stat_module.S_ISDIR(stat.st_mode):
        raise _error(f"{label} must be a directory: {path}")


def _ensure_directory(path: Path, label: str) -> None:
    if path.exists() or path.is_symlink():
        _directory(path, label)
        return
    path.mkdir(parents=True, exist_ok=True)
    _directory(path, label)


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise _error(f"{label} must be a non-empty string")
    if "\\" in value or value.startswith("/"):
        raise _error(f"{label} is not a safe relative path: {value}")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise _error(f"{label} is not a safe relative path: {value}")
    if posixpath.normpath(value) != value:
        raise _error(f"{label} is not normalized: {value}")
    return value


def _safe_asset_path(root: Path, relative: str, label: str) -> Path:
    relative = _safe_relative(relative, label)
    path = root.joinpath(*relative.split("/"))
    try:
        path.relative_to(root)
    except ValueError as exc:  # defensive even after lexical validation
        raise _error(f"{label} escapes its root: {relative}") from exc
    return path


def _assert_no_symlink_parents(path: Path, root: Path, label: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise _error(f"{label} escapes its root: {path}") from exc
    current = root
    for component in relative.parts[:-1]:
        current = current / component
        if current.is_symlink():
            raise _error(f"{label} contains a symlink parent: {current}")
        if current.exists() and not current.is_dir():
            raise _error(f"{label} parent is not a directory: {current}")


def _validate_tree(root: Path, label: str) -> None:
    _directory(root, label)
    for entry in root.iterdir():
        stat = entry.lstat()
        if stat_module.S_ISLNK(stat.st_mode):
            raise _error(f"{label} contains a symlink: {entry}")
        if stat_module.S_ISDIR(stat.st_mode):
            _validate_tree(entry, label)
        elif not stat_module.S_ISREG(stat.st_mode):
            raise _error(f"{label} contains non-regular data: {entry}")


def _enumerate_files(root: Path) -> list[str]:
    _directory(root, "asset directory")
    result: list[str] = []

    def visit(directory: Path, prefix: str) -> None:
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            _safe_relative(relative, "asset path")
            stat = entry.lstat()
            if stat_module.S_ISLNK(stat.st_mode):
                raise _error(f"symlinks are not allowed in assets: {relative}")
            if stat_module.S_ISDIR(stat.st_mode):
                visit(entry, relative)
            elif stat_module.S_ISREG(stat.st_mode):
                result.append(relative)
            else:
                raise _error(
                    f"asset entry is not a regular file or directory: {relative}"
                )

    visit(root, "")
    return result


def _read_json(path: Path, label: str) -> Any:
    _regular_file(path, label)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"{label} is not valid JSON: {path}: {exc}") from exc


def _read_inventory(path: Path, label: str = "asset inventory") -> list[str]:
    value = _read_json(path, label)
    if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
        raise _error(f"{label} version must be 1: {path}")
    files = value.get("files")
    if not isinstance(files, list):
        raise _error(f"{label} files must be an array: {path}")
    result = [
        _safe_relative(item, f"{label} files[{index}]")
        for index, item in enumerate(files)
    ]
    if len(set(result)) != len(result):
        raise _error(f"{label} contains duplicate files: {path}")
    if result != sorted(result):
        raise _error(f"{label} files must be sorted: {path}")
    if any(item == "config.js" or item.endswith("/config.js") for item in result):
        raise _error(f"runtime config must not be in {label}: {path}")
    return result


def _manifest_asset(value: Any, label: str) -> str:
    _safe_relative(value, label)
    if not value.startswith("assets/"):
        raise _error(f"{label} must be beneath assets/: {value}")
    relative = value[len("assets/") :]
    if not relative:
        raise _error(f"{label} cannot refer to the assets directory")
    return _safe_relative(relative, label)


def _validate_manifest(value: Any, inventory: set[str], label: str) -> None:
    if not isinstance(value, dict) or isinstance(value, list):
        raise _error(f"{label} must be an object")
    for entry_name, expected_type in REQUIRED_MANIFEST_ENTRIES.items():
        if entry_name not in value:
            raise _error(f"{label} is missing required manifest entry: {entry_name}")
        entry = value[entry_name]
        if not isinstance(entry, dict) or isinstance(entry, list):
            raise _error(f"{label} entry is invalid: {entry_name}")
        file_name = entry.get("file")
        if not isinstance(file_name, str) or not file_name:
            raise _error(
                f"{label} required file must be a non-empty string: {entry_name}"
            )
        relative = _manifest_asset(file_name, f"{label} {entry_name}.file")
        if relative not in inventory:
            raise _error(
                f"{label} {entry_name}.file is absent from asset inventory: {file_name}"
            )
        if expected_type == "css" and not file_name.endswith(".css"):
            raise _error(f"{label} required entry must reference CSS: {entry_name}")
        if expected_type == "js" and not file_name.endswith(".js"):
            raise _error(
                f"{label} required entry must reference JavaScript: {entry_name}"
            )
    for entry_name, entry in value.items():
        if not isinstance(entry, dict) or isinstance(entry, list):
            raise _error(f"{label} entry is invalid: {entry_name}")
        if "file" not in entry:
            raise _error(f"{label} file must be a non-empty string: {entry_name}")
        for field in ("file", "css", "assets"):
            if field not in entry:
                continue
            references = entry[field] if field != "file" else [entry[field]]
            if field != "file" and not isinstance(references, list):
                raise _error(f"{label} {entry_name}.{field} must be an array")
            for index, reference in enumerate(references):
                reference_label = f"{label} {entry_name}.{field}"
                if field != "file":
                    reference_label += f"[{index}]"
                relative = _manifest_asset(reference, reference_label)
                if relative not in inventory:
                    raise _error(
                        f"{reference_label} is absent from asset inventory: {reference}"
                    )
                if field == "css" and not reference.endswith(".css"):
                    raise _error(
                        f"{label} {entry_name}.css must reference CSS: {reference}"
                    )
        for field in ("imports", "dynamicImports"):
            if field not in entry:
                continue
            references = entry[field]
            if not isinstance(references, list):
                raise _error(f"{label} {entry_name}.{field} must be an array")
            for index, reference in enumerate(references):
                if not isinstance(reference, str) or reference not in value:
                    raise _error(
                        f"{label} {entry_name}.{field}[{index}] references missing entry: {reference}"
                    )


def _inventory_paths(release: Path, *, require_assets: bool) -> tuple[list[str], Path]:
    source = release / ASSET_INVENTORY
    retained = release / FRONTEND_INVENTORY
    source_exists = source.exists() or source.is_symlink()
    retained_exists = retained.exists() or retained.is_symlink()
    if not source_exists and not retained_exists:
        raise _error(f"asset inventory is missing from release: {release}")
    source_files = _read_inventory(source) if source_exists else None
    retained_files = _read_inventory(retained) if retained_exists else None
    if (
        source_files is not None
        and retained_files is not None
        and source_files != retained_files
    ):
        raise _error(f"release inventories disagree: {release}")
    files = source_files if source_files is not None else retained_files
    assert files is not None
    assets = release / "web" / "assets"
    if require_assets:
        actual = _enumerate_files(assets)
        if actual != files:
            raise _error(
                f"asset inventory does not match regular files under web/assets: {release}"
            )
    return files, retained


def _public_asset_file(path: Path, label: str) -> None:
    _regular_file(path, label)
    mode = stat_module.S_IMODE(path.stat().st_mode)
    if mode != PUBLIC_ASSET_MODE:
        raise _error(f"{label} must be publicly readable with mode 0644: {path}")


def _validate_prepared_assets(
    release: Path, app_home: Path, files: list[str], retained: Path
) -> None:
    web_assets = release / "web" / "assets"
    if web_assets.exists() or web_assets.is_symlink():
        raise _error(f"prepared release must not contain web/assets: {release}")
    _regular_file(retained, "prepared frontend inventory")
    asset_root = app_home / "frontend-assets"
    _directory(asset_root, "shared frontend asset directory")
    for relative in files:
        shared = _safe_asset_path(asset_root, relative, "prepared asset path")
        _assert_no_symlink_parents(shared, asset_root, "prepared asset")
        _public_asset_file(shared, "prepared shared asset")


def validate_release(
    release: Path,
    *,
    require_assets: bool | None = True,
    app_home: Path | None = None,
) -> list[str]:
    release = Path(release)
    app_home = Path(app_home or os.environ.get("APP_HOME") or release.parent.parent)
    _directory(release, "release")
    web = release / "web"
    _validate_tree(web, "release web directory")
    _regular_file(web / "js" / "config.js", "generated frontend config")
    web_assets = web / "assets"
    if require_assets is None:
        require_assets = web_assets.exists() or web_assets.is_symlink()
    files, retained = _inventory_paths(release, require_assets=require_assets)
    manifest = _read_json(release / "manifest.json", "Vite manifest")
    _validate_manifest(manifest, set(files), "Vite manifest")
    if not require_assets:
        _validate_prepared_assets(release, app_home, files, retained)
    return files


def _same_bytes(left: Path, right: Path) -> bool:
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        with left.open("rb") as left_file, right.open("rb") as right_file:
            while True:
                left_chunk = left_file.read(1024 * 1024)
                right_chunk = right_file.read(1024 * 1024)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    except OSError:
        return False


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: Any) -> None:
    _ensure_directory(path.parent, "JSON destination directory")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _atomic_copy(source: Path, destination: Path) -> bool:
    if destination.exists() or destination.is_symlink():
        _regular_file(destination, "existing shared asset")
        if not _same_bytes(source, destination):
            raise _error(f"immutable asset has different bytes: {destination}")
        os.chmod(destination, PUBLIC_ASSET_MODE)
        _fsync_directory(destination.parent)
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_parents(destination, destination.parent, "shared asset")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, PUBLIC_ASSET_MODE)
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
        if destination.exists() or destination.is_symlink():
            _regular_file(destination, "existing shared asset")
            if not _same_bytes(source, destination):
                raise _error(f"immutable asset has different bytes: {destination}")
            os.chmod(destination, PUBLIC_ASSET_MODE)
            _fsync_directory(destination.parent)
            temporary.unlink()
            return False
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
        return True
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def publish_assets(release: Path, app_home: Path) -> list[str]:
    release = Path(release)
    app_home = Path(app_home)
    source_root = release / "web" / "assets"
    if not (source_root.exists() or source_root.is_symlink()):
        return validate_release(release, require_assets=False, app_home=app_home)

    files = validate_release(release, require_assets=True, app_home=app_home)
    destination_root = app_home / "frontend-assets"
    _ensure_directory(destination_root, "shared frontend asset directory")

    sources: list[tuple[str, Path, Path]] = []
    for relative in files:
        source = _safe_asset_path(source_root, relative, "asset inventory path")
        destination = _safe_asset_path(
            destination_root, relative, "asset inventory path"
        )
        _regular_file(source, "staged frontend asset")
        _assert_no_symlink_parents(destination, destination_root, "shared asset")
        if destination.exists() or destination.is_symlink():
            _regular_file(destination, "existing shared asset")
            if not _same_bytes(source, destination):
                raise _error(f"immutable asset has different bytes: {destination}")
        sources.append((relative, source, destination))

    for _, source, destination in sources:
        _atomic_copy(source, destination)

    for relative in files:
        _public_asset_file(
            _safe_asset_path(destination_root, relative, "published asset path"),
            "published shared asset",
        )
    inventory = {"version": STATE_VERSION, "files": files}
    retained = release / FRONTEND_INVENTORY
    if retained.exists() or retained.is_symlink():
        existing = _read_inventory(retained, "release frontend inventory")
        if existing != files:
            raise _error(f"release frontend inventory disagrees: {retained}")
    else:
        _atomic_json(retained, inventory)
    shutil.rmtree(source_root)
    _fsync_directory(source_root.parent)
    return files


def prune_assets(asset_root: Path, keep: set[str]) -> None:
    asset_root = Path(asset_root)
    _directory(asset_root, "shared frontend asset directory")
    safe_keep = {_safe_relative(item, "retained asset") for item in keep}
    actual = _enumerate_files(asset_root)
    for relative in actual:
        if relative not in safe_keep:
            _safe_asset_path(asset_root, relative, "asset deletion path").unlink()
    directories = sorted(
        (
            path
            for path in asset_root.rglob("*")
            if path.is_dir() and not path.is_symlink()
        ),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        if not any(directory.iterdir()):
            directory.rmdir()
    _fsync_directory(asset_root)


def _relative_to_app(path: Path, app_home: Path) -> str:
    try:
        relative = path.absolute().relative_to(app_home.absolute())
    except ValueError as exc:
        raise _error(f"managed path is outside APP_HOME: {path}") from exc
    return _safe_relative(relative.as_posix(), "managed state path")


def _state_path(app_home: Path) -> Path:
    return Path(app_home) / "frontend-state.json"


def _pending_path(app_home: Path) -> Path:
    return Path(app_home) / "frontend-pending.json"


def _record(release: Path, app_home: Path, api_image: str) -> dict[str, Any]:
    if not isinstance(api_image, str) or not api_image:
        raise _error("API image identity must be non-empty")
    _assert_no_symlink_parents(release / "web", app_home, "release candidate web")
    record = {
        "id": release.name,
        "web": _relative_to_app(release / "web", app_home),
        "inventory": _relative_to_app(release / FRONTEND_INVENTORY, app_home),
        "image": api_image,
        "legacy": False,
    }
    return _validate_record_shape(record, "release candidate")


def _validate_record_shape(record: Any, label: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise _error(f"{label} must be an object")
    identifier = record.get("id")
    if (
        not isinstance(identifier, str)
        or not identifier
        or identifier in {".", ".."}
        or "/" in identifier
        or "\\" in identifier
    ):
        raise _error(f"{label}.id is invalid")
    web = _safe_relative(record.get("web"), f"{label}.web")
    legacy = record.get("legacy")
    if not isinstance(legacy, bool):
        raise _error(f"{label}.legacy must be boolean")
    inventory = record.get("inventory")
    if legacy:
        if (
            identifier != "legacy"
            or inventory is not None
            or record.get("image") is not None
        ):
            raise _error(f"{label} is not a valid legacy frontend record")
        web_parts = web.split("/")
        if (
            len(web_parts) != 2
            or web_parts[0] != "releases"
            or not web_parts[1].startswith("previous-web-")
            or web_parts[1] == "previous-web-"
        ):
            raise _error(f"{label}.web is not the preserved legacy frontend path")
    else:
        expected_web = f"releases/{identifier}/web"
        expected_inventory = f"releases/{identifier}/{FRONTEND_INVENTORY}"
        if web != expected_web:
            raise _error(f"{label}.web is not the owned release web path: {web}")
        if inventory is None:
            raise _error(f"{label}.inventory is required for hashed releases")
        inventory = _safe_relative(inventory, f"{label}.inventory")
        if inventory != expected_inventory:
            raise _error(
                f"{label}.inventory is not the matching release metadata path: {inventory}"
            )
    image = record.get("image")
    if not legacy and (not isinstance(image, str) or not image):
        raise _error(f"{label}.image is invalid")
    return {
        "id": identifier,
        "web": web,
        "inventory": inventory,
        "image": image,
        "legacy": legacy,
    }


def _load_state(app_home: Path) -> dict[str, Any] | None:
    path = _state_path(app_home)
    if not path.exists() and not path.is_symlink():
        return None
    value = _read_json(path, "frontend state")
    if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
        raise _error(f"frontend state version must be 1: {path}")
    if "current" not in value or "retired" not in value:
        raise _error(f"frontend state is missing required fields: {path}")
    current = _validate_record_shape(value["current"], "frontend state current")
    if current["legacy"]:
        raise _error("frontend state current cannot be a legacy record")
    previous_value = value.get("previous")
    previous = (
        None
        if previous_value is None
        else _validate_record_shape(previous_value, "frontend state previous")
    )
    retired_value = value["retired"]
    if not isinstance(retired_value, list):
        raise _error(f"frontend state retired must be an array: {path}")
    retired = [
        _validate_record_shape(record, f"frontend state retired[{index}]")
        for index, record in enumerate(retired_value)
    ]
    state = {
        "version": STATE_VERSION,
        "current": current,
        "previous": previous,
        "retired": retired,
    }
    _validate_state_record_disjointness(state)
    return state


def _immutable_image_id(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) <= len("sha256:")
        or any(character.isspace() for character in value)
    ):
        raise _error(f"{label} must be an immutable image ID")
    return value


def _capture_prior_frontend(
    app_home: Path, state: dict[str, Any] | None
) -> dict[str, Any]:
    served = _served_path_from_environment(app_home)
    if state is not None:
        current = state["current"]
        expected = (app_home / current["web"]).resolve()
        if not served.is_symlink():
            raise _error(f"served frontend is not the committed symlink: {served}")
        actual = (served.parent / os.readlink(served)).resolve()
        if actual != expected:
            raise _error(
                f"served frontend does not match committed current: {actual} != {expected}"
            )
        return {"kind": "hashed-release", "record": current}

    try:
        stat = served.lstat()
    except FileNotFoundError as exc:
        raise _error(f"first-rollout legacy frontend is missing: {served}") from exc
    if stat_module.S_ISLNK(stat.st_mode):
        raise _error("first-rollout legacy frontend must be a real directory")
    if not stat_module.S_ISDIR(stat.st_mode):
        raise _error("first-rollout legacy frontend must be a directory")
    return {
        "kind": "legacy-directory",
        "path": _relative_to_app(served, app_home),
        "st_dev": stat.st_dev,
        "st_ino": stat.st_ino,
    }


def _validate_prior_frontend(
    app_home: Path, pending: dict[str, Any], state: dict[str, Any] | None
) -> None:
    prior = pending["prior_frontend"]
    if prior["kind"] == "hashed-release":
        expected_record = pending["previous"]
        if expected_record is None or state is None:
            raise _error("pending prior frontend requires a committed current release")
        if not _same_record(state["current"], expected_record):
            raise _error(
                "committed frontend state no longer matches pending prior frontend"
            )
        _served_matches(app_home, expected_record)
        return
    if prior["kind"] == "legacy-directory":
        if state is not None:
            raise _error("first-rollout prior frontend now has committed state")
        served = _served_path_from_environment(app_home)
        try:
            stat = served.lstat()
        except FileNotFoundError as exc:
            raise _error("first-rollout legacy frontend is missing") from exc
        if stat_module.S_ISLNK(stat.st_mode) or not stat_module.S_ISDIR(stat.st_mode):
            raise _error("first-rollout legacy frontend identity changed")
        observed_path = _relative_to_app(served, app_home)
        if (
            observed_path != prior["path"]
            or stat.st_dev != prior["st_dev"]
            or stat.st_ino != prior["st_ino"]
        ):
            raise _error(
                "first-rollout legacy frontend identity changed: "
                f"path={observed_path} st_dev={stat.st_dev} st_ino={stat.st_ino}"
            )
        return
    raise _error(f"unsupported pending prior frontend kind: {prior.get('kind')}")


def _load_pending(app_home: Path) -> dict[str, Any]:
    path = _pending_path(app_home)
    if not path.exists() and not path.is_symlink():
        raise _error(f"frontend pending marker is missing: {path}")
    value = _read_json(path, "frontend pending marker")
    if not isinstance(value, dict):
        raise _error(f"frontend pending marker must be an object: {path}")
    version = value.get("version")
    if version == STATE_VERSION:
        raise _error(
            f"frontend pending marker version 1 is unsupported; manual identity and database reconciliation is required: {path}"
        )
    if version != PENDING_VERSION:
        raise _error(f"frontend pending marker version must be 2: {path}")
    phase = value.get("phase")
    if phase not in {"prepublication", "cutover"}:
        raise _error(f"frontend pending marker phase is invalid: {path}")
    candidate = _validate_record_shape(value.get("candidate"), "pending candidate")
    if candidate["legacy"]:
        raise _error("pending candidate cannot be a legacy record")
    previous = value.get("previous")
    if previous is not None:
        previous = _validate_record_shape(previous, "pending previous")
        if previous["legacy"]:
            raise _error("pending previous cannot be a legacy record")
    candidate_image_id = _immutable_image_id(
        value.get("candidate_image_id"), "pending candidate image ID"
    )
    prior_api_image_id = _immutable_image_id(
        value.get("prior_api_image_id"), "pending prior API image ID"
    )
    prior_frontend = value.get("prior_frontend")
    if not isinstance(prior_frontend, dict):
        raise _error("pending prior frontend must be an object")
    if prior_frontend.get("kind") == "hashed-release":
        record = _validate_record_shape(
            prior_frontend.get("record"), "pending prior frontend record"
        )
        if record["legacy"]:
            raise _error("pending prior frontend record cannot be legacy")
        if previous is None or not _same_record(record, previous):
            raise _error("pending prior frontend record disagrees with previous")
        prior_frontend = {"kind": "hashed-release", "record": record}
    elif prior_frontend.get("kind") == "legacy-directory":
        if previous is not None:
            raise _error("legacy prior frontend cannot have previous state")
        path_value = _safe_relative(
            prior_frontend.get("path"), "pending prior frontend path"
        )
        st_dev = prior_frontend.get("st_dev")
        st_ino = prior_frontend.get("st_ino")
        if (
            not isinstance(st_dev, int)
            or st_dev < 0
            or not isinstance(st_ino, int)
            or st_ino < 0
        ):
            raise _error("pending legacy frontend identity is invalid")
        prior_frontend = {
            "kind": "legacy-directory",
            "path": path_value,
            "st_dev": st_dev,
            "st_ino": st_ino,
        }
    else:
        raise _error("pending prior frontend kind is invalid")
    legacy = value.get("legacy_previous_web")
    if legacy is not None:
        legacy = _safe_relative(legacy, "pending legacy_previous_web")
    return {
        "version": PENDING_VERSION,
        "phase": phase,
        "candidate": candidate,
        "candidate_image_id": candidate_image_id,
        "prior_api_image_id": prior_api_image_id,
        "previous": previous,
        "prior_frontend": prior_frontend,
        "legacy_previous_web": legacy,
    }


def _validate_owned_path(
    path: Path,
    label: str,
    *,
    kind: str,
    allow_missing: bool = False,
) -> None:
    if not (path.exists() or path.is_symlink()):
        if allow_missing:
            return
        raise _error(f"{label} is missing: {path}")
    if kind == "directory":
        _validate_tree(path, label)
    elif kind == "file":
        _regular_file(path, label)
    else:  # pragma: no cover - only callers in this module provide fixed kinds
        raise ValueError(f"unknown owned path kind: {kind}")


def _validate_record_paths(
    app_home: Path,
    record: dict[str, Any],
    label: str,
    *,
    allow_missing: bool,
) -> None:
    _directory(app_home, "APP_HOME")
    web = app_home / record["web"]
    _assert_no_symlink_parents(web, app_home, f"{label}.web")
    _validate_owned_path(
        web,
        f"{label} web",
        kind="directory",
        allow_missing=allow_missing,
    )
    inventory = record["inventory"]
    if inventory is not None:
        inventory_path = app_home / inventory
        _assert_no_symlink_parents(inventory_path, app_home, f"{label}.inventory")
        _validate_owned_path(
            inventory_path,
            f"{label} inventory",
            kind="file",
            allow_missing=allow_missing,
        )


def _paths_overlap(left: str, right: str) -> bool:
    left_path = Path(left)
    right_path = Path(right)
    return (
        left_path == right_path
        or left_path in right_path.parents
        or right_path in left_path.parents
    )


def _validate_state_record_disjointness(state: dict[str, Any]) -> None:
    paths: list[tuple[str, str]] = []
    for label in ("current", "previous"):
        record = state.get(label)
        if record is not None:
            entries = [(f"{label}.web", record["web"])]
            if record["inventory"] is not None:
                entries.append((f"{label}.inventory", record["inventory"]))
            paths.extend(entries)
    for index, record in enumerate(state["retired"]):
        entries = [(f"retired[{index}].web", record["web"])]
        if record["inventory"] is not None:
            entries.append((f"retired[{index}].inventory", record["inventory"]))
        paths.extend(entries)
    for index, (label, path) in enumerate(paths):
        for other_label, other_path in paths[:index]:
            if _paths_overlap(path, other_path):
                raise _error(
                    f"frontend state paths overlap: {label}={path} and "
                    f"{other_label}={other_path}"
                )


def _validate_state_files(app_home: Path, state: dict[str, Any]) -> set[str]:
    keep: set[str] = set()
    asset_root = app_home / "frontend-assets"
    for label in ("current", "previous"):
        record = state.get(label)
        if record is None:
            continue
        _validate_record_paths(
            app_home, record, f"retained {label}", allow_missing=False
        )
        inventory = record["inventory"]
        if inventory is None:
            if not record["legacy"]:
                raise _error(f"retained {label} has no inventory")
            continue
        files = _read_inventory(app_home / inventory, f"retained {label} inventory")
        keep.update(files)
        _directory(asset_root, "shared frontend asset directory")
        for relative in files:
            _public_asset_file(
                _safe_asset_path(asset_root, relative, "retained asset path"),
                f"retained {label} asset",
            )
    return keep


def _preflight_prune(app_home: Path, state: dict[str, Any]) -> set[str]:
    _validate_state_record_disjointness(state)
    keep = _validate_state_files(app_home, state)
    for index, record in enumerate(state["retired"]):
        label = f"retired frontend {index}"
        _validate_record_paths(app_home, record, label, allow_missing=True)
        inventory = record["inventory"]
        if inventory is not None:
            inventory_path = app_home / inventory
            if inventory_path.exists() or inventory_path.is_symlink():
                _read_inventory(inventory_path, f"{label} inventory")
    asset_root = app_home / "frontend-assets"
    _directory(asset_root, "shared frontend asset directory")
    _enumerate_files(asset_root)
    return keep


def begin(
    release: Path,
    api_image: str,
    candidate_image_id: str,
    prior_api_image_id: str,
    app_home: Path | None = None,
) -> dict[str, Any]:
    release = Path(release)
    app_home = Path(app_home or os.environ.get("APP_HOME", "/opt/cocktaildb"))
    if _pending_path(app_home).exists() or _pending_path(app_home).is_symlink():
        raise _error(
            f"unresolved frontend pending marker blocks deployment: {_pending_path(app_home)}"
        )
    candidate_image_id = _immutable_image_id(candidate_image_id, "candidate image ID")
    prior_api_image_id = _immutable_image_id(prior_api_image_id, "prior API image ID")
    validate_release(release, require_assets=True, app_home=app_home)
    state = _load_state(app_home)
    if state is not None:
        _validate_state_files(app_home, state)
    prior_frontend = _capture_prior_frontend(app_home, state)
    candidate = _record(release, app_home, api_image)
    pending = {
        "version": PENDING_VERSION,
        "phase": "prepublication",
        "candidate": candidate,
        "candidate_image_id": candidate_image_id,
        "prior_api_image_id": prior_api_image_id,
        "previous": state["current"] if state else None,
        "prior_frontend": prior_frontend,
        "legacy_previous_web": None,
    }
    _atomic_json(_pending_path(app_home), pending)
    return pending


def _served_path_from_environment(app_home: Path | None = None) -> Path:
    app_home = Path(app_home or os.environ.get("APP_HOME", "/opt/cocktaildb"))
    return Path(os.environ.get("SERVED_WEB", str(app_home / "web")))


def publish_web(
    release: Path, served: Path, app_home: Path | None = None
) -> Path | None:
    release = Path(release)
    served = Path(served)
    app_home = Path(app_home or release.parent.parent)
    release_web = release / "web"
    _validate_tree(release_web, "release web directory")
    if (release_web / "assets").exists() or (release_web / "assets").is_symlink():
        raise _error(f"release web directory still contains assets: {release_web}")
    _ensure_directory(served.parent, "served web parent")

    existing = served.exists() or served.is_symlink()
    backup: Path | None = None
    moved = False
    if existing:
        stat = served.lstat()
        if stat_module.S_ISLNK(stat.st_mode):
            pass
        elif stat_module.S_ISDIR(stat.st_mode):
            backup = release.parent / f"previous-web-{release.name}"
            if backup.exists() or backup.is_symlink():
                raise _error(f"refusing to overwrite preserved frontend: {backup}")
        else:
            raise _error(f"served web path is not a directory or symlink: {served}")

    temporary = (
        served.parent
        / f".{served.name}.frontend-{os.getpid()}-{next(tempfile._get_candidate_names())}"
    )
    target = os.path.relpath(release_web, served.parent)
    try:
        if backup is not None:
            os.replace(served, backup)
            moved = True
        os.symlink(target, temporary)
        os.replace(temporary, served)
        if backup is not None:
            _fsync_directory(backup.parent)
        _fsync_directory(served.parent)
        return backup
    except BaseException:
        try:
            if temporary.is_symlink() or temporary.exists():
                temporary.unlink()
        except FileNotFoundError:
            pass
        if moved:
            try:
                if not (served.exists() or served.is_symlink()):
                    os.replace(backup, served)
            except OSError as restore_error:
                raise _error(
                    f"frontend publication failed and restoration failed: {restore_error}"
                ) from restore_error
        raise


def _validate_pending_candidate(
    pending: dict[str, Any],
    release: Path,
    api_image: str,
    app_home: Path,
    candidate_image_id: str | None = None,
) -> None:
    candidate = pending["candidate"]
    expected = _record(release, app_home, api_image)
    if not _same_record(candidate, expected):
        raise _error("pending candidate identity does not match release or API image")
    if candidate_image_id is not None:
        candidate_image_id = _immutable_image_id(
            candidate_image_id, "candidate image ID"
        )
        if pending["candidate_image_id"] != candidate_image_id:
            raise _error(
                "candidate immutable image ID does not match pending marker: "
                f"observed={candidate_image_id} expected={pending['candidate_image_id']}"
            )


def _clear_pending(app_home: Path) -> None:
    _pending_path(app_home).unlink()
    _fsync_directory(app_home)


def abort_prepublication(
    release: Path,
    api_image: str,
    candidate_image_id: str,
    active_api_image_id: str,
    app_home: Path | None = None,
) -> None:
    release = Path(release)
    app_home = Path(app_home or os.environ.get("APP_HOME", "/opt/cocktaildb"))
    pending = _load_pending(app_home)
    if pending["phase"] != "prepublication":
        raise _error("prepublication abort is forbidden after cutover phase")
    _validate_pending_candidate(
        pending, release, api_image, app_home, candidate_image_id
    )
    active_api_image_id = _immutable_image_id(
        active_api_image_id, "active API image ID"
    )
    if active_api_image_id != pending["prior_api_image_id"]:
        raise _error(
            "active API image ID does not match pending prior API: "
            f"observed={active_api_image_id} expected={pending['prior_api_image_id']}"
        )
    state = _load_state(app_home)
    _validate_prior_frontend(app_home, pending, state)
    _clear_pending(app_home)


def mark_cutover(
    release: Path,
    api_image: str,
    candidate_image_id: str,
    app_home: Path | None = None,
) -> dict[str, Any]:
    release = Path(release)
    app_home = Path(app_home or os.environ.get("APP_HOME", "/opt/cocktaildb"))
    pending = _load_pending(app_home)
    if pending["phase"] != "prepublication":
        raise _error("pending marker is not in prepublication phase")
    _validate_pending_candidate(
        pending, release, api_image, app_home, candidate_image_id
    )
    validate_release(release, require_assets=False, app_home=app_home)
    state = _load_state(app_home)
    _validate_prior_frontend(app_home, pending, state)
    pending["phase"] = "cutover"
    _atomic_json(_pending_path(app_home), pending)
    return pending


def publish(
    release: Path, served: Path | None = None, app_home: Path | None = None
) -> dict[str, Any]:
    release = Path(release)
    app_home = Path(app_home or os.environ.get("APP_HOME", "/opt/cocktaildb"))
    served = Path(served or _served_path_from_environment())
    pending = _load_pending(app_home)
    if pending["phase"] != "cutover":
        raise _error("frontend publication requires durable cutover phase")
    candidate = pending["candidate"]
    if candidate["id"] != release.name or candidate["web"] != _relative_to_app(
        release / "web", app_home
    ):
        raise _error("release identity does not match the pending candidate")
    validate_release(release, require_assets=False, app_home=app_home)
    state = _load_state(app_home)
    legacy_backup = None
    if served.exists() and not served.is_symlink():
        if state is not None and state.get("current") is not None:
            raise _error("committed frontend state requires a served symlink")
        legacy_backup = release.parent / f"previous-web-{release.name}"
        pending["legacy_previous_web"] = _relative_to_app(legacy_backup, app_home)
        _atomic_json(_pending_path(app_home), pending)
    backup = publish_web(release, served, app_home)
    if backup is not None:
        if legacy_backup is not None and backup != legacy_backup:
            raise _error("preserved legacy frontend path changed during publication")
        pending["legacy_previous_web"] = _relative_to_app(backup, app_home)
        _atomic_json(_pending_path(app_home), pending)
    return pending


def _same_record(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        left.get(key) == right.get(key)
        for key in ("id", "web", "inventory", "image", "legacy")
    )


def _served_matches(app_home: Path, candidate: dict[str, Any]) -> None:
    served = _served_path_from_environment(app_home)
    expected = (app_home / candidate["web"]).absolute()
    if not served.is_symlink():
        raise _error(f"served web is not the pending release symlink: {served}")
    try:
        actual = (served.parent / os.readlink(served)).resolve()
    except OSError as exc:
        raise _error(f"cannot inspect served web symlink: {served}") from exc
    if actual != expected.resolve():
        raise _error(
            f"served web identity does not match pending candidate: {actual} != {expected}"
        )


def commit(
    release: Path, api_image: str, app_home: Path | None = None
) -> dict[str, Any]:
    release = Path(release)
    app_home = Path(app_home or os.environ.get("APP_HOME", "/opt/cocktaildb"))
    pending = _load_pending(app_home)
    if pending["phase"] != "cutover":
        raise _error("frontend commit requires durable cutover phase")
    candidate = pending["candidate"]
    if candidate["id"] != release.name or candidate["image"] != api_image:
        raise _error("commit identity does not match pending candidate")
    expected = _record(release, app_home, api_image)
    if not _same_record(candidate, expected):
        raise _error("commit release identity is inconsistent with pending marker")
    state = _load_state(app_home)
    if state is not None and _same_record(state["current"], candidate):
        _validate_state_files(app_home, state)
        _served_matches(app_home, candidate)
        _pending_path(app_home).unlink()
        _fsync_directory(app_home)
        return state

    validate_release(release, require_assets=False, app_home=app_home)
    _served_matches(app_home, candidate)
    if state is not None:
        _validate_state_files(app_home, state)

    old_current = state["current"] if state else None
    if old_current is not None:
        previous = old_current
        retired = list(state["retired"])
        if state.get("previous") is not None:
            retired.append(state["previous"])
    else:
        retired = []
        legacy_path = pending.get("legacy_previous_web")
        if legacy_path is not None:
            if not (app_home / legacy_path).exists():
                raise _error(
                    f"preserved legacy frontend is missing: {app_home / legacy_path}"
                )
            previous = _validate_record_shape(
                {
                    "id": "legacy",
                    "web": legacy_path,
                    "inventory": None,
                    "image": None,
                    "legacy": True,
                },
                "preserved legacy frontend",
            )
            _validate_record_paths(
                app_home, previous, "preserved legacy frontend", allow_missing=False
            )
        else:
            previous = None
    next_state = {
        "version": STATE_VERSION,
        "current": candidate,
        "previous": previous,
        "retired": retired,
    }
    _atomic_json(_state_path(app_home), next_state)
    _pending_path(app_home).unlink()
    _fsync_directory(app_home)
    return next_state


def _remove_owned_path(path: Path, label: str, root: Path | None = None) -> None:
    if root is not None:
        _assert_no_symlink_parents(path, root, label)
    if not (path.exists() or path.is_symlink()):
        return
    stat = path.lstat()
    if stat_module.S_ISLNK(stat.st_mode):
        raise _error(f"{label} must not be a symlink: {path}")
    if stat_module.S_ISDIR(stat.st_mode):
        for child in path.rglob("*"):
            if child.is_symlink():
                raise _error(f"{label} contains a symlink: {child}")
        shutil.rmtree(path)
    elif stat_module.S_ISREG(stat.st_mode):
        path.unlink()
    else:
        raise _error(f"{label} is not removable regular data: {path}")


def prune(app_home: Path | None = None) -> dict[str, Any] | None:
    app_home = Path(app_home or os.environ.get("APP_HOME", "/opt/cocktaildb"))
    if _pending_path(app_home).exists() or _pending_path(app_home).is_symlink():
        _load_pending(app_home)
        raise _error(
            f"unresolved frontend pending marker blocks pruning: {_pending_path(app_home)}"
        )
    state = _load_state(app_home)
    if state is None:
        return None
    keep = _preflight_prune(app_home, state)
    prune_assets(app_home / "frontend-assets", keep)

    remaining = list(state["retired"])
    for record in list(remaining):
        _remove_owned_path(app_home / record["web"], "retired frontend web", app_home)
        if record["inventory"] is not None:
            _remove_owned_path(
                app_home / record["inventory"],
                "retired frontend inventory",
                app_home,
            )
        remaining.remove(record)
        state["retired"] = remaining
        _atomic_json(_state_path(app_home), state)
    return state


def recover(
    release: Path, api_image: str, app_home: Path | None = None
) -> dict[str, Any]:
    release = Path(release)
    app_home = Path(app_home or os.environ.get("APP_HOME", "/opt/cocktaildb"))
    pending = _load_pending(app_home)
    if pending["phase"] != "cutover":
        raise _error(
            "candidate recovery requires cutover phase; use abort-prepublication "
            "or resume-stopped for a prepublication marker"
        )
    _validate_pending_candidate(pending, release, api_image, app_home)
    candidate = pending["candidate"]
    state = _load_state(app_home)
    if state is not None and _same_record(state["current"], candidate):
        _validate_state_files(app_home, state)
        _served_matches(app_home, candidate)
        _clear_pending(app_home)
        return state
    return commit(release, api_image, app_home)


def _usage() -> str:
    return (
        "usage: frontend-release.py <validate|assets|begin|abort-prepublication|"
        "mark-cutover|publish|commit|prune|recover> ..."
    )


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(_usage(), file=sys.stderr)
        return 2
    command = arguments.pop(0)
    app_home = Path(os.environ.get("APP_HOME", "/opt/cocktaildb"))
    served = Path(os.environ.get("SERVED_WEB", str(app_home / "web")))
    try:
        if command == "validate" and len(arguments) == 1:
            validate_release(Path(arguments[0]), require_assets=None, app_home=app_home)
        elif command == "assets" and len(arguments) == 1:
            publish_assets(Path(arguments[0]), app_home)
        elif command == "begin" and len(arguments) == 4:
            begin(
                Path(arguments[0]),
                arguments[1],
                arguments[2],
                arguments[3],
                app_home,
            )
        elif command == "abort-prepublication" and len(arguments) == 4:
            abort_prepublication(
                Path(arguments[0]),
                arguments[1],
                arguments[2],
                arguments[3],
                app_home,
            )
        elif command == "mark-cutover" and len(arguments) == 3:
            mark_cutover(Path(arguments[0]), arguments[1], arguments[2], app_home)
        elif command == "publish" and len(arguments) == 1:
            publish(Path(arguments[0]), served, app_home)
        elif command == "commit" and len(arguments) == 2:
            commit(Path(arguments[0]), arguments[1], app_home)
        elif command == "prune" and not arguments:
            prune(app_home)
        elif command == "recover" and len(arguments) == 2:
            recover(Path(arguments[0]), arguments[1], app_home)
        else:
            print(_usage(), file=sys.stderr)
            return 2
    except (FrontendReleaseError, OSError, ValueError) as exc:
        print(f"frontend release error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
