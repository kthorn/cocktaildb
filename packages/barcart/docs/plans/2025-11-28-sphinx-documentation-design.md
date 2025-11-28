# Sphinx Documentation Design

**Date:** 2025-11-28
**Status:** Approved

## Purpose

Create auto-generated API reference documentation for the barcart package using Sphinx. The documentation is for personal use when context-switching between the local research repo and production cocktail database website.

## Audience

Single user/developer (package author) who needs quick API reference when using the package across multiple projects.

## Scope

**Included:**
- Auto-generated API reference from NumPy-style docstrings
- sphinx-rtd-theme for clean, familiar interface
- Quick installation and usage instructions
- API docs for all four modules: distance, registry, reporting, em_learner

**Excluded:**
- Existing design documents from `docs/plans/` (kept separate)
- Comprehensive tutorials or narrative documentation
- General-audience documentation

## Documentation Structure

```
docs/
├── source/
│   ├── conf.py           # Sphinx configuration
│   ├── index.rst         # Main page with toctree
│   └── api/
│       ├── index.rst     # API reference landing page
│       ├── distance.rst  # Auto-docs for distance module
│       ├── registry.rst  # Auto-docs for registry module
│       ├── reporting.rst # Auto-docs for reporting module
│       └── em_learner.rst# Auto-docs for em_learner module
├── build/                # Generated HTML (gitignored)
└── Makefile              # Build commands
```

## Technical Configuration

**Sphinx Extensions:**
- `sphinx.ext.autodoc` - Auto-generate docs from docstrings
- `sphinx.ext.napoleon` - Parse NumPy-style docstrings
- `sphinx.ext.viewcode` - Add [source] links to documentation
- `sphinx.ext.intersphinx` - Link to external docs (numpy, pandas)

**Theme:**
- `sphinx-rtd-theme` (Read the Docs theme)

**Dependencies:**
Add to `pyproject.toml` dev dependencies:
- `sphinx>=7.0.0`
- `sphinx-rtd-theme>=2.0.0`

**Git Configuration:**
- Add `docs/build/` to `.gitignore` (generated content)
- Keep `docs/source/` tracked

## Build Commands

```bash
# Build HTML documentation
cd docs && make html

# Clean build artifacts
cd docs && make clean

# View documentation
open docs/build/html/index.rst
```

## API Documentation Approach

Each module uses the `automodule` directive with:
- `:members:` - Document all members
- `:undoc-members:` - Include members without docstrings
- `:show-inheritance:` - Show class inheritance

This automatically generates documentation for:
- Function signatures with type hints
- NumPy-style Parameters, Returns, Examples sections
- Class definitions and methods
- Source code links

## Rationale

**Why API reference only?**
- Single user knows the architecture and design decisions
- Primary need is quick reference for function signatures and parameters
- Reduces maintenance burden

**Why NumPy-style docstrings?**
- Already used consistently throughout the codebase
- Well-suited for scientific/analytical packages
- Napoleon extension provides excellent rendering

**Why sphinx-rtd-theme?**
- Widely recognized and familiar
- Clean, professional appearance
- Good navigation for API reference

**Why separate from design docs?**
- Design docs are historical context for architectural decisions
- API docs are current reference for daily use
- Keeps Sphinx focused on its core purpose
