# Frontend Screenshot Tool

Automated screenshot capture for visual testing and documentation of frontend changes across multiple viewports.

---

## Quick Start

```bash
# 1. Install system dependencies (one-time)
sudo playwright install-deps

# 2. Start local server
./scripts/local-config.sh
./scripts/serve.sh

# 3. Capture screenshots (in another terminal)
./scripts/screenshot.sh
```

---

## Prerequisites

### System Dependencies (Required)

Playwright requires system libraries to run Chromium. Install them once:

```bash
# Automated install (recommended)
sudo playwright install-deps

# Manual install (if above fails)
sudo apt-get install libnspr4 libnss3 libasound2t64 \
    libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
    libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 \
    libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
    libxrandr2
```

### Python Dependencies (Already Installed)

- `playwright` - Browser automation library
- Installed via: `pip install playwright`
- Browser binaries: `playwright install chromium`

---

## Usage

### Basic Screenshot Capture

```bash
# Capture all pages at default viewports (mobile, tablet, desktop)
./scripts/screenshot.sh

# Capture specific pages
./scripts/screenshot.sh --pages index.html search.html

# Capture at specific viewports
./scripts/screenshot.sh --viewports mobile desktop

# Custom output directory
./scripts/screenshot.sh --output screenshots/nav-redesign
```

### Available Viewports

| Viewport | Resolution | Device |
|----------|-----------|--------|
| `mobile` | 375x667 | iPhone SE |
| `mobile-large` | 414x896 | iPhone XR |
| `tablet` | 768x1024 | iPad Portrait |
| `tablet-landscape` | 1024x768 | iPad Landscape |
| `desktop` | 1280x720 | Desktop |
| `desktop-large` | 1920x1080 | Large Desktop |

### Default Pages

Screenshots are captured for these pages by default:
- Home (`index.html`)
- Search (`search.html`)
- Explore/Analytics (`analytics.html`)
- Browse Ingredients (`ingredients.html`)
- My Bar (`user-ingredients.html`)
- About (`about.html`)

---

## Common Workflows

### Before/After Comparison for Navigation Redesign

```bash
# 1. Capture "before" screenshots
./scripts/serve.sh &
./scripts/screenshot.sh --output screenshots/before

# 2. Make navigation changes

# 3. Restart server and capture "after" screenshots
# Kill server: Ctrl+C or pkill -f "python3 -m http.server"
./scripts/serve.sh &
./scripts/screenshot.sh --output screenshots/after

# 4. Compare visually or use image diff tools
```

### Testing Specific Component

```bash
# Capture just the page you're working on
./scripts/screenshot.sh --pages search.html --viewports mobile tablet desktop

# Capture with all viewports for thorough testing
./scripts/screenshot.sh --pages search.html --viewports mobile mobile-large tablet tablet-landscape desktop desktop-large
```

### Testing Responsive Design

```bash
# Capture at all viewports
./scripts/screenshot.sh --viewports mobile mobile-large tablet tablet-landscape desktop desktop-large

# Focus on mobile and tablet breakpoints
./scripts/screenshot.sh --viewports mobile tablet tablet-landscape
```

---

## Script Options

### Full Command Reference

```bash
python3 scripts/screenshot.py [OPTIONS]

Options:
  --url URL                Base URL (default: http://localhost:8000)
  --output DIR, -o DIR     Output directory (default: screenshots/)
  --pages PAGE [PAGE...]   Specific pages to capture (default: all)
  --viewports VP [VP...]   Viewports to capture (default: mobile tablet desktop)
  --headless               Run browser in headless mode (default)
  --no-headless            Show browser window while capturing
  -h, --help               Show help message
```

### Examples

```bash
# Capture home page at all viewports
python3 scripts/screenshot.py --pages index.html --viewports mobile mobile-large tablet tablet-landscape desktop desktop-large

# Capture with custom server URL
python3 scripts/screenshot.py --url http://localhost:3000

# Watch browser while capturing (debugging)
python3 scripts/screenshot.py --no-headless --pages index.html --viewports desktop

# Capture navigation pages only
python3 scripts/screenshot.py --pages index.html search.html analytics.html ingredients.html
```

---

## Output

### Filename Format

Screenshots are saved with this naming pattern:
```
{page-name}_{viewport}_{timestamp}.png
```

**Example:**
```
home_mobile_20251016_143052.png
home_desktop_20251016_143053.png
search_tablet_20251016_143054.png
```

### Directory Structure

