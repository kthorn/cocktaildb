# UI Standardization Phase 1: CSS Refactoring Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Refactor styles.css to create a clean, maintainable foundation with CSS variables for all sizing, spacing, and design tokens.

**Architecture:** Extract magic numbers into semantic CSS variables, consolidate duplicate rules, organize into logical sections, remove dead code. This creates a maintainable foundation for implementing WCAG standards and mobile optimization.

**Tech Stack:** CSS3 custom properties (variables), vanilla CSS

**Scope:** This addresses bd-28 (Simplify and refactor CSS) and prepares the foundation for bd-31, bd-33, bd-34, bd-26, bd-29, bd-32, bd-30, bd-27.

---

## Task 1: Evaluate CSS Reset Strategy

**Files:**
- Read: `src/web/styles.css:1-6` (current reset)
- Read: All HTML files to understand browser support needs

**Step 1: Review current minimal reset**

The current CSS has a minimal reset (lines 1-6):
```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}
```

**Step 2: Consider alternatives**

Three options:

**Option A: Keep minimal reset**
- Pros: Lightweight (3 rules), no dependencies, already working
- Cons: Inconsistent rendering across browsers, missing modern defaults

**Option B: Add normalize.css**
- Pros: Cross-browser consistency, widely adopted, preserves useful defaults
- Cons: 400+ lines, some rules we might not need
- Implementation: Link to CDN or add to project

**Option C: Add modern-normalize**
- Pros: Modern browsers only, smaller than normalize (150 lines), opinionated improvements
- Cons: Drops IE support (but we may not need it)
- Implementation: npm install or copy file

**Step 3: Recommendation**

For this project, **Option C: modern-normalize** is recommended because:
1. The application is modern (FastAPI, CloudFront, vanilla JS)
2. Mobile optimization is a priority (modern-normalize handles mobile better)
3. Smaller footprint than normalize.css
4. Sets good defaults for forms, which we're heavily refactoring

**Step 4: Implement modern-normalize**

Download modern-normalize and add to project:

```bash
cd /home/kurtt/cocktaildb/.worktrees/ui-standardization
curl -o src/web/normalize.css https://cdn.jsdelivr.net/npm/modern-normalize@2.0.0/modern-normalize.css
```

**Step 5: Update HTML files to include normalize**

Add to `<head>` of all HTML files BEFORE styles.css:

```html
<link rel="stylesheet" href="normalize.css">
<link rel="stylesheet" href="styles.css">
```

Files to update:
- src/web/index.html
- src/web/recipes.html
- src/web/search.html
- src/web/ingredients.html
- src/web/analytics.html
- src/web/recipe.html
- src/web/user-ingredients.html
- src/web/admin.html
- src/web/about.html
- src/web/login.html
- src/web/logout.html
- src/web/callback.html

**Step 6: Remove redundant reset from styles.css**

Remove lines 1-6 from styles.css since modern-normalize handles this better.

**Step 7: Test all pages**

Open each page and verify:
- No visual regressions
- Forms look correct
- Typography is consistent

**Step 8: Commit CSS reset**

```bash
git add src/web/normalize.css src/web/*.html src/web/styles.css
git commit -m "feat: add modern-normalize CSS reset

Replace minimal CSS reset with modern-normalize for better cross-browser
consistency and modern defaults.

- Adds modern-normalize 2.0.0 for consistent baseline
- Removes redundant manual reset from styles.css
- Updates all HTML files to include normalize before styles

Part of bd-28: CSS refactoring foundation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Alternative: Keep minimal reset**

If you prefer to keep the lightweight approach and avoid adding dependencies:
- Document the decision in a comment at the top of styles.css
- Note which browsers are supported
- Skip to Task 2

---

## Task 2: Audit Current CSS Variables

**Files:**
- Read: `src/web/styles.css:1-60` (existing :root section)

**Step 1: Document existing CSS variables**

Create audit document to track what variables exist and what's missing:

```bash
cd /home/kurtt/cocktaildb/.worktrees/ui-standardization
mkdir -p docs/audits
```

**Step 2: Extract current variable usage**

Read the :root section and list all existing variables. Document in audit file:

```markdown
# CSS Variables Audit

