# Navigation Redesign - Design Document

**Status:** Approved for Implementation
**Date:** 2025-10-15
**Related:** docs/navigation.md (recommendations)

---

## Executive Summary

Comprehensive redesign of the navigation system to improve mobile UX, implement authentication-aware menus, and separate content browsing from content editing capabilities.

---

## Architecture Overview

### Core Components

The new navigation system consists of:

1. **MobileNavigation** - Bottom bar (3-4 core items) + hamburger menu (secondary features)
2. **DesktopNavigation** - Horizontal top nav with dropdowns + user menu
3. **NavigationController** - Orchestrates component rendering based on viewport size

### Technology Stack

- **Module:** `src/web/js/navigation.js` (new file)
- **Integration:** Replaces header generation in `common.js`
- **Styling:** Consolidated section in `styles.css`
- **Dependencies:** Existing `auth.js` for authentication state

### Responsive Breakpoints

- **Mobile:** < 768px - Bottom nav + hamburger menu
- **Tablet:** 768-1024px - Mobile layout (simplified scope)
- **Desktop:** > 1024px - Horizontal nav with dropdowns

---

## Navigation Configuration

### User Roles

| Role | Description | Check Method |
|------|-------------|--------------|
| Guest | Unauthenticated visitor | `!api.isAuthenticated()` |
| User | Authenticated, can track bar/rate/tag | `api.isAuthenticated()` |
| Editor | Can create/edit recipes and ingredients | `api.isEditor()` (includes admin) |
| Admin | Full system access | `api.isAdmin()` |

### Mobile Navigation Structure

#### Bottom Navigation Bar (Always Visible)

**Guest Users (3 items):**
- 🏠 Home
- 🔍 Search
- 📊 Explore

**Authenticated Users (4 items):**
- 🏠 Home
- 🔍 Search
- 📊 Explore
- 📦 My Bar

#### Hamburger Menu (Overlay)

**All Users:**
- Browse Ingredients
- About

**Divider (if editor)**

**Editor/Admin Only:**
- ➕ Add Recipe
- ➕ Add Ingredient

**Divider (if admin)**

**Admin Only:**
- 🔧 Admin

### Desktop Navigation Structure

#### Top Horizontal Nav

**Primary Items (Always Visible):**
- Home
- Search
- Explore ▼ (dropdown: Visualization)
- Ingredients ▼ (dropdown: Browse All, My Bar*)

**Editor/Admin Only:**
- Create ▼ (dropdown: Add Recipe, Add Ingredient)

*Requires authentication

#### User Menu (Top Right)

**Authenticated Users:**
- ⚙️ Settings (disabled/placeholder)
- 🚪 Log Out

**Admin Users (additional):**
- 🔧 Admin (link to admin dashboard)

---

## Configuration Object Structure

```javascript
const NAV_CONFIG = {
  mobile: {
    bottomNav: [
      { id: 'home', label: 'Home', url: 'index.html', icon: '🏠' },
      { id: 'search', label: 'Search', url: 'search.html', icon: '🔍' },
      { id: 'explore', label: 'Explore', url: 'analytics.html', icon: '📊' },
      { id: 'mybar', label: 'My Bar', url: 'user-ingredients.html', icon: '📦', requireAuth: true }
    ],
    hamburgerMenu: {
      items: [
        { id: 'all-ingredients', label: 'Browse Ingredients', url: 'ingredients.html' },
        { id: 'about', label: 'About', url: 'about.html' },
        { id: 'divider-1', type: 'divider', requireEditor: true },
        { id: 'add-recipe', label: '➕ Add Recipe', url: 'recipes.html', requireEditor: true },
        { id: 'add-ingredient', label: '➕ Add Ingredient', url: 'ingredients.html?mode=edit', requireEditor: true },
        { id: 'divider-2', type: 'divider', requireAdmin: true },
        { id: 'admin', label: '🔧 Admin', url: 'admin.html', requireAdmin: true }
      ]
    }
  },
  desktop: {
    topNav: [
      { id: 'home', label: 'Home', url: 'index.html' },
      { id: 'search', label: 'Search', url: 'search.html' },
      {
        id: 'explore',
        label: 'Explore',
        dropdown: [
          { label: 'Visualization', url: 'analytics.html' }
        ]
      },
      {
        id: 'ingredients',
        label: 'Ingredients',
        dropdown: [
          { label: 'Browse All', url: 'ingredients.html' },
          { label: 'My Bar', url: 'user-ingredients.html', requireAuth: true }
        ]
      },
      {
        id: 'create',
        label: 'Create',
        requireEditor: true,
        dropdown: [
          { label: 'Add Recipe', url: 'recipes.html' },
          { label: 'Add Ingredient', url: 'ingredients.html?mode=edit' }
        ]
      }
    ],
    userMenu: {
      authenticated: [
        { id: 'settings', label: '⚙️ Settings', url: '#', disabled: true },
        { id: 'logout', label: '🚪 Log Out', action: 'logout' }
      ],
      admin: [
        { id: 'admin', label: '🔧 Admin', url: 'admin.html' }
      ]
    }
  }
};
```

