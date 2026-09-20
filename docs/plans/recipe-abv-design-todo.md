# Recipe ABV design checklist

- [x] Explore ingredient composition, unit conversion, and recipe display flows.
- [x] Clarify calculation basis and missing-data policy (one question at a time).
- [x] Consider visual companion: not needed for the calculation decisions.
- [x] Compare approaches and recommend the smallest adequate solution.
- [x] Present design sections and obtain approval of calculation rules.
- [x] Write and commit the design specification (`42d3c2a`).
- [x] Self-review and refine the exact specification with pi-refine (converged after three reviews; owner-approved rollup fix included; see `recipe-abv-review-log.md`).
- [x] Obtain user approval of the refined specification (whole-percent display requested; implementation authorized).
- [x] Create implementation plan using writing-plans (`docs/superpowers/plans/2026-09-19-recipe-abv.md`).
- [x] Implement Task 1: live ranges and last-child correction; independent review passed (`76cdd23`).
- [x] Implement Task 2: calculator and recipe enrichment; independent review findings addressed and mutation-tested (`1f1080c`, `18ad6b7`).
- [x] Implement Task 3: recipe display and validation (`df1f1ef`); owner authorized direct execution after runner failures, with final whole-branch review retained.
- [ ] Complete whole-branch review and report verification.

Spec: `docs/superpowers/specs/2026-09-19-recipe-abv-design.md`.
Dilution and structured preparation are deferred to GitHub issue #70.

Pre-existing changes to `api/db/db_core.py`, `api/models/responses.py`,
`api/routes/pages.py`, `tests/test_page_route_contracts.py`, and untracked
`research/` are outside this design task and must remain untouched.
Implementation must use a separate clean worktree rather than mix these changes.
