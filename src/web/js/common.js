// Common components for the cocktail database
import { initAuth, isAuthenticated, getUserInfo } from './auth.js';
import { getMobileBottomNav } from './mobileBottomNav.js';
import { getMobileHamburgerMenu } from './mobileHamburgerMenu.js';
import { getDesktopNav } from './desktopNav.js';

// Store navigation instances
let mobileBottomNav = null;
let mobileHamburgerMenu = null;
let desktopNav = null;

/**
 * Loads common head elements into the document
 * This includes meta tags, icons, CSS with FOUC prevention
 */
export function loadCommonHead() {
    const headContent = `
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <!-- Direct CSS link with FOUC prevention -->
        <style>
            body { visibility: hidden; }
        </style>
        <link rel="stylesheet" href="normalize.css">
        <link rel="stylesheet" href="styles.css"
            onload="document.body.style.visibility=''"
            onerror="document.body.style.visibility=''">
        <!-- Favicon and app icons -->
        <link rel="icon" type="image/png" href="img/favicon-96x96.png" sizes="96x96" />
        <link rel="icon" type="image/svg+xml" href="img/favicon.svg" />
        <link rel="shortcut icon" href="img/favicon.ico" />
        <link rel="apple-touch-icon" sizes="180x180" href="img/apple-touch-icon.png" />
        <meta name="apple-mobile-web-app-title" content="Mixology Tools" />
        <link rel="manifest" href="site.webmanifest" />
    `;

    // Insert the common head elements
    document.head.insertAdjacentHTML('beforeend', headContent);
}

/**
 * Loads header component into the page
 */
export function loadHeader() {
  const header = document.createElement('header');
  header.innerHTML = `
    <div class="header-container">
      <h1 class="site-title"><span class="title-line">Mixology</span><span class="title-line">Tools</span></h1>
      <div class="auth-controls">
        <span id="user-info" class="hidden">
          <span id="username-display"></span>
          <button id="logout-btn" class="btn-logout">Logout</button>
        </span>
        <button id="login-btn" class="btn-auth">Login</button>
        <button id="signup-btn" class="btn-auth btn-signup">Sign Up</button>
      </div>
      <nav id="header-nav-container">
        <!-- Desktop navigation will be inserted here -->
        <!-- Hamburger button for mobile will be inserted here -->
      </nav>
    </div>
  `;

  // Find the existing header and replace it
  const existingHeader = document.querySelector('header');
  if (existingHeader) {
    existingHeader.replaceWith(header);
  } else {
    // If no header exists, insert at the beginning of the body
    document.body.insertBefore(header, document.body.firstChild);
  }
}

/**
 * Get user groups from ID token
 */
function getUserGroups() {
  const userInfo = getUserInfo();
  if (!userInfo.idToken) return [];

  try {
    const parts = userInfo.idToken.split('.');
    if (parts.length === 3) {
      const payload = JSON.parse(atob(parts[1]));
      return payload['cognito:groups'] || [];
    }
  } catch (e) {
    console.error('Error parsing groups from token:', e);
  }
  return [];
}

/**
 * Initialize all navigation components
 */
export function initNavigation() {
  // Get current auth state
  const authenticated = isAuthenticated();
  const groups = getUserGroups();
  const isAdmin = groups.includes('admin');

  const authState = {
    isAuthenticated: authenticated,
    isAdmin: isAdmin
  };

  // Get header nav container for hamburger button
  const headerNavContainer = document.querySelector('#header-nav-container');

  // Initialize desktop navigation
  desktopNav = getDesktopNav(authState);

  // Insert desktop nav into header before auth controls
  if (headerNavContainer && desktopNav.container) {
    const authControls = headerNavContainer.querySelector('.auth-controls');
    headerNavContainer.insertBefore(desktopNav.container, authControls);
  }

  // Initialize mobile bottom navigation
  mobileBottomNav = getMobileBottomNav(authState);

  // Initialize mobile hamburger menu
  mobileHamburgerMenu = getMobileHamburgerMenu({
    ...authState,
    hamburgerButtonContainer: headerNavContainer
  });
}

/**
 * Update navigation when authentication state changes
 */
export function updateNavigationAuth() {
  const authenticated = isAuthenticated();
  const groups = getUserGroups();
  const isAdmin = groups.includes('admin');

  const authState = {
    isAuthenticated: authenticated,
    isAdmin: isAdmin
  };

  // Dispatch custom auth state change event
  document.dispatchEvent(new CustomEvent('auth-state-changed', {
    detail: authState
  }));

  // Update all navigation components
  if (desktopNav) {
    desktopNav.updateAuthState(authState);
  }
  if (mobileBottomNav) {
    mobileBottomNav.updateAuthState(authState);
  }
  if (mobileHamburgerMenu) {
    mobileHamburgerMenu.updateAuthState(authState);
  }
}

/**
 * Loads footer component into the page
 */
export function loadFooter() {
  const footer = document.createElement('footer');
  footer.innerHTML = `
    <p>&copy; ${new Date().getFullYear()} Kurt Thorn</p>
    <style>
        body { visibility: visible !important; }
    </style>
  `;
  
  // Find the existing footer and replace it
  const existingFooter = document.querySelector('footer');
  if (existingFooter) {
    existingFooter.replaceWith(footer);
  } else {
    // If no footer exists, append it to the body
    document.body.appendChild(footer);
  }
}

