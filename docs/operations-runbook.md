# CocktailDB Operations Runbook

Quick reference for CocktailDB infrastructure operations (EC2, CloudFormation, PostgreSQL).

## Prerequisites

```bash
# Required tools
- AWS CLI (configured with credentials)
- Ansible
- SSH key: ~/.ssh/id_ed25519 (used with EC2 Instance Connect)

# Environment-specific config is in inventory files:
# - infrastructure/ansible/inventory/dev.yml
# - infrastructure/ansible/inventory/prod.yml

# Only COCKTAILDB_DB_PASSWORD needs to be passed at runtime
```

**Important: Database Password Restrictions**

The database password (`COCKTAILDB_DB_PASSWORD`) must **not contain `$` characters**. Docker Compose interprets `$` as variable expansion in .env files, which corrupts the password. Use only alphanumeric characters and these safe special characters: `@`, `!`, `#`, `%`, `^`, `&`, `*`, `-`, `_`, `+`, `=`.

---

## 1. Initial Setup (New Environment)

### CloudFormation Stack Architecture

CocktailDB uses two CloudFormation stacks:

1. **EC2 Stack** (`cocktaildb-{env}-ec2`): EC2-specific resources
   - IAM Role and Instance Profile (for S3 access)
   - Elastic IP (for stable DNS)

2. **Main Stack** (`cocktail-db-{env}`): Shared AWS resources
   - S3: AnalyticsBucket, BackupBucket (prod only)
   - Cognito: User pool, client, domain, groups
   - DNS: A record pointing to Elastic IP (prod only)

### Step 1a: Deploy EC2 IAM Stack

Creates IAM role, instance profile, and Elastic IP:

```bash
# Dev or Prod environment
aws cloudformation deploy \
  --template-file infrastructure/cloudformation/ec2-iam.yaml \
  --stack-name cocktaildb-dev-ec2 \
  --parameter-overrides Environment=dev \
  --capabilities CAPABILITY_NAMED_IAM

# Get the Elastic IP for use in main stack
aws cloudformation describe-stacks --stack-name cocktaildb-dev-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`ElasticIP`].OutputValue' --output text
```

**What gets created:**
- IAM: EC2Role, EC2InstanceProfile (for S3 access)
- EC2: Elastic IP address

### Step 1b: Deploy Main CloudFormation Stack

Creates S3 buckets, Cognito, and DNS records:

```bash
# Dev environment
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name cocktaildb-dev \
  --parameter-overrides Environment=dev \
  --capabilities CAPABILITY_NAMED_IAM

# Prod environment (requires additional parameters)
ELASTIC_IP=$(aws cloudformation describe-stacks --stack-name cocktaildb-prod-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`ElasticIP`].OutputValue' --output text)

aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name cocktaildb-prod \
  --parameter-overrides \
    Environment=prod \
    HostedZoneId=Z098387725SH34NHYBQWI \
    EC2ElasticIP=$ELASTIC_IP \
    AuthCertificateArn=arn:aws:acm:us-east-1:732940910135:certificate/ef4e8b26-0806-4d73-80a1-682201322d1f \
  --capabilities CAPABILITY_NAMED_IAM
```

**What gets created:**
- S3: AnalyticsBucket, BackupBucket (prod only)
- Cognito: User pool, client, domain, groups
- DNS: A record pointing to Elastic IP (prod only)

### Step 2: Launch EC2 Instance

```bash
./infrastructure/scripts/launch-ec2.sh dev
```

This will:
- Launch t4g.small (dev) or t4g.medium (prod) ARM instance
- Create security group (SSH, HTTP, HTTPS)
- Attach IAM instance profile for S3 access
- Output the public IP

### Step 3: Set Environment Variables

```bash
export COCKTAILDB_HOST=<ip-from-step-2>
export COCKTAILDB_DB_PASSWORD=<choose-secure-password>
```

### Step 4: Provision Server

```bash
cd infrastructure/ansible
COCKTAILDB_DB_PASSWORD="<your-password>" ansible-playbook -i inventory/dev.yml playbooks/provision.yml
```

Installs: Docker, PostgreSQL, Caddy, Python, system packages.

### Step 5: Setup Database

```bash
COCKTAILDB_DB_PASSWORD="<your-password>" ansible-playbook -i inventory/dev.yml playbooks/setup-database.yml
```

Creates PostgreSQL database and user.

### Step 6: Deploy Application

```bash
COCKTAILDB_DB_PASSWORD="<your-password>" ansible-playbook -i inventory/dev.yml playbooks/deploy.yml
```

Deploys API, frontend, and systemd services.

### Step 7: Restore Data (if migrating)

```bash
# Run migration playbook
COCKTAILDB_DB_PASSWORD="<your-password>" ansible-playbook -i inventory/dev.yml playbooks/migrate-data.yml
```

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

### Run Database Migrations

Run the deploy playbook first so `/opt/cocktaildb` ownership and scripts are set:

```bash
COCKTAILDB_DB_PASSWORD="<your-password>" ansible-playbook -i inventory/dev.yml playbooks/deploy.yml
```

Then run migrations from your local machine:

```bash
COCKTAILDB_SSH_KEY=~/.ssh/cocktaildb-ec2.pem scripts/run-remote-migrations.sh dev
```

By default, the script uploads the most recent local migration from `migrations/`.
To target a specific file, set `COCKTAILDB_MIGRATION_FILE=/path/to/migration.sql`.
The upload happens via `/tmp` and then moves into `/opt/cocktaildb/migrations` with sudo.

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

---

## 3. Deployments

All Ansible commands should be run from `infrastructure/ansible/` directory.

### Deploy Code Changes

