# Ingredient Substitution Logic

**Version**: 2.0 (Boolean System)
**Last Updated**: 2025-11-05
**Issue**: bd-53

## Overview

The substitution system determines whether a user's inventory ingredient can satisfy a recipe's ingredient requirement. This document describes the complete matching logic.

## Core Principle

**Question**: Can a user's ingredient satisfy a recipe's ingredient requirement?

The system checks multiple matching paths, each with specific conditions. A match occurs if **ANY** of these paths succeeds.

## Matching Paths

### 1. Direct Match (Always Allowed)

```
IF user_ingredient.id == recipe_ingredient.id
  → MATCH
```

**Example**: User has "Bourbon" → Recipe needs "Bourbon" ✓

**No substitution flags are checked** - exact matches always work.

---

### 2. Parent-to-Child Substitution (Conditional)

```
IF recipe_ingredient.allow_substitution == TRUE
  AND user_ingredient is ancestor of recipe_ingredient (path-based)
  AND no blocking parents exist in between
  → MATCH
```

**Example Hierarchy**:
```
Rum [allow_sub=true]
  └─ Pot Still Unaged Rum [allow_sub=false]  ← BLOCKING
      └─ Wray And Nephew [allow_sub=true]
```

**Scenarios**:
- User has "Rum" → Recipe needs "Wray And Nephew" → **NO MATCH** ✗
  - Reason: "Pot Still Unaged Rum" has `allow_substitution=false`, blocking the path

**SQL Implementation**:
```sql
(i_recipe.allow_substitution = 1
 AND i_recipe.path LIKE i_user.path || '%'
 AND NOT EXISTS (
     SELECT 1 FROM ingredients blocking
     WHERE i_recipe.path LIKE blocking.path || '%'  -- blocking is ancestor of recipe
     AND blocking.path LIKE i_user.path || '%'      -- blocking is descendant of user
     AND blocking.id != i_user.id                    -- not the user ingredient
     AND blocking.allow_substitution = 0             -- blocks substitution
 ))
```

**Key Point**: ALL ancestors in the substitution path must have `allow_substitution=true`.

---

### 3. Child-to-Parent Substitution (Always Allowed)

This is actually handled by Path #2, but logically it's the reverse direction:

```
IF user_ingredient is ancestor of recipe_ingredient
  AND recipe_ingredient.allow_substitution == TRUE
  AND no blocking parents in path
  → MATCH
```

**Example**: User has "Old Tom Gin" → Recipe needs "Gin" ✓

**Rationale**: Having a specific type satisfies a general category requirement.

---

### 4. Sibling Substitution (Bidirectional)

```
IF recipe_ingredient.allow_substitution == TRUE
  AND user_ingredient.allow_substitution == TRUE
  AND both share the same parent_id (not null)
  → MATCH
```

**Example Hierarchy**:
```
Whiskey [parent]
  ├─ Bourbon [allow_sub=true]
  └─ Rye [allow_sub=true]
```

**Scenarios**:
- User has "Bourbon" → Recipe needs "Rye" → **MATCH** ✓ (both allow substitution)
- User has "Bourbon" [allow_sub=false] → Recipe needs "Rye" → **NO MATCH** ✗ (user blocks)
- User has "Bourbon" → Recipe needs "Rye" [allow_sub=false] → **NO MATCH** ✗ (recipe blocks)

**Key Point**: BOTH siblings must have `allow_substitution=true`.

---

### 5. User Has Direct Parent

```
IF recipe_ingredient.allow_substitution == TRUE
  AND user_ingredient.id == recipe_ingredient.parent_id
  → MATCH
```

**Example**: User has "Whiskey" → Recipe needs "Bourbon" (child of Whiskey) ✓

**Note**: This is a special case of parent-to-child substitution.

---

### 6. Recursive Common Ancestor Substitution

```
IF recipe_ingredient.allow_substitution == TRUE
  AND EXISTS a common ancestor with allow_substitution == TRUE
  AND no blocking parents between ancestor and recipe ingredient
  → MATCH
```

**Example Hierarchy**:
```
Spirit [allow_sub=true]  ← Common ancestor
  ├─ Whiskey [allow_sub=true]
  │   └─ Bourbon [allow_sub=true]
  └─ Rum [allow_sub=true]
      └─ Dark Rum [allow_sub=true]
```

**Scenarios**:
- User has "Bourbon" → Recipe needs "Dark Rum" → **MATCH** ✓
  - Common ancestor: "Spirit" (allow_sub=true)
  - No blocking parents in path to Dark Rum

**SQL Implementation**:
```sql
EXISTS (
    SELECT 1 FROM ingredients anc
    WHERE i_user.path LIKE anc.path || '%'        -- ancestor of user ingredient
    AND i_recipe.path LIKE anc.path || '%'        -- ancestor of recipe ingredient
    AND anc.allow_substitution = 1                -- allows substitution
    AND NOT EXISTS (
        SELECT 1 FROM ingredients blocking
        WHERE i_recipe.path LIKE blocking.path || '%'
        AND blocking.path LIKE anc.path || '%'
        AND blocking.id != anc.id
        AND blocking.allow_substitution = 0       -- blocks path to recipe
    )
)
```

