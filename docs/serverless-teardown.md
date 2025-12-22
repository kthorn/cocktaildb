# Serverless Infrastructure Teardown Guide

This document describes how to safely decommission the serverless infrastructure after migrating to EC2.

> **IMPORTANT:** Only proceed with teardown after the EC2 deployment has been running stably for at least 48 hours and all smoke tests pass consistently.

## Pre-Teardown Checklist

Before starting teardown, verify:

- [ ] EC2 instance is running and healthy
- [ ] All smoke tests pass (`./infrastructure/scripts/smoke-test.sh https://your-domain.com`)
- [ ] DNS points to EC2 instance
- [ ] At least 48 hours of stable operation on EC2
- [ ] Final backup from serverless environment (stored in S3)
- [ ] PostgreSQL database populated with migrated data
- [ ] Analytics are being generated on schedule
- [ ] Daily backups are running successfully
- [ ] Users notified of any maintenance window

## Resources to Keep

These resources should **NOT** be deleted as they're still used by EC2:

| Resource | Reason |
|----------|--------|
| Cognito User Pool | Authentication still uses same pool |
| Cognito App Client | Frontend auth unchanged |
| S3 Backup Bucket | Backups stored here |
| S3 Analytics Bucket | Analytics data shared |
| Route53 Hosted Zone | DNS management |

## Teardown Steps

### Phase 1: Disable (Soft Delete)

First, disable without deleting to allow quick rollback:

```bash
# Get the CloudFormation stack name
STACK_NAME="cocktail-db-prod"  # or cocktail-db-dev

# Disable backup Lambda schedule
aws events disable-rule --name "${STACK_NAME}-BackupSchedule" || true

# Note: API Gateway and Lambda remain active but unused
# Traffic should already be going to EC2
```

### Phase 2: Monitor (24-48 Hours)

Monitor EC2 deployment:

```bash
# Check EC2 health
./infrastructure/scripts/smoke-test.sh https://your-domain.com

# Check logs
ssh ec2-user@YOUR_IP 'docker logs cocktaildb-api-1 --tail 100'

# Verify backups
aws s3 ls s3://YOUR-BACKUP-BUCKET/ | tail -5
```

### Phase 3: Delete CloudFormation Stack

Once confident EC2 is stable:

```bash
STACK_NAME="cocktail-db-prod"

# Empty S3 buckets first (CloudFormation can't delete non-empty buckets)
# Note: Only empty buckets you want to DELETE, not shared ones!
aws s3 rm s3://${STACK_NAME}-website --recursive
aws s3 rm s3://${STACK_NAME}-cloudfront-logs --recursive || true

# Delete the stack
aws cloudformation delete-stack --stack-name "$STACK_NAME"

# Monitor deletion (takes 10-20 minutes)
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME"
echo "Stack deleted successfully"
```

### Phase 4: Cleanup Orphaned Resources

Some resources may need manual cleanup:

```bash
# CloudWatch Log Groups
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/${STACK_NAME}" \
    --query 'logGroups[].logGroupName' --output text | \
    xargs -I {} aws logs delete-log-group --log-group-name {}

# ECR Repository (if not needed)
aws ecr delete-repository --repository-name "${STACK_NAME}-analytics" --force || true

# VPC Endpoints (usually deleted with stack, but verify)
# EFS File System (after confirming final backup)
```

## Rollback Procedure

If issues arise and you need to rollback:

### Quick Rollback (DNS)

```bash
# Point DNS back to CloudFront
./infrastructure/scripts/update-dns.sh --rollback
```

### Full Rollback (Re-enable Serverless)

```bash
# Re-enable Lambda schedules
aws events enable-rule --name "${STACK_NAME}-BackupSchedule"

# Verify serverless API is responding
curl https://your-cloudfront-domain.cloudfront.net/api/v1/recipes

# Update DNS to CloudFront
./infrastructure/scripts/update-dns.sh --rollback
```

## Cost Comparison

Document your before/after costs:

### Before (Serverless)
| Service | Monthly Cost |
|---------|-------------|
| Lambda | $X |
| EFS | $X |
| NAT Gateway | ~$32 |
| VPC Endpoints | ~$21 |
| API Gateway | $X |
| Batch/Fargate | $X |
| CloudFront | $X |
| **Total** | **$X/month** |

### After (EC2)
| Service | Monthly Cost |
|---------|-------------|
| EC2 t4g.small (dev) | ~$12 |
| EC2 t4g.medium (prod) | ~$24 |
| EBS 20GB gp3 | ~$2 |
| S3 (backups/analytics) | ~$1 |
| Route53 | ~$0.50 |
| **Total** | **~$15-27/month** |

## Timeline

| Day | Action |
|-----|--------|
| 0 | EC2 deployment complete, smoke tests pass |
| 1-2 | Monitor EC2, keep serverless as backup |
| 3 | Phase 1: Disable serverless schedules |
| 4-5 | Monitor EC2 exclusively |
| 6 | Phase 3: Delete CloudFormation stack |
| 7 | Phase 4: Clean up orphaned resources |

## Troubleshooting

### Stack Deletion Failed

```bash
# Check for resources preventing deletion
aws cloudformation describe-stack-events --stack-name "$STACK_NAME" \
    --query 'StackEvents[?ResourceStatus==`DELETE_FAILED`]'

# Common issues:
# - Non-empty S3 buckets
# - ENIs attached to Lambda in VPC
# - Security groups with dependencies
```

### Need to Keep Some Resources

Create a new stack that references existing resources, or update the stack to remove only specific resources.
