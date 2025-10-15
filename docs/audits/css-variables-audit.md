# CSS Variables Audit

**Date:** 2025-10-15
**Purpose:** Audit existing CSS variables and identify hardcoded magic numbers that need to be extracted into semantic CSS variables.

## Executive Summary

- **Existing CSS Variables:** 28 variables defined in :root (lines 2-54)
- **Hardcoded Pixel Values Found:** 158 instances
- **Files Audited:** src/web/styles.css (2425 lines)

## Existing Variables (lines 2-54)

### Color Palette (14 variables)
- `--primary-color: #2c3e50`
- `--secondary-color: #7f8c8d`
- `--accent-color: #A61816`
- `--accent-hover: #8A1412`
- `--success-color: #4CAF50`
- `--success-hover: #388E3C`
- `--danger-color: #F44336`
- `--danger-hover: #d32f2f`
- `--info-color: #2196F3`
- `--warn-color: #ffc107`
- `--text-dark: #333`
- `--text-medium: #555`
- `--text-light: #777`
- `--bg-light: #f5f5f5`

### Background Colors (3 variables)
- `--bg-white: #fff`
- `--bg-light-hover: #e9ecef`

### Border Colors (2 variables)
- `--border-light: #ddd`
- `--border-lighter: #eee`

### Spacing (5 variables)
- `--space-xs: 0.25rem` (4px)
- `--space-sm: 0.5rem` (8px)
- `--space-md: 1rem` (16px)
- `--space-lg: 1.5rem` (24px)
- `--space-xl: 2rem` (32px)

### Font Sizes (6 variables)
- `--text-xs: 0.8rem`
- `--text-sm: 0.9rem`
- `--text-md: 1rem`
- `--text-lg: 1.2rem`
- `--text-xl: 1.4rem`
- `--text-xxl: 1.6rem`

### Border Radius (4 variables)
- `--radius-sm: 4px`
- `--radius-md: 8px`
- `--radius-lg: 12px`
- `--radius-round: 50%`

### Shadows (3 variables)
- `--shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.1)`
- `--shadow-md: 0 2px 8px rgba(0, 0, 0, 0.08)`
- `--shadow-lg: 0 5px 15px rgba(0, 0, 0, 0.2)`

## Missing Variables Needed

### Touch Targets & Accessibility (WCAG 2.5.5)
**Not defined** - Need minimum touch target sizes:
- Touch target minimum: 44px (WCAG 2.5.5 requirement)
- Touch target comfortable: 48px (recommended)

### Form Elements
**Not defined** - Need consistent form input sizing:
- Form input height minimum: 44px (accessibility + touch target)
- Form input padding: consistent padding for all inputs
- Form input font size: 16px (prevents iOS zoom on focus)

### Mobile Viewport
**Not defined** - Need mobile-specific spacing:
- Mobile padding: 16px minimum
- Mobile padding comfortable: 20px

### Typography Line Heights
**Not defined** - Need semantic line heights:
- Line height tight: 1.2 (headings)
- Line height normal: 1.5 (body text, WCAG 1.4.8)
- Line height relaxed: 1.8 (long-form content)

### Focus Indicators (WCAG 2.4.7)
**Not defined** - Need visible focus indicators:
- Focus outline width: 3px
- Focus outline color: should reference accent-color
- Focus outline offset: 2px

## Hardcoded Magic Numbers Found

### High-Priority Issues (Accessibility & Touch Targets)

**Button & Interactive Element Sizing:**
- Line 285-286: `.btn-circle` width/height 32px (below WCAG minimum)
- Line 656: `.tag-input-wrapper` min-height 40px (below WCAG minimum)
- Line 1022-1023: `.loading-spinner` 16px (decorative, OK)
- Line 1428-1429: `.carousel-arrow` 50px (above minimum, good)
- Line 1562: `.tag-chips-container` min-height 40px (below minimum)
- Line 1808-1809: Mobile `.carousel-arrow` 40px (below minimum)
- Line 2361-2362: `.modal-close` 32px (below minimum)

**Form Input Heights:**
- Line 196: `input[type="text"]` padding 0.35rem (inconsistent)
- No explicit min-height set for inputs (should be 44px)

**Mobile Padding:**
- Line 1758: `.results-section` padding 0 1rem (16px, OK)
- Line 1804: `.carousel-container` padding 1rem 0 (inconsistent)
- Line 2036: `.analytics-container` padding 2rem (32px)
- Line 2289: Mobile `.analytics-container` padding 1rem (16px)

