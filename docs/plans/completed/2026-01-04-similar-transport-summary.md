# Similar Transport Summary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add transport-plan ingredient name summaries to Similar Cocktails so the UI can show distance-first lines like `0.123 Hemingway Daiquiri — Lillet → Cocchi Americano; Bourbon → Rye`.

**Architecture:** Enrich the analytics artifact (`recipe-similar`) during EM reporting so each `transport_plan` entry contains both IDs and ingredient names. The API continues to read stored analytics JSON, and the frontend formats the transport plan inline with the distance-first requirement.

**Tech Stack:** Python (barcart analytics), FastAPI (analytics route), vanilla JS frontend.

### Task 1: Update analytics transport plan to include ingredient names

**Files:**
- Modify: `packages/barcart/barcart/reporting.py`
- Test: `packages/barcart/tests/test_recipe_similarity.py`

**Step 1: Write the failing test**

```python
def test_build_recipe_similarity_includes_transport_names():
    result = build_recipe_similarity(
        distance_matrix=dist,
        plans=plans,
        recipe_registry=recipe_registry,
        ingredient_registry=ingredient_registry,
        k=1,
        plan_topk=1,
    )
    transport = result[0]["neighbors"][0]["transport_plan"][0]
    assert transport["from_ingredient_name"] == "Lillet"
    assert transport["to_ingredient_name"] == "Cocchi Americano"
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/barcart/tests/test_recipe_similarity.py::test_build_recipe_similarity_includes_transport_names -v`
Expected: FAIL with `KeyError: 'from_ingredient_name'`

**Step 3: Write minimal implementation**

```python
transport_plan = [
    {
        "from_ingredient_id": int(ingredient_registry.get_id(index=int(from_idx))),
        "from_ingredient_name": ingredient_registry.get_name(index=int(from_idx)),
        "to_ingredient_id": int(ingredient_registry.get_id(index=int(to_idx))),
        "to_ingredient_name": ingredient_registry.get_name(index=int(to_idx)),
        "mass": float(amount),
    }
    for from_idx, to_idx, amount, _ in plan_sorted
]
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/barcart/tests/test_recipe_similarity.py::test_build_recipe_similarity_includes_transport_names -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/barcart/barcart/reporting.py packages/barcart/tests/test_recipe_similarity.py
git commit -m "feat: include transport ingredient names in recipe similarity"
```

### Task 2: Update analytics API tests to accept name fields

**Files:**
- Modify: `tests/test_recipe_similar_api.py`

**Step 1: Write the failing test**

```python
def test_get_recipe_similar_includes_transport_names():
    storage.put_analytics(
        "recipe-similar",
        [
            {
                "recipe_id": 1,
                "recipe_name": "One",
                "neighbors": [
                    {
                        "neighbor_recipe_id": 2,
                        "neighbor_name": "Two",
                        "distance": 0.1,
                        "transport_plan": [
                            {
                                "from_ingredient_id": 10,
                                "from_ingredient_name": "Lillet",
                                "to_ingredient_id": 11,
                                "to_ingredient_name": "Cocchi Americano",
                                "mass": 0.4,
                            }
                        ],
                    }
                ],
            }
        ],
    )
    ...
    body = response.json()
    transport = body["neighbors"][0]["transport_plan"][0]
    assert transport["from_ingredient_name"] == "Lillet"
    assert transport["to_ingredient_name"] == "Cocchi Americano"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_recipe_similar_api.py::test_get_recipe_similar_includes_transport_names -v`
Expected: FAIL (test missing / transport keys)

**Step 3: Write minimal implementation**

Update the existing fixture in `tests/test_recipe_similar_api.py` to include `from_ingredient_name` and `to_ingredient_name` so the API passes them through unchanged.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_recipe_similar_api.py::test_get_recipe_similar_includes_transport_names -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_recipe_similar_api.py
git commit -m "test: cover transport ingredient names in recipe similar api"
```

### Task 3: Render transport summary in recipe card similar list

**Files:**
- Modify: `src/web/js/recipeCard.js`
- Modify: `src/web/styles.css`

**Step 1: Write the failing test**

Skip frontend tests per request.

**Step 2: Implement minimal UI change**

- In `loadSimilarCocktails`, map each neighbor to a transport summary string using the first 2–3 entries in `neighbor.transport_plan`.
- Render line format: `<span class="similar-distance">${distance}</span> <a ...>${neighbor_name}</a><span class="similar-transport"> — Lillet → Cocchi Americano; Bourbon → Rye</span>`.
- Add a small CSS rule in `src/web/styles.css` to style `.similar-transport` (lighter color + smaller size) to keep focus on name + distance.

**Step 3: Manual verification**

Open a recipe page with similar cocktails and confirm the line reads `0.123 Hemingway Daiquiri — Lillet → Cocchi Americano; Bourbon → Rye` with distance first.

**Step 4: Commit**

```bash
git add src/web/js/recipeCard.js src/web/styles.css
git commit -m "feat: show transport summaries for similar cocktails"
```

### Task 4: Update design doc (optional)

**Files:**
- Modify: `docs/plans/2026-01-03-similar-cocktails-design.md`

**Step 1: Note transport name fields in JSON**

Add `from_ingredient_name` and `to_ingredient_name` to the JSON example for `transport_plan`.

**Step 2: Commit**

```bash
git add docs/plans/2026-01-03-similar-cocktails-design.md
git commit -m "docs: document transport name fields in similar recipes"
```
