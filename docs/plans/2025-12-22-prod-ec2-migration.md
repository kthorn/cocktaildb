# Production EC2 Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Safely migrate production from serverless infrastructure (Lambda/EFS/CloudFront) to EC2 with PostgreSQL without breaking user authentication or causing downtime.

**Architecture:** Launch EC2 instance with Elastic IP, provision PostgreSQL database, migrate SQLite data, update DNS to point domain to EC2. Cognito callback URLs already use the custom domain, so authentication continues working when DNS switches.

**Tech Stack:** EC2 (t4g.medium), PostgreSQL, Docker, Caddy, Ansible, CloudFormation

**Key Safety Insight:** Cognito callback URLs use `https://mixology.tools/callback.html` (the domain), not CloudFront directly. When DNS points to EC2, authentication flows continue working unchanged.

---

## Prerequisites Checklist

Before starting, verify:

- [x] Dev EC2 deployment working and tested
- [x] SQLite to PostgreSQL migration validated on dev
- [x] Database backup from prod: `~/cocktaildb/backup-2025-12-22_08-00-45.db`
- [ ] AWS CLI configured with appropriate permissions
- [ ] SSH key for EC2 access (`cocktaildb-ec2` key pair exists)

---

## Phase 1: Preparation (Before Any Changes)

### Task 1: Verify Prod Cognito Configuration

**Purpose:** Confirm Cognito uses domain-based URLs (critical for safe migration).

**Existing backup:** `~/cocktaildb/backup-2025-12-22_08-00-45.db` (already available, skip backup creation)

**Step 1: Get prod Cognito callback URLs**

```bash
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name cocktail-db-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' --output text)
CLIENT_ID=$(aws cloudformation describe-stacks --stack-name cocktail-db-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' --output text)

aws cognito-idp describe-user-pool-client \
  --user-pool-id "$USER_POOL_ID" \
  --client-id "$CLIENT_ID" \
  --query 'UserPoolClient.{CallbackURLs:CallbackURLs,LogoutURLs:LogoutURLs}'
```

Expected output should show domain-based URLs:
```json
{
    "CallbackURLs": [
        "https://mixology.tools/callback.html",
        "https://mixology.tools/login.html"
    ],
    "LogoutURLs": [
        "https://mixology.tools/logout.html"
    ]
}
```

**If URLs reference CloudFront instead of the domain, STOP and update them first!**

---

## Phase 2: EC2 Infrastructure Setup

### Task 3: Deploy EC2 IAM Stack and Launch Instance

**Files:**
- Creates: `infrastructure/cloudformation/ec2-iam.yaml` (if not exists)
- Uses: `infrastructure/scripts/launch-ec2.sh`

**Architecture Note:** We use a separate CloudFormation stack (`cocktaildb-prod-ec2`) for EC2-specific resources (IAM role, instance profile, Elastic IP). This keeps the EC2 infrastructure separate from the main serverless stack during migration, and can later be imported into the main stack.

**Step 1: Deploy EC2 IAM CloudFormation stack**

```bash
aws cloudformation deploy \
  --template-file infrastructure/cloudformation/ec2-iam.yaml \
  --stack-name cocktaildb-prod-ec2 \
  --parameter-overrides Environment=prod \
  --capabilities CAPABILITY_NAMED_IAM
```

Expected: Stack creates successfully with EC2Role, EC2InstanceProfile, and ElasticIP.

**Step 2: Get the Elastic IP from stack outputs**

```bash
export PROD_ELASTIC_IP=$(aws cloudformation describe-stacks --stack-name cocktaildb-prod-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`ElasticIP`].OutputValue' --output text)
export ALLOCATION_ID=$(aws cloudformation describe-stacks --stack-name cocktaildb-prod-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`ElasticIPAllocationId`].OutputValue' --output text)
echo "Elastic IP: $PROD_ELASTIC_IP (Allocation ID: $ALLOCATION_ID)"
```

**Step 3: Launch the EC2 instance**

```bash
cd /home/kurtt/cocktaildb
./infrastructure/scripts/launch-ec2.sh prod
```

Expected output:
```
=== Launching CocktailDB prod Instance ===
Instance type: t4g.medium
Using AMI: ami-XXXX
...
=== Instance Ready ===
Instance ID: i-XXXX
Public IP: X.X.X.X
```

