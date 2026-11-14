from __future__ import annotations

import csv
import gzip
import importlib.util
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "infrastructure" / "scripts" / "page-view-counts.py"

DAY = date(2026, 11, 13)
NOON = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc).timestamp()
NEXT_DAY_NOON = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc).timestamp()


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