---

## Blocking Parent Logic

**Critical Rule**: When checking parent-to-child or recursive substitution, ALL intermediate ancestors must have `allow_substitution=true`.

### Example: Blocking Parent Scenario

```
Rum [allow_sub=true]
  └─ Pot Still Unaged Rum [allow_sub=FALSE]  ← BLOCKS
      └─ Wray And Nephew [allow_sub=true]
```

**Check**: User has "Rum", recipe needs "Wray And Nephew"

1. Recipe allows substitution? YES (Wray And Nephew = true)
2. User is ancestor? YES (Rum is grandparent)
3. **Check for blocking parents**:
   - "Pot Still Unaged Rum" is between them
   - Has `allow_substitution=false`
   - → **BLOCKED** ✗

**Result**: No match, even though both endpoints allow substitution.

---

## Path Representation

Ingredients use a hierarchical path stored as text with format: `/id1/id2/id3/`

**Example**:
```
Rum (id=1)          → path: /1/
├─ Dark Rum (id=5)  → path: /1/5/
└─ White Rum (id=6) → path: /1/6/
```

**Path Matching**:
- `LIKE '/1/%'` matches all descendants of Rum
- `LIKE '/1/5/%'` matches all descendants of Dark Rum

---

## Complete Decision Tree

```
User has ingredient U, Recipe needs ingredient R

1. IF U.id == R.id
     → MATCH (direct)

2. IF R.allow_substitution == FALSE
     → STOP (recipe blocks all substitution)

3. IF R.allow_substitution == TRUE:

   a. IF R.path LIKE U.path || '%'  (U is ancestor of R)
        AND no blocking parents between U and R
        → MATCH (parent-to-child)

   b. IF R.parent_id == U.parent_id (siblings)
        AND R.parent_id IS NOT NULL
        AND U.allow_substitution == TRUE
        → MATCH (sibling)

   c. IF U.id == R.parent_id  (U is direct parent)
        → MATCH (user has parent)

   d. IF EXISTS common ancestor A
        WHERE U.path LIKE A.path || '%'
        AND R.path LIKE A.path || '%'
        AND A.allow_substitution == TRUE
        AND no blocking parents between A and R
        → MATCH (recursive common ancestor)

4. ELSE
     → NO MATCH
```

---

## SQLite Storage

- **Column**: `allow_substitution BOOLEAN NOT NULL DEFAULT 0`
- **Values**: SQLite stores booleans as integers
  - `0` = false (no substitution)
  - `1` = true (allow substitution)
- **Python**: Values returned as `int` (0 or 1), not Python `bool`
- **API**: Pydantic models convert to/from boolean for JSON

---
## Testing

Key test scenarios:

1. **Direct Match**: User has exact ingredient → always matches
2. **Parent Match**: User has parent, recipe allows substitution → matches
3. **Blocking Child**: User has parent, child blocks substitution → no match
4. **Blocking Middle Parent**: Grandparent → blocking parent → grandchild → no match
5. **Sibling Match**: Both siblings allow substitution → matches
6. **Sibling Blocked**: One sibling blocks → no match
7. **Recursive Ancestor**: Common ancestor allows, no blocking path → matches

---

## Performance Considerations

### Indexed Columns
- `parent_id`: Index for sibling lookups
- `path`: Index for ancestor/descendant queries

### Query Optimization
- Path-based matching uses `LIKE` with prefix patterns
- `NOT EXISTS` subqueries check for blocking parents
- Limits on recursive depth (6 levels) prevent expensive queries

---


## Related Issues

- **bd-53**: Boolean overhaul (main issue)
- **bd-65**: Ingredient recommendations bug (fixed by this system)
- **bd-54** through **bd-59**: Implementation tasks

---

## Implementation Files

- **Database Schema**: `schema-deploy/schema.sql` (line 16)
- **Migration Script**: `migrations/08_migration_substitution_level_to_boolean.sql`
- **Recipe Search Query**: `api/db/sql_queries.py` (lines 199-243)
- **Ingredient Recommendations**: `api/db/db_core.py` (lines 2656-2697)
- **API Models**: `api/models/requests.py`, `api/models/responses.py`
- **Frontend**: `src/web/ingredients.html`, `src/web/js/ingredients.js`
- **Tests**: `tests/test_substitution_system.py` (16 tests)

---

## Quick Reference

| User Has | Recipe Needs | Match? | Why |
|----------|-------------|--------|-----|
| Bourbon | Bourbon | ✓ | Direct match |
| Whiskey (parent) | Bourbon (child, allow_sub=true) | ✓ | Parent-to-child |
| Bourbon (child) | Whiskey (parent) | ✓ | Child-to-parent |
| Bourbon (allow_sub=true) | Rye (sibling, allow_sub=true) | ✓ | Sibling substitution |
| Rum | Wray And Nephew (allow_sub=true) | ✗ | Pot Still (middle parent) blocks |
| Bourbon (allow_sub=false) | Rye | ✗ | User blocks substitution |
| Rum | Dark Rum (allow_sub=false) | ✗ | Recipe blocks substitution |
| Bourbon | Dark Rum | ✓ | Common ancestor (Spirit) allows |

---

**End of Documentation**
