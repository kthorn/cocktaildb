import fcntl
import gzip
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CUTOVER = ROOT / "infrastructure" / "scripts" / "deploy-cutover.sh"
ANSIBLE = shutil.which("ansible-playbook") or str(
    Path(sys.executable).with_name("ansible-playbook")
)
MIGRATION_15 = "15_migration_add_user_groups.sql"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _write_frontend_artifact(path: Path) -> None:
    assets = path / "web" / "assets"
    assets.mkdir(parents=True)
    (assets / "test-A.js").write_text("export default 1;\n")
    (path / "web" / "index.html").write_text("<!doctype html>\n")
    (path / "manifest.json").write_text(
        json.dumps({"index.html": {"file": "assets/test-A.js"}})
    )
    (path / "asset-inventory.json").write_text(
        json.dumps({"version": 1, "files": ["test-A.js"]})
    )


@pytest.fixture
def cutover_harness(tmp_path):
    app_home = tmp_path / "app"
    release_root = app_home / "releases" / "test-release"
    state = tmp_path / "state"
    ops = tmp_path / "ops"
    served_web = app_home / "web"
    for directory in (
        release_root / "migrations",
        release_root / "web" / "js",
        state,
        ops,
        served_web,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    (release_root / "migrations" / MIGRATION_15).write_text("-- staged migration\n")
    (release_root / "web" / "js" / "config.js").write_text("// staged config\n")
    (served_web / "version.txt").write_text("old frontend\n")
    (state / "old_api_running").touch()
    (state / "old_frontend_served").touch()
    # Models a request that commits immediately before the graceful writer stop.
    (state / "request_in_flight").touch()

    dispatcher = ops / "operation"
    _write_executable(
        dispatcher,
        """#!/bin/bash
set -euo pipefail
operation=$(basename "$0")
printf '%s\n' "$operation" >> "$STATE_DIR/events"

if [[ "${FAIL_PHASE:-}" == "$operation" ]]; then
  exit 42
fi

case "$operation" in
  pending)
    {
      if [[ "${MIGRATION_15_PENDING:-true}" == true ]]; then
        printf 'Would apply: 15_migration_add_user_groups.sql\n'
      fi
      printf 'Would apply: 16_future.sql\n'
    } | tee "$STATE_DIR/pending_output"
    ;;
  validate_frontend)
    touch "$STATE_DIR/frontend_validated"
    ;;
  cleanup)
    ;;
  backup)
    touch "$STATE_DIR/backup_verified"
    ;;
  build)
    touch "$STATE_DIR/previous_image_preserved" "$STATE_DIR/new_image_built"
    ;;
  begin)
    touch "$STATE_DIR/frontend_pending"
    ;;
  assets)
    test -f "$STATE_DIR/frontend_pending"
    touch "$STATE_DIR/frontend_assets_published"
    ;;
  stop)
    if [[ -f "$STATE_DIR/request_in_flight" ]]; then
      mv "$STATE_DIR/request_in_flight" "$STATE_DIR/legacy_write"
    fi
    rm -f "$STATE_DIR/old_api_running"
    touch "$STATE_DIR/old_api_stopped"
    ;;
  verify_stopped)
    test ! -f "$STATE_DIR/old_api_running"
    ;;
  migrate)
    test ! -f "$STATE_DIR/old_api_running"
    touch "$STATE_DIR/migrated" "$STATE_DIR/migration_recorded"
    if [[ -f "$STATE_DIR/legacy_write" ]]; then
      cp "$STATE_DIR/legacy_write" "$STATE_DIR/group_write"
    fi
    ;;
  verify_recorded)
    test -f "$STATE_DIR/migration_recorded"
    ;;
  verify_parity)
    test -f "$STATE_DIR/legacy_write"
    test -f "$STATE_DIR/group_write"
    touch "$STATE_DIR/parity_verified"
    ;;
  start)
    test -f "$STATE_DIR/migration_recorded"
    touch "$STATE_DIR/new_api_running"
    ;;
  health)
    test -f "$STATE_DIR/new_api_running"
    touch "$STATE_DIR/readiness_verified"
    ;;
  stop_new)
    rm -f "$STATE_DIR/new_api_running"
    touch "$STATE_DIR/new_api_stopped"
    ;;
  publish)
    test -f "$STATE_DIR/readiness_verified"
    rm -f "$STATE_DIR/old_frontend_served"
    touch "$STATE_DIR/frontend_published"
    ;;
  smoke)
    test -f "$STATE_DIR/frontend_published"
    touch "$STATE_DIR/frontend_smoke_verified"
    ;;
  commit)
    test -f "$STATE_DIR/frontend_smoke_verified"
    rm -f "$STATE_DIR/frontend_pending"
    touch "$STATE_DIR/frontend_state_committed"
    ;;
  verify_prune_identity)
    test -f "$STATE_DIR/frontend_state_committed"
    ;;
  prune)
    test -f "$STATE_DIR/frontend_state_committed"
    touch "$STATE_DIR/frontend_pruned"
    ;;
  *)
    printf 'unexpected operation: %s\n' "$operation" >&2
    exit 64
    ;;
esac
""",
    )
    for operation in (
        "pending",
        "validate_frontend",
        "cleanup",
        "backup",
        "build",
        "begin",
        "assets",
        "stop",
        "verify_stopped",
        "migrate",
        "verify_recorded",
        "verify_parity",
        "start",
        "health",
        "stop_new",
        "publish",
        "smoke",
        "commit",
        "verify_prune_identity",
        "prune",
    ):
        (ops / operation).symlink_to(dispatcher)

    playbook = tmp_path / "cutover.yml"
    playbook.write_text(
        f"""---
- name: Exercise the production cutover helper locally
  hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Run cutover
      ansible.builtin.command:
        argv:
          - /bin/bash
          - {CUTOVER}
      environment:
        APP_HOME: {app_home}
        RELEASE_ROOT: {release_root}
        SERVED_WEB: {served_web}
        CUTOVER_OPS_DIR: {ops}
        STATE_DIR: {state}
        DEPLOY_LOCK_FILE: {tmp_path / "deploy.lock"}
        RELEASE_ID: test-release
        APP_ENV: prod
        MIGRATION_15_PENDING: "{{{{ migration_15_pending | default('true') }}}}"
        FAIL_PHASE: "{{{{ fail_phase | default('') }}}}"
"""
    )

    def run(*, pending=True, fail_phase=None):
        extra_vars = [f"migration_15_pending={'true' if pending else 'false'}"]
        if fail_phase:
            extra_vars.append(f"fail_phase={fail_phase}")
        env = os.environ.copy()
        env.update(
            {
                "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
                "ANSIBLE_REMOTE_TEMP": str(tmp_path / "ansible-remote"),
            }
        )
        return subprocess.run(
            [ANSIBLE, "-i", "localhost,", str(playbook), "-e", " ".join(extra_vars)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    return run, state


def _events(state: Path) -> list[str]:
    event_file = state / "events"
    return event_file.read_text().splitlines() if event_file.exists() else []


def test_failed_backup_command_cannot_fall_through_to_an_older_archive(tmp_path):
    app_home = tmp_path / "app"
    release_root = app_home / "releases" / "release"
    (release_root / "migrations").mkdir(parents=True)
    (release_root / "web" / "js").mkdir(parents=True)
    (release_root / "web" / "assets").mkdir(parents=True)
    (app_home / "scripts").mkdir()
    (app_home / "backups").mkdir()
    (release_root / "migrations" / MIGRATION_15).write_text("-- migration\n")
    (release_root / "web" / "js" / "config.js").write_text("// config\n")
    (release_root / "web" / "assets" / "test-A.js").write_text("export default 1;\n")
    (release_root / "manifest.json").write_text(
        json.dumps({"index.html": {"file": "assets/test-A.js"}})
    )
    (release_root / "asset-inventory.json").write_text(
        json.dumps({"version": 1, "files": ["test-A.js"]})
    )
    (app_home / ".env").write_text(
        "DB_HOST=localhost\nDB_PORT=5432\nDB_USER=test\nDB_PASSWORD=test\nDB_NAME=test\n"
    )
    with gzip.open(app_home / "backups" / "backup-old.sql.gz", "wb") as backup:
        backup.write(b"old backup")
    _write_executable(
        app_home / "scripts" / "run-migrations.sh",
        "#!/bin/sh\nprintf 'Would apply: 15_migration_add_user_groups.sql\\n'\n",
    )
    _write_executable(
        app_home / "scripts" / "backup-postgres.sh", "#!/bin/sh\nexit 42\n"
    )
    env = {
        **os.environ,
        "APP_HOME": str(app_home),
        "RELEASE_ROOT": str(release_root),
        "DEPLOY_LOCK_FILE": str(tmp_path / "deploy.lock"),
        "DOCKER_BIN": "/bin/true",
        "PYTHON_BIN": sys.executable,
        "FRONTEND_RELEASE_SCRIPT": str(
            ROOT / "infrastructure" / "scripts" / "frontend-release.py"
        ),
    }

    result = subprocess.run(
        ["bash", str(CUTOVER)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Cutover failed during backup" in result.stdout
    assert "CUTOVER phase=build" not in result.stdout


def test_corrupt_new_backup_stops_before_build(tmp_path):
    app_home = tmp_path / "app"
    release_root = app_home / "releases" / "release"
    for directory in (
        release_root / "migrations",
        release_root / "web" / "js",
        release_root / "web" / "assets",
        app_home / "scripts",
        app_home / "backups",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (release_root / "migrations" / MIGRATION_15).write_text("-- migration\n")
    (release_root / "web" / "js" / "config.js").write_text("// config\n")
    (release_root / "web" / "assets" / "test-A.js").write_text("export default 1;\n")
    (release_root / "manifest.json").write_text(
        json.dumps({"index.html": {"file": "assets/test-A.js"}})
    )
    (release_root / "asset-inventory.json").write_text(
        json.dumps({"version": 1, "files": ["test-A.js"]})
    )
    (app_home / ".env").write_text(
        "DB_HOST=localhost\nDB_PORT=5432\nDB_USER=test\nDB_PASSWORD=test\nDB_NAME=test\n"
    )
    _write_executable(
        app_home / "scripts" / "run-migrations.sh",
        "#!/bin/sh\nprintf 'Would apply: 15_migration_add_user_groups.sql\\n'\n",
    )
    _write_executable(
        app_home / "scripts" / "backup-postgres.sh",
        "#!/bin/sh\nprintf 'not gzip' > \"$BACKUP_DIR/backup-new.sql.gz\"\n",
    )
    env = {
        **os.environ,
        "APP_HOME": str(app_home),
        "RELEASE_ROOT": str(release_root),
        "DEPLOY_LOCK_FILE": str(tmp_path / "deploy.lock"),
        "DOCKER_BIN": "/bin/true",
        "PYTHON_BIN": sys.executable,
        "FRONTEND_RELEASE_SCRIPT": str(
            ROOT / "infrastructure" / "scripts" / "frontend-release.py"
        ),
    }

    result = subprocess.run(
        ["bash", str(CUTOVER)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Cutover failed during backup" in result.stdout
    assert "CUTOVER phase=build" not in result.stdout


def _run_default_operations(
    tmp_path: Path,
    docker_body: str,
    curl_body: str = "",
    *,
    gate_image_id: str = "sha256:current",
):
    app_home = tmp_path / "app"
    release_root = app_home / "releases" / "release"
    bin_dir = tmp_path / "bin"
    for directory in (
        release_root / "migrations",
        release_root / "web" / "js",
        release_root / "web" / "assets",
        release_root / "api",
        app_home / "scripts",
        app_home / "backups",
        bin_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (release_root / "migrations" / MIGRATION_15).write_text("-- migration\n")
    (release_root / "web" / "js" / "config.js").write_text("// config\n")
    (release_root / "web" / "assets" / "test-A.js").write_text("export default 1;\n")
    (release_root / "manifest.json").write_text(
        json.dumps({"index.html": {"file": "assets/test-A.js"}})
    )
    (release_root / "asset-inventory.json").write_text(
        json.dumps({"version": 1, "files": ["test-A.js"]})
    )
    (release_root / "api" / "Dockerfile.prod").write_text("FROM scratch\n")
    (app_home / ".env").write_text(
        "DB_HOST=localhost\nDB_PORT=5432\nDB_USER=test\nDB_PASSWORD=test\nDB_NAME=test\n"
    )
    _write_executable(
        app_home / "scripts" / "run-migrations.sh",
        """#!/bin/bash
if [[ "$*" == *--dry-run* ]]; then
  printf 'Would apply: 16_future.sql\n'
fi
""",
    )
    _write_executable(
        app_home / "scripts" / "backup-postgres.sh",
        """#!/bin/bash
mkdir -p "$BACKUP_DIR"
printf 'new backup' | gzip > "$BACKUP_DIR/backup-new.sql.gz"
""",
    )
    docker_calls = tmp_path / "docker-calls"
    docker = bin_dir / "docker"
    _write_executable(
        docker,
        f"""#!/bin/bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_CALLS"
if [[ "${{FRONTEND_GATE:-}}" == true && -e "$APP_HOME/web/js/config.js" ]]; then
  if [[ "$*" == *" ps -q api"* ]]; then
    printf 'api-container\\n'
    exit 0
  elif [[ "$1" == inspect && "$3" == '{{{{.Config.Image}}}}' ]]; then
    printf 'cocktaildb-api:release-release\\n'
    exit 0
  elif [[ "$1" == inspect && "$3" == '{{{{.Image}}}}' ]]; then
    printf '%s\\n' "$FRONTEND_GATE_IMAGE_ID"
    exit 0
  elif [[ "$1" == image && "$2" == inspect ]]; then
    printf 'sha256:current\\n'
    exit 0
  fi
fi
{docker_body}
""",
    )
    psql = bin_dir / "psql"
    _write_executable(psql, "#!/bin/sh\nprintf 't\\n'\n")
    curl_bin = "/bin/true"
    if curl_body:
        curl = bin_dir / "curl"
        _write_executable(
            curl,
            f"""#!/bin/bash
printf 'curl %s\n' "$*" >> "$DOCKER_CALLS"
{curl_body}
""",
        )
        curl_bin = str(curl)
    env = {
        **os.environ,
        "APP_HOME": str(app_home),
        "RELEASE_ROOT": str(release_root),
        "DEPLOY_LOCK_FILE": str(tmp_path / "deploy.lock"),
        "DOCKER_BIN": str(docker),
        "PSQL_BIN": str(psql),
        "CURL_BIN": curl_bin,
        "DOCKER_CALLS": str(docker_calls),
        "RELEASE_ID": "release",
        "PYTHON_BIN": sys.executable,
        "FRONTEND_RELEASE_SCRIPT": str(
            ROOT / "infrastructure" / "scripts" / "frontend-release.py"
        ),
        "SMOKE_TEST_BIN": "/bin/true",
        "FRONTEND_GATE": "true",
        "FRONTEND_GATE_IMAGE_ID": gate_image_id,
    }
    result = subprocess.run(
        ["bash", str(CUTOVER)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    calls = docker_calls.read_text().splitlines() if docker_calls.exists() else []
    return result, calls


def test_docker_cleanup_is_conservative_and_surrounds_deployment(tmp_path):
    result, calls = _run_default_operations(tmp_path, "exit 0")

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls[:2] == ["image prune --force", "builder prune --force"]
    assert calls[-2:] == ["image prune --force", "builder prune --force"]
    assert sum("prune" in call for call in calls) == 4
    assert (tmp_path / "app" / "web" / "js" / "config.js").exists()


@pytest.mark.parametrize("command", ["image prune", "builder prune"])
@pytest.mark.parametrize("after_publication", [False, True])
def test_docker_cleanup_failures_do_not_stop_a_healthy_release(
    tmp_path, command, after_publication
):
    condition = '[[ -f "$APP_HOME/web/js/config.js" ]]' if after_publication else "true"
    result, calls = _run_default_operations(
        tmp_path,
        f'''if [[ "$1 $2" == "{command}" ]] && {condition}; then
  exit 42
fi
''',
    )

    assert result.returncode != 0
    if after_publication:
        assert (
            "Release is deployed, but Docker artifact cleanup failed" in result.stdout
        )
        assert (tmp_path / "app" / "web" / "js" / "config.js").exists()
        assert sum(" stop " in f" {call} " for call in calls) == 1
    else:
        assert "Cutover failed during cleanup" in result.stdout
        assert not any(call.startswith("build ") for call in calls)
        assert not any(" stop " in f" {call} " for call in calls)


def test_failed_previous_image_tag_stops_before_build(tmp_path):
    result, calls = _run_default_operations(
        tmp_path,
        """if [[ "$*" == *" ps -q api" ]]; then
  printf 'old-container\n'
elif [[ "$1" == inspect ]]; then
  printf 'old-image\n'
elif [[ "$1 $2" == "image tag" ]]; then
  exit 42
fi
""",
    )

    assert result.returncode != 0
    assert "Cutover failed during build" in result.stdout
    assert not any(call.startswith("build ") for call in calls)


def test_failed_release_image_tag_does_not_fall_through_to_api_start(tmp_path):
    result, calls = _run_default_operations(
        tmp_path,
        """if [[ "$*" == *"--status running"* ]]; then
  exit 0
elif [[ "$*" == *" ps -q api" ]]; then
  printf 'old-container\n'
elif [[ "$1" == inspect ]]; then
  printf 'old-image\n'
elif [[ "$1 $2" == "image tag" && "$4" == "cocktaildb-api:latest" ]]; then
  exit 42
fi
""",
    )

    assert result.returncode != 0
    assert "Cutover failed during start" in result.stdout
    assert not any(" up " in f" {call} " for call in calls)
    assert any(" stop " in f" {call} " for call in calls), (
        "a possibly started new API was not stopped"
    )


def test_readiness_calls_have_per_attempt_wall_clock_timeouts(tmp_path):
    result, calls = _run_default_operations(
        tmp_path,
        """if [[ "$*" == *"--status running"* ]]; then
  exit 0
elif [[ "$*" == *" ps -q api" ]]; then
  printf 'old-container\n'
elif [[ "$1" == inspect ]]; then
  printf 'old-image\n'
fi
""",
        "exit 0",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    curl_call = next(call for call in calls if call.startswith("curl "))
    assert "--connect-timeout 2" in curl_call
    assert "--max-time 5" in curl_call


def test_cleanup_retry_gate_rejects_committed_api_image_id_drift(tmp_path):
    result, _ = _run_default_operations(
        tmp_path, "exit 0", gate_image_id="sha256:wrong"
    )

    assert result.returncode != 0
    assert "Committed API image ID does not match expected image" in result.stdout
    assert "CUTOVER phase=frontend-prune\n" not in result.stdout


def test_first_cutover_orders_writer_shutdown_migration_readiness_and_publication(
    cutover_harness,
):
    run, state = cutover_harness

    result = run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would apply: 16_future.sql" in (state / "pending_output").read_text()
    assert _events(state) == [
        "pending",
        "validate_frontend",
        "cleanup",
        "backup",
        "build",
        "begin",
        "assets",
        "stop",
        "verify_stopped",
        "migrate",
        "verify_recorded",
        "verify_parity",
        "start",
        "health",
        "publish",
        "smoke",
        "commit",
        "verify_prune_identity",
        "prune",
        "cleanup",
    ]
    assert (state / "previous_image_preserved").exists()
    assert (state / "group_write").exists(), (
        "the last pre-shutdown request was not backfilled"
    )
    assert (state / "new_api_running").exists()
    assert (state / "frontend_published").exists()
    assert not (state / "old_frontend_served").exists()


def test_frontend_prune_failure_keeps_committed_release_running(cutover_harness):
    run, state = cutover_harness

    result = run(fail_phase="prune")

    assert result.returncode != 0
    assert _events(state)[-1] == "prune"
    assert (state / "new_api_running").exists()
    assert (state / "frontend_state_committed").exists()
    assert not (state / "new_api_stopped").exists()
    assert "frontend retention cleanup failed" in result.stdout


def test_frontend_prune_identity_failure_does_not_prune(cutover_harness):
    run, state = cutover_harness

    result = run(fail_phase="verify_prune_identity")

    assert result.returncode != 0
    assert _events(state)[-1] == "verify_prune_identity"
    assert "frontend retention cleanup identity verification failed" in result.stdout
    assert not (state / "frontend_pruned").exists()
    assert (state / "new_api_running").exists()


def test_unresolved_frontend_marker_blocks_preflight(cutover_harness):
    run, state = cutover_harness
    (state.parent / "app" / "frontend-pending.json").write_text("pending")

    result = run()

    assert result.returncode != 0
    assert not _events(state)
    assert "unresolved frontend publication marker blocks deployment" in result.stdout


def test_dangling_frontend_marker_blocks_before_any_mutation(cutover_harness):
    run, state = cutover_harness
    marker = state.parent / "app" / "frontend-pending.json"
    marker.symlink_to(state.parent / "missing-pending.json")

    result = run()

    assert result.returncode != 0
    assert not _events(state)
    assert "unresolved frontend publication marker blocks deployment" in result.stdout
    assert "CUTOVER phase=cleanup" not in result.stdout
    assert "CUTOVER phase=backup" not in result.stdout
    assert "CUTOVER phase=build" not in result.stdout


@pytest.mark.parametrize(
    "missing_path",
    [
        Path("migrations") / MIGRATION_15,
        Path("web/js/config.js"),
    ],
)
def test_staging_preflight_failure_leaves_old_release_running(
    cutover_harness, missing_path
):
    run, state = cutover_harness
    release_root = state.parent / "app" / "releases" / "test-release"
    (release_root / missing_path).unlink()

    result = run()

    assert result.returncode != 0
    assert not _events(state)
    assert (state / "old_api_running").exists()
    assert (state / "old_frontend_served").exists()
    assert "Cutover failed during preflight" in result.stdout


def test_repeat_release_skips_initial_legacy_parity(cutover_harness):
    run, state = cutover_harness

    result = run(pending=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "verify_parity" not in _events(state)
    assert _events(state).index("verify_recorded") < _events(state).index("start")


def test_failed_initial_parity_cannot_be_skipped_by_a_repeat_run(cutover_harness):
    run, state = cutover_harness

    first = run(fail_phase="verify_parity")
    assert first.returncode != 0

    second = run(pending=False)

    assert second.returncode == 0, second.stdout + second.stderr
    assert _events(state).count("verify_parity") == 2
    assert not (
        state.parent / "app" / "releases" / ".migration15-parity-required"
    ).exists()


def test_uncertain_migration_failure_requires_manual_recovery_before_replay(
    cutover_harness,
):
    run, state = cutover_harness

    first = run(fail_phase="migrate")
    assert first.returncode != 0
    events_before_retry = list(_events(state))

    second = run()

    assert second.returncode != 0
    assert _events(state) == events_before_retry + ["pending"]
    assert "must not be replayed" in second.stdout


def test_host_lock_rejects_an_overlapping_cutover(cutover_harness):
    run, state = cutover_harness
    lock_path = state.parent / "deploy.lock"
    lock_path.touch()

    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run()

    assert result.returncode != 0
    assert not _events(state)
    assert "Cutover failed during lock" in result.stdout


@pytest.mark.parametrize(
    ("failed_phase", "last_event", "old_running", "new_running", "new_stopped"),
    [
        ("validate_frontend", "validate_frontend", True, False, False),
        ("cleanup", "cleanup", True, False, False),
        ("backup", "backup", True, False, False),
        ("build", "build", True, False, False),
        ("begin", "begin", True, False, False),
        ("assets", "assets", True, False, False),
        ("stop", "stop", True, False, False),
        ("migrate", "migrate", False, False, False),
        ("verify_recorded", "verify_recorded", False, False, False),
        ("verify_parity", "verify_parity", False, False, False),
        ("start", "stop_new", False, False, True),
        ("health", "stop_new", False, False, True),
        ("publish", "publish", False, True, False),
        ("smoke", "smoke", False, True, False),
        ("commit", "commit", False, True, False),
    ],
)
def test_cutover_failure_states(
    cutover_harness, failed_phase, last_event, old_running, new_running, new_stopped
):
    run, state = cutover_harness

    result = run(fail_phase=failed_phase)

    assert result.returncode != 0
    assert _events(state)[-1] == last_event
    assert (state / "old_api_running").exists() is old_running
    assert (state / "new_api_running").exists() is new_running
    assert (state / "new_api_stopped").exists() is new_stopped
    assert (state / "old_frontend_served").exists() is (
        failed_phase not in {"smoke", "commit"}
    )
    assert (state / "frontend_published").exists() is (
        failed_phase in {"smoke", "commit"}
    )
    assert "Cutover failed during" in result.stdout

    events = _events(state)
    if failed_phase in {
        "validate_frontend",
        "backup",
        "build",
        "begin",
        "assets",
        "stop",
        "migrate",
        "verify_recorded",
        "verify_parity",
    }:
        assert "start" not in events
    if failed_phase in {"backup", "build", "stop"}:
        assert "migrate" not in events


def test_deploy_playbook_stages_frontend_and_has_no_restart_handlers():
    playbook_path = ROOT / "infrastructure" / "ansible" / "playbooks" / "deploy.yml"
    playbook = yaml.safe_load(playbook_path.read_text())
    tasks = playbook[0]["tasks"]
    handlers = playbook[0].get("handlers", [])
    frozen_release = next(
        task["ansible.builtin.set_fact"]
        for task in playbook[0]["pre_tasks"]
        if "ansible.builtin.set_fact" in task
    )

    assert "deployment_release_id" in frozen_release
    lifecycle_lock = next(
        task
        for task in playbook[0]["pre_tasks"]
        if task["name"] == "Acquire deployment lifecycle lock"
    )
    assert lifecycle_lock["name"] == "Acquire deployment lifecycle lock"
    assert lifecycle_lock["ansible.builtin.command"]["argv"] == [
        "mkdir",
        "/var/lock/cocktaildb-deploy-ansible.lock",
    ]
    cutover_tasks = [
        task
        for task in tasks
        if any(
            "deploy-cutover.sh" in str(argument)
            for argument in (
                (task.get("ansible.builtin.command") or {}).get("argv") or []
            )
        )
    ]
    assert cutover_tasks, "normal deploy playbook does not invoke the cutover gate"
    assert len(cutover_tasks) == 1, "the cutover gate must run exactly once"
    assert "Restart API" not in {handler["name"] for handler in handlers}
    assert all("Restart Caddy" not in task.get("notify", []) for task in tasks)

    artifact_validation = next(
        task
        for task in playbook[0]["pre_tasks"]
        if task["name"] == "Validate frontend artifact before deployment lock"
    )
    assert artifact_validation["ansible.builtin.command"]["argv"][-2:] == [
        "validate",
        "{{ frontend_artifact_dir }}",
    ]
    assert playbook[0]["pre_tasks"].index(artifact_validation) < playbook[0][
        "pre_tasks"
    ].index(lifecycle_lock)

    frontend_sync = next(
        task for task in tasks if task["name"] == "Stage frontend code"
    )
    frontend_sync_args = frontend_sync["ansible.builtin.synchronize"]
    config = next(task for task in tasks if task["name"] == "Stage frontend config.js")
    js_directory = next(
        task for task in tasks if task["name"] == "Create staged frontend js directory"
    )
    assert frontend_sync_args["src"] == "{{ frontend_artifact_dir }}/web/"
    assert frontend_sync_args["delete"] is True
    assert "release_web_root" in frontend_sync_args["dest"]
    assert "release_web_root" in config["ansible.builtin.template"]["dest"]
    assert tasks.index(js_directory) < tasks.index(config)

    api_sync = next(task for task in tasks if task["name"] == "Stage API code")
    api_manifest = next(
        task for task in tasks if task["name"] == "Stage API frontend manifest"
    )
    assert api_sync["ansible.builtin.synchronize"]["delete"] is True
    assert (
        api_manifest["ansible.builtin.copy"]["src"]
        == "{{ frontend_artifact_dir }}/manifest.json"
    )
    assert (
        api_manifest["ansible.builtin.copy"]["dest"]
        == "{{ release_root }}/api/frontend-manifest.json"
    )
    assert tasks.index(api_sync) < tasks.index(api_manifest)

    metadata = next(task for task in tasks if task["name"] == "Stage frontend metadata")
    assert metadata["ansible.builtin.copy"]["dest"] == "{{ release_root }}/{{ item }}"
    assert "release_web_root" not in metadata["ansible.builtin.copy"]["dest"]
    caddy_validation = next(
        task for task in tasks if task["name"] == "Validate staged Caddy configuration"
    )
    caddy_restart = next(task for task in tasks if task["name"] == "Restart Caddy")
    assert caddy_restart["ansible.builtin.systemd"]["state"] == "restarted"
    assert tasks.index(caddy_validation) < tasks.index(caddy_restart)
    assert tasks.index(caddy_restart) < tasks.index(cutover_tasks[0])
    assert tasks[-1]["name"] == "Release deployment lifecycle lock"

    syntax = subprocess.run(
        [ANSIBLE, "--syntax-check", str(playbook_path)],
        cwd=ROOT / "infrastructure" / "ansible",
        env={
            **os.environ,
            "ANSIBLE_LOCAL_TEMP": "/tmp/cocktaildb-ansible-local",
            "ANSIBLE_REMOTE_TEMP": "/tmp/cocktaildb-ansible-remote",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stdout + syntax.stderr


def test_deploy_wrapper_rejects_invalid_artifact_before_playbook(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _write_executable(
        bin_dir / "ansible-playbook",
        '#!/bin/sh\nprintf \'playbook %s\\n\' "$*" >> "$CALLS"\n',
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CALLS": str(calls),
            "COCKTAILDB_DB_PASSWORD": "test-only",
        }
    )

    result = subprocess.run(
        [
            "bash",
            "scripts/deploy-ec2.sh",
            "dev",
            "--frontend-artifact",
            str(tmp_path / "invalid-artifact"),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "frontend artifact error" in result.stderr
    assert not calls.exists()


def test_deploy_wrapper_consumes_existing_artifact_without_npm_rebuild(tmp_path):
    artifact = tmp_path / "artifact"
    _write_frontend_artifact(artifact)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _write_executable(
        bin_dir / "npm",
        '#!/bin/sh\nprintf \'npm %s\\n\' "$*" >> "$CALLS"\n',
    )
    _write_executable(
        bin_dir / "ansible-playbook",
        '#!/bin/sh\nprintf \'playbook %s\\n\' "$*" >> "$CALLS"\n',
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CALLS": str(calls),
            "COCKTAILDB_DB_PASSWORD": "test-only",
        }
    )

    result = subprocess.run(
        [
            "bash",
            "scripts/deploy-ec2.sh",
            "--frontend-artifact",
            str(artifact),
            "dev",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    logged = calls.read_text().splitlines()
    assert not any(line.startswith("npm ") for line in logged)
    assert any(f"frontend_artifact_dir={artifact.resolve()}" in line for line in logged)


def test_deploy_wrapper_builds_default_artifact_and_passes_absolute_dist(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _write_executable(
        bin_dir / "npm",
        """#!/bin/sh
set -eu
printf 'npm %s\\n' "$*" >> "$CALLS"
if [ "$*" = "run build" ]; then
  rm -rf dist
  mkdir -p dist/web/assets
  printf 'export default 1;\\n' > dist/web/assets/test-A.js
  printf '{\"index.html\":{\"file\":\"assets/test-A.js\"}}\\n' > dist/manifest.json
  printf '{\"version\":1,\"files\":[\"test-A.js\"]}\\n' > dist/asset-inventory.json
fi
""",
    )
    _write_executable(
        bin_dir / "ansible-playbook",
        """#!/bin/sh
printf 'playbook %s\\n' "$*" >> "$CALLS"
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CALLS": str(calls),
            "COCKTAILDB_DB_PASSWORD": "test-only",
        }
    )

    original_dist = ROOT / "dist"
    saved_dist = tmp_path / "saved-dist"
    if original_dist.exists():
        shutil.copytree(original_dist, saved_dist)
    try:
        result = subprocess.run(
            ["bash", "scripts/deploy-ec2.sh", "dev"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        shutil.rmtree(original_dist, ignore_errors=True)
        if saved_dist.exists():
            shutil.copytree(saved_dist, original_dist)

    assert result.returncode == 0, result.stdout + result.stderr
    logged = calls.read_text().splitlines()
    assert logged[:2] == ["npm ci", "npm run build"]
    assert any(f"frontend_artifact_dir={ROOT / 'dist'}" in line for line in logged[2:])


def _recovery_harness(
    tmp_path: Path,
    *,
    actual_image_id: str = "sha256:expected",
    served_matches: bool = True,
):
    app_home = tmp_path / "app"
    release_root = app_home / "releases" / "candidate"
    (release_root / "web").mkdir(parents=True)
    (release_root / "web" / "index.html").write_text("candidate")
    other_root = app_home / "releases" / "other" / "web"
    other_root.mkdir(parents=True)
    (other_root / "index.html").write_text("other")
    served = app_home / "web"
    served.parent.mkdir(parents=True, exist_ok=True)
    served.symlink_to(
        release_root / "web" if served_matches else other_root,
        target_is_directory=True,
    )
    (app_home / "frontend-pending.json").write_text("pending")
    ops = tmp_path / "ops"
    ops.mkdir()
    dispatcher = ops / "operation"
    _write_executable(
        dispatcher,
        """#!/bin/bash
set -euo pipefail
operation=$(basename "$0")
printf '%s\\n' "$operation" >> "$STATE_DIR/events"
case "$operation" in
  health|smoke|recover|verify_prune_identity|prune|cleanup) ;;
  *) printf 'unexpected operation: %s\\n' "$operation" >&2; exit 64 ;;
esac
""",
    )
    for operation in (
        "health",
        "smoke",
        "recover",
        "verify_prune_identity",
        "prune",
        "cleanup",
    ):
        (ops / operation).symlink_to(dispatcher)

    docker = tmp_path / "docker"
    _write_executable(
        docker,
        """#!/bin/bash
set -euo pipefail
printf '%s\\n' "$*" >> "$DOCKER_LOG"
if [[ "$*" == *" ps -q api"* ]]; then
  printf 'api-container\\n'
elif [[ "$1" == inspect && "$3" == '{{.Config.Image}}' ]]; then
  printf '%s\\n' "$RUNNING_IMAGE_TAG"
elif [[ "$1" == inspect && "$3" == '{{.Image}}' ]]; then
  printf '%s\\n' "$ACTUAL_IMAGE_ID"
elif [[ "$1" == image && "$2" == inspect ]]; then
  printf '%s\\n' "$EXPECTED_IMAGE_ID"
fi
""",
    )
    env = {
        **os.environ,
        "APP_HOME": str(app_home),
        "RELEASE_ROOT": str(release_root),
        "SERVED_WEB": str(served),
        "DEPLOY_LOCK_FILE": str(tmp_path / "deploy.lock"),
        "DOCKER_BIN": str(docker),
        "DOCKER_LOG": str(tmp_path / "docker.log"),
        "RUNNING_IMAGE_TAG": "cocktaildb-api:release-candidate",
        "ACTUAL_IMAGE_ID": actual_image_id,
        "EXPECTED_IMAGE_ID": "sha256:expected",
        "RELEASE_ID": "candidate",
        "CUTOVER_OPS_DIR": str(ops),
        "STATE_DIR": str(tmp_path / "state"),
    }
    Path(env["STATE_DIR"]).mkdir()
    return env, app_home, release_root


@pytest.mark.parametrize("actual_image_id", ["sha256:wrong"])
def test_recovery_rejects_active_api_image_id_mismatch(tmp_path, actual_image_id):
    env, _, _ = _recovery_harness(tmp_path, actual_image_id=actual_image_id)

    result = subprocess.run(
        [
            "bash",
            str(CUTOVER),
            "recover",
            env["RELEASE_ROOT"],
            env["RUNNING_IMAGE_TAG"],
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "image ID does not match" in result.stdout
    assert not (Path(env["STATE_DIR"]) / "events").exists()


def test_recovery_rejects_served_frontend_mismatch(tmp_path):
    env, _, _ = _recovery_harness(tmp_path, served_matches=False)

    result = subprocess.run(
        [
            "bash",
            str(CUTOVER),
            "recover",
            env["RELEASE_ROOT"],
            env["RUNNING_IMAGE_TAG"],
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Served frontend does not match pending candidate" in result.stdout
    assert not (Path(env["STATE_DIR"]) / "events").exists()


def test_recovery_reconciles_matching_api_and_frontend(tmp_path):
    env, _, _ = _recovery_harness(tmp_path)

    result = subprocess.run(
        [
            "bash",
            str(CUTOVER),
            "recover",
            env["RELEASE_ROOT"],
            env["RUNNING_IMAGE_TAG"],
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (Path(env["STATE_DIR"]) / "events").read_text().splitlines() == [
        "health",
        "smoke",
        "recover",
        "verify_prune_identity",
        "prune",
        "cleanup",
    ]
    assert "reconciled" in result.stdout


def test_recovery_diagnoses_dangling_pending_marker(tmp_path):
    env, app_home, _ = _recovery_harness(tmp_path)
    marker = app_home / "frontend-pending.json"
    marker.unlink()
    marker.symlink_to(tmp_path / "missing-pending.json")

    result = subprocess.run(
        [
            "bash",
            str(CUTOVER),
            "recover",
            env["RELEASE_ROOT"],
            env["RUNNING_IMAGE_TAG"],
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "dangling" in result.stdout
    assert "No frontend pending marker" not in result.stdout
    assert not (Path(env["STATE_DIR"]) / "events").exists()


def test_deploy_wrapper_uses_normal_playbook(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    _write_executable(
        bin_dir / "ansible-galaxy",
        '#!/bin/sh\nprintf \'galaxy %s\\n\' "$*" >> "$CALLS"\n',
    )
    _write_executable(
        bin_dir / "ansible-playbook",
        '#!/bin/sh\nprintf \'playbook %s\\n\' "$*" >> "$CALLS"\n',
    )
    artifact = tmp_path / "artifact"
    _write_frontend_artifact(artifact)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CALLS": str(calls),
            "COCKTAILDB_DB_PASSWORD": "test-only",
        }
    )

    result = subprocess.run(
        [
            "bash",
            "scripts/deploy-ec2.sh",
            "dev",
            "--frontend-artifact",
            str(artifact),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    logged = calls.read_text().splitlines()
    assert "-i inventory/dev.yml playbooks/deploy.yml -v" in logged[-1]
    assert "deployment_release_id=" in logged[-1]
