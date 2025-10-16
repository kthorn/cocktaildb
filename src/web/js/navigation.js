// Navigation configuration and utilities for the Mixology Tools

/**
 * Navigation configuration object
 * This centralizes all navigation items and their properties for different UI contexts
 */
export const NAV_CONFIG = {
  // Primary navigation items - shown in main navigation
  primary: [
    {
      id: 'home',
      label: 'Home',
      href: 'index.html',
      icon: '🏠',
      mobileBottom: true,    // Show in mobile bottom nav
      mobileMenu: true,      // Show in mobile hamburger menu
      desktop: true,         // Show in desktop nav
      authRequired: false,   // No authentication needed
      adminOnly: false
    },
    {
      id: 'search',
      label: 'Search',
      href: 'search.html',
      icon: '🔍',
      mobileBottom: true,
      mobileMenu: true,
      desktop: true,
      authRequired: false,
      adminOnly: false
    },
    {
      id: 'my-ingredients',
      label: 'My Ingredients',
      shortLabel: 'My Bar',   // Shorter label for compact spaces
      href: 'user-ingredients.html',
      icon: '🍸',
      mobileBottom: true,
      mobileMenu: true,
      desktop: true,
      authRequired: true,     // Requires login
      adminOnly: false
    },
    {
      id: 'add-recipe',
      label: 'Add Recipe',
      shortLabel: 'Add',
      href: 'recipes.html',
      icon: '➕',
      mobileBottom: true,
      mobileMenu: true,
      desktop: true,
      authRequired: true,
      adminOnly: false
    }
  ],

  // Secondary navigation items - shown in hamburger menu or dropdown
  secondary: [
    {
      id: 'all-ingredients',
      label: 'All Ingredients',
      href: 'ingredients.html',
      icon: '📋',
      mobileBottom: false,
      mobileMenu: true,
      desktop: true,
      authRequired: false,
      adminOnly: false
    },
    {
      id: 'analytics',
      label: 'Analytics',
      href: 'analytics.html',
      icon: '📊',
      mobileBottom: false,
      mobileMenu: true,
      desktop: true,
      authRequired: false,
      adminOnly: false
    },
    {
      id: 'about',
      label: 'About',
      href: 'about.html',
      icon: 'ℹ️',
      mobileBottom: false,
      mobileMenu: true,
      desktop: true,
      authRequired: false,
      adminOnly: false
    }
  ],

  // Admin navigation items
  admin: [
    {
      id: 'admin',
      label: 'Admin',
      href: 'admin.html',
      icon: '⚙️',
      mobileBottom: false,
      mobileMenu: true,
      desktop: true,
      authRequired: true,
      adminOnly: true
    }
  ]
};

/**
 * Navigation display modes
 */
export const NAV_MODES = {
  MOBILE_BOTTOM: 'mobile-bottom',
  MOBILE_MENU: 'mobile-menu',
  DESKTOP: 'desktop'
};

/**
 * Get navigation items filtered by mode and user context
 * @param {string} mode - One of NAV_MODES
 * @param {Object} options - User context and filtering options
 * @param {boolean} options.isAuthenticated - Whether user is logged in
 * @param {boolean} options.isAdmin - Whether user has admin privileges
 * @param {boolean} options.includeAuthRequired - Include items that require auth (default: true)
 * @returns {Array} Filtered navigation items
 */
export function getNavigationItems(mode, options = {}) {
  const {
    isAuthenticated = false,
    isAdmin = false,
    includeAuthRequired = true
  } = options;

  // Combine all navigation groups
  const allItems = [
    ...NAV_CONFIG.primary,
    ...NAV_CONFIG.secondary,
    ...(isAdmin ? NAV_CONFIG.admin : [])
  ];

  // Filter based on mode and user context
  return allItems.filter(item => {
    // Check if item should be shown in this mode
    let showInMode = false;
    switch (mode) {
      case NAV_MODES.MOBILE_BOTTOM:
        showInMode = item.mobileBottom;
        break;
      case NAV_MODES.MOBILE_MENU:
        showInMode = item.mobileMenu;
        break;
      case NAV_MODES.DESKTOP:
        showInMode = item.desktop;
        break;
      default:
        showInMode = true;
    }

    if (!showInMode) return false;

    // Filter based on authentication
    if (item.authRequired && !isAuthenticated && !includeAuthRequired) {
      return false;
    }

    // Filter admin-only items
    if (item.adminOnly && !isAdmin) {
      return false;
    }

    return true;
  });
}

