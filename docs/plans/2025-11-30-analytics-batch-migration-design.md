# Analytics Refresh: Lambda to AWS Batch Migration

**Date:** 2025-11-30
**Status:** Approved

## Problem

The `AnalyticsRefreshFunction` Lambda times out (15-minute limit) when computing cocktail space analytics with Earth Mover's Distance and UMAP.

## Solution

Migrate analytics refresh to AWS Batch running on Graviton Spot instances.

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  CocktailLambda │────▶│ AnalyticsTrigger     │────▶│   AWS Batch Job     │
│  (API Handler)  │     │ Lambda (thin)        │     │   (analytics)       │
└─────────────────┘     └──────────────────────┘     └─────────────────────┘
                              │                              │
                              │ returns job ARN              │
                              ▼                              │
                        ┌──────────┐                         │
                        │ Caller   │                         │
                        └──────────┘                         │
                                                             ▼
┌─────────────────┐                                  ┌───────────────┐
│  EFS (SQLite)   │◀─────────── read-only ──────────│ Batch Container│
└─────────────────┘                                  └───────┬───────┘
                                                             │
                                                             ▼
                                                     ┌───────────────┐
                                                     │ S3 Analytics  │
                                                     │ Bucket        │
                                                     └───────────────┘
```

## Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Trigger mechanism | Thin Lambda submits Batch job | Keeps async interface, enables future debouncing |
| Database access | Mount EFS directly (read-only) | Reuses existing VPC/security groups, minimal change |
| Container image | CLI entrypoint, no Lambda handler | Clean separation, simpler image |
| Compute | Graviton Spot (c7g family) | Cost-effective, ARM64 performance |
| Instance types | c7g.medium, c7g.large, c7g.xlarge, c7g.2xlarge | Spot flexibility, room to scale to 8+ CPUs |
| Memory | 2048 MB minimum | Sufficient for current workload |
| Retries | 3 attempts for Spot interruptions | Handles reclamation gracefully |
| Environments | Both dev and prod | Testing parity |
| Response | Return job ARN | Enables optional status polling |

## Infrastructure Changes (template.yaml)

### New Resources

| Resource | Purpose |
|----------|---------|
| `BatchServiceRole` | IAM role for Batch to manage EC2/ECS |
| `BatchInstanceRole` | IAM role for EC2 instances (EFS, S3, ECR access) |
| `BatchInstanceProfile` | Instance profile wrapping the role |
| `BatchSecurityGroup` | Security group allowing EFS access (port 2049) |
| `AnalyticsComputeEnvironment` | Managed Spot compute env with Graviton instances |
| `AnalyticsJobQueue` | Job queue linked to compute environment |
| `AnalyticsJobDefinition` | Container config: image, memory, EFS mount, env vars |
| `AnalyticsTriggerLambda` | Thin Lambda to submit Batch jobs |

### Modified Resources

| Resource | Change |
|----------|--------|
| `CocktailLambda` | Update env var: `ANALYTICS_REFRESH_FUNCTION` → `ANALYTICS_TRIGGER_FUNCTION` |

### Removed Resources

| Resource | Reason |
|----------|--------|
| `AnalyticsRefreshFunction` | Replaced by Batch job |

### Kept As-Is

| Resource | Reason |
|----------|--------|
| `AnalyticsECRRepository` | Same repo, different image entrypoint |
| `AnalyticsBucket` | Unchanged - Batch writes here |

## Code Changes

### New Files

| File | Purpose |
|------|---------|
| `api/analytics/__main__.py` | CLI entrypoint for Batch |
| `api/analytics/trigger.py` | Trigger Lambda handler (submits Batch job) |

### Modified Files

| File | Change |
|------|--------|
| `api/analytics/Dockerfile` | Change entrypoint to CLI |
| `api/analytics/analytics_refresh.py` | Extract core logic, remove Lambda handler |
| `api/utils/analytics_helpers.py` | Update to invoke trigger Lambda |
| `scripts/trigger-analytics-refresh.sh` | Update to invoke trigger Lambda |

### Code Structure After

```
api/analytics/
├── __main__.py           # CLI: python -m analytics (Batch entrypoint)
├── analytics_refresh.py  # Core logic: regenerate_analytics() function
├── trigger.py            # Lambda handler: submits Batch job
└── Dockerfile            # CMD ["python", "-m", "analytics"]
```

## Error Handling

### Batch Retry Strategy

```yaml
retryStrategy:
  attempts: 3
  evaluateOnExit:
    - onStatusReason: "Host EC2*"  # Spot interruption
      action: RETRY
    - onReason: "*Spot*"
      action: RETRY
    - onExitCode: "*"
      action: EXIT  # Don't retry app failures
```

### Observability

- CloudWatch Logs: `/aws/batch/job` for job output
- CloudWatch Logs: `/aws/lambda/<trigger-function>` for trigger logs
- Batch console for job status and history

## Deployment

1. Deploy to dev: `sam build && sam deploy --config-env dev`
2. Test: `./scripts/trigger-analytics-refresh.sh dev`
3. Verify S3 analytics updated
4. Deploy to prod: `sam deploy --config-env prod`

### Rollback

Revert SAM template to restore Lambda-based analytics. No data migration needed.
