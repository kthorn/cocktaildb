"""Exercise response contracts against the production Starlette dependency."""

import httpx
import pytest
from core.exception_handlers import (
    general_exception_handler,
    starlette_http_exception_handler,
    validation_exception_handler,
)
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from main import CORSHeaderMiddleware
from routes.admin import CleanupFileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@pytest.mark.asyncio
async def test_error_responses_with_cors_middleware():
    app = FastAPI()
    app.add_middleware(CORSHeaderMiddleware)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="Forbidden")

    @app.get("/validate")
    async def validate(count: int):
        return {"count": count}

    @app.get("/crash")
    async def crash():
        raise RuntimeError("private internal detail")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        for path, status in [
            ("/forbidden", 403),
            ("/missing", 404),
            ("/validate?count=bad", 422),
        ]:
            response = await client.get(path)
            assert response.status_code == status
            assert response.headers["access-control-allow-origin"] == "*"
            assert response.json()["detail"]
        response = await client.get("/crash")
        assert response.status_code == 500
        assert response.json() == {
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred",
        }


@pytest.mark.asyncio
async def test_download_sends_file_before_cleanup(tmp_path):
    backup = tmp_path / "backup.sql"
    backup.write_text("example backup")
    app = FastAPI()

    @app.get("/download")
    async def download():
        return CleanupFileResponse(
            path=backup,
            media_type="application/sql",
            filename="backup.sql",
            cleanup_path=str(backup),
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/download")
    assert response.status_code == 200
    assert response.text == "example backup"
    assert 'filename="backup.sql"' in response.headers["content-disposition"]
    assert not backup.exists()
