# Recipe ABV implementation verification

## Scope delivered

- Live known-leaf family ABV ranges and nearest-family resolution.
- Last-child derived-ABV cleanup, additive PostgreSQL migration 16 and rollback.
- Ingredient-only calculation, volume-weighted uncertainty, 20-point cutoff,
  whole-percent display, and explicit top-up/rinse/counted-item assumptions.
- One bulk lookup for recipe get/search, additive API response, safe JavaScript
  and server-rendered display with expandable notes.
- No dilution estimate, sugar/acid feature, deployment, or merge.

## Tests observed by the parent

- Baseline before work: 18 selected unit/page tests and 4 PostgreSQL rollup tests passed.
- Database task: 17 PostgreSQL tests passed; its independent review approved.
- Calculator task: 843 tests under `tests/` passed; review required stronger
  unknown-ingredient integration assertions, subsequently fixed in `18ad6b7`.
- The stronger integration test uses a real PostgreSQL recipe with 60 mL of 40%
  spirit and 5 mL of an unobserved ingredient. Get/list/keyset/random paths assert
  the literal `Estimated 36–45%` and hand-derived raw bounds.
- Mutation check: replacing the SQL's unknown upper bound 100 with 0 in a single
  test process caused all three new integration cases to fail on `37%` versus
  `36–45%`. No production files were changed by this check.
- UI RED: the Node card test and four SSR cases failed for the absent ABV block.
  UI GREEN: the actual card builder and SSR template now pass those checks.
- 97 focused calculator, PostgreSQL, SSR, and Node-contract tests passed.
- Full branch run with explicit coverage flags: **934 passed**, 138 warnings;
  coverage **75.30%**, so the 80% coverage gate failed (exit 1).
- A subsequent full normal run after an optional-key typing correction:
  **933 passed, 1 failed**, 138 warnings. The failure was
  `tests/test_db_integration.py::TestConcurrentAccess::test_concurrent_rating_updates`
  (`rating_count == 19`, expected 20). See baseline reproduction below.
- Canonical pre-commit formatter hooks and changed JavaScript syntax checks passed.
- Active LSP check identified one new optional dictionary-key typing error, which
  was corrected. Re-probing calculator/card/test returned no diagnostics, but the
  push-only language servers could not affirm a clean result. Existing database
  typing/import findings and unresolved test import configuration remain; no claim
  of an all-clean static-analysis gate is made.

Logs for this session are under the feature worktree's ignored
`.superpowers/sdd/2026-09-19-recipe-abv/`:
`full-verification.Tyf9ybhj.log` (explicit coverage) and
`final-suite.RNIjLu0v.log` (intermittent concurrent-rating failure).

## Existing repository issues, not hidden by this change

### Coverage configuration and baseline

`pytest.ini` uses `[tool:pytest]` instead of `[pytest]`. A direct pytest Config
probe reported the file but `Configured addopts: []`: ordinary runs do not apply
the intended coverage flags. The parent therefore supplied them explicitly:

```sh
~/miniforge3/envs/cocktaildb/bin/python -m pytest -q \
  --cov=api --cov-report=term --cov-fail-under=80
```

On an untouched archive of implementation base `4f3708c`, this ran **857 passing
tests** but failed the same gate at **74.51%**. Archive:
`/tmp/recipe-abv-baseline.nuhBEGrz`; log:
`/tmp/recipe-abv-baseline-tests.DEiWBq1p.log`.

Follow-up: correct the pytest config section and bring repository-wide coverage
to its intended 80% gate. Do not silently lower the threshold or claim it passed.
ABV calculator coverage measured **91%** in the branch run.

### Concurrent rating aggregation race

On the untouched base archive, separate invocations of:

```sh
~/miniforge3/envs/cocktaildb/bin/python -m pytest \
  tests/test_db_integration.py::TestConcurrentAccess::test_concurrent_rating_updates \
  -q --tb=short --show-capture=no
```

passed once, then reproduced the exact **19 versus 20** rating-count failure on
the second invocation. Evidence:
`/tmp/recipe-abv-baseline-race-runs.KAxoko7r/run-2.log`.

Follow-up: investigate concurrency/snapshot behavior of rating aggregation.
Do not suppress or weaken this assertion, and do not fold that separate write-path
fix into an ingredient-ABV display feature. A green rerun would not erase this risk.

### Other limitations

Existing dependency deprecation warnings remain visible. Family extrema are
observed ranges, not physical guarantees; historical former-parent measurements
need the already-documented owner data audit. Analytics still intentionally uses
its separate volume proxies. Performance evidence is a 100-ingredient synthetic
fixture, not a production-scale guarantee.

## Delivery state

Feature branch: `feat/recipe-abv` in `.worktrees/recipe-abv`.
Final independent whole-branch review approved head `61d3300` with no introduced
blocking findings (review run `e99e7fd8-2c1c-4b08-8929-136c766c6818`).
The reviewer inspected the full diff and approved design; it could not execute
tests. The coverage shortfall and baseline rating race remain explicit caveats.
No deployment or merge performed.
