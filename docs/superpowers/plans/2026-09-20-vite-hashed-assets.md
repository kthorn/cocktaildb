# Vite Hashed Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the existing JavaScript frontend as an environment-independent Vite build with hashed assets and safe current-plus-previous frontend retention.

**Architecture:** Vite builds static HTML and explicit server-rendered entries. The API image contains the matching manifest, while public runtime config remains external. Existing cutover orchestration publishes assets before API startup and retains two verified frontend releases under the existing locks.

**Tech Stack:** Vanilla JavaScript, Vite 8.3.0, Node 22.22.2, Python/FastAPI/Jinja, Caddy, Ansible, Bash, pytest and Node's built-in test/assert modules.

**Spec:** `docs/superpowers/specs/2026-09-19-vite-hashed-assets-design.md`

## Approval and baseline

User approved the reconciled spec and proceeding on 2026-09-20. Do not describe failed independent review runs as passed: their history remains in `docs/plans/vite-hashed-assets-review-log.md`. Execution reviews still require working reviewer tooling; do not silently substitute an external runner.

Workspace: `/home/kurtt/cocktaildb/.worktrees/vite-assets`, branch `feat/vite-assets`. Base main: `0fd4cb0`; reconciled docs: `ef3b706`. The shared checkout and its unattributed changes are out of bounds. Deployment/config/cache/smoke baseline: 40 tests passed with three dependency deprecation warnings. Run all commands below from this worktree.

Registry checks on 2026-09-20: Vite 8.3.0 was published 2026-09-10 and declares Node `^20.19.0 || >=22.12.0`. Pin 8.3.0 and its lockfile; use repository Node 22.22.2 and a project engine floor of 22.12.0. Validate externalization and manifest details against this actual version instead of copying legacy Rollup assumptions.

## Global Constraints

- No TypeScript conversion, UI framework, SPA routing, new staging infrastructure, authentication redesign, API contract changes, or database changes.
- Use exactly the same build artifact in every environment; deployment supplies public runtime configuration.
- Keep the current successful frontend release plus one previous successful release.
- Cleanup runs only after successful publication and verification. Existing Docker cleanup is separate and remains intact.
- First deployment may break old unversioned tabs; no legacy URL bridge.
- Vite listens on localhost:8000 with strict-port behavior; generated config points to the remote dev API.
- Hashed assets: `Cache-Control: public, max-age=31536000, immutable`; HTML/config revalidate with `no-cache`.
- Preserve the outer Ansible lifecycle lock, nested cutover lock, migration parity checks and post-write recovery rules.
- One writer per worktree. Do not touch the main checkout or deploy production during implementation.
- Pin new GitHub Actions by full commit SHA with a version comment. Prettier owns YAML; shfmt owns shell.

## Review Focus

1. Fresh clone without config.js: production build succeeds and never embeds environment configuration — Task 1.
2. Missing hashed file or overlapping media matcher: true 404 without immutable caching — Task 4.
3. Changed working directory or router-only ASGI tests: manifest lookup remains deterministic, with explicit asset mode — Task 3.
4. Crash after API startup but before successful frontend record: no cleanup or blind rollback; recovery must reconcile identities — Task 5.
5. Reused assets, unsafe inventory paths and legacy first rollout: retain the union of two successful sets without deleting unrelated files — Tasks 1 and 5.

## File ownership and interfaces

- `vite.config.mjs`: multi-page input/externalization/public files, manifest generation.
- `scripts/frontend-artifact.mjs`: inventory validation and disposable preview staging; no deployment state machine.
- `scripts/generate_config.py`: shared public config normalization/serialization; existing CLI retained.
- `api/core/frontend_assets.py`: API-side manifest validation and template URL resolution.
- `infrastructure/scripts/frontend-release.py`: small stdlib-only filesystem helper for inventories, atomic publication and retention records. JSON/path safety belongs here rather than shell interpolation; shell retains orchestration and existing Docker/database logic.
- Existing cutover/playbooks/Caddy config: wire these capabilities into the actual release flow.

Artifact layout (ignored `dist/`):

