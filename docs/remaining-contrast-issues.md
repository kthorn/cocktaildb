# Remaining Color Contrast Issues (WCAG AA)

After fixing critical interactive elements in bd-30, these contrast issues remain. They are lower priority because they affect less critical elements or have acceptable reasons for reduced contrast.

## Issues by Category

### 1. Secondary Button (3.48:1 - needs 4.5:1)
**Current**: White on #7f8c8d (gray)
**Where**: Reset button (search form), Cancel button (tag modal)
**Status**: ACCEPTABLE - These are intentionally de-emphasized secondary actions
**Fix if needed**: Darken to #5c6668 (4.5:1)

### 2. Placeholder Text (2.85:1 - needs 4.5:1)
**Current**: #999 on white backgrounds
**Where**: Form input placeholders
**Status**: ACCEPTABLE - WCAG specifically allows reduced contrast for placeholder text
**Note**: Placeholder text is not considered "text content" under WCAG 2.1

### 3. Disabled Text (4.45:1 - needs 4.5:1)
**Current**: #6c757d on #f8f9fa
**Where**: Disabled form elements, inactive states
**Status**: NEARLY COMPLIANT - Only 0.05 short of requirement
**WCAG Exception**: Disabled controls have relaxed contrast requirements
**Fix if needed**: Change bg to #f5f5f5 or text to #656565

### 4. Info Color - Decorative Uses (3.12:1 - needs 4.5:1)
**Current**: #2196F3 on white
**Where**:
- Stat card numbers (styles.css:397) - Large text, decorative
- Autocomplete highlighting (styles.css:955) - Supplementary
- Tag type labels (styles.css:1193) - Supplementary badges
**Status**: ACCEPTABLE - These are:
  - Large text (stat cards) = only needs 3:1 for WCAG AA Large
  - Non-text content (badges)
  - Supplementary information (autocomplete)
**Fix if needed**: Darken to #0d6eab (4.5:1)

### 5. Tab Active Color (3.12:1 - needs 4.5:1)
**Current**: white on #2196F3
**Where**: Active tab text (analytics page)
**Status**: NEEDS VERIFICATION - Actually uses #1f77b4, not #2196F3
**Action**: Check actual usage, may already be compliant
**Fix if needed**: Darken background or make text bold instead of color change

### 6. Link Colors (3.12:1 - needs 4.5:1)
**Current**: #2196F3 on white
**Where**: Hyperlinks in content (about page, recipe sources)
**Status**: NEEDS FIX for content links
**Fix**: Darken to #0d6eab (4.5:1) for body text links
**Note**: Browser default link colors may override this

### 7. Light Text (2.85:1 - needs 4.5:1)
**Current**: #999 on white and #f8f9fa backgrounds
**Where**: --text-light variable, de-emphasized supplementary text
**Status**: ACCEPTABLE - Intentional visual hierarchy for non-essential info
**Examples**: Timestamps, metadata, helper text
**Fix if needed**: Change to #777 (4.6:1) but may lose hierarchy effect

### 8. Error Text (3.57:1 - needs 4.5:1)
**Current**: #e74c3c on #fff5f5
**Where**: Error messages on light pink background
**Status**: SHOULD FIX for accessibility
**Fix**: Darken text to #c7392a (4.5:1) OR darken background to #ffe8e6

### 9. Star Ratings (1.36:1 and 1.63:1 - needs 4.5:1)
**Current**:
- Empty stars: #ddd on white (1.36:1)
- Filled stars: #ffc107 (yellow) on white (1.63:1)
**Where**: Recipe rating displays
**Status**: QUESTIONABLE - Stars may be considered:
  - Graphical objects (need only 3:1 under WCAG 2.1 1.4.11)
  - Part of text (need 4.5:1)
**Action**: Need design decision - are stars decorative or informational?
**Options**:
  1. Keep as-is if considered decorative + text label provides info
  2. Darken empty to #a0a0a0, filled to #c79100 (4.5:1)
  3. Use filled/outlined icons instead of color for state

## Prioritization Recommendations

### High Priority (Should Fix)
1. **Error text** - Important user feedback
2. **Content links** - Navigation and references

### Medium Priority (Review & Decide)
1. **Tab active color** - Verify actual implementation
2. **Star ratings** - Determine if decorative or informational

### Low Priority (Acceptable As-Is)
1. Placeholder text - WCAG allows reduced contrast
2. Disabled text - Nearly compliant, disabled controls excepted
3. Light text - Intentional hierarchy
4. Secondary button - Appropriately de-emphasized
5. Info color badges - Supplementary, non-essential

### Not Required
1. Large stat numbers using info color - Only need 3:1 for large text

## Testing Approach

When fixing these issues:
1. Run contrast checker: `python3 /tmp/check_contrast.py`
2. Visual review on actual devices
3. Test with screen readers if changing semantic elements
4. Verify visual hierarchy is maintained

## Related Issues
- bd-30: Fixed critical interactive element contrast (closed)
- bd-25: Parent epic for UI standardization

## References
- WCAG 2.1 Level AA: 4.5:1 for normal text, 3:1 for large text
- Large text defined as: 18pt+ or 14pt+ bold
- Exceptions: Placeholder text, disabled controls, decorative content
