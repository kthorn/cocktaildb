import fcntl
import gzip
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
  backup)
    touch "$STATE_DIR/backup_verified"
    ;;
  build)
    touch "$STATE_DIR/previous_image_preserved" "$STATE_DIR/new_image_built"
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
  *)
    printf 'unexpected operation: %s\n' "$operation" >&2
    exit 64
    ;;
esac
""",
    )
    for operation in (
        "pending",
        "backup",
        "build",
        "stop",
        "verify_stopped",
        "migrate",
        "verify_recorded",
        "verify_parity",
        "start",
        "health",
        "stop_new",
        "publish",
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
    (app_home / "scripts").mkdir()
    (app_home / "backups").mkdir()
    (release_root / "migrations" / MIGRATION_15).write_text("-- migration\n")
    (release_root / "web" / "js" / "config.js").write_text("// config\n")
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
        "DOCKER_BIN": "/bin/false",
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
        app_home / "scripts",
        app_home / "backups",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (release_root / "migrations" / MIGRATION_15).write_text("-- migration\n")
    (release_root / "web" / "js" / "config.js").write_text("// config\n")
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
        "DOCKER_BIN": "/bin/false",
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


def _run_default_operations(tmp_path: Path, docker_body: str, curl_body: str = ""):
    app_home = tmp_path / "app"
    release_root = app_home / "releases" / "release"
    bin_dir = tmp_path / "bin"
    for directory in (
        release_root / "migrations",
        release_root / "web" / "js",
        release_root / "api",
        app_home / "scripts",
        app_home / "backups",
        bin_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (release_root / "migrations" / MIGRATION_15).write_text("-- migration\n")
    (release_root / "web" / "js" / "config.js").write_text("// config\n")
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


def test_first_cutover_orders_writer_shutdown_migration_readiness_and_publication(
    cutover_harness,
):
    run, state = cutover_harness

    result = run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would apply: 16_future.sql" in (state / "pending_output").read_text()
    assert _events(state) == [
        "pending",
        "backup",
        "build",
        "stop",
        "verify_stopped",
        "migrate",
        "verify_recorded",
        "verify_parity",
        "start",
        "health",
        "publish",
    ]
    assert (state / "previous_image_preserved").exists()
    assert (state / "group_write").exists(), (
        "the last pre-shutdown request was not backfilled"
    )
    assert (state / "new_api_running").exists()
    assert (state / "frontend_published").exists()
    assert not (state / "old_frontend_served").exists()


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
        ("backup", "backup", True, False, False),
        ("build", "build", True, False, False),
        ("stop", "stop", True, False, False),
        ("migrate", "migrate", False, False, False),
        ("verify_recorded", "verify_recorded", False, False, False),
        ("verify_parity", "verify_parity", False, False, False),
        ("start", "stop_new", False, False, True),
        ("health", "stop_new", False, False, True),
        ("publish", "publish", False, True, False),
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
    assert (state / "old_frontend_served").exists()
    assert not (state / "frontend_published").exists()
    assert "Cutover failed during" in result.stdout

    events = _events(state)
    if failed_phase in {
        "backup",
        "build",
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
    frozen_release = playbook[0]["pre_tasks"][0]["ansible.builtin.set_fact"]

    assert "deployment_release_id" in frozen_release
    lifecycle_lock = playbook[0]["pre_tasks"][1]
    assert lifecycle_lock["name"] == "Acquire deployment lifecycle lock"
    assert lifecycle_lock["ansible.builtin.command"]["argv"] == [
        "mkdir",
        "/var/lock/cocktaildb-deploy-ansible.lock",
    ]
    cutover_tasks = [task for task in tasks if "deploy-cutover.sh" in str(task)]
    assert cutover_tasks, "normal deploy playbook does not invoke the cutover gate"
    assert "Restart API" not in {handler["name"] for handler in handlers}
    assert all("Restart Caddy" not in task.get("notify", []) for task in tasks)

    frontend_sync = next(
        task for task in tasks if task["name"] == "Stage frontend code"
    )
    config = next(task for task in tasks if task["name"] == "Stage frontend config.js")
    assert "release_web_root" in frontend_sync["ansible.builtin.synchronize"]["dest"]
    assert "release_web_root" in config["ansible.builtin.template"]["dest"]
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
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CALLS": str(calls),
            "COCKTAILDB_DB_PASSWORD": "test-only",
        }
    )

    result = subprocess.run(
        ["bash", "scripts/deploy-ec2.sh", "dev"],
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