```
screenshots/
├── home_mobile_20251016_143052.png
├── home_tablet_20251016_143052.png
├── home_desktop_20251016_143053.png
├── search_mobile_20251016_143054.png
├── search_tablet_20251016_143054.png
└── search_desktop_20251016_143055.png
```

---

## Integration with Development Workflow

### For Navigation Redesign (bd-42, bd-43, bd-44, bd-45)

1. **Capture baseline:**
   ```bash
   ./scripts/screenshot.sh --output screenshots/before-nav
   ```

2. **Implement changes** (create navigation.js, update styles.css, etc.)

3. **Capture after changes:**
   ```bash
   ./scripts/screenshot.sh --output screenshots/after-nav
   ```

4. **Visual review:**
   - Compare before/after screenshots
   - Verify responsive behavior
   - Check all user states (guest, authenticated, editor, admin)

5. **Document in PR:**
   - Include screenshots in pull request
   - Show before/after comparisons
   - Highlight key improvements

### For Testing User Roles

Since screenshots capture the page as-is, you need to manually set authentication state:

1. **Guest user:** Start server without logging in, capture screenshots
2. **Authenticated user:** Log in via browser, then capture screenshots (cookies persist)
3. **Editor user:** Log in with editor account, capture screenshots

**Note:** For now, authentication state must be set manually in browser. Future enhancement could automate this with Playwright authentication.

---

## Troubleshooting

### Problem: Missing system dependencies

```
BrowserType.launch: Host system is missing dependencies
```

**Solution:**
```bash
sudo playwright install-deps
```

### Problem: Server not responding

```
Error: net::ERR_CONNECTION_REFUSED at http://localhost:8000
```

**Solution:**
```bash
# Check if server is running
lsof -i :8000

# Start server if not running
./scripts/serve.sh
```

### Problem: Permission denied

```
PermissionError: [Errno 13] Permission denied: 'screenshots/'
```

**Solution:**
```bash
# Create directory with correct permissions
mkdir -p screenshots
chmod 755 screenshots
```

### Problem: Slow screenshot capture

**Cause:** Full-page screenshots of long pages (like analytics) take time.

**Solutions:**
- Use `--pages` to capture specific pages
- Use specific viewports instead of all
- Screenshots are already optimized (networkidle, minimal wait time)

---

## Advanced Usage

### Automated Visual Regression Testing (Future)

Can be integrated with image comparison tools:

```bash
# Capture baseline
./scripts/screenshot.sh --output screenshots/baseline

# Make changes and capture new screenshots
./scripts/screenshot.sh --output screenshots/current

# Compare with tools like pixelmatch, looks-same, or Percy
npm install -g looks-same
looks-same screenshots/baseline/home_desktop_*.png screenshots/current/home_desktop_*.png
```

### CI/CD Integration (Future)

```yaml
# .github/workflows/visual-tests.yml
- name: Setup local server
  run: |
    ./scripts/local-config.sh
    ./scripts/serve.sh &

- name: Capture screenshots
  run: ./scripts/screenshot.sh --output screenshots/pr-${{ github.event.number }}

- name: Upload artifacts
  uses: actions/upload-artifact@v3
  with:
    name: screenshots
    path: screenshots/
```

---

## Performance Notes

- **Headless mode:** Faster, no GUI overhead (default)
- **Headed mode:** Slower, useful for debugging (`--no-headless`)
- **Full-page screenshots:** Captures entire scrollable page (may be large for analytics page)
- **Network idle:** Waits for network requests to complete before capturing
- **Typical timing:** ~2-3 seconds per screenshot

---

## Related Documentation

- [Local Development Guide](./local-development.md) - Setting up local server
- [Navigation Design](./navigation-design.md) - Navigation redesign specs
- [Testing Guide](../TESTING.md) - General testing documentation

---

## Quick Reference

```bash
# Essential Commands
./scripts/screenshot.sh                                    # Capture all pages, default viewports
./scripts/screenshot.sh --pages index.html                # Capture specific page
./scripts/screenshot.sh --viewports mobile desktop        # Capture specific viewports
./scripts/screenshot.sh --output screenshots/my-feature   # Custom output directory

# System Setup (one-time)
sudo playwright install-deps                              # Install browser dependencies

# Check Output
ls screenshots/                                           # List captured screenshots
open screenshots/home_desktop_*.png                       # View screenshot (macOS)
xdg-open screenshots/home_desktop_*.png                   # View screenshot (Linux)
```