```text
dist/
  web/                  # built HTML, public files, assets; NO runtime config
    assets/
    img/
    robots.txt
    llms.txt
    site.webmanifest
  manifest.json         # Vite manifest, not served
  asset-inventory.json  # sorted relative names under web/assets, not served
```

Inventory wire format:

```json
{"version":1,"files":["common-ABC123.js","styles-DEF456.css"]}
```

Inventory paths are POSIX relative paths beneath assets/, never absolute, empty, dot/dot-dot, backslash-containing or symlink paths. Enumerate every emitted file, not just manifest entries. Require manifest asset references to be inventoried and present. Never include config.js in inventory or build output.

## Task 1: Build a complete, config-independent multi-page artifact

**Files:** Create `package.json`, `package-lock.json`, `vite.config.mjs`, `scripts/frontend-artifact.mjs`, `tests/test_frontend_build.mjs`. Modify `.gitignore`, `.pre-commit-config.yaml`; move public files into `src/web/public/`. Existing application modules stay JavaScript.

**Interfaces:** `npm run build` produces the layout above. `validateArtifact(directory)` in scripts/frontend-artifact.mjs throws on invalid content and returns the parsed inventory. Its CLI `node scripts/frontend-artifact.mjs validate DIRECTORY` exits nonzero on failure. `npm run dev` runs Vite at port 8000; `npm run preview` operates on a disposable artifact copy supplied with generated config.

- [ ] Write the build integration check using a temporary checkout fixture, so existing local config is never deleted or overwritten:

```javascript
import assert from 'node:assert/strict';
import { mkdtemp, cp, readFile, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
// The fixture copies tracked build inputs, not the generated config or .git.
// Link installed node_modules from the worktree into the fixture.
const inventory = JSON.parse(await readFile('dist/asset-inventory.json', 'utf8'));
assert.equal(inventory.version, 1);
assert.deepEqual(inventory.files, [...inventory.files].sort());
assert(inventory.files.some((name) => name.endsWith('.js')));
assert(inventory.files.some((name) => name.endsWith('.css')));
await assert.rejects(access('dist/web/js/config.js'));
```

Implement the fixture setup in this test with mkdtemp/cp/symlink and cleanup in finally. Build twice there with config absent, compare inventories and file bytes; modify a copied CSS file and a copied JS module separately and require changed asset names. Parse every emitted HTML local script/stylesheet URL and check files exist. Assert external config imports are exactly `/js/config.js` and no fixture sentinel config values occur in bundles. Validate robots/llms/webmanifest and each icon URL explicitly.

- [ ] Run `node --test tests/test_frontend_build.mjs`; confirm failure is missing build capability, not a missing Node executable.
- [ ] Add the pinned npm manifest and lockfile. Keep root package typeless:

```json
{
  "private": true,
  "engines": {"node": ">=22.12.0"},
  "scripts": {
    "dev": "vite --host localhost --port 8000 --strictPort",
    "build": "vite build && node scripts/frontend-artifact.mjs inventory dist",
    "preview": "node scripts/frontend-artifact.mjs preview dist",
    "test:build": "node --test tests/test_frontend_build.mjs"
  },
  "devDependencies": {"vite": "8.3.0"}
}
```

- [ ] Configure root src/web, appType mpa, build output dist/web and manifest output ../manifest.json. Discover all root HTML entries, plus normalize.css, styles.css, recipe-card.css, js/common.js and js/recipe.js. Match the config external before filesystem lookup using both importer and specifier; map its emitted path to `/js/config.js` through the pinned bundler's output-path configuration. Check the built text, not just configuration structure. Do not externalize arbitrary basename matches.
- [ ] Move stable files with `git mv` into public/: robots.txt, llms.txt, site.webmanifest, img/. Keep their content and URLs unchanged. Update ignored txt exceptions; unignore root npm manifest/lockfile, ignore node_modules/dist. Extend formatter coverage for root config, package.json and scripts/frontend-artifact.mjs without changing existing YAML/shfmt scope.
- [ ] Implement inventory generation by recursively enumerating regular files under dist/web/assets and sorting their relative names. Validation rejects symlinks, invalid path components, absent files, invalid manifest references and metadata inside web/. Preview validates the artifact, copies web/ to mkdtemp, copies explicitly selected local config to js/config.js, starts Vite preview against that temporary outDir, and deletes it on normal exit. Missing preview config fails clearly; never mutate dist.
- [ ] Run `npm ci`, `npm run build`, `npm run test:build`, and existing native Node suites. Ensure CJS tests and imported frontend ESM both work with the typeless root. Commit only Task 1 files after red/green evidence.

