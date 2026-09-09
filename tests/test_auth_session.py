"""Run browser session regression tests with Node's built-in test runner."""

import subprocess


def test_cognito_persistent_session():
    subprocess.run(["node", "tests/test_auth_session.js"], check=True)
