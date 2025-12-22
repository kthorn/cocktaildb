# Local Development Setup

Guide for testing frontend changes locally without deploying to AWS.

---

## Quick Start

```bash
# 1. Generate local config (points to dev API)
./scripts/local-config.sh

# 2. Start local server
./scripts/serve.sh

# 3. Open browser
# Navigate to: http://localhost:8000
```

---

## Prerequisites

### Required
- **Python 3.x** - For local HTTP server (already installed in conda environment)
- **AWS CLI** - Configured with credentials to access dev stack
- **Access to dev stack** - `cocktail-db-dev` CloudFormation stack

### Optional
- **Node.js & npm** - For enhanced live-reload server (already installed)

---

## Setup Scripts

### 1. Generate Local Config

**Script:** `scripts/local-config.sh`

**Purpose:** Generates `src/web/js/config.js` configured for local development

**What it does:**
- Fetches API endpoint from dev CloudFormation stack
- Fetches Cognito configuration from dev stack
- Generates config.js with `appUrl: 'http://localhost:8000'`
- Backend API requests still go to dev environment

**Usage:**
```bash
# Use default dev stack
./scripts/local-config.sh

# Use specific stack
./scripts/local-config.sh cocktail-db-custom
```

**Output:**
```javascript
const config = {
    apiUrl: 'https://[dev-api].execute-api.us-east-1.amazonaws.com/api',
    userPoolId: 'us-east-1_XXX',
    clientId: 'XXXXX',
    cognitoDomain: 'https://[dev-domain]',
    appUrl: 'http://localhost:8000',  // ← Local server
    appName: 'Cocktail Database (local dev)'
};
```

**⚠️ Important:** Don't commit the generated config.js to git!

---

### 2. Start Local Server

**Script:** `scripts/serve.sh`

**Purpose:** Serves static files from `src/web/` on localhost

**What it does:**
- Checks that config.js exists and is configured for local dev
- Starts Python's built-in HTTP server
- Serves all static files (HTML, CSS, JS, images)
- No hot-reload (manual page refresh needed)

**Usage:**
```bash
# Start server on default port (8000)
./scripts/serve.sh

# Start on custom port
./scripts/serve.sh 3000
```

**Stopping the server:**
- Press `Ctrl+C` to stop

---

## Development Workflow

### Initial Setup (once)
```bash
./scripts/local-config.sh
```

### Daily Development Loop
```bash
# 1. Start server (leave running in terminal)
./scripts/serve.sh

# 2. Open browser
open http://localhost:8000

# 3. Edit files (HTML, CSS, JS)
# 4. Refresh browser to see changes
# 5. Iterate

# When done: Ctrl+C to stop server
```

### Before Committing
```bash
# Regenerate production config
python3 scripts/generate_config.py cocktail-db-prod prod

# OR restore from git
git checkout src/web/js/config.js
```

---

## Enhanced Development (Optional)

### Live-Reload with live-server

**Benefits:**
- Automatic browser refresh on file changes
- Faster iteration
- Better DX

**Setup:**
```bash
# Install globally (one-time)
npm install -g live-server

# Or use without installing
npx live-server src/web --port=8000
```

**Usage:**
```bash
# From project root
npx live-server src/web --port=8000 --open=/index.html

# Or add to scripts/serve.sh as an alternative
```

**Configuration (optional):**

Create `.vscode/settings.json` for VS Code users:
```json
{
  "liveServer.settings.port": 8000,
  "liveServer.settings.root": "/src/web"
}
```

---

## Architecture

### Local vs Deployed

| Component | Local Dev | Deployed |
|-----------|-----------|----------|
| Frontend (HTML/CSS/JS) | http://localhost:8000 | CloudFront |
| Backend API | Dev stack (AWS) | Dev/Prod stack (AWS) |
| Authentication | Dev Cognito | Dev/Prod Cognito |
| Database | Dev EFS SQLite | Dev/Prod EFS SQLite |
| Static Assets | Local filesystem | S3 + CloudFront |

### Request Flow (Local Dev)

```
Browser (localhost:8000)
    ↓
Local HTTP Server (Python)
    ↓
Static Files (HTML/CSS/JS)
    ↓
JavaScript API calls
    ↓
Dev Backend API (AWS)
    ↓
Dev Database (EFS SQLite)
```

### Authentication Flow (Local Dev)

```
Browser (localhost:8000)
    ↓
Click "Login"
    ↓
Redirect to Dev Cognito Hosted UI
    ↓
User logs in
    ↓
Redirect back to http://localhost:8000/callback.html
    ↓
Tokens stored in localStorage
    ↓
API calls include auth tokens
```

**Note:** You must configure `http://localhost:8000` as a valid callback URL in Cognito if it's not already set.

---

## Troubleshooting

### Problem: `config.js not found`
**Solution:** Run `./scripts/local-config.sh` first

### Problem: `aws: command not found`
**Solution:** Install AWS CLI or run `conda activate cocktaildb`

### Problem: `Stack not found` error
**Solution:**
- Verify stack name: `aws cloudformation list-stacks --query 'StackSummaries[?contains(StackName, `cocktail`)].StackName'`
- Use correct stack name as argument

