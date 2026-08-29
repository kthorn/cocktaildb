import os
import subprocess


def run_smoke_test(tmp_path, status):
    curl = tmp_path / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        "if [[ \" $* \" == *\" -w \"* ]]; then\n"
        f"  printf '{status}'\n"
        "else\n"
        "  printf '{\"status\":\"healthy\",\"recipes\":[],\"ingredients\":[]}'\n"
        "fi\n"
    )
    curl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    return subprocess.run(
        ["bash", "infrastructure/scripts/smoke-test.sh", "https://example.test"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_smoke_test_runs_every_check_when_they_pass(tmp_path):
    result = run_smoke_test(tmp_path, "200")

    assert result.returncode == 0
    assert "Testing Static CSS" in result.stdout
    assert "Passed: 13" in result.stdout
    assert "Failed: 0" in result.stdout


def test_smoke_test_runs_every_check_when_they_fail(tmp_path):
    result = run_smoke_test(tmp_path, "500")

    assert result.returncode == 1
    assert "Testing Static CSS" in result.stdout
    assert "Passed: 3" in result.stdout
    assert "Failed: 10" in result.stdout
