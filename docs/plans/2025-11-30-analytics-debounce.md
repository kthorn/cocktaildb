# Analytics Debounce Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add EventBridge Scheduler-based debouncing to coalesce rapid database mutations into single analytics runs.

**Architecture:** Replace direct Lambda invocation with EventBridge Schedule updates. Each mutation pushes the scheduled time forward by 5 min (dev) / 15 min (prod). When schedule fires, it invokes existing AnalyticsTriggerFunction.

**Tech Stack:** AWS EventBridge Scheduler, boto3, SAM/CloudFormation

---

## Task 1: Add AnalyticsSchedulerRole to template.yaml

**Files:**
- Modify: `template.yaml:1446` (after AnalyticsTriggerFunction, before ApiGatewayAccount)

**Step 1: Add the IAM role resource**

Insert after line 1446 (after AnalyticsTriggerFunction closing), before ApiGatewayAccount:

```yaml
  # IAM Role for EventBridge Scheduler to invoke analytics trigger
  AnalyticsSchedulerRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: scheduler.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: InvokeAnalyticsTrigger
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action: lambda:InvokeFunction
                Resource: !GetAtt AnalyticsTriggerFunction.Arn

```

**Step 2: Validate template syntax**

Run: `sam validate --template-file template.yaml`
Expected: Template is valid

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "feat: add AnalyticsSchedulerRole for EventBridge Scheduler"
```

---

## Task 2: Add scheduler permissions to CocktailLambda

**Files:**
- Modify: `template.yaml:669-673` (add after AnalyticsTriggerFunctionInvoke policy)

**Step 1: Add scheduler and PassRole permissions**

After the `AnalyticsTriggerFunctionInvoke` statement (line 673), add:

```yaml
            - Sid: AnalyticsSchedulerAccess
              Effect: Allow
              Action:
                - scheduler:CreateSchedule
                - scheduler:UpdateSchedule
              Resource: !Sub "arn:aws:scheduler:${AWS::Region}:${AWS::AccountId}:schedule/default/${AWS::StackName}-analytics-debounce"
            - Sid: PassSchedulerRole
              Effect: Allow
              Action: iam:PassRole
              Resource: !GetAtt AnalyticsSchedulerRole.Arn
```

**Step 2: Validate template syntax**

Run: `sam validate --template-file template.yaml`
Expected: Template is valid

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "feat: add scheduler permissions to CocktailLambda"
```

---

## Task 3: Add environment variables to CocktailLambda

**Files:**
- Modify: `template.yaml:627` (after ANALYTICS_TRIGGER_FUNCTION)

**Step 1: Add new environment variables**

After `ANALYTICS_TRIGGER_FUNCTION: !Ref AnalyticsTriggerFunction` (line 627), add:

```yaml
          ANALYTICS_SCHEDULE_NAME: !Sub "${AWS::StackName}-analytics-debounce"
          ANALYTICS_SCHEDULER_ROLE_ARN: !GetAtt AnalyticsSchedulerRole.Arn
          ANALYTICS_DEBOUNCE_MINUTES: !If [IsProdEnvironment, "15", "5"]
```

**Step 2: Validate template syntax**

Run: `sam validate --template-file template.yaml`
Expected: Template is valid

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "feat: add analytics debounce environment variables"
```

---

## Task 4: Write failing tests for signal_analytics_run

**Files:**
- Modify: `tests/test_analytics_helpers.py`

**Step 1: Add imports for new tests**

At the top of the file, update imports to include `signal_analytics_run`:

```python
from utils.analytics_helpers import trigger_analytics_refresh, signal_analytics_run
```

**Step 2: Add test for successful schedule update**

Add after existing tests:

```python
@patch('boto3.client')
def test_signal_analytics_run_updates_existing_schedule(mock_boto_client):
    """Test that signal_analytics_run updates an existing schedule"""
    mock_scheduler = Mock()
    mock_boto_client.return_value = mock_scheduler

    env = {
        'ANALYTICS_SCHEDULE_NAME': 'test-stack-analytics-debounce',
        'ANALYTICS_TRIGGER_FUNCTION': 'arn:aws:lambda:us-east-1:123456789:function:test-trigger',
        'ANALYTICS_SCHEDULER_ROLE_ARN': 'arn:aws:iam::123456789:role/test-role',
        'ANALYTICS_DEBOUNCE_MINUTES': '5'
    }

    with patch.dict('os.environ', env):
        signal_analytics_run()

    mock_boto_client.assert_called_with('scheduler')
    mock_scheduler.update_schedule.assert_called_once()
    call_args = mock_scheduler.update_schedule.call_args[1]
    assert call_args['Name'] == 'test-stack-analytics-debounce'
    assert call_args['Target']['Arn'] == env['ANALYTICS_TRIGGER_FUNCTION']
    assert call_args['Target']['RoleArn'] == env['ANALYTICS_SCHEDULER_ROLE_ARN']
    assert call_args['FlexibleTimeWindow'] == {'Mode': 'OFF'}
    assert call_args['ScheduleExpression'].startswith('at(')
