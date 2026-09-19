# Recipe ABV design checklist

- [x] Explore ingredient composition, unit conversion, and recipe display flows.
- [x] Clarify calculation basis and missing-data policy (one question at a time).
- [x] Consider visual companion: not needed for the calculation decisions.
- [x] Compare approaches and recommend the smallest adequate solution.
- [x] Present design sections and obtain approval of calculation rules.
- [ ] Write and commit the design specification.
- [ ] Self-review and refine the exact specification with pi-refine.
- [ ] Obtain user approval of the refined specification.
- [ ] Create implementation plan using writing-plans.

Spec: `docs/superpowers/specs/2026-09-19-recipe-abv-design.md`.
Dilution and structured preparation are deferred to GitHub issue #70.

Pre-existing changes to `api/db/db_core.py`, `api/models/responses.py`, and
untracked `research/` are outside this design task and must remain untouched.
