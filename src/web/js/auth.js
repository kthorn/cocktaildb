// Authentication module
import config from './config.js';

// Initialize authentication on page load
export function initAuth() {
    const loginButton = document.getElementById('login-btn');
    const logoutButton = document.getElementById('logout-btn');
    const userInfo = document.getElementById('user-info');
    
    // Check if elements exist (they should be on every page)
    if (!loginButton || !logoutButton || !userInfo) {
        console.error('Auth UI elements not found in the DOM');
        return;
    }
    
    // Check if user is already logged in
    updateAuthUI();
    
    // Setup login button
    loginButton.addEventListener('click', () => {
        // Redirect to Cognito hosted UI
        window.location.href = `${config.cognitoDomain}/login?client_id=${config.clientId}&response_type=token&scope=email+openid+profile&redirect_uri=${encodeURIComponent(window.location.origin + '/callback.html')}`;
    });
    
    // Setup logout button
    logoutButton.addEventListener('click', () => {
        logout();
    });
    
    // Function to update the UI based on auth state
    function updateAuthUI() {
        if (isAuthenticated()) {
            // User is logged in
            loginButton.classList.add('hidden');
            userInfo.classList.remove('hidden');
        } else {
            // User is logged out
            loginButton.classList.remove('hidden');
            userInfo.classList.add('hidden');
        }
    }
}

// Check if user is authenticated
export function isAuthenticated() {
    return localStorage.getItem('token') !== null;
}

// Get user information
export function getUserInfo() {
    return {
        token: localStorage.getItem('token'),
        idToken: localStorage.getItem('id_token'),
        username: localStorage.getItem('username')
    };
}

// Log the user out
export function logout() {
    // Clear token from localStorage
    localStorage.removeItem('token');
    localStorage.removeItem('id_token');
    localStorage.removeItem('username');
    
    // Redirect to Cognito logout
    window.location.href = `${config.cognitoDomain}/logout?client_id=${config.clientId}&logout_uri=${encodeURIComponent(window.location.origin + '/logout.html')}`;
    
    // Note: The page will be redirected, so the following code won't execute
    // window.location.reload();
} 