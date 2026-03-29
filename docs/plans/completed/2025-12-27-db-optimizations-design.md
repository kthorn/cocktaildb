# Database Optimizations Design (Postgres)

**Goal:** Improve query performance and maintainability for ordering and case-insensitive search, and extend ingredient metadata. Postgres-only; remove remaining SQLite-only code paths.

**Out of Scope:**
- Replacing `ORDER BY RANDOM()` (explicitly deferred)
- Ingredient path filtering migration to `ltree` (explicitly omitted for now)

---

## Problem Statement

- ORDER BY paths currently block index usage due to CASE/CAST patterns and dynamic ordering without a strict whitelist.
- Case-insensitive search uses liberal `LOWER()` calls, which can defeat index usage and complicate query logic.
- Ingredients are missing structured fields for `percent_abv`, `percent_sugar`, `titratable_acidity`, and `url`.
- Query construction logic is scattered, with legacy SQLite branching still present.

## Proposed Changes

### 1) Index-Friendly ORDER BY

- Replace CASE/CAST-based ordering with validated dynamic ORDER BY fields.
- Always include `id` as a tiebreaker for stable pagination.
- Add btree indexes `(field, id)` for each supported order column.

**Order fields (initial set, validate at API boundary):**
- `recipes.name`
- `recipes.avg_rating`
- `recipes.created_at`
- `recipes.rating_count`

**Expected impact:** planner can use indexes for pagination; reduces sort cost.

### 2) Case-Insensitive Search with `citext`

- Enable/confirm `citext` extension.
- Migrate relevant name/search columns to `citext` (starting with `recipes.name`, `ingredients.name`; extend based on query audit).
- Remove `LOWER()` usage throughout API query construction and tests.
- Retain `pg_trgm` for substring `ILIKE %query%` searches where needed.

**Notes:** This assumes `pg_trgm` is already present; confirm existing index coverage and adjust as needed.

### 3) Ingredient Metadata Fields

Add columns to `ingredients`:
- `percent_abv` (numeric, nullable, constrained 0-100)
- `sugar_g_per_l` (numeric, nullable, constrained 0-1000)
- `titratable_acidity_g_per_l` (numeric, nullable, constrained 0-100)
- `url` (string, nullable)

Add basic CHECK constraints for bounds if known; these fields will not be used for searching.

### 4) Code Organization / Refactor

- Consolidate SQL construction helpers in `api/db/sql_queries.py` and shared validation helpers in `api/db/db_utils.py`.
- Remove or isolate SQLite-only branching paths.
- Centralize order-by whitelist validation to reduce duplication and guard against unsafe sorting.

---

## Data Migration Strategy

1) Add new indexes for ORDER BY fields.
2) Add `citext` extension (if missing) and migrate column types.
3) Update queries to remove `LOWER()` usage.
4) Add ingredient chemistry columns with constraints.

Migrations should be additive or type-altering only; no data loss expected.

---

## Risks & Mitigations

- **citext behavior changes**: equality/uniqueness may change for mixed-case values.
  - Mitigation: audit for duplicates before type change; confirm with a one-time report query.
- **Over-indexing**: too many btree indexes can slow writes.
  - Mitigation: limit to confirmed order fields and revisit after EXPLAIN.
- **Legacy SQLite logic**: leaving residual branches can cause drift.
  - Mitigation: remove or gate with explicit Postgres-only checks during refactor.

---

## Validation Plan

- Run `EXPLAIN (ANALYZE, BUFFERS)` on primary search and listing endpoints to confirm index usage.
- Regression tests for search and ordering behaviors.
- Spot-check case-insensitive search results after `citext` migration.

---

## Open Questions

- Which additional text columns should be migrated to `citext` (tags, units, user-facing labels)?