### Problem: Authentication redirect fails
**Solution:**
- Check Cognito User Pool → App Client → Callback URLs
- Add `http://localhost:8000/callback.html` if missing
- Update via AWS Console or CloudFormation template

### Problem: CORS errors from API
**Solution:**
- Dev API should already allow CORS from any origin
- Check API Gateway CORS settings if issues persist
- Verify OPTIONS requests succeed in browser dev tools

### Problem: Changes not visible
**Solution:**
- Hard refresh browser: `Ctrl+Shift+R` (Linux/Windows) or `Cmd+Shift+R` (Mac)
- Clear browser cache
- Check that you're editing files in `src/web/`, not a build directory

### Problem: Port already in use
**Solution:**
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
./scripts/serve.sh 3000
```

---

## Testing Navigation Changes

### Setup for Navigation Testing

1. **Start local server:**
   ```bash
   ./scripts/local-config.sh
   ./scripts/serve.sh
   ```

2. **Test as different user roles:**
   - Guest: Don't log in
   - User: Log in with regular test account
   - Editor: Log in with editor/admin test account

3. **Test different viewports:**
   - Desktop: Browser at full width
   - Tablet: Resize to ~768px-1024px
   - Mobile: Resize to <768px or use browser dev tools device emulation

### What to Test

- [ ] Navigation renders correctly on all viewports
- [ ] Menu items appear/disappear based on auth state
- [ ] Dropdowns work (desktop)
- [ ] Hamburger menu works (mobile)
- [ ] Active page is highlighted
- [ ] Touch targets are 44px minimum (mobile)
- [ ] Keyboard navigation works
- [ ] Screen reader compatibility

---

## Advanced Configuration

### Custom API Endpoint

Edit `scripts/local-config.sh` to hardcode a specific API:

```bash
API_URL="https://custom-api.example.com/api"
```

### Mock Authentication (Future)

For testing without Cognito:

```javascript
// In config.js, add:
mockAuth: true,

// Then in auth.js, check for mockAuth and skip real Cognito
```

### Local API (Advanced)

To run the backend API locally:

1. **Install FastAPI dependencies:**
   ```bash
   pip install fastapi uvicorn
   ```

2. **Run API locally:**
   ```bash
   cd api
   uvicorn main:app --reload --port 8080
   ```

3. **Update config:**
   ```javascript
   apiUrl: 'http://localhost:8080/api'
   ```

4. **Handle Cognito auth:** You'll need to mock or proxy auth tokens

---

## Git Best Practices

### .gitignore Updates (Recommended)

Add to `.gitignore`:
```
# Local development config
src/web/js/config.local.js
```

### Pre-commit Hook (Future)

Prevent committing local config:

```bash
#!/bin/bash
# .git/hooks/pre-commit

if git diff --cached --name-only | grep -q "src/web/js/config.js"; then
    if grep -q "localhost" "src/web/js/config.js"; then
        echo "❌ Error: Attempting to commit local dev config!"
        echo "Run: git checkout src/web/js/config.js"
        exit 1
    fi
fi
```

---

## Visual Testing with Screenshots

Automated screenshot capture is available for visual testing and documentation:

```bash
# Install system dependencies (one-time)
sudo playwright install-deps

# Capture screenshots at multiple viewports
./scripts/screenshot.sh

# Capture specific pages
./scripts/screenshot.sh --pages index.html search.html

# Custom output directory
./scripts/screenshot.sh --output screenshots/before-nav
```

**Use cases:**
- Before/after comparisons for UI changes
- Testing responsive design
- Documenting navigation redesign
- Visual regression testing

See [docs/screenshots.md](./screenshots.md) for detailed usage and troubleshooting.

## Future Enhancements

- [ ] Hot-reload with file watchers
- [ ] Auto-generate config on server start
- [ ] Mock authentication mode
- [ ] Local API development guide
- [ ] VS Code launch configurations
- [ ] npm scripts for common tasks
- [ ] Docker-based local environment
- [x] Automated screenshot capture (implemented)
- [ ] Automated visual regression testing

---

## Related Documentation

- [Navigation Design](./navigation-design.md) - Navigation redesign spec
- [CLAUDE.md](../CLAUDE.md) - General project documentation
- [Navigation Recommendations](./navigation.md) - Original UX recommendations

---

## Quick Reference

### Commands
```bash
# Setup
./scripts/local-config.sh                    # Generate local config
./scripts/serve.sh                           # Start server on port 8000
./scripts/serve.sh 3000                      # Start server on port 3000

# Alternative with live-reload
npx live-server src/web --port=8000         # Start with hot-reload

# Restore production config
git checkout src/web/js/config.js           # Reset config

# Check what's running
lsof -i :8000                                # Check if port is in use
```

### URLs
- **Local:** http://localhost:8000
- **Dev:** https://[dev-cloudfront].cloudfront.net
- **Prod:** https://mixology.tools

### File Locations
- **Config template:** `scripts/local-config.sh`
- **Server script:** `scripts/serve.sh`
- **Generated config:** `src/web/js/config.js` (don't commit!)
- **Static files:** `src/web/`
