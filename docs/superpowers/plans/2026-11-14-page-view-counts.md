# Daily Page-View Counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A nightly job on the EC2 host turns yesterday's Caddy access logs
into per-page view/visitor counts and merges them into a CSV in S3.

**Architecture:** There is one stdlib-only Python script,
`infrastructure/scripts/page-view-counts.py`. Pure functions parse, filter and
count; a thin `main()` does the S3 I/O through the `aws` CLI. A systemd
oneshot service plus a timer runs it daily. Caddy's log mode is widened so the
`cocktaildb` user can read the logs through the `caddy` group.

**Tech Stack:** Python 3 stdlib (`json`, `gzip`, `csv`, `argparse`,
`subprocess`), aws CLI, systemd, Ansible, Caddy.

**Spec:** `docs/superpowers/specs/2026-11-14-page-view-counts-design.md`

## Global Constraints

- The script runs on the host's `python3` (Amazon Linux 2023, Python 3.9).
  Use the stdlib only, put `from __future__ import annotations` first, and use
  no 3.10+ syntax (`match`, runtime `X | Y`).
- Output location: `s3://$BACKUP_BUCKET/traffic/page-views.csv`. Header
  `date,path,views,visitors`.
- Never write IPs or user agents anywhere, only counts.
- All day boundaries are UTC. Caddy's `ts` is Unix seconds (float).
- Empty or unset `BACKUP_BUCKET`: print a message and exit 0 without
  uploading.
- Tests use `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest`.
  None of these tests need Docker.

## Review Focus

1. **Repeat visits return 304.** Pages are `no-cache`, so a GET with status
   304 must count as a view. Tested in Task 1:
   `test_is_page_view_counts_304`.
2. **Rotated gzip files and a truncated or garbage line.** Caddy gzips rolled
   files, and a line can be cut off at rotation. The parser reads `.gz`
   transparently and skips bad lines without failing. Tested in Task 1:
   `test_iter_log_entries_reads_gzip_and_skips_bad_lines`.
3. **Unreadable logs must not upload zeros.** A `PermissionError` (or no
   `access*.log*` files at all) makes the run exit nonzero, so systemd shows
   it failed, and nothing is uploaded. Tested in Task 2:
   `test_main_fails_without_readable_logs`.
4. **A rerun of the same day replaces rather than duplicates**, and the
   first run, with no CSV yet, creates the file. Tested in Task 1:
   `test_merge_csv_replaces_day_and_keeps_others` and
   `test_merge_csv_from_empty`.
