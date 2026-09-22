# CocktailDB Operations Runbook

Quick reference for CocktailDB infrastructure operations (EC2, CloudFormation, PostgreSQL).

## Prerequisites

- AWS CLI configured with deployment credentials
- Ansible
- Docker for the pre-deployment test suite and real-Caddy release checks
- Node 22.22.2 and npm for the configuration-free frontend artifact
- SSH access configured by `infrastructure/ansible/inventory/{dev,prod}.yml` and `infrastructure/ansible/ansible.cfg`
- The deployed database password in `COCKTAILDB_DB_PASSWORD`

### Database Password Restrictions

The database password (`COCKTAILDB_DB_PASSWORD`) must **not contain `$` characters**. Docker Compose interprets `$` as variable expansion in .env files, which corrupts the password. Use only alphanumeric characters and these safe special characters: `@`, `!`, `#`, `%`, `^`, `&`, `*`, `-`, `_`, `+`, `=`.

---

## 1. Routine Redeployment

The deployment script is the normal path for both environments. Production deployment is an explicit human action after review and merge; CI builds and tests but never deploys.

Build or select one artifact on the controller, then validate and promote those exact bytes:

```bash
export TARGET=dev
export BASE_URL=https://dev.mixology.tools
export COCKTAILDB_DB_PASSWORD='<database-password>'

npm ci && npm run build && npm run test:build
./scripts/deploy-ec2.sh "$TARGET" --frontend-artifact dist
curl --max-time 30 --fail --silent --show-error "$BASE_URL/health"
```

Without `--frontend-artifact`, the wrapper runs the same `npm ci && npm run build`
gate before passing the resulting `dist/` directory to Ansible. Ansible
validates the artifact and public config before remote mutation, stages the API
manifest and frontend, and preserves the existing Caddy configuration.

The cutover helper validates the staged release, writes the pending frontend
publication marker, publishes immutable hashed assets before API start, runs the
existing backup/build/migration checks, starts and health-checks the matching
API image, publishes the release web/config symlink, and smoke-checks static and
SSR pages through Caddy. Only after smoke succeeds does it commit the current /
previous frontend record. It then verifies API and symlink identity before
pruning retired frontend directories and assets outside the union of the two
retained inventories. Docker image/builder cleanup remains a separate phase.

The first hashed deployment preserves the existing real web directory as an
explicit legacy previous record while converting `/opt/cocktaildb/web` to a
symlink. That first conversion is guarded and restorable but is not atomic.
Later releases use a temporary symlink followed by atomic replacement. Existing
unversioned tabs may need an immediate refresh after the first cutover; tabs
older than the retained two-generation window may also require refresh.

A known rating aggregation failure is tracked in
`docs/plans/vite-validation-followups.md`; report it separately from release
gate failures rather than repairing the database or retrying until green.

If rollback is needed, check out the last known-good revision and run the same
reviewed deployment path. Database migrations are not automatically reversed,
and a frontend/API rollback is not a promise that database writes can be undone;
use the coordinated post-write recovery procedure below.

---

## Frontend artifact, local workflow, and recovery

### Local frontend-only workflow

```bash
./scripts/local-config.sh
./scripts/serve.sh
```

Vite listens on strict `http://localhost:8000`; the generated config uses the
remote development API and local FastAPI/database are optional. For integrated
SSR development, start FastAPI on port 8001 with
`FRONTEND_ASSET_MODE=development`, then browse recipe, ingredient, and sitemap
routes through Vite on port 8000. Direct browser access to port 8001 is not a
supported frontend asset flow. A disposable built preview uses an explicitly
selected config and does not modify `dist/`:

```bash
npm ci
npm run build
npm run preview -- dist /path/to/config.js
```

No browser automation is installed. The Node gate checks source/config
externalization and fetches static artifact references, but does not execute
built application modules or SSR. Manually check `/`, search, analytics and
D3, nested recipe/ingredient pages, and login/callback/logout while watching
that hashed assets return 200 and runtime requests use the selected API/auth
configuration.

### Pending publication and cleanup recovery

`/opt/cocktaildb/frontend-pending.json` is a hard preflight gate. Never delete
it to bypass reconciliation. First inspect the marker, active Compose API
container image ID, `/opt/cocktaildb/web` symlink target, current/previous
records, and Caddy health/smoke responses. Recover only with the matching
candidate release and image:

```bash
APP_HOME=/opt/cocktaildb \
  /opt/cocktaildb/scripts/deploy-cutover.sh recover \
  /opt/cocktaildb/releases/<release-id> \
  cocktaildb-api:release-<release-id>
```

