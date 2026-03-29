# Barcart Monorepo Migration Design

**Date:** 2025-11-28
**Status:** Approved

## Overview

Migrate the `barcart` package from `/home/kurtt/cocktail-analytics` into the cocktaildb repository to create a monorepo structure. This enables:
- Local exploration and development with barcart algorithms
- Integration of barcart into backend analytics Lambda functions
- Easy migration of successful ideas from local experiments to production

## Use Cases

1. **Local development**: Use barcart for exploratory analysis with local database copies
2. **Production analytics**: Integrate barcart algorithms into pre-computed analytics stored in S3
3. **Iterative workflow**: Experiment locally → validate → migrate to analytics Lambda

## Design Decisions

### Repository Structure

```
cocktaildb/
├── packages/
│   └── barcart/
│       ├── barcart/              # Package source code
│       │   ├── __init__.py
│       │   ├── distance.py
│       │   ├── em_learner.py
│       │   ├── registry.py
│       │   └── reporting.py
│       ├── tests/                # Package tests
│       ├── docs/                 # Sphinx documentation
│       ├── pyproject.toml        # Package metadata & dev deps
│       ├── requirements.txt      # Runtime deps (for Docker caching)
│       ├── README.md
│       └── LICENSE
├── api/
│   ├── analytics/
│   │   ├── Dockerfile           # Updated to install barcart
│   │   ├── requirements.txt
│   │   └── analytics_refresh.py # Can now import barcart
│   └── ...
├── scripts/                      # Can import barcart for local analysis
└── ...
```

**Rationale:**
- `packages/` clearly indicates installable Python packages
- Barcart remains self-contained and independently installable
- Scales well for future shared packages
- Clean separation from cocktaildb API code

### Migration Strategy

- **Fresh copy**: Copy current state of barcart without git history
- **Archive original**: Keep `/home/kurtt/cocktail-analytics` as-is for historical reference
- **No git surgery**: Avoid complexity of `git subtree` or `git filter-repo`

**Rationale:**
- Simpler to execute
- Cleaner monorepo history
- Original repo available for reference if needed
- Early stage makes history preservation less critical

### Dependency Management

- **Independent pyproject.toml**: Maintain barcart's own package metadata
- **Separate requirements.txt**: Extract runtime dependencies for Docker layer caching

**Rationale:**
- Barcart remains independently installable: `pip install -e packages/barcart`
- Easy to use in Docker: `COPY packages/barcart/ && pip install ./barcart`
- Could be extracted back to separate repo if needed
- Docker optimization: cache heavy dependencies (numpy, pandas, POT) separately from code

### Testing

- Tests stay in `packages/barcart/tests/`
- Run with `pytest packages/barcart/tests/`
- Self-contained with the package

**Rationale:**
- Maintains package abstraction
- Tests travel with the code
- Clear ownership and scope

### Documentation

- Keep Sphinx docs in `packages/barcart/docs/`
- README.md stays with package
- Self-contained documentation

**Rationale:**
- Package documentation lives with the package
- Maintains independence
- Can be built separately if needed

## Docker Integration

Updated `api/analytics/Dockerfile` with optimized layer caching:

```dockerfile
FROM public.ecr.aws/lambda/python:3.12

# Layer 1: Install barcart dependencies (heavy, rarely change)
COPY packages/barcart/requirements.txt /tmp/barcart-requirements.txt
RUN pip install --no-cache-dir -r /tmp/barcart-requirements.txt

# Layer 2: Install analytics dependencies (rarely change)
COPY analytics/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Layer 3: Copy shared modules (change occasionally)
COPY db/ ${LAMBDA_TASK_ROOT}/db/
COPY utils/ ${LAMBDA_TASK_ROOT}/utils/
COPY core/ ${LAMBDA_TASK_ROOT}/core/

# Layer 4: Install barcart package code (changes frequently)
COPY packages/barcart/ ${LAMBDA_TASK_ROOT}/packages/barcart/
RUN pip install --no-deps ${LAMBDA_TASK_ROOT}/packages/barcart/

# Layer 5: Copy analytics function code (changes frequently)
COPY analytics/analytics_refresh.py ${LAMBDA_TASK_ROOT}/

CMD [ "analytics_refresh.lambda_handler" ]
```