---

## Component Lifecycle

### Initialization (Page Load)

1. `NavigationController.init()` detects viewport size
2. Subscribes to auth state changes
3. Renders appropriate navigation component (mobile or desktop)
4. Attaches event listeners
5. Highlights active page

### Auth State Changes

1. Auth module triggers callback
2. `NavigationController.refresh()` called
3. Menu items updated based on new auth state
4. No full page reload required

### Viewport Resize (Debounced, 250ms)

1. Detect breakpoint crossing (mobile ↔ desktop)
2. Destroy current navigation
3. Render new navigation for current viewport
4. Preserve active page state

---

## Key Interactions

### Mobile Hamburger Menu

**Behavior:**
- Tap hamburger icon → full-screen overlay slides in from top
- Tap outside overlay or close button → menu slides out
- Tap menu item → navigate to page, close menu
- Menu stacks vertically with adequate spacing (44px touch targets)

**Animation:**
- Slide down from top (300ms ease-out)
- Semi-transparent backdrop (rgba(0,0,0,0.5))

### Desktop Dropdowns

**Behavior:**
- Hover over nav item with dropdown → dropdown appears below
- Click dropdown item → navigate to page
- Mouse leave dropdown → dropdown closes after 200ms delay
- Keyboard navigation: Tab to focus, Enter to open, Arrow keys to navigate

**Animation:**
- Fade in (150ms)
- No jarring movements

### Bottom Navigation Bar (Mobile)

**Behavior:**
- Fixed position at bottom of viewport
- Always visible (z-index: 100)
- Main content has `padding-bottom` to prevent overlap
- Active page highlighted with different background color

---

## Authentication Integration

### Role Checking

```javascript
// Check if item should be visible
function shouldShowItem(item) {
  if (item.requireAdmin) return api.isAdmin();
  if (item.requireEditor) return api.isEditor();
  if (item.requireAuth) return api.isAuthenticated();
  return true; // Public item
}
```

### Real-Time Updates

```javascript
// Subscribe to auth state changes
function onAuthStateChange() {
  const wasAuthenticated = lastAuthState;
  const isAuthenticated = api.isAuthenticated();

  if (wasAuthenticated !== isAuthenticated) {
    NavigationController.refresh();
  }

  lastAuthState = isAuthenticated;
}

// Check periodically for token expiration
setInterval(onAuthStateChange, 30000);
```

---

## Active Page Highlighting

```javascript
// Detect current page
const currentPage = window.location.pathname.split('/').pop() || 'index.html';

// Add 'active' class to matching items
navItems.forEach(item => {
  if (item.url === currentPage ||
      (item.url === 'index.html' && currentPage === '')) {
    item.element.classList.add('active');
  }
});
```

**Styles:**
- Desktop: Bold text + underline
- Mobile bottom nav: Highlighted background + bolder icon
- Mobile hamburger: Highlighted background

---

## Error Handling

### Token Expiration
- Gracefully hide auth-required items
- Show login prompt if user tries to access protected page

### Role Changes
- User promoted to editor sees new menu items immediately on next page load
- Handled by token refresh (JWT contains updated groups)

### Network Failures
- Navigation remains functional offline
- Menu rendering is client-side only

### Missing Pages
- All URLs validated during testing
- 404 handling by web server

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Deep link to auth-required page | Redirect to login, preserve destination in URL param |
| Viewport resize during dropdown | Close dropdowns before switching layouts |
| Hamburger open during orientation change | Close menu, re-render for new layout |
| Bottom nav overlapping content | `<main>` has `padding-bottom: 70px` on mobile |
| Rapid login/logout | Debounce auth state changes (500ms) |

---

## CSS Organization

### New Styles Section

Add to `styles.css`:

```css
/* ==========================================================================
   NAVIGATION REDESIGN
   ========================================================================== */

/* Mobile Bottom Navigation */
.bottom-nav { /* ... */ }
.bottom-nav-item { /* ... */ }

/* Mobile Hamburger Menu */
.hamburger-button { /* ... */ }
.hamburger-overlay { /* ... */ }
.hamburger-menu { /* ... */ }

/* Desktop Navigation */
.desktop-nav { /* ... */ }
.desktop-nav-dropdown { /* ... */ }
.user-menu { /* ... */ }

/* Responsive Breakpoints */
@media (max-width: 768px) { /* ... */ }
@media (min-width: 769px) { /* ... */ }
```

