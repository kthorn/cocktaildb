# Lambda Remnants Cleanup Proposal (EC2 + CloudFormation)

## Goal
Remove Lambda-era assumptions from the EC2 deployment while preserving CloudFormation for shared resources (Cognito, S3, IAM).

## Proposed Code Changes

### 1) Remove CloudFormation lookup for Cognito config
Current behavior in `api/core/config.py` falls back to CloudFormation outputs to fill `USER_POOL_ID` and `APP_CLIENT_ID` when env vars are missing. This was useful in Lambda/SAM environments but is unnecessary on EC2 because Ansible already supplies explicit Cognito values.

Proposed change:
- Remove `_load_cognito_config_from_cfn()` and its invocation.
- Rely solely on `USER_POOL_ID` / `APP_CLIENT_ID` env vars (set by Ansible inventory).

Why:
- EC2 hosts do not have Lambda/SAM env vars.
- Removes AWS API calls on app startup.
- Keeps config deterministic and explicit.

Impacted files:
- `api/core/config.py`

### 2) Remove or update Lambda-specific comments
Update comments that still reference Lambda-only behavior.

Impacted files:
- `api/db/database.py` (comment: "Global database connection cache for Lambda environments")
- `api/core/database.py` (unused, Lambda-era comment)

Recommendation:
- Either remove `api/core/database.py` if truly unused, or strip Lambda references.
- Update `api/db/database.py` comment to generic connection cache.

## Proposed Docs Cleanup (Optional)
These are still Lambda-centric and likely outdated:
- `api/README.md` (Mangum, handler, serverless.yml)
- `README.md` (serverless/EFS/Lambda architecture statements)

Recommendation:
- If EC2 is the only deploy target, retire or move these to an archive folder and update docs to point to EC2 workflows.
- If these remain for rollback or legacy, label them clearly as "legacy/serverless".

## Open Questions
1) Should legacy Lambda/SAM scripts be deleted or archived?
2) Is `api/core/database.py` safe to remove (no imports found)?