5. **A day with no traffic still records a `TOTAL,0,0` row**, so a gap
   (job didn't run) is distinguishable from zero visits. Tested in Task 1:
   `test_count_day_empty_still_has_total`.

---

### Task 1: Counting core

**Files:**
- Create: `infrastructure/scripts/page-view-counts.py`
- Test: `tests/test_page_view_counts.py`

**Interfaces:**
- Produces, all in `page-view-counts.py`:
  - `iter_log_entries(paths: Iterable[Path]) -> Iterator[dict]`: yields
    parsed JSON objects. Opens `*.gz` with `gzip.open(..., "rt")` and skips
    lines that are not valid JSON objects.
  - `is_page_view(entry: dict) -> bool`
  - `entry_day(entry: dict) -> date | None`: the UTC date of `entry["ts"]`,
    or None if missing or invalid.
  - `count_day(entries: Iterable[dict], day: date) -> list[tuple[str, int, int]]`
    returns `(path, views, visitors)`. The first row is `("TOTAL", views,
    distinct_ips)`, followed by per-path rows sorted by views descending,
    then path ascending.
  - `merge_csv(existing: str, day: date, rows: list[tuple[str, int, int]]) -> str`
    returns full CSV text with a header. Rows for `day` are replaced, other
    days are kept, and rows are ordered by date ascending with each day's
    row order preserved.
  - Constants: `CSV_HEADER = ["date", "path", "views", "visitors"]`,
    `S3_KEY = "traffic/page-views.csv"`, `DEFAULT_LOG_DIR = "/var/log/caddy"`.

Caddy entry fields used: `ts`, `status`, `request.method`, `request.uri`,
`request.client_ip` (fall back to `request.remote_ip`), and
`request.headers["User-Agent"][0]` (a missing UA counts as a bot).

Page-view rule: method `GET`, status in `{200, 304}`, a user agent that does
not match the bot pattern, and a path (the URI with `?…`/`#…` stripped)
that is `/`, ends in `.html`, or starts with `/recipe/` or `/ingredient/`.
Bot pattern, case-insensitive:
`bot|crawl|spider|slurp|preview|curl|wget|python|httpx|go-http-client|headless|facebookexternalhit|monitor|uptime`.

- [ ] **Step 1: Write the failing tests** in
  `tests/test_page_view_counts.py`. Load the module by file path with
  `importlib.util.spec_from_file_location`, following the pattern in
  `tests/test_frontend_release.py`. Use a helper
  `_entry(uri="/", status=200, method="GET", ua="Mozilla/5.0", ip="1.1.1.1", ts=<2026-11-13 12:00 UTC>)`
  that builds a Caddy-shaped dict. Tests:
  - `test_is_page_view_accepts_pages`: `/`, `/index.html`,
    `/search.html?q=gin`, `/recipe/42` and `/ingredient/gin` are all True.
  - `test_is_page_view_rejects_non_pages`: `/api/v1/recipes`,
    `/assets/app-abc.js`, `/styles.css`, `/logo.png`, `/health` and
    `/sitemap.xml` are all False.
  - `test_is_page_view_counts_304`: status 304 gives True, status 404 or 301
    gives False, and method `HEAD` gives False.
  - `test_is_page_view_rejects_bots`: UA `Googlebot/2.1`, `curl/8.0` and
    `python-requests/2.31` all give False, and so does an entry with no
    `User-Agent` header.
  - `test_iter_log_entries_reads_gzip_and_skips_bad_lines`: in a plain file
    write 2 valid lines and `{"truncated`; in a `.gz` file write 1 valid
    line. Expect 3 entries in total.
  - `test_count_day_filters_day_and_counts`: on day D, 3 views of
    `/recipe/1` from 2 IPs and 1 view of `/` from a third IP; plus 1
    `/recipe/1` view on D+1 and 1 asset hit on D. Expect
    `[("TOTAL", 4, 3), ("/recipe/1", 3, 2), ("/", 1, 1)]`.
  - `test_count_day_strips_query_strings`: `/search.html?q=a` and
    `/search.html?q=b` combine into one row `("/search.html", 2, ...)`.
  - `test_count_day_empty_still_has_total`: no entries gives
    `[("TOTAL", 0, 0)]`.
  - `test_merge_csv_from_empty`: `merge_csv("", D, [("TOTAL",1,1)])` equals
    `"date,path,views,visitors\r\n<D>,TOTAL,1,1\r\n"` (the csv module's
    default line ending).
  - `test_merge_csv_replaces_day_and_keeps_others`: the existing CSV has
    rows for D-1 and D. Merging new rows for D leaves D-1 unchanged and
    replaces the old D rows. D-1 comes before D.
  - `test_merge_csv_quotes_paths_with_commas`: path `/recipe/a,b`
    round-trips through `csv.reader`.

- [ ] **Step 2: Run the tests and confirm they fail**

  Run: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_page_view_counts.py -q`
  Expected: errors because the module file does not exist.

- [ ] **Step 3: Implement the interfaces above** in
  `infrastructure/scripts/page-view-counts.py`. Start with a shebang,
  `#!/usr/bin/env python3`, then a docstring that summarizes the spec. Use
  `csv.writer` and `csv.reader` over `io.StringIO`, and `urllib.parse` or a
  split to strip the query and fragment.

- [ ] **Step 4: Run the tests and confirm they pass**

  Run: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_page_view_counts.py -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add infrastructure/scripts/page-view-counts.py tests/test_page_view_counts.py
  git commit -m "feat: count daily page views from Caddy access logs"
  ```

---

### Task 2: CLI and S3 merge

**Files:**
- Modify: `infrastructure/scripts/page-view-counts.py`
- Test: `tests/test_page_view_counts.py`

**Interfaces:**
- Consumes: everything Task 1 produces.
- Produces:
  - `log_paths(log_dir: Path) -> list[Path]`: `sorted(log_dir.glob("access*.log*"))`.
  - `download_csv(bucket: str, key: str) -> str`: returns `""` when the
    object is missing. Check with `aws s3 ls s3://bucket/key` (exit 1 means
    absent), then run `aws s3 cp s3://bucket/key -` and capture stdout. Any
    other failure raises.
  - `upload_csv(bucket: str, key: str, text: str) -> None`: runs
    `aws s3 cp - s3://bucket/key --content-type text/csv` with `input=text`
    and `check=True`.
  - `main(argv: list[str] | None = None) -> int`, with these arguments:
    `--date YYYY-MM-DD` (default: yesterday UTC), `--dry-run` (print the
    merged rows for the day to stdout, with no S3 calls), and
    `--log-dir` (default `DEFAULT_LOG_DIR`). The bucket comes from
    `os.environ.get("BACKUP_BUCKET", "")`. Order of operations:
    1. If there is no bucket and this is not a dry run, print
       `"BACKUP_BUCKET not set; skipping"` and return 0.
    2. Get the log paths. If there are none, print to stderr and return 1.
    3. Count the day. Any `OSError` while reading is printed to stderr and
       returns 1 before any upload.
    4. Download, merge and upload.
    5. Print one summary line: `"<date>: <views> views, <visitors> visitors"`.

    The script ends with `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 1: Write the failing tests.** Monkeypatch `download_csv` and
  `upload_csv` on the loaded module to record calls. Tests:
  - `test_main_skips_without_bucket`: with `BACKUP_BUCKET` unset, the
    return value is 0, nothing is uploaded, and the output contains
    "skipping".
  - `test_main_fails_without_readable_logs`: with the bucket set, an empty
    `--log-dir` returns 1 and nothing is uploaded. Also cover a log file
    with `chmod 000`; skip that part if running as root
    (`os.geteuid() == 0`).
  - `test_main_merges_and_uploads`: write a log containing 2 page views on
    2026-11-13. Have `download_csv` return an existing CSV with a 2026-11-12
    row. Run with `--date 2026-11-13`. The return value is 0, `upload_csv`
    receives key `traffic/page-views.csv`, and the text contains both days
    plus `2026-11-13,TOTAL,2,`.
  - `test_main_dry_run_does_not_touch_s3`: with `--dry-run`, neither
    download nor upload is called and the output contains `TOTAL`.

- [ ] **Step 2: Run the tests and confirm the new ones fail**

  Run: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_page_view_counts.py -q`
  Expected: the 4 new tests fail with `AttributeError` on `main`.

