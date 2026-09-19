# Vite and content-hashed frontend assets

**Status:** Draft — self-reviewed; independent refinement pending

## Goal and approved scope

Build the existing vanilla JavaScript, multi-page frontend with Vite. Changed application assets receive new URLs. Use exactly the same build artifact in every environment; deployment supplies public runtime configuration. Keep the current successful frontend release plus one previous successful release. Cleanup runs only after successful publication and verification. Tabs from older releases may need refreshing after their assets are pruned.

No TypeScript conversion, UI framework, SPA routing, new staging infrastructure, authentication redesign, API contract changes, or database changes. Cleanup is limited to superseded asset-loading/build/deployment code. Existing unrelated working-tree changes are not part of this work.

## Current architecture

- `src/web/` contains static HTML, CSS and native JavaScript modules, without a frontend package/build configuration.
- `src/web/js/api.js` and `auth.js` import the generated `config.js` ES module. Login, callback and logout pages also contain inline module scripts.
- `api/templates/base.html`, `recipe.html` and `ingredient.html` render HTML through `api/routes/pages.py`. They currently refer directly to source CSS and JavaScript URLs.
- `infrastructure/ansible/playbooks/deploy.yml` copies frontend sources and generates environment-specific `web/js/config.js`.
- `infrastructure/scripts/deploy-cutover.sh` locks deployment, backs up, builds the API image, stops writers, runs migrations, starts/checks the API, then publishes the frontend by moving directories. The new API can render pages before that final publication.
- Both Caddy configurations currently revalidate unversioned HTML/JS/CSS. The Ansible template and standalone configuration must remain aligned.
- Analytics loads D3 from a CDN. This migration leaves that dependency unchanged; content-hashing guarantees apply to application build assets, not that external resource.

## Build and runtime configuration

Add a root npm manifest and committed lockfile, a small Vite multi-page configuration, and `dev`, `build`, and `preview` commands. Select a supported, vetted Vite release compatible with the repository's tested Node 22.22.2 and document its actual Node requirement. Build output is ignored `dist/`, never tracked source changes.

All existing static HTML pages are build entrypoints, preserving their URLs. Vite processes their module scripts (including inline modules) and local stylesheet links. Explicit additional inputs cover server-rendered page JavaScript and CSS. Emit Vite's manifest; keep entry identifiers stable and verify them against real build output. Preserve necessary non-bundled files such as robots.txt, llms.txt, icons and the web manifest without copying the source JS tree into production.

Use a fixed `/js/config.js` runtime ES-module URL, excluded from bundling. Change configuration consumers to that absolute import and mark that exact URL external in the build. Vite development serves the locally generated file at that URL. Production deployment supplies the file separately; it is absent from the reusable build artifact. Do not bake environment configuration into Vite variables or bundled code. ES-module dependency evaluation ensures configuration is loaded before its consumers, without an async bootstrap framework.

Preserve the current configuration fields and default export. Generate values with JSON serialization rather than interpolating raw strings into JavaScript. Validate required fields and public URL values during deployment before cutover, and fail clearly on missing configuration. No credential, client secret, or database value may enter the public file. Adapt `scripts/generate_config.py`, `scripts/local-config.sh`, and the Ansible template consistently. API/auth tests that load modules outside a browser must explicitly supply runtime config rather than depending on the old relative import.

## Server-rendered asset resolution

Package the build's manifest in the API image from the same staged artifact; do not have the running API read a mutable manifest through the served web directory. Add one small asset resolver used by Jinja templates. It resolves stable entry keys, emits hashed module URLs and required stylesheet links, and follows manifest imports for dependent CSS without duplicate links. Preserve stylesheet order and module initialization order. Vite handles equivalent rewriting for static HTML.

Production startup validates the manifest, required entries and safe relative asset paths; missing or malformed data is an error, never a fallback to stale source URLs. Tests and local development explicitly select development mode. In that mode, the resolver uses source URLs served through Vite; no missing-manifest heuristic selects the mode. The Vite development server proxies API and server-rendered routes to local FastAPI, giving pages and `/js/config.js` one browser origin. Use Vite's normal development port rather than competing with FastAPI on port 8000. Update `scripts/serve.sh` and local setup documentation rather than retaining competing static-server instructions.

## Asset serving and cache policy

Serve `/assets/*` from a persistent shared asset directory separate from the release-specific HTML/config root. Publish assets there before starting the new API so its manifest references already resolve. Copy each asset atomically; if an existing pathname has different bytes, fail instead of overwriting an immutable URL.

Successful hashed asset responses receive `Cache-Control: public, max-age=31536000, immutable`. Missing assets must return a real 404 without long-lived immutable caching; no HTML fallback. HTML, server-rendered pages and `/js/config.js` revalidate with `Cache-Control: no-cache`. Unhashed public media retain a conservative short cache lifetime. Ensure the broad existing JS/CSS matchers do not overwrite hashed-asset headers, and do not change personalized API cache behavior.

## Deployment and artifact contract

Build on the deployment/controller machine, not EC2. A deployment can consume an explicitly supplied, already-built frontend artifact directory; the normal wrapper may build one when none is supplied. Ansible stages that artifact instead of `src/web/`. Both paths validate it before touching the live application. This supports promoting identical bytes to a second environment without rebuilding.

The artifact contains built HTML/public files, hashed assets and manifest, but no environment-specific runtime configuration. Record an inventory of all emitted `/assets/` files as part of the artifact, including transitive chunks and CSS-referenced files; retention must not rely only on top-level manifest entries. Validate inventory paths remain inside the asset directory. Include the matching manifest in the staged API build context and image. Inspect Docker ignore rules when choosing its destination.

Under the existing deployment lock:

1. Validate staged HTML, manifest, asset inventory and generated public config before stopping API writers. Keep existing backup, build and migration safety checks.
2. Publish new hashed assets into shared storage before API start. Do not remove any existing assets at this point. Staging failure leaves the serving release unchanged.
3. Perform the existing guarded API/migration cutover and health check, using the image with the matching manifest.
4. Publish the new release's HTML/config together, retaining the prior successful frontend. Use an atomic symlink replacement for normal releases, keeping release directories stable rather than moving their contents. The first migration from the existing real web directory requires an explicit guarded conversion with restoration on failure; do not describe that initial conversion as atomic.
5. Smoke-check representative static and server-rendered pages, runtime config, and referenced assets through Caddy. Only after successful checks record the new current/previous pair.
6. Prune older managed frontend release directories and shared assets outside the union of the two retained inventories. Keep current and previous manifests/inventories/configuration with their releases. A redeployment of the same artifact is still safe and may share all assets.

Track successful publication explicitly; do not infer it from timestamps or arbitrary directories. On any failure before verified publication, do not advance retention or prune. After an interrupted deployment, recovery must resolve publication state before another retention pass. If post-publication checks fail, report the exact serving state and require recovery; do not automatically roll back the database/API after possible writes. A cleanup failure reports the deployment as published but cleanup incomplete, preserves the current/previous record and permits an idempotent retry.

Cleanup is confined to frontend-owned release data and assets. Never recursively delete the existing whole release root: it also contains API, migration and package data. Database backups and Docker image retention remain governed by existing operations. Preserve assets from a failed candidate until a subsequent successful cleanup rather than risking deletion while its API might still serve references.

### First hashed deployment and rollback

The prior unversioned frontend has no manifest/inventory. Preserve it as the previous frontend and retain its legacy source asset URLs during this transition, except `/js/config.js`, which remains the active environment configuration. Treat the legacy copy as an explicit one-time retention record, not as an empty manifest. Remove legacy source assets when this release leaves the two-release window.

The previous frontend/config and matching API image are rollback inputs, not a promise that frontend rollback alone can reverse an API/database migration. Preserve existing post-write recovery constraints and document the coordinated recovery procedure. New and previous hashed asset sets remain available regardless of the active frontend pointer. Compatibility of old frontend code with a changed API remains a separate application contract.

## Targeted cleanup

Replace source-directory deployment and obsolete static-server guidance. Remove redundant standalone module script tags only when their imports already guarantee equivalent initialization, with regression coverage. Update existing source-URL assertions to test built behavior rather than simply deleting them. Do not rewrite navigation, API clients, charts or unrelated page logic.

## Verification and acceptance

- Build all static pages and explicit template entries; verify every emitted local reference resolves, with runtime config as the deliberate external exception. No environment-specific config values or source configuration module appear in bundles.
- Build twice unchanged and compare asset names; change a fixture's JS/CSS content and verify relevant URLs change. Reuse the same built bytes with two runtime configurations and verify API/auth configuration changes without asset changes.
- Exercise static pages, recipe/ingredient pages, and login/callback/logout through production-like serving; verify page scripts initialize once, styles load and nested routes use correct absolute URLs.
- Test manifest resolution, dependent CSS, invalid/missing manifests and entries, explicit development mode, and safe path validation.
- Extend Caddy cache tests to check hashed success, missing assets, HTML, config, media and unchanged API policies. Include a runnable real-server smoke check rather than relying only on configuration text matching.
- Extend the existing `tests/test_group_inventory_deploy.py` operation harness: assets exist before API start; failures do not prune; only successful publication advances retention; three releases retain exactly the newest two frontend sets; shared files survive; failed candidates, interrupted publication, cleanup retry and legacy first deployment are handled; unrelated release data is untouched.
- Run existing frontend JavaScript checks and affected pytest suites, including page contracts and auth startup tests. Update formatter coverage to include added build files and enforce the build in CI using SHA-pinned actions if actions are added.
- Document build/deploy/artifact reuse, local Vite + FastAPI setup, config generation, first rollout, recovery and cleanup. Explicitly state that tabs older than the retained release window may require refresh.

## Remaining gate

Independent codebase-grounded refinement and final user approval are required before implementation planning. TypeScript remains a separate future decision.
