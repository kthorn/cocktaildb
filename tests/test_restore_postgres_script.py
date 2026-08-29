import fcntl
import os
import subprocess

SCRIPT = "scripts/restore-postgres.sh"
BACKUP = "s3://cocktaildbbackups-123-prod/backup-2026-08-29_12-00-00.sql.gz"


def write_command(path, body):
    path.write_text(f"#!/bin/bash\nset -euo pipefail\n{body}")
    path.chmod(0o755)


def make_fake_commands(tmp_path):
    write_command(
        tmp_path / "ssh",
        'printf \'%s\\n\' "$*" > "$SSH_ARGS_CAPTURE"\n'
        'cat > "$SSH_STDIN_CAPTURE"\n'
        'if [[ "${EXECUTE_REMOTE:-}" == true ]]; then\n'
        '  bash "$SSH_STDIN_CAPTURE" "$TEST_BACKUP" "$TEST_BASE_URL"\n'
        "fi\n",
    )
    write_command(
        tmp_path / "aws",
        'echo "aws $*" >> "$COMMAND_LOG"\n'
        'destination="${@: -1}"\n'
        'if [[ "${FAIL_REMOTE:-}" == malformed ]]; then\n'
        "  printf 'SELECT 1;' | /usr/bin/gzip > \"$destination\"\n"
        "else\n"
        "  printf '%s\\n' '-- PostgreSQL database dump' 'SELECT 1;' | /usr/bin/gzip > \"$destination\"\n"
        "fi\n",
    )
    write_command(
        tmp_path / "systemctl",
        'echo "systemctl $*" >> "$COMMAND_LOG"\n'
        'action="$1"\n'
        "shift\n"
        'if [[ "$action" == is-active ]]; then\n'
        '  unit="${@: -1}"\n'
        '  if [[ "${FAIL_REMOTE:-}" == timer-query && "$unit" == cocktaildb-analytics-debounce.timer ]]; then\n'
        "    exit 4\n"
        "  fi\n"
        '  [[ -e "$STATE_DIR/$unit.active" ]] || exit 3\n'
        'elif [[ "$action" == stop ]]; then\n'
        '  for unit in "$@"; do\n'
        '    if [[ "${FAIL_REMOTE:-}" == timer-stop && "$unit" == cocktaildb-analytics-debounce.timer ]]; then\n'
        "      exit 1\n"
        "    fi\n"
        '    rm -f "$STATE_DIR/$unit.active"\n'
        "  done\n"
        'elif [[ "$action" == start ]]; then\n'
        '  for unit in "$@"; do\n'
        '    [[ "$unit" == *.timer ]] && touch "$STATE_DIR/$unit.active"\n'
        "  done\n"
        '  if [[ "$*" == *"cocktaildb-backup.service"* ]]; then\n'
        '    mkdir -p "$APP_HOME/backups"\n'
        "    printf 'safety' | /usr/bin/gzip > \"$APP_HOME/backups/backup-safety.sql.gz\"\n"
        "  fi\n"
        "fi\n",
    )
    write_command(
        tmp_path / "docker",
        'echo "docker $*" >> "$COMMAND_LOG"\n'
        'if [[ "$*" == *"stop api"* ]]; then\n'
        '  if [[ "${FAIL_REMOTE:-}" == stop && ! -e "$STATE_DIR/stop-failed" ]]; then\n'
        '    touch "$STATE_DIR/stop-failed"\n'
        "    exit 1\n"
        "  fi\n"
        '  rm -f "$STATE_DIR/api.active"\n'
        'elif [[ "$*" == *"up -d api"* ]]; then\n'
        '  touch "$STATE_DIR/api.active"\n'
        'elif [[ "$*" == *"ps --status running --services api"* && "${FAIL_REMOTE:-}" == verify ]]; then\n'
        "  exit 2\n"
        'elif [[ "$*" == *"ps --status running --services api"* && -e "$STATE_DIR/api.active" ]]; then\n'
        "  echo api\n"
        "fi\n",
    )
    write_command(
        tmp_path / "runuser",
        'echo "runuser $*" >> "$COMMAND_LOG"\n'
        'if [[ "$*" == *"psql -v ON_ERROR_STOP=1 cocktaildb"* ]]; then\n'
        "  cat >/dev/null\n"
        '  [[ "${FAIL_REMOTE:-}" != restore ]]\n'
        "fi\n",
    )
    write_command(
        tmp_path / "curl",
        'echo "curl $*" >> "$COMMAND_LOG"\n'
        'if [[ "${FAIL_REMOTE:-}" == delayed-health ]]; then\n'
        '  count=$(cat "$STATE_DIR/curl-count" 2>/dev/null || echo 0)\n'
        "  ((++count))\n"
        '  echo "$count" > "$STATE_DIR/curl-count"\n'
        "  [[ $count -gt 2 ]]\n"
        "else\n"
        '  [[ "${FAIL_REMOTE:-}" != health ]]\n'
        "fi\n",
    )
    write_command(tmp_path / "sleep", 'echo "sleep $*" >> "$COMMAND_LOG"\n')


