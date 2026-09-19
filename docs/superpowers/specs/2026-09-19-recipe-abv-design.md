# Ingredient-only recipe ABV

**Status:** Draft — ready for codebase-grounded review

## Goal and scope

Show calculated **ABV before dilution** on cocktail recipe cards and recipe
pages. Represent missing ingredient strengths with volume-weighted intervals,
using observed ingredient-family ranges where possible. Expose assumptions
rather than presenting estimates as measurements.

Include a live ingredient-family range view, a backend calculator, additive
recipe-response data, JavaScript and server-rendered presentation, and tests.
Do not change recipe editing or introduce new ingredient-entry fields.

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
Never feed inferred values or calculated parent means back into this view.
Count each observed leaf once; do not average subgroup ranges or means.

Use `parent_id` relationships for ancestry so reparenting does not depend on a
separately refreshed textual path. A recursive query can propagate observed
leaves upward and aggregate by ancestor. Use cycle-safe traversal (for example,
distinct leaf/ancestor pairs with recursive `UNION`) so malformed ancestry cannot
make the query recurse forever. This is a regular read-only view, not a trigger
or an alteration of the existing rollup behavior.

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

Use unrounded values for arithmetic and the width cutoff. Keep sufficient
numeric precision for the exactly-20 boundary; test that boundary explicitly.
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

Add a narrow database enrichment helper that accepts the recipe collection and
its query executor, performs the bulk range lookup once, and calls the same
calculator for every recipe. Use it for single-recipe and search responses.
Preserve the unit conversion field in search's intermediate ingredient rows.
Keep added calculation inputs internal; no need to expand public ingredient
response models merely to support the calculation.

Add an optional `abv` object to `RecipeResponse` with default null for compatibility
with existing mock/legacy producers. All production get/search paths populate
it, including the get-recipe reads already used after create/update/bulk upload.
Do not add ABV fields to recipe write requests or store caller-supplied ABV.

The result object contains:

- `status`: `calculated`, `estimated`, or `unknown`.
- `min_percent` and `max_percent`: unrounded numeric bounds, or both null when
  volumes cannot be resolved or there is no modeled volume. When the width
  exceeds 20, preserve computed bounds here but set status to `unknown`.
- `display`: a backend-formatted value, such as `26.7%`, `20.0–30.0%`, or `Unknown`.
  Both renderers use this rather than reimplementing threshold/rounding rules.
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
the raw width, not this rounded display. Prefix estimated displays in the UI with
`Estimated`; a single-observation point must not appear as recorded strength.

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
exist. Do not rely only on a hover tooltip. JavaScript should use textContent or
an existing escaping helper for the new display and notes; Jinja autoescaping
must remain enabled. Expanding notes must not trigger compact-card navigation.
Do not change JSON-LD nutrition fields or unrelated recipe formatting.

## Schema, rollout, and performance

Add the view to `infrastructure/postgres/schema.sql` and a new numbered PostgreSQL
migration after the latest existing migration (currently 15), with matching
`CREATE OR REPLACE VIEW` definitions. Do not modify historical SQLite migrations
01/02. The new migration is additive and rerunnable, does not rewrite ingredient
values, and does not require destructive initialization. Add its rollback under
`migrations/rollbacks/` following the current repository convention.

Apply the additive view migration before deploying API code that queries it.
Code rollback can leave the unused view in place; drop it only after old code is
restored. No production deployment or database modification is authorized by
this design work.

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
2. Resolution: recorded leaf versus parent average; category's own subtree;
   nearest populated ancestor; one observed sibling; no observations => 0–100;
   no cross-root borrowing. Test cycle-safe read behavior without invoking the
   existing rollup writer on a cyclic hierarchy.
3. Calculator: exact mix; narrow/wide unknown-strength contributions; width exactly
   20 and just above; inferred point versus recorded point; true zero; null versus
   zero; top-up 88.7205 mL; rinse 1 mL; `each` exclusion; special-unit amount policy;
   unsupported units; missing/negative/non-finite quantities; invalid conversions;
   empty/all-excluded/all-zero recipes; rounding and deduplicated explanations.
4. Integration: identical results in single-get, offset search, keyset search,
   and create/update follow-up reads. Include the transaction-bound executor and
   inventory search. Verify bounded query count and fresh results after ABV edits.
5. Migration: initialize with the canonical schema; apply the new migration twice;
   confirm matching results and no mutation of stored composition data.
6. UI/API: response-model preservation, SSR and card display for calculated,
   estimated, unknown, and missing objects; notes with HTML-sensitive names;
   keyboard-accessible details; expanding notes does not navigate compact cards.
7. Run relevant existing recipe, pagination, ingredient-rollup, and page tests;
   run repository formatter checks and changed-file diagnostics. Preserve
   unrelated working-tree edits and record any external test prerequisites.

## Residual limitations

Observed family extrema may understate the true strength range of an unobserved
product. Excluding `each` can omit meaningful juice or alcohol in unusual recipes;
it is an explicit user-selected approximation, not automatic solid detection.
Top-up and rinse volumes may differ from actual preparation. Notes expose these
limitations. Recipe ABV is not a measure of served strength or a safety claim.
