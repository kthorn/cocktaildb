# Latest Backup Download Link Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a public “latest database backup” download link on the about page, backed by an S3 marker updated by the backup job.

**Architecture:** Extend the backup script to upload `latest.txt` (and optional `latest.json`) to the backups S3 bucket after a successful upload. Configure the S3 bucket for public read plus CORS for browser fetches. Update `src/web/about.html` and `src/web/js/about.js` to fetch `latest.txt` on page load and set the download link to the latest backup object.

**Tech Stack:** Bash (backup script), AWS CloudFormation (S3 bucket + policy + CORS), vanilla HTML/JS.

### Task 1: Add a lightweight about-page regression test

**Files:**
- Create: `tests/test_about_backup_link.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_about_page_has_backup_link_id():
    html = Path("src/web/about.html").read_text(encoding="utf-8")
    assert 'id="backup-download-link"' in html


def test_about_js_fetches_latest_marker():
    js = Path("src/web/js/about.js").read_text(encoding="utf-8")
    assert "latest.txt" in js
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_about_backup_link.py -v`
Expected: FAIL (missing link id and latest marker reference).

**Step 3: Write minimal implementation**

Proceed to Task 2 updates.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_about_backup_link.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_about_backup_link.py
git commit -m "test: cover about backup download link"
```

### Task 2: Add latest backup download link on about page

**Files:**
- Modify: `src/web/about.html`
- Modify: `src/web/js/about.js`

**Step 1: Write the failing test**

Covered by Task 1.

**Step 2: Update about page HTML**

Add a button/link and status area near the “About The Code” section:

```html
<p>
  <a id="backup-download-link" class="btn btn-secondary" href="#" aria-disabled="true">
    Download latest database backup
  </a>
  <span id="backup-download-status">Loading latest backup...</span>
</p>
```

**Step 3: Update about page JS**

Fetch the marker and update the link:

```js
const BACKUP_BUCKET = 'cocktaildbbackups-732940910135-prod';
const MARKER_URL = `https://${BACKUP_BUCKET}.s3.amazonaws.com/latest.txt`;

async function setLatestBackupLink() {
  const link = document.getElementById('backup-download-link');
  const status = document.getElementById('backup-download-status');
  if (!link || !status) return;

  try {
    const response = await fetch(MARKER_URL, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const filename = (await response.text()).trim();
    if (!filename) throw new Error('Empty latest marker');

    link.href = `https://${BACKUP_BUCKET}.s3.amazonaws.com/${filename}`;
    link.setAttribute('download', filename);
    link.removeAttribute('aria-disabled');
    status.textContent = '';
  } catch (error) {
    console.error('Failed to load latest backup link:', error);
    link.href = '#';
    link.setAttribute('aria-disabled', 'true');
    status.textContent = 'Backup download unavailable.';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setLatestBackupLink();
});
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_about_backup_link.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/web/about.html src/web/js/about.js
git commit -m "feat: add latest backup download link"
```

### Task 3: Publish latest backup marker + public-read bucket access

**Files:**
- Modify: `infrastructure/scripts/backup-postgres.sh`
- Modify: `template.yaml`

**Step 1: Write the failing test**

Create a basic dry-run smoke test for the backup script output.

File: `tests/test_backup_latest_marker.py`

```python
import os
import subprocess


def test_backup_script_dry_run_mentions_latest_markers():
    env = os.environ.copy()
    env['BACKUP_BUCKET'] = 'example-bucket'
    result = subprocess.run(
        ['bash', 'infrastructure/scripts/backup-postgres.sh', '--dry-run'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert 'latest.txt' in result.stdout
    assert 'latest.json' in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_backup_latest_marker.py -v`
Expected: FAIL (no latest marker output yet).

**Step 3: Update backup script to upload latest markers**

Add after the backup upload succeeds:

```bash
LATEST_TXT_PATH="${BACKUP_DIR}/latest.txt"
LATEST_JSON_PATH="${BACKUP_DIR}/latest.json"
BACKUP_SIZE_BYTES=$(stat -c %s "$BACKUP_PATH")

printf '%s\n' "$BACKUP_FILE" > "$LATEST_TXT_PATH"
cat > "$LATEST_JSON_PATH" <<JSON
{"filename":"$BACKUP_FILE","timestamp":"$TIMESTAMP","size_bytes":$BACKUP_SIZE_BYTES}
JSON

aws s3 cp "$LATEST_TXT_PATH" "s3://${BACKUP_BUCKET}/latest.txt" --content-type text/plain
aws s3 cp "$LATEST_JSON_PATH" "s3://${BACKUP_BUCKET}/latest.json" --content-type application/json
```

Also update the `--dry-run` output section to mention these uploads so the test can assert against it.

**Step 4: Update CloudFormation for public read + CORS**

Add a bucket policy and CORS rules (prod only):

```yaml
  BackupBucket:
    Type: AWS::S3::Bucket
    Condition: IsProdEnvironment
    Properties:
      PublicAccessBlockConfiguration:
        BlockPublicAcls: false
        BlockPublicPolicy: false
        IgnorePublicAcls: false
        RestrictPublicBuckets: false
      CorsConfiguration:
        CorsRules:
          - AllowedMethods:
              - GET
              - HEAD
            AllowedOrigins:
              - "*"
            AllowedHeaders:
              - "*"
            MaxAge: 3000

  BackupBucketPolicy:
    Type: AWS::S3::BucketPolicy
    Condition: IsProdEnvironment
    Properties:
      Bucket: !Ref BackupBucket
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Sid: PublicReadBackups
            Effect: Allow
            Principal: "*"
            Action:
              - s3:GetObject
            Resource: !Sub "${BackupBucket.Arn}/*"
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_backup_latest_marker.py -v`
Expected: PASS.

**Step 6: Commit**

```bash
git add infrastructure/scripts/backup-postgres.sh template.yaml tests/test_backup_latest_marker.py
git commit -m "feat: publish latest backup marker and allow public read"
```