Recovery verifies the candidate API image and served symlink, reruns health and
frontend smoke, reconciles identities, commits the successful state, and then
retries frontend retention. It never automatically restarts an old API after
possible writes. If publication and state commit succeeded but cleanup failed,
the release remains healthy and current; verify identities and rerun the
cleanup path. Cleanup retains current plus one previous successful generation
and the union of both inventories, and never removes API, migration, backup,
Docker, or migration-parity data.

### Frontend release paths

| Path | Contents |
| --- | --- |
| `/opt/cocktaildb/web` | Active release symlink (or the pre-migration real directory) |
| `/opt/cocktaildb/releases/<id>/web` | Release HTML and generated public config |
| `/opt/cocktaildb/frontend-assets` | Shared immutable hashed assets |
| `/opt/cocktaildb/frontend-state.json` | Committed current/previous/retired frontend identities |
| `/opt/cocktaildb/frontend-pending.json` | In-progress publication marker requiring recovery |

## 2. Day-to-Day Operations

### Check Instance Status

```bash
./infrastructure/scripts/ec2-status.sh dev
```

### Start Instance (after stop)

```bash
./infrastructure/scripts/start-ec2.sh dev
# Note: IP may change - update COCKTAILDB_HOST
```

### Stop Instance (save costs)

```bash
./infrastructure/scripts/stop-ec2.sh dev
```

### SSH Access

Uses EC2 Instance Connect (key expires in 60 seconds):

```bash
# Dev environment
INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=cocktaildb-dev" --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ec2-instance-connect send-ssh-public-key --instance-id $INSTANCE_ID --instance-os-user ec2-user --ssh-public-key file://~/.ssh/id_ed25519.pub
ssh -i ~/.ssh/id_ed25519 ec2-user@dev.mixology.tools
```

### View Logs

After SSH key is pushed (see SSH Access above):

```bash
# API logs
ssh -i ~/.ssh/id_ed25519 ec2-user@dev.mixology.tools "sudo docker logs cocktaildb-api-1 --tail 100"

# Caddy logs
ssh -i ~/.ssh/id_ed25519 ec2-user@dev.mixology.tools "sudo journalctl -u caddy -n 100"

# PostgreSQL logs
ssh -i ~/.ssh/id_ed25519 ec2-user@dev.mixology.tools "sudo journalctl -u postgresql -n 100"
```

### CloudWatch Logs (Prod)

Caddy access logs are shipped to CloudWatch via the CloudWatch Agent. Log group: `/cocktaildb/prod/caddy-access`. Retention: 30 days.

**Quick check — recent requests:**

```bash
aws logs filter-log-events \
  --log-group-name /cocktaildb/prod/caddy-access \
  --limit 10
```

**Logs Insights queries** (run via Console > CloudWatch > Logs Insights, or CLI):

```bash
# Start a query (returns query ID)
aws logs start-query \
  --log-group-name /cocktaildb/prod/caddy-access \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message | limit 20'

# Get results (use query ID from above)
aws logs get-query-results --query-id <query-id>
```

**Useful Logs Insights queries:**

```text
# Top pages by request count
fields request.uri, status
| stats count() as requests by request.uri
| sort requests desc
| limit 20

# Traffic over time (hourly buckets)
fields @timestamp
| stats count() as requests by bin(1h)

# Error rate
fields status
| stats count() as total,
        sum(status >= 400) as errors
| display total, errors, (errors / total) * 100 as error_pct

# Slow requests (>1s)
fields request.uri, duration, status
| filter duration > 1
| sort duration desc
| limit 20

# Requests by status code
fields status
| stats count() as requests by status
| sort requests desc
```

**CloudWatch Agent status (on EC2):**

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status
```

---

## 3. Database Operations

### Manual Backup

Run the configured systemd service so it loads the database and S3 settings:

```bash
ssh ec2-user@$COCKTAILDB_HOST "sudo systemctl start cocktaildb-backup.service"
ssh ec2-user@$COCKTAILDB_HOST "sudo journalctl -u cocktaildb-backup.service -n 50"
```

### Restore from S3 Backup

List the available backups, then run the restore from the repository root:

```bash
aws s3 ls s3://cocktaildbbackups-<account-id>-prod/
SSH_KEY=~/.ssh/cocktaildb-ec2.pem \
  ./scripts/restore-postgres.sh prod \
  s3://cocktaildbbackups-<account-id>-prod/backup-<timestamp>.sql.gz
