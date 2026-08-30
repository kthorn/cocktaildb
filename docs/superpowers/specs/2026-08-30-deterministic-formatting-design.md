# Deterministic Formatting Design

**Status:** Refined

## Context

GitHub issue #35 records that small Python and frontend edits can trigger large, unrelated formatting changes because the repository has no single documented or enforced formatting path. Barcart has a local Ruff configuration, but the rest of the Python code has no root formatter configuration. Static JavaScript and HTML have no formatter configuration. The repository also has no pre-commit hook or formatting CI workflow.

A clean `origin/main` audit compared Prettier 3.9.6 with Biome 2.5.11. Biome's JavaScript formatter was idempotent, but its experimental HTML formatter changed `src/web/about.html` again on a second pass. That violates #35's idempotence requirement. Prettier formatted the same static frontend scope idempotently and preserved JavaScript syntax and the existing frontend contract tests. Biome linting is valuable but is separately tracked by #45 because its baseline contains 173 findings requiring deliberate review.

The audit is reproducible from separate archives rather than the dirty working checkout. In each archive, initialize a temporary Git repository and build the exact file list with:

```bash
mapfile -t files < <(
    find src/web -type f \( -name '*.js' -o -name '*.mjs' -o -name '*.html' \) -print
    find tests -type f \( -name '*.js' -o -name '*.mjs' \) -print
)
git init
git add .
git -c user.name=audit -c user.email=audit@example.invalid commit -m baseline
```

The Prettier archive used:

```bash
npx --yes prettier@3.9.6 --write --tab-width 4 --single-quote --print-width 100 "${files[@]}"
git add "${files[@]}"
npx --yes prettier@3.9.6 --write --tab-width 4 --single-quote --print-width 100 "${files[@]}"
git diff --name-only -- "${files[@]}"
```

The Biome archive used a `biome.json` with `formatter.indentStyle = "space"`, `formatter.indentWidth = 4`, `formatter.lineWidth = 100`, `javascript.formatter.quoteStyle = "single"`, `html.experimentalFullSupportEnabled = true`, and `html.formatter.enabled = true`, then ran the same stage-between-passes procedure with `npx --yes @biomejs/biome@2.5.11 format --write "${files[@]}"`. Biome changed `src/web/about.html` on its second HTML pass; Prettier produced no second-pass changes. The same audit ran `node --check` over every tracked frontend JS/MJS file and `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_frontend_node.py -q` after Prettier; both passed.

## Goals

- Make Python formatting deterministic with Ruff.
- Make static frontend JavaScript, MJS, and HTML formatting deterministic with Prettier.
- Give developers, editors, agents, pre-commit hooks, and CI the same checked configuration.
- Format only relevant staged files during commits.
- Establish a mechanical formatting baseline in a commit separate from tooling and documentation.
- Keep a clean checkout formatting-idempotent and runnable from a non-interactive shell.

## Non-goals

- Add or change Python lint policy.
- Add frontend linting; #45 owns Biome lint adoption.
- Change the supported Python runtime; #46 owns Python runtime policy and Python 3.13 evaluation.
- Format Jinja templates in `api/templates/`; Prettier is not Jinja-aware.
- Format CSS, JSON, SVG, YAML, Markdown, generated files, or vendored artifacts.
- Refactor or semantically change application code while creating the baseline.
- Add `package.json`, ESLint, Biome, Husky, Lefthook, or another hook manager.

## Tooling Decisions

### Python

Ruff 0.16.5 is the sole Python formatter. A root `ruff.toml` sets:

- `line-length = 88`
- `target-version = "py311"`

Python 3.11 is the minimum supported Barcart syntax version, not the preferred runtime. Keeping the formatter target at 3.11 avoids emitting syntax that violates `packages/barcart/pyproject.toml`, which already uses the same line length and target version. Ruff linting remains unchanged and out of scope.

### Frontend

Prettier 3.9.6 is the sole frontend formatter. The extensionless `.prettierrc` is used because the repository's blanket `*.json` ignore rule would silently exclude `.prettierrc.json`. It sets:

- `useTabs: false`
- `tabWidth: 4`
- `singleQuote: true`
- `printWidth: 100`

The scope is:

- `src/web/**/*.js`
- `src/web/**/*.mjs`
- `src/web/**/*.html`
- `tests/**/*.js`
- `tests/**/*.mjs`

`.prettierignore` excludes `src/web/js/config.js` and `api/templates/`. The pre-commit filename filter already excludes Jinja templates; the ignore file protects direct editor and CLI use too.

### Tool installation

pre-commit 4.6.2 is the only developer-installed orchestration dependency. `.pre-commit-config.yaml` defines local hooks with isolated environments:

- `ruff-format`: `language: python`, `entry: ruff format`, `additional_dependencies: [ruff==0.16.5]`, Python file types only.
- `prettier`: `language: node`, `entry: prettier --write`, `additional_dependencies: [prettier@3.9.6]`, limited to `^(src/web/.*\.(js|mjs|html)|tests/.*\.(js|mjs))$`.

This avoids global Ruff or Prettier installation, avoids a root Node package, and keeps exact tool pins in one executable configuration. `pre-commit run --all-files` bootstraps both isolated tool environments. Node 22.7 or newer is still a local prerequisite for the Node hook and for `node --check`; without a root `package.json`, Node's default module-syntax detection introduced in 22.7 is what lets `node --check` parse the frontend's ESM `.js` files. Node 22.22.2 is the documented and CI-tested version.

