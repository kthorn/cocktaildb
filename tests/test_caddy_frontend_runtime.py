"""Real-Caddy cache and routing checks for the frontend release paths."""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import stat
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from inspect import getsource
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = ROOT / "infrastructure" / "caddy" / "Caddyfile"
FRONTEND_RELEASE_PATH = ROOT / "infrastructure" / "scripts" / "frontend-release.py"
_RELEASE_SPEC = importlib.util.spec_from_file_location(
    "frontend_release_for_caddy", FRONTEND_RELEASE_PATH
)
assert _RELEASE_SPEC and _RELEASE_SPEC.loader
frontend_release = importlib.util.module_from_spec(_RELEASE_SPEC)
_RELEASE_SPEC.loader.exec_module(frontend_release)
CADDY_IMAGE = (
    "caddy:2.10.2-alpine@sha256:"
    "4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d"
)


class _SsrHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith(("/recipe/", "/ingredient/")):
            body = f"SSR upstream: {self.path}".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, _format, *_args):
        return


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _ensure_caddy_image(docker: str) -> None:
    inspected = subprocess.run(
        [docker, "image", "inspect", CADDY_IMAGE],
        text=True,
        capture_output=True,
        check=False,
    )
    if inspected.returncode == 0:
        return
    pulled = subprocess.run(
        [docker, "pull", CADDY_IMAGE],
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    if pulled.returncode != 0:
        pytest.fail(
            "Caddy is required for the frontend release gate; pinned image pull "
            f"failed:\n{pulled.stdout}\n{pulled.stderr}"
        )


def _caddy_runner(tmp_path: Path, domain_port: int, http_port: int, upstream_port: int):
    configured_binary = os.environ.get("CADDY_BIN")
    binary = configured_binary or shutil.which("caddy")
    docker = shutil.which("docker")
    use_docker = binary is None
    if use_docker and docker is None:
        pytest.fail(
            "Caddy is required for the frontend release gate; set CADDY_BIN or "
            "provide Docker for the pinned official test image"
        )
    if use_docker:
        _ensure_caddy_image(docker)

    app_home = tmp_path / "app"
    release = app_home / "releases" / "caddy"
    web = release / "web"
    assets = web / "assets"
    logs = tmp_path / "logs"
    (web / "js").mkdir(parents=True)
    assets.mkdir()
    logs.mkdir()
    logs.chmod(0o777)
    (web / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (web / "media.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>\n', encoding="utf-8"
    )
    (web / "js" / "config.js").write_text(
        "export default { apiUrl: 'http://upstream.invalid' };\n", encoding="utf-8"
    )
    (assets / "test-A.js").write_text("export default 1;\n", encoding="utf-8")
    (assets / "icon-A.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>\n', encoding="utf-8"
    )
    for name in (
        "normalize.css",
        "styles.css",
        "recipe-card.css",
        "common.js",
        "recipe.js",
    ):
        (assets / name).write_text(name, encoding="utf-8")
    (release / "manifest.json").write_text(
        '{"normalize.css":{"file":"assets/normalize.css"},"styles.css":{"file":"assets/styles.css"},"recipe-card.css":{"file":"assets/recipe-card.css"},"js/common.js":{"file":"assets/common.js"},"js/recipe.js":{"file":"assets/recipe.js"},"index.html":{"file":"assets/test-A.js","assets":["assets/icon-A.svg"]}}\n',
        encoding="utf-8",
    )
    (release / "asset-inventory.json").write_text(
        '{"version":1,"files":["common.js","icon-A.svg","normalize.css","recipe-card.css","recipe.js","styles.css","test-A.js"]}\n',
        encoding="utf-8",
    )
    frontend_release.publish_assets(release, app_home)
    published_assets = app_home / "frontend-assets"
    (published_assets / "test-A.js").chmod(0o600)

    reused_release = app_home / "releases" / "reused"
    reused_web = reused_release / "web"
    reused_assets = reused_web / "assets"
    (reused_web / "js").mkdir(parents=True)
    reused_assets.mkdir()
    (reused_web / "js" / "config.js").write_text(
        "export default { apiUrl: 'http://upstream.invalid' };\n", encoding="utf-8"
    )
    (reused_web / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (reused_web / "media.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>\n', encoding="utf-8"
    )
    for source in published_assets.iterdir():
        shutil.copy2(source, reused_assets / source.name)
    (reused_release / "manifest.json").write_text(
        '{"normalize.css":{"file":"assets/normalize.css"},"styles.css":{"file":"assets/styles.css"},"recipe-card.css":{"file":"assets/recipe-card.css"},"js/common.js":{"file":"assets/common.js"},"js/recipe.js":{"file":"assets/recipe.js"},"index.html":{"file":"assets/test-A.js","assets":["assets/icon-A.svg"]}}\n',
        encoding="utf-8",
    )
    (reused_release / "asset-inventory.json").write_text(
        '{"version":1,"files":["common.js","icon-A.svg","normalize.css","recipe-card.css","recipe.js","styles.css","test-A.js"]}\n',
        encoding="utf-8",
    )
    frontend_release.publish_assets(reused_release, app_home)
    assert stat.S_IMODE((published_assets / "test-A.js").stat().st_mode) == 0o644
    web = reused_web
    assets = published_assets

    network = None
    upstream_name = None
    upstream_process = None
    caddy_name = None
    caddy_process = None

    def cleanup():
        nonlocal caddy_process, upstream_process
        for process in (caddy_process, upstream_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=15)
        if use_docker:
            for container in (caddy_name, upstream_name):
                if container:
                    subprocess.run(
                        [docker, "rm", "-f", container],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
            if network:
                subprocess.run(
                    [docker, "network", "rm", network],
                    text=True,
                    capture_output=True,
                    check=False,
                )

    try:
        if use_docker:
            network = f"cocktaildb-task4-{uuid.uuid4().hex}"
            created = subprocess.run(
                [docker, "network", "create", network],
                text=True,
                capture_output=True,
                check=False,
            )
            assert created.returncode == 0, created.stdout + created.stderr

            upstream_config = tmp_path / "ssr-upstream.Caddyfile"
            upstream_config.write_text(
                """{
    admin off
    auto_https off
}

:8000 {
    handle /recipe/test {
        respond "SSR upstream: /recipe/test"
    }

    handle /ingredient/test {
        respond "SSR upstream: /ingredient/test"
    }
}
""",
                encoding="utf-8",
            )
            upstream_name = f"cocktaildb-task4-upstream-{uuid.uuid4().hex}"
            upstream_process = subprocess.Popen(
                [
                    docker,
                    "run",
                    "--rm",
                    "--name",
                    upstream_name,
                    "--network",
                    network,
                    "--network-alias",
                    "ssr-upstream",
                    "-v",
                    f"{upstream_config}:/etc/caddy/Caddyfile:ro",
                    CADDY_IMAGE,
                    "caddy",
                    "run",
                    "--config",
                    "/etc/caddy/Caddyfile",
                    "--adapter",
                    "caddyfile",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if upstream_process.poll() is not None:
                    output = (
                        upstream_process.stdout.read()
                        if upstream_process.stdout
                        else ""
                    )
                    raise AssertionError(
                        f"SSR upstream exited during startup:\n{output}"
                    )
                ready = subprocess.run(
                    [
                        docker,
                        "exec",
                        upstream_name,
                        "wget",
                        "-qO-",
                        "http://127.0.0.1:8000/recipe/test",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("SSR upstream did not start before the timeout")
            upstream_host = "ssr-upstream"
            upstream_target_port = 8000
        else:
            upstream_host = "127.0.0.1"
            upstream_target_port = upstream_port

        config = CADDYFILE.read_text(encoding="utf-8")
        config = config.replace(
            "localhost:8000", f"{upstream_host}:{upstream_target_port}"
        )
        config = config.replace(":80 {", f":{http_port} {{")
        config = config.replace(
            "    admin off\n", "    admin off\n    auto_https off\n"
        )
        if use_docker:
            config = config.replace(
                "not remote_ip 127.0.0.1", "not remote_ip 127.0.0.1 172.16.0.0/12"
            )
        else:
            config = config.replace("/opt/cocktaildb/web", str(web))
            config = config.replace("/opt/cocktaildb/frontend-assets", str(assets))
            config = config.replace(
                "/var/log/caddy/access.log", str(logs / "access.log")
            )
        config_path = tmp_path / "Caddyfile"
        config_path.write_text(config, encoding="utf-8")

        environment = {
            **os.environ,
            "DOMAIN_NAME": f"http://domain.test:{domain_port}",
            "ACME_EMAIL": "test@example.invalid",
        }
        if use_docker:
            mounts = [
                f"{config_path}:/etc/caddy/Caddyfile:ro",
                f"{web}:/opt/cocktaildb/web:ro",
                f"{assets}:/opt/cocktaildb/frontend-assets:ro",
                f"{logs}:/var/log/caddy",
            ]
            caddy_name = f"cocktaildb-task4-caddy-{uuid.uuid4().hex}"
            command = [
                docker,
                "run",
                "--rm",
                "--name",
                caddy_name,
                # The pinned image runs as root by default and has no named
                # service user; nobody exercises the same non-owner read gate.
                "--user",
                "65534:65534",
                "--network",
                network,
                "-p",
                f"127.0.0.1:{domain_port}:{domain_port}",
                "-p",
                f"127.0.0.1:{http_port}:{http_port}",
                *[item for mount in mounts for item in ("-v", mount)],
                "-e",
                f"DOMAIN_NAME=http://domain.test:{domain_port}",
                "-e",
                "ACME_EMAIL=test@example.invalid",
                CADDY_IMAGE,
                "caddy",
                "run",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            ]
            validate = [
                docker,
                "run",
                "--rm",
                "--network",
                network,
                "-v",
                f"{config_path}:/etc/caddy/Caddyfile:ro",
                "-e",
                f"DOMAIN_NAME=http://domain.test:{domain_port}",
                "-e",
                "ACME_EMAIL=test@example.invalid",
                CADDY_IMAGE,
                "caddy",
                "validate",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            ]
        else:
            command = [
                binary,
                "run",
                "--config",
                str(config_path),
                "--adapter",
                "caddyfile",
            ]
            validate = [
                binary,
                "validate",
                "--config",
                str(config_path),
                "--adapter",
                "caddyfile",
            ]

        checked = subprocess.run(
            validate,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        caddy_process = subprocess.Popen(
            command,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return caddy_process, cleanup
    except BaseException:
        cleanup()
        raise


def test_docker_caddy_uses_owned_network_for_ssr_upstream():
    runner = getsource(_caddy_runner)
    assert "host.docker.internal" not in runner
    assert '"--network"' in runner
    assert '"--network-alias"' in runner


def get(base_url: str, path: str, host: str):
    """Fetch a route while retaining HTTPError as a response for 404 checks."""
    request = Request(f"{base_url}{path}", headers={"Host": host})
    try:
        return urlopen(request, timeout=3)
    except HTTPError as error:
        return error


def _wait_for_server(process: subprocess.Popen, base_url: str, host: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise AssertionError(f"Caddy exited during startup:\n{output}")
        try:
            response = get(base_url, "/js/config.js", host)
            response.close()
            return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("Caddy did not start before the timeout")


def test_real_caddy_serves_hashed_assets_and_both_route_styles(tmp_path):
    use_docker = (os.environ.get("CADDY_BIN") or shutil.which("caddy")) is None
    upstream = None
    upstream_thread = None
    if not use_docker:
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), _SsrHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
    process = None
    cleanup = None
    domain_port = _free_port()
    http_port = _free_port()
    try:
        process, cleanup = _caddy_runner(
            tmp_path,
            domain_port,
            http_port,
            upstream.server_address[1] if upstream is not None else 0,
        )
        routes = (
            (f"http://127.0.0.1:{domain_port}", f"domain.test:{domain_port}"),
            (f"http://127.0.0.1:{http_port}", f"127.0.0.1:{http_port}"),
        )
        for base_url, host in routes:
            _wait_for_server(process, base_url, host)

            asset = get(base_url, "/assets/test-A.js", host)
            assert asset.status == 200
            assert (
                asset.headers["Cache-Control"] == "public, max-age=31536000, immutable"
            )
            asset.close()

            icon = get(base_url, "/assets/icon-A.svg", host)
            assert icon.status == 200
            assert (
                icon.headers["Cache-Control"] == "public, max-age=31536000, immutable"
            )
            icon.close()

            missing = get(base_url, "/assets/missing.js", host)
            assert missing.status == 404
            assert "immutable" not in missing.headers.get("Cache-Control", "")
            missing.close()

            config = get(base_url, "/js/config.js", host)
            assert config.status == 200
            assert config.headers["Cache-Control"] == "no-cache"
            config.close()

            html = get(base_url, "/", host)
            assert html.status == 200
            assert html.headers["Cache-Control"] == "no-cache"
            html.close()

            media = get(base_url, "/media.svg", host)
            assert media.status == 200
            assert media.headers["Cache-Control"] == "public, max-age=3600"
            media.close()

            ssr = get(base_url, "/recipe/test", host)
            assert ssr.status == 200
            assert ssr.read().decode() == "SSR upstream: /recipe/test"
            ssr.close()
    finally:
        if cleanup is not None:
            cleanup()
        if upstream is not None:
            upstream.shutdown()
            upstream.server_close()
        if upstream_thread is not None:
            upstream_thread.join(timeout=5)