## Existing Variables (lines 8-60)
- Colors: --primary-color, --secondary-color, --accent-color, etc.
- Spacing: --space-xs through --space-xl
- Text sizes: --text-xs through --text-xxl
- Border radius: --radius-sm through --radius-round
- Shadows: --shadow-sm, --shadow-md, --shadow-lg

## Missing Variables Needed
- Touch target sizes (44px minimum for WCAG 2.5.5)
- Form input heights (44px minimum)
- Mobile viewport padding (16-20px)
- Line heights for typography
- Focus indicator styles
```

**Step 3: Scan CSS for magic numbers**

Use grep to find all hardcoded pixel values that should be variables:

```bash
grep -n "px" src/web/styles.css | grep -v "var(--" | head -50
```

Expected: List of lines with hardcoded values like `padding: 12px`, `height: 32px`, etc.

**Step 4: Create comprehensive variable plan**

Document which new variables are needed based on the grep results and WCAG requirements.

**Step 5: Commit audit**

```bash
git add docs/audits/
git commit -m "docs: audit CSS variables for refactoring

Document existing variables and identify magic numbers that need
to be extracted into semantic CSS variables.

Part of bd-28: CSS refactoring foundation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Add Missing CSS Variables for Touch Targets and Forms

**Files:**
- Modify: `src/web/styles.css:8-60` (:root section)

**Step 1: Add touch target and form variables**

Add new variables to :root section after existing spacing variables:

```css
    /* Touch targets (WCAG 2.5.5) */
    --touch-target-min: 44px;
    --touch-target-comfortable: 48px;

    /* Form elements */
    --form-input-height-min: 44px;
    --form-input-padding: 0.75rem 1rem;
    --form-input-font-size: 16px;  /* Prevents iOS zoom on focus */

    /* Mobile viewport */
    --mobile-padding: 16px;
    --mobile-padding-comfortable: 20px;

    /* Line heights for typography */
    --line-height-tight: 1.2;
    --line-height-normal: 1.5;
    --line-height-relaxed: 1.8;

    /* Focus indicators */
    --focus-outline-width: 3px;
    --focus-outline-color: var(--accent-color);
    --focus-outline-offset: 2px;
```

**Step 2: Verify syntax**

Open a browser and check if CSS parses correctly. Look for any syntax errors in console.

**Step 3: Commit new variables**

```bash
git add src/web/styles.css
git commit -m "feat: add CSS variables for WCAG and mobile standards

Add touch target, form input, mobile padding, line height, and focus
indicator variables to prepare for implementation.

- Touch targets: 44px minimum per WCAG 2.5.5
- Form inputs: 44px height, 16px font (prevents iOS zoom)
- Mobile padding: 16-20px range
- Line heights: 1.2/1.5/1.8 for typography hierarchy
- Focus indicators: 3px outline for WCAG 2.4.7

Part of bd-28: CSS refactoring foundation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Consolidate Button Styles

**Files:**
- Modify: `src/web/styles.css:212-309` (button styles section)

**Step 1: Identify button duplication**

Read lines 212-309 and identify duplicate patterns:
- Base button styles (button, .btn)
- Variants (.btn-primary, .btn-secondary, .btn-success, .btn-danger)
- Sizes (.btn-small, .btn-circle)
- States (.btn-outline, .btn-outline-danger)

**Step 2: Create consolidated button base**

Replace scattered button rules with consolidated base:

```css
/* Button base - consolidated */
button, .btn {
    background-color: var(--accent-color);
    color: white;
    border: none;
    padding: var(--space-sm) var(--space-md);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: var(--text-md);
    min-height: var(--touch-target-min);
    min-width: var(--touch-target-min);
    transition: background-color 0.3s, transform 0.1s;
}

