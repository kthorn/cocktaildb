# TestClient AnyIO Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade FastAPI/Starlette/AnyIO/HTTPX stack to restore TestClient functionality in the cocktaildb environment.

**Architecture:** Update dependency pins in `api/requirements.txt`, reinstall test dependencies, and verify TestClient-based analytics test no longer hangs. Keep changes minimal to avoid unrelated behavior changes.

**Tech Stack:** Python, FastAPI, Starlette, AnyIO, HTTPX, pytest

### Task 1: Capture the failing behavior in a focused test run

**Files:**
- Modify: none
- Test: `tests/test_analytics_em_distances_download.py`

**Step 1: Run the failing test to verify the hang**

Run: `python -m pytest tests/test_analytics_em_distances_download.py::test_download_em_distance_matrix -v`
Expected: timeout/hang (no completion)

**Step 2: Document the exact failure mode**

Run: `python - <<'PY'\nfrom starlette.applications import Starlette\nfrom starlette.responses import PlainTextResponse\nfrom starlette.testclient import TestClient\n\napp = Starlette()\n\n@app.route('/hello')\nasync def hello(request):\n    return PlainTextResponse('hi')\n\nclient = TestClient(app)\nresp = client.get('/hello')\nprint('status', resp.status_code, resp.text)\nPY`
Expected: hang/timeout

### Task 2: Update dependency pins to the agreed versions

**Files:**
- Modify: `api/requirements.txt`

**Step 1: Update versions**

Set:
- `fastapi==0.111.1`
- `uvicorn[standard]==0.30.1`
- Add `httpx==0.27.0` (explicit pin for TestClient stack)

**Step 2: Reinstall test dependencies**

Run: `python -m pip install -r requirements-test.txt`
Expected: successful install with updated versions

### Task 3: Verify TestClient works after upgrade

**Files:**
- Modify: none
- Test: `tests/test_analytics_em_distances_download.py`

**Step 1: Re-run the minimal TestClient reproduction**

Run: `python - <<'PY'\nfrom starlette.applications import Starlette\nfrom starlette.responses import PlainTextResponse\nfrom starlette.testclient import TestClient\n\napp = Starlette()\n\n@app.route('/hello')\nasync def hello(request):\n    return PlainTextResponse('hi')\n\nclient = TestClient(app)\nresp = client.get('/hello')\nprint('status', resp.status_code, resp.text)\nPY`
Expected: `status 200 hi`

**Step 2: Re-run the analytics test**

Run: `python -m pytest tests/test_analytics_em_distances_download.py::test_download_em_distance_matrix -v`
Expected: PASS

**Step 3: Commit the dependency changes**

Run:
```
git add api/requirements.txt

git commit -m "chore: bump fastapi stack for testclient"
```
