import numpy as np
from fastapi.testclient import TestClient


def test_save_em_distance_matrix_writes_file(tmp_path):
    from api.utils import analytics_files

    matrix = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
    output_path = analytics_files.save_em_distance_matrix(str(tmp_path), matrix)

    assert output_path.exists()
    loaded = np.load(output_path)
    assert np.allclose(loaded, matrix)


def test_download_em_distance_matrix(tmp_path, monkeypatch):
    matrix = np.array([[0.0, 2.0], [2.0, 0.0]], dtype=np.float32)
    from api.utils import analytics_files

    file_path = analytics_files.save_em_distance_matrix(str(tmp_path), matrix)

    monkeypatch.setenv("ANALYTICS_PATH", str(tmp_path))

    from api.main import app

    client = TestClient(app)
    response = client.get("/analytics/recipe-distances-em/download")

    assert response.status_code == 200
    assert response.content == file_path.read_bytes()
    assert "attachment" in response.headers.get("content-disposition", "")