/**
 * Get the current active page ID based on the current URL
 * @returns {string|null} The ID of the current page or null
 */
export function getCurrentPageId() {
  const currentPage = window.location.pathname.split('/').pop() || 'index.html';

  // Search through all navigation items
  const allItems = [
    ...NAV_CONFIG.primary,
    ...NAV_CONFIG.secondary,
    ...NAV_CONFIG.admin
  ];

  const currentItem = allItems.find(item => item.href === currentPage);
  return currentItem ? currentItem.id : null;
}

/**
 * Get a navigation item by its ID
 * @param {string} id - The item ID
 * @returns {Object|null} The navigation item or null
 */
export function getNavigationItemById(id) {
  const allItems = [
    ...NAV_CONFIG.primary,
    ...NAV_CONFIG.secondary,
    ...NAV_CONFIG.admin
  ];

  return allItems.find(item => item.id === id) || null;
}

/**
 * Check if a navigation item should be highlighted as active
 * @param {Object} item - Navigation item
 * @param {string} currentPageId - Current page ID (optional, will auto-detect)
 * @returns {boolean} True if item should be highlighted
 */
export function isNavItemActive(item, currentPageId = null) {
  const pageId = currentPageId || getCurrentPageId();
  return item.id === pageId;
}

/**
 * Mobile breakpoint detection
 * @returns {boolean} True if current viewport is mobile size
 */
export function isMobileViewport() {
  return window.matchMedia('(max-width: 768px)').matches;
}

/**
 * Get the appropriate label for a navigation item based on available space
 * @param {Object} item - Navigation item
 * @param {boolean} useShortLabel - Whether to use short label if available
 * @returns {string} The label to display
 */
export function getNavLabel(item, useShortLabel = false) {
  if (useShortLabel && item.shortLabel) {
    return item.shortLabel;
  }
  return item.label;
}

/**
 * Navigation event types for custom events
 */
export const NAV_EVENTS = {
  ITEM_CLICKED: 'nav-item-clicked',
  MODE_CHANGED: 'nav-mode-changed',
  MENU_TOGGLED: 'nav-menu-toggled'
};

/**
 * Dispatch a navigation event
 * @param {string} eventType - One of NAV_EVENTS
 * @param {Object} detail - Event detail data
 */
export function dispatchNavEvent(eventType, detail = {}) {
  const event = new CustomEvent(eventType, {
    detail,
    bubbles: true,
    cancelable: true
  });
  document.dispatchEvent(event);
}

/**
 * CSS class names used by navigation components
 */
export const NAV_CLASSES = {
  // Container classes
  MOBILE_BOTTOM: 'nav-mobile-bottom',
  MOBILE_MENU: 'nav-mobile-menu',
  DESKTOP_NAV: 'nav-desktop',

  // State classes
  ACTIVE: 'nav-active',
  DISABLED: 'nav-disabled',
  MENU_OPEN: 'nav-menu-open',

  // Item classes
  NAV_ITEM: 'nav-item',
  NAV_ICON: 'nav-icon',
  NAV_LABEL: 'nav-label',

  // Auth classes
  AUTH_REQUIRED: 'nav-auth-required',
  ADMIN_ONLY: 'nav-admin-only'
};

/**
 * Z-index layering for navigation components
 */
export const NAV_Z_INDEX = {
  MOBILE_BOTTOM: 1000,
  MOBILE_MENU: 1100,
  MOBILE_MENU_OVERLAY: 1050,
  DESKTOP_NAV: 100
};

/**
 * Animation durations (in milliseconds)
 */
export const NAV_ANIMATIONS = {
  MENU_SLIDE: 300,
  FADE: 200,
  QUICK: 150
};
