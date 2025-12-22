# EC2 Operations Runbook

Quick reference for CocktailDB EC2 infrastructure operations.

## Prerequisites

```bash
# Required tools
- AWS CLI (configured with credentials)
- Ansible
- SSH key: ~/.ssh/cocktaildb-ec2.pem

# Required environment variables
export COCKTAILDB_HOST=<ec2-public-ip>
export COCKTAILDB_DB_PASSWORD=<database-password>
export AWS_REGION=us-east-1
```

---

## 1. Initial Setup (New Instance)

### Step 1: Deploy CloudFormation Stack

Creates S3 buckets, Cognito, and IAM resources:

```bash
sam build && sam deploy --stack-name cocktail-db-dev \
  --s3-bucket cocktail-db-dev-deployment-$(aws sts get-caller-identity --query Account --output text) \
  --parameter-overrides Environment=dev DatabaseName=cocktaildb-dev \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
```

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
ansible-playbook playbooks/provision.yml
```

Installs: Docker, PostgreSQL, Caddy, Python, system packages.

### Step 5: Setup Database

```bash
ansible-playbook playbooks/setup-database.yml
```

Creates PostgreSQL database and user.

### Step 6: Deploy Application

```bash
ansible-playbook playbooks/deploy.yml
```

Deploys API, frontend, and systemd services.

### Step 7: Restore Data (if migrating)

```bash
# Set backup bucket
export COCKTAILDB_BACKUP_BUCKET=cocktaildbbackups-<account-id>-prod

# Run migration playbook
ansible-playbook playbooks/migrate-data.yml
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

```bash
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$COCKTAILDB_HOST
```

### View Logs

```bash
# API logs
ssh ec2-user@$COCKTAILDB_HOST "docker logs cocktaildb-api-1 --tail 100"

# Caddy logs
ssh ec2-user@$COCKTAILDB_HOST "sudo journalctl -u caddy -n 100"

# PostgreSQL logs
ssh ec2-user@$COCKTAILDB_HOST "sudo journalctl -u postgresql -n 100"
```

---

## 3. Deployments

### Deploy Code Changes

```bash
cd infrastructure/ansible
ansible-playbook playbooks/deploy.yml
```

### Deploy Only Frontend

```bash
ansible-playbook playbooks/deploy.yml --tags frontend
```

### Deploy Only API

```bash
ansible-playbook playbooks/deploy.yml --tags api
```

### Deploy Caddy Config

```bash
ansible-playbook playbooks/deploy-caddy.yml
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

# Provision server
cd infrastructure/ansible && ansible-playbook playbooks/provision.yml

# Deploy application
ansible-playbook playbooks/deploy.yml

# Start/stop instance
./infrastructure/scripts/start-ec2.sh dev
./infrastructure/scripts/stop-ec2.sh dev

# Check status
./infrastructure/scripts/ec2-status.sh dev

# Run smoke tests
./infrastructure/scripts/smoke-test.sh http://$COCKTAILDB_HOST

# SSH access
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$COCKTAILDB_HOST
```
