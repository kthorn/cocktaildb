Barcart Documentation
=====================

Backend code for cocktail analytics - recipe and ingredient similarities.

Features
--------

- **Hierarchical Ingredient Trees**: Build weighted ingredient taxonomies from DataFrames
- **Distance Metrics**: Compute tree-based distances between ingredients
- **Earth Mover's Distance**: Compare recipe similarity using optimal transport
- **Neighborhood Analysis**: Find k-nearest neighbors with Boltzmann weighting
- **Iterative Refinement**: BLOSUM-like cost matrix updates from recipe pairs

Installation
------------

From Git (Recommended)
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install git+https://github.com/username/cocktail-analytics.git

For Development
~~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/username/cocktail-analytics.git
   cd cocktail-analytics
   pip install -e ".[dev]"

Quick Start
-----------

.. code-block:: python

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

API Reference
-------------

.. toctree::
   :maxdepth: 2

   api/index

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
