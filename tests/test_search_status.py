"""Run the dependency-free search status regression test under pytest."""

import subprocess


def test_search_status_preserved_during_rendering():
    subprocess.run(["node", "tests/test_search_status.js"], check=True)
