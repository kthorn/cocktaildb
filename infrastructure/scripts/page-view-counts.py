#!/usr/bin/env python3
"""Summarize a day of Caddy access logs into page-view counts.

Reads Caddy's JSON access logs (current and rotated, gzipped or not), keeps
successful GET requests for HTML pages from non-bot user agents, and counts
views and distinct client IPs per path for one UTC day. Only counts leave
this process; IPs and user agents are never written anywhere.

See docs/superpowers/specs/2026-11-14-page-view-counts-design.md.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

CSV_HEADER = ["date", "path", "views", "visitors"]
S3_KEY = "traffic/page-views.csv"
DEFAULT_LOG_DIR = "/var/log/caddy"
TOTAL = "TOTAL"

PAGE_STATUSES = {200, 304}
BOT_PATTERN = re.compile(
    r"bot|crawl|spider|slurp|preview|curl|wget|python|httpx|go-http-client"
    r"|headless|facebookexternalhit|monitor|uptime",
    re.IGNORECASE,
)


def iter_log_entries(paths: Iterable[Path]) -> Iterator[dict]:
    """Yield each JSON object in the given log files, skipping bad lines."""
    for path in paths:
        opener = gzip.open if path.name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    yield entry


def _request(entry: dict) -> dict:
    request = entry.get("request")
    return request if isinstance(request, dict) else {}


def _path(entry: dict) -> str:
    uri = str(_request(entry).get("uri", ""))
    return uri.split("?", 1)[0].split("#", 1)[0]


def _user_agent(entry: dict) -> str:
    headers = _request(entry).get("headers")
    if not isinstance(headers, dict):
        return ""
    values = headers.get("User-Agent") or []
    return str(values[0]) if values else ""


def _client_ip(entry: dict) -> str:
    request = _request(entry)
    return str(request.get("client_ip") or request.get("remote_ip") or "")


def _is_page_path(path: str) -> bool:
    return (
        path == "/"
        or path.endswith(".html")
        or path.startswith("/recipe/")
        or path.startswith("/ingredient/")
    )


def is_page_view(entry: dict) -> bool:
    if _request(entry).get("method") != "GET":
        return False
    if entry.get("status") not in PAGE_STATUSES:
        return False
    ua = _user_agent(entry)
    if not ua or BOT_PATTERN.search(ua):
        return False
    return _is_page_path(_path(entry))


def entry_day(entry: dict) -> date | None:
    try:
        return datetime.fromtimestamp(float(entry["ts"]), tz=timezone.utc).date()
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None


def count_day(entries: Iterable[dict], day: date) -> list[tuple[str, int, int]]:
    """Return [(TOTAL, views, visitors), (path, views, visitors), ...]."""
    views: dict[str, int] = defaultdict(int)
    visitors: dict[str, set[str]] = defaultdict(set)
    all_visitors: set[str] = set()
    for entry in entries:
        if entry_day(entry) != day or not is_page_view(entry):
            continue
        path = _path(entry)
        ip = _client_ip(entry)
        views[path] += 1
        visitors[path].add(ip)
        all_visitors.add(ip)

    per_path = sorted(
        ((path, views[path], len(visitors[path])) for path in views),
        key=lambda row: (-row[1], row[0]),
    )
    return [(TOTAL, sum(views.values()), len(all_visitors))] + per_path


def merge_csv(existing: str, day: date, rows: list[tuple[str, int, int]]) -> str:
    """Replace `day`'s rows in the CSV text and return the full new CSV."""
    day_str = day.isoformat()
    kept = [
        row
        for row in csv.reader(io.StringIO(existing))
        if row and row != CSV_HEADER and row[0] != day_str
    ]
    kept += [[day_str, path, str(v), str(u)] for path, v, u in rows]
    # Stable sort keeps each day's row order.
    kept.sort(key=lambda row: row[0])

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_HEADER)
    writer.writerows(kept)
    return out.getvalue()