### Touch Target Requirements

- All interactive elements: **minimum 44x44px**
- Comfortable target: **48x48px** (use for primary actions)
- Spacing between targets: **minimum 8px**

### Accessibility Requirements

- Focus indicators: **3px solid outline**
- Color contrast: **WCAG AA minimum (4.5:1)**
- Focus management: Trap focus in overlays

---

## Testing Strategy

### Manual Testing

**Viewport Testing:**
- Mobile: iPhone SE, iPhone 14 Pro, Pixel 5
- Tablet: iPad, iPad Pro
- Desktop: 1024px, 1440px, 1920px

**Role Testing:**
- [ ] Guest user sees: Home, Search, Explore, Browse Ingredients, About
- [ ] Authenticated user sees: + My Bar
- [ ] Editor sees: + Add Recipe, Add Ingredient
- [ ] Admin sees: + Admin panel

**Interaction Testing:**
- [ ] Hamburger menu opens/closes correctly
- [ ] Dropdowns open on hover, close on mouse leave
- [ ] Bottom nav stays fixed at bottom
- [ ] Active page highlighted correctly
- [ ] Login/logout updates menu immediately

**Keyboard Testing:**
- [ ] Tab through all nav items
- [ ] Enter activates links
- [ ] Escape closes overlays
- [ ] Arrow keys navigate dropdowns

**Touch Testing:**
- [ ] All buttons tappable with thumb
- [ ] No accidental taps
- [ ] Swipe gestures don't interfere

### Integration Testing

- [ ] Navigation works on all pages
- [ ] Deep linking preserves auth redirects
- [ ] Page transitions don't break nav state
- [ ] Auth token expiration handled gracefully

### Accessibility Testing

- [ ] Screen reader announces all nav items
- [ ] ARIA labels present for icon-only buttons
- [ ] Focus indicators visible
- [ ] Color contrast meets WCAG AA
- [ ] Keyboard navigation complete

---

## Performance Considerations

- **Debounce resize events:** 250ms
- **Throttle scroll events:** 100ms (if implementing scroll-based behaviors)
- **CSS transitions:** Keep under 300ms for smooth feel
- **DOM manipulation:** Minimize re-renders on auth state changes
- **Module loading:** Use ES6 modules (non-blocking)

---

## Implementation Dependencies

### Required Files

- [x] `src/web/js/api.js` - Already has `isEditor()` and `isAdmin()`
- [x] `src/web/js/auth.js` - Already has `isAuthenticated()` and `getUserInfo()`
- [x] `src/web/styles.css` - Needs new navigation styles added
- [ ] `src/web/js/navigation.js` - **NEW FILE** (to be created)

### Required Changes

- [ ] `src/web/js/common.js` - Replace `loadHeader()` to call new navigation module
- [ ] `src/web/js/ingredients.js` - Support `?mode=edit` URL parameter for editor mode
- [ ] `src/web/styles.css` - Add navigation styles and mobile padding-bottom

---

## Local Testing Requirements

**Note:** Local testing infrastructure needs improvement.

### Current State
- No documented local server setup
- Testing primarily done via SAM deployment to dev stack

### Required for Navigation Testing
- Local static file server (e.g., Python http.server, live-server, etc.)
- Mock authentication state for role testing
- Hot reload for rapid CSS/JS iteration

### Recommended Setup Task
- Create local development server tooling
- Document setup in docs/local-development.md
- Add npm scripts for common dev tasks

---

## Terminology Changes

| Old Term | New Term | Reason |
|----------|----------|--------|
| Analytics | Explore | Less technical, clearer purpose |
| My Ingredients | My Bar | More personality, bartender terminology |
| Add Recipes | Add Recipe | Singular action (adding one recipe) |
| All Ingredients | Browse Ingredients | Clearer that it's read-only |
| Manage Ingredients | Add Ingredient | Clearer editor action (when in edit mode) |

---

## Future Enhancements (Not in Scope)

- Gesture navigation (swipe between sections)
- Skeleton loading states
- Keyboard shortcuts (e.g., `/` for search)
- Breadcrumbs for deep navigation
- Search autocomplete in header
- Recently viewed recipes
- Mega-menu for Explore section with multiple viz types

---

## References

- Original recommendations: `docs/navigation.md`
- Current navigation: `src/web/js/common.js:36-69`
- Auth system: `src/web/js/auth.js`, `src/web/js/api.js:282-327`
- Existing editor pattern: `src/web/js/ingredients.js:140-149`
