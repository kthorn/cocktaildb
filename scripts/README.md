# Deployment and frontend scripts

The scripts directory contains the controller-side frontend workflow and the
EC2 deployment entry point.

## Files

- `deploy-ec2.sh` - validates or builds a frontend artifact, then invokes the
  Ansible deployment
- `frontend-artifact.mjs` - inventories, validates, and previews a disposable
  build artifact
- `generate_config.py` - validates and generates public `web/js/config.js`
- `local-config.sh` - generates the localhost:8000 development config
- `serve.sh` - starts the Vite development server on localhost:8000

## Configuration-free artifact

Use the committed lockfile and Node 22.22.2:

```bash
npm ci
npm run build
npm run test:build
```

The reusable artifact is `dist/` (ignored by Git):

```text
dist/
  web/                  # HTML, public files, and hashed assets
  manifest.json         # API image/template manifest; not served
  asset-inventory.json  # every file beneath web/assets; not served
```

Runtime configuration is deliberately absent. `npm run test:build` performs
source/config externalization and HTTP artifact-fetch checks only; it does not
execute browser behavior, built API/auth modules, or SSR. Validate an existing
artifact without rebuilding, or run a disposable preview with a selected config:

```bash
node scripts/frontend-artifact.mjs validate dist
npm run preview -- dist /path/to/config.js
# FRONTEND_PREVIEW_CONFIG=/path/to/config.js npm run preview -- dist
```

## Frontend-only local workflow

```bash
./scripts/local-config.sh
./scripts/serve.sh
```

Vite owns port 8000 with strict-port behavior and the generated config points
at the remote development API. A local FastAPI process and database are not
required. For optional SSR integration, start FastAPI on port 8001 with
`FRONTEND_ASSET_MODE=development`; Vite proxies recipe, ingredient, and sitemap
routes to it. Always browse through Vite on port 8000 so root-absolute source
assets use the correct origin.

## Deployment wrapper

Deployment remains an explicit human action after review and merge:

```bash
./scripts/deploy-ec2.sh dev
./scripts/deploy-ec2.sh prod --frontend-artifact dist
```

When `--frontend-artifact` is omitted, the wrapper runs `npm ci && npm run build`
on the controller. When supplied, it validates that directory and promotes
those exact bytes; it does not rebuild them. The wrapper then passes
an absolute artifact path to Ansible.

## Release phases

The host helper `infrastructure/scripts/deploy-cutover.sh` retains the outer
Ansible lifecycle lock and its nested cutover lock. Its frontend phases are:

1. Validate HTML, manifests, inventory, runtime config, and unresolved-state
   preconditions before live mutations.
2. Run the existing Docker cleanup, backup, image build, and migration safety
   checks.
3. Write the version-2 `prepublication` marker (including immutable
   candidate/prior API image IDs and the prior frontend identity), publish
   hashed assets into shared storage, then stop writers and verify they are
   stopped. Asset publication is retryable in either staged (`web/assets`)
   or prepared (`frontend-assets.json` plus shared bytes) form.
4. Durably mark the marker `cutover` before any migration, then start the
   matching API image and wait for health readiness.
5. Publish the release web/config symlink, run static and SSR smoke checks
   through Caddy, and commit the successful current/previous record.
6. Verify the active API image and served symlink still match the committed
   release, then prune only frontend-owned retired releases and assets outside
   the two retained inventories.
7. Run the existing Docker cleanup separately.

Hashed assets are immutable: existing identical files are reused and a byte
collision fails. A failed candidate remains available for recovery; no cleanup
runs before successful publication and verification. The first conversion from
a real `web` directory to a symlink is guarded and restorable, but is not
atomic. Later releases use a temporary symlink followed by atomic replacement.

## Recovery, abort, and cleanup retry

An unresolved `frontend-pending.json` marker is a hard gate. Version 2 is
independent of successful `frontend-state.json` version 1 and records
`phase`, immutable `candidate_image_id`/`prior_api_image_id`, and the exact
prior frontend. Version-1 pending markers are diagnosed and require manual
identity/database reconciliation; never infer their phase or clear them.

Before writers stop, a verified abort can clear only the marker. It requires
the exact candidate tag/ID, the prior API image ID, unchanged successful state
and served frontend (or the original first-rollout real-directory device/inode):

```bash
APP_HOME=/opt/cocktaildb \
  /opt/cocktaildb/scripts/deploy-cutover.sh abort-prepublication \
  /opt/cocktaildb/releases/<release-id> \
  cocktaildb-api:release-<release-id>
```

Abort never deletes shared or staged/prepared assets and never prunes. If
writers stopped before the durable phase transition, abort is forbidden. The
approved guarded forward-only route is:

```bash
APP_HOME=/opt/cocktaildb \
  /opt/cocktaildb/scripts/deploy-cutover.sh resume-stopped \
  /opt/cocktaildb/releases/<release-id> \
  cocktaildb-api:release-<release-id>
```

`resume-stopped` runs under the existing cutover lock and requires zero API
writers, the exact immutable candidate image, unchanged prior frontend,
valid staged/prepared assets, the existing migration dry-run/parity checks,
and a fresh verified backup while stopped. It marks `cutover` durably before
migration and proceeds through migration, start, health, publish, smoke,
commit, and retention. It never restarts the old API. Ambiguous bookkeeping,
identity, or parity leaves the marker intact for manual forward recovery.

For a marker already in `cutover` (or after possible writes), use candidate
recovery only after checking the exact candidate image and served pointer:

```bash
APP_HOME=/opt/cocktaildb \
  /opt/cocktaildb/scripts/deploy-cutover.sh recover \
  /opt/cocktaildb/releases/<release-id> \
  cocktaildb-api:release-<release-id>
```

Recovery checks identities, reruns health and smoke, reconciles and commits the
state, and only then retries retention. It never blindly rolls back an
API/database after possible writes. Any failure or abort leaves assets and
release data additive; no pruning occurs until successful commit. If the state
record is committed but frontend cleanup fails, the release is already
deployed; keep it serving, verify identity, and retry cleanup. The cleanup
preflight is fail-closed and preserves unrelated API, migration, backup,
Docker, and migration-parity data.

The first hashed release keeps the old directory as an explicit `legacy`
previous record with no asset inventory. Existing unversioned tabs can require
an immediate refresh. Subsequent releases retain the current and one previous
successful hashed release; assets are retained as the union of those two
inventories. Tabs older than that window may require refresh after pruning.

## Public config generation

The generator accepts CloudFormation outputs, validates the six public fields,
and serializes JSON safely:

```bash
python scripts/generate_config.py cocktail-db-dev dev
python scripts/generate_config.py cocktail-db-prod prod --region us-west-2
python scripts/generate_config.py cocktail-db-dev dev --output custom/path/config.js
```

Only public API and Cognito values are emitted. Database credentials, client
secrets, and AWS secrets are rejected. Ansible uses the same validated field
set before staging its generated config.
