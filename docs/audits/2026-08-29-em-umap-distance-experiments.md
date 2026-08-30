# EM, distance, clustering, and UMAP experiments

Date: 2026-08-29

## Executive summary

Experiments used 1,955 production recipes and 406 ingredients after hierarchy rollup. The selected production configuration is:

- constrained EM with `candidate_k` equal to 15% of recipe count (293 in this dataset)
- BLOSUM smoothing `alpha=0.2`
- UMAP `n_neighbors=10`, `min_dist=0.05`, and `random_state=42`

The rolled EM pipeline produced more compact native-space clusters than the unrolled Manhattan baseline. This was a pipeline comparison, not an isolation of EM alone. After lowering BLOSUM smoothing from 1.0 to 0.2, candidate width mattered slightly more; 15% retained nearly all wider-run structure without the runtime cost of 20% or 40%. Lower smoothing improved both HDBSCAN coverage and silhouette at fixed candidate width, although it did not improve the intended rum/whiskey or gin/vodka substitutions.

Two attempts to learn functional substitutions were rejected:

1. adding generic leave-one-ingredient-out template evidence to the EM update
2. replacing the learned cost with hierarchy-aware co-ingredient context similarity

Neither improved clustering or cross-spirit neighborhoods. The evidence indicates that the current ingredient-only data does not reliably encode human-recognized cocktail templates. Recipe-level ABV, sugar, and acidity are a more promising future source of family structure once coverage is sufficient.

## Questions

The experiments addressed:

1. Does EM produce meaningfully better cocktail clusters than Manhattan distance?
2. Does a wider constrained-EM candidate set improve the result enough to justify its cost?
3. Which BLOSUM smoothing value gives the best clustering with the current EM algorithm?
4. Which UMAP settings best preserve EM neighborhoods and clusters?
5. Can unsupervised template or ingredient-context evidence teach functional substitutions such as rum/whiskey and gin/vodka?

## Data and fixed evaluation settings

- Recipes: 1,955
- Source ingredient records: 672
- Recipe-ingredient rows: 8,797
- Ingredients represented after rollup: 406
- HDBSCAN: `min_cluster_size=10`, `min_samples=1`, `cluster_selection_method="leaf"`, precomputed native-space distances
- Exact EM: not run

Cluster quality was measured in the original distance space, not in the displayed two-dimensional UMAP space. UMAP was evaluated separately as a visualization-preservation problem.

Constrained matrices contain unknown pairs. Production-compatible evaluations replaced unknown distances with twice the largest computed distance in that matrix. Metrics involving completed matrices are therefore imputed proxies, not exact all-pairs measurements.

## Rolled EM pipeline versus unrolled Manhattan baseline

This comparison includes both the distance method and preprocessing: EM used hierarchy-rolled recipes, while Manhattan used the unrolled recipe vectors. It measures the two available pipelines and does not attribute the full difference to EM alone.

Using the original smoothing value (`alpha=1.0`) and `candidate_k=195`:

| Metric | EM | Manhattan |
|---|---:|---:|
| Clusters | 37 | 43 |
| Clustered recipes | 844 | 833 |
| Coverage | 43.2% | 42.6% |
| Median cluster size | 19 | 14 |
| Native-space silhouette | **0.333** | 0.249 |

Agreement with EM:

- all-recipe ARI: 0.519
- all-recipe AMI: 0.624
- jointly clustered ARI: 0.911
- jointly clustered AMI: 0.959

Manhattan and the EM pipeline largely agreed on assignments when both methods confidently clustered a recipe. The rolled EM pipeline had greater within-cluster compactness, but this experiment did not isolate how much came from rollup versus EM learning.

## Constrained-EM candidate width

### Initial alpha-1 evaluation

| `candidate_k` | Runtime | EMD evaluations | Result |
|---:|---:|---:|---|
| 195 | 228 s | 720,566 | initial production setting |
| 391 | 355 s | 1,422,780 | no assignment improvement |
| 780 | 737 s | 2,756,729 | negligible structural change |

At `alpha=1.0`, `k=195` retained 99.4% of the `k=780` proxy's top-10 neighbors, cost-matrix correlation 0.99997, and approximately 0.996 all-recipe cluster ARI/AMI. This originally supported the 10% fraction.

### Re-evaluation after selecting alpha 0.2

Lower smoothing made the learned matrix more sensitive to which pairs were evaluated, so candidate width was rerun before finalizing production settings.

| `candidate_k` | Fraction | Runtime | Top-10 overlap vs 780 | Cost correlation vs 780 | Cluster ARI vs 780 |
|---:|---:|---:|---:|---:|---:|
| 195 | 10% | 248 s | 98.72% | 0.99950 | 0.9879 |
| **293** | **15%** | **371 s** | **98.96%** | **0.99964** | **0.9960** |
| 391 | 20% | 512 s | 99.00% | 0.99967 | 1.0000 |
| 780 | 40% | 1,071 s | reference | reference | reference |

