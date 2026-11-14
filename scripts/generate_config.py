#!/usr/bin/env python3
"""
Generate the public runtime config.js for the Cocktail Database frontend.

Values come from the Ansible inventory for the target environment, the same
source the deployment uses, so a generated config matches what is deployed.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_DIR = ROOT / "infrastructure" / "ansible" / "inventory"

PUBLIC_CONFIG_FIELDS = (
    "apiUrl",
    "userPoolId",
    "clientId",
    "cognitoDomain",
    "appUrl",
    "appName",
)
PUBLIC_URL_FIELDS = ("apiUrl", "cognitoDomain", "appUrl")


def render_public_config(config: dict) -> str:
    """Validate and serialize the browser-visible runtime configuration."""
    if not isinstance(config, dict):
        raise TypeError("public configuration must be a dictionary")

    missing = [field for field in PUBLIC_CONFIG_FIELDS if field not in config]
    if missing:
        raise ValueError(f"missing required public configuration fields: {missing}")

    unexpected = sorted(set(config) - set(PUBLIC_CONFIG_FIELDS))
    if unexpected:
        raise ValueError(f"unexpected public configuration fields: {unexpected}")

    for field in PUBLIC_CONFIG_FIELDS:
        value = config[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-blank string")

    for field in PUBLIC_URL_FIELDS:
        value = config[field]
        try:
            parsed = urlparse(value)
            has_supported_scheme = parsed.scheme in {"http", "https"}
            has_hostname = bool(parsed.hostname)
        except ValueError:
            has_supported_scheme = False
            has_hostname = False
        if not has_supported_scheme or not has_hostname:
            raise ValueError(f"{field} must use http or https and include a hostname")

    public_config = {field: config[field] for field in PUBLIC_CONFIG_FIELDS}
    return f"export default {json.dumps(public_config)};\n"


def public_config_from_inventory(inventory_path, app_url=None, app_name=None):
    """Build the public config from an Ansible inventory file.

    Mirrors ``public_frontend_config`` in infrastructure/ansible/playbooks/
    deploy.yml. ``app_url``/``app_name`` override the deployed values, e.g. to
    point a local frontend at the remote API.
    """
    import yaml

    inventory = yaml.safe_load(Path(inventory_path).read_text(encoding="utf-8"))
    host_vars = next(iter(inventory["all"]["hosts"].values()))
    domain = host_vars["domain_name"]
    return {
        "apiUrl": f"https://{domain}/api",
        "userPoolId": host_vars["user_pool_id"],
        "clientId": host_vars["app_client_id"],
        "cognitoDomain": host_vars["cognito_domain"],
        "appUrl": app_url or f"https://{domain}",
        "appName": app_name or f"Cocktail Database ({host_vars.get('app_env', 'dev')})",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate config.js from the Ansible inventory"
    )
    parser.add_argument("target_env", choices=["dev", "prod"])
    parser.add_argument("--app-url", help="Override appUrl (e.g. a local server)")
    parser.add_argument("--app-name", help="Override appName")
    parser.add_argument(
        "--output",
        default=str(ROOT / "src" / "web" / "js" / "config.js"),
        help="Output path (default: src/web/js/config.js)",
    )
    args = parser.parse_args()

    try:
        config = public_config_from_inventory(
            INVENTORY_DIR / f"{args.target_env}.yml",
            app_url=args.app_url,
            app_name=args.app_name,
        )
        content = render_public_config(config)
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(f"Error generating config.js: {error}", file=sys.stderr)
        sys.exit(1)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"Wrote {output} for {args.target_env} (API: {config['apiUrl']})")


if __name__ == "__main__":
    main()