```

**Step 3: Add test for schedule creation on ResourceNotFoundException**

```python
@patch('boto3.client')
def test_signal_analytics_run_creates_schedule_when_not_found(mock_boto_client):
    """Test that signal_analytics_run creates schedule if it doesn't exist"""
    from botocore.exceptions import ClientError

    mock_scheduler = Mock()
    mock_scheduler.update_schedule.side_effect = ClientError(
        {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Schedule not found'}},
        'UpdateSchedule'
    )
    mock_boto_client.return_value = mock_scheduler

    env = {
        'ANALYTICS_SCHEDULE_NAME': 'test-stack-analytics-debounce',
        'ANALYTICS_TRIGGER_FUNCTION': 'arn:aws:lambda:us-east-1:123456789:function:test-trigger',
        'ANALYTICS_SCHEDULER_ROLE_ARN': 'arn:aws:iam::123456789:role/test-role',
        'ANALYTICS_DEBOUNCE_MINUTES': '15'
    }

    with patch.dict('os.environ', env):
        signal_analytics_run()

    mock_scheduler.create_schedule.assert_called_once()
    call_args = mock_scheduler.create_schedule.call_args[1]
    assert call_args['Name'] == 'test-stack-analytics-debounce'
```

**Step 4: Add test for missing environment variables**

```python
@patch('boto3.client')
def test_signal_analytics_run_skips_when_not_configured(mock_boto_client):
    """Test that signal_analytics_run skips when env vars missing"""
    mock_scheduler = Mock()
    mock_boto_client.return_value = mock_scheduler

    with patch.dict('os.environ', {}, clear=True):
        signal_analytics_run()

    mock_scheduler.update_schedule.assert_not_called()
    mock_scheduler.create_schedule.assert_not_called()
```

**Step 5: Add test for failure handling**

```python
@patch('boto3.client')
def test_signal_analytics_run_handles_errors_gracefully(mock_boto_client):
    """Test that signal_analytics_run logs errors but doesn't raise"""
    mock_scheduler = Mock()
    mock_scheduler.update_schedule.side_effect = Exception("Scheduler error")
    mock_boto_client.return_value = mock_scheduler

    env = {
        'ANALYTICS_SCHEDULE_NAME': 'test-stack-analytics-debounce',
        'ANALYTICS_TRIGGER_FUNCTION': 'arn:aws:lambda:us-east-1:123456789:function:test-trigger',
        'ANALYTICS_SCHEDULER_ROLE_ARN': 'arn:aws:iam::123456789:role/test-role',
        'ANALYTICS_DEBOUNCE_MINUTES': '5'
    }

    with patch.dict('os.environ', env):
        # Should not raise
        signal_analytics_run()
```

**Step 6: Run tests to verify they fail**

Run: `python -m pytest tests/test_analytics_helpers.py -v`
Expected: FAIL with "cannot import name 'signal_analytics_run'"

**Step 7: Commit failing tests**

```bash
git add tests/test_analytics_helpers.py
git commit -m "test: add failing tests for signal_analytics_run"
```

---

## Task 5: Implement signal_analytics_run function

**Files:**
- Modify: `api/utils/analytics_helpers.py`

**Step 1: Add datetime import**

At top of file, add:

```python
import datetime
```

**Step 2: Add scheduler client caching**

After `_lambda_client = None` (line 10), add:

```python
_scheduler_client = None


def _get_scheduler_client():
    """Get or create the EventBridge Scheduler client (cached at module level)"""
    global _scheduler_client
    if _scheduler_client is None:
        try:
            import boto3
            _scheduler_client = boto3.client('scheduler')
        except Exception as e:
            logger.error(f"Failed to create Scheduler client: {str(e)}")
            raise
    return _scheduler_client
```

**Step 3: Add signal_analytics_run function**

After `trigger_analytics_refresh()` function (after line 47), add:

```python
def signal_analytics_run():
    """Signal that analytics should be regenerated.

    Uses EventBridge Scheduler to debounce rapid mutations.
    Each call pushes the scheduled run further out by DEBOUNCE_MINUTES.
    Failures are logged but don't fail the main operation.
    """
    try:
        from botocore.exceptions import ClientError

        schedule_name = os.environ.get("ANALYTICS_SCHEDULE_NAME")
        target_arn = os.environ.get("ANALYTICS_TRIGGER_FUNCTION")
        invoke_role_arn = os.environ.get("ANALYTICS_SCHEDULER_ROLE_ARN")
        debounce_minutes = int(os.environ.get("ANALYTICS_DEBOUNCE_MINUTES", "15"))

        if not all([schedule_name, target_arn, invoke_role_arn]):
            logger.debug("Analytics debounce not configured, skipping")
            return

        run_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=debounce_minutes)
        schedule_expression = f"at({run_at.strftime('%Y-%m-%dT%H:%M:%S')})"

        scheduler = _get_scheduler_client()
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

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_analytics_helpers.py -v`
Expected: All tests PASS

**Step 5: Commit implementation**

```bash
git add api/utils/analytics_helpers.py
git commit -m "feat: implement signal_analytics_run with EventBridge debouncing"
```

---

## Task 6: Update test fixture to reset scheduler client

**Files:**
- Modify: `tests/test_analytics_helpers.py`

**Step 1: Update reset fixture to include scheduler client**

Update the `reset_lambda_client` fixture:

```python
@pytest.fixture(autouse=True)
def reset_clients():
    """Reset the module-level client caches for test isolation"""
    analytics_helpers._lambda_client = None
    analytics_helpers._scheduler_client = None
    yield
    analytics_helpers._lambda_client = None
    analytics_helpers._scheduler_client = None
