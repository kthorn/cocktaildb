// Mobile Bottom Navigation Component
import {
  NAV_CONFIG,
  NAV_MODES,
  NAV_CLASSES,
  getNavigationItems,
  getCurrentPageId,
  isNavItemActive,
  getNavLabel,
  dispatchNavEvent,
  NAV_EVENTS
} from './navigation.js';

/**
 * Renders and manages the mobile bottom navigation bar
 */
export class MobileBottomNav {
  constructor() {
    this.container = null;
    this.isAuthenticated = false;
    this.isAdmin = false;
  }

  /**
   * Initialize the mobile bottom navigation
   * @param {Object} options - Configuration options
   * @param {boolean} options.isAuthenticated - Whether user is logged in
   * @param {boolean} options.isAdmin - Whether user has admin privileges
   */
  init(options = {}) {
    this.isAuthenticated = options.isAuthenticated || false;
    this.isAdmin = options.isAdmin || false;

    // Create and insert the navigation
    this.render();

    // Listen for auth changes
    document.addEventListener('auth-state-changed', (e) => {
      this.updateAuthState(e.detail);
    });
  }

  /**
   * Update authentication state and re-render
   * @param {Object} authState - New authentication state
   */
  updateAuthState(authState) {
    this.isAuthenticated = authState.isAuthenticated || false;
    this.isAdmin = authState.isAdmin || false;
    this.render();
  }

  /**
   * Render the mobile bottom navigation
   */
  render() {
    // Remove existing navigation if present
    if (this.container) {
      this.container.remove();
    }

    // Get navigation items for mobile bottom view
    const navItems = getNavigationItems(NAV_MODES.MOBILE_BOTTOM, {
      isAuthenticated: this.isAuthenticated,
      isAdmin: this.isAdmin,
      includeAuthRequired: true // Show all items, we'll style disabled ones
    });

    // Create navigation container
    this.container = document.createElement('nav');
    this.container.className = NAV_CLASSES.MOBILE_BOTTOM;
    this.container.setAttribute('aria-label', 'Mobile bottom navigation');

    // Create nav items list
    const navList = document.createElement('ul');
    navList.className = 'nav-items';
    navList.setAttribute('role', 'list');

    const currentPageId = getCurrentPageId();

    // Render each navigation item
    navItems.forEach(item => {
      const li = this.createNavItem(item, currentPageId);
      navList.appendChild(li);
    });

    this.container.appendChild(navList);

    // Insert into DOM at the end of body
    document.body.appendChild(this.container);
  }

  /**
   * Create a single navigation item
   * @param {Object} item - Navigation item from config
   * @param {string} currentPageId - Current page ID
   * @returns {HTMLElement} List item element
   */
  createNavItem(item, currentPageId) {
    const li = document.createElement('li');
    li.className = NAV_CLASSES.NAV_ITEM;

    // Add active class if this is the current page
    if (isNavItemActive(item, currentPageId)) {
      li.classList.add(NAV_CLASSES.ACTIVE);
    }

    // Add auth/admin indicator classes
    if (item.authRequired) {
      li.classList.add(NAV_CLASSES.AUTH_REQUIRED);
    }
    if (item.adminOnly) {
      li.classList.add(NAV_CLASSES.ADMIN_ONLY);
    }

    // Disable item if user doesn't have required permissions
    const shouldDisable = (item.authRequired && !this.isAuthenticated) ||
                          (item.adminOnly && !this.isAdmin);

    if (shouldDisable) {
      li.classList.add(NAV_CLASSES.DISABLED);
    }

    // Create link
    const link = document.createElement('a');
    link.href = shouldDisable ? '#' : item.href;
    link.setAttribute('aria-label', item.label);

    if (isNavItemActive(item, currentPageId)) {
      link.setAttribute('aria-current', 'page');
    }

    // Create icon
    const icon = document.createElement('span');
    icon.className = NAV_CLASSES.NAV_ICON;
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = item.icon;

    // Create label (use shortLabel for mobile if available)
    const label = document.createElement('span');
    label.className = NAV_CLASSES.NAV_LABEL;
    label.textContent = getNavLabel(item, true); // Use short label

    // Assemble the link
    link.appendChild(icon);
    link.appendChild(label);

    // Add click handler
    if (!shouldDisable) {
      link.addEventListener('click', (e) => {
        this.handleNavItemClick(e, item);
      });
    } else {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        // Optionally show a message that login is required
        if (item.authRequired && !this.isAuthenticated) {
          console.log('Login required for', item.label);
        }
      });
    }

    li.appendChild(link);
    return li;
  }

  /**
   * Handle navigation item click
   * @param {Event} e - Click event
   * @param {Object} item - Navigation item
   */
  handleNavItemClick(e, item) {
    // Dispatch custom event
    dispatchNavEvent(NAV_EVENTS.ITEM_CLICKED, {
      item,
      mode: NAV_MODES.MOBILE_BOTTOM
    });

    // Allow default navigation to proceed
  }

  /**
   * Destroy the navigation component
   */
  destroy() {
    if (this.container) {
      this.container.remove();
      this.container = null;
    }
  }

  /**
   * Update the active item highlight
   */
  updateActiveItem() {
    if (!this.container) return;

    const currentPageId = getCurrentPageId();
    const items = this.container.querySelectorAll(`.${NAV_CLASSES.NAV_ITEM}`);

    items.forEach(item => {
      const link = item.querySelector('a');
      const href = link.getAttribute('href');

      // Check if this item's href matches the current page
      const itemId = this.findItemIdByHref(href);
      const isActive = itemId === currentPageId;

      if (isActive) {
        item.classList.add(NAV_CLASSES.ACTIVE);
        link.setAttribute('aria-current', 'page');
      } else {
        item.classList.remove(NAV_CLASSES.ACTIVE);
        link.removeAttribute('aria-current');
      }
    });
  }

  /**
   * Find navigation item ID by href
   * @param {string} href - Link href
   * @returns {string|null} Item ID
   */
  findItemIdByHref(href) {
    const allItems = [
      ...NAV_CONFIG.primary,
      ...NAV_CONFIG.secondary,
      ...NAV_CONFIG.admin
    ];

    const item = allItems.find(i => i.href === href);
    return item ? item.id : null;
  }
}

/**
 * Create and initialize a mobile bottom navigation instance
 * @param {Object} options - Initialization options
 * @returns {MobileBottomNav} Navigation instance
 */
export function createMobileBottomNav(options = {}) {
  const nav = new MobileBottomNav();
  nav.init(options);
  return nav;
}

// Export singleton instance
let _instance = null;

/**
 * Get or create the singleton mobile bottom navigation instance
 * @param {Object} options - Initialization options
 * @returns {MobileBottomNav} Navigation instance
 */
export function getMobileBottomNav(options = {}) {
  if (!_instance) {
    _instance = createMobileBottomNav(options);
  } else if (options.isAuthenticated !== undefined || options.isAdmin !== undefined) {
    // Update auth state if provided
    _instance.updateAuthState({
      isAuthenticated: options.isAuthenticated ?? _instance.isAuthenticated,
      isAdmin: options.isAdmin ?? _instance.isAdmin
    });
  }
  return _instance;
}