```bash
cd infrastructure/ansible
COCKTAILDB_DB_PASSWORD="<your-password>" ansible-playbook -i inventory/dev.yml playbooks/deploy.yml
```

### Deploy Caddy Config

```bash
COCKTAILDB_DB_PASSWORD="<your-password>" ansible-playbook -i inventory/dev.yml playbooks/deploy-caddy.yml
```

---

## 4. Database Operations

### Manual Backup

```bash
ssh ec2-user@$COCKTAILDB_HOST "/opt/cocktaildb/scripts/backup-postgres.sh"
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

## 5. Analytics

### Trigger Analytics Refresh

```bash
./scripts/trigger-analytics-refresh.sh dev
# or manually on EC2:
ssh ec2-user@$COCKTAILDB_HOST "/opt/cocktaildb/scripts/trigger-analytics.sh"
```

### Check Analytics Timer Status

```bash
ssh ec2-user@$COCKTAILDB_HOST "systemctl status cocktaildb-analytics.timer"
```

---

## 6. Health Checks

### Quick Smoke Test

```bash
./infrastructure/scripts/smoke-test.sh http://$COCKTAILDB_HOST
```

### API Health Check

```bash
curl -s http://$COCKTAILDB_HOST/api/v1/stats | jq .
```

### Test S3 Access (IAM Role)

```bash
ssh ec2-user@$COCKTAILDB_HOST "aws s3 ls s3://cocktailanalytics-<account-id>-dev/"
```

---

## 7. Troubleshooting

### API Not Responding

```bash
# Check if container is running
ssh ec2-user@$COCKTAILDB_HOST "docker ps"

# Check container logs
ssh ec2-user@$COCKTAILDB_HOST "docker logs cocktaildb-api-1 --tail 50"

# Restart container
ssh ec2-user@$COCKTAILDB_HOST "cd /opt/cocktaildb && docker compose restart"
```

### Database Connection Issues

```bash
# Check PostgreSQL status
ssh ec2-user@$COCKTAILDB_HOST "systemctl status postgresql"

# Check PostgreSQL is listening
ssh ec2-user@$COCKTAILDB_HOST "ss -tlnp | grep 5432"

# Test connection
ssh ec2-user@$COCKTAILDB_HOST "psql -U cocktaildb -h localhost -d cocktaildb -c 'SELECT 1;'"
```

### Caddy/SSL Issues

```bash
# Check Caddy status
ssh ec2-user@$COCKTAILDB_HOST "systemctl status caddy"

# View Caddy logs
ssh ec2-user@$COCKTAILDB_HOST "sudo journalctl -u caddy -n 50"

# Reload Caddy config
ssh ec2-user@$COCKTAILDB_HOST "sudo systemctl reload caddy"
```

### Disk Space

```bash
ssh ec2-user@$COCKTAILDB_HOST "df -h"
```

### Memory Usage

```bash
ssh ec2-user@$COCKTAILDB_HOST "free -h"
```

### Instance Won't Start

```bash
# Check EC2 status
aws ec2 describe-instance-status --instance-ids <instance-id>

# Check system logs
aws ec2 get-console-output --instance-id <instance-id> --output text
```

---

## 8. DNS Management

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

## 9. Cost Management

### Instance Costs (us-east-1)

| Instance | Monthly Cost | Use Case |
|----------|-------------|----------|
| t4g.small | ~$12 | Dev |
| t4g.medium | ~$24 | Prod |
| EBS 30GB gp3 | ~$3 | Storage |

### Stop Instance When Not in Use

```bash
./infrastructure/scripts/stop-ec2.sh dev
```

Stopped instances only pay for EBS storage (~$3/month).

---

## 10. Environment Reference

### CloudFormation Outputs

```bash
aws cloudformation describe-stacks --stack-name cocktail-db-dev \
  --query 'Stacks[0].Outputs' --output table
```

### Key Outputs

| Output | Description |
|--------|-------------|
| EC2InstanceProfileName | IAM profile for S3 access |
| AnalyticsBucketName | S3 bucket for analytics cache |
| BackupBucketName | S3 bucket for backups (prod only) |
| UserPoolId | Cognito user pool ID |
| UserPoolClientId | Cognito client ID |

### Important Paths on EC2

| Path | Contents |
|------|----------|
| /opt/cocktaildb | Application root |
| /opt/cocktaildb/api | API code |
| /opt/cocktaildb/web | Frontend files |
| /opt/cocktaildb/backups | Local backup storage |
| /opt/cocktaildb/.env | Environment config |
| /etc/caddy/Caddyfile | Caddy configuration |

---

## Quick Command Reference

```bash
# Launch new instance
./infrastructure/scripts/launch-ec2.sh dev

# Provision server (from infrastructure/ansible/)
cd infrastructure/ansible
COCKTAILDB_DB_PASSWORD="<pw>" ansible-playbook -i inventory/dev.yml playbooks/provision.yml

# Deploy application (from infrastructure/ansible/)
COCKTAILDB_DB_PASSWORD="<pw>" ansible-playbook -i inventory/dev.yml playbooks/deploy.yml

# Start/stop instance
./infrastructure/scripts/start-ec2.sh dev
./infrastructure/scripts/stop-ec2.sh dev

# Check status
./infrastructure/scripts/ec2-status.sh dev

# Run smoke tests
./infrastructure/scripts/smoke-test.sh http://$COCKTAILDB_HOST

# SSH access (push key first, expires in 60s)
INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=cocktaildb-dev" --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ec2-instance-connect send-ssh-public-key --instance-id $INSTANCE_ID --instance-os-user ec2-user --ssh-public-key file://~/.ssh/id_ed25519.pub
ssh -i ~/.ssh/id_ed25519 ec2-user@dev.mixology.tools
```
