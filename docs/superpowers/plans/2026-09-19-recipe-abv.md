# Recipe ABV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add whole-percent ingredient-only ABV estimates to every recipe display, with family-derived intervals and explicit assumptions.

**Architecture:** A live PostgreSQL view aggregates known leaf ABVs. One bulk query resolves nearest populated families, and a pure Decimal calculator enriches database recipe dictionaries before API/SSR rendering. A narrow trigger clears stale ABV when a parent loses its last child.

**Tech Stack:** PostgreSQL 15+, Python/Decimal, FastAPI/Pydantic, vanilla JavaScript, Jinja, pytest, Node built-in assertions.

**Spec:** `docs/superpowers/specs/2026-09-19-recipe-abv-design.md` (approved; latest owner change is whole-percent display).

## Global Constraints

- Ingredient-only **ABV before dilution**; no served-strength, preparation, sugar, or acid feature.
- Known leaf values, including zero, are recorded; current parent means are never observations.
- Nearest populated family gives observed leaf min/max; no observations gives **0–100%**.
- A width **greater than 20 percentage points** is Unknown; exactly 20 is displayable. Check before display rounding.
- `to top` = **88.7205 mL** per row; `to rinse` = **1 mL** per row; `each` excluded and disclosed.
- Special-unit positive amounts do not multiply these per-row assumptions; explicit zero contributes nothing; negative/non-finite amounts are invalid.
- Point display rounds half up to whole-percent ABV; positive points below 1% display `<1%`. Interval endpoints round outward to whole percentages. Keep raw bounds in the API.
- The backend includes `Estimated` in its display string. Both renderers show it verbatim using safe text output.
- One range lookup per fetched recipe collection, using the caller's executor/cursor; no per-recipe/per-ingredient queries or caches.
- Preserve analytics proxies and write-request contracts. Bulk upload keeps minimal responses with `abv: null`.
- No new dependency, deployment, main-branch changes, push, or merge. Work only in the feature worktree.
- Python: `~/miniforge3/envs/cocktaildb/bin/python`. Node 22.7+ (22.22.2 available).
- TDD: tests before implementation, record RED/GREEN output. Focused pytest uses `-o addopts=''`; the final full suite retains the configured 80% coverage gate.
- Canonical formatter command: `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files`.

## Review Focus

1. A category becomes a leaf after deleting/reparenting its last child: clear only its derived ABV and recompute higher ancestors (Task 1).
2. Cyclic raw-SQL hierarchy and depth-carrying walks: terminate without borrowing unrelated observations (Task 1).
3. Small unknown strength vs unknown volume: weighted range for the former, whole-recipe Unknown for the latter (Task 2).
4. Precision at exactly 20 points and intervals that collapse under naive rounding: compare cross-products and display outward integer bounds (Task 2).
5. SSR hydration, HTML-sensitive ingredient names, and compact-card details clicks: same safe display with no accidental navigation (Task 3).

## File responsibilities and interfaces

- `infrastructure/postgres/schema.sql`, migration 16 and rollback: range view and last-child correction only.
- `api/db/sql_queries.py`: `RESOLVE_INGREDIENT_ABV_SQL`, accepting `%(ingredient_ids)s` as an integer array.
- `api/recipe_abv.py`: `calculate_recipe_abv(ingredients, ranges) -> dict`, pure Decimal math plus display/notes.
- `api/db/db_core.py`: `_add_recipe_abv(recipes, execute_query)` helper, called by get/search after assembly/trimming.
- `api/models/responses.py`: `RecipeABVResponse` and optional `RecipeResponse.abv`.
- `src/web/js/recipeCard.js`, `api/templates/recipe.html`: presentation only, no arithmetic.
- Focused tests beside existing recipe, migration, and frontend contracts.

The resolved-range mapping is keyed by integer ingredient ID. Each value has
`min_percent_abv`, `max_percent_abv`, `observation_count`, `family_id`,
`family_name`, and `source` (`recorded`, `family`, or `unknown`). SQL rows also
include `ingredient_id`. Recorded leaf rows use their own ID/name; unknown rows
have null family identity, zero count, and 0/100 bounds. Keep numbers as returned
by psycopg2 until the pure calculator normalizes them.

Output contract: `status` (`calculated`, `estimated`, `unknown`),
`min_percent`/`max_percent` (JSON numbers or both null), `display` (string),
`notes` (ordered deduplicated strings). Preserve raw numeric bounds for too-wide
Unknown results; unresolved/no volume returns null bounds.

---

### Task 1: Current family ranges and last-child rollup correction

