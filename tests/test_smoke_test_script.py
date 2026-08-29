import os
import subprocess


def run_smoke_test(tmp_path, status):
    curl = tmp_path / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        "printf '%s\\n' \"$*\" >> \"$CURL_LOG\"\n"
        "if [[ \" $* \" == *\" -w \"* ]]; then\n"
        f"  printf '{status}'\n"
        "else\n"
        "  case \"${@: -1}\" in\n"
        "    */health) printf '{\"status\":\"healthy\"}' ;;\n"
        "    */recipes/search) printf '{\"recipes\":[{\"id\":1}]}' ;;\n"
        "    */ingredients) printf '[{\"id\":1,\"name\":\"Whiskey\"}]' ;;\n"
        "    *) printf '{}' ;;\n"
        "  esac\n"
        "fi\n"
    )
    curl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["CURL_LOG"] = str(tmp_path / "curl.log")
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


def test_smoke_test_uses_current_public_api_routes(tmp_path):
    result = run_smoke_test(tmp_path, "200")

    assert result.returncode == 0
    requests = (tmp_path / "curl.log").read_text().splitlines()
    assert any(request.endswith("https://example.test/api/v1/recipes/search") for request in requests)
    assert any(request.endswith("https://example.test/api/v1/tags/public") for request in requests)
    assert not any(request.endswith("https://example.test/api/v1/recipes") for request in requests)
    assert not any(request.endswith("https://example.test/api/v1/tags") for request in requests)


def test_smoke_test_runs_every_check_when_they_fail(tmp_path):
    result = run_smoke_test(tmp_path, "500")

    assert result.returncode == 1
    assert "Testing Static CSS" in result.stdout
    assert "Passed: 3" in result.stdout
    assert "Failed: 10" in result.stdout
