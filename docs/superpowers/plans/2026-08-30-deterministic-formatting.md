# Deterministic Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one deterministic Ruff/Prettier formatting path for local hooks, editors, agents, and CI, then commit the mechanical repository baseline separately.

**Architecture:** pre-commit is the sole orchestration entry point. Its local Python and Node hooks provision pinned Ruff and Prettier versions without a root package manifest; CI invokes those same hooks. The first commit contains the design/plan, configuration, hooks, CI, Dependabot maintenance, and documentation; the second contains formatter output only.

**Tech Stack:** Ruff 0.16.5, Prettier 3.9.6, pre-commit 4.6.2, Python 3.12.10, Node 22.22.2, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-08-30-deterministic-formatting-design.md`

## Global Constraints

- Ruff is the sole Python formatter; do not add or change Python lint policy.
- Prettier is the sole frontend formatter; do not add Biome, ESLint, `package.json`, Husky, Lefthook, or semantic fixes.
- Root Ruff policy is `line-length = 88` and `target-version = "py311"`, matching Barcart.
- Prettier policy is spaces, width 4, single quotes, and print width 100.
- Prettier scope is static `src/web` JS/MJS/HTML plus `tests` JS/MJS; Jinja templates, CSS, JSON, generated `src/web/js/config.js`, and other file types remain excluded.
- Pin Ruff 0.16.5, Prettier 3.9.6, pre-commit 4.6.2, Python 3.12.10, and Node 22.22.2 exactly.
- Pin every GitHub Action to the full reviewed commit SHA with a version comment.
- The final branch must contain exactly two commits above `origin/main`: tooling/documentation first, mechanical baseline second.
- The baseline commit must contain only formatter-generated changes; no hand cleanup or semantic edits.
- Merge with a merge commit, not squash, so the baseline remains independently addressable for blame.
- Follow #35 only. Biome linting is #45 and Python runtime modernization is #46.

---

## Execution Preparation (controller only)

The design was refined through several local commits. Before Task 1, fold those unpublished document commits into the agreed tooling commit without deleting their files.

- [ ] **Step 1: Verify the isolated branch and clean worktree**

```bash
cd /home/kurtt/cocktaildb/.worktrees/issue-35
test "$(git branch --show-current)" = "dev/35-deterministic-formatting"
test -z "$(git status --porcelain)"
git merge-base --is-ancestor origin/main HEAD
```

Expected: all commands exit 0.

- [ ] **Step 2: Rewind only the unpublished branch history while preserving files**

```bash
git reset --mixed origin/main
git status --short
```

Expected: the refined spec and this plan appear as untracked files; no application file is modified or deleted.

---

### Task 1: Add formatter configuration, hooks, CI, and documentation

**Files:**
- Create: `ruff.toml`
- Create: `.prettierrc`
- Create: `.prettierignore`
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/format.yml`
- Modify: `.github/dependabot.yml`
- Modify: `AGENTS.md`
- Include: `docs/superpowers/specs/2026-08-30-deterministic-formatting-design.md`
- Include: `docs/superpowers/plans/2026-08-30-deterministic-formatting.md`

**Interfaces:**
- Consumes: existing Barcart Ruff minimum (`py311`, 88 columns), existing generated-config ignore, existing Dependabot weekly/four-day policy.
- Produces: hook IDs `ruff-format` and `prettier`; CI command `python -m pre_commit run --all-files --show-diff-on-failure`; exact documented local commands used by Task 2.

- [ ] **Step 1: Install the orchestration dependency and confirm the configuration is absent**

```bash
cd /home/kurtt/cocktaildb/.worktrees/issue-35
~/miniforge3/envs/cocktaildb/bin/python -m pip install pre-commit==4.6.2
test ! -e ruff.toml
test ! -e .prettierrc
test ! -e .prettierignore
test ! -e .pre-commit-config.yaml
test ! -e .github/workflows/format.yml
```

Expected: install succeeds and every absence assertion exits 0.

- [ ] **Step 2: Add the root Ruff configuration**

Create `ruff.toml` exactly:

```toml
line-length = 88
target-version = "py311"
```

- [ ] **Step 3: Add the trackable Prettier configuration and excludes**

Create `.prettierrc` exactly:

```json
{
    "useTabs": false,
    "tabWidth": 4,
    "singleQuote": true,
    "printWidth": 100
}
```

Create `.prettierignore` exactly:

```text
api/templates/
src/web/js/config.js
```

Confirm the extensionless config is tracked rather than swallowed by the repository's `*.json` ignore:

```bash
! git check-ignore -q .prettierrc
```