```

The script requires an environment-specific confirmation, downloads and validates the selected backup on EC2, creates and reports a safety backup, locks out overlapping restores, stops the API and analytics jobs, recreates and restores the database, then restarts the API and checks database-backed stats. If restoration fails after writers stop, the API, analytics, and backup timer remain stopped; inspect `journalctl -u cocktaildb-backup.service` and the reported safety backup before restarting services.

### Connect to PostgreSQL

```bash
ssh ec2-user@$COCKTAILDB_HOST "sudo -u postgres psql cocktaildb"
```

### Run SQL Query

```bash
ssh ec2-user@$COCKTAILDB_HOST "sudo -u postgres psql cocktaildb -c 'SELECT COUNT(*) FROM recipes;'"
```

---

## 4. Analytics

### Trigger Analytics Refresh

```bash
./infrastructure/scripts/trigger-analytics-remote.sh dev.mixology.tools --bg
```

### Check Analytics Status

```bash
./infrastructure/scripts/trigger-analytics-remote.sh dev.mixology.tools --status
```

---

## 5. Health Checks

### API Health Check

```bash
curl --fail --silent --show-error https://dev.mixology.tools/health
curl --fail --silent --show-error https://mixology.tools/health
```

---

## 6. Troubleshooting

Start with instance status, failed services, and recent logs:

```bash
./infrastructure/scripts/ec2-status.sh <dev|prod>
ssh ec2-user@$COCKTAILDB_HOST "sudo systemctl --failed"
ssh ec2-user@$COCKTAILDB_HOST "sudo docker ps"
ssh ec2-user@$COCKTAILDB_HOST "sudo docker logs cocktaildb-api-1 --tail 100"
ssh ec2-user@$COCKTAILDB_HOST "sudo journalctl -u caddy -n 100"
ssh ec2-user@$COCKTAILDB_HOST "sudo journalctl -u postgresql -n 100"
```

For a non-migration failure, fix the reported problem and rerun the routine deployment. If a migration fails, inspect the database and `schema_migrations` before retrying because the failed SQL may have been partially applied. For an application regression, redeploy the last known-good revision as described above.

---

## 7. DNS Management

### Update DNS to Point to EC2

```bash
export HOSTED_ZONE_ID=<your-zone-id>
export DOMAIN_NAME=mixology.tools
export EC2_PUBLIC_IP=$COCKTAILDB_HOST

./infrastructure/scripts/update-dns.sh
```

### Check DNS Propagation

```bash
dig +short mixology.tools
```

---

## 8. Cost Management

### Instance Costs (us-east-1)

| Instance | Monthly Cost | Use Case |
| ---------- | ------------ | -------- |
| t4g.small | ~$12 | Dev |
| t4g.medium | ~$24 | Prod |
| EBS 30GB gp3 | ~$3 | Storage |

### Stop Instance When Not in Use

```bash
./infrastructure/scripts/stop-ec2.sh dev
```

Stopped instances only pay for EBS storage (~$3/month).

---

## 9. Environment Reference

### CloudFormation Outputs

```bash
aws cloudformation describe-stacks --stack-name cocktail-db-dev \
  --query 'Stacks[0].Outputs' --output table
```

### Key Outputs

| Output | Description |
| ------ | ----------- |
| EC2InstanceProfileName | IAM profile for S3 access |
| BackupBucketName | S3 bucket for backups (prod only) |
| UserPoolId | Cognito user pool ID |
| UserPoolClientId | Cognito client ID |

### Important Paths on EC2

| Path | Contents |
| ---- | -------- |
| /opt/cocktaildb | Application root |
| /opt/cocktaildb/api | API code |
| /opt/cocktaildb/web | Frontend files |
| /opt/cocktaildb/backups | Local backup storage |
| /opt/cocktaildb/.env | Environment config |
| /etc/caddy/Caddyfile | Caddy configuration |

---

## Quick Command Reference

```bash
# Routine production deployment
export COCKTAILDB_DB_PASSWORD='<pw>'
python -m pytest tests/ -q &&
  ./scripts/deploy-ec2.sh prod &&
  curl --max-time 30 --fail --silent --show-error https://mixology.tools/health

# Start/stop instance
./infrastructure/scripts/start-ec2.sh dev
./infrastructure/scripts/stop-ec2.sh dev

# Check status
./infrastructure/scripts/ec2-status.sh dev

# SSH access (push key first, expires in 60s)
INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=cocktaildb-dev" --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ec2-instance-connect send-ssh-public-key --instance-id $INSTANCE_ID --instance-os-user ec2-user --ssh-public-key file://~/.ssh/id_ed25519.pub
ssh -i ~/.ssh/id_ed25519 ec2-user@dev.mixology.tools
```