```

**Step 2: Run all tests**

Run: `python -m pytest tests/test_analytics_helpers.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_analytics_helpers.py
git commit -m "test: reset scheduler client in test fixture"
```

---

## Task 7: Replace trigger_analytics_refresh calls with signal_analytics_run

**Files:**
- Modify: `api/routes/recipes.py` (4 locations)
- Modify: `api/routes/ingredients.py` (4 locations)

**Step 1: Update imports in recipes.py**

Change:
```python
from utils.analytics_helpers import trigger_analytics_refresh
```

To:
```python
from utils.analytics_helpers import signal_analytics_run
```

**Step 2: Replace function calls in recipes.py**

Replace all occurrences of `trigger_analytics_refresh()` with `signal_analytics_run()`.
Locations: lines ~283, ~353, ~384, ~693

**Step 3: Update imports in ingredients.py**

Change:
```python
from utils.analytics_helpers import trigger_analytics_refresh
```

To:
```python
from utils.analytics_helpers import signal_analytics_run
```

**Step 4: Replace function calls in ingredients.py**

Replace all occurrences of `trigger_analytics_refresh()` with `signal_analytics_run()`.
Locations: lines ~62, ~121, ~150, ~367

**Step 5: Run full test suite**

Run: `python -m pytest tests/ -v --ignore=tests/test_fastapi.py`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add api/routes/recipes.py api/routes/ingredients.py
git commit -m "feat: replace trigger_analytics_refresh with signal_analytics_run"
```

---

## Task 8: Final validation and squash commits (optional)

**Step 1: Validate SAM template**

Run: `sam validate --template-file template.yaml`
Expected: Template is valid

**Step 2: Run all tests**

Run: `python -m pytest tests/ -v --ignore=tests/test_fastapi.py`
Expected: All tests PASS

**Step 3: Review git log**

Run: `git log --oneline main..HEAD`
Expected: Clean commit history showing feature progression
