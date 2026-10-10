# Vite validation follow-ups

This note tracks validation limits that are outside the bounded mapped-port readiness repair. It does not authorize production rating or test-container framework changes.

## Inherited Testcontainers terminal auth/config behavior

The readiness repair at `7f9bc24c262ce3b5c7cf1c13b1859d0cc442ecf9` adds the upstream-supported `PortWaitStrategy(5432)` for the Docker-mapped host port. It does **not** replace the installed Testcontainers PostgreSQL connection check or promise earlier classification of terminal authentication/database configuration failures.

With testcontainers `4.13.3`, `PostgresContainer._connect` is decorated with the deprecated `wait_container_is_ready` implementation. It executes `psql` inside the container and raises `ConnectionError("pg_isready is not ready yet")` for every nonzero result. The legacy waiter treats `ConnectionError` as transient, retries at the configured one-second poll interval, and raises after the default 120-second startup timeout with the original exception embedded in a message shaped like:

```text
Wait time (120.0s) exceeded for _connect(args: (), kwargs: {}). Exception: pg_isready is not ready yet. Hint: Check if the container is ready, the function parameters are correct, and the expected conditions are met for the function to succeed.
```

The fixture's existing setup handler preserves that original error text in its `pytest.exit` message when setup fails, but it does not classify auth/config errors separately. This inherited upstream behavior remains a follow-up; do not add a new connection framework or retry the rating assertion under the Vite task.

Diagnostics retained under the SDD path:

- `historical-task3-concurrency.CkZ73a/current-1.log` is a copied historical log from the pre-repair diagnostic at Task 3 HEAD `000e448e1011da9a96c28557387a95004eed9586`. It records the mapped-port failure verbatim: `psycopg2.OperationalError: connection to server at "localhost" (127.0.0.1), port 49720 failed: Connection refused`, after an internal `pg_isready is not ready yet` message. The disposable container was already removed before inspection, so its Docker logs could not be recovered.
- `readiness-run.vmLZlW/` records a successful first host-side `select 1` with the old default strategy; that success does not prove terminal auth/config failures are classified.
- `readiness-fixed-run.tSDesc/` records a successful host-side `select 1` after the mapped-port strategy and retains PostgreSQL stdout/stderr plus inspect data before owned cleanup.

A future follow-up should preserve the original exception and timeout diagnostics while deciding whether upstream behavior can be improved without widening the task scope.

## Independently reproduced rating-count defect

The concurrent test's aggregate count remains a separate database/rating-path defect and is explicitly outside this readiness repair:

- Historical `validation-baseline.rIaLnO/baseline-run-4.log` uses the pre-Task-3 comparison revision `6d416dc40f5a01e3cbd56697c7868b93be7581b4` and records 20 successful `set_rating` results followed by `rating_count == 19` instead of 20.
- Historical `full-suite-final.HseKzS/current-final.log` is post-readiness repair at `7f9bc24c262ce3b5c7cf1c13b1859d0cc442ecf9` and records `rating_count == 18` instead of 20.
- Fix-round-1's one authorized current run at `validation-fix1-current.kMtk3y/current-run-1.log` records `rating_count == 19` instead of 20. Its one authorized equivalent baseline run at the git-archive extraction `validation-fix1-baseline.XXMAQG/baseline-run-1.log` passes.

These are retained observations, not a frequency or severity estimate: the authorized post-repair sample is one run per revision, and the historical five-run sample is not an apples-to-apples post-repair comparison. Do not change production rating SQL, triggers, schema, or database behavior as part of readiness validation.
