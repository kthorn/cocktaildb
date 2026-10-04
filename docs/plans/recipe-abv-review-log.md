# Recipe ABV spec refinement

Subject: `docs/superpowers/specs/2026-09-19-recipe-abv-design.md`

## Dispatch 1

- Runner: Paseo, Claude `claude-opus-5`, thinking `high`, Plan Mode.
- Workspace: `wks_51a7d0ee0f7b9e38` (`/home/kurtt/cocktaildb`).
- Agent: `eea12541-ab8d-4812-a124-47b96d0ff68b`.
- Report: `/tmp/recipe-abv-spec-review.roTvLD9E.md`.
- Outcome: `RESULT: findings`; one result marker; not converged.
- Parent verified the rollup issue directly in the schema function: its update
  only targets IDs that still have children. A last-child deletion or reparent
  leaves the former parent's old calculated values behind, indistinguishable
  from recorded leaf values.

## Dispositions

1. **Approved and specified:** owner approved clearing a former parent's derived
   ABV when its last child is deleted or reparented. Specify a narrow row trigger,
   existing advisory-lock ordering, batch tests, and ancestor refresh. Historical
   former-parent values cannot be distinguished from genuine recorded leaf values
   using today's schema alone: preserve data and flag an owner audit before rollout.
   Equivalent sugar/acidity cleanup is deferred until those fields are in scope.
2. **Fixed:** document analytics' distinct volume model (90 mL top-up,
   5 mL rinse, counted-item proxy). Do not silently change similarity semantics.
3. **Fixed:** specify Decimal normalization for database NUMERIC, REAL,
   fallback bounds, and constants before arithmetic and threshold checks.
4. **Fixed:** correct the assertion that bulk upload already calls get_recipe;
   it returns minimal metadata. Keep bulk-upload ABV null unless a later ordinary
   recipe fetch occurs; do not introduce N+1 follow-up reads.
5. **Clarified:** enrichment belongs inside Database.get_recipe and the
   paginated-search assembler, not only in API response serialization; cover SSR.
6. **Fixed:** explicitly seed rinse in focused PostgreSQL fixtures; old
   SQLite migrations document units but are not a PostgreSQL seeding path.
7. **Clarified:** put the Estimated prefix in the backend display string.
8. **Clarified:** name the compact-card interactive-target selector as the
   change point for details/summary click handling.
9. **Clarified:** use textContent for new frontend strings; no exported
   shared escaping helper was identified.
10. **Do not adopt:** a rounded-down interval lower bound of zero is a conservative
    bound, not a zero-alcohol point estimate. Preserve outward interval rounding.
11. **Clarified:** enrich after offset/keyset over-fetch trimming; cover
    random ordering too. This is efficiency, not a correctness blocker.
12. **Do not adopt:** an arbitrary percentage of recipes displaying ABV is not an
    acceptance requirement; correct handling of incomplete data is. Historical
    CSV coverage is not evidence of current database coverage.
13. **Fixed:** include the existing pytest coverage gate in verification.
14. **Clarified:** test rerunnable migration SQL by direct application twice;
    the deployment runner intentionally skips recorded migration filenames.

Owner answered yes to item 1. Substantive corrections are applied to the subject.

## Dispatch 2

- Runner: Pi, `opencode-go/kimi-k3`, thinking `max`.
- Workflow: `effd88cf-9e30-440e-9444-9fe1d57cebaf`.
- Child: `d5ede3ee-05fc-463e-b71e-d83e1757bf05`.
- Report: `/tmp/recipe-abv-spec-review.lpf0LFQv.md`.
- Outcome: findings; no design blockers; not yet converged.
- **Fixed:** Markdown formatting had mangled unquoted numeric expressions.
  Backtick-wrap the finite check, cutoff formula, Decimal conversion, and method
  names. Verified the corrected literal expressions after the formatter ran.
- **Clarified:** explicit rerunnable trigger/function DDL, unit-name normalization
  tests, and database helper placement.
- **No change needed:** 88.7205 mL follows the existing project ounce conversion,
  not a claim to a more precise SI conversion.

## Dispatch 3 — converged

- Runner: Pi, `opencode-go/qwen3.8-max`, thinking `max`.
- Workflow: `851bff5d-8860-4c25-af89-e34332dc2077`.
- Child: `408c67b0-6506-4bfc-8fa1-6578d6e893e4`.
- Report: `/tmp/recipe-abv-spec-review.UrtqPEn1.md`.
- Outcome: clean; no Critical or Important findings. Stop the roster here.
- Minor clarifications adopted: distinguish depth-carrying cycle guards from
  depth-free UNION deduplication, acknowledge enrichment cost on existence probes,
  and require an isolated clean implementation worktree to preserve overlapping
  unrelated edits. Also record Node test registration and the reviewer environment's
  missing Docker prerequisite.
- No implementation or PostgreSQL runtime validation has occurred. Review verified
  the design against code; it is not evidence that implementation tests pass.

Three dispatches total: Paseo Opus 5 High, Pi Kimi K3 Max, Pi Qwen 3.8 Max.
The design is Refined and awaits final owner approval before implementation planning.
