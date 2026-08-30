# EM, distance, clustering, and UMAP experiments

Date: 2026-08-29

## Executive summary

Experiments used 1,955 production recipes and 406 ingredients after hierarchy rollup. The selected production configuration is:

- constrained EM with `candidate_k` equal to 10% of recipe count (195 in this dataset)
- BLOSUM smoothing `alpha=0.2`
- UMAP `n_neighbors=10`, `min_dist=0.05`, and `random_state=42`

EM produced more compact native-space clusters than Manhattan distance. Increasing `candidate_k` did not materially improve learned costs, neighbors, or clusters. Lowering BLOSUM smoothing from 1.0 to 0.2 improved both HDBSCAN coverage and silhouette, although it did not improve the intended rum/whiskey or gin/vodka substitutions.

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
- HDBSCAN: `min_cluster_size=10`, `min_samples=1`, precomputed native-space distances
- Exact EM: not run

Cluster quality was measured in the original distance space, not in the displayed two-dimensional UMAP space. UMAP was evaluated separately as a visualization-preservation problem.

Constrained matrices contain unknown pairs. Production-compatible evaluations replaced unknown distances with twice the largest computed distance in that matrix. Metrics involving completed matrices are therefore imputed proxies, not exact all-pairs measurements.

## EM versus Manhattan distance

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

Manhattan and EM largely agreed on assignments when both methods confidently clustered a recipe. EM's principal advantage was greater within-cluster compactness.

## Constrained-EM candidate width

| `candidate_k` | Runtime | EMD evaluations | Result |
|---:|---:|---:|---|
| 195 | 228 s | 720,566 | selected |
| 391 | 355 s | 1,422,780 | no assignment improvement |
| 780 | 737 s | 2,756,729 | negligible structural change |

Compared with the `k=780` proxy, `k=195` retained approximately:

- 99.4% of top-10 neighbors
- 99.2% of top-20 neighbors
- 98.9% of top-50 neighbors
- cost-matrix correlation 0.99997
- all-recipe cluster ARI/AMI approximately 0.996/0.996
- jointly clustered ARI/AMI 1.0/1.0

`k=780` was a wider approximation, not exact EM ground truth. The evidence supports retaining the cheaper 10% candidate fraction.

## BLOSUM smoothing

### Why smoothing needed investigation

The original learned ingredient matrix was nearly constant:

- initial off-diagonal coefficient of variation: 19.5%
- learned coefficient of variation with `alpha=1.0`: 1.0%
- learned 10th/90th percentiles: 0.9996/1.0099

In one first-iteration measurement, the weighted ingredient-match matrix contained total mass 1,568.3. Adding one pseudo-count to every cell in a 406×406 matrix contributed 164,836 pseudo-counts, approximately 105 times the observed mass.

### Grid results

All settings retained the current neighbor selection, `candidate_k=195`, and a maximum of five iterations.

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

| Setting | Median local preservation | Worst seed | Median source-cluster silhouette in 2D | Median all-recipe AMI |
|---|---:|---:|---:|---:|
| Current: 5 / 0.05 | 0.7920 | 0.7908 | 0.5297 | 0.3762 |
| **Selected: 10 / 0.05** | **0.8004** | **0.7999** | **0.6085** | **0.3872** |
| 10 / 0 | 0.8003 | 0.7989 | 0.6218 | 0.3921 |
| 10 / 0.10 | 0.7996 | 0.7996 | 0.5946 | 0.3895 |

`n_neighbors=10`, `min_dist=0.05` was selected as the stable, minimal change. `min_dist=0` made clusters slightly more compact in two dimensions but risked unnecessary visual crowding.

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

The selected `alpha=0.2` EM matrix is the reference.

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

1. EM adds meaningful cluster compactness over Manhattan distance.
2. The current 10% candidate fraction is sufficient; wider candidate graphs are expensive and nearly identical.
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

- keep `candidate_k` at 10% of recipe count
- set BLOSUM `alpha=0.2`
- set UMAP `n_neighbors=10`
- retain UMAP `min_dist=0.05` and `random_state=42`

Not adopted:

- exact EM
- wider candidate defaults
- dominant-ingredient template neighbors
- hierarchy-aware ingredient-context distance
- `min_dist=0`

## Reproducibility and limitations

The committed `scripts/test_constrained_em.py` supports candidate-width, Manhattan, clustering, artifact, and UMAP-grid evaluation. Smoothing, template-neighbor, and context-distance variants were isolated throwaway experiments; their durable results are recorded here, but their experimental code and large matrices were not committed.

The six pre-existing stale Barcart distance-test failures encountered during setup are tracked in GitHub issue #29.
