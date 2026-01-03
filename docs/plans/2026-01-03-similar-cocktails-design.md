# Similar Cocktails Links + Transport Plan Summaries

## Overview

Add a “Similar Cocktails” section to the recipe card that links to the four most similar recipes. Similarity is based on the EM distance matrix. The analytics pipeline will emit a compact JSON artifact containing the top neighbors and a sparse transport-plan summary for each neighbor pair.

## Goals

- Show the four most similar cocktails for each recipe on the card.
- Use EM distance data without serving large `.npy` artifacts.
- Store a lightweight transport-plan summary for future “how it differs” UI.
- Keep API calls minimal by returning neighbor IDs and names together.

## Non-Goals

- Full transport-plan visualization in the UI.
- Serving or parsing the full distance matrix in the API.
- Adding a DB-backed similarity table in this phase.

## Data Products

### Similar Cocktails JSON (Analytics Storage)

Create a new analytics JSON artifact (versioned alongside other analytics JSON files) with one entry per recipe:

```json
{
  "data": [
    {
      "recipe_id": 123,
      "recipe_name": "Daiquiri",
      "neighbors": [
        {
          "neighbor_recipe_id": 456,
          "neighbor_name": "Hemingway Daiquiri",
          "distance": 0.123,
          "transport_plan": [
            { "from_ingredient_id": 12, "to_ingredient_id": 98, "mass": 0.34 }
          ]
        }
      ]
    }
  ],
  "metadata": {
    "generated_at": "...",
    "storage_version": "v1",
    "analytics_type": "recipe-similar"
  }
}
```

Notes:
- For each recipe, select the 4 nearest neighbors by distance, excluding the recipe itself.
- Keep zero-distance neighbors (if `distance == 0` and `neighbor_recipe_id != recipe_id`).
- Transport plan is sparse: only the 3 largest transport terms per neighbor.

## Analytics Pipeline Changes

- Extend the EM analytics pipeline in `packages/barcart` to emit the new JSON file.
- Preserve the recipe order used for the distance matrix to map indices to `recipe_id` and `recipe_name`.
- Extract transport plans from the EM step and retain the top 3 mass entries per neighbor pair.
- Keep the `.npy` distance matrix for analytics/debugging (do not replace in this phase).

## API

Add a new endpoint:

- `GET /analytics/recipe-similar?recipe_id=<id>`
  - Loads the `recipe-similar` JSON artifact from analytics storage.
  - Returns the neighbor list for the requested recipe (ID + name + distance + transport plan summary).
  - Returns 404 if the analytics artifact or the recipe entry is missing.

Add a recipe lookup by ID for the recipe page:

- Extend the existing recipe search/lookup to accept `id`, so `recipe.html?id=<id>` works.

## Frontend

- Add a “Similar Cocktails” section at the bottom of the recipe card in `src/web/js/recipeCard.js`.
- Render only if neighbors are available.
- Each item links to `recipe.html?id=<neighbor_id>` and displays the neighbor name and distance.
- The recipe page should accept `id` query parameter and fetch the recipe by ID.

## Error Handling

- If similar data is missing, omit the section on the card.
- If the API returns 404 for similar data, log and continue.

## Testing

- Unit tests for neighbor selection (exclude self, keep zero-distance neighbors, top-4 ordering).
- API tests using a fixture JSON to validate the response shape and 404 behavior.

## Open Questions

- None.
