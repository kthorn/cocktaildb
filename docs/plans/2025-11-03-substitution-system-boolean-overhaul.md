# Ingredient Substitution System: Boolean Overhaul

**Date:** 2025-11-03
**Issue:** bd-53
**Status:** Design Complete, Ready for Implementation

## Overview

Replace the complex 3-level integer substitution system with a simple boolean flag. This change addresses user confusion and implementation bugs while maintaining flexible ingredient matching.

## Problem Statement

**Current Issues:**
1. **User Complexity:** The 3-level system (0=none, 1=parent, 2=grandparent, null=inherit) is confusing for users
2. **Implementation Bugs:** Complex inheritance logic with 3-level COALESCE is bug-prone (see bd-65: ingredient recommendations don't consider substitutability)
3. **Maintenance Burden:** Hard to debug and extend the current system

**Current System:**
- `substitution_level` INTEGER (0, 1, 2, or null)
- 0 = exact match only
- 1 = parent-level substitution (siblings)
- 2 = grandparent-level substitution (cousins)
- null = inherit from parent (up to 3 levels)

## Proposed Solution

### New Schema

```sql
-- Change in ingredients table
-- OLD: substitution_level INTEGER DEFAULT 0
-- NEW: allow_substitution BOOLEAN NOT NULL DEFAULT 0
```

**Key Properties:**
- Explicit boolean: true or false (no null/inheritance)
- NOT NULL constraint ensures every ingredient has a clear value
- Default to false (conservative approach)

### Matching Logic

**Recursive substitution algorithm:**

When checking if `user_ingredient` can satisfy `recipe_ingredient`:

1. **Direct match:** If IDs are equal → match
2. **Substitution gate:** If `recipe_ingredient.allow_substitution = false` → no match
3. **Sibling match:** If they share same parent AND both have `allow_substitution = true` → match
4. **Parent match:** If user has the recipe ingredient's parent → match
5. **Recursive upward:** If recipe ingredient's parent has `allow_substitution = true`, recursively check if user ingredient can match the parent

**Example Hierarchy:**
```
Spirit (allow_sub=true)
  ├─ Whiskey (allow_sub=true)
  │   ├─ Bourbon (allow_sub=true)
  │   └─ Rye (allow_sub=true)
  └─ Rum (allow_sub=false)
      └─ Dark Rum (allow_sub=true)
```

**Recipe requires "Bourbon" with `allow_substitution=true`:**
- ✅ Bourbon (exact match)
- ✅ Whiskey (parent)
- ✅ Rye (sibling, both have allow_sub=true)
- ✅ Spirit (grandparent, via recursive traversal through Whiskey)
- ❌ Rum (uncle with allow_sub=false blocks substitution)
- ❌ Dark Rum (cousin blocked by non-substitutable Rum)

**Bidirectional matching:** If recipe calls for "Whiskey" and user has "Bourbon", it matches (children can substitute for parents via existing search logic).

### Data Migration

**Migration Strategy:**

```sql
-- Conservative mapping: only explicit opt-in gets true
BEGIN TRANSACTION;

-- Add new column
ALTER TABLE ingredients ADD COLUMN allow_substitution BOOLEAN NOT NULL DEFAULT 0;

-- Populate from old values
UPDATE ingredients
SET allow_substitution = CASE
  WHEN substitution_level IN (1, 2) THEN 1  -- Explicit substitution → true
  ELSE 0                                     -- 0 or NULL → false
END;

-- Drop old column
ALTER TABLE ingredients DROP COLUMN substitution_level;

COMMIT;
```

**Rollback Plan (if needed):**

```sql
BEGIN TRANSACTION;

ALTER TABLE ingredients ADD COLUMN substitution_level INTEGER DEFAULT 0;

UPDATE ingredients
SET substitution_level = CASE
  WHEN allow_substitution = 1 THEN 1  -- Map back to parent-level
  ELSE 0
END;

ALTER TABLE ingredients DROP COLUMN allow_substitution;

COMMIT;
```

## Implementation Changes

### 1. Database Layer (`api/db/`)

**Files to update:**
- `db_core.py`: Update CRUD operations for ingredients
  - `create_ingredient()`: Use `allow_substitution` instead of `substitution_level`
  - `update_ingredient()`: Same change
  - `get_ingredient()`, `get_all_ingredients()`, `search_ingredients()`: Return boolean field
  - `get_ingredient_recommendations()`: Implement new matching logic

- `sql_queries.py`: Rewrite inventory matching query
  - Remove complex COALESCE-based inheritance resolution
  - Implement path-based recursive matching with `allow_substitution` checks
  - Simplify `SEARCH_RECIPES_BY_USER_INGREDIENTS_QUERY`

**SQL Query Pattern:**

```sql
-- Simplified structure (pseudo-code)
SELECT DISTINCT r.id, r.name
FROM recipes r
WHERE NOT EXISTS (
  SELECT 1 FROM recipe_ingredients ri
  JOIN ingredients req ON ri.ingredient_id = req.id
  WHERE ri.recipe_id = r.id
  AND NOT EXISTS (
    SELECT 1 FROM user_ingredients ui
    JOIN ingredients usr ON ui.ingredient_id = usr.id
    WHERE ui.cognito_user_id = :user_id
    AND (
      usr.id = req.id  -- Direct match
      OR (req.allow_substitution = 1 AND matches_via_recursive_logic(usr, req))
    )
  )
)
```

The `matches_via_recursive_logic` would be implemented via self-joins walking up the tree, checking `allow_substitution` at each level.

### 2. API Models (`api/models/`)

**requests.py:**

```python
class IngredientCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    allow_substitution: bool = Field(
        default=False,
        description="Whether this ingredient can be substituted with siblings/ancestors"
    )

class IngredientUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    allow_substitution: Optional[bool] = Field(
        None,
        description="Whether this ingredient can be substituted"
    )

class BulkIngredientCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_name: Optional[str] = None
    parent_id: Optional[int] = None
    allow_substitution: Optional[bool] = Field(default=False, ...)
```

**responses.py:**

```python
class IngredientResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    path: Optional[str] = None
    allow_substitution: bool  # Changed from substitution_level
    exact_match: Optional[bool] = None

class IngredientRecommendationResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    path: Optional[str] = None
    allow_substitution: bool  # Changed from substitution_level
    recipes_unlocked: int
    recipe_names: List[str]
```

**Breaking Changes:**
- API consumers expecting `substitution_level` will break
- No backward compatibility period needed (only frontend uses API)
- Deploy API and frontend together

### 3. Frontend (`src/web/`)

**HTML Changes:**

`ingredients.html` and `admin.html`:

```html
<!-- OLD -->
<div class="form-group">
  <label for="substitution-level">Substitution Level</label>
  <select id="substitution-level" name="substitution_level">
    <option value="">Inherit from parent</option>
    <option value="0">No substitution</option>
    <option value="1">Parent-level</option>
    <option value="2">Grandparent-level</option>
  </select>
</div>

<!-- NEW -->
<div class="form-group">
  <input type="checkbox" id="allow-substitution" name="allow_substitution">
  <label for="allow-substitution">
    Allow substitution with siblings/ancestors
    <span class="tooltip-icon" title="When enabled, this ingredient can be substituted with similar ingredients sharing the same parent">ⓘ</span>
  </label>
</div>
```

**JavaScript Changes:**

`ingredients.js` and `admin.js`:

```javascript
// OLD
const data = {
  name: form.name.value,
  description: form.description.value,
  parent_id: form.parent_id.value || null,
  substitution_level: parseInt(form.substitution_level.value) || null
};

// NEW
const data = {
  name: form.name.value,
  description: form.description.value,
  parent_id: form.parent_id.value || null,
  allow_substitution: form.allow_substitution.checked
};
```

**Display Updates:**
- Ingredient detail views: Show "Substitutable: Yes/No" instead of "Substitution Level: 0/1/2"
- Consider adding tooltips explaining substitution behavior

**Affected Files:**
- `src/web/ingredients.html`
- `src/web/admin.html`
- `src/web/js/ingredients.js`
- `src/web/js/admin.js`

### 4. Testing Updates

**Test files to update:**
- `tests/test_substitution_api.py` - API endpoint tests
- `tests/test_substitution_system.py` - Core logic tests
- `tests/test_substitution_integration.py` - End-to-end tests
- `tests/test_ingredient_recommendations.py` - Recommendation logic (fixes bd-65)
- `tests/test_substitution_migration.py` - **DELETE** after migration complete

**Critical Test Cases:**

1. **Direct match:** User has exact ingredient → recipe matches
2. **Parent match:** Recipe="Whiskey", User="Bourbon" → matches
3. **Sibling match:** Recipe="Bourbon"(allow_sub=true), User="Rye"(allow_sub=true) → matches
4. **Blocked substitution:** Recipe="Rum"(allow_sub=false), User="Dark Rum" → no match
5. **Recursive match:** Recipe="Bourbon", User="Spirit" → matches through parent chain
6. **Blocking propagation:** Middle ancestor has allow_sub=false → blocks traversal
7. **User ingredient blocks:** User="Rye"(allow_sub=false) → no sibling matching
8. **Null safety:** Ingredients without parents handle recursion correctly

## Implementation Sequence

**Phase 1: Database & Backend**
1. Write migration SQL file
2. Update `db_core.py` (CRUD operations)
3. Update `sql_queries.py` (matching queries)
4. Update API models (requests/responses)
5. Update route handlers (if needed)
6. Update backend tests

**Phase 2: Frontend**
7. Update ingredient forms (HTML)
8. Update JavaScript form handling
9. Manual testing of create/edit flows

**Phase 3: Migration & Deployment**
10. Apply migration to dev database
11. Test end-to-end in dev
12. Coordinate prod deployment:
    - Apply migration to prod database
    - Deploy updated code immediately (API + frontend)
    - Brief manual validation

**Deployment Notes:**
- Only 2 active users, manual coordination is acceptable
- Database backups available for rollback if needed
- Migration + deployment should happen together (breaking schema change)

## Risk Mitigation

**Error Scenarios:**

1. **Migration fails:** SQLite transaction will rollback automatically
2. **New code + no migration:** API gets 500 errors on missing column → run migration
3. **Migration + old code:** API gets 500 errors on missing column → deploy new code
4. **Logic bugs:** Wrong recipe results → hotfix query logic

**Mitigation:**
- Test thoroughly in dev before prod
- Keep database backups (already in place)
- Consider 5-minute maintenance window for coordinated deployment
- Rollback script ready if needed (see Data Migration section)

## Success Criteria

**Post-deployment validation:**
1. Ingredient create/edit forms work with checkbox
2. Existing ingredients display correct allow_substitution values
3. Recipe search with inventory respects new substitution logic
4. Ingredient recommendations work correctly (fixes bd-65)
5. No 500 errors in API logs
6. Both users confirm UI is clearer

## Related Issues

- **bd-65:** Ingredient recommendations don't consider substitutability (FIXES)
- **bd-59:** Create data migration script (IMPLEMENTS)
- **bd-58:** Update tests (IMPLEMENTS)
- **bd-57:** Update frontend forms (IMPLEMENTS)
- **bd-56:** Update API models (IMPLEMENTS)
- **bd-55:** Remove inheritance logic (IMPLEMENTS)
- **bd-54:** Database migration (IMPLEMENTS)

## Benefits

1. **Simpler UX:** Checkbox vs dropdown with 4 options
2. **Clearer semantics:** "Allow substitution" vs "Level 0/1/2"
3. **Easier maintenance:** Explicit values, no inheritance resolution
4. **Fewer bugs:** Simpler recursive logic, easier to test
5. **Better recommendations:** Fixes bd-65 by making substitutability explicit

## Future Considerations

**Out of scope for this change:**
- Advanced substitution rules (e.g., "only substitute with X and Y")
- User-configurable substitution preferences
- Substitution confidence scores
- Tracking which substitutions were used in a recipe

These could be added later if needed, building on the boolean foundation.