### Medium-Priority Issues (Layout & Spacing)

**Container Max-Widths:**
- Line 138: `main` max-width 1200px
- Line 1496: `#recipe-display .recipe-card` max-width 600px
- Line 1524: `.modal-content` max-width 480px
- Line 2033: `.analytics-container` max-width 1200px
- Line 2341: `.modal-content` max-width 600px

**Grid & Flex Layouts:**
- Line 162: Grid columns `minmax(300px, 1fr)`
- Line 803: `.ingredient-fields` flex 0 0 100px
- Line 807: `.ingredient-fields` flex 0 0 150px
- Line 946: `.item-row-field-fixed` flex 0 0 140px
- Line 970: `.form-actions` width 120px
- Line 1178: Section header input min-width 200px
- Line 1185-1186: `.ingredients-list` min-height 300px, max-height 500px
- Line 1793: Mobile form actions button max-width 150px

**Padding & Margins:**
- Line 299: `.btn-icon` margin-right 5px (should use --space-xs)
- Line 301: `.btn-icon` font-size 16px
- Line 513: `.add-tag-btn` padding 3px 8px
- Line 541: `.tag-chip` padding 2px 8px
- Line 571: `.tag-remove-btn` margin 0 0 0 2px
- Line 857: `.autocomplete-item` padding 8px 12px
- Line 880: `.auth-controls button` padding 5px 10px
- Line 886: `.auth-controls button` margin-left 10px
- Line 903: `#username` margin-right 10px
- Line 908-909: `.notification` padding 12px 15px, margin-bottom 20px
- Line 1310: `.rating-count` margin-left 5px
- Line 1314: `.rating-stats` margin-left 8px
- Line 1390: `.rating-notification` padding 4px 8px
- Line 1393: `.rating-notification` margin-left 8px
- Line 1922: `.ingredient-tree-row` padding 4px 8px
- Line 1923: `.ingredient-tree-row` margin-bottom 2px

**Border & Shadow Values:**
- Line 249: `.btn-outline` border 1px solid
- Line 259: `.btn-outline-danger` border 1px solid
- Line 317: Custom shadow `0 4px 12px rgba(0, 0, 0, 0.12)`
- Line 326: Border-bottom 1px solid
- Line 345: Height 2px (decorative border)
- Line 436: Border-top 1px solid
- Line 515: `.add-tag-btn` border 1px solid
- Line 516: `.add-tag-btn` border-radius 12px
- Line 542: `.tag-chip` border-radius 12px
- Line 546: `.tag-chip` border 1px solid
- Line 548: Gap 4px (should use spacing variable)
- Line 667: Custom shadow `0 0 0 2px rgba(166, 24, 22, 0.1)`
- Line 737: Custom shadow `0 2px 8px rgba(0, 0, 0, 0.1)`
- Line 851: Custom shadow `0 2px 6px rgba(0, 0, 0, 0.15)`
- Line 914: Custom shadow `0 2px 5px rgba(0, 0, 0, 0.2)`
- Line 1024: `.loading-spinner` border 2px solid
- Line 1160: Custom shadow `0 2px 4px rgba(0, 0, 0, 0.1)`
- Line 1188: Custom shadow `0 2px 4px rgba(0, 0, 0, 0.1)`
- Line 1436: Custom shadow `0 2px 5px rgba(0, 0, 0, 0.2)`
- Line 1522: `.modal-content` border 1px solid
- Line 1559: `.tag-chips-container` border 1px solid
- Line 1560: `.tag-chips-container` border-radius 6px
- Line 1569: `.tag-chip` border-radius 14px
- Line 1573: `.tag-chip` border 1px solid
- Line 1668: `.existing-tag-btn` border 1px solid

**Positioning & Transform:**
- Line 1011: Right 10px
- Line 1033: Margin-top 4px
- Line 1105: Margin-right 2px
- Line 1279-1280: `.toast` top 20px, right 20px
- Line 1345: Gap 2px
- Line 1533-1534: `.close-tag-modal-btn` top 8px, right 12px
- Line 1535: Font-size 24px
- Line 1578: Transform translateY(-1px)
- Line 1666: Gap 4px
- Line 1667: Padding 4px 8px
- Line 1680: Transform translateY(-1px)
- Line 1695: Font-size 10px
- Line 1725: Transform translateY(-20px)
- Line 1740: Transform translateY(20px)

