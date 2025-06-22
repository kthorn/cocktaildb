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
    
    // Check auth state periodically (every 30 seconds) to handle token expiration
    setInterval(() => {
        updateAuthUI();
    }, 30000);
    
    // Also check when page becomes visible (e.g., switching tabs)
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            updateAuthUI();
        }
    });
}

// Check if user is authenticated
export function isAuthenticated() {
    const token = localStorage.getItem('token');
    const idToken = localStorage.getItem('id_token');
    
    if (!token || !idToken) {
        return false;
    }
    
    try {
        // Check if the ID token is expired
        const parts = idToken.split('.');
        if (parts.length === 3) {
            const payload = JSON.parse(atob(parts[1]));
            const currentTime = Math.floor(Date.now() / 1000);
            
            // If token is expired, clear stored tokens and return false
            if (payload.exp && payload.exp < currentTime) {
                localStorage.removeItem('token');
                localStorage.removeItem('id_token');
                localStorage.removeItem('username');
                return false;
            }
        }
    } catch (e) {
        console.error('Error checking token expiration:', e);
        // If we can't parse the token, consider it invalid
        localStorage.removeItem('token');
        localStorage.removeItem('id_token');
        localStorage.removeItem('username');
        return false;
    }
    
    return true;
}

// Get user information
export function getUserInfo() {
    const token = localStorage.getItem('token');
    const idToken = localStorage.getItem('id_token');
    const username = localStorage.getItem('username');
    
    let cognitoUserId = null;
    
    // Try to extract user ID from the ID token if available
    if (idToken) {
        try {
            // JWT tokens are in the format header.payload.signature
            const parts = idToken.split('.');
            if (parts.length === 3) {
                // Decode the payload (middle part)
                const payload = JSON.parse(atob(parts[1]));
                cognitoUserId = payload.sub; // 'sub' claim contains the Cognito user ID
            }
        } catch (e) {
            console.error('Error parsing ID token:', e);
        }
    }
    
    return {
        token,
        idToken,
        username,
        cognitoUserId
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