**Rationale:**
- Heavy dependencies (numpy, pandas, POT) installed early and cached
- Barcart code copied late since it changes frequently
- Optimal build times: expensive layers cached, changing layers fast
- Analytics Lambda already containerized and runs infrequently, so larger image size acceptable

## Package Installation & Usage

### Local Development

```bash
# One-time setup
pip install -e packages/barcart

# In scripts
from barcart import build_ingredient_tree, emd_matrix
# Use with DataFrames prepared by caller
```

### Analytics Lambda

Installed automatically via Dockerfile. Usage in `analytics_refresh.py`:

```python
from barcart import emd_matrix, knn_matrix
from db.database import get_database

# Fetch data from database
db = get_database()
recipes_df = db.get_recipes_dataframe()  # Add helper methods as needed

# Use barcart algorithms
distances = emd_matrix(recipe_volumes, ingredient_distances)

# Store results in S3 analytics cache
```

### Design Principle

**Barcart stays data-agnostic.** It operates on DataFrames and arrays. Database access, DataFrame preparation, and results storage are handled by calling code.

**Rationale:**
- Clean separation of concerns
- Barcart is purely algorithmic
- Easy to test with synthetic data
- Flexible for different data sources (API, DB, files)

## Migration Workflow

1. **Experiment locally**: Use barcart with local database copy for exploration
2. **Develop analytics**: Prototype new metrics using barcart algorithms
3. **Integrate**: Add successful ideas to `analytics_refresh.py`
4. **Deploy**: Docker build automatically installs barcart
5. **Refresh**: Trigger analytics refresh to generate new metrics

## Implementation Checklist

1. **Preparation**
   - Create feature branch: `feature/monorepo-barcart`
   - Create `packages/` directory

2. **File Migration**
   - Copy barcart source: `cocktail-analytics/barcart/` → `packages/barcart/`
   - Copy tests: `cocktail-analytics/tests/` → `packages/barcart/tests/`
   - Copy docs: `cocktail-analytics/docs/` → `packages/barcart/docs/`
   - Copy LICENSE, README.md, pyproject.toml

3. **Dependencies**
   - Create `packages/barcart/requirements.txt`
   - Extract from pyproject.toml: numpy, pandas, POT, tqdm, joblib with versions

4. **Docker Integration**
   - Update `api/analytics/Dockerfile` with multi-stage build
   - Ensure `packages/` in SAM build context

5. **Verification**
   - Install locally: `pip install -e packages/barcart`
   - Run tests: `pytest packages/barcart/tests/`
   - Test imports: `python -c "from barcart import build_ingredient_tree"`
   - Build Docker: `sam build AnalyticsRefreshFunction`

6. **Documentation**
   - Update root README.md about monorepo structure
   - Add barcart note to CLAUDE.md

## Non-Goals

- **Not preserving git history**: Clean break for simpler implementation
- **Not modifying original repo**: Stays available for reference
- **Not CI integration**: No CI pipeline exists yet
- **Not creating API endpoints**: Focus is on analytics and local use, not public API

## Risks & Mitigations

**Risk**: Large Lambda package size from heavy dependencies
**Mitigation**: Already accepted - analytics Lambda is containerized and runs infrequently, cold starts not critical

**Risk**: Build context size increase
**Mitigation**: Barcart is small (~5 Python files), minimal impact

**Risk**: Dependency conflicts between barcart and analytics
**Mitigation**: Both use similar scientific Python stack (numpy, pandas), conflicts unlikely

## Future Considerations

- Could add more packages to `packages/` as monorepo grows
- Barcart could be extracted back to separate repo if needed (still independently installable)
- Could add barcart-powered API endpoints later for recipe similarity features
- May add CI/CD in future to run barcart tests automatically