// Initialize common components when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Load the common head elements first
  loadCommonHead();

  // Then load the header
  loadHeader();

  // Load the footer
  loadFooter();

  // Initialize authentication
  initAuth();

  // Initialize navigation (after auth is set up)
  // Delay slightly to ensure auth state is available
  setTimeout(() => {
    initNavigation();
  }, 100);
});

/**
 * Generates HTML for displaying star ratings
 * @param {number} rating - The average rating (0-5)
 * @param {number} count - The number of ratings
 * @returns {string} HTML string for the star rating display
 */
export function generateStarRating(rating, count) {
  // Round to nearest half star
  const roundedRating = Math.round((rating || 0) * 2) / 2;
  
  // Generate stars HTML
  let starsHtml = '<div class="star-rating">';
  
  // Add filled and half-filled stars
  for (let i = 1; i <= 5; i++) {
    if (i <= roundedRating) {
      // Full star
      starsHtml += '<span class="star filled">★</span>';
    } else if (i - 0.5 === roundedRating) {
      // Half star
      starsHtml += '<span class="star half">★</span>';
    } else {
      // Empty star
      starsHtml += '<span class="star">☆</span>';
    }
  }
  
  // Add rating count
  starsHtml += `<span class="rating-count">(${count || 0})</span>`;
  starsHtml += '</div>';
  
  return starsHtml;
}

/**
 * Creates a pure interactive star component (5 stars only, no additional text)
 * @param {Object} options - Configuration options
 * @param {number} options.initialRating - The initial rating value (0 for no selection)
 * @param {boolean} options.allowToggle - Whether clicking the same star again deselects it (default: false)
 * @param {boolean} options.showDifferentStates - Whether to show different visual states for no-rating vs 0-star vs filled (default: false)
 * @param {Function} options.onClick - Callback when a star is clicked: (rating) => {}
 * @returns {HTMLElement} The interactive star component
 */
export function createInteractiveStars(options) {
  const {
    initialRating = 0,
    allowToggle = false,
    showDifferentStates = false,
    onClick
  } = options;

  const container = document.createElement('div');
  container.className = 'star-rating interactive';
  container.dataset.rating = (initialRating ?? 0).toString();
  
  // Distinguish between no rating and 0-star rating for visual states
  const hasRating = showDifferentStates ? (initialRating !== null && initialRating !== undefined) : true;
  const ratingValue = initialRating ?? 0;
  
  // Create 5 stars
  for (let i = 1; i <= 5; i++) {
    const star = document.createElement('span');
    star.className = 'star interactive';
    star.dataset.value = i;
    
    // Set initial star appearance
    if (showDifferentStates) {
      // Rating mode: show different states
      if (!hasRating) {
        star.textContent = '☆';
        star.classList.add('no-rating');
      } else if (ratingValue === 0) {
        star.textContent = '★';
        star.classList.add('zero-rating');
      } else {
        star.textContent = i <= ratingValue ? '★' : '☆';
        if (i <= ratingValue) {
          star.classList.add('filled');
        }
      }
    } else {
      // Filter mode: use filled stars with active class
      star.textContent = '★';
      if (i <= ratingValue) {
        star.classList.add('active');
      }
    }
    
    // Add hover effect
    star.addEventListener('mouseover', () => {
      container.querySelectorAll('.star').forEach(s => {
        const value = parseInt(s.dataset.value);
        if (showDifferentStates) {
          // Rating mode: change content and add hover class
          if (value <= i) {
            s.textContent = '★';
            s.classList.add('hover');
          } else {
            s.textContent = '☆';
            s.classList.remove('hover');
          }
        } else {
          // Filter mode: just add hover class
          if (value <= i) {
            s.classList.add('hover');
          } else {
            s.classList.remove('hover');
          }
        }
      });
    });
    
    // Click event
    star.addEventListener('click', () => {
      const currentRating = parseInt(container.dataset.rating) || 0;
      let newRating = i;
      
      // Handle toggle behavior if enabled
      if (allowToggle && currentRating === i) {
        newRating = 0;
      }
      
      // Update container state
      container.dataset.rating = newRating.toString();
      updateStarDisplay(container, newRating, showDifferentStates, hasRating);
      
      // Call callback
      if (typeof onClick === 'function') {
        onClick(newRating);
      }
    });
    
    container.appendChild(star);
  }
  
  // Reset hover effect on mouse leave
  container.addEventListener('mouseleave', () => {
    const currentRating = parseInt(container.dataset.rating) || 0;
    updateStarDisplay(container, currentRating, showDifferentStates, hasRating);
    container.querySelectorAll('.star').forEach(s => s.classList.remove('hover'));
  });
  
  return container;
}

/**
 * Helper function to update star display
 */
function updateStarDisplay(container, rating, showDifferentStates, hasRating) {
  container.querySelectorAll('.star').forEach(star => {
    const value = parseInt(star.dataset.value);
    star.classList.remove('hover', 'active', 'filled', 'no-rating', 'zero-rating');
    
    if (showDifferentStates) {
      // Rating mode: different visual states
      if (!hasRating) {
        star.textContent = '☆';
        star.classList.add('no-rating');
      } else if (rating === 0) {
        star.textContent = '★';
        star.classList.add('zero-rating');
      } else {
        star.textContent = value <= rating ? '★' : '☆';
        if (value <= rating) {
          star.classList.add('filled');
        }
      }
    } else {
      // Filter mode: active class
      star.textContent = '★';
      if (value <= rating) {
        star.classList.add('active');
      }
    }
  });
} 