**Files:**
- Modify `infrastructure/postgres/schema.sql`, `api/db/sql_queries.py`.
- Create `migrations/16_migration_add_recipe_abv_ranges.sql` and `migrations/rollbacks/16_rollback_recipe_abv_ranges.sql` (verify 16 remains next before writing).
- Create `tests/test_recipe_abv_ranges.py`; extend `tests/test_ingredient_value_rollups.py` only for tightly related regressions.

**Interfaces:** Produces `ingredient_abv_ranges(ingredient_id, min_percent_abv, max_percent_abv, observation_count)` and `RESOLVE_INGREDIENT_ABV_SQL` with the exact mapping above. Consumes existing `ingredients.parent_id`, `percent_abv`, and statement rollup/advisory-lock behavior.

- [ ] Write PostgreSQL tests before schema/query code. Use existing `pg_db_with_schema`/`db_instance` fixtures and the existing direct-SQL patterns. Begin with:

```python
from decimal import Decimal
from api.db.sql_queries import RESOLVE_INGREDIENT_ABV_SQL


def test_unknown_gin_uses_nearest_observed_leaf_range(db_instance):
    db_instance.execute_query("""
        INSERT INTO ingredients (id, name, parent_id, percent_abv) VALUES
        (1, 'Spirits', NULL, NULL), (2, 'Gin', 1, NULL),
        (3, 'Gin A', 2, 40), (4, 'Gin B', 2, 50),
        (5, 'Unknown gin', 2, NULL), (6, 'Vodka', 1, 35)
    """)
    rows = db_instance.execute_query(
        RESOLVE_INGREDIENT_ABV_SQL, {'ingredient_ids': [5]}
    )
    assert rows[0]['min_percent_abv'] == Decimal('40')
    assert rows[0]['max_percent_abv'] == Decimal('50')
    assert rows[0]['family_id'] == 2
    assert rows[0]['observation_count'] == 2
    assert rows[0]['source'] == 'family'
```

- [ ] Add cases for recorded zero, category's own subtree, deep/uneven branches, one observation, independent empty root => 0/100, no-op parent update, remaining-child parent, last-child deletion/reparenting, higher ancestors, and multi-row operations. For the last-child case create root → category → known leaf plus another known root child; deleting the category's leaf must leave category ABV NULL and root reflecting only its remaining observed branch. Verify unrelated recorded leaves are unchanged.
- [ ] Add cycle tests using direct SQL in a controlled fixture, asserting termination for both depth-free aggregation and depth-carrying resolution. Add migration rerun tests following `test_rollup_migration_backfills_and_can_be_retried`; execute the new SQL twice against schema-initialized fixtures and verify no historical leaf measurements were erased.
- [ ] Run RED: `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_recipe_abv_ranges.py -q -o addopts=''`. An unavailable Docker runtime is not RED evidence; report it separately and still leave executable PG tests.
- [ ] Implement the view as known-leaf → ancestor propagation. A concrete CTE shape is:

```sql
WITH RECURSIVE observations(leaf_id, ingredient_id, percent_abv) AS (
  SELECT i.id, i.id, i.percent_abv FROM ingredients i
  WHERE i.percent_abv BETWEEN 0 AND 100
    AND NOT EXISTS (SELECT 1 FROM ingredients c WHERE c.parent_id = i.id)
  UNION
  SELECT o.leaf_id, i.parent_id, o.percent_abv
  FROM observations o JOIN ingredients i ON i.id = o.ingredient_id
  WHERE i.parent_id IS NOT NULL
)
SELECT i.id AS ingredient_id,
       MIN(o.percent_abv) AS min_percent_abv,
       MAX(o.percent_abv) AS max_percent_abv,
       COUNT(o.leaf_id) AS observation_count
FROM ingredients i LEFT JOIN observations o ON o.ingredient_id = i.id
GROUP BY i.id;
```

- [ ] Implement the resolver with a requested-ID ancestor walk carrying depth and a visited array. Select the first populated view row per requested ingredient by ascending depth (e.g. lateral ordered subquery). Bound cycles with `NOT next_id = ANY(visited)`. Produce one record per existing requested ingredient, including explicit unknown fallback. A known leaf is `recorded`; non-leaf/self or ancestor-derived rows are `family`.
- [ ] Implement a row trigger function that checks deletion or `OLD.parent_id IS DISTINCT FROM NEW.parent_id`, and runs:

```sql
UPDATE ingredients p SET percent_abv = NULL
WHERE p.id = OLD.parent_id
  AND p.percent_abv IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ingredients c WHERE c.parent_id = p.id);
```