**Step 4: Note the instance ID**

```bash
export PROD_INSTANCE_ID="i-XXXX"  # Use actual value from output
```

**Step 5: Wait for instance to be fully ready (2-3 minutes)**

```bash
aws ec2 wait instance-status-ok --instance-ids "$PROD_INSTANCE_ID"
echo "Instance ready"
```

---

### Task 4: Associate Elastic IP with Instance

**Purpose:** Associate the CloudFormation-created Elastic IP with the new instance.

**Step 1: Associate Elastic IP with instance**

```bash
aws ec2 associate-address --instance-id "$PROD_INSTANCE_ID" --allocation-id "$ALLOCATION_ID"
echo "Associated $PROD_ELASTIC_IP with instance $PROD_INSTANCE_ID"
```

**Step 2: Verify association**

```bash
aws ec2 describe-addresses --allocation-ids "$ALLOCATION_ID" \
  --query 'Addresses[0].{IP:PublicIp,InstanceId:InstanceId}'
```

Expected: Shows the Elastic IP associated with the instance ID.

---

### Task 5: Create Production Ansible Inventory

**Files:**
- Create: `infrastructure/ansible/inventory/prod.yml`

**Step 1: Create the prod inventory file**

Create `infrastructure/ansible/inventory/prod.yml`:

```yaml
# infrastructure/ansible/inventory/prod.yml
# Production environment inventory
all:
  hosts:
    cocktaildb:
      ansible_host: <ELASTIC_IP>  # Replace with actual Elastic IP
      ansible_user: ec2-user
      ansible_python_interpreter: /usr/bin/python3

      # Application settings
      app_name: cocktaildb
      app_user: cocktaildb
      app_group: cocktaildb
      app_home: /opt/cocktaildb

      # Database settings
      db_name: cocktaildb
      db_user: cocktaildb
      db_password: "{{ lookup('env', 'COCKTAILDB_DB_PASSWORD') }}"

      # Prod-specific configuration
      domain_name: mixology.tools
      app_env: prod
      aws_region: us-east-1

      # Cognito (from existing prod stack)
      user_pool_id: us-east-1_ECF4xd8J6
      app_client_id: 50rcs7t960nm1p0q4n9t56503e
      cognito_domain: "https://auth.mixology.tools"

      # S3 buckets
      analytics_bucket: cocktailanalytics-732940910135-prod
      backup_bucket: cocktaildbbackups-732940910135-prod
```

**Step 2: Replace placeholder with actual Elastic IP**

Edit the file and replace `<ELASTIC_IP>` with the actual value from Task 4.

**Step 3: Commit**

```bash
git add infrastructure/ansible/inventory/prod.yml
git commit -m "feat: add prod Ansible inventory for EC2 migration"
```

---

### Task 6: Provision the EC2 Instance

**Purpose:** Install PostgreSQL, Docker, Caddy, and all dependencies.

**Step 1: Set the database password environment variable**

```bash
# Use a strong password for prod
export COCKTAILDB_DB_PASSWORD="<your-secure-password>"
```

**Step 2: Run the provision playbook**

```bash
cd /home/kurtt/cocktaildb
COCKTAILDB_DB_PASSWORD="$COCKTAILDB_DB_PASSWORD" \
  ansible-playbook -i infrastructure/ansible/inventory/prod.yml \
  infrastructure/ansible/playbooks/provision.yml
```

Expected: All tasks complete successfully (takes 5-10 minutes)

**Step 3: Verify PostgreSQL is running**

```bash
# SSH to instance and check
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PROD_ELASTIC_IP \
  "sudo systemctl status postgresql"
```

Expected: `active (running)`

---

### Task 7: Setup PostgreSQL Database

**Purpose:** Create the database user and schema.

**Step 1: Run the database setup playbook**

```bash
COCKTAILDB_DB_PASSWORD="$COCKTAILDB_DB_PASSWORD" \
  ansible-playbook -i infrastructure/ansible/inventory/prod.yml \
  infrastructure/ansible/playbooks/setup-database.yml
```

Expected: Database and user created

**Step 2: Verify database connection**

