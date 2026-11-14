"""Identify the deployed release from the file the deploy stages beside the API."""

import json
from pathlib import Path

RELEASE_INFO_PATH = Path(__file__).resolve().parents[1] / "release.json"


def read_release_info(path: Path = RELEASE_INFO_PATH) -> dict | None:
    """Return the staged release identity, or None outside a deployed build.

    A present but malformed file raises, so a broken deploy fails at startup
    instead of reporting a wrong identity.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    info = json.loads(text)
    return {
        "release_id": info["release_id"],
        "git_commit": info["git_commit"],
        "git_dirty": info["git_dirty"],
    }
