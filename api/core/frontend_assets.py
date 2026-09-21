"""Resolve server-rendered frontend assets from the packaged Vite manifest."""

import json
from pathlib import Path, PurePosixPath
from typing import Any


class FrontendAssets:
    """Resolve built asset URLs or explicit source URLs for Jinja templates."""

    REQUIRED_ENTRIES = (
        "normalize.css",
        "styles.css",
        "recipe-card.css",
        "js/common.js",
        "js/recipe.js",
    )
    _CSS_ENTRIES = {"normalize.css", "styles.css", "recipe-card.css"}
    _SCRIPT_ENTRIES = {"js/common.js", "js/recipe.js"}

    def __init__(self, mode: str, manifest_path: Path | None = None):
        if mode not in {"built", "development"}:
            raise ValueError(f"Unsupported frontend asset mode: {mode!r}")
        self.mode = mode
        self.manifest_path = (
            Path(manifest_path).resolve()
            if manifest_path is not None
            else Path(__file__).resolve().parents[1] / "frontend-manifest.json"
        )

    def validate(self) -> None:
        """Validate the packaged production manifest and required entry graph."""
        if self.mode == "development":
            return

        manifest = self._read_manifest()
        visited: set[str] = set()
        for entry in self.REQUIRED_ENTRIES:
            if entry not in manifest:
                raise ValueError(f"Missing required manifest entry: {entry}")
            self._validate_entry(manifest, entry, visited)
            file_name = manifest[entry]["file"]
            if entry in self._CSS_ENTRIES and not file_name.endswith(".css"):
                raise ValueError(f"Manifest entry {entry!r} must reference CSS")
            if entry in self._SCRIPT_ENTRIES and not file_name.endswith(".js"):
                raise ValueError(f"Manifest entry {entry!r} must reference JavaScript")
        for entry in manifest:
            self._validate_entry(manifest, entry, visited)

    def script(self, entry: str) -> str:
        """Return a root-absolute executable module URL for *entry*."""
        if self.mode == "development":
            return self._source_url(entry)

        manifest = self._read_manifest()
        self._validate_entry(manifest, entry, set())
        file_name = manifest[entry]["file"]
        if not file_name.endswith(".js"):
            raise ValueError(f"Manifest entry {entry!r} must reference JavaScript")
        return self._asset_url(file_name)

    def styles(self, entries: list[str]) -> list[str]:
        """Return deduplicated stylesheet URLs in dependency order."""
        if self.mode == "development":
            return [self._source_url(entry) for entry in entries]

        manifest = self._read_manifest()
        styles: list[str] = []
        seen_styles: set[str] = set()
        visited_entries: set[str] = set()
        for entry in entries:
            self._collect_styles(manifest, entry, visited_entries, seen_styles, styles)
        return styles

    def _read_manifest(self) -> dict[str, Any]:
        try:
            with self.manifest_path.open(encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
        except FileNotFoundError as error:
            raise ValueError(
                f"Frontend manifest is missing: {self.manifest_path}"
            ) from error
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Frontend manifest is invalid: {self.manifest_path}"
            ) from error

        if not isinstance(manifest, dict):
            raise ValueError(
                f"Frontend manifest must be an object: {self.manifest_path}"
            )
        return manifest

    def _validate_entry(
        self, manifest: dict[str, Any], entry: str, visited: set[str]
    ) -> None:
        if entry in visited:
            return
        record = manifest.get(entry)
        if not isinstance(record, dict):
            raise ValueError(f"Missing manifest entry: {entry}")
        visited.add(entry)

        file_name = record.get("file")
        self._asset_url(file_name, entry)
        for imported_entry in self._list_field(record, "imports", entry):
            self._validate_entry(manifest, imported_entry, visited)
        for css_file in self._list_field(record, "css", entry):
            self._asset_url(css_file, entry)
            if not css_file.endswith(".css"):
                raise ValueError(
                    f"Manifest entry {entry!r} references non-CSS stylesheet {css_file!r}"
                )

    def _collect_styles(
        self,
        manifest: dict[str, Any],
        entry: str,
        visited_entries: set[str],
        seen_styles: set[str],
        styles: list[str],
    ) -> None:
        if entry in visited_entries:
            return
        record = manifest.get(entry)
        if not isinstance(record, dict):
            raise ValueError(f"Missing manifest entry: {entry}")
        visited_entries.add(entry)

        file_name = record.get("file")
        file_url = self._asset_url(file_name, entry)
        for imported_entry in self._list_field(record, "imports", entry):
            self._collect_styles(
                manifest, imported_entry, visited_entries, seen_styles, styles
            )
        if file_name.endswith(".css"):
            self._append_style(file_url, seen_styles, styles)
        for css_file in self._list_field(record, "css", entry):
            css_url = self._asset_url(css_file, entry)
            if not css_file.endswith(".css"):
                raise ValueError(
                    f"Manifest entry {entry!r} references non-CSS stylesheet {css_file!r}"
                )
            self._append_style(css_url, seen_styles, styles)

    @staticmethod
    def _list_field(record: dict[str, Any], field: str, entry: str) -> list[str]:
        values = record.get(field, [])
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            raise ValueError(f"Manifest entry {entry!r} has invalid {field}")
        return values

    @staticmethod
    def _append_style(url: str, seen_styles: set[str], styles: list[str]) -> None:
        if url not in seen_styles:
            seen_styles.add(url)
            styles.append(url)

    @staticmethod
    def _asset_url(value: Any, entry: str = "manifest") -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"Manifest entry {entry!r} has an invalid asset path")
        if "\\" in value or "\x00" in value or "//" in value:
            raise ValueError(f"Manifest entry {entry!r} has an unsafe asset path")
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or len(path.parts) < 2
            or path.parts[0] != "assets"
            or any(part in {".", ".."} for part in path.parts)
        ):
            raise ValueError(f"Manifest entry {entry!r} has an unsafe asset path")
        return f"/{value}"

    @staticmethod
    def _source_url(entry: str) -> str:
        if not isinstance(entry, str) or not entry or entry.startswith("/"):
            raise ValueError(f"Invalid frontend source entry: {entry!r}")
        if "\\" in entry or "\x00" in entry or "//" in entry:
            raise ValueError(f"Invalid frontend source entry: {entry!r}")
        path = PurePosixPath(entry)
        if any(part in {".", ".."} for part in path.parts):
            raise ValueError(f"Invalid frontend source entry: {entry!r}")
        return f"/{entry}"
