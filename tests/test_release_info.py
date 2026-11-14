"""The deployed release identity reported by /health."""

import json

import httpx
import pytest
from httpx import ASGITransport

from api.core.release_info import read_release_info

RELEASE = {
    "release_id": "20261114T180000Z-4242",
    "git_commit": "fa18b6e0123456789abcdef0123456789abcdef0",
    "git_dirty": False,
}


def test_reads_the_staged_release_identity(tmp_path):
    path = tmp_path / "release.json"
    path.write_text(json.dumps(RELEASE), encoding="utf-8")

    assert read_release_info(path) == RELEASE


def test_no_staged_file_means_no_release_identity(tmp_path):
    assert read_release_info(tmp_path / "release.json") is None


def test_a_malformed_release_file_fails_loudly(tmp_path):
    path = tmp_path / "release.json"
    path.write_text(json.dumps({"release_id": "x"}), encoding="utf-8")

    with pytest.raises(KeyError):
        read_release_info(path)


@pytest.mark.asyncio
@pytest.mark.parametrize("release", [RELEASE, None])
async def test_health_reports_the_release_identity(monkeypatch, release):
    import api.main

    monkeypatch.setattr(api.main, "RELEASE_INFO", release)
    transport = ASGITransport(app=api.main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["release"] == release