## Developer and Editor Workflow

`AGENTS.md` documents the Node 22.7+ prerequisite (22.22.2 tested) and these commands:

```bash
node --version
~/miniforge3/envs/cocktaildb/bin/python -m pip install pre-commit==4.6.2
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit install
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run ruff-format --all-files
~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run prettier --all-files
```

On commit, hooks rewrite only matching staged files. If a hook rewrites a file, the commit stops so the developer can review and stage the formatter output. Hooks never run semantic or unsafe fixes.

Ruff and Prettier editor extensions consume `ruff.toml` and `.prettierrc`, respectively. CI remains authoritative when an editor extension is absent or differs locally.

## CI

`.github/workflows/format.yml` runs on pull requests and pushes to `main` with `contents: read` permissions. It uses:

- `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd` (`v6.0.2`)
- `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` (`v7.0.0`) with Python 3.12.10
- `actions/setup-node@820762786026740c76f36085b0efc47a31fe5020` (`v7.0.0`) with Node 22.22.2

The workflow installs `pre-commit==4.6.2` and runs it through the selected interpreter so it never depends on a generated console script being on `PATH`:

```bash
python -m pre_commit run --all-files --show-diff-on-failure
```

The same hooks therefore implement local rewriting and CI checking. CI never commits formatter output; any rewrite makes the job fail and display the diff. `.github/dependabot.yml` gains a `github-actions` entry with `directory: /`, a weekly schedule, and the repository's existing four-day cooldown so action SHA update PRs remain reviewable and releases receive the required vetting period.

## Commit Structure

The pull request contains two commits:

1. `dev: add deterministic formatting checks (#35)`
   - formatter configuration
   - pre-commit configuration
   - SHA-pinned CI workflow and GitHub Actions Dependabot maintenance
   - exact developer/agent documentation
2. `style: establish formatting baseline (#35)`
   - Ruff-generated Python changes
   - Prettier-generated static frontend and frontend-test changes
   - no hand edits or semantic changes

The isolated baseline commit lets reviewers inspect configuration separately and lets future blame operations ignore the mechanical revision explicitly when needed. The PR must be merged with a merge commit, not squash-merged, so the baseline remains an independently addressable revision for `git blame --ignore-rev`.

## Validation

Before formatting, install `pre-commit==4.6.2` and the existing test dependencies (`~/miniforge3/envs/cocktaildb/bin/python -m pip install -r requirements-test.txt` and `~/miniforge3/envs/cocktaildb/bin/python -m pip install -e 'packages/barcart[dev]'`) so the hooks are available and both pytest configuration islands have `pytest-cov`, then record the complete baseline command exits and summaries. Invoke local hooks as `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit ...` so non-interactive shells do not depend on Conda activation or `PATH`. After both commits:

1. Run `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files --show-diff-on-failure`; it must pass.
2. Run it a second time and verify `git status --porcelain` is unchanged.
3. Verify every tracked `src/web/**/*.js`, `src/web/**/*.mjs`, `tests/**/*.js`, and `tests/**/*.mjs` file with `node --check`.
4. Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/test_frontend_node.py -q` and run `node tests/test_frontend_ingredient_display.js` directly because the current pytest wrapper does not register that contract script.
5. Run `~/miniforge3/envs/cocktaildb/bin/python -m pytest tests/ -v` and `~/miniforge3/envs/cocktaildb/bin/python -m pytest packages/barcart/tests/ -q`; compare complete exit codes and test/coverage summaries against the recorded baseline, not only failure counts. Any environment-dependent baseline result must not worsen or change after formatting.
6. Run `~/miniforge3/envs/cocktaildb/bin/python -m compileall -q api packages/barcart scripts tests`.
7. Run `git diff --check origin/main...HEAD`.
8. Temporarily make one small syntactically valid edit, run its matching hook, and verify no unrelated tracked file changes; restore the temporary edit afterward.

The pull request is complete only when formatter checks are idempotent, JavaScript syntax checks pass, focused frontend tests pass, Python compilation passes, and no new test failures appear relative to the recorded baseline.

## Risks and Mitigations

### Large baseline diff

The audit showed that frontend formatting alone changes most static JS/HTML files. Keeping the baseline in a mechanical second commit prevents configuration and semantic review from being buried in formatting churn.

### Formatting accidentally changes behavior

Ruff and Prettier are syntax-preserving formatters, but the design still runs JavaScript syntax checks, Python compilation, frontend contract tests, and both Python suites before and after the baseline. No manual cleanup is allowed in the baseline commit.

### Nested Ruff configuration

Barcart retains its existing `packages/barcart/pyproject.toml`. Its line length and target version match the root configuration, so the nearest-config behavior does not create competing format policy.

### Generated or templated files

`src/web/js/config.js` remains excluded as generated local configuration. `api/templates/` remains excluded because Prettier does not understand Jinja control syntax. These exclusions are explicit rather than silent fallbacks.

### Future linting or runtime work

Biome linting and Python runtime modernization are tracked independently by #45 and #46. Neither can expand #35's baseline or CI behavior.

## Rollback

The two-commit structure permits reverting tooling and the mechanical baseline independently. If the workflow is disruptive, revert the tooling commit and baseline commit together. No database, API, deployment, or runtime state is changed.