`k=293` saved 27.5% runtime versus `k=391` while losing only 0.046 percentage points of top-10 overlap and changing one clustered recipe. The cost matrices were effectively identical. `k=780` remains a wider approximation, not exact EM ground truth. The final production choice is the 15% fraction.

## BLOSUM smoothing

### Why smoothing needed investigation

The original learned ingredient matrix was nearly constant:

- initial off-diagonal coefficient of variation: 19.5%
- learned coefficient of variation with `alpha=1.0`: 1.0%
- learned 10th/90th percentiles: 0.9996/1.0099

In one first-iteration measurement, the weighted ingredient-match matrix contained total mass 1,568.3. Adding one pseudo-count to every cell in a 406×406 matrix contributed 164,836 pseudo-counts, approximately 105 times the observed mass.

### Grid results

All smoothing-grid settings retained the then-current `candidate_k=195` neighbor selection and a maximum of five iterations. Candidate width was retuned afterward.

| Alpha | Clusters | Clustered | Coverage | Silhouette | Convergence status |
|---:|---:|---:|---:|---:|---|
| 1.0 | 37 | 844 | 43.2% | 0.333 | converged |
| 0.5 | 37 | 837 | 42.8% | **0.344** | converged after 4 |
| 0.3 | 39 | **899** | **46.0%** | 0.332 | converged after 5 |
| **0.2** | **38** | 898 | **45.9%** | **0.340** | reached production iteration limit |
| 0.1 | 39 | 895 | 45.8% | 0.322 | reached production iteration limit |

`alpha=0.2` was selected because it improved both coverage and silhouette over production while retaining compact, granular clusters. It preserved 89.0% of the original top-10 neighbors.

A blind Luna review found `alpha=0.5` and `alpha=0.2` effectively tied in interpretability:

| Alpha | High confidence | Medium confidence | Low confidence |
|---:|---:|---:|---:|
| 0.5 | 23 | 14 | 0 |
| 0.2 | 23 | 15 | 0 |

The additional coverage at 0.2 therefore did not introduce an obvious coherence penalty.

### Limitation

Lower smoothing did not improve functional spirit substitutions:

- rum recipes with whiskey in their top 10 fell from 13.3% at alpha 1.0 to 11.8% at alpha 0.2
- gin recipes with vodka in their top 10 fell from 3.1% to 2.0%

The smoothing change is a clustering improvement, not a solution to the substitution-learning problem.

## UMAP tuning

The grid covered:

- `n_neighbors`: 5, 10, 15, 30, 50
- `min_dist`: 0, 0.01, 0.05, 0.10, 0.25
- seeds: 0, 1, 42
- total runs: 75

The primary objective combined k-neighbor recall, trustworthiness, and continuity at neighborhood sizes 5, 10, and 20. Cluster preservation was secondary.

The final grid used the selected `alpha=0.2`, `candidate_k=293` matrix and explicitly removed self-neighbors before ranking tied distances.

| Setting | Median local preservation | Worst seed | Median source-cluster silhouette in 2D | Median all-recipe AMI |
|---|---:|---:|---:|---:|
| Current: 5 / 0.05 | 0.8036 | 0.8018 | 0.5537 | 0.3993 |
| **Selected: 10 / 0.05** | **0.8084** | **0.8082** | **0.6035** | 0.3913 |
| 10 / 0.01 | 0.8092 | 0.8076 | 0.6223 | 0.4015 |
| 10 / 0.10 | 0.8082 | 0.8080 | 0.5648 | 0.4046 |

`n_neighbors=10`, `min_dist=0.05` ranked first by worst-seed stability, then median preservation. It also retained stronger two-dimensional source-cluster separation than 0.10. `min_dist=0.01` had a slightly higher median but a lower worst seed.

## Functional-substitution investigation

The intended behavior was template-aware substitution: for example, rum and whiskey should become cheaper when recipes demonstrate rum and whiskey Old Fashioneds or Manhattans. Gin and vodka should behave similarly in Martini-like templates.

### Evidence available to the current EM update

The M-step uses only each recipe's ten nearest neighbors. Under the original learned distance:

- 13.3% of rum recipes had a whiskey recipe in their top 10
- 3.1% of gin recipes had a vodka recipe in their top 10
- Old Fashioned to Rum Old Fashioned rank: 193
- Old Fashioned to a second rum Old Fashioned rank: 207
- Manhattan to Banana Manhattan rank: 1,011 and outside the final candidate graph

The dataset was not simply too small:

- about 437 recipes contained rum-family ingredients
- about 442 contained whiskey-family ingredients
- about 496 contained gin-family ingredients
- about 88 contained vodka-family ingredients

Adding ordinary same-spirit recipes would not necessarily help because they can further crowd cross-spirit analogues out of the ten neighbors used for learning.

### Generic template-neighbor experiment

To avoid hard-coding base spirits, an experiment removed each recipe's dominant ingredient and compared the residual composition. It then added two cross-ingredient template neighbors to the match evidence.

