# Asset Fingerprinting Design

**Date:** 2025-11-28
**Status:** Approved, Ready for Implementation

## Problem

Static assets (JS/CSS) are being cached by browsers (especially Safari on iPhone), causing users to see stale code after deployments. This leads to:
- API endpoint mismatches (old config.js pointing to wrong environment)
- JavaScript errors from outdated code
- CSS styling issues

## Solution

Implement content-based asset fingerprinting with aggressive caching headers, following modern frontend best practices (webpack, vite, etc.).

## Design Overview

### Architecture

**Deployment Flow:**
```
deploy.sh:
1. SAM build & deploy (infrastructure)
2. Generate config.js (existing)
3. ⭐ NEW: Asset fingerprinting
   - Create temp directory
   - Hash ALL JS/CSS files (including config.js)
   - Copy files with hashed names
   - Update HTML references
4. ⭐ NEW: Upload with cache headers
   - Hashed assets: max-age=31536000, immutable
   - HTML files: max-age=300, must-revalidate
5. ⭐ NEW: Cleanup old hashed files from S3
6. CloudFront invalidation (HTML only)
7. Clean up temp directory
```

### Fingerprinting Strategy

**Hash Format:** `filename.{8-char-hash}.ext`
- Example: `styles.css` → `styles.47c9f5c8.css`
- Hash: MD5 truncated to 8 characters
- Deterministic: Same content = same hash

**Files to Fingerprint:**
- All `.js` files (including config.js)
- All `.css` files
- Skip: HTML files (they reference hashed assets)

**Storage:**
- Build artifacts in temp directory (`mktemp -d`)
- Keeps local git tree clean
- Automatic cleanup after deploy

### Cache Headers Strategy

**Hashed Assets (JS/CSS):**
```
Cache-Control: public, max-age=31536000, immutable
```
- 1 year cache
- `immutable` flag tells browsers file will never change
- Safe because filename changes when content changes

**HTML Files:**
```
Cache-Control: public, max-age=300, must-revalidate
```
- 5 minute cache
- Must revalidate to pick up new asset references
- Short TTL ensures users get updated HTML quickly

**Why This Works:**
- Changed JS/CSS → new filename → new URL → browser makes fresh request
- Unchanged files keep same hash → continue serving from cache
- HTML always fresh enough to reference latest assets

### S3 Cleanup Strategy

**Approach:** Delete old hashed files AFTER uploading new ones (zero downtime)

**Process:**
1. Upload new hashed files to S3
2. Upload updated HTML files
3. List all S3 files matching pattern `*.*.{js,css}`
4. Parse HTML to find currently referenced hashed files
5. Delete orphaned files (old hashes not in current HTML)

**Safety:**
- New files uploaded before old ones deleted
- Only deletes files matching hash pattern
- Verifies file is not referenced in HTML before deleting

## Implementation Components

### 1. Fingerprinting Script

**File:** `scripts/fingerprint_assets.py`

**Responsibilities:**
- Find all JS/CSS files in `src/web/`
- Generate MD5 hash for each file (8 chars)
- Copy to temp directory with hashed filenames
- Update HTML files to reference hashed filenames
- Preserve directory structure
- Output manifest of current hashed files

**Key Functions:**
```python
def hash_file(filepath) -> str:
    """Generate 8-char MD5 hash of file content"""

def get_hashed_filename(original_path) -> str:
    """Convert 'styles.css' to 'styles.47c9f5c8.css'"""

def update_html_references(html_path, hash_mapping, output_path):
    """Update <script>/<link> tags to reference hashed files"""
```

**Dependencies:**
- `hashlib` (built-in)
- `beautifulsoup4` (for HTML parsing)

**Arguments:**
- `--source`: Source directory (default: `src/web/`)
- `--output`: Output temp directory (required)
- `--manifest`: Path to write current filenames list

### 2. Cleanup Script

**File:** `scripts/cleanup_old_assets.py`

**Responsibilities:**
- List all hashed files in S3 bucket
- Parse HTML to find currently referenced files
- Delete orphaned files

**Key Functions:**
```python
def find_hashed_files_in_s3(bucket_name) -> list:
    """Find all files matching *.*.{js,css} pattern"""

def find_current_hashed_files(html_dir) -> set:
    """Parse HTML to find referenced hashed files"""

def cleanup_old_assets(bucket_name, html_dir):
    """Delete old hashed files not in current deployment"""
```

**Pattern Matching:**
- Regex: `r'.+\.[a-f0-9]{8}\.(js|css)$'`
- Matches: `api.a3d8e2f.js`, `styles.47c9f5c.css`
- Ignores: `config.js`, `normalize.css` (non-hashed)

**Dependencies:**
- `boto3` (AWS SDK)
- `beautifulsoup4` (for HTML parsing)

**Arguments:**
- `--bucket`: S3 bucket name (required)
- `--html-dir`: Directory containing HTML files (required)
- `--region`: AWS region (default: `us-east-1`)

### 3. Deploy Script Modifications