```bash
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PROD_ELASTIC_IP \
  "PGPASSWORD='$COCKTAILDB_DB_PASSWORD' psql -h localhost -U cocktaildb -d cocktaildb -c '\dt'"
```

Expected: Empty table list (no tables yet, schema comes with data migration)

---

## Phase 3: Application Deployment

### Task 8: Deploy Application to EC2

**Purpose:** Deploy API, frontend, and configuration.

**Step 1: Run the deploy playbook**

```bash
COCKTAILDB_DB_PASSWORD="$COCKTAILDB_DB_PASSWORD" \
  ansible-playbook -i infrastructure/ansible/inventory/prod.yml \
  infrastructure/ansible/playbooks/deploy.yml
```

Expected: All tasks complete successfully

**Step 2: Verify Docker container is running**

```bash
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PROD_ELASTIC_IP \
  "sudo docker ps"
```

Expected: `cocktaildb-api` container running

**Step 3: Verify Caddy is running**

```bash
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PROD_ELASTIC_IP \
  "sudo systemctl status caddy"
```

Expected: `active (running)`

---

## Phase 4: Database Migration

### Task 9: Migrate SQLite Data to PostgreSQL

**Purpose:** Import production data from the SQLite backup.

**Step 1: Run the migration playbook with local backup file**

```bash
COCKTAILDB_DB_PASSWORD="$COCKTAILDB_DB_PASSWORD" \
COCKTAILDB_LOCAL_SQLITE="$HOME/cocktaildb/backup-2025-12-22_08-00-45.db" \
  ansible-playbook -i infrastructure/ansible/inventory/prod.yml \
  infrastructure/ansible/playbooks/migrate-data.yml
```

Expected: Migration completes with row counts

**Step 2: Verify data was migrated**

```bash
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PROD_ELASTIC_IP \
  "PGPASSWORD='$COCKTAILDB_DB_PASSWORD' psql -h localhost -U cocktaildb -d cocktaildb -c 'SELECT COUNT(*) FROM recipes; SELECT COUNT(*) FROM ingredients;'"
```

Expected: Non-zero row counts matching your prod data

---

### Task 10: Verify API Works with Database

**Purpose:** Test the EC2 deployment before switching DNS.

**Step 1: Test health endpoint via IP**

```bash
curl -s "http://$PROD_ELASTIC_IP/health" | jq .
```

Expected: `{"status": "healthy", ...}`

**Step 2: Test recipes endpoint**

```bash
curl -s "http://$PROD_ELASTIC_IP/api/v1/recipes?limit=3" | jq '.recipes | length'
```

Expected: `3` (or your recipe count)

**Step 3: Test ingredients endpoint**

```bash
curl -s "http://$PROD_ELASTIC_IP/api/v1/ingredients?limit=3" | jq '.ingredients | length'
```

Expected: `3` (or your ingredient count)

**Step 4: Run full smoke test**

```bash
./infrastructure/scripts/smoke-test.sh "http://$PROD_ELASTIC_IP"
```

Expected: `ALL SMOKE TESTS PASSED`

---

## Phase 5: DNS Cutover

### Task 11: Update DNS to Point to EC2

**Purpose:** Switch traffic from CloudFront to EC2.

**IMPORTANT:** This is the cutover point. After this, users will hit EC2.

**Step 1: Update Route 53 record via AWS CLI**

```bash
# Get the hosted zone ID
HOSTED_ZONE_ID="Z098387725SH34NHYBQWI"  # Your Route 53 hosted zone

# Create change batch
cat > /tmp/dns-change.json << EOF
{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "mixology.tools",
      "Type": "A",
      "TTL": 300,
      "ResourceRecords": [{"Value": "$PROD_ELASTIC_IP"}]
    }
  }]
}
EOF

# Apply the change
aws route53 change-resource-record-sets \
  --hosted-zone-id "$HOSTED_ZONE_ID" \
  --change-batch file:///tmp/dns-change.json
```

Expected: Change submitted successfully

**Step 2: Wait for DNS propagation (1-5 minutes)**

```bash
# Check DNS resolution
dig +short mixology.tools

# Should return your Elastic IP
echo "Expected: $PROD_ELASTIC_IP"
```

**Step 3: Verify HTTPS works**

Caddy will automatically obtain an SSL certificate. This may take 1-2 minutes on first request.

