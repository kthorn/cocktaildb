# Analytics Debounce Design

## Problem

Currently, every database mutation (create/update/delete recipe or ingredient) triggers an immediate analytics refresh via AWS Batch. Rapid mutations cause multiple expensive Batch jobs to run in quick succession.

## Solution

Use EventBridge Scheduler to debounce analytics triggers. Each mutation pushes out a scheduled run by N minutes. When the schedule finally fires, it invokes the existing `AnalyticsTriggerFunction` to submit a single Batch job.

## Architecture

**Current flow:**
```
API mutation → trigger_analytics_refresh() → invoke AnalyticsTriggerFunction → Batch job
```

**New flow:**
```
API mutation → signal_analytics_run() → update/create EventBridge Schedule
                                              ↓ (5-15 min later)
                              EventBridge → invoke AnalyticsTriggerFunction → Batch job
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Debounce window | 5 min (dev), 15 min (prod) | Faster feedback in dev, more coalescing in prod |
| Schedule target | Existing `AnalyticsTriggerFunction` | Already has correct permissions, does exactly what we need |
| Schedule name | `{StackName}-analytics-debounce` | Aligns with existing naming, handles multi-env |
| Error handling | Fire-and-forget | Analytics secondary to user operations |
| Manual trigger | Bypasses debounce | Intentional triggers should run immediately |
| Scheduler group | `default` | Single schedule doesn't warrant dedicated group |

## Code Changes

### api/utils/analytics_helpers.py

Replace `trigger_analytics_refresh()` with `signal_analytics_run()`:

```python
import datetime
from botocore.exceptions import ClientError

def signal_analytics_run():
    """Signal that analytics should be regenerated.

    Uses EventBridge Scheduler to debounce rapid mutations.
    Each call pushes the scheduled run further out by DEBOUNCE_MINUTES.
    Failures are logged but don't fail the main operation.
    """
    try:
        schedule_name = os.environ.get("ANALYTICS_SCHEDULE_NAME")
        target_arn = os.environ.get("ANALYTICS_TRIGGER_FUNCTION")
        invoke_role_arn = os.environ.get("ANALYTICS_SCHEDULER_ROLE_ARN")
        debounce_minutes = int(os.environ.get("ANALYTICS_DEBOUNCE_MINUTES", "15"))

        if not all([schedule_name, target_arn, invoke_role_arn]):
            logger.debug("Analytics debounce not configured, skipping")
            return

        run_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=debounce_minutes)
        schedule_expression = f"at({run_at.strftime('%Y-%m-%dT%H:%M:%S')})"

        scheduler = boto3.client('scheduler')
        args = {
            "Name": schedule_name,
            "ScheduleExpression": schedule_expression,
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {
                "Arn": target_arn,
                "RoleArn": invoke_role_arn,
                "Input": "{}",
            },
        }

        try:
            scheduler.update_schedule(**args)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                scheduler.create_schedule(**args)
            else:
                raise

        logger.info(f"Analytics scheduled for {run_at.isoformat()}")
    except Exception as e:
        logger.warning(f"Failed to schedule analytics: {str(e)}")
```

### template.yaml

**New IAM role for EventBridge Scheduler:**

```yaml
AnalyticsSchedulerRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal:
            Service: scheduler.amazonaws.com
          Action: sts:AssumeRole
    Policies:
      - PolicyName: InvokeAnalyticsTrigger
        PolicyDocument:
          Version: "2012-10-17"
          Statement:
            - Effect: Allow
              Action: lambda:InvokeFunction
              Resource: !GetAtt AnalyticsTriggerFunction.Arn
```

**New environment variables for CocktailLambda:**

```yaml
ANALYTICS_SCHEDULE_NAME: !Sub "${AWS::StackName}-analytics-debounce"
ANALYTICS_SCHEDULER_ROLE_ARN: !GetAtt AnalyticsSchedulerRole.Arn
ANALYTICS_DEBOUNCE_MINUTES: !If [IsProd, "15", "5"]
```

**Additional permissions for CocktailLambda:**

```yaml
# Scheduler permissions
- Effect: Allow
  Action:
    - scheduler:CreateSchedule
    - scheduler:UpdateSchedule
  Resource: !Sub "arn:aws:scheduler:${AWS::Region}:${AWS::AccountId}:schedule/default/${AWS::StackName}-analytics-debounce"

# PassRole for scheduler
- Effect: Allow
  Action: iam:PassRole
  Resource: !GetAtt AnalyticsSchedulerRole.Arn
```

## What Stays the Same

- `AnalyticsTriggerFunction` - unchanged, just invoked by EventBridge instead of direct invoke
- All 9 call sites in routes - unchanged (function rename only)
- Manual trigger script (`scripts/trigger-analytics-refresh.sh`) - unchanged, bypasses debounce
- Batch job infrastructure - unchanged

## Testing

**Unit tests:**
- Schedule creation when none exists (ResourceNotFoundException → create)
- Schedule update when it exists
- Graceful failure handling (logs warning, doesn't raise)
- Missing env vars (skips silently)

**Integration testing (manual, post-deployment):**
- Create/update a recipe, verify schedule appears in EventBridge console
- Make rapid mutations, confirm only one schedule exists (updated timestamp)
- Wait for debounce window, verify Batch job runs
- Use manual trigger script to confirm it bypasses debounce

## Deployment

1. Deploy infrastructure first (SAM) - creates IAM role and permissions
2. Code changes deploy with Lambda update
3. First mutation after deployment creates the schedule

## Rollback

Revert `signal_analytics_run()` to direct Lambda invoke. Orphaned schedule is harmless.
