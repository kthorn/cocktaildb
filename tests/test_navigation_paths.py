"""Verify navigation works from server-rendered nested pages."""

import subprocess
from pathlib import Path


def test_navigation_paths():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["node", "tests/test_navigation_paths.mjs"], cwd=root, check=True)