```bash
# First request may be slow (certificate issuance)
curl -s "https://mixology.tools/health" | jq .
```

Expected: `{"status": "healthy", ...}`

---

### Task 12: Verify Authentication Works

**Purpose:** Confirm Cognito authentication still functions.

**Step 1: Test the login page loads**

```bash
curl -s -o /dev/null -w "%{http_code}" "https://mixology.tools/login.html"
```

Expected: `200`

**Step 2: Manual test (CRITICAL)**

Open a browser and:
1. Go to `https://mixology.tools`
2. Click Login
3. Verify Cognito hosted UI appears at `auth.mixology.tools`
4. Log in with existing credentials
5. Verify callback works and you're logged in
6. Test creating/editing a recipe (if you have edit permissions)
7. Verify logout works

**DO NOT PROCEED until authentication is verified working!**

---

### Task 13: Run Post-Cutover Smoke Tests

**Purpose:** Full validation of production on EC2.

**Step 1: Run smoke tests against production domain**

```bash
./infrastructure/scripts/smoke-test.sh "https://mixology.tools"
```

Expected: `ALL SMOKE TESTS PASSED`

**Step 2: Verify analytics are accessible**

```bash
curl -s "https://mixology.tools/api/v1/analytics/ingredient-usage" | jq 'keys'
```

Expected: Analytics data returned

**Step 3: Trigger analytics refresh**

```bash
./scripts/trigger-analytics-refresh.sh prod
```

Expected: Analytics generated and uploaded to S3

---

## Phase 6: Monitoring and Validation

### Task 14: Monitor for 24-48 Hours

**Purpose:** Ensure stability before decommissioning serverless.

**Step 1: Set up log monitoring**

```bash
# View API logs
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PROD_ELASTIC_IP \
  "sudo docker logs cocktaildb-api-1 --tail 100 -f"
```

**Step 2: Monitor error rates**

Check for:
- 5xx errors in Caddy logs
- Database connection errors
- Authentication failures

```bash
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PROD_ELASTIC_IP \
  "sudo journalctl -u caddy -f"
```

**Step 3: Verify backups are running**

After 24 hours:
```bash
aws s3 ls s3://cocktaildbbackups-732940910135-prod/ --recursive | sort | tail -3
```

Expected: New backup files created by EC2 backup timer

**Step 4: Document stability period**

Note the date/time when you've confirmed 48 hours of stable operation.

---

## Phase 7: Serverless Teardown (After Stability Confirmed)

**WAIT** until you've had 48 hours of stable EC2 operation before proceeding!

### Task 15: Disable Serverless Schedules

**Purpose:** Stop serverless components without deleting (allows rollback).

**Step 1: Disable backup schedule**

```bash
aws events disable-rule --name "cocktail-db-prod-BackupSchedule" || echo "Rule may not exist or already disabled"
```

**Step 2: Verify serverless is no longer receiving traffic**

Check CloudWatch metrics for the API Gateway and Lambda - should show near-zero invocations.

---

### Task 16: Update CloudFormation to Remove Serverless Resources

**Purpose:** Clean up serverless infrastructure via CloudFormation.

**This uses the existing cleanup plan:** See `docs/plans/2025-12-22-serverless-cleanup.md` for detailed resource removal.

**Step 1: Verify local template.yaml is the cleaned-up version**

```bash
# Should show minimal resources (Cognito, S3, IAM, DNS only)
grep -E "^  [A-Z]" template.yaml | head -30
```

Expected: Only see AnalyticsBucket, BackupBucket, EC2Role, EC2InstanceProfile, CognitoUserPoolV3, etc.

**Step 2: Deploy the cleaned-up template**

```bash
sam build
sam deploy \
  --stack-name cocktail-db-prod \
  --parameter-overrides \
    Environment=prod \
    DomainName=mixology.tools \
    HostedZoneId=Z098387725SH34NHYBQWI \
    EC2ElasticIP=$PROD_ELASTIC_IP \
    AuthCertificateArn=arn:aws:acm:us-east-1:732940910135:certificate/ef4e8b26-0806-4d73-80a1-682201322d1f \
    UserPoolName=CocktailDB-UserPool-prod \
  --capabilities CAPABILITY_NAMED_IAM
```