- [ ] **Step 4: Add isolated local pre-commit hooks**

Create `.pre-commit-config.yaml` exactly:

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-format
        name: ruff format
        entry: ruff format
        language: python
        additional_dependencies:
          - ruff==0.16.5
        types:
          - python

      - id: prettier
        name: prettier
        entry: prettier --write
        language: node
        additional_dependencies:
          - prettier@3.9.6
        files: ^(src/web/.*\.(js|mjs|html)|tests/.*\.(js|mjs))$
```

Validate and provision the hook environments through the selected interpreter:

```bash
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit validate-config
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit install-hooks
```

Expected: both commands exit 0.

- [ ] **Step 5: Add the SHA-pinned formatting workflow**

Create `.github/workflows/format.yml` exactly:

```yaml
name: Formatting

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  format:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false

      - name: Set up Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: 3.12.10

      - name: Set up Node
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: 22.22.2

      - name: Install pre-commit
        run: python -m pip install pre-commit==4.6.2

      - name: Check formatting
        run: python -m pre_commit run --all-files --show-diff-on-failure
```

- [ ] **Step 6: Add GitHub Actions update maintenance**

Append this third entry under `updates:` in `.github/dependabot.yml`, preserving the two existing pip entries:

```yaml
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 4
```

- [ ] **Step 7: Document the exact local/editor/agent workflow**

Add this section after `## Build, Test, and Development Commands` in `AGENTS.md`:

```markdown
## Formatting

- Requires Node 22.7 or newer; Node 22.22.2 is the tested version. The floor is required so `node --check` detects ESM syntax without a root `package.json`.
- Install hooks with `~/miniforge3/envs/cocktaildb/bin/python -m pip install pre-commit==4.6.2 && ~/miniforge3/envs/cocktaildb/bin/python -m pre_commit install`.
- Run every formatter check with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files`.
- Format/check Python only with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run ruff-format --all-files`.
- Format/check static frontend JS/MJS/HTML only with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run prettier --all-files`.
- Ruff and Prettier editor extensions use `ruff.toml` and `.prettierrc`; CI is authoritative.
```

Update the existing coding-style bullets so Python names Ruff as the repository formatter and JavaScript names Prettier rather than saying only to follow existing style. Do not alter unrelated repository instructions.

- [ ] **Step 8: Validate the tooling commit without generating the baseline**

```bash
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit validate-config
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit install-hooks
! git check-ignore -q .prettierrc
git diff --check
git status --short
```

Expected: validation succeeds. Status contains only Task 1 files plus the refined spec and plan; no tracked Python/JS/MJS/HTML application file is modified yet.

- [ ] **Step 9: Commit the complete tooling/documentation unit**

```bash
git add \
  ruff.toml \
  .prettierrc \
  .prettierignore \
  .pre-commit-config.yaml \
  .github/workflows/format.yml \
  .github/dependabot.yml \
  AGENTS.md \
  docs/superpowers/specs/2026-08-30-deterministic-formatting-design.md \
  docs/superpowers/plans/2026-08-30-deterministic-formatting.md
git commit -m "dev: add deterministic formatting checks (#35)"
git status --short
```

Expected: commit succeeds and the worktree is clean.

---

### Task 2: Generate and verify the mechanical formatting baseline

**Files:**
- Modify mechanically: all tracked Python files selected by `types: [python]`
- Modify mechanically: matching `src/web/**/*.{js,mjs,html}`
- Modify mechanically: matching `tests/**/*.{js,mjs}`
- Must not modify: formatter config, documentation, Jinja templates, CSS, JSON, generated files, or unrelated artifacts

**Interfaces:**
- Consumes: Task 1 hook IDs and exact pinned tool environments.
- Produces: one formatter-only baseline commit and a clean, idempotent checkout accepted by local hooks and CI.

- [ ] **Step 1: Record the pre-format test baseline**

Use unique logs so parallel sessions cannot overwrite evidence:

```bash
cd /home/kurtt/cocktaildb/.worktrees/issue-35
~/miniforge3/envs/cocktaildb/bin/python -m pip install -r requirements-test.txt
~/miniforge3/envs/cocktaildb/bin/python -m pip install -e 'packages/barcart[dev]'
~/miniforge3/envs/cocktaildb/bin/python -c 'import pytest, pytest_cov; import barcart'
root_log="$(mktemp)"
barcart_log="$(mktemp)"
set +e
~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/ -v >"$root_log" 2>&1
root_status=$?
~/miniforge3/envs/cocktaildb/bin/python -m pytest packages/barcart/tests/ -q >"$barcart_log" 2>&1
barcart_status=$?
set -e
printf 'root_status=%s root_log=%s\nbarcart_status=%s barcart_log=%s\n' \
  "$root_status" "$root_log" "$barcart_status" "$barcart_log"
