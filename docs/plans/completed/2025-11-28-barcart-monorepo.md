# Barcart Monorepo Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate the barcart package from `/home/kurtt/cocktail-analytics` into the cocktaildb monorepo at `packages/barcart/` and integrate it into the analytics Lambda Docker build.

**Architecture:** Copy barcart package files into new `packages/` directory, create requirements.txt for Docker layer caching, update analytics Dockerfile with multi-stage build to install barcart with optimized caching.

**Tech Stack:** Python 3.11+, Docker, AWS Lambda, SAM

---

## Task 1: Create packages directory structure

**Files:**
- Create: `packages/barcart/.gitkeep` (temporary marker)

**Step 1: Create packages/barcart directory**

```bash
mkdir -p packages/barcart
```

**Step 2: Verify directory created**

```bash
ls -la packages/
```

Expected: `barcart/` directory exists

**Step 3: Commit directory structure**

```bash
git add packages/
git commit -m "feat: create packages directory for monorepo structure"
```

---

## Task 2: Copy barcart source code

**Files:**
- Create: `packages/barcart/barcart/*.py` (all source files)

**Step 1: Copy barcart source package**

```bash
cp -r /home/kurtt/cocktail-analytics/barcart/ packages/barcart/
```

**Step 2: Verify source files copied**

```bash
find packages/barcart/barcart -name "*.py"
```

Expected output should include:
- `packages/barcart/barcart/__init__.py`
- `packages/barcart/barcart/distance.py`
- `packages/barcart/barcart/em_learner.py`
- `packages/barcart/barcart/registry.py`
- `packages/barcart/barcart/reporting.py`

**Step 3: Stage source files**

```bash
git add packages/barcart/barcart/
```

---

## Task 3: Copy barcart tests

**Files:**
- Create: `packages/barcart/tests/*.py` (all test files)

**Step 1: Copy test directory**

```bash
cp -r /home/kurtt/cocktail-analytics/tests/ packages/barcart/
```

**Step 2: Verify tests copied**

```bash
find packages/barcart/tests -name "test_*.py"
```

Expected: Test files visible

**Step 3: Stage test files**

```bash
git add packages/barcart/tests/
```

---

## Task 4: Copy barcart documentation

**Files:**
- Create: `packages/barcart/docs/` (documentation files)

**Step 1: Copy docs directory**

```bash
cp -r /home/kurtt/cocktail-analytics/docs/ packages/barcart/
```

**Step 2: Verify docs copied**

```bash
ls -la packages/barcart/docs/
```

Expected: Documentation files present

**Step 3: Stage documentation**

```bash
git add packages/barcart/docs/
```

---

## Task 5: Copy package metadata files

**Files:**
- Create: `packages/barcart/pyproject.toml`
- Create: `packages/barcart/README.md`
- Create: `packages/barcart/LICENSE`

**Step 1: Copy metadata files**

```bash
cp /home/kurtt/cocktail-analytics/pyproject.toml packages/barcart/
cp /home/kurtt/cocktail-analytics/README.md packages/barcart/
cp /home/kurtt/cocktail-analytics/LICENSE packages/barcart/
```

**Step 2: Verify files copied**

```bash
ls -la packages/barcart/ | grep -E "(pyproject.toml|README.md|LICENSE)"
```

Expected: All three files present

**Step 3: Stage metadata files**

```bash
git add packages/barcart/pyproject.toml packages/barcart/README.md packages/barcart/LICENSE
```

**Step 4: Commit barcart package**

```bash
git commit -m "feat: add barcart package from cocktail-analytics repo

Migrate barcart package into monorepo structure at packages/barcart/.
Includes source code, tests, docs, and package metadata.

Source: /home/kurtt/cocktail-analytics @ current HEAD"
```

---

## Task 6: Create requirements.txt for Docker caching

**Files:**
- Create: `packages/barcart/requirements.txt`

**Step 1: Create requirements.txt**

Create `packages/barcart/requirements.txt` with content:

```
numpy>=1.24.0
pandas>=2.0.0
POT>=0.9.0
tqdm>=4.65.0
joblib>=1.3.0
```

**Step 2: Verify file created**

```bash
cat packages/barcart/requirements.txt
```

Expected: Shows the five dependencies with version constraints

**Step 3: Commit requirements.txt**

```bash
git add packages/barcart/requirements.txt
git commit -m "feat: add requirements.txt for Docker layer caching"
```

---

## Task 7: Update analytics Dockerfile

**Files:**
- Modify: `api/analytics/Dockerfile`

**Step 1: Read current Dockerfile**

```bash
cat api/analytics/Dockerfile
```

**Step 2: Replace Dockerfile with updated version**

Replace entire `api/analytics/Dockerfile` with:

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

# Set the CMD to your handler
CMD [ "analytics_refresh.lambda_handler" ]
```

**Step 3: Verify Dockerfile updated**

```bash
cat api/analytics/Dockerfile | grep -A2 "Layer 1"
```

Expected: Shows Layer 1 comment and barcart requirements copy

**Step 4: Commit Dockerfile changes**

```bash
git add api/analytics/Dockerfile
git commit -m "feat: update analytics Dockerfile to install barcart

Multi-stage build with optimized layer caching:
- Layer 1: Barcart dependencies (numpy, pandas, POT)
- Layer 2: Analytics dependencies
- Layer 3: Shared modules
- Layer 4: Barcart code
- Layer 5: Analytics code

Heavy dependencies cached early, frequently-changing code copied late."
```

---

## Task 8: Verify local installation

**Files:**
- None (verification only)

**Step 1: Install barcart in editable mode**

```bash
pip install -e packages/barcart
```

Expected: Installation completes successfully

**Step 2: Test import**

```bash
python -c "from barcart import build_ingredient_tree; print('Import successful')"
```

Expected: "Import successful"

**Step 3: Verify package metadata**

```bash
pip show barcart
```

Expected: Shows barcart version 0.1.0, location at packages/barcart

---

## Task 9: Run barcart tests

**Files:**
- None (verification only)

**Step 1: Run test suite**

```bash
pytest packages/barcart/tests/ -v
```

Expected: All tests pass (or show current test status)

**Step 2: Check test discovery**

```bash
pytest packages/barcart/tests/ --collect-only
```

Expected: Shows discovered test functions

---

## Task 10: Verify Docker build

**Files:**
- None (verification only)

**Step 1: Build analytics Lambda with SAM**

```bash
sam build AnalyticsRefreshFunction --template-file template.yaml
```

Expected: Build completes successfully with no errors

**Step 2: Check build output for barcart**

```bash
ls .aws-sam/build/AnalyticsRefreshFunction/packages/barcart/
```

Expected: Shows barcart package files in build output

**Step 3: Verify barcart installed in container**

```bash
grep -r "barcart" .aws-sam/build/AnalyticsRefreshFunction/ | head -5
```

Expected: Shows barcart files and installation artifacts

---

## Task 11: Update root README.md

**Files:**
- Modify: `README.md`

**Step 1: Read current README**

```bash
head -30 README.md
```

**Step 2: Add monorepo section**

Add this section to `README.md` after the main project description:

```markdown
## Monorepo Structure

This repository contains multiple packages:

- **`packages/barcart/`** - Cocktail analytics algorithms (recipe similarity, ingredient distance metrics)
  - Install: `pip install -e packages/barcart`
  - Used by analytics Lambda and local analysis scripts
  - Independent package with own tests and documentation

See individual package READMEs for details.
```

**Step 3: Commit README update**

```bash
git add README.md
git commit -m "docs: document monorepo structure in README"
```

---

## Task 12: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Read CLAUDE.md architecture section**

```bash
grep -A10 "Architecture Overview" CLAUDE.md
```

**Step 2: Add packages section**

Add this section to `CLAUDE.md` after the "Architecture Overview" heading:

```markdown
### Packages (`packages/`)
- **Barcart**: Cocktail analytics algorithms (similarity, distance metrics)
  - Location: `packages/barcart/`
  - Purpose: Recipe/ingredient similarity using Earth Mover's Distance and optimal transport
  - Dependencies: numpy, pandas, POT, tqdm, joblib
  - Installation: `pip install -e packages/barcart` (local), automatic in analytics Lambda
  - Tests: `pytest packages/barcart/tests/`
  - **Data-agnostic**: Works with DataFrames, database access handled by callers
  - **Usage pattern**: Local exploration → develop analytics → migrate to `analytics_refresh.py`
```

**Step 3: Commit CLAUDE.md update**

```bash
git add CLAUDE.md
git commit -m "docs: add barcart package to CLAUDE.md architecture"
```

---

## Task 13: Final verification and summary

**Files:**
- None (verification only)

**Step 1: Verify all files in place**

```bash
ls -la packages/barcart/
```

Expected: Shows barcart/, tests/, docs/, pyproject.toml, requirements.txt, README.md, LICENSE

**Step 2: Check git status**

```bash
git status
```

Expected: On branch feature/monorepo-barcart, working tree clean

**Step 3: Review commits**

```bash
git log --oneline main..HEAD
```

Expected: Shows all commits from this migration

**Step 4: Summary check**

Verify these key items:
- [ ] Barcart source copied to packages/barcart/
- [ ] Tests, docs, metadata files present
- [ ] requirements.txt created for Docker
- [ ] analytics/Dockerfile updated with multi-stage build
- [ ] Local installation works (`pip install -e packages/barcart`)
- [ ] Tests run successfully
- [ ] SAM build completes
- [ ] Documentation updated (README.md, CLAUDE.md)
- [ ] All changes committed to feature branch

---

## Post-Implementation

After completing all tasks:

1. **Test the integration**: Write a simple test in `analytics_refresh.py` that imports barcart
2. **Optional: Deploy to dev**: If ready, merge to main and deploy to test in dev environment
3. **Archive original repo**: Add note to `/home/kurtt/cocktail-analytics` README that package migrated

## References

- Design document: `docs/plans/2025-11-28-barcart-monorepo-design.md`
- Original repo: `/home/kurtt/cocktail-analytics`
- Barcart package: `packages/barcart/README.md`