- [ ] **Step 3: Implement `log_paths`, `download_csv`, `upload_csv` and
  `main`** as specified above.

- [ ] **Step 4: Run the tests and confirm they pass**

  Run: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_page_view_counts.py -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add infrastructure/scripts/page-view-counts.py tests/test_page_view_counts.py
  git commit -m "feat: merge daily page-view counts into S3 CSV"
  ```

---

### Task 3: Schedule, log access, deploy wiring and runbook

**Files:**
- Create: `infrastructure/systemd/cocktaildb-page-views.service`
- Create: `infrastructure/systemd/cocktaildb-page-views.timer`
- Modify: `infrastructure/caddy/Caddyfile:135-141` (the HTTPS site `log` block)
- Modify: `infrastructure/ansible/playbooks/deploy.yml` (the "Copy deployment
  scripts" loop, around line 223, and the timer-enable tasks, around line 384)
- Modify: `docs/operations-runbook.md` (new "Traffic Counts (Prod)"
  subsection after "CloudWatch Logs (Prod)")
- Test: `tests/test_page_view_counts.py`

**Interfaces:**
- Consumes: `main()` from Task 2, invoked as
  `/usr/bin/python3 /opt/cocktaildb/scripts/page-view-counts.py`.
- Produces: the deployed units. Nothing later depends on them.

Unit contents:
- **Service:** model it on `cocktaildb-backup.service`. Use
  `Type=oneshot`, `User=cocktaildb`, `Group=cocktaildb`,
  `SupplementaryGroups=caddy`, `EnvironmentFile=/opt/cocktaildb/.env`,
  `ExecStart=/usr/bin/python3 /opt/cocktaildb/scripts/page-view-counts.py`,
  journal output, `SyslogIdentifier=cocktaildb-page-views`,
  `TimeoutStartSec=600` and `Restart=no`.
- **Timer:** `OnCalendar=*-*-* 00:30:00`, `Persistent=true`,
  `RandomizedDelaySec=300` and `WantedBy=timers.target`.
- **Caddyfile:** in the HTTPS site's `output file /var/log/caddy/access.log`
  block, add `mode 0640`. This needs Caddy 2.8+.

- [ ] **Step 1: Write the failing tests**
  - `test_page_view_units_exist_and_run_script`: both unit files exist.
    The service contains `SupplementaryGroups=caddy` and
    `/opt/cocktaildb/scripts/page-view-counts.py`. The timer contains
    `OnCalendar=*-*-* 00:30:00` and `Persistent=true`.
  - `test_caddy_access_log_is_group_readable`: the Caddyfile text contains
    `mode 0640` inside the block that writes `/var/log/caddy/access.log`.
  - `test_deploy_enables_page_view_timer`: `yaml.safe_load` of `deploy.yml`
    has a `systemd` task named `cocktaildb-page-views.timer` with
    `enabled: yes` and `state: started`.

  The existing
  `tests/test_deploy_config_sources.py::test_deploy_playbook_copies_an_explicit_host_script_set`
  will also fail until the script is added to the copy loop, because the
  new service references it.

- [ ] **Step 2: Run the tests and confirm they fail**

  Run: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_page_view_counts.py tests/test_deploy_config_sources.py -q`
  Expected: the 3 new tests fail, plus the host-script-set test.