Attach as AFTER DELETE OR UPDATE OF parent_id. Do not change sugar/acidity or existing advisory lock/rollup recursion guards. Existing outer AFTER STATEMENT rollup must handle ancestor recomputation. In the forward migration use a transaction, `CREATE OR REPLACE` definitions and `DROP TRIGGER IF EXISTS`; rollback removes only this new trigger/function/view. Keep canonical schema and migration equivalent.
- [ ] Run GREEN on the new tests and `tests/test_ingredient_value_rollups.py`. Capture `EXPLAIN (ANALYZE, BUFFERS)` for a bulk resolver lookup on fixture or representative local data; state dataset size. If Docker remains inaccessible, report PG execution as blocked, never passing.
- [ ] Self-review and commit only Task 1 files: `feat: derive ingredient ABV ranges and clear stale rollups`. Generate the review package from the BASE captured before this task, not HEAD~1, and report tests, risks, and commit IDs.

### Task 2: Pure ABV calculator and recipe enrichment

**Files:**
- Create `api/recipe_abv.py`, `tests/test_recipe_abv.py`, `tests/test_recipe_abv_integration.py`.
- Modify `api/db/db_core.py`, `api/models/responses.py`.

**Interfaces:** Consumes Task 1's query/mapping exactly. Produces `calculate_recipe_abv(ingredients: list[dict], ranges: dict[int, dict]) -> dict`, `Database._add_recipe_abv(self, recipes: list[dict], execute_query) -> None`, and additive `RecipeABVResponse`/`RecipeResponse.abv`. Ingredient dictionaries include amount, unit_name, conversion_to_ml and ingredient ID/name.

- [ ] Write pure tests first with an inline row helper and exact literal expectations:

```python
from api.recipe_abv import calculate_recipe_abv


def row(i, amount, unit='ml', factor=1):
    return dict(ingredient_id=i, ingredient_name=f'Ingredient {i}',
                amount=amount, unit_name=unit, conversion_to_ml=factor)


def strength(lo, hi, source='recorded'):
    return dict(min_percent_abv=lo, max_percent_abv=hi,
                observation_count=1 if source != 'unknown' else 0,
                family_id=1 if source != 'unknown' else None,
                family_name='Family' if source != 'unknown' else None,
                source=source)


def test_small_unknown_has_useful_integer_range():
    result = calculate_recipe_abv([row(1, 60), row(2, 5)],
        {1: strength(40, 40), 2: strength(0, 100, 'unknown')})
    assert result['status'] == 'estimated'
    assert result['display'] == 'Estimated 36–45%'
    assert result['min_percent'] > 36


def test_exactly_twenty_points_is_displayable():
    result = calculate_recipe_abv([row(1, 80), row(2, 20)],
        {1: strength(0, 0), 2: strength(0, 100, 'unknown')})
    assert result['display'] == 'Estimated 0–20%'
    assert result['status'] == 'estimated'
```

- [ ] Parameterize point display (26.5→27%, 0→0%, 0.4→<1%), fractional interval outward rounding, Decimal/float/int inputs, cutoff just above/below 20, recorded/inferred identical endpoints, tiny unknown vs base-spirit unknown, finite validation, non-volume/missing units/amounts, special-unit zero/null/positive/negative quantities, mixed-case/whitespace unit names, all-empty/excluded/zero rows, HTML-sensitive names, and duplicate notes. Top/rinse test exact modeled ratios using approved volumes, not approximations.
- [ ] Run RED: `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_recipe_abv.py -q -o addopts=''`.
- [ ] Implement the pure calculator with `Decimal(str(value))`, local precision 50, named constants, small volume helper, and accumulated notes. Classify invalid/missing volume before division. Do not silently ignore a missing strength mapping: return Unknown with an explicit missing-data reason, retaining no invented exact bound. The normal unknown-strength SQL result is different: propagate its 0/100 interval.

```python
# after validated contributions, all these values are Decimal
low_sum = sum(volume * lo for volume, lo, hi in contributions)
high_sum = sum(volume * hi for volume, lo, hi in contributions)
width_sum = sum(volume * (hi - lo) for volume, lo, hi in contributions)
too_wide = width_sum > Decimal('20') * total_volume
# point: quantize(Decimal('1'), rounding=ROUND_HALF_UP)
# interval: lower ROUND_FLOOR, upper ROUND_CEILING, integer display
```

