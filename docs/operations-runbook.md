# CocktailDB Operations Runbook

Quick reference for CocktailDB infrastructure operations (EC2, CloudFormation, PostgreSQL).

## Prerequisites

- AWS CLI configured with deployment credentials
- Ansible
- Docker for the pre-deployment test suite
- SSH access configured by `infrastructure/ansible/inventory/{dev,prod}.yml` and `infrastructure/ansible/ansible.cfg`
- The deployed database password in `COCKTAILDB_DB_PASSWORD`

### Database Password Restrictions

The database password (`COCKTAILDB_DB_PASSWORD`) must **not contain `$` characters**. Docker Compose interprets `$` as variable expansion in .env files, which corrupts the password. Use only alphanumeric characters and these safe special characters: `@`, `!`, `#`, `%`, `^`, `&`, `*`, `-`, `_`, `+`, `=`.

---

## 1. Routine Redeployment

The deployment script is the normal path for both environments. It deploys the current working tree, applies pending database migrations, rebuilds the API container, syncs the frontend and Caddy configuration, and restarts affected services.

Choose the target environment and run from the repository root with the intended revision checked out. Use `TARGET=dev` and `BASE_URL=https://dev.mixology.tools` when staging a release in dev first.

```bash
export TARGET=prod
export BASE_URL=https://mixology.tools
export COCKTAILDB_DB_PASSWORD='<database-password>'

python -m pytest tests/ -q &&
  ./scripts/deploy-ec2.sh "$TARGET" &&
  curl --max-time 30 --fail --silent --show-error "$BASE_URL/health"
```

A routine redeployment does not require provisioning or separate migration/Caddy commands. New-environment bootstrap is intentionally omitted because it is not a routine operation and the current scripts do not fully automate it.

If rollback is needed, check out the last known-good revision and run the same deployment command. Database migrations are not automatically reversed; confirm that the older application is compatible with the migrated schema before rolling back.

---

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

```bash
# List available backups
aws s3 ls s3://cocktaildbbackups-<account-id>-prod/

# Download specific backup
aws s3 cp s3://cocktaildbbackups-<account-id>-prod/backup-2024-01-15_08-00-00.sql.gz /tmp/

# Restore (on EC2)
ssh ec2-user@$COCKTAILDB_HOST
gunzip -c /tmp/backup-*.sql.gz | psql -U cocktaildb -d cocktaildb
```

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
