// Desktop Navigation Component
import {
  NAV_CONFIG,
  NAV_MODES,
  NAV_CLASSES,
  getNavigationItems,
  getCurrentPageId,
  isNavItemActive,
  dispatchNavEvent,
  NAV_EVENTS
} from './navigation.js';

/**
 * Renders and manages the desktop horizontal navigation
 */
export class DesktopNav {
  constructor() {
    this.container = null;
    this.isAuthenticated = false;
    this.isAdmin = false;
  }

  /**
   * Initialize the desktop navigation
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
   * Render the desktop navigation
   */
  render() {
    // Remove existing navigation if present
    if (this.container) {
      this.container.remove();
    }

    // Create navigation container
    this.container = document.createElement('nav');
    this.container.className = NAV_CLASSES.DESKTOP_NAV;
    this.container.setAttribute('aria-label', 'Main navigation');

    const currentPageId = getCurrentPageId();

    // Get primary navigation items
    const primaryItems = this.getNavItems(NAV_CONFIG.primary);

    // Get secondary navigation items
    const secondaryItems = this.getNavItems(NAV_CONFIG.secondary);

    // Get admin items
    const adminItems = this.isAdmin ? this.getNavItems(NAV_CONFIG.admin) : [];

    // Create primary nav list
    const primaryList = document.createElement('ul');
    primaryList.className = 'nav-items';
    primaryList.setAttribute('role', 'list');

    // Render primary items
    primaryItems.forEach(item => {
      const li = this.createNavItem(item, currentPageId);
      primaryList.appendChild(li);
    });

    // Create dropdown for secondary items if any exist
    if (secondaryItems.length > 0 || adminItems.length > 0) {
      const dropdownLi = this.createDropdownMenu(secondaryItems, adminItems, currentPageId);
      primaryList.appendChild(dropdownLi);
    }

    this.container.appendChild(primaryList);
  }

  /**
   * Get filtered navigation items from a config section
   * @param {Array} configSection - Navigation config section
   * @returns {Array} Filtered items
   */
  getNavItems(configSection) {
    return configSection.filter(item => {
      // Check if item should be shown in desktop nav
      if (!item.desktop) return false;

      // Filter based on authentication
      if (item.authRequired && !this.isAuthenticated) return false;
      if (item.adminOnly && !this.isAdmin) return false;

      return true;
    });
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

    // Create link
    const link = document.createElement('a');
    link.href = item.href;
    link.setAttribute('aria-label', item.label);

    if (isNavItemActive(item, currentPageId)) {
      link.setAttribute('aria-current', 'page');
    }

    // Create icon
    const icon = document.createElement('span');
    icon.className = NAV_CLASSES.NAV_ICON;
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = item.icon;

    // Create label
    const label = document.createElement('span');
    label.className = NAV_CLASSES.NAV_LABEL;
    label.textContent = item.label;

    // Assemble the link
    link.appendChild(icon);
    link.appendChild(label);

    // Add click handler
    link.addEventListener('click', (e) => {
      this.handleNavItemClick(e, item);
    });

    li.appendChild(link);
    return li;
  }

  /**
   * Create a dropdown menu for secondary and admin items
   * @param {Array} secondaryItems - Secondary navigation items
   * @param {Array} adminItems - Admin navigation items
   * @param {string} currentPageId - Current page ID
   * @returns {HTMLElement} Dropdown list item
   */
  createDropdownMenu(secondaryItems, adminItems, currentPageId) {
    const li = document.createElement('li');
    li.className = `${NAV_CLASSES.NAV_ITEM} nav-dropdown`;

    // Create dropdown toggle button
    const toggle = document.createElement('a');
    toggle.href = '#';
    toggle.className = 'nav-dropdown-toggle';
    toggle.setAttribute('aria-label', 'More menu');
    toggle.setAttribute('aria-haspopup', 'true');
    toggle.setAttribute('aria-expanded', 'false');

    const icon = document.createElement('span');
    icon.className = NAV_CLASSES.NAV_ICON;
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '⋮';

    const label = document.createElement('span');
    label.className = NAV_CLASSES.NAV_LABEL;
    label.textContent = 'More';

    toggle.appendChild(icon);
    toggle.appendChild(label);

    // Prevent default link behavior
    toggle.addEventListener('click', (e) => {
      e.preventDefault();
    });

    // Create dropdown menu
    const dropdownMenu = document.createElement('ul');
    dropdownMenu.className = 'nav-dropdown-menu';
    dropdownMenu.setAttribute('role', 'menu');

    // Add secondary items
    secondaryItems.forEach(item => {
      const menuItem = this.createDropdownItem(item, currentPageId);
      dropdownMenu.appendChild(menuItem);
    });

    // Add admin items with a divider if there are any
    if (adminItems.length > 0 && secondaryItems.length > 0) {
      const divider = document.createElement('li');
      divider.className = 'nav-dropdown-divider';
      divider.setAttribute('role', 'separator');
      divider.style.borderTop = '1px solid var(--border-light)';
      divider.style.margin = 'var(--space-xs) 0';
      dropdownMenu.appendChild(divider);
    }

    adminItems.forEach(item => {
      const menuItem = this.createDropdownItem(item, currentPageId);
      dropdownMenu.appendChild(menuItem);
    });

    li.appendChild(toggle);
    li.appendChild(dropdownMenu);

    // Handle keyboard navigation
    this.setupDropdownKeyboardNav(li, toggle, dropdownMenu);

    return li;
  }