button:hover, .btn:hover {
    background-color: var(--accent-hover);
    transform: translateY(-1px);
}

button:active, .btn:active {
    transform: translateY(0);
}

button:disabled, .btn:disabled {
    background-color: var(--secondary-color);
    cursor: not-allowed;
    opacity: 0.6;
}
```

**Step 3: Update button variants to use inheritance**

Simplify variants to only specify what differs:

```css
/* Button variants - only specify differences */
.btn-primary {
    background-color: var(--primary-color);
}

.btn-primary:hover {
    background-color: #1a2530;
}

.btn-secondary {
    background-color: var(--secondary-color);
}

.btn-secondary:hover {
    background-color: #666e6f;
}

.btn-success {
    background-color: var(--success-color);
}

.btn-success:hover {
    background-color: var(--success-hover);
}

.btn-danger {
    background-color: var(--danger-color);
}

.btn-danger:hover {
    background-color: var(--danger-hover);
}
```

**Step 4: Test button appearance**

Open any HTML page with buttons (recipes.html, search.html) and verify:
- All buttons render correctly
- Hover states work
- Minimum touch target size applied
- No visual regressions

**Step 5: Commit button consolidation**

```bash
git add src/web/styles.css
git commit -m "refactor: consolidate button styles and add touch targets

Consolidate duplicate button CSS rules into base + variants pattern.
Add minimum touch target size (44px) to all buttons.

- Base button inherits common properties
- Variants only specify differences
- All buttons now meet WCAG 2.5.5 touch target minimum
- Removed ~60 lines of duplicate CSS

Part of bd-28: CSS refactoring.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Consolidate Form Input Styles

**Files:**
- Modify: `src/web/styles.css:196-210` (input styles)

**Step 1: Replace hardcoded input sizing**

Update input styles to use new variables:

```css
/* Input styles consolidated */
input[type="text"],
input[type="number"],
input[type="email"],
input[type="password"],
select,
textarea {
    width: 100%;
    padding: var(--form-input-padding);
    min-height: var(--form-input-height-min);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-sm);
    font-size: var(--form-input-font-size);
    line-height: var(--line-height-normal);
    transition: border-color 0.2s, box-shadow 0.2s;
}

input:focus,
select:focus,
textarea:focus {
    outline: var(--focus-outline-width) solid var(--focus-outline-color);
    outline-offset: var(--focus-outline-offset);
    border-color: var(--accent-color);
}

textarea {
    resize: vertical;
    min-height: calc(var(--form-input-height-min) * 2);
}
```

**Step 2: Test form inputs**

Open pages with forms (recipes.html for recipe creation, search.html) and verify:
- Inputs are at least 44px tall
- Font is 16px (prevents iOS zoom)
- Focus indicators are visible
- No visual regressions

**Step 3: Commit form input consolidation**

```bash
git add src/web/styles.css
git commit -m "refactor: consolidate form input styles with WCAG standards

Consolidate form input CSS and apply accessibility standards.

- Minimum height 44px (WCAG 2.5.5)
- Font size 16px (prevents mobile browser zoom)
- Line height 1.5 (WCAG 1.4.8)
- Visible focus indicators (WCAG 2.4.7)

Part of bd-28: CSS refactoring.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Organize CSS into Logical Sections

**Files:**
- Modify: `src/web/styles.css:1-2430` (entire file)

**Step 1: Create section headers**

Add clear section headers throughout the file to organize rules:

```css
/* ==========================================================================
   1. RESET & BASE STYLES
   ========================================================================== */

/* ==========================================================================
   2. CSS VARIABLES (:root)
   ========================================================================== */

/* ==========================================================================
   3. TYPOGRAPHY
   ========================================================================== */

/* ==========================================================================
   4. LAYOUT (Header, Nav, Main, Footer)
   ========================================================================== */

/* ==========================================================================
   5. COMPONENTS (Cards, Buttons, Forms)
   ========================================================================== */

