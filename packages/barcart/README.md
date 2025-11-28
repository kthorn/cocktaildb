# Barcart

Backend code for cocktail analytics - recipe and ingredient similarities.

## Features

- **Hierarchical Ingredient Trees**: Build weighted ingredient taxonomies from DataFrames
- **Distance Metrics**: Compute tree-based distances between ingredients
- **Earth Mover's Distance**: Compare recipe similarity using optimal transport
- **Neighborhood Analysis**: Find k-nearest neighbors with Boltzmann weighting
- **Iterative Refinement**: BLOSUM-like cost matrix updates from recipe pairs

## Installation

### From Git (Recommended)

```bash
pip install git+https://github.com/username/cocktail-analytics.git
```

### For Development

```bash
git clone https://github.com/username/cocktail-analytics.git
cd cocktail-analytics
pip install -e ".[dev]"
```

## Quick Start

```python
import pandas as pd
from barcart import build_ingredient_tree, emd_matrix, knn_matrix

# Build ingredient hierarchy
tree, parent_map = build_ingredient_tree(ingredients_df)

# Compute ingredient distance matrix
from barcart import build_ingredient_distance_matrix
dist_matrix, ingredient_registry = build_ingredient_distance_matrix(parent_map)

# Build recipe volume matrix
from barcart import build_recipe_volume_matrix
vol_matrix, recipe_registry = build_recipe_volume_matrix(
    recipes_df,
    ingredient_registry
)

# Compute recipe similarities with EMD
recipe_distances = emd_matrix(vol_matrix, dist_matrix)

# Find nearest neighbors
nn_idx, nn_dist = knn_matrix(recipe_distances, k=5)
```

## API Reference

### Tree Building
- `build_ingredient_tree()` - Constructs hierarchical ingredient trees

### Distance Computations
- `weighted_distance()` - Tree-based weighted distance between nodes
- `build_ingredient_distance_matrix()` - Pairwise distance matrix

### Recipe Analysis
- `build_recipe_volume_matrix()` - Convert recipe DataFrame to volume matrix
- `compute_emd()` - Earth Mover's Distance between two recipes
- `emd_matrix()` - Pairwise EMD for all recipes

### Neighborhood Analysis
- `knn_matrix()` - Find k-nearest neighbors
- `report_neighbors()` - Human-readable neighbor report for any entity type
- `neighbor_weight_matrix()` - Weighted neighbor matrix

### Advanced Analytics
- `expected_ingredient_match_matrix()` - Expected matches from recipe pairs
- `m_step_blosum()` - BLOSUM-like cost matrix update

### Utilities
- `build_index_to_id()` - Reverse mapping from indices to IDs

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
ruff format barcart/

# Lint
ruff check barcart/

# Type check
mypy barcart/
```

## Requirements

- Python 3.11+
- numpy
- pandas
- POT (Python Optimal Transport)
- tqdm
- joblib

## License

MIT License - see LICENSE file for details.