  /**
   * Create a dropdown menu item
   * @param {Object} item - Navigation item from config
   * @param {string} currentPageId - Current page ID
   * @returns {HTMLElement} Dropdown item element
   */
  createDropdownItem(item, currentPageId) {
    const li = document.createElement('li');
    li.className = NAV_CLASSES.NAV_ITEM;
    li.setAttribute('role', 'none');

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

    // Create link
    const link = document.createElement('a');
    link.href = item.href;
    link.setAttribute('role', 'menuitem');
    link.setAttribute('aria-label', item.label);

    if (isNavItemActive(item, currentPageId)) {
      link.setAttribute('aria-current', 'page');
    }

    // Create icon
    const icon = document.createElement('span');
    icon.className = NAV_CLASSES.NAV_ICON;
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = item.icon;

    // Create label
    const label = document.createElement('span');
    label.className = NAV_CLASSES.NAV_LABEL;
    label.textContent = item.label;

    // Assemble the link
    link.appendChild(icon);
    link.appendChild(label);

    // Add click handler
    link.addEventListener('click', (e) => {
      this.handleNavItemClick(e, item);
    });

    li.appendChild(link);
    return li;
  }

  /**
   * Setup keyboard navigation for dropdown
   * @param {HTMLElement} dropdownLi - Dropdown list item
   * @param {HTMLElement} toggle - Dropdown toggle button
   * @param {HTMLElement} menu - Dropdown menu
   */
  setupDropdownKeyboardNav(dropdownLi, toggle, menu) {
    toggle.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault();
        toggle.setAttribute('aria-expanded', 'true');
        menu.style.opacity = '1';
        menu.style.visibility = 'visible';
        menu.style.transform = 'translateY(0)';

        // Focus first menu item
        const firstItem = menu.querySelector('a');
        if (firstItem) {
          firstItem.focus();
        }
      }
    });

    // Close menu when clicking outside or pressing Escape
    const closeMenu = () => {
      toggle.setAttribute('aria-expanded', 'false');
      menu.style.opacity = '';
      menu.style.visibility = '';
      menu.style.transform = '';
    };

    menu.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeMenu();
        toggle.focus();
      }
    });

    menu.addEventListener('focusout', (e) => {
      // Close menu if focus moves outside the dropdown
      setTimeout(() => {
        if (!dropdownLi.contains(document.activeElement)) {
          closeMenu();
        }
      }, 0);
    });
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
      mode: NAV_MODES.DESKTOP
    });

    // Allow default navigation to proceed
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

  /**
   * Destroy the navigation component
   */
  destroy() {
    if (this.container) {
      this.container.remove();
      this.container = null;
    }
  }
}

/**
 * Create and initialize a desktop navigation instance
 * @param {Object} options - Initialization options
 * @returns {DesktopNav} Navigation instance
 */
export function createDesktopNav(options = {}) {
  const nav = new DesktopNav();
  nav.init(options);
  return nav;
}

// Export singleton instance
let _instance = null;

/**
 * Get or create the singleton desktop navigation instance
 * @param {Object} options - Initialization options
 * @returns {DesktopNav} Navigation instance
 */
export function getDesktopNav(options = {}) {
  if (!_instance) {
    _instance = createDesktopNav(options);
  } else if (options.isAuthenticated !== undefined || options.isAdmin !== undefined) {
    // Update auth state if provided
    _instance.updateAuthState({
      isAuthenticated: options.isAuthenticated ?? _instance.isAuthenticated,
      isAdmin: options.isAdmin ?? _instance.isAdmin
    });
  }
  return _instance;
}
