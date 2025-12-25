import numpy as np
import scipy.sparse as sp

from barcart.em_learner import em_fit


def test_em_fit_accepts_sparse_volume_matrix_float32() -> None:
    volume = sp.csr_matrix(
        np.array(
            [
                [0.6, 0.4],
                [0.2, 0.8],
            ],
            dtype=np.float32,
        )
    )
    cost = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)

    dist, new_cost, _log = em_fit(volume, cost, n_ingredients=2, iters=1, n_jobs=1)

    assert dist.shape == (2, 2)
    assert new_cost.shape == (2, 2)
    assert dist.dtype == np.float32
    assert new_cost.dtype == np.float32
