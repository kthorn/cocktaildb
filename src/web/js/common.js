// Common components for the cocktail database
import { initAuth } from './auth.js';

// Load header component into the page
function loadHeader() {
  const header = document.createElement('header');
  header.innerHTML = `
    <h1>Cocktail Database</h1>
    <nav>
      <ul>
        <li><a href="index.html">Home</a></li>
        <li><a href="ingredients.html">Ingredients</a></li>
        <li><a href="recipes.html">Recipes</a></li>
      </ul>
      <div class="auth-controls">
        <span id="user-info" class="hidden">
          <button id="logout-btn">Logout</button>
        </span>
        <button id="login-btn">Login</button>
      </div>
    </nav>
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

// Initialize common components when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  loadHeader();
  // Initialize authentication AFTER header is loaded to ensure elements exist
  setTimeout(() => {
    initAuth();
  }, 0);
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
 * Creates an interactive star rating component
 * @param {number} recipeId - The ID of the recipe
 * @param {number} currentRating - The current user's rating (if any)
 * @param {number} avgRating - The average rating (0-5)
 * @param {number} count - The number of ratings
 * @param {Function} onRatingSubmitted - Callback when rating is submitted
 * @returns {HTMLElement} The interactive star rating element
 */
export function createInteractiveRating(recipeId, currentRating, avgRating, count, onRatingSubmitted) {
  const container = document.createElement('div');
  container.className = 'star-rating interactive';
  container.dataset.recipeId = recipeId;
  
  // Create 5 stars
  for (let i = 1; i <= 5; i++) {
    const star = document.createElement('span');
    star.className = 'star interactive';
    star.textContent = i <= (currentRating || 0) ? '★' : '☆';
    star.dataset.value = i;
    
    // Add filled class if this star is filled based on current user rating
    if (i <= (currentRating || 0)) {
      star.classList.add('filled');
    }
    
    // Add hover effect
    star.addEventListener('mouseover', () => {
      // Fill all stars up to this one on hover
      container.querySelectorAll('.star').forEach(s => {
        if (parseInt(s.dataset.value) <= i) {
          s.textContent = '★';
          s.classList.add('hover');
        } else {
          s.textContent = '☆';
          s.classList.remove('hover');
        }
      });
    });
    
    // Remove hover effect
    star.addEventListener('mouseout', () => {
      // Reset to original state
      container.querySelectorAll('.star').forEach(s => {
        const value = parseInt(s.dataset.value);
        s.classList.remove('hover');
        if (value <= (currentRating || 0)) {
          s.textContent = '★';
          s.classList.add('filled');
        } else {
          s.textContent = '☆';
          s.classList.remove('filled');
        }
      });
    });
    
    // Click event to set rating
    star.addEventListener('click', async () => {
      if (typeof onRatingSubmitted === 'function') {
        await onRatingSubmitted(recipeId, i);
      }
    });
    
    container.appendChild(star);
  }
  
  // Add rating average and count
  const stats = document.createElement('span');
  stats.className = 'rating-stats';
  stats.textContent = ` - Avg: ${avgRating.toFixed(1)} (${count || 0})`;
  container.appendChild(stats);
  
  return container;
}

export { loadHeader };

// Function to load common head elements
export function loadCommonHead() {
    const headContent = `
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <!-- CSS is now loaded directly in HTML to prevent FOUC -->
        <link rel="icon" type="image/png" href="img/favicon-96x96.png" sizes="96x96" />
        <link rel="icon" type="image/svg+xml" href="img/favicon.svg" />
        <link rel="shortcut icon" href="img/favicon.ico" />
        <link rel="apple-touch-icon" sizes="180x180" href="img/apple-touch-icon.png" />
        <meta name="apple-mobile-web-app-title" content="CocktailDB" />
        <link rel="manifest" href="site.webmanifest" />
    `;
    
    // Insert the common head elements
    document.head.insertAdjacentHTML('beforeend', headContent);
} 