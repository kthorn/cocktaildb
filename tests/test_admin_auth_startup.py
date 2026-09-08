"""Run the dependency-free admin auth startup regression test under pytest."""

import subprocess


def test_admin_auth_startup_is_initialized_once():
    subprocess.run(["node", "tests/test_admin_auth_startup.js"], check=True)