## Task 2: Preserve public configuration and local development

**Files:** Modify `scripts/generate_config.py`, `scripts/local-config.sh`, `scripts/serve.sh`, `infrastructure/ansible/files/config.js.j2`, `vite.config.mjs`; create `tests/test_frontend_config.py` and extend build checks.

**Interfaces:** Add `render_public_config(config: dict) -> str` in the existing Python generator; accepts exact public camelCase fields and returns `export default <JSON>;\n`. Existing CloudFormation CLI maps its snake_case inputs to this function. Local generation uses the same function. Ansible serializes its equivalent explicit public dictionary with its JSON filter and asserts required values before staging. No secret-bearing environment dump is allowed.

- [ ] Write failing serialization tests:

```python
import json
from scripts.generate_config import render_public_config

def test_public_config_escapes_javascript_values():
    config = dict(apiUrl='https://dev.example/api', userPoolId='pool',
                  clientId='client', cognitoDomain='https://auth.example',
                  appUrl='http://localhost:8000', appName="Kurt's \\ bar\n")
    source = render_public_config(config)
    assert source.startswith('export default ')
    assert json.loads(source[len('export default '):].rstrip(';\n')) == config
```

Add cases for missing required field, blank identifiers, unsupported URL scheme, localhost HTTP and unknown secret-like fields. Exact public allowlist excludes database/AWS credentials. URLs require http/https and a nonempty hostname; do not introduce auth or redirect behavior from appUrl.

- [ ] Run `python -m pytest tests/test_frontend_config.py --no-cov -q` using the cocktaildb environment; observe failure before implementation.
- [ ] Replace raw JavaScript interpolation with json.dumps and Ansible to_json respectively. Preserve CLI flags/field names. Remove character-rejection workarounds only once escaping tests replace their purpose. Keep secrets in the existing server env template.
- [ ] Make serve.sh invoke npm run dev, retaining its local-config prerequisite and explicit warning for remote config. Port is strictly 8000. Keep remote dev apiUrl and localhost:8000 appUrl. Optional SSR proxy target is explicitly configured for local backend port 8001; no silent local-backend requirement.
- [ ] Verify the same built artifact's asset checksums remain unchanged when two generated configs are placed in two disposable served copies; each config exports its distinct API/auth values. Verify no generated config is staged in Git.
- [ ] Run config/build/auth tests, then commit Task 2 files.

## Task 3: Resolve server-rendered assets from the packaged manifest

**Files:** Create `api/core/frontend_assets.py`, `tests/test_frontend_assets.py`. Modify `api/core/config.py`, `api/main.py`, `api/routes/pages.py`, `api/templates/base.html`, `api/templates/recipe.html`, page tests and their explicit test setup.

**Interfaces:** `FrontendAssets(mode: str, manifest_path: Path | None = None)` exposes `validate() -> None`, `script(entry: str) -> str`, `styles(entries: list[str]) -> list[str]`. Default manifest path derives from __file__ to api/frontend-manifest.json. Mode is `built` or `development`, selected by dedicated FRONTEND_ASSET_MODE setting; default built. Jinja global frontend_assets uses the instance. Production lifespan calls validate; request-time lookup also fails clearly if invalid, so router-only clients cannot silently bypass validation.

- [ ] Add focused failing tests with minimal manifest fixtures:

```python
import json
from api.core.frontend_assets import FrontendAssets

def test_styles_follow_imports_and_dedupe(tmp_path):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({
        'js/recipe.js': {'file': 'assets/recipe-A.js', 'imports': ['_shared'],
                         'css': ['assets/recipe-A.css']},
        '_shared': {'file': 'assets/shared-B.js', 'css': ['assets/base-B.css']},
    }))
    assets = FrontendAssets('built', manifest)
    assert assets.script('js/recipe.js') == '/assets/recipe-A.js'
    assert assets.styles(['js/recipe.js']) == [
        '/assets/base-B.css', '/assets/recipe-A.css']
```

Also test CSS file entries versus JS entries with css arrays, missing keys, malformed JSON, import cycles, path escapes, duplicate styles, explicit source mode and cwd changes. Fixture-based tests may validate individual entries; startup tests supply the complete required entry set.

- [ ] Run resolver tests and observe import failure; then implement one small resolver using json, pathlib and visited sets. Validate all required production entries and every referenced path. Never turn malformed production data into development mode.
- [ ] Register Jinja global and emit template links through it:

```jinja2
{% for href in frontend_assets.styles(['normalize.css', 'styles.css']) %}
<link rel="stylesheet" href="{{ href }}">
{% endfor %}
```

Recipe adds recipe-card.css and executable module scripts for js/common.js and js/recipe.js, in that order. Ingredient/404 add no scripts. Do not change recipe caller identity, ratings/auth logic or page API semantics. Ensure dependencies' CSS is included without emitting JS as stylesheets.
- [ ] Set source mode explicitly in existing source-URL page fixtures. Add built-mode rendering against the real Task 1 manifest and tests after monkeypatch.chdir(tmp_path). Verify nested routes emit `/assets/...`, never relative asset paths.
- [ ] Run `python -m pytest tests/test_frontend_assets.py tests/test_page_route_contracts.py tests/test_pages.py --no-cov -q`, then built-manifest page checks. Commit Task 3 files.

## Task 4: Stage reusable artifacts and serve assets correctly

**Files:** Modify `scripts/deploy-ec2.sh`, both deployment playbooks, `infrastructure/caddy/Caddyfile`, `tests/test_caddy_cache_headers.py`, `tests/test_deploy_config_sources.py`, `tests/test_group_inventory_deploy.py`; create `tests/test_caddy_frontend_runtime.py`.

**Interfaces:** Wrapper accepts `--frontend-artifact DIRECTORY`; absent flag builds once on controller and passes absolute dist path as Ansible frontend_artifact_dir. Ansible validates before mutating live state, stages web/ into release_root/web, manifest/inventory outside web, and matching manifest into release_root/api/frontend-manifest.json after API sync. Existing Docker COPY api/ includes it without a new image build system.

- [ ] Extend playbook/wrapper tests to reject invalid artifacts before cutover, consume an existing artifact without npm rebuilding it, and stage config only after creating js/. Assert API manifest copy follows delete-enabled API sync. Preserve lifecycle lock final-release assertion.
- [ ] Write the real-Caddy check using a temporary Caddy config and port, clean subprocess teardown and curl/urllib requests. Required observations:

```python
assert get('/assets/test-A.js').status == 200
assert get('/assets/test-A.js').headers['Cache-Control'] == 'public, max-age=31536000, immutable'
assert get('/assets/icon-A.svg').headers['Cache-Control'] == 'public, max-age=31536000, immutable'
assert get('/assets/missing.js').status == 404
assert 'immutable' not in get('/assets/missing.js').headers.get('Cache-Control', '')
assert get('/js/config.js').headers['Cache-Control'] == 'no-cache'
```