tail -40 "$root_log"
tail -40 "$barcart_log"
```

Record both exit codes and complete pytest/coverage summaries in the implementation report. Existing environment-dependent failures may continue only if their complete post-format result is identical.

- [ ] **Step 2: Run the formatters and verify the expected first-pass failure**

```bash
set +e
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files --show-diff-on-failure
first_status=$?
set -e
test "$first_status" -ne 0
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files --show-diff-on-failure
```

Expected: the first run rewrites files and exits nonzero; the second run exits 0.

- [ ] **Step 3: Reject any out-of-scope formatter change**

```bash
unexpected="$({
  git diff --name-only --diff-filter=ACMRT
} | grep -Ev '\.pyi?$|^src/web/.*\.(js|mjs|html)$|^tests/.*\.(js|mjs)$' || true)"
if [ -n "$unexpected" ]; then
  printf 'Unexpected formatter output:\n%s\n' "$unexpected" >&2
  exit 1
fi

git diff --name-only -- api/templates src/web/js/config.js '*.css' '*.json'
```

Expected: `unexpected` is empty and the explicit excluded-path diff is empty. Do not hand-edit formatter output; correct configuration and rerun if scope is wrong.

- [ ] **Step 4: Inspect and commit only the mechanical baseline**

```bash
git diff --stat
git diff --check
git add -u
git diff --cached --name-only
git commit -m "style: establish formatting baseline (#35)"
```

Before committing, confirm the staged list contains only the allowed Python/frontend/test file classes from Step 3. Expected: the commit succeeds and contains no Task 1 file.

- [ ] **Step 5: Prove formatter idempotence**

```bash
before="$(git status --porcelain)"
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files --show-diff-on-failure
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files --show-diff-on-failure
after="$(git status --porcelain)"
test "$before" = "$after"
test -z "$after"
```

Expected: both runs exit 0 and the clean status remains byte-for-byte unchanged.

- [ ] **Step 6: Verify JavaScript syntax and all frontend contracts**

```bash
while IFS= read -r -d '' file; do
  node --check "$file"
done < <(
  git ls-files -z | grep -zE '^(src/web/.*\.(js|mjs)|tests/.*\.(js|mjs))$'
)
~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_frontend_node.py -q
node tests/test_frontend_ingredient_display.js
```

Expected: every command exits 0.

- [ ] **Step 7: Re-run Python validation and compare complete results**

```bash
post_root_log="$(mktemp)"
post_barcart_log="$(mktemp)"
set +e
~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/ -v >"$post_root_log" 2>&1
post_root_status=$?
~/miniforge3/envs/cocktaildb/bin/python -m pytest packages/barcart/tests/ -q >"$post_barcart_log" 2>&1
post_barcart_status=$?
set -e
printf 'post_root_status=%s post_root_log=%s\npost_barcart_status=%s post_barcart_log=%s\n' \
  "$post_root_status" "$post_root_log" "$post_barcart_status" "$post_barcart_log"
tail -40 "$post_root_log"
tail -40 "$post_barcart_log"
~/miniforge3/envs/cocktaildb/bin/python -m compileall -q api packages/barcart scripts tests
```

Expected: post-format exit codes and pytest/coverage summaries equal the Step 1 baseline, and compileall exits 0. If a result worsens or changes, stop and investigate rather than accepting formatter output.

- [ ] **Step 8: Prove one-file blast-radius isolation**

```bash
probe=src/web/js/api.js
backup="$(mktemp)"
cp "$probe" "$backup"
printf '\n// formatting blast-radius probe\n' >>"$probe"
set +e
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run prettier --files "$probe"
probe_status=$?
set -e
case "$probe_status" in
  0|1) ;;
  *) exit "$probe_status" ;;
esac
test "$(git diff --name-only | wc -l)" -eq 1
test "$(git diff --name-only)" = "$probe"
cp "$backup" "$probe"
rm -f "$backup"
test -z "$(git status --porcelain)"
```

Expected: only `api.js` changes during the probe and restoring it returns the worktree to clean.

- [ ] **Step 9: Verify the final two-commit history and branch diff**

```bash
test "$(git rev-list --count origin/main..HEAD)" -eq 2
git log --oneline origin/main..HEAD
git diff --check origin/main...HEAD
git status --short
```

Expected subjects, newest first:

```text
style: establish formatting baseline (#35)
dev: add deterministic formatting checks (#35)
```

The final status is empty.
