import os
import subprocess


def run_smoke_test(tmp_path, status, *, recipe_id="1", ingredient_id="2"):
    curl = tmp_path / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        'printf \'%s\\n\' "$*" >> "$CURL_LOG"\n'
        'url="${@: -1}"\n'
        'if [[ "$url" == *"/manifest.json" || "$url" == *"/asset-inventory.json" || "$url" == *"/frontend-state.json" || "$url" == *"/frontend-pending.json" || "$url" == *"/recipe/404" || "$url" == *"/ingredient/404" ]]; then\n'
        "  printf '404'\n"
        'elif [[ " $* " == *" -w "* ]]; then\n'
        f"  printf '{status}'\n"
        "else\n"
        '  case "$url" in\n'
        '    */) printf \'<html><link href="/assets/style-A.css"><script src="/assets/app-A.js"></script></html>\' ;;\n'
        "    */js/config.js) printf 'export default { apiUrl: \"https://api.example.test\" };' ;;\n"
        '    */recipe/*|*/ingredient/*) printf \'<html><link href="/assets/style-A.css"><script src="/assets/app-A.js"></script></html>\' ;;\n'
        '    */health) printf \'{"status":"healthy"}\' ;;\n'
        '    */recipes/search) [[ "${SMOKE_EMPTY_DB:-}" == true ]] && printf \'{"recipes":[]}\' || printf \'{"recipes":[{"id":1}]}\' ;;\n'
        '    */ingredients) [[ "${SMOKE_EMPTY_DB:-}" == true ]] && printf \'[]\' || printf \'[{"id":2,"name":"Whiskey"}]\' ;;\n'
        "    *) printf '{}' ;;\n"
        "  esac\n"
        "fi\n"
    )
    curl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["CURL_LOG"] = str(tmp_path / "curl.log")
    env["SMOKE_RECIPE_ID"] = recipe_id
    env["SMOKE_INGREDIENT_ID"] = ingredient_id
    env["SMOKE_EMPTY_DB"] = "true" if not recipe_id and not ingredient_id else ""
    env["SMOKE_ALLOW_EMPTY_DB"] = (
        "true" if not recipe_id and not ingredient_id else "false"
    )
    return subprocess.run(
        ["bash", "infrastructure/scripts/smoke-test.sh", "https://example.test"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_smoke_test_discovers_built_assets_and_checks_metadata(tmp_path):
    result = run_smoke_test(tmp_path, "200")

    assert result.returncode == 0
    assert "Testing Static index" in result.stdout
    assert "Testing Static config" in result.stdout
    assert "Testing Recipe page" in result.stdout
    assert "Testing Ingredient page" in result.stdout
    assert "manifest metadata exclusion" in result.stdout
    assert "asset availability" in result.stdout
    requests = (tmp_path / "curl.log").read_text().splitlines()
    assert any(
        request.endswith("https://example.test/assets/app-A.js") for request in requests
    )
    assert any(
        request.endswith("https://example.test/assets/style-A.css")
        for request in requests
    )
    assert not any(
        request.endswith("https://example.test/js/api.js") for request in requests
    )
    assert not any(
        request.endswith("https://example.test/css/styles.css") for request in requests
    )


def test_smoke_test_uses_current_public_api_routes(tmp_path):
    result = run_smoke_test(tmp_path, "200")

    assert result.returncode == 0
    requests = (tmp_path / "curl.log").read_text().splitlines()
    assert any(
        request.endswith("https://example.test/api/v1/recipes/search")
        for request in requests
    )
    assert any(
        request.endswith("https://example.test/api/v1/tags/public")
        for request in requests
    )
    assert not any(
        request.endswith("https://example.test/api/v1/recipes") for request in requests
    )
    assert not any(
        request.endswith("https://example.test/api/v1/tags") for request in requests
    )


def test_smoke_test_fails_when_selected_page_checks_fail(tmp_path):
    result = run_smoke_test(tmp_path, "500")

    assert result.returncode == 1
    assert "SMOKE TEST FAILED" in result.stdout
    assert "Failed:" in result.stdout


def test_empty_database_smoke_checks_not_found_pages_without_fake_ids(tmp_path):
    result = run_smoke_test(tmp_path, "200", recipe_id="", ingredient_id="")

    assert result.returncode == 0
    requests = (tmp_path / "curl.log").read_text().splitlines()
    assert any(
        request.endswith("https://example.test/recipe/404") for request in requests
    )
    assert any(
        request.endswith("https://example.test/ingredient/404") for request in requests
    )
    assert not any(
        request.endswith("https://example.test/recipe/1") for request in requests
    )
    assert not any(
        request.endswith("https://example.test/ingredient/2") for request in requests
    )
