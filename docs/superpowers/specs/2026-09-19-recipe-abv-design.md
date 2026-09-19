# Ingredient-only recipe ABV

**Status:** Refined

## Goal and scope

Show calculated **ABV before dilution** on cocktail recipe cards and recipe
pages. Represent missing ingredient strengths with volume-weighted intervals,
using observed ingredient-family ranges where possible. Expose assumptions
rather than presenting estimates as measurements.

Include a live ingredient-family range view, a backend calculator, additive
recipe-response data, JavaScript and server-rendered presentation, and tests.
Also include the owner-approved fix that clears a former parent's derived ABV
when its last child is deleted or reparented. Do not change recipe editing or
introduce new ingredient-entry fields.

Estimated served strength and structured preparation methods are deferred to
[issue #70](https://github.com/kthorn/cocktaildb/issues/70). Do not infer shaking,
stirring, or dilution from instructions. Sugar and acidity calculations are not
part of this change; keep volume handling separate enough to reuse later without
building a generic nutrient framework now.

## Agreed behavior

- A known leaf ingredient uses its recorded ABV, including a recorded zero.
- A category or unknown ingredient uses an observed family interval, not a
  parent's average ABV.
- With no observed family values, use an ingredient interval of **0–100%**.
- Weight every included ingredient's ABV bounds by its liquid volume.
- Display **Unknown** when the resulting interval is wider than **20 percentage
  points**. A width of exactly 20 is displayable. Apply this before display rounding.
- `to top` means **3 US fl oz**, or **88.7205 mL**, assumed per ingredient row.
- `to rinse` means **1 mL**, assumed per ingredient row.
- `each` contributes no modeled liquid volume or ethanol; disclose the omission.
- All other supported volume units use their existing `conversion_to_ml`.
- Assumptions remain visible in fine print. These intervals describe the model,
  not guaranteed bounds on the physical drink or an alcohol-free certification.

## Existing code and constraints

- `infrastructure/postgres/schema.sql` defines `ingredients.percent_abv`,
  `parent_id`, and `path`; unit conversion factors live in `units`.
- `roll_up_ingredient_values()` and migration 14 replace non-leaf composition
  values with averages of immediate children. Tests in
  `tests/test_ingredient_value_rollups.py` cover this behavior. These non-leaf
  values must not be treated as independent observations or exact strengths.
- `recipe_ingredients` stores only ingredient, amount, and unit; the unit already
  communicates top-up, rinse, or counted items. Migration 02 documents `to top`
  and `to rinse`; migration 01 documents `Each` and volume conversion factors.
- `Database.get_recipe()` retrieves ingredient rows via `_get_recipe_ingredients()`.
  `Database._search_recipes_paginated()` separately constructs ingredient rows
  from offset or keyset SQL. Its construction currently drops `conversion_to_ml`,
  even though both SQL queries select it.
- `api/models/responses.py::RecipeResponse` validates API output. The SSR route
  in `api/routes/pages.py` consumes database dictionaries directly.
- `src/web/js/recipeCard.js::createRecipeCard()` renders both compact and full
  cards. `api/templates/recipe.html` renders the initial/no-JavaScript page.
- Search can run through a supplied database cursor. Any new bulk lookup must
  use the same query executor/cursor, not open a separate connection.
- `api/db/db_analytics.py` has existing similarity/ordering volume proxies:
  top-up 90 mL, rinse 5 mL, and counted-item sentinels. These serve different
  analytics semantics and intentionally remain unchanged here. Do not reuse
  their permissive unknown-unit fallbacks for ABV. Harmonizing those analytics
  assumptions is a recorded follow-up, not part of this calculation.
- The canonical PostgreSQL schema does not seed units. Historical SQLite
  migrations are documentation, not executable PostgreSQL seeding instructions.
  Focused PostgreSQL tests must explicitly seed all units they use, including
  `to rinse`, absent from the minimal `pg_db_with_schema` fixture.

## Approach and alternatives

**Choose a regular PostgreSQL view plus a small Python calculator.** The view
exposes current observed family ranges, and Python handles volume assumptions,
interval arithmetic, and explanatory output. No stored recipe ABV or cache
invalidation is needed; subsequent reads reflect ingredient edits.

A materialized view or persisted min/max columns would add refresh/write-path
obligations before there is performance evidence to justify them. An entirely
Python-derived hierarchy would also work, but would duplicate hierarchy
aggregation across requests rather than expose one queryable database relation.
Neither is needed initially. No new dependency is required.

## Family observations and fallback

Add a regular view named `ingredient_abv_ranges`, with one row per ingredient:

- `ingredient_id`
- `min_percent_abv` and `max_percent_abv` (nullable)
- `observation_count` (zero when there are no observations)

For each ingredient, aggregate known **leaf** descendants, including itself if
it is a leaf. A leaf has no children by `parent_id`. A usable observation has a
finite ABV between 0 and 100, inclusive. Ignore null or invalid observations.
Never feed newly inferred values or values from current non-leaf parents back
into this view. Stored leaf values are assumed recorded: the legacy schema has
no measurement provenance, including for historical former-parent values (see
Rollup correction below).
Count each observed leaf once; do not average subgroup ranges or means.

Use `parent_id` relationships for ancestry so reparenting does not depend on a
separately refreshed textual path. A recursive query can propagate observed
leaves upward and aggregate by ancestor. Use cycle-safe traversal (for example,
distinct leaf/ancestor pairs with recursive `UNION`) so malformed ancestry cannot
make the query recurse forever. The view itself is read-only. The separate
last-child correction below fixes the existing rollup's stale-value behavior.

Resolve an ingredient as follows:

1. If it is a leaf with a valid recorded value, use `[value, value]` as recorded.
2. Otherwise consider itself, then its parent, then successive ancestors. Use
   the first candidate with any observed leaves. A category therefore uses its
   own subtree before looking outside it.
3. If no candidate has observations, use `[0, 100]` with an explicit unknown-strength
   note. Never borrow observations from an unrelated root family.

For inferred values, retain the selected family's ID, name, range, and observation
count while building explanations. A family with one observation produces a
point estimate but must remain labeled **estimated**; it is not an exact known
value. Multiple identical observations likewise remain inferred. The interval
is the observed min/max, not a confidence interval or a prediction guarantee.

Use a bounded-count bulk query for the unique ingredient IDs across the fetched
recipe(s), resolving their ancestor candidates against the view in SQL. Return
one resolved range and provenance record per requested ID. Do not query once
per ingredient, ancestor, or recipe. Detect missing resolution records rather
than silently dropping requested ingredients. Stop ancestor traversal safely
on cycles; if no usable observation is found, use the documented 0–100 fallback.
The depth-carrying resolution walk must use a visited-ID guard or PostgreSQL
`CYCLE`; recursive `UNION` alone only deduplicates the view's depth-free pairs.

## Rollup correction

The owner approved clearing a former parent's derived ABV when its final child
is deleted or moved. The current rollup only updates nodes that still have
children, leaving old averages on nodes that become leaves.

Add a narrowly scoped row-level AFTER DELETE / AFTER UPDATE OF parent_id trigger
on ingredients. For a deletion, or a real parent_id change, inspect OLD.parent_id.
If that parent still exists but now has no children, clear its percent_abv to
NULL. Do not clear a parent that still has children, a deleted parent, unrelated
leaves, or a node merely because a same-parent update occurred. The existing
statement-level rollup then recomputes its ancestors from the corrected values.

Retain the existing BEFORE-statement advisory lock and its before-row-lock
ordering. The clearing update changes percent_abv, not parent_id, so it must
not re-enter the new row trigger. Keep existing rollup recursion guards. Test
batch deletion/reparenting as well as single-row operations, and verify ancestors
are updated in the same transaction. Do not clear sugar/acidity in this ABV-only
fix; their equivalent last-child behavior is recorded as follow-up debt.

No provenance column or historical-data purge is introduced. Old childless
categories with retained averages are indistinguishable from genuine recorded
leaves using the existing schema. Do not automatically null existing leaf values
at migration time; flag this historical limitation for a data audit with the
owner before production rollout. The new fix prevents future occurrences but
cannot retroactively certify stored measurements. A later explicit edit of a
now-childless ingredient's ABV remains a legitimate recorded leaf value.

## Volume model and interval calculation

Normalize unit names with surrounding-whitespace removal and case folding;
recognize `to top`, `to rinse`, and `each` by canonical name, not numeric IDs.
Do not parse instruction text or guess other units from ingredient names.

Process rows in this order:

1. A provided negative or non-finite amount makes the result Unknown with an
   invalid-quantity explanation. Treat explicit numeric zero as an absent
   contribution (including special units); it does not require a known ABV.
2. `each`: exclude the entire row from numerator and denominator, and note the
   ingredient whose counted-item contribution was omitted. A missing amount
   does not prevent this explicitly agreed exclusion.
3. `to top` and `to rinse`: assign 88.7205 mL and 1 mL respectively. A missing
   amount is permitted. For a positive amount, these are still one assumption
   per row, not a multiplier; the unit describes an action, not repeated pours.
   Explain the assumed volume and ingredient in the notes.
4. Other units require a finite positive amount and a finite positive conversion
   factor; volume is their product. Reject missing/unsupported units, missing
   amounts, nonpositive conversion factors, and non-finite results with an
   Unknown result and an ingredient-specific explanation. Do not interpret an
   arbitrary non-volume unit as a solid merely because its conversion is null.

Let `v_i` be modeled volume in mL, and `[l_i, u_i]` be ABV percentages:

```
V = sum(v_i)
minimum_percent = sum(v_i * l_i) / V
maximum_percent = sum(v_i * u_i) / V
```

Normalize numeric inputs to stdlib Decimal before arithmetic: retain database
NUMERIC Decimals; convert finite REAL floats/integers using `Decimal(str(value))`;
construct constants and fallback bounds from decimal strings. Never multiply
Decimal strengths by float volumes. Check `is_finite()` before comparisons. Use
unrounded values for arithmetic; compare `sum(v_i * (u_i - l_i))` against `20 * V`
for the width cutoff, avoiding division-rounding artifacts at exactly 20. Use a
local Decimal precision sufficient for these database input types (50 significant
digits), and convert only final finite bounds to JSON numbers in the returned
plain dictionary. Format display from Decimal values, not serialized floats.
Test Decimal/float/int mixtures and the exactly-20 boundary explicitly.
No density model, ethanol/water contraction, ice melt, fruit extraction, or
rinse-retention model beyond the agreed assumptions is included.

An empty recipe, all-zero recipe, or recipe containing only excluded items has
no positive modeled volume: return Unknown, never divide by zero or report 0%.
An unresolved liquid quantity makes the entire result Unknown, because a
strength interval alone cannot repair an unknown denominator.

Unknown ABV is different: if its volume is known, propagate `[0,100]` normally.
For example, 60 mL of 40% spirit plus 5 mL of completely unknown strength gives
approximately 36.92–44.62%; the small unknown ingredient does not invalidate it.
Conversely, 30 mL of unknown strength plus 30 mL of recorded 0% mixer gives
0–50% and displays Unknown.

## Backend and API contract

Add `api/recipe_abv.py` for pure volume/interval calculation and presentation
metadata. Keep database access out of this module. Volume handling is a small
function in this module, not a configurable rules engine or plugin registry.
Future sugar/acid work can extract/reuse it when that second consumer exists.

Add a narrow database enrichment helper in `api/db/db_core.py` that accepts the recipe collection and
its query executor, performs the bulk range lookup once, and calls the same
calculator for every recipe. Call it inside `Database.get_recipe()` after ingredient
assembly, so SSR receives the same populated dictionary as API consumers. Also
call it inside `Database._search_recipes_paginated()` after over-fetch trimming,
on both pagination-return and list-return paths, including random ordering.
Use the transaction-bound executor when supplied. Do not rely on response-model
serialization or API route hooks to enrich SSR data. Existing tag/rating handlers
also call `get_recipe()` for existence checks; accept its additional bounded
lookup there rather than adding a separate retrieval mode in this feature.
Preserve the unit conversion field in search's intermediate ingredient rows.
Keep added calculation inputs internal; no need to expand public ingredient
response models merely to support the calculation.

Add an optional `abv` object to `RecipeResponse` with default null for compatibility
with existing mock/legacy producers. All production get/search paths populate
it, including the get-recipe reads already used after single create/update.
Bulk upload currently returns minimal created-recipe metadata directly, without
reading full recipes: preserve that contract with abv null; a subsequent normal
get/search returns the calculation. Do not add per-recipe bulk-upload reads.
Do not add ABV fields to recipe write requests or store caller-supplied ABV.

The result object contains:

- `status`: `calculated`, `estimated`, or `unknown`.
- `min_percent` and `max_percent`: unrounded numeric bounds, or both null when
  volumes cannot be resolved or there is no modeled volume. When the width
  exceeds 20, preserve computed bounds here but set status to `unknown`.
- `display`: a backend-formatted value, such as `26.7%`, `Estimated 20.0–30.0%`,
  or `Unknown`. Include the `Estimated` prefix here for estimated results.
  Both renderers use it verbatim, without duplicating status or formatting logic.
- `notes`: ordered, deduplicated strings identifying the ingredients/families and
  assumptions used, or reasons for Unknown. Treat them as untrusted text in HTML.

`calculated` means every included strength was recorded and no special-unit or
exclusion assumption was used. `estimated` means there was any inferred strength,
top-up/rinse assumption, or excluded counted ingredient, unless an Unknown rule
wins. Existing volume-unit conversion factors are accepted as the project's
standard, even where they approximate dashes or drops.

Format point values to one decimal place. For a nonzero point below 0.1%, use
`<0.1%` rather than suggesting zero alcohol. Format interval lower bounds downward
and upper bounds upward to one decimal place so rounding does not shrink the
interval or collapse a nonzero-width interval into a point. Decide Unknown using
the raw width, not this rounded display. Include `Estimated` in the backend
formatted string; a single-observation point must not appear as recorded strength.
A rounded-down interval lower bound of zero remains a conservative model bound,
not an assertion that the drink is alcohol-free.

Missing data is a modeled result, not an exception. Database/query failures are
real errors and retain existing error handling; do not silently return a guessed
ABV after a failed lookup. Do not return NaN or infinity in API output.

## Presentation

Place a compact **ABV before dilution** line near recipe metadata on both compact
and full cards, and in `api/templates/recipe.html`. Render the same display and
estimated/unknown status on SSR and hydrated JavaScript paths. If `abv` is null
or absent, omit the block for backwards compatibility; a populated unknown
result renders Unknown plus its explanation.

Use native `details`/`summary` for accessible expandable fine print when notes
exist. Do not rely only on a hover tooltip. Build the new JavaScript block with
DOM nodes and textContent for display and notes; no shared exported escaping
helper currently exists. Jinja autoescaping must remain enabled. Add details and
summary to createRecipeCard's compact-card interactive-target exclusion selector
so expanding notes does not trigger navigation.
Do not change JSON-LD nutrition fields or unrelated recipe formatting.

## Schema, rollout, and performance

Add the view to `infrastructure/postgres/schema.sql` and a new numbered PostgreSQL
migration after the latest existing migration (currently 15), with matching
`CREATE OR REPLACE VIEW` definitions and identical last-child correction function
and trigger definitions. Use `CREATE OR REPLACE FUNCTION` and
`DROP TRIGGER IF EXISTS` before recreating the trigger for idempotency.
Do not modify historical SQLite migrations 01/02.
The new migration installs the view and targeted rollup correction; it is rerunnable,
does not rewrite existing ingredient measurements, and does not require destructive
initialization. Add its rollback under `migrations/rollbacks/`: drop the new trigger
and function, then the view; leave pre-existing rollup functions/triggers intact.
Test rerunnability by directly executing the SQL twice; the deployment migration
runner intentionally skips already-recorded migration filenames.

Apply the migration before deploying API code that queries the view. Code rollback
can leave the unused view and beneficial last-child correction in place. If the
schema change must also be rolled back, restore old code first; note that removing
the correction restores the old stale-average behavior. No production deployment
or database modification is authorized by this design work.

Preserve search ordering, pagination/cursors, tags, ratings, group inventory
filtering, and authorization. ABV describes the recipe's specified ingredients,
not substitutions from the user's inventory. Query count must not grow with the
number of recipes or their ingredients. Capture an EXPLAIN ANALYZE for the bulk
lookup on a representative local dataset during implementation; start with the
regular view and existing parent_id index. Add caching/materialization only if
measurement demonstrates the need, as a separate decision.

## Tests and acceptance

Use existing pytest/PostgreSQL and Node test patterns; no new test framework.

1. View: zero and null observations, multiple tree depths, leaf-only aggregation,
   unequal branch sizes, single observations, empty families, and independent
   roots. Verify view results after edits, inserts, deletes, and reparenting.
   Rollup regression: loss of the last child clears the former parent's ABV and
   removes it as an observation; higher ancestors recalculate; remaining-child
   parents still average; unrelated measured leaves and no-op reparenting are
   unchanged. Cover multi-row changes, direct SQL, and existing lock ordering.
2. Resolution: recorded leaf versus parent average; category's own subtree;
   nearest populated ancestor; one observed sibling; no observations => 0–100;
   no cross-root borrowing. Test cycle-safe read behavior without invoking the
   existing rollup writer on a cyclic hierarchy.
3. Calculator: exact mix; narrow/wide unknown-strength contributions; width exactly
   20 and just above; inferred point versus recorded point; true zero; null versus
   zero; top-up 88.7205 mL; rinse 1 mL; `each` exclusion; special-unit amount policy;
   unit-name case/whitespace variants; unsupported units;
   missing/negative/non-finite quantities; invalid conversions;
   empty/all-excluded/all-zero recipes; rounding and deduplicated explanations.
4. Integration: identical results in single-get, offset search, keyset search,
   and create/update follow-up reads. Include the transaction-bound executor and
   inventory search and random ordering. Verify bounded query count and fresh
   results after ABV edits. Bulk upload keeps its minimal response with abv null;
   subsequent normal reads populate it without changing bulk-upload query count.
5. Migration: initialize with the canonical schema and explicit unit fixtures,
   including rinse; directly apply the new migration twice; confirm matching view
   and trigger behavior and no mutation of pre-existing stored composition data.
6. UI/API: response-model preservation, SSR and card display for calculated,
   estimated, unknown, and missing objects; notes with HTML-sensitive names;
   keyboard-accessible details; expanding notes does not navigate compact cards.
7. Run relevant existing recipe, pagination, ingredient-rollup, and page tests;
   run the existing pytest coverage gate (80% across api), repository formatter
   checks, and changed-file diagnostics. Register new Node contract tests in
   `tests/test_frontend_node.py` when they must run under pytest. Preserve unrelated
   working-tree edits: implement in a separate clean worktree from committed HEAD,
   without moving or committing the other work. Record external test prerequisites;
   the final design reviewer could not run PostgreSQL tests because Docker was
   unavailable in its environment.

## Residual limitations

Observed family extrema may understate the true strength range of an unobserved
product. Excluding `each` can omit meaningful juice or alcohol in unusual recipes;
it is an explicit user-selected approximation, not automatic solid detection.
Top-up and rinse volumes may differ from actual preparation. Notes expose these
limitations. Recipe ABV is not a measure of served strength or a safety claim.
