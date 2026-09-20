import json
from pathlib import Path

import pytest

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


def test_public_config_escapes_javascript_values():
    config = dict(
        apiUrl="https://dev.example/api",
        userPoolId="pool",
        clientId="client",
        cognitoDomain="https://auth.example",
        appUrl="http://localhost:8000",
        appName="Kurt's \\ bar\n",
    )

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


def test_config_template_serializes_explicit_public_dictionary():
    template = (ROOT / "infrastructure/ansible/files/config.js.j2").read_text(
        encoding="utf-8"
    )

    assert "to_json" in template
    for field in VALID_CONFIG:
        assert field in template
    for secret in ("DB_PASSWORD", "AWS_SECRET_ACCESS_KEY", "client_secret"):
        assert secret not in template


def test_ansible_validates_public_config_before_frontend_staging():
    playbook = (ROOT / "infrastructure/ansible/playbooks/deploy.yml").read_text(
        encoding="utf-8"
    )

    assert "ansible.builtin.assert" in playbook
    assert playbook.index("ansible.builtin.assert") < playbook.index(
        "name: Stage frontend code"
    )
    for variable in ("domain_name", "user_pool_id", "app_client_id", "cognito_domain"):
        assert variable in playbook


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
