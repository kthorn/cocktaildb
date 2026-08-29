# Barcart Package Design

**Date:** 2025-10-24
**Status:** Approved for implementation

## Overview

Transform the `utils/` directory into a pip-installable package called `barcart` that provides backend code for cocktail analytics, specifically recipe and ingredient similarity computations. The package will be used both for exploratory data analysis (EDA) and for serving analytics.

## Requirements

- **Package name:** barcart
- **Python versions:** 3.11+
- **Installation:** Git-only (no PyPI publishing)
- **Build system:** setuptools with pyproject.toml (PEP 517/518)
- **Code structure:** Flat layout (barcart/ at repo root)
- **License:** MIT (already in repo)
- **Dev tooling:** pytest, ruff, mypy

## Architecture

### Project Structure

```
cocktail-analytics/
├── barcart/
│   ├── __init__.py      # Public API exports
│   └── distance.py      # Core analytics (moved from utils/)
├── tests/
│   ├── __init__.py
│   └── test_distance.py # Test suite
├── pyproject.toml       # Package metadata & dependencies
├── README.md            # Package documentation
├── .gitignore          # Ignore build artifacts
└── utils/               # Original code (keep temporarily)
```

**Rationale:** Flat layout is simpler than src/ layout for small packages. The barcart/ directory becomes the importable package, while keeping utils/ temporarily for backward compatibility.

### Public API

The `barcart/__init__.py` exposes all main functions from `distance.py`:

**Tree building:**
- `build_ingredient_tree()` - Constructs hierarchical ingredient trees

**Distance computations:**
- `weighted_distance()` - Tree-based weighted distance between nodes
- `build_ingredient_distance_matrix()` - Pairwise distance matrix

**Recipe analysis:**
- `build_recipe_volume_matrix()` - Convert recipe DataFrame to volume matrix
- `compute_emd()` - Earth Mover's Distance between two recipes
- `emd_matrix()` - Pairwise EMD for all recipes

**Neighborhood analysis:**
- `knn_matrix()` - Find k-nearest neighbors
- `report_ingredient_neighbors()` - Human-readable neighbor report
- `neighbor_weight_matrix()` - Weighted neighbor matrix

**Advanced analytics:**
- `expected_ingredient_match_matrix()` - Expected matches from recipe pairs
- `m_step_blosum()` - BLOSUM-like cost matrix update

**Utilities:**
- `build_index_to_id()` - Reverse mapping from indices to IDs

**Usage example:**
```python
from barcart import build_ingredient_tree, emd_matrix, knn_matrix
```

### Dependencies

**Core runtime dependencies:**
- `numpy` - Array operations and distance matrices
- `pandas` - DataFrame operations
- `POT` (Python Optimal Transport) - EMD computations
- `tqdm` - Progress bars
- `joblib` - Parallel computation support

**Development dependencies (optional):**
- `pytest` - Testing framework
- `pytest-cov` - Coverage reporting
- `ruff` - Linting and formatting
- `mypy` - Static type checking

### Package Configuration

The `pyproject.toml` defines:

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "barcart"
version = "0.1.0"
description = "Backend code for cocktail analytics - recipe and ingredient similarities"
requires-python = ">=3.11"
license = {text = "MIT"}
dependencies = [
    "numpy",
    "pandas",
    "POT",
    "tqdm",
    "joblib",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-cov",
    "ruff",
    "mypy",
]
```

## Development Workflow

**Installation:**
```bash
# Editable install for development
pip install -e .

# With dev dependencies
pip install -e ".[dev]"

# From git (for users)
pip install git+https://github.com/username/cocktail-analytics.git
```

**Development cycle:**
1. Make changes to `barcart/distance.py`
2. Run tests: `pytest`
3. Check types: `mypy barcart/`
4. Format code: `ruff format barcart/`
5. Lint: `ruff check barcart/`

**Testing strategy:**
- Basic smoke tests to verify imports work
- Test key functions with sample data
- Use pytest fixtures for common test data
- Track coverage with pytest-cov

## Migration Plan

**Phase 1: Create package structure**
1. Create `barcart/` directory
2. Copy `utils/distance.py` → `barcart/distance.py`
3. Create `barcart/__init__.py` with API exports
4. Create `tests/` directory structure

**Phase 2: Configure package**
1. Create `pyproject.toml` with metadata and dependencies
2. Create/update `.gitignore` for build artifacts
3. Create `README.md` with installation and usage docs

**Phase 3: Add development tooling**
1. Configure pytest in `pyproject.toml`
2. Configure ruff in `pyproject.toml`
3. Configure mypy in `pyproject.toml`
4. Create initial test file

**Phase 4: Verify installation**
1. Test editable install: `pip install -e .`
2. Verify imports work: `python -c "from barcart import build_ingredient_tree"`
3. Run test suite: `pytest`

**Phase 5: Cleanup (later)**
- Delete `utils/` directory when ready
- Update any existing notebooks/scripts to use `barcart` instead of `utils`

## Design Decisions

**Why flat layout instead of src/ layout?**
- Simpler for small packages
- Easier to navigate
- src/ layout benefits (import isolation) are less critical for this use case

**Why keep utils/ temporarily?**
- Allows gradual migration
- Existing code continues to work
- No immediate breaking changes

**Why minimal restructuring?**
- The existing code in `distance.py` is well-organized
- All functions have excellent docstrings
- No need to split into multiple modules yet
- Can refactor later if package grows

**Why setuptools over poetry/hatch?**
- Simplest option for git-only installation
- PEP 517/518 compliant
- Minimal configuration needed
- No lock files needed for this use case

## Success Criteria

1. Package installs successfully via `pip install -e .`
2. All public API functions are importable via `from barcart import ...`
3. Existing functionality remains unchanged (no breaking changes)
4. Tests pass and provide reasonable coverage
5. Type checking passes with mypy
6. Code passes ruff linting
7. README provides clear installation and usage instructions

## Future Considerations

- Split `distance.py` into multiple modules if it grows
- Add more comprehensive tests with realistic data
- Add CI/CD pipeline (GitHub Actions)
- Consider PyPI publishing if package is useful to others
- Add type stubs or improve type annotations
- Add examples/tutorials in docs/
