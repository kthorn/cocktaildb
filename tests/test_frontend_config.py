import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.generate_config import render_public_config

ROOT = Path(__file__).resolve().parents[1]


VALID_CONFIG = {
    "apiUrl": "https://dev.example/api",
    "userPoolId": "pool",
    "clientId": "client",
    "cognitoDomain": "https://auth.example",
    "appUrl": "http://localhost:8000",
    "appName": "Cocktail Database (dev)",
}


def test_public_renderer_imports_without_boto3():
    script = """
import sys

class BlockBoto3:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'boto3' or fullname.startswith('boto3.'):
            raise ModuleNotFoundError('blocked boto3 for import isolation')
        return None

sys.meta_path.insert(0, BlockBoto3())
from scripts.generate_config import render_public_config

print(render_public_config({
    'apiUrl': 'https://api.example',
    'userPoolId': 'pool',
    'clientId': 'client',
    'cognitoDomain': 'https://auth.example',
    'appUrl': 'http://localhost:8000',
    'appName': 'Cocktail Database',
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("export default ")


def test_public_config_escapes_javascript_values():
    config = {
        "apiUrl": "https://dev.example/api",
        "userPoolId": "pool",
        "clientId": "client",
        "cognitoDomain": "https://auth.example",
        "appUrl": "http://localhost:8000",
        "appName": "Kurt's \\ bar\n",
    }

    source = render_public_config(config)

    assert source.startswith("export default ")
    assert json.loads(source[len("export default ") :].rstrip(";\n")) == config


def test_public_config_accepts_localhost_http_url():
    config = dict(VALID_CONFIG, appUrl="http://localhost:8000")

    assert (
        json.loads(render_public_config(config)[len("export default ") :].rstrip(";\n"))
        == config
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("apiUrl", "ftp://dev.example/api"),
        ("cognitoDomain", "file:///tmp/auth"),
        ("appUrl", "https:///missing-host"),
        ("apiUrl", "https://"),
    ],
)
def test_public_config_rejects_invalid_urls(field, value):
    with pytest.raises(ValueError, match=field):
        render_public_config(dict(VALID_CONFIG, **{field: value}))


@pytest.mark.parametrize("field", ["userPoolId", "clientId", "cognitoDomain"])
def test_public_config_rejects_blank_identifiers(field):
    with pytest.raises(ValueError, match=field):
        render_public_config(dict(VALID_CONFIG, **{field: "  "}))


def test_public_config_rejects_missing_required_field():
    config = dict(VALID_CONFIG)
    del config["appName"]

    with pytest.raises(ValueError, match="appName"):
        render_public_config(config)


@pytest.mark.parametrize(
    "field", ["DB_PASSWORD", "AWS_SECRET_ACCESS_KEY", "clientSecret"]
)
def test_public_config_rejects_unknown_secret_like_fields(field):
    with pytest.raises(ValueError, match=field):
        render_public_config(dict(VALID_CONFIG, **{field: "do-not-publish"}))


def test_public_config_rejects_unknown_non_secret_fields_too():
    with pytest.raises(ValueError, match="unexpected"):
        render_public_config(dict(VALID_CONFIG, unexpected="value"))


def test_public_config_requires_string_values():
    with pytest.raises(ValueError, match="clientId"):
        render_public_config(dict(VALID_CONFIG, clientId=None))


def test_generator_maps_cloudformation_names_to_public_names(tmp_path):
    from scripts.generate_config import generate_config_js

    output = tmp_path / "js" / "config.js"
    values = {
        "api_url": "https://dev.example/api",
        "user_pool_id": "pool",
        "client_id": "client",
        "cognito_domain": "https://auth.example",
        "app_url": "http://localhost:8000",
    }

    assert generate_config_js(values, "dev", str(output))
    source = output.read_text(encoding="utf-8")
    assert json.loads(source[len("export default ") :].rstrip(";\n")) == {
        **VALID_CONFIG,
        "appName": "Cocktail Database (dev)",
    }


def test_config_template_serializes_validated_public_dictionary():
    template = (ROOT / "infrastructure/ansible/files/config.js.j2").read_text(
        encoding="utf-8"
    )
    playbook = yaml.safe_load(
        (ROOT / "infrastructure/ansible/playbooks/deploy.yml").read_text(
            encoding="utf-8"
        )
    )[0]

    assert "public_frontend_config | to_json" in template
    assert set(playbook["vars"]["public_frontend_config"]) == set(VALID_CONFIG)
    for secret in ("DB_PASSWORD", "AWS_SECRET_ACCESS_KEY", "client_secret"):
        assert secret not in template


def _ansible_public_config_validation_task():
    playbook = yaml.safe_load(
        (ROOT / "infrastructure/ansible/playbooks/deploy.yml").read_text(
            encoding="utf-8"
        )
    )[0]
    for task in playbook["tasks"]:
        if task.get("name") == "Validate generated public frontend configuration":
            return task
    raise AssertionError("shared public-config validation task is missing")


def _run_ansible_public_config_validation(tmp_path, config):
    task = _ansible_public_config_validation_task()
    task["ansible.builtin.command"]["chdir"] = str(ROOT)
    playbook = tmp_path / "validate-public-config.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {"public_frontend_config": config},
                    "tasks": [task],
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    ansible_playbook = Path(sys.executable).with_name("ansible-playbook")
    return subprocess.run(
        [str(ansible_playbook), "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _ansible_candidate_config(**overrides):
    config = {
        "apiUrl": "https://dev.example/api",
        "userPoolId": "pool",
        "clientId": "client",
        "cognitoDomain": "https://auth.example",
        "appUrl": "https://dev.example",
        "appName": "Cocktail Database (dev)",
    }
    config.update(overrides)
    return config


def test_ansible_validates_public_config_before_frontend_staging():
    playbook = yaml.safe_load(
        (ROOT / "infrastructure/ansible/playbooks/deploy.yml").read_text(
            encoding="utf-8"
        )
    )[0]
    task_names = [task["name"] for task in playbook["tasks"]]

    assert task_names.index("Validate generated public frontend configuration") < (
        task_names.index("Create staged release directories")
    )
    assert task_names.index("Validate generated public frontend configuration") < (
        task_names.index("Stage frontend code")
    )
    assert any("ansible.builtin.assert" in task for task in playbook["tasks"])
    for variable in ("domain_name", "user_pool_id", "app_client_id", "cognito_domain"):
        assert variable in (
            ROOT / "infrastructure/ansible/playbooks/deploy.yml"
        ).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "config",
    [
        _ansible_candidate_config(cognitoDomain="ftp://auth.example"),
        _ansible_candidate_config(cognitoDomain="https:///missing-host"),
        _ansible_candidate_config(apiUrl="https:///missing-host/api"),
        _ansible_candidate_config(appUrl="https:///missing-host"),
    ],
)
def test_ansible_preflight_rejects_concrete_malformed_public_urls(tmp_path, config):
    result = _run_ansible_public_config_validation(tmp_path, config)

    assert result.returncode != 0
    assert "Validate generated public frontend configuration" in (
        result.stdout + result.stderr
    )


def test_ansible_preflight_accepts_renderer_valid_public_urls(tmp_path):
    result = _run_ansible_public_config_validation(
        tmp_path, _ansible_candidate_config()
    )

    assert result.returncode == 0, result.stdout + result.stderr


def _serve_fixture(tmp_path, config):
    project = tmp_path / "serve-project"
    (project / "scripts").mkdir(parents=True)
    (project / "src" / "web" / "js").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/serve.sh", project / "scripts/serve.sh")
    (project / "src" / "web" / "js" / "config.js").write_text(
        render_public_config(config), encoding="utf-8"
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    npm_log = tmp_path / "npm-args.txt"
    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" > "$FAKE_NPM_LOG"\n', encoding="utf-8"
    )
    fake_npm.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "FAKE_NPM_LOG": str(npm_log),
    }
    return project, environment, npm_log


def test_serve_accepts_renderer_generated_local_config_without_prompt(tmp_path):
    project, environment, npm_log = _serve_fixture(tmp_path, VALID_CONFIG)

    result = subprocess.run(
        ["bash", str(project / "scripts" / "serve.sh")],
        cwd=project,
        env=environment,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Continue anyway?" not in result.stdout
    assert npm_log.read_text(encoding="utf-8").strip() == "run dev"


def test_serve_warns_before_declining_remote_renderer_config(tmp_path):
    remote_config = dict(VALID_CONFIG, appUrl="https://dev.example")
    project, environment, npm_log = _serve_fixture(tmp_path, remote_config)

    result = subprocess.run(
        ["bash", str(project / "scripts" / "serve.sh")],
        cwd=project,
        env=environment,
        input="n\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "remote configuration" in result.stdout
    assert not npm_log.exists()


def test_local_development_uses_fixed_vite_port_and_shared_generator():
    local_config = (ROOT / "scripts/local-config.sh").read_text(encoding="utf-8")
    serve = (ROOT / "scripts/serve.sh").read_text(encoding="utf-8")

    assert "render_public_config" in local_config
    assert "npm run dev" in serve
    assert 'PORT="8000"' in serve or "PORT=8000" in serve
    assert "localhost:8000" in local_config
    assert "localhost:8000" in serve


def test_vite_config_proxies_optional_ssr_to_explicit_backend_port():
    vite_config = (ROOT / "vite.config.mjs").read_text(encoding="utf-8")

    assert "localhost:8001" in vite_config
    assert "proxy" in vite_config
    assert "/recipe" in vite_config
    assert "/ingredient" in vite_config