**Heights & Max-Heights:**
- Line 588: `.tags-management-list` max-height 400px
- Line 734: `.tag-suggestions-dropdown` max-height 200px
- Line 846: `.autocomplete-dropdown` max-height 200px
- Line 1043: `.results-section` min-height 150px
- Line 1048: `#search-results-container` min-height 200px
- Line 1061: `.empty-message` min-height 120px
- Line 1416: `.carousel-content` min-height 400px
- Line 1459: `.loading-placeholder` min-height 120px
- Line 1639: `#existing-tags-section` max-height 300px
- Line 1862: `.progress-bar` height 8px
- Line 2124: `.chart-container` min-height 400px
- Line 2129-2130: `.chart-area` min-height 400px
- Line 2139: `.loading-state` min-height 300px
- Line 2148-2150: `.spinner` 40px x 40px, border 4px
- Line 2371: `#recipe-modal-body` min-height 200px
- Line 2412: `#cocktail-space-chart` min-height 650px

### Low-Priority Issues (Fine-tuning)

**Media Query Breakpoint:**
- Line 1750: `@media (max-width: 768px)` - should be a variable
- Line 2287: `@media (max-width: 768px)` - duplicate breakpoint

**Various Small Values:**
- Line 1695: Font-size 10px (very small text)
- Line 1956: `.tree-toggle` margin-right 6px
- Line 1957: Min-width 16px
- Line 2232: `.legend-color` 20px x 12px

## Recommendations

### Phase 1: Add Missing Critical Variables (WCAG & Touch Targets)
1. Touch target variables (44px minimum, 48px comfortable)
2. Form input variables (height, padding, font-size)
3. Mobile viewport padding (16-20px)
4. Line height variables (1.2, 1.5, 1.8)
5. Focus indicator variables (3px width, color, 2px offset)

### Phase 2: Extract Hardcoded Spacing
Replace all hardcoded pixel spacing with existing spacing variables:
- 2px → --space-xs (0.25rem = 4px) or create --space-xxs: 0.125rem (2px)
- 4px → --space-xs (0.25rem)
- 5px → closest to --space-xs
- 8px → --space-sm (0.5rem)
- 10px → closest to --space-sm
- 12px → between --space-sm and --space-md, may need --space-base: 0.75rem
- 16px → --space-md (1rem)
- 20px → closest to --space-lg or create --space-md-lg: 1.25rem
- 24px → --space-lg (1.5rem)
- 32px → --space-xl (2rem)

### Phase 3: Consolidate Custom Shadows
Replace one-off shadow values with existing shadow variables or create new semantic shadows:
- Existing: --shadow-sm, --shadow-md, --shadow-lg
- Need: --shadow-focus (for focus indicators)
- Custom shadows at lines 317, 667, 737, 851, 914, 1160, 1188, 1436

### Phase 4: Create Layout Variables
Add variables for commonly repeated layout values:
- Container max-widths (600px, 1200px)
- Grid column minimums (300px)
- Form field widths (100px, 120px, 140px, 150px, 200px)
- Media query breakpoint (768px)

### Phase 5: Border Radius Consolidation
Review custom border-radius values:
- 2px, 4px (--radius-sm exists)
- 6px (between sm and md)
- 8px (--radius-md exists)
- 12px, 14px (--radius-lg is 12px)
- Consider adding --radius-pill: 999px for pill-shaped elements

## Files Requiring Updates

1. **src/web/styles.css** - Add new variables to :root section (lines 2-54)
2. **src/web/styles.css** - Replace hardcoded values throughout entire file (158 instances)

## Impact Assessment

**Accessibility Impact:** HIGH
- Buttons and interactive elements below 44px minimum will be fixed
- Focus indicators will be standardized and visible
- Form inputs will meet WCAG height requirements

**Maintainability Impact:** HIGH
- Single source of truth for all sizing values
- Easy to adjust touch targets across entire application
- Simplified theming and design system changes

**Performance Impact:** NONE
- CSS variables are performant in modern browsers
- No JavaScript required for variable substitution

## Next Steps

1. ✅ **Task 2 Complete:** Audit documented
2. **Task 3:** Add missing CSS variables to :root
3. **Task 4:** Consolidate button styles with new variables
4. **Task 5:** Consolidate form input styles with new variables
5. **Task 6:** Organize CSS into logical sections
6. **Task 7:** Extract hardcoded spacing values
7. **Task 8:** Remove dead CSS (unused classes)

## Notes

- Current styles.css has 2425 lines
- Well-organized existing variable system
- Most colors and typography already use variables
- Main issues are sizing, spacing, and accessibility touch targets
- CSS reset is minimal (box-sizing only)
- File shows recent modifications to header/nav sections
