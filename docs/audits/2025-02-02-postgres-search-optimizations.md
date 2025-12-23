# Postgres Search Optimizations (Follow-ups)

Context: After migrating to Postgres, the search and infinite scroll paths can still be improved beyond cursor pagination. This note captures the remaining proposed optimizations.

## Priority Proposals

1) Replace random ordering on the homepage
   - Current: `ORDER BY RANDOM()` with pagination, which forces a full scan and sort each page.
   - Proposal A: Add a `random_sort` column to `recipes`, populate once, index it, and paginate by `(random_sort, id)`.
   - Proposal B: For a single session, seed a deterministic order (e.g., hash of `id` + seed) only for the first page, cache client-side, and avoid paginated random sorts entirely.

2) Make ORDER BY index-friendly
   - Current: `ORDER BY CASE ... CAST(... AS TEXT)` blocks index usage.
   - Proposal: Build SQL with validated dynamic order fields, e.g. `ORDER BY r.name`, `r.avg_rating`, `r.created_at` and always include `id` for tie-breaks.
   - Add indexes: `recipes(name, id)`, `recipes(avg_rating, id)`, `recipes(created_at, id)`.

3) Improve ingredient path filtering
   - Current: `path LIKE %/id/%` with a btree index is not selective.
   - Proposal A: Convert `ingredients.path` to `ltree` or `int[]` and add a GIN index for ancestor/descendant queries.
   - Proposal B (minimal): Add `GIN (path gin_trgm_ops)` for `%/id/%` pattern scans.

4) Ensure Postgres text search indexes are present
   - Confirm `pg_trgm` extension is enabled and `idx_recipes_name_trgm` exists.
   - Without this, `ILIKE %query%` searches will degrade quickly at scale.

## Operational Checks

- Run `EXPLAIN (ANALYZE, BUFFERS)` on `/recipes/search` for common queries and confirm index usage.
- Check autovacuum/ANALYZE settings after migration to keep planner stats fresh.