**File:** `scripts/deploy.sh`

**Changes after line 121 (after config.js generation):**

```bash
# Fingerprint static assets
echo "Fingerprinting static assets..."
TEMP_DIR=$(mktemp -d)
echo "Using temp directory: $TEMP_DIR"

python scripts/fingerprint_assets.py \
    --source src/web/ \
    --output "$TEMP_DIR" \
    --manifest "$TEMP_DIR/asset-manifest.txt"

if [ $? -ne 0 ]; then
    echo "Error fingerprinting assets"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "Assets fingerprinted successfully!"
```

**Replace S3 upload section (lines 123-129):**

```bash
# Upload web content to S3 with appropriate cache headers
echo "Uploading web content to S3..."

# Upload hashed assets with long cache (1 year, immutable)
echo "Uploading hashed assets with aggressive caching..."
aws s3 sync "$TEMP_DIR/" "s3://$BUCKET_NAME/" \
    --exclude "*.html" \
    --cache-control "public, max-age=31536000, immutable" \
    --region "$REGION"

# Upload HTML files with short cache (5 minutes)
echo "Uploading HTML files with short cache..."
aws s3 sync "$TEMP_DIR/" "s3://$BUCKET_NAME/" \
    --exclude "*" --include "*.html" \
    --cache-control "public, max-age=300, must-revalidate" \
    --region "$REGION"

if [ $? -ne 0 ]; then
    echo "Error uploading web content"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "Web content uploaded successfully!"

# Cleanup old hashed assets from S3
echo "Cleaning up old hashed assets from S3..."
python scripts/cleanup_old_assets.py \
    --bucket "$BUCKET_NAME" \
    --html-dir "$TEMP_DIR" \
    --region "$REGION"

if [ $? -ne 0 ]; then
    echo "Warning: Error cleaning up old assets (non-fatal)"
fi

# Clean up temp directory
echo "Cleaning up temp directory..."
rm -rf "$TEMP_DIR"
```

**CloudFront Invalidation:**
- Keep existing invalidation logic (lines 133-149)
- Only HTML needs invalidation (asset URLs change)
- Could optimize to invalidate only `/*.html` instead of `/*`

## Benefits

### Cache Performance
- **1-year cache for assets** = faster page loads for returning users
- **`immutable` flag** = no revalidation requests (saves bandwidth)
- **Short HTML cache** = quick propagation of updates

### Reliability
- No more cache-related bugs after deployments
- Works with aggressive browser caching (Safari, Chrome, etc.)
- Content-based hashing = same content always has same URL

### Deployment Safety
- Zero downtime (new files uploaded before old deleted)
- Clean local tree (no build artifacts in git)
- Atomic updates (HTML references match deployed assets)

## Trade-offs

### Build Time
- **Added time:** ~5-10 seconds for hashing and uploading
- **Worth it:** Eliminates cache invalidation issues permanently

### S3 Storage
- **Temporary increase:** Old files exist briefly until cleanup
- **Steady state:** Same as current (only current deploy's files)
- **Cost:** Negligible (assets are small, cleanup is fast)

### Complexity
- **Added scripts:** 2 new Python scripts (~200 lines total)
- **Modified scripts:** deploy.sh (add ~40 lines)
- **Maintenance:** Low (scripts are straightforward)

## Testing Plan

### Manual Testing
1. Deploy to dev environment
2. Verify hashed filenames in S3 (e.g., `api.a3d8e2f.js`)
3. Check HTML references updated correctly
4. Test on iPhone Safari (hard refresh, clear cache)
5. Deploy again, verify old hashes cleaned up

### Validation Checks
- [ ] HTML pages load without errors
- [ ] JavaScript functionality works
- [ ] CSS styling correct
- [ ] config.js has correct API endpoints
- [ ] Old hashed files removed from S3
- [ ] Cache headers set correctly (check S3 metadata)

### Rollback Plan
If issues occur:
1. Revert deploy.sh changes
2. Re-deploy with original upload logic
3. CloudFront invalidation clears any problematic cached content

## Future Enhancements

### Potential Improvements
1. **Fingerprint images/fonts** - Extend to all static assets
2. **Source maps** - Generate source maps for debugging production JS
3. **Minification** - Compress JS/CSS before hashing
4. **Separate CDN** - Serve static assets from dedicated CDN/domain
5. **Build manifest API** - Endpoint to query current deployed asset versions

### Not Needed Now (YAGNI)
- Build manifest tracking (we upload everything each deploy)
- Incremental builds (deploy time is already fast)
- Asset bundling (current file structure works fine)

## Dependencies

### Python Packages
```
beautifulsoup4>=4.12.0  # HTML parsing
boto3>=1.28.0           # AWS SDK (already installed)
```

### System Requirements
- Python 3.11+ (already in use)
- AWS CLI (already in use)
- Bash shell (already in use)

## References

- [MDN: HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching)
- [Webpack Content Hashing](https://webpack.js.org/guides/caching/)
- [CloudFront Caching Best Practices](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/ConfiguringCaching.html)
