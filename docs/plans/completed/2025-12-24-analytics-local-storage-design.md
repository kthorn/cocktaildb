# Analytics Local Storage Migration

**Date:** 2025-12-24
**Status:** Approved

## Summary

Migrate analytics storage from S3 to local filesystem on EC2. This simplifies the architecture by removing cloud storage dependency and fixes the immediate issue where the prod S3 bucket doesn't exist.

## Background

Analytics weren't visible on `mixology.tools/analytics.html` because the configured S3 bucket (`cocktailanalytics-732940910135-prod`) doesn't exist. Rather than create the bucket, we're migrating to local storage.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage location | `/var/lib/cocktaildb/analytics/` | Linux FHS convention for app data |
| S3 fallback | Remove entirely | Simpler code, single storage backend |
| Configuration | `ANALYTICS_PATH` env var | Consistent with existing pattern, flexible for dev/test |

## Changes

### 1. Storage Class (`api/utils/analytics_cache.py`)

Replace S3-based implementation with filesystem-based:

```python
from pathlib import Path
import json
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class AnalyticsStorage:
    """Local filesystem storage for pre-generated analytics data"""

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_version = "v1"
        # Ensure directory exists
        version_path = self.storage_path / self.storage_version
        version_path.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, analytics_type: str) -> Path:
        return self.storage_path / self.storage_version / f"{analytics_type}.json"

    def get_analytics(self, analytics_type: str) -> Optional[Dict[Any, Any]]:
        """Retrieve pre-generated analytics data from local storage"""
        try:
            file_path = self._get_file_path(analytics_type)
            if not file_path.exists():
                logger.info(f"No analytics data found for {analytics_type}")
                return None

            with open(file_path, 'r') as f:
                data = json.load(f)
            logger.info(f"Retrieved analytics data for {analytics_type}")
            return data

        except Exception as e:
            logger.error(f"Error retrieving analytics data for {analytics_type}: {str(e)}")
            return None

    def put_analytics(self, analytics_type: str, data: Dict[Any, Any]) -> bool:
        """Store pre-generated analytics data to local storage"""
        try:
            file_path = self._get_file_path(analytics_type)

            storage_data = {
                "data": data,
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "storage_version": self.storage_version,
                    "analytics_type": analytics_type
                }
            }

            with open(file_path, 'w') as f:
                json.dump(storage_data, f)

            logger.info(f"Successfully stored analytics data for {analytics_type}")
            return True

        except Exception as e:
            logger.error(f"Error storing analytics data for {analytics_type}: {str(e)}")
            return False
```

### 2. Route Configuration (`api/routes/analytics.py`)

```python
# Change from:
ANALYTICS_BUCKET = os.environ.get("ANALYTICS_BUCKET", "")
storage_manager = AnalyticsStorage(ANALYTICS_BUCKET) if ANALYTICS_BUCKET else None

# To:
ANALYTICS_PATH = os.environ.get("ANALYTICS_PATH", "")
storage_manager = AnalyticsStorage(ANALYTICS_PATH) if ANALYTICS_PATH else None
```

### 3. Ansible Inventory

**`infrastructure/ansible/inventory/dev.yml`:**
```yaml
# Remove: analytics_bucket: cocktaildb-dev-analyticsbucket-tydlnoijqkpw
# Add:
analytics_path: /var/lib/cocktaildb/analytics
```

**`infrastructure/ansible/inventory/prod.yml`:**
```yaml
# Remove: analytics_bucket: cocktailanalytics-732940910135-prod
# Add:
analytics_path: /var/lib/cocktaildb/analytics
```

### 4. Ansible Env Template (`infrastructure/ansible/files/env.j2`)

```
# Change from:
ANALYTICS_BUCKET={{ analytics_bucket }}

# To:
ANALYTICS_PATH={{ analytics_path }}
```

### 5. Ansible Deploy Task

Add to deployment playbook:

```yaml
- name: Create analytics directory
  file:
    path: /var/lib/cocktaildb/analytics
    state: directory
    owner: "{{ app_user }}"
    group: "{{ app_user }}"
    mode: '0755'
```

### 6. Docker Compose Volume

Add volume mount for persistence:

```yaml
services:
  api:
    volumes:
      - /var/lib/cocktaildb/analytics:/var/lib/cocktaildb/analytics
```

### 7. CloudFormation Cleanup (`template.yaml`)

Remove:
- `AnalyticsBucket` resource
- `AnalyticsBucketName` output
- IAM policy references to analytics bucket

### 8. Test Updates (`tests/test_analytics_cache.py`)

- Replace S3 mocking with `tmp_path` pytest fixture
- Test file read/write operations
- Test directory auto-creation

## Verification

1. SSH to EC2, verify `/var/lib/cocktaildb/analytics/v1/` exists
2. Run `./infrastructure/scripts/trigger-analytics.sh` to generate analytics
3. Verify JSON files created: `ls -la /var/lib/cocktaildb/analytics/v1/`
4. Test API: `curl https://mixology.tools/api/v1/analytics/ingredient-usage`
5. Check frontend: `https://mixology.tools/analytics.html`

## Rollback

If issues arise:
1. Recreate S3 bucket
2. Revert `ANALYTICS_PATH` to `ANALYTICS_BUCKET` in env
3. Redeploy with original code

Analytics data is regenerated (not migrated), so no data loss risk.
