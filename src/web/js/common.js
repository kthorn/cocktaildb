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
          <span id="username">Not logged in</span>
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

export { loadHeader };

// Function to load common head elements
export function loadCommonHead() {
    const headContent = `
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="styles.css">
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