This did not recover the named examples:

- Old Fashioned to Rum Old Fashioned residual rank: 145
- Old Fashioned to the second rum version: 304
- Manhattan to Banana Manhattan: 1,438

The named recipes are not literal one-ingredient substitutions. The rum Old Fashioneds use multiple rums and additional modifiers; the Banana Manhattan adds banana liqueur and absinthe. Their shared template is largely semantic rather than a near match in the available ingredient vector.

Exploratory variants using lower smoothing, tree shrinkage, and template evidence did not improve the target neighborhoods. Increasing template evidence to equal the ordinary-neighbor evidence also reduced silhouette to 0.295. This approach was rejected.

## Ingredient-context similarity

### Method

The context experiment did not use curated spirit or template labels. For each ingredient it:

1. aggregated evidence from descendants in the existing ingredient hierarchy
2. represented the ingredient by ingredients accompanying it outside its own top-level family
3. downweighted ubiquitous context ingredients with inverse document frequency
4. converted context-vector cosine similarity to an ingredient cost
5. blended context cost with the original tree cost
6. computed recipe EMD over the union of Manhattan and context-derived candidate neighbors

At the ingredient level, the hierarchy-aware representation placed generic rum/whiskey and gin/vodka pairs in approximately the closest 4% of ingredient pairs. This promising ingredient-level result did not survive recipe-level EMD.

### Recipe-level results

The historical `alpha=0.2`, `candidate_k=195` EM matrix was the reference for this rejected experiment; candidate width was retuned afterward.

| Context weight | Clusters | Clustered | Coverage | Silhouette | Top-10 overlap with EM |
|---:|---:|---:|---:|---:|---:|
| EM alpha 0.2 | 38 | 898 | 45.9% | **0.340** | 100% |
| 25% | 36 | 752 | 38.5% | 0.321 | 69.6% |
| 50% | 35 | 697 | 35.7% | 0.261 | 70.3% |
| 75% | 33 | 747 | 38.2% | 0.332 | 67.4% |
| 100% | 29 | 703 | 36.0% | 0.339 | 59.4% |

Cross-spirit results also failed to improve consistently:

| Method | Rum→whiskey top 10 | Gin→vodka top 10 |
|---|---:|---:|
| EM alpha 0.2 | **11.8%** | 2.0% |
| 25% context | 4.3% | **3.5%** |
| 50% context | 5.8% | 2.7% |
| 75% context | 6.5% | 2.2% |
| 100% context | 7.5% | 1.8% |

Although some absolute analogue distances decreased, their ranks worsened because the context model made many ingredients broadly similar rather than learning selective substitutions. The context approach was rejected for production.

## What was learned

1. The rolled EM pipeline is more compact than the unrolled Manhattan baseline; EM's isolated contribution remains unmeasured.
2. At alpha 0.2, a 15% candidate fraction is the best runtime/fidelity balance; wider graphs are nearly identical.
3. The original smoothing overwhelms observed match evidence and flattens the learned cost matrix.
4. `alpha=0.2` improves clustering but not functional substitutions.
5. Functional substitution is not reliably recoverable from the current nearest-neighbor loop.
6. Cocktail names encode template semantics not present in simple ingredient vectors.
7. Co-ingredient context produces broad stylistic similarity, not sufficiently selective recipe neighborhoods.
8. Exact EM is unlikely to fix the objective mismatch; it would only evaluate more pairs under the same update rule.

## Future direction: physical cocktail features

Recipe-level physical features are a stronger candidate for cocktail-family structure:

- finished ABV
- sugar concentration or total sugar per serving
- titratable acidity
- dilution and total serving volume

These features could distinguish spirit-forward, sour, highball, and dessert families even when the base ingredients differ. They should supplement ingredient distance rather than silently replace it.

Data requirements and cautions:

- ingredient ABV and sugar coverage must be measured before enabling the metric
- missing values must remain explicit rather than being silently treated as zero
- acidity should use titratable acidity where possible; pH is not additive
- dilution assumptions must be consistent across shaken, stirred, built, and carbonated drinks
- feature scales and blend weights must be validated against held-out families

## Decisions

Adopted in PR #31:

- set `candidate_k` to 15% of recipe count
- set BLOSUM `alpha=0.2`
- set UMAP `n_neighbors=10`
- retain UMAP `min_dist=0.05` and `random_state=42`

Not adopted:

- exact EM
- candidate fractions of 20% or greater
- dominant-ingredient template neighbors
- hierarchy-aware ingredient-context distance
- `min_dist=0`

## Reproducibility and limitations

The committed `scripts/test_constrained_em.py` uses the production alpha and supports candidate-width, Manhattan, clustering, artifact, grouped UMAP-grid ranking, and raw per-seed output. The smoothing grid, template-neighbor, and context-distance variants were isolated throwaway experiments; their durable results are recorded here, but their experimental code and large matrices were not committed.

The six pre-existing stale Barcart distance-test failures encountered during setup are tracked in GitHub issue #29.