- [ ] Use a Pydantic response class with Literal statuses, optional float min/max, display string, and `Field(default_factory=list)` notes; `RecipeResponse.abv` defaults to None. Do not add write request fields.
- [ ] Add one narrow enrichment helper that collects unique IDs, calls `RESOLVE_INGREDIENT_ABV_SQL` once via the passed executor, indexes returned rows, and invokes the calculator for each recipe. Empty ingredient lists need no lookup. Get path calls it after ingredient assembly; search preserves conversion factors in intermediate rows and enriches after each applicable pagination trim. Cover the nonpagination list path too. Leave authorization and bulk-upload fast path unchanged.
- [ ] Write tests for mocked executor query count, same-cursor use, SQL failure propagation, missing returned IDs, model serialization, and identical get/search payloads. Add PG integration coverage for recorded and unknown ingredients, offset/keyset/random/list/inventory paths, fresh results after ABV edits, and create/update reads. Verify bulk upload remains null then ordinary get produces ABV.
- [ ] Run calculator and integration tests plus focused existing recipe/search/special-unit regressions. Run no-Docker tests even if PG remains blocked. Do not weaken coverage configuration to conceal a full-suite gap.
- [ ] Self-review and commit: `feat: calculate ingredient-only recipe ABV with uncertainty`. Generate task review package and include RED/GREEN, exact commands, modified files, risks, and BASE/HEAD in the report.

### Task 3: Safe whole-percent recipe display and final verification

**Files:**
- Modify `src/web/js/recipeCard.js`, `api/templates/recipe.html`.
- Create `tests/test_recipe_abv_display.mjs`; register in `tests/test_frontend_node.py`.
- Extend `tests/test_page_route_contracts.py` for SSR ABV cases.
- Update only narrowly necessary `src/web/recipe-card.css` styles if the existing styles cannot carry the native block.

**Interfaces:** Consumes `recipe.abv` exactly as Task 2 returns it; no client-side arithmetic. No new API calls or frontend dependencies.

- [ ] Write failing SSR tests using the existing route mock/template patterns: calculated `27%`, estimated `Estimated 20–30%`, Unknown with explanation, absent/null block omitted, `<script>` ingredient notes escaped, no JSON-LD nutrition additions.
- [ ] Write executable Node assertions against the actual card builder with the repository's existing DOM/stub/import patterns. Verify compact/full cards, safe textContent, absent/null omission, literal integer backend displays, notes details/summary, and that clicking summary does not navigate. Register the script in the pytest Node-test list.

```javascript
assert.equal(abvLabel.textContent, 'ABV before dilution');
assert.equal(abvValue.textContent, 'Estimated 20–30%');
assert.equal(note.textContent, '<script>alert(1)</script>: assumed 1 mL rinse');
assert.equal(navigationCountAfterSummaryClick, 0);
```

These names refer to test-local DOM handles returned by the existing test harness;
resolve actual selectors from the implemented block, not source-text snapshots.
- [ ] Run RED for the new Node and SSR tests. Implement a DOM-created block near metadata using `createElement` and textContent; insert it after the card's base innerHTML assignment. Use an inline block unless a real second JS consumer needs extraction. Add `details, summary` to the compact-card interactive-target exclusion.

```html
{% if recipe.abv %}
<div class="recipe-abv">
  <strong>ABV before dilution</strong>: {{ recipe.abv.display }}
  {% if recipe.abv.notes %}
  <details><summary>Calculation notes</summary><ul>
    {% for note in recipe.abv.notes %}<li>{{ note }}</li>{% endfor %}
  </ul></details>
  {% endif %}
</div>
{% endif %}
```

- [ ] Run GREEN: new Node test, existing recipe-card Node contracts, SSR contracts, and new Python calculator/integration tests. Use the same backend-provided display verbatim in both rendering paths.
- [ ] Final validation: run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/ -q` once with configured coverage; run `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files`; run Node checks for modified JS; run active LSP diagnostics for changed supported files when available. Do not label an unavailable Docker/full-suite check as a pass. Preserve logs and distinguish pre-existing failures from regressions.
- [ ] Commit: `feat: display recipe ABV ranges and calculation notes`. Generate this task's review package. Also prepare the complete branch review package from the recorded implementation start commit and include all task reports, deferred minors, and validation evidence for the final independent reviewer.

## Execution and review

Tasks run sequentially with one writer. A fresh `worker-integration` on
`openai-codex/gpt-5.6-luna:max` implements each task, and a fresh `task-reviewer`
on the same model checks spec compliance and quality after each. Review packages
must include actual BASE..HEAD diffs. Fixes remain with implementers, followed by
scoped re-review. A final `reviewer` on `openai-codex/gpt-5.6-terra:max` reviews
the whole branch. No automatic review of this implementation plan is needed.

The owner explicitly authorized implementation after the display update; no
additional plan approval pause is required. Do not merge/push/deploy automatically.
If external PostgreSQL tooling stays unavailable, complete the code and runnable
checks, leave the database tests in place, and report the unverified gate.
