// Mobile Hamburger Menu Component
import {
  NAV_CONFIG,
  NAV_MODES,
  NAV_CLASSES,
  NAV_ANIMATIONS,
  getNavigationItems,
  getCurrentPageId,
  isNavItemActive,
  dispatchNavEvent,
  NAV_EVENTS
} from './navigation.js';

/**
 * Renders and manages the mobile hamburger slide-in menu
 */
export class MobileHamburgerMenu {
  constructor() {
    this.menuContainer = null;
    this.overlay = null;
    this.hamburgerButton = null;
    this.isOpen = false;
    this.isAuthenticated = false;
    this.isAdmin = false;
  }

  /**
   * Initialize the mobile hamburger menu
   * @param {Object} options - Configuration options
   * @param {boolean} options.isAuthenticated - Whether user is logged in
   * @param {boolean} options.isAdmin - Whether user has admin privileges
   * @param {HTMLElement} options.hamburgerButtonContainer - Container for hamburger button (usually header nav)
   */
  init(options = {}) {
    this.isAuthenticated = options.isAuthenticated || false;
    this.isAdmin = options.isAdmin || false;

    // Create and insert the menu
    this.render();

    // Create hamburger button if container provided
    if (options.hamburgerButtonContainer) {
      this.createHamburgerButton(options.hamburgerButtonContainer);
    }

    // Listen for auth changes
    document.addEventListener('auth-state-changed', (e) => {
      this.updateAuthState(e.detail);
    });

    // Listen for escape key to close menu
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.isOpen) {
        this.close();
      }
    });
  }

  /**
   * Update authentication state and re-render
   * @param {Object} authState - New authentication state
   */
  updateAuthState(authState) {
    this.isAuthenticated = authState.isAuthenticated || false;
    this.isAdmin = authState.isAdmin || false;
    const wasOpen = this.isOpen;
    this.render();
    if (wasOpen) {
      this.open();
    }
  }

  /**
   * Create the hamburger button
   * @param {HTMLElement} container - Container element
   */
  createHamburgerButton(container) {
    // Remove existing button if present
    if (this.hamburgerButton) {
      this.hamburgerButton.remove();
    }

    this.hamburgerButton = document.createElement('button');
    this.hamburgerButton.className = 'nav-hamburger-btn';
    this.hamburgerButton.setAttribute('aria-label', 'Open navigation menu');
    this.hamburgerButton.setAttribute('aria-expanded', 'false');
    this.hamburgerButton.setAttribute('aria-controls', 'mobile-hamburger-menu');
    this.hamburgerButton.innerHTML = '☰';

    this.hamburgerButton.addEventListener('click', () => {
      this.toggle();
    });

    container.appendChild(this.hamburgerButton);
  }

  /**
   * Render the mobile hamburger menu
   */
  render() {
    // Remove existing menu if present
    if (this.menuContainer) {
      this.menuContainer.remove();
    }
    if (this.overlay) {
      this.overlay.remove();
    }

    // Create overlay
    this.overlay = document.createElement('div');
    this.overlay.className = 'nav-mobile-menu-overlay';
    this.overlay.addEventListener('click', () => {
      this.close();
    });

    // Create menu container
    this.menuContainer = document.createElement('nav');
    this.menuContainer.id = 'mobile-hamburger-menu';
    this.menuContainer.className = NAV_CLASSES.MOBILE_MENU;
    this.menuContainer.setAttribute('aria-label', 'Mobile navigation menu');

    // Create menu header
    const header = document.createElement('div');
    header.className = 'nav-mobile-menu-header';

    const title = document.createElement('h2');
    title.textContent = 'Menu';
    header.appendChild(title);

    const closeButton = document.createElement('button');
    closeButton.className = 'nav-mobile-menu-close';
    closeButton.setAttribute('aria-label', 'Close navigation menu');
    closeButton.innerHTML = '×';
    closeButton.addEventListener('click', () => {
      this.close();
    });
    header.appendChild(closeButton);

    this.menuContainer.appendChild(header);

    // Create menu items
    const menuContent = this.createMenuContent();
    this.menuContainer.appendChild(menuContent);

    // Insert into DOM
    document.body.appendChild(this.overlay);
    document.body.appendChild(this.menuContainer);
  }

  /**
   * Create the menu content with sections
   * @returns {HTMLElement} Menu content element
   */
  createMenuContent() {
    const container = document.createElement('div');
    container.className = 'nav-mobile-menu-content';

    const currentPageId = getCurrentPageId();

    // Get primary items
    const primaryItems = this.getMenuItems(NAV_CONFIG.primary);
    if (primaryItems.length > 0) {
      const primaryList = this.createMenuSection(primaryItems, currentPageId);
      container.appendChild(primaryList);
    }

    // Get secondary items
    const secondaryItems = this.getMenuItems(NAV_CONFIG.secondary);
    if (secondaryItems.length > 0) {
      // Add divider
      const divider = document.createElement('div');
      divider.className = 'nav-section-divider';
      divider.textContent = 'More';
      container.appendChild(divider);

      const secondaryList = this.createMenuSection(secondaryItems, currentPageId);
      container.appendChild(secondaryList);
    }

    // Get admin items (if user is admin)
    if (this.isAdmin) {
      const adminItems = this.getMenuItems(NAV_CONFIG.admin);
      if (adminItems.length > 0) {
        // Add divider
        const divider = document.createElement('div');
        divider.className = 'nav-section-divider';
        divider.textContent = 'Admin';
        container.appendChild(divider);

        const adminList = this.createMenuSection(adminItems, currentPageId);
        container.appendChild(adminList);
      }
    }

    return container;
  }

  /**
   * Get filtered menu items from a config section
   * @param {Array} configSection - Navigation config section
   * @returns {Array} Filtered items
   */
  getMenuItems(configSection) {
    return configSection.filter(item => {
      // Check if item should be shown in mobile menu
      if (!item.mobileMenu) return false;

      // Filter based on authentication
      if (item.authRequired && !this.isAuthenticated) return false;
      if (item.adminOnly && !this.isAdmin) return false;

      return true;
    });
  }

  /**
   * Create a menu section with items
   * @param {Array} items - Navigation items
   * @param {string} currentPageId - Current page ID
   * @returns {HTMLElement} Menu list element
   */
  createMenuSection(items, currentPageId) {
    const ul = document.createElement('ul');
    ul.className = 'nav-items';
    ul.setAttribute('role', 'list');

    items.forEach(item => {
      const li = this.createMenuItem(item, currentPageId);
      ul.appendChild(li);
    });

    return ul;
  }

  /**
   * Create a single menu item
   * @param {Object} item - Navigation item from config
   * @param {string} currentPageId - Current page ID
   * @returns {HTMLElement} List item element
   */
  createMenuItem(item, currentPageId) {
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
      this.handleMenuItemClick(e, item);
    });

    li.appendChild(link);
    return li;
  }

  /**
   * Handle menu item click
   * @param {Event} e - Click event
   * @param {Object} item - Navigation item
   */
  handleMenuItemClick(e, item) {
    // Close menu
    this.close();

    // Dispatch custom event
    dispatchNavEvent(NAV_EVENTS.ITEM_CLICKED, {
      item,
      mode: NAV_MODES.MOBILE_MENU
    });

    // Allow default navigation to proceed
  }

  /**
   * Open the menu
   */
  open() {
    if (this.isOpen) return;

    this.isOpen = true;

    // Add open class to overlay and menu
    this.overlay.classList.add(NAV_CLASSES.MENU_OPEN);
    this.menuContainer.classList.add(NAV_CLASSES.MENU_OPEN);

    // Update hamburger button
    if (this.hamburgerButton) {
      this.hamburgerButton.setAttribute('aria-expanded', 'true');
      this.hamburgerButton.innerHTML = '×';
    }

    // Prevent body scroll
    document.body.style.overflow = 'hidden';

    // Dispatch event
    dispatchNavEvent(NAV_EVENTS.MENU_TOGGLED, {
      isOpen: true,
      mode: NAV_MODES.MOBILE_MENU
    });

    // Focus the close button for accessibility
    setTimeout(() => {
      const closeButton = this.menuContainer.querySelector('.nav-mobile-menu-close');
      if (closeButton) {
        closeButton.focus();
      }
    }, NAV_ANIMATIONS.MENU_SLIDE);
  }

  /**
   * Close the menu
   */
  close() {
    if (!this.isOpen) return;

    this.isOpen = false;

    // Remove open class from overlay and menu
    this.overlay.classList.remove(NAV_CLASSES.MENU_OPEN);
    this.menuContainer.classList.remove(NAV_CLASSES.MENU_OPEN);

    // Update hamburger button
    if (this.hamburgerButton) {
      this.hamburgerButton.setAttribute('aria-expanded', 'false');
      this.hamburgerButton.innerHTML = '☰';
    }

    // Restore body scroll
    document.body.style.overflow = '';

    // Dispatch event
    dispatchNavEvent(NAV_EVENTS.MENU_TOGGLED, {
      isOpen: false,
      mode: NAV_MODES.MOBILE_MENU
    });

    // Return focus to hamburger button
    if (this.hamburgerButton) {
      this.hamburgerButton.focus();
    }
  }

  /**
   * Toggle the menu open/closed
   */
  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  /**
   * Destroy the menu component
   */
  destroy() {
    this.close();

    if (this.menuContainer) {
      this.menuContainer.remove();
      this.menuContainer = null;
    }

    if (this.overlay) {
      this.overlay.remove();
      this.overlay = null;
    }

    if (this.hamburgerButton) {
      this.hamburgerButton.remove();
      this.hamburgerButton = null;
    }

    document.body.style.overflow = '';
  }
}

/**
 * Create and initialize a mobile hamburger menu instance
 * @param {Object} options - Initialization options
 * @returns {MobileHamburgerMenu} Menu instance
 */
export function createMobileHamburgerMenu(options = {}) {
  const menu = new MobileHamburgerMenu();
  menu.init(options);
  return menu;
}

// Export singleton instance
let _instance = null;

/**
 * Get or create the singleton mobile hamburger menu instance
 * @param {Object} options - Initialization options
 * @returns {MobileHamburgerMenu} Menu instance
 */
export function getMobileHamburgerMenu(options = {}) {
  if (!_instance) {
    _instance = createMobileHamburgerMenu(options);
  } else if (options.isAuthenticated !== undefined || options.isAdmin !== undefined) {
    // Update auth state if provided
    _instance.updateAuthState({
      isAuthenticated: options.isAuthenticated ?? _instance.isAuthenticated,
      isAdmin: options.isAdmin ?? _instance.isAdmin
    });
  }
  return _instance;
}
