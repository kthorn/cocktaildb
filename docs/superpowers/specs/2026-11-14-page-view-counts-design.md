# Daily Page-View Counts — Design

**Status:** Approved 2026-11-14

## Intent

Get a rough, long-lived answer to "how much is the site used?" without adding
third-party analytics or frontend changes. The owner checks it occasionally,
so minimal beats polished.

## Goals

- One summary per day: page views and approximate unique visitors, overall
  and per page.
- History kept indefinitely. CloudWatch keeps only 30 days of access logs.
- No IPs or other personal data stored, only counts.

## Non-goals

- Dashboards, charts, or an API/UI to view the numbers.
- Client-side tracking, referrers, sessions, time-on-page.
- Precise bot filtering; a user-agent heuristic is good enough.
- Dev environment. It has no backup bucket, so the job does nothing there.

## Approaches considered

1. **Postgres table.** Rows are queryable and included in DB backups, but
   it needs a migration and is more machinery than the owner wants.
2. **CSV in S3 (chosen).** No schema change. The owner downloads the file
   when curious.
3. **Raise CloudWatch retention and use ad-hoc Logs Insights.** Cheapest,
   but the instance role can't run queries. Raw hits also need filtering on
   every look.

## Design

- **Source:** Caddy's local JSON access logs, `/var/log/caddy/access.log`
  plus rotated files. Reading them locally avoids any IAM change.
- **Script:** `infrastructure/scripts/page-view-counts.py`, Python, standard
  library only. It is deployed with the other scripts by `deploy.yml`.
  - Default target day is yesterday (UTC). `--date YYYY-MM-DD` overrides it.
    `--dry-run` prints rows instead of uploading.
  - A request counts as a **page view** when it is a `GET` with status 200
    or 304 whose path is `/`, `*.html`, `/recipe/*` or `/ingredient/*`. API calls,
    `/assets/*`, images and fonts are excluded, as are user agents matching
    a bot pattern (`bot|crawl|spider|slurp|preview|curl|python|wget|…`).
    304 counts because pages are served `Cache-Control: no-cache`, so
    repeat visits revalidate rather than receiving a 200.
  - Query strings are stripped before grouping.
  - **Visitors** = distinct client IPs. IPs are used only in memory.
- **Output:** `s3://$BACKUP_BUCKET/traffic/page-views.csv` with columns
  `date,path,views,visitors`. Each day gets a `TOTAL` row plus one row per
  path. The script downloads the CSV, replaces any existing rows for the
  target day, and uploads it again, so reruns are safe. The backup pruning
  only touches `backup-*.sql.gz`, so this file is never removed.
- **Schedule:** `cocktaildb-page-views.service` plus a `.timer` at about
  00:30 UTC daily with `Persistent=true`, modeled on the backup units. The
  timer is enabled in `deploy.yml`. If `BACKUP_BUCKET` is empty, the script
  logs that and exits 0.
- **Log access:** Caddy creates its log files readable only by the `caddy`
  user. The builder picks the narrowest fix, such as Caddy's `mode` file
  option plus `SupplementaryGroups=caddy` on the unit, after checking it
  also applies to rotated files.
- **Docs:** Add a short "Traffic counts" note to `docs/operations-runbook.md`
  with the one-line `aws s3 cp` command to fetch the CSV.

## Accepted limitations

- If the job misses a day and logs rotate past it (5 × 10 MB kept), that day
  is lost. This is fine at current traffic.
- Shared or changing IPs make "visitors" approximate.

## Testing

Use pytest unit tests for the parsing and counting function with fixture log
lines: page vs asset vs API, bot user agents, non-200, query strings, a
day-boundary filter, and replace-day merging of an existing CSV. No
database is needed.