/* ==========================================================================
   6. UTILITIES (Hidden, Loading, etc.)
   ========================================================================== */

/* ==========================================================================
   7. ANIMATIONS
   ========================================================================== */

/* ==========================================================================
   8. RESPONSIVE (Media Queries)
   ========================================================================== */
```

**Step 2: Reorganize rules into sections**

Move rules into their appropriate sections. Current structure is somewhat organized but can be improved.

**Step 3: Add subsection comments**

Within each major section, add subsection comments:

```css
/* ==========================================================================
   5. COMPONENTS
   ========================================================================== */

/* Buttons
   ========================================================================== */

/* Forms
   ========================================================================== */

/* Cards
   ========================================================================== */

/* Modals
   ========================================================================== */
```

**Step 4: Verify no rules were lost**

Do a line count before/after to ensure all rules are preserved:

```bash
# Before reorganization
grep -c "^[^/].*{" src/web/styles.css

# After reorganization (should be same number)
grep -c "^[^/].*{" src/web/styles.css
```

**Step 5: Test all pages**

Quickly check each HTML page to ensure styling is unchanged:
- index.html
- recipes.html
- search.html
- ingredients.html
- analytics.html

**Step 6: Commit organization**

```bash
git add src/web/styles.css
git commit -m "refactor: organize CSS into logical sections

Add clear section headers and reorganize rules for maintainability.

Sections:
1. Reset & Base Styles
2. CSS Variables
3. Typography
4. Layout
5. Components
6. Utilities
7. Animations
8. Responsive

No visual changes, pure organization for easier maintenance.

Part of bd-28: CSS refactoring.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Extract Hardcoded Spacing Values

**Files:**
- Modify: `src/web/styles.css` (various locations with hardcoded spacing)

**Step 1: Find hardcoded spacing values**

```bash
grep -n "padding: [0-9]" src/web/styles.css | grep -v "var(--"
grep -n "margin: [0-9]" src/web/styles.css | grep -v "var(--"
```

**Step 2: Replace with CSS variables**

For each hardcoded value, replace with appropriate variable:
- `padding: 12px` → `padding: var(--space-sm)`
- `padding: 16px` → `padding: var(--space-md)`
- `padding: 24px` → `padding: var(--space-lg)`
- `margin: 8px` → `margin: var(--space-sm)`

**Step 3: Handle special cases**

Some spacing might not fit existing variables. For those:
- If it's 44px (touch target), use `var(--touch-target-min)`
- If it's 16px for mobile, use `var(--mobile-padding)`
- If truly unique, add a semantic variable to :root

**Step 4: Verify visual consistency**

Check all pages to ensure spacing looks correct after variable substitution.

**Step 5: Commit spacing extraction**

