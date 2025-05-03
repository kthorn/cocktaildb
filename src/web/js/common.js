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
  
  // Initialize authentication after header is loaded
  initAuth();
}

// Initialize common components when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  loadHeader();
});

export { loadHeader }; 