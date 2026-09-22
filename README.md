# CocktailDB

CocktailDB is a cocktail database application hosted on EC2 with FastAPI,
PostgreSQL, Caddy, and a vanilla JavaScript frontend.

## Prerequisites

- AWS CLI and deployment credentials for infrastructure work
- Python 3.12.10 for the documented test environment
- Node 22.22.2 and npm
- Docker for the API and real-Caddy release gates

## Frontend build and artifact gate

The root package is intentionally typeless. Existing CommonJS `.js` scripts keep
working while Node 22.22.2's syntax detection handles frontend ESM; do not add
`"type": "module"` to the root package.

Build the reusable, configuration-free artifact with the committed lockfile:

```bash
npm ci
npm run build
npm run test:build
```

The build writes ignored `dist/` output containing `dist/web/`, hashed assets,
`manifest.json`, and `asset-inventory.json`. It never includes `src/web/js/config.js`.
The same `dist/` directory can be promoted to more than one environment; each
deployment supplies its own public runtime configuration.

A disposable preview copies an explicitly selected generated config into a
temporary directory and never changes `dist/`:

```bash
npm run preview -- dist /path/to/config.js
# or set FRONTEND_PREVIEW_CONFIG=/path/to/config.js
```

## Frontend-only local development

Generate a config pointing at the remote development API, then run Vite on its
strict localhost port:

```bash
./scripts/local-config.sh
npm ci                         # first setup, or after package-lock.json changes
./scripts/serve.sh             # http://localhost:8000
```

The frontend-only workflow does not require a local FastAPI process or local
database. For optional server-rendered development, run FastAPI separately on
port 8001 with `FRONTEND_ASSET_MODE=development`; Vite proxies `/recipe/*`,
`/ingredient/*`, and `/sitemap.xml` to that process. Browse those pages through
`http://localhost:8000`, not directly through port 8001. The runtime `appUrl`
remains `http://localhost:8000`, while `apiUrl` remains the configured remote
API URL.

No browser automation is installed in this repository. Manual smoke steps are:

1. Open `/`, `/search.html`, and `/analytics.html`; confirm styles and the
   analytics D3 CDN script load once.
2. Exercise a search and an analytics view; inspect the network panel and verify
   requests use the configured API URL.
3. Open `/recipe/<known-id>` and `/ingredient/<known-id>` through Vite or Caddy,
   including a nested URL, and verify hashed scripts/styles return 200.
4. Open `/login.html`, `/callback.html`, and `/logout.html`; verify the Cognito
   client/domain and callback/logout origin come from `config.js`.

The automated build/runtime checks exercise the same configuration-free artifact
with two runtime configurations, but do not claim to execute a browser.

## Deployment and artifact promotion

Production deployment is an explicit human action after review and merge. The
wrapper builds an artifact when none is supplied, or validates and promotes an
existing artifact without rebuilding:

```bash
./scripts/deploy-ec2.sh dev
./scripts/deploy-ec2.sh prod --frontend-artifact dist
```

The deployment gates validate the artifact and generated public config, publish
hashed assets before the API starts, run the guarded API/migration cutover,
atomically switch the normal release symlink, smoke-check Caddy-served pages,
commit the successful frontend record, and then prune only frontend-owned data.
Docker cleanup remains a separate existing operation.

The first hashed deployment preserves the old real web directory as the
explicit legacy previous release. That one-time web-directory-to-symlink
conversion is guarded and restorable but is **not atomic**; later releases use
temporary symlinks and atomic replacement. Existing unversioned tabs may need a
refresh after the first cutover. The release state retains the current and one
previous successful frontend, and keeps the union of their asset inventories.
Tabs older than that retained window may require a refresh after cleanup.

An unresolved `frontend-pending.json` marker blocks another deployment and
cleanup. Inspect the active API image and served symlink, then use the normal
recovery command only after reconciling those identities:

```bash
APP_HOME=/opt/cocktaildb \
  /opt/cocktaildb/scripts/deploy-cutover.sh recover \
  /opt/cocktaildb/releases/<release-id> \
  cocktaildb-api:release-<release-id>
```

Recovery reruns health and frontend smoke checks before committing the state.
It never deletes a marker to bypass reconciliation and never automatically
restarts an old API after possible writes. If publication succeeded but cleanup
failed, the healthy release remains current; verify identities and retry the
frontend cleanup rather than rolling back the API or database.

See [`scripts/README.md`](scripts/README.md) and
[`docs/operations-runbook.md`](docs/operations-runbook.md) for release phases,
config generation, recovery, retention, and operational commands.

## Tests and formatting

Run the focused release gate with the documented interpreter:

```bash
/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest \
  tests/test_frontend_config.py tests/test_frontend_assets.py \
  tests/test_frontend_release.py tests/test_group_inventory_deploy.py \
  tests/test_deploy_config_sources.py tests/test_caddy_cache_headers.py \
  tests/test_caddy_frontend_runtime.py tests/test_smoke_test_script.py \
  tests/test_page_route_contracts.py tests/test_pages.py tests/test_frontend_node.py \
  --no-cov -q
/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files
```

The repository API suite additionally needs its documented database fixture and
normal coverage configuration. A known rating aggregation failure remains
tracked in [`docs/plans/vite-validation-followups.md`](docs/plans/vite-validation-followups.md)
and is reported separately from frontend release-gate results.

## License

This project is licensed under the MIT License - see the LICENSE file for
details.