This will DELETE the serverless resources (Lambda, API Gateway, VPC, EFS, etc.) but KEEP:
- Cognito User Pool and Client
- S3 Buckets (Analytics, Backups)
- IAM Role and Instance Profile
- DNS Records

Monitor the CloudFormation console - deletion takes 10-20 minutes.

---

### Task 17: Manual Cleanup of Orphaned Resources

**Purpose:** Remove resources CloudFormation can't delete.

**Step 1: Delete CloudWatch Log Groups**

```bash
# List and delete Lambda log groups
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/cocktail-db-prod" \
  --query 'logGroups[].logGroupName' --output text | \
  xargs -I {} aws logs delete-log-group --log-group-name {}

# Delete Batch log groups
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/batch" \
  --query 'logGroups[].logGroupName' --output text | \
  xargs -I {} aws logs delete-log-group --log-group-name {}
```

**Step 2: Delete retained CloudFront OAC**

```bash
# List OACs
aws cloudfront list-origin-access-controls \
  --query 'OriginAccessControlList.Items[?contains(Name, `cocktail`)].{Id:Id,Name:Name}'

# Delete if found (get ETag first)
OAC_ID="<oac-id-from-above>"
ETAG=$(aws cloudfront get-origin-access-control --id "$OAC_ID" --query 'ETag' --output text)
aws cloudfront delete-origin-access-control --id "$OAC_ID" --if-match "$ETAG"
```

**Step 3: Empty and delete unused S3 buckets (optional)**

Only if you want to remove website/logs buckets:
```bash
# Website bucket
aws s3 rm s3://cocktailwebsite-732940910135-prod --recursive
aws s3 rb s3://cocktailwebsite-732940910135-prod

# CloudFront logs bucket
aws s3 rm s3://cocktailcflogs-732940910135-prod --recursive
aws s3 rb s3://cocktailcflogs-732940910135-prod
```

---

### Task 18: Commit Migration Completion

**Step 1: Update documentation**

Update `CLAUDE.md` if needed to reflect the new production setup.

**Step 2: Commit and push**

```bash
git add -A
git commit -m "feat: complete production EC2 migration

- Production now running on EC2 with PostgreSQL
- Serverless infrastructure decommissioned
- Authentication working via existing Cognito
- All smoke tests passing"
git push
```

---

## Rollback Procedures

### Quick Rollback (DNS)

If issues arise after DNS cutover but before serverless teardown:

```bash
# Point DNS back to CloudFront
cat > /tmp/dns-rollback.json << EOF
{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "mixology.tools",
      "Type": "A",
      "AliasTarget": {
        "DNSName": "ddkdje38i7q57.cloudfront.net",
        "HostedZoneId": "Z2FDTNDATAQYW2",
        "EvaluateTargetHealth": false
      }
    }
  }]
}
EOF

aws route53 change-resource-record-sets \
  --hosted-zone-id "Z098387725SH34NHYBQWI" \
  --change-batch file:///tmp/dns-rollback.json
```

### Full Rollback (If Serverless Already Deleted)

If you've already removed serverless resources and need to rollback:

1. You cannot easily restore the serverless infrastructure
2. Focus on fixing EC2 issues instead
3. Use the database backup to restore data if needed
4. Contact AWS support if critical

---

## Summary

**Migration Phases:**
1. Preparation - Backup and verification
2. Infrastructure - Launch EC2, Elastic IP
3. Deployment - Provision and deploy application
4. Database - Migrate SQLite to PostgreSQL
5. Cutover - DNS switch to EC2
6. Monitoring - 48 hours stability
7. Cleanup - Remove serverless resources

**Resources Kept:**
- Cognito User Pool, Client, Domain, Groups (authentication)
- S3 Buckets (Analytics, Backups)
- IAM Role and Instance Profile
- Route 53 DNS Records

**Resources Removed:**
- Lambda Functions (4)
- API Gateway
- CloudFront Distribution
- EFS File System
- VPC, Subnets, Security Groups
- VPC Endpoints (7)
- AWS Batch (Compute Environment, Job Queue, Job Definition)
- CloudWatch Log Groups

**Estimated Time:**
- Active work: 2-3 hours
- Monitoring period: 48 hours before serverless teardown
