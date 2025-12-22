# Responsive Web Design - Technical Standards

## Typography Minimums
- **Body text: 16px (1rem) minimum**
  - While WCAG does not specify a minimum font size, 16px for body text is widely recommended as a starting point [1][2]
  - Penn State Accessibility recommends 12pt (16px) for body text on traditional computer monitors [3]

- **Line height: 1.5 for body text, 1.2-1.3 for headings**
  - Industry standard for readability

- **Max line length: 65-75 characters (use max-width: 65ch on text containers)**
  - Optimal readability standard

- **Font stack:** `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`

## Touch Targets & Interaction
- **All clickable elements: minimum 44x44px**
  - WCAG 2.5.5 (Level AAA) requires touch targets to be at least 44 by 44 CSS pixels [4]
  - Apple's iOS Human Interface Guidelines recommend a minimum target size of 44×44 points [5][6]
  - Google's Material Design recommends at least 48×48 density-independent pixels [5]

- **Spacing between touch targets: minimum 8px**
  - Prevents accidental activation of adjacent targets

- **Form inputs: minimum 44px height**
  - Ensures easy interaction on touch devices

## Spacing & Layout
- **Mobile viewport padding: 16-20px minimum on sides**
  - Prevents content from touching screen edges

- **Desktop max content width: 1200-1400px**
  - Maintains comfortable reading line length

- **Use rem/em units for scalability, not fixed px**
  - WCAG recommends scalable text that users can resize up to 200% using standard browser features [1]

## Breakpoints (Standard)
- Mobile: < 768px
- Tablet: 768px - 1024px  
- Desktop: > 1024px

## Accessibility Requirements
- **Color contrast:**
  - WCAG 2.0 Level AA requires 4.5:1 for normal text and 3:1 for large text (18pt/24px or 14pt bold) [7][8]
  - WCAG Level AAA requires 7:1 for normal text and 4.5:1 for large text [7]
  - Tool: [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)

- **Focus indicators:** visible on all interactive elements

- **Skip to main content link** for keyboard users

## Performance
- Images: always include width/height attributes
- Use srcset for responsive images
- Lazy load images below the fold

## CSS Foundation
```css
/* Apply to all projects */
*, *::before, *::after { box-sizing: border-box; }
body { font-size: 1rem; line-height: 1.5; }
img { max-width: 100%; height: auto; display: block; }
```

## References

[1] A11Y Collective - "How to Pick the Perfect Font Size: A Guide to WCAG Accessibility"  
https://www.a11y-collective.com/blog/wcag-minimum-font-size/

[2] Accessible Web - "Minimum font size?"  
https://accessibleweb.com/question-answer/minimum-font-size/

[3] Penn State Accessibility - "Font Size on the Web"  
https://accessibility.psu.edu/fontsizehtml/

[4] W3C WCAG 2.1 - "Understanding Success Criterion 2.5.5: Target Size"  
https://www.w3.org/WAI/WCAG21/Understanding/target-size.html

[5] LogRocket - "All accessible touch target sizes"  
https://blog.logrocket.com/ux-design/all-accessible-touch-target-sizes/

[6] TetraLogical - "Foundations: target sizes"  
https://tetralogical.com/blog/2022/12/20/foundations-target-size/

[7] WebAIM - "Contrast and Color Accessibility"  
https://webaim.org/articles/contrast/

[8] W3C WCAG 2.1 - "Understanding Success Criterion 1.4.3: Contrast (Minimum)"  
https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html

## Additional Resources
- **WCAG 2.1/2.2:** https://www.w3.org/WAI/WCAG21/
- **Apple Human Interface Guidelines:** https://developer.apple.com/design/human-interface-guidelines
- **Material Design:** https://m3.material.io/
- **Normalize.css:** https://necolas.github.io/normalize.css/