def run_restore(
    tmp_path, confirmation, *, execute_remote=False, fail_remote="", backup=BACKUP
):
    make_fake_commands(tmp_path)
    app_home = tmp_path / "app"
    app_home.mkdir(exist_ok=True)
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "api.active").touch()
    (state_dir / "cocktaildb-backup.timer.active").touch()
    (state_dir / "cocktaildb-analytics-debounce.timer.active").touch()

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "SSH_ARGS_CAPTURE": str(tmp_path / "ssh-args"),
            "SSH_STDIN_CAPTURE": str(tmp_path / "ssh-stdin"),
            "EXECUTE_REMOTE": str(execute_remote).lower(),
            "TEST_BACKUP": backup,
            "TEST_BASE_URL": "https://mixology.tools",
            "APP_HOME": str(app_home),
            "LOCK_FILE": str(tmp_path / "restore.lock"),
            "RESTORE_DIR": str(tmp_path),
            "COMMAND_LOG": str(tmp_path / "commands"),
            "STATE_DIR": str(state_dir),
            "FAIL_REMOTE": fail_remote,
        }
    )
    return subprocess.run(
        ["bash", SCRIPT, "prod", backup],
        input=confirmation,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_restore_requires_exact_environment_confirmation(tmp_path):
    result = run_restore(tmp_path, "yes\n")

    assert result.returncode != 0
    assert "Restore cancelled" in result.stdout
    assert not (tmp_path / "ssh-args").exists()


def test_restore_rejects_backup_outside_environment_bucket(tmp_path):
    result = run_restore(
        tmp_path,
        "RESTORE prod\n",
        backup="s3://untrusted-bucket/backup-2026-08-29.sql.gz",
    )

    assert result.returncode == 2
    assert not (tmp_path / "ssh-args").exists()


def test_restore_rejects_non_dump_before_stopping_writers(tmp_path):
    result = run_restore(
        tmp_path, "RESTORE prod\n", execute_remote=True, fail_remote="malformed"
    )

    assert result.returncode != 0
    commands = (tmp_path / "commands").read_text()
    assert "stop api" not in commands
    assert "systemctl stop" not in commands


def test_restore_success_runs_safety_flow_and_database_check(tmp_path):
    result = run_restore(tmp_path, "RESTORE prod\n", execute_remote=True)

    assert result.returncode == 0
    assert "Restore completed" in result.stdout
    commands = (tmp_path / "commands").read_text()
    steps = [
        "aws s3 cp",
        "systemctl start cocktaildb-backup.service",
        "docker compose -f docker-compose.yml -f docker-compose.prod.yml stop api",
        "systemctl stop cocktaildb-analytics.timer cocktaildb-analytics-debounce.timer",
        "runuser -u postgres -- dropdb",
        "runuser -u postgres -- createdb",
        "runuser -u postgres -- psql -v ON_ERROR_STOP=1 cocktaildb",
        "docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api",
        "curl --max-time 30 --fail --silent --show-error https://mixology.tools/api/v1/stats",
        "systemctl start cocktaildb-analytics-debounce.timer cocktaildb-backup.timer",
    ]
    positions = [commands.index(step) for step in steps]
    assert positions == sorted(positions)


def test_restore_retries_until_api_and_database_are_ready(tmp_path):
    result = run_restore(
        tmp_path, "RESTORE prod\n", execute_remote=True, fail_remote="delayed-health"
    )

    assert result.returncode == 0
    commands = (tmp_path / "commands").read_text()
    assert commands.count("curl ") == 4
    assert commands.count("sleep 5") == 2


def test_restore_aborts_before_shutdown_when_timer_state_is_unknown(tmp_path):
    result = run_restore(
        tmp_path, "RESTORE prod\n", execute_remote=True, fail_remote="timer-query"
    )

    assert result.returncode != 0
    commands = (tmp_path / "commands").read_text()
    assert "stop api" not in commands
    assert (
        "Could not determine whether cocktaildb-analytics-debounce.timer is active"
        in result.stderr
    )


def test_restore_failure_keeps_api_and_background_writers_stopped(tmp_path):
    result = run_restore(
        tmp_path, "RESTORE prod\n", execute_remote=True, fail_remote="restore"
    )

    assert result.returncode != 0
    assert "API and analytics remain stopped" in result.stderr
    assert "Safety backup:" in result.stdout
    commands = (tmp_path / "commands").read_text()
    assert "up -d api" not in commands
    assert "systemctl start cocktaildb-analytics-debounce.timer" not in commands
    assert commands.count("stop api") >= 2


def test_restore_retries_api_stop_during_cleanup(tmp_path):
    result = run_restore(
        tmp_path, "RESTORE prod\n", execute_remote=True, fail_remote="stop"
    )

    assert result.returncode != 0
    commands = (tmp_path / "commands").read_text()
    assert commands.count("stop api") == 2
    assert "API and analytics remain stopped" in result.stderr


def test_restore_escalates_when_writer_shutdown_cannot_be_verified(tmp_path):
    result = run_restore(
        tmp_path, "RESTORE prod\n", execute_remote=True, fail_remote="timer-stop"
    )

    assert result.returncode != 0
    assert (
        "CRITICAL: could not verify that all database writers stopped" in result.stderr
    )
    assert "API and analytics remain stopped" not in result.stderr


def test_restore_escalates_when_writer_state_query_fails(tmp_path):
    result = run_restore(
        tmp_path, "RESTORE prod\n", execute_remote=True, fail_remote="verify"
    )

    assert result.returncode != 0
    assert (
        "CRITICAL: could not verify that all database writers stopped" in result.stderr
    )
    assert "API and analytics remain stopped" not in result.stderr


def test_restore_refuses_overlapping_run(tmp_path):
    lock_path = tmp_path / "restore.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_restore(tmp_path, "RESTORE prod\n", execute_remote=True)

    assert result.returncode != 0
    assert "Another restore is already running" in result.stderr
    assert not (tmp_path / "commands").exists()
    assert not list(tmp_path.glob("cocktaildb-restore.*.sql.gz"))