```bash
git add src/web/styles.css
git commit -m "refactor: replace hardcoded spacing with CSS variables

Replace magic number spacing values with semantic CSS variables
for consistency and maintainability.

Part of bd-28: CSS refactoring.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Remove Dead CSS (Unused Classes)

**Files:**
- Read: `src/web/*.html` (all HTML files)
- Modify: `src/web/styles.css`

**Step 1: Extract all CSS class selectors**

```bash
grep -o "\.[a-zA-Z0-9_-]*" src/web/styles.css | sort -u > /tmp/css-classes.txt
```

**Step 2: Extract all HTML class usage**

```bash
grep -oh 'class="[^"]*"' src/web/*.html | sed 's/class="//g' | sed 's/"//g' | tr ' ' '\n' | sort -u > /tmp/html-classes.txt
```

**Step 3: Find unused classes**

```bash
comm -23 /tmp/css-classes.txt /tmp/html-classes.txt > /tmp/unused-classes.txt
```

**Step 4: Review unused classes**

Manually review the list. Some classes might be:
- Added dynamically by JavaScript (keep these)
- Actually unused (safe to remove)
- Used in other files like JavaScript (check before removing)

**Step 5: Remove confirmed unused classes**

Carefully remove CSS rules for truly unused classes. Document what was removed.

**Step 6: Test all pages**

Verify no visual regressions after removing unused CSS.

**Step 7: Commit dead code removal**

```bash
git add src/web/styles.css
git commit -m "refactor: remove unused CSS classes

Remove CSS classes that aren't used in any HTML or JavaScript files.

Removed classes: [list removed classes]
Lines reduced: ~[number]

Part of bd-28: CSS refactoring.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Document CSS Architecture

**Files:**
- Create: `docs/css-architecture.md`

**Step 1: Create architecture documentation**

```markdown
# CSS Architecture

## Overview

The CocktailDB CSS follows a component-based architecture with CSS custom properties (variables) for design tokens.

## File Structure

- `src/web/styles.css` - Single stylesheet with organized sections

## CSS Variables

All design tokens are defined in `:root` for consistency:

### Sizing & Spacing
- `--touch-target-min`: 44px (WCAG 2.5.5 minimum)
- `--form-input-height-min`: 44px
- `--space-xs` through `--space-xl`: Standard spacing scale
- `--mobile-padding`: 16px minimum for mobile viewports

### Typography
- `--text-xs` through `--text-xxl`: Font size scale
- `--line-height-tight/normal/relaxed`: Line height standards

### Colors
- `--primary-color`, `--secondary-color`, `--accent-color`
- `--success-color`, `--danger-color`, `--info-color`, `--warn-color`
- `--text-dark/medium/light`: Text color hierarchy
- `--bg-light`, `--bg-white`: Background colors

### Focus & Accessibility
- `--focus-outline-width`: 3px
- `--focus-outline-color`: Links to accent color
- `--focus-outline-offset`: 2px

## Component Patterns

### Buttons
Base styles in `button, .btn` with variant classes for different purposes.
All buttons meet 44px touch target minimum.

### Forms
Input elements use consistent height (44px) and 16px font size to prevent mobile zoom.

### Cards
Recipe and ingredient cards share base styles with specific overrides.

## Mobile-First Approach

Media query at 768px breakpoint handles mobile-specific adjustments.
Mobile padding enforced via `--mobile-padding` variable.

## WCAG Compliance

- Touch targets: 44x44px minimum (WCAG 2.5.5)
- Focus indicators: 3px visible outline (WCAG 2.4.7)
- Line height: 1.5 minimum for body text (WCAG 1.4.8)
- Color contrast: Validated separately (WCAG 1.4.3)
```

**Step 2: Commit documentation**

```bash
git add docs/css-architecture.md
git commit -m "docs: add CSS architecture documentation

Document CSS variable system, component patterns, and WCAG compliance
approach for future maintainers.

Part of bd-28: CSS refactoring.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Update Beads Issue Status

**Files:**
- N/A (command-line only)

**Step 1: Mark bd-28 as completed**

```bash
bd update bd-28 --status closed
```

**Step 2: Verify closure**

```bash
bd show bd-28
```

Expected: Status should show "closed"

**Step 3: Check epic progress**

```bash
bd show bd-25
```

Expected: Should show 1 of 9 tasks completed (bd-28)

---

## Completion Checklist

- [ ] CSS reset strategy evaluated and implemented
- [ ] CSS variables audited
- [ ] CSS variables added for touch targets, forms, mobile, typography, focus
- [ ] Button styles consolidated (base + variants)
- [ ] Form input styles consolidated with WCAG standards
- [ ] CSS organized into clear sections
- [ ] Hardcoded spacing replaced with variables
- [ ] Dead CSS classes removed
- [ ] Architecture documented
- [ ] All pages tested for visual regressions
- [ ] bd-28 marked as closed

## Next Phase

After completing bd-28, proceed to Phase 2:
- bd-31: Implement proper typography standards
- bd-33: Ensure mobile viewport padding

Use this same worktree and continue building on the refactored CSS foundation.
