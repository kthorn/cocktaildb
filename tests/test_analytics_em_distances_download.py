import httpx
import numpy as np
import pytest
from httpx import ASGITransport


def test_save_em_distance_matrix_writes_file(tmp_path):
    from api.utils import analytics_files

    matrix = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
    output_path = analytics_files.save_em_distance_matrix(str(tmp_path), matrix)

    assert output_path.exists()
    loaded = np.load(output_path)
    assert np.allclose(loaded, matrix)


def test_save_em_ingredient_distance_matrix_writes_file(tmp_path):
    from api.utils import analytics_files

    matrix = np.array([[0.0, 2.0], [2.0, 0.0]], dtype=np.float32)
    output_path = analytics_files.save_em_ingredient_distance_matrix(
        str(tmp_path), matrix
    )

    assert output_path.exists()
    loaded = np.load(output_path)
    assert np.allclose(loaded, matrix)


@pytest.mark.asyncio
async def test_download_em_distance_matrix(tmp_path, monkeypatch):
    matrix = np.array([[0.0, 2.0], [2.0, 0.0]], dtype=np.float32)
    from api.utils import analytics_files

    file_path = analytics_files.save_em_distance_matrix(str(tmp_path), matrix)

    monkeypatch.setenv("ANALYTICS_PATH", str(tmp_path))

    from api.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/analytics/recipe-distances-em/download")

    assert response.status_code == 200
    assert response.content == file_path.read_bytes()
    assert "attachment" in response.headers.get("content-disposition", "")