- [ ] **Step 3: Implement.** Create the units, add `mode 0640` to the
  Caddyfile, add `page-view-counts.py` to the deploy copy loop
  (alphabetical position), and add an "Enable page view counts timer" task
  after "Enable backup timer" in the same style. In the runbook, write 3 or
  4 lines:
  - what the job does;
  - how to fetch the file:
    `aws s3 cp s3://cocktaildbbackups-<account>-prod/traffic/page-views.csv -`;
  - how to backfill or rerun a day:
    `sudo -u cocktaildb ... page-view-counts.py --date YYYY-MM-DD`;
  - how to check status: `systemctl list-timers cocktaildb-page-views.timer`
    and `journalctl -u cocktaildb-page-views`;
  - a note that after the first deploy, `ls -l /var/log/caddy` should show
    `-rw-r-----` with group `caddy`. If the existing `access.log` is still
    `0600`, run `sudo chmod 0640 /var/log/caddy/access.log` once.

- [ ] **Step 4: Run the full checks**

  Run: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest -q`.
  Expected: all pass. Report DB-backed tests as not run if Docker is
  unavailable.
  Run: `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files`.
  Expected: it passes.

- [ ] **Step 5: Commit**

  ```bash
  git add infrastructure/systemd/cocktaildb-page-views.* infrastructure/caddy/Caddyfile \
      infrastructure/ansible/playbooks/deploy.yml docs/operations-runbook.md tests/test_page_view_counts.py
  git commit -m "feat: schedule nightly page-view counts on EC2"
  ```

## Manual checks after deploy (human; not run by the implementer)

- `ls -l /var/log/caddy`: files are `0640` with group `caddy`.
- `sudo systemctl start cocktaildb-page-views.service`, then
  `journalctl -u cocktaildb-page-views -n 20` shows the summary line.
- `aws s3 cp s3://<backup bucket>/traffic/page-views.csv -` shows
  yesterday's rows.
