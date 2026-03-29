# EM Sparse/Float32 Memory Reduction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce EM-based cocktail space memory by switching to float32 and sparse recipe volume matrices.

**Architecture:** Use sparse CSR for the recipe volume matrix to avoid a full dense recipe-by-ingredient array, and keep EM cost/distance matrices in float32 throughout the EM loop. Update EM/EMD utilities to accept sparse inputs and to avoid implicit upcasts to float64.

**Tech Stack:** Python, NumPy, SciPy sparse, POT (ot), pytest.

### Task 1: Add failing tests for sparse EM input + float32 outputs

**Files:**
- Create: `packages/barcart/tests/test_em_learner.py`

**Step 1: Write the failing test**

```python
import numpy as np
import scipy.sparse as sp

from barcart.em_learner import em_fit


def test_em_fit_accepts_sparse_volume_matrix_float32():
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

    dist, new_cost, log = em_fit(volume, cost, n_ingredients=2, iters=1, n_jobs=1)

    assert dist.shape == (2, 2)
    assert new_cost.shape == (2, 2)
    assert dist.dtype == np.float32
    assert new_cost.dtype == np.float32
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/barcart/tests/test_em_learner.py::test_em_fit_accepts_sparse_volume_matrix_float32 -v`  
Expected: FAIL (TypeError or dtype mismatch).

**Step 3: Commit test**

```bash
git add packages/barcart/tests/test_em_learner.py
git commit -m "test: require sparse em_fit inputs and float32 outputs"
```

### Task 2: Build sparse recipe volume matrix + float32 in EM path

**Files:**
- Modify: `packages/barcart/barcart/distance.py`
- Modify: `api/db/db_analytics.py`

**Step 1: Write a failing test for sparse matrix creation (optional if covered by Task 1)**

If needed, add a small unit test in `packages/barcart/tests/test_distance.py` to assert
`build_recipe_volume_matrix(..., sparse=True)` returns a CSR matrix with float32 dtype.

**Step 2: Implement sparse volume matrix builder**

In `packages/barcart/barcart/distance.py`, extend `build_recipe_volume_matrix` with a
`sparse: bool = False` parameter. When `sparse=True`, assemble a `scipy.sparse.coo_matrix`
from row/col/value arrays and return CSR with `dtype=np.float32`.

**Step 3: Update EM analytics caller to request sparse + float32**

In `api/db/db_analytics.py` within `compute_cocktail_space_umap_em`:

- Cast `cost_matrix = cost_matrix.astype(np.float32, copy=False)`.
- Call `build_recipe_volume_matrix(..., sparse=True)` and ensure its dtype is float32.
- Add a log line for `cost_matrix.dtype` and `volume_matrix.dtype`.

**Step 4: Run test to verify it fails/passes as appropriate**

Run: `pytest packages/barcart/tests/test_em_learner.py::test_em_fit_accepts_sparse_volume_matrix_float32 -v`

**Step 5: Commit**

```bash
git add packages/barcart/barcart/distance.py api/db/db_analytics.py
git commit -m "perf: build sparse volume matrix for em analytics"
```

### Task 3: Update EM/EMD utilities to accept sparse inputs + keep float32

**Files:**
- Modify: `packages/barcart/barcart/distance.py`
- Modify: `packages/barcart/barcart/em_learner.py`

**Step 1: Write failing test (if not already covered)**

If Task 1 is failing due to sparse inputs, proceed directly to implementation.

**Step 2: Implement sparse support in `emd_matrix` and `compute_emd`**

In `packages/barcart/barcart/distance.py`:

- Detect sparse matrices via `scipy.sparse.issparse`.
- For sparse `volume_matrix`, compute supports via row `.indices`.
- Pass sparse rows into `compute_emd` with `support_idx` and extract `a_sub`/`b_sub` via
  `a[:, support_idx].toarray().ravel().astype(np.float32, copy=False)` (same for `b`).
- Ensure `emd_matrix` allocates `emd_matrix = np.zeros(..., dtype=np.float32)` and
  casts distances to float32 on assignment.

**Step 3: Keep EM outputs float32**

In `packages/barcart/barcart/em_learner.py`:

- Ensure `previous_cost_matrix` is float32 at entry.
- After `m_step_blosum`, cast `new_cost_matrix = new_cost_matrix.astype(np.float32, copy=False)`.
- After `emd_matrix`, cast `distance_matrix = distance_matrix.astype(np.float32, copy=False)` if needed.

**Step 4: Run tests to verify pass**

Run: `pytest packages/barcart/tests/test_em_learner.py::test_em_fit_accepts_sparse_volume_matrix_float32 -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add packages/barcart/barcart/distance.py packages/barcart/barcart/em_learner.py
git commit -m "perf: support sparse emd inputs and float32 em outputs"
```

Plan complete and saved to `docs/plans/2025-12-25-em-sparse-float32.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