Implement get with urllib catching HTTPError as an HTTP response. Caddy availability is required for the release gate; do not count skipped runtime checks as passing validation. Exercise both domain-style and HTTP-style route blocks with a local test upstream for SSR.
- [ ] Run new checks red, then stage the validated artifact on the controller/remote boundary. Exclude assets and metadata from the final served release tree after transfer to their managed locations, retaining the complete asset inventory in the release metadata. Runtime config stays out of reusable dist.
- [ ] Add handle_path /assets/* with root /opt/cocktaildb/frontend-assets, file_server and deferred header response matching `match status 2xx`. Exclude assets from existing mutable and media matchers; keep actual 404s and existing API header semantics. Create shared directory before either Caddy deployment restarts; preserve valid web-root symlink and fail on dangling link.
- [ ] Validate both deployment paths and real Caddy behavior. Inspect the built API image for /app/frontend-manifest.json during final integration. Commit Task 4 files; do not deploy yet because Task 5 wires asset publication.

## Task 5: Publish and prune two verified frontend generations

**Files:** Create `infrastructure/scripts/frontend-release.py`, `tests/test_frontend_release.py`; modify `infrastructure/scripts/deploy-cutover.sh`, `infrastructure/ansible/playbooks/deploy.yml`, deployment source/operation tests, `infrastructure/scripts/smoke-test.sh` and its tests.

**Interfaces:** Stdlib helper is invoked only under existing cutover lock. CLI subcommands: `validate RELEASE_ROOT`, `assets RELEASE_ROOT`, `begin RELEASE_ROOT API_IMAGE`, `publish RELEASE_ROOT`, `commit RELEASE_ROOT API_IMAGE`, `prune`, `recover RELEASE_ROOT API_IMAGE`. Paths derive from APP_HOME/SERVED_WEB env already used by the harness. Recovery validates active Docker image and serving symlink through the shell before invoking the filesystem helper; helper rejects identities inconsistent with its marker/state.

State lives at APP_HOME/frontend-state.json, pending marker at APP_HOME/frontend-pending.json, shared assets at APP_HOME/frontend-assets. Write JSON using tempfile in the destination directory plus os.replace; flush/fsync before publication. No custom persistence framework.

```json
{
  "version": 1,
  "current": {"id":"B","web":"releases/B/web","inventory":"releases/B/frontend-assets.json","image":"cocktaildb-api:release-B","legacy":false},
  "previous": {"id":"A","web":"releases/A/web","inventory":"releases/A/frontend-assets.json","image":"cocktaildb-api:release-A","legacy":false},
  "retired": []
}
```

Only explicit owned web/metadata paths enter retired. Before removing old generations, retain their identities in state; remove each retired record only after its deletion succeeds. Do not enumerate arbitrary releases/ entries as deletion candidates. Legacy previous stores its preserved previous-web path and null inventory with legacy=true; only that explicit case permits no inventory.

- [ ] Write filesystem tests importing the helper via importlib.util. Expose small module functions `publish_assets(release: Path, app_home: Path)`, `publish_web(release: Path, served: Path)`, `prune_assets(asset_root: Path, keep: set[str])` for direct checks. Test keep-set behavior:

```python
def test_shared_asset_survives_two_generation_prune(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    for name in ['old.js', 'shared.js', 'current.js']:
        (assets / name).write_text(name)
    prune_assets(assets, {'shared.js', 'current.js'})
    assert sorted(p.name for p in assets.iterdir()) == ['current.js', 'shared.js']
```

Add path escape, symlink, immutable-name byte collision, failed copy, pending marker, three-generation union, missing/corrupt retained inventory, legacy-first-release and cleanup-retry tests. Corrupt state aborts pruning without deleting anything.
- [ ] Run tests red. Implement asset copying with temporary files and atomic rename; existing identical files are reused, conflicting bytes fail. Implement publish via temporary symlink plus os.replace. First real-directory conversion preserves previous web and restores it if replacement fails. No legacy request fallback.
- [ ] Extend CUTOVER_OPS_DIR operation hooks and exact event tests. Keep Docker cleanup/backup/build/migrations unchanged. Add frontend validation before live mutations, asset publication before start, pending marker before stop/start, frontend publish after health, smoke after publish, successful-state commit after smoke, frontend prune after state commit, then existing post-deploy Docker cleanup.
- [ ] Make unresolved marker block deployment and prune. Recovery must inspect `docker compose ... ps`/container image and served symlink, match the pending candidate, rerun health and frontend smoke, then commit the reconciled state; otherwise exit with identities and manual recovery instructions. Never auto-restart old API after possible writes. If pending record is already reflected in committed current state, verify identities and clear marker idempotently before a cleanup retry.
- [ ] Test each injected failure stage: old files survive prepublication failures; post-start failure preserves marker/assets and reports serving state; successful commit followed by cleanup error keeps healthy API running; retry prunes only verified obsolete frontend data. Preserve migration parity marker, backups, tagged Docker images and non-frontend release data.
- [ ] Update smoke-test.sh to extract referenced built local assets rather than use obsolete source URLs; test static index, config, a real recipe page and ingredient page, metadata exclusion and asset availability. Use fixture IDs in automated tests; deployment obtains existing IDs from API and fails clearly if its selected verification endpoints fail. Empty database smoke uses route 404 HTML plus static assets without inventing recipe data.
- [ ] Add frontend-release.py to the explicit host-script copy loop. Verify source-list tests and shfmt output. Run all deployment/config/cache/smoke/retention suites. Commit Task 5 files.

## Task 6: End-to-end checks, documentation and CI

**Files:** Extend build/asset/runtime suites; modify `.github/workflows/format.yml` or add `.github/workflows/frontend.yml`, README.md, scripts/README.md, CLAUDE.md, AGENTS.md, docs/operations-runbook.md and the historical formatting spec's superseded rationale.

**Interfaces:** `npm ci && npm run build && npm run test:build` is the config-free artifact gate. Python frontend/deploy tests and real-Caddy checks are the release gates. Production deployment remains an explicit human action after merge.

- [ ] Add an integration test that serves two configured copies of the same build and checks application requests use their respective API/auth settings. Exercise index/search/analytics and inline-module login/callback/logout behavior, recipe and ingredient SSR, nested URLs, common initialization once and unchanged D3 loading. Use existing browser tooling if present; otherwise document browser smoke steps explicitly and do not claim they ran automatically.
- [ ] Add CI build/test commands with Node 22.22.2, npm ci and committed lockfile. Reuse existing pinned checkout/setup-node SHAs if compatible; fetch exact reviewed SHA for any new action. CI build runs without generated config. Keep root package typeless and assert CJS and ESM scripts still execute.
- [ ] Run focused tests:

```bash
npm ci
npm run build
npm run test:build
/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest \
  tests/test_frontend_config.py tests/test_frontend_assets.py \
  tests/test_frontend_release.py tests/test_group_inventory_deploy.py \
  tests/test_deploy_config_sources.py tests/test_caddy_cache_headers.py \
  tests/test_caddy_frontend_runtime.py tests/test_smoke_test_script.py \
  tests/test_page_route_contracts.py tests/test_pages.py tests/test_frontend_node.py \
  --no-cov -q
/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files
```

Also run the repository API suite with its normal coverage setting in the documented test environment; report database/tool prerequisites distinctly from failures introduced by this branch. Run active LSP diagnostics on changed Python/JS where supported, with missing coverage explicitly reported.
- [ ] Document config generation, frontend-only localhost workflow, optional SSR proxy, disposable preview, artifact promotion flag, first deployment refresh requirement, two-generation retention, pending-state recovery and cleanup retry. Document the one-time web-directory-to-symlink transition; do not promise atomicity on that first conversion.
- [ ] Update Node formatting rationale to reflect typeless package syntax detection, and do not rewrite historical design intent without marking it superseded. Remove stale nonexistent local-development links and old live-server/Python-static instructions.
- [ ] Perform a fresh whole-branch review on the final branch. Fix substantive findings, rerun affected tests and retain evidence. No runner fallback without owner approval. Commit final docs/tests, present diff/tests/residual risks and ask before merge or production rollout.

## Self-review and execution handoff

Coverage: Task 1 owns artifact/public files/config independence; Task 2 owns safe public configuration/local workflow; Task 3 owns Jinja/manifest; Task 4 owns staging/cache rules; Task 5 owns atomic publication/recovery/two-generation retention; Task 6 owns end-to-end, CI and runbooks. All five Review Focus risks have runnable test ownership above. No task changes database schema, auth policy, frontend framework or TypeScript.

Recommended execution: **subagent-driven, sequential writers with task review**, because build output, API manifests and destructive retention must agree and each task has independently testable boundaries. Use the approved routine/integration model routing; resolve reviewer extension loading before relying on those gates. Implementation-plan review is not automatically required; user reviews this plan before execution.
