# Deployment Scripts

This directory contains scripts for configuring and deploying CocktailDB.

## Files

- `deploy-ec2.sh` - EC2 deployment wrapper (Ansible-based)
- `generate_config.py` - Generates `src/web/js/config.js` from CloudFormation outputs
- `requirements.txt` - Python dependencies for the generate_config.py script

## Usage

### Deploy Script (EC2)

```bash
# Deploy to dev environment
./scripts/deploy-ec2.sh dev

# Deploy to prod environment
./scripts/deploy-ec2.sh prod

# Provision + deploy
./scripts/deploy-ec2.sh --provision
```

`deploy-ec2.sh` is the enforced deployment entry point. It assigns one release
ID and runs `playbooks/deploy.yml`, which stages the API, migrations, frontend,
and generated `web/js/config.js` below
`/opt/cocktaildb/releases/<release-id>/`. Caddy continues serving
`/opt/cocktaildb/web` while the playbook stages files. Before its first remote
mutation, the playbook atomically acquires
`/var/lock/cocktaildb-deploy-ansible.lock`. It validates and restarts Caddy
while the old API and frontend are still active, then retains this lifecycle
lock through cutover and timer configuration.

The host helper `/opt/cocktaildb/scripts/deploy-cutover.sh` then holds
`/var/lock/cocktaildb-deploy.lock` and performs this sequence:

1. Inspect every pending migration and require migration 15 in the release.
2. Create and validate a local pre-cutover backup.
3. Preserve the current API image and build the release image without starting it.
4. Gracefully stop the Compose `api` service and verify no API container is running.
5. Run pending migrations and verify migration 15 bookkeeping.
6. For the initial migration, compare legacy and group inventory in both directions.
7. Start the new API and wait for its bounded `/health` readiness check.
8. Replace `/opt/cocktaildb/web` with the staged frontend. The previous frontend
   is retained as `/opt/cocktaildb/releases/previous-web-<release-id>`.

Build and backup failures leave the old API and frontend serving. Failures after
writer shutdown leave the old API stopped. A start or readiness failure also
stops the new API, while a publication failure leaves the ready new API running
with the previous frontend. The previous image is tagged
`cocktaildb-api:rollback-<release-id>`. The helper never restarts the old API.

### Cutover recovery

Read the failed `CUTOVER phase=...` line first. Check API state and the retained
artifacts with:

```bash
cd /opt/cocktaildb
sudo docker compose -p cocktaildb -f docker-compose.yml -f docker-compose.prod.yml ps
sudo docker image ls 'cocktaildb-api:*'
sudo ls -lh backups/ releases/
```

A failed Ansible play deliberately leaves the lifecycle lock directory so a
second deployment cannot overwrite recovery inputs. After confirming no
Ansible deployment is still running and inspecting the failed phase, clear the
empty stale lock before the authorized retry:

```bash
sudo rmdir /var/lock/cocktaildb-deploy-ansible.lock
```

For a failure before writer shutdown, fix the reported problem and rerun the
normal `./scripts/deploy-ec2.sh <environment>` command. After shutdown, keep the
old API stopped. Do not use `scripts/run-remote-migrations.sh` as a standalone
initial group-inventory cutover and do not blindly replay migration 15.

The marker
`/opt/cocktaildb/releases/.migration15-parity-required` persists until exact
initial parity passes. If SQL completed but insertion into `schema_migrations`
failed, inspect the new tables and backfill, then record the verified filename:

```bash
cd /opt/cocktaildb
set -a; . ./.env; set +a
export PGPASSWORD="$DB_PASSWORD"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 \
  -c "INSERT INTO schema_migrations (filename) VALUES ('15_migration_add_user_groups.sql') ON CONFLICT DO NOTHING;"
```

Then rerun `./scripts/deploy-ec2.sh prod` from the repository workstation. That
rerun must retain the marker so the helper performs the exact parity gate.
If inspection proves the migration transaction rolled back completely, move the
marker aside before rerunning so the pending migration can run:

```bash
sudo mv /opt/cocktaildb/releases/.migration15-parity-required \
  /opt/cocktaildb/releases/.migration15-parity-rolled-back
```

Then rerun the normal deploy from the repository workstation.

After the new API has been started, assume it may have accepted group-inventory
writes. Recover by fixing the new release and rerunning the normal deployment.
Returning to the old API requires stopping writers and either restoring the
pre-cutover backup with explicitly accepted data loss or performing a reviewed
reverse export of current group inventory into legacy user rows. Retained legacy
rows alone are not a safe post-write rollback.

### Config Generation Script

The Python script is automatically called by the deploy script, but can also be run standalone:

```bash
# Generate config.js for dev environment
python scripts/generate_config.py cocktail-db-dev dev

# Generate config.js for prod environment with custom region
python scripts/generate_config.py cocktail-db-prod prod --region us-west-2

# Generate config.js with custom output path
python scripts/generate_config.py cocktail-db-dev dev --output custom/path/config.js
```

## Dependencies

Before using the Python script, install the required dependencies:

```bash
pip install -r scripts/requirements.txt
```

Or if using mamba/conda (as used in the deploy script):

```bash
mamba activate cocktaildb-312
pip install -r scripts/requirements.txt
```

## What the Config Script Does

The `generate_config.py` script:

1. Retrieves configuration values from CloudFormation stack outputs:
   - API endpoint URL
   - Cognito User Pool ID
   - Cognito User Pool Client ID
   - Cognito Domain URL
   - Application URL (CloudFront or custom domain based on environment)

2. Validates all values and checks for problematic characters

3. Generates the `src/web/js/config.js` file with the correct configuration

4. Handles environment-specific logic (dev vs prod) for determining the correct application URL

This approach is much cleaner and more maintainable than the complex batch file logic that was previously used. 
