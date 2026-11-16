from __future__ import annotations

import csv
import gzip
import importlib.util
import io
import json
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "infrastructure" / "scripts" / "page-view-counts.py"

DAY = date(2026, 11, 13)
NOON = datetime(2026, 11, 13, 12, 0, tzinfo=UTC).timestamp()
NEXT_DAY_NOON = datetime(2026, 11, 14, 12, 0, tzinfo=UTC).timestamp()


@pytest.fixture
def pvc():
    spec = importlib.util.spec_from_file_location("page_view_counts", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(
    uri="/",
    status=200,
    method="GET",
    ua="Mozilla/5.0",
    ip="1.1.1.1",
    ts=NOON,
):
    headers = {} if ua is None else {"User-Agent": [ua]}
    return {
        "ts": ts,
        "status": status,
        "request": {
            "method": method,
            "uri": uri,
            "client_ip": ip,
            "remote_ip": ip,
            "headers": headers,
        },
    }


@pytest.mark.parametrize(
    "uri",
    ["/", "/index.html", "/search.html?q=gin", "/recipe/42", "/ingredient/gin"],
)
def test_is_page_view_accepts_pages(pvc, uri):
    assert pvc.is_page_view(_entry(uri=uri)) is True


@pytest.mark.parametrize(
    "uri",
    [
        "/api/v1/recipes",
        "/assets/app-abc.js",
        "/styles.css",
        "/logo.png",
        "/health",
        "/sitemap.xml",
    ],
)
def test_is_page_view_rejects_non_pages(pvc, uri):
    assert pvc.is_page_view(_entry(uri=uri)) is False


def test_is_page_view_counts_304(pvc):
    assert pvc.is_page_view(_entry(status=304)) is True
    assert pvc.is_page_view(_entry(status=404)) is False
    assert pvc.is_page_view(_entry(status=301)) is False
    assert pvc.is_page_view(_entry(method="HEAD")) is False


@pytest.mark.parametrize(
    "ua", ["Googlebot/2.1", "curl/8.0", "python-requests/2.31", None]
)
def test_is_page_view_rejects_bots(pvc, ua):
    assert pvc.is_page_view(_entry(ua=ua)) is False


def test_iter_log_entries_reads_gzip_and_skips_bad_lines(pvc, tmp_path):
    plain = tmp_path / "access.log"
    plain.write_text(
        json.dumps(_entry(uri="/a.html"))
        + "\n"
        + json.dumps(_entry(uri="/b.html"))
        + "\n"
        + '{"truncated\n',
        encoding="utf-8",
    )
    rolled = tmp_path / "access-2026-11-13T00-00-00.000.log.gz"
    with gzip.open(rolled, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(_entry(uri="/c.html")) + "\n")

    uris = sorted(e["request"]["uri"] for e in pvc.iter_log_entries([plain, rolled]))
    assert uris == ["/a.html", "/b.html", "/c.html"]


def test_count_day_filters_day_and_counts(pvc):
    entries = [
        _entry(uri="/recipe/1", ip="10.0.0.1"),
        _entry(uri="/recipe/1", ip="10.0.0.1"),
        _entry(uri="/recipe/1", ip="10.0.0.2"),
        _entry(uri="/", ip="10.0.0.3"),
        _entry(uri="/recipe/1", ip="10.0.0.4", ts=NEXT_DAY_NOON),
        _entry(uri="/assets/app.js", ip="10.0.0.5"),
    ]
    assert pvc.count_day(entries, DAY) == [
        ("TOTAL", 4, 3),
        ("/recipe/1", 3, 2),
        ("/", 1, 1),
    ]


def test_count_day_strips_query_strings(pvc):
    entries = [
        _entry(uri="/search.html?q=a", ip="10.0.0.1"),
        _entry(uri="/search.html?q=b", ip="10.0.0.2"),
    ]
    assert pvc.count_day(entries, DAY) == [
        ("TOTAL", 2, 2),
        ("/search.html", 2, 2),
    ]


def test_count_day_empty_still_has_total(pvc):
    assert pvc.count_day([], DAY) == [("TOTAL", 0, 0)]


def test_merge_csv_from_empty(pvc):
    assert (
        pvc.merge_csv("", DAY, [("TOTAL", 1, 1)])
        == "date,path,views,visitors\r\n2026-11-13,TOTAL,1,1\r\n"
    )


def test_merge_csv_replaces_day_and_keeps_others(pvc):
    existing = (
        "date,path,views,visitors\r\n"
        "2026-11-13,TOTAL,99,99\r\n"
        "2026-11-13,/old,99,99\r\n"
        "2026-11-12,TOTAL,5,4\r\n"
        "2026-11-12,/,5,4\r\n"
    )
    merged = pvc.merge_csv(existing, DAY, [("TOTAL", 2, 1), ("/", 2, 1)])
    assert merged == (
        "date,path,views,visitors\r\n"
        "2026-11-12,TOTAL,5,4\r\n"
        "2026-11-12,/,5,4\r\n"
        "2026-11-13,TOTAL,2,1\r\n"
        "2026-11-13,/,2,1\r\n"
    )


def test_merge_csv_quotes_paths_with_commas(pvc):
    merged = pvc.merge_csv("", DAY, [("TOTAL", 1, 1), ("/recipe/a,b", 1, 1)])
    rows = list(csv.reader(io.StringIO(merged)))
    assert rows[2] == ["2026-11-13", "/recipe/a,b", "1", "1"]


@pytest.fixture
def s3_calls(pvc, monkeypatch):
    calls = {"download": [], "upload": [], "existing": ""}

    def fake_download(bucket, key):
        calls["download"].append((bucket, key))
        return calls["existing"]

    def fake_upload(bucket, key, text):
        calls["upload"].append((bucket, key, text))

    monkeypatch.setattr(pvc, "download_csv", fake_download)
    monkeypatch.setattr(pvc, "upload_csv", fake_upload)
    return calls


def _write_log(log_dir: Path, entries) -> Path:
    path = log_dir / "access.log"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


def test_main_skips_without_bucket(pvc, s3_calls, monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("BACKUP_BUCKET", raising=False)
    _write_log(tmp_path, [_entry()])
    assert pvc.main(["--log-dir", str(tmp_path), "--date", "2026-11-13"]) == 0
    assert s3_calls["upload"] == []
    assert "skipping" in capsys.readouterr().out


def test_main_fails_without_readable_logs(pvc, s3_calls, monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_BUCKET", "bucket")
    assert pvc.main(["--log-dir", str(tmp_path), "--date", "2026-11-13"]) == 1
    assert s3_calls["upload"] == []

    if os.geteuid() == 0:
        pytest.skip("root can read mode-000 files")
    log = _write_log(tmp_path, [_entry()])
    log.chmod(0)
    try:
        assert pvc.main(["--log-dir", str(tmp_path), "--date", "2026-11-13"]) == 1
    finally:
        log.chmod(0o644)
    assert s3_calls["upload"] == []


def test_main_merges_and_uploads(pvc, s3_calls, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BACKUP_BUCKET", "bucket")
    s3_calls["existing"] = "date,path,views,visitors\r\n2026-11-12,TOTAL,7,5\r\n"
    _write_log(tmp_path, [_entry(ip="10.0.0.1"), _entry(ip="10.0.0.2")])

    assert pvc.main(["--log-dir", str(tmp_path), "--date", "2026-11-13"]) == 0

    assert s3_calls["download"] == [("bucket", "traffic/page-views.csv")]
    [(bucket, key, text)] = s3_calls["upload"]
    assert (bucket, key) == ("bucket", "traffic/page-views.csv")
    assert "2026-11-12,TOTAL,7,5" in text
    assert "2026-11-13,TOTAL,2,2" in text
    assert "2026-11-13: 2 views, 2 visitors" in capsys.readouterr().out


def test_main_dry_run_does_not_touch_s3(pvc, s3_calls, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BACKUP_BUCKET", "bucket")
    _write_log(tmp_path, [_entry()])
    assert (
        pvc.main(["--log-dir", str(tmp_path), "--date", "2026-11-13", "--dry-run"]) == 0
    )
    assert s3_calls["download"] == [] and s3_calls["upload"] == []
    assert "TOTAL" in capsys.readouterr().out


SYSTEMD = ROOT / "infrastructure" / "systemd"


def test_page_view_units_exist_and_run_script():
    service = (SYSTEMD / "cocktaildb-page-views.service").read_text(encoding="utf-8")
    timer = (SYSTEMD / "cocktaildb-page-views.timer").read_text(encoding="utf-8")
    assert "SupplementaryGroups=caddy" in service
    assert "/opt/cocktaildb/scripts/page-view-counts.py" in service
    assert "OnCalendar=*-*-* 00:30:00" in timer
    assert "Persistent=true" in timer


def test_caddy_access_log_is_group_readable():
    caddyfile = (ROOT / "infrastructure" / "caddy" / "Caddyfile").read_text(
        encoding="utf-8"
    )
    block = re.search(
        r"output file /var/log/caddy/access\.log \{(.*?)\}", caddyfile, re.DOTALL
    )
    assert block, "HTTPS site must log to /var/log/caddy/access.log"
    assert re.search(r"^\s*mode 0640\s*$", block.group(1), re.MULTILINE)


def test_deploy_enables_page_view_timer():
    play = yaml.safe_load(
        (ROOT / "infrastructure" / "ansible" / "playbooks" / "deploy.yml").read_text(
            encoding="utf-8"
        )
    )[0]
    timers = [
        task["systemd"]
        for task in play["tasks"]
        if isinstance(task.get("systemd"), dict)
        and task["systemd"].get("name") == "cocktaildb-page-views.timer"
    ]
    assert len(timers) == 1
    assert timers[0]["enabled"] is True
    assert timers[0]["state"] == "started"


class _Run:
    """Fake subprocess.run returning scripted results per aws subcommand."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        rc, out, err = self.results[cmd[2]]
        if kwargs.get("check") and rc != 0:
            raise pvc_subprocess_error(rc, cmd)
        return type("Done", (), {"returncode": rc, "stdout": out, "stderr": err})()


def pvc_subprocess_error(rc, cmd):
    import subprocess

    return subprocess.CalledProcessError(rc, cmd)


LS_LINE = "2026-11-13 00:31:02       1234 page-views.csv\n"


def test_download_csv_missing_object_returns_empty(pvc, monkeypatch):
    run = _Run({"ls": (1, "", "")})
    monkeypatch.setattr(pvc.subprocess, "run", run)
    assert pvc.download_csv("bucket", "traffic/page-views.csv") == ""
    assert [c[2] for c in run.calls] == ["ls"]


def test_download_csv_ignores_prefix_matches(pvc, monkeypatch):
    run = _Run({"ls": (0, "2026-11-13 00:31:02 9 page-views.csv.bak\n", "")})
    monkeypatch.setattr(pvc.subprocess, "run", run)
    assert pvc.download_csv("bucket", "traffic/page-views.csv") == ""
    assert [c[2] for c in run.calls] == ["ls"]


def test_download_csv_returns_existing_text(pvc, monkeypatch):
    run = _Run({"ls": (0, LS_LINE, ""), "cp": (0, "date,path\r\n", "")})
    monkeypatch.setattr(pvc.subprocess, "run", run)
    assert pvc.download_csv("bucket", "traffic/page-views.csv") == "date,path\r\n"


@pytest.mark.parametrize(
    "ls_result",
    [
        (1, "", "An error occurred (AccessDenied)"),
        (254, "", "Unable to locate credentials"),
        (255, "", "Could not connect"),
    ],
)
def test_download_csv_raises_on_aws_errors(pvc, monkeypatch, ls_result):
    run = _Run({"ls": ls_result})
    monkeypatch.setattr(pvc.subprocess, "run", run)
    with pytest.raises(RuntimeError):
        pvc.download_csv("bucket", "traffic/page-views.csv")


def test_deploy_makes_existing_caddy_logs_group_readable():
    tasks = yaml.safe_load(
        (ROOT / "infrastructure" / "ansible" / "playbooks" / "deploy.yml").read_text(
            encoding="utf-8"
        )
    )[0]["tasks"]
    names = [t.get("name") for t in tasks]
    timer_index = next(
        i
        for i, t in enumerate(tasks)
        if isinstance(t.get("systemd"), dict)
        and t["systemd"].get("name") == "cocktaildb-page-views.timer"
    )
    fix_index = names.index("Make existing Caddy access logs group-readable")
    assert fix_index < timer_index
    command = tasks[fix_index]["ansible.builtin.command"]["argv"]
    assert command[:2] == ["find", "/var/log/caddy"]
    assert "access*.log*" in command
    assert "g+r" in command


class _CfnLoader(yaml.SafeLoader):
    """SafeLoader that reads CloudFormation short-form tags as plain values."""


def _cfn_tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_CfnLoader.add_multi_constructor("!", _cfn_tag)


def _backup_bucket_resources():
    template = yaml.load(
        (ROOT / "template.yaml").read_text(encoding="utf-8"), Loader=_CfnLoader
    )
    return template["Resources"]


def _publicly_readable(key: str) -> bool:
    from fnmatch import fnmatchcase

    policy = _backup_bucket_resources()["BackupBucketPolicy"]["Properties"]
    for statement in policy["PolicyDocument"]["Statement"]:
        if statement["Effect"] != "Allow" or statement.get("Principal") != "*":
            continue
        resources = statement["Resource"]
        resources = [resources] if isinstance(resources, str) else resources
        for resource in resources:
            pattern = resource.replace("${BackupBucket.Arn}/", "")
            if fnmatchcase(key, pattern):
                return True
    return False


def test_backup_bucket_keeps_downloads_public_but_not_traffic():
    assert _publicly_readable("backup-2026-11-13_08-00-00.sql.gz")
    assert _publicly_readable("latest.txt")
    assert _publicly_readable("latest.json")
    assert not _publicly_readable("traffic/page-views.csv")


def test_backup_bucket_expiry_spares_traffic_history():
    rules = _backup_bucket_resources()["BackupBucket"]["Properties"][
        "LifecycleConfiguration"
    ]["Rules"]
    expiring = [
        r for r in rules if r["Status"] == "Enabled" and "ExpirationInDays" in r
    ]
    assert expiring, "old backups must still expire"
    for rule in expiring:
        prefix = rule.get("Prefix", "")
        assert "backup-2026-11-13_08-00-00.sql.gz".startswith(prefix)
        assert not "traffic/page-views.csv".startswith(prefix)
