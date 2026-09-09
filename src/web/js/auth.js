// Authentication module
import config from './config.js';

// Initialize authentication on page load
export function initAuth(onAuthChange = () => {}) {
    const loginButton = document.getElementById('login-btn');
    const signupButton = document.getElementById('signup-btn');
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
        // Redirect to Cognito hosted UI for login
        startLogin().catch(() => alert('Unable to start login. Please try again.'));
    });

    // Setup signup button (if it exists)
    if (signupButton) {
        signupButton.addEventListener('click', () => {
            // Redirect to Cognito hosted UI for signup
            startLogin('signup').catch(() => alert('Unable to start signup. Please try again.'));
        });
    }

    // Setup logout button
    logoutButton.addEventListener('click', () => {
        logout();
    });

    // Function to update the UI based on auth state
    async function updateAuthUI() {
        try {
            await ensureSession();
        } catch {
            // Keep the session on temporary network failures; retry on the next check.
        }
        if (isAuthenticated()) {
            // User is logged in
            loginButton.classList.add('hidden');
            if (signupButton) signupButton.classList.add('hidden');
            userInfo.classList.remove('hidden');
        } else {
            // User is logged out
            loginButton.classList.remove('hidden');
            if (signupButton) signupButton.classList.remove('hidden');
            userInfo.classList.add('hidden');
        }
        onAuthChange();
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

// This synchronous check describes a signed-in or refreshable browser session.
// Authenticated API requests must await ensureSession before using its tokens.
export function isAuthenticated() {
    try {
        const access = decodeToken(localStorage.getItem('token'));
        const identity = decodeToken(localStorage.getItem('id_token'));
        return (
            Boolean(localStorage.getItem('refresh_token')) ||
            Math.min(access.exp, identity.exp) > Date.now() / 1000
        );
    } catch {
        return false;
    }
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
                const payload = decodeToken(idToken);
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
        cognitoUserId,
    };
}

// Log the user out
export function logout() {
    // Clear token from localStorage
    clearSession();

    // Redirect to Cognito logout
    window.location.href = `${config.cognitoDomain}/logout?client_id=${config.clientId}&logout_uri=${encodeURIComponent(window.location.origin + '/logout.html')}`;

    // Note: The page will be redirected, so the following code won't execute
    // window.location.reload();
}

let refreshPromise = null;
let sessionGeneration = 0;

function decodeToken(token) {
    if (!token || token.split('.').length !== 3) throw new Error('Invalid token');
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(
        decodeURIComponent(
            Array.from(
                atob(base64),
                (char) => '%' + char.charCodeAt(0).toString(16).padStart(2, '0'),
            ).join(''),
        ),
    );
    if (!Number.isFinite(payload.exp)) throw new Error('Missing token expiry');
    return payload;
}

export function clearSession() {
    sessionGeneration++;
    for (const key of ['token', 'id_token', 'username', 'refresh_token']) {
        localStorage.removeItem(key);
    }
    sessionStorage.removeItem('oauth_transaction');
}

function storeTokens(tokens) {
    const identity = decodeToken(tokens.id_token);
    decodeToken(tokens.access_token);
    localStorage.setItem('token', tokens.access_token);
    localStorage.setItem('id_token', tokens.id_token);
    localStorage.setItem('username', identity.preferred_username || identity.email || identity.sub);
    if (tokens.refresh_token) localStorage.setItem('refresh_token', tokens.refresh_token);
}

async function requestTokens(parameters) {
    const response = await fetch(`${config.cognitoDomain}/oauth2/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ client_id: config.clientId, ...parameters }).toString(),
    });
    const tokens = await response.json();
    if (!response.ok) {
        const error = new Error('Unable to renew login. Please try again.');
        error.code = tokens.error;
        throw error;
    }
    return tokens;
}

export async function ensureSession() {
    try {
        const expiry = Math.min(
            decodeToken(localStorage.getItem('token')).exp,
            decodeToken(localStorage.getItem('id_token')).exp,
        );
        if (expiry > Date.now() / 1000 + 60) return true;
    } catch {
        // A persisted refresh token can recover an expired or incomplete session.
    }
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) return isAuthenticated();
    if (refreshPromise) return refreshPromise;
    const generation = sessionGeneration;
    refreshPromise = (async () => {
        try {
            const tokens = await requestTokens({
                grant_type: 'refresh_token',
                refresh_token: refreshToken,
            });
            // Logout or another tab's login may have changed the session while waiting.
            if (
                generation !== sessionGeneration ||
                localStorage.getItem('refresh_token') !== refreshToken
            )
                return false;
            storeTokens(tokens);
            return true;
        } catch (error) {
            if (error.code === 'invalid_grant') {
                if (
                    generation === sessionGeneration &&
                    localStorage.getItem('refresh_token') === refreshToken
                )
                    clearSession();
                return false;
            }
            throw error;
        } finally {
            refreshPromise = null;
        }
    })();
    return refreshPromise;
}

function base64url(bytes) {
    return btoa(String.fromCharCode(...bytes))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
}

export async function startLogin(page = 'login') {
    const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
    const state = base64url(crypto.getRandomValues(new Uint8Array(32)));
    const challenge = base64url(
        new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))),
    );
    const redirectUri = window.location.origin + '/callback.html';
    sessionStorage.setItem(
        'oauth_transaction',
        JSON.stringify({ verifier, state, redirectUri, createdAt: Date.now() }),
    );
    const params = new URLSearchParams({
        client_id: config.clientId,
        response_type: 'code',
        scope: 'email openid profile',
        redirect_uri: redirectUri,
        state,
        code_challenge: challenge,
        code_challenge_method: 'S256',
    });
    window.location.href = `${config.cognitoDomain}/${page === 'signup' ? 'signup' : 'login'}?${params}`;
}

export async function completeLogin() {
    const params = new URLSearchParams(window.location.search);
    const transaction = JSON.parse(sessionStorage.getItem('oauth_transaction') || 'null');
    sessionStorage.removeItem('oauth_transaction');
    window.history.replaceState({}, '', window.location.pathname);
    if (
        !transaction ||
        !params.get('state') ||
        params.get('state') !== transaction.state ||
        Date.now() - transaction.createdAt > 10 * 60 * 1000 ||
        !params.get('code') ||
        params.has('error')
    ) {
        throw new Error('Invalid or expired login response. Please log in again.');
    }
    const tokens = await requestTokens({
        grant_type: 'authorization_code',
        code: params.get('code'),
        redirect_uri: transaction.redirectUri,
        code_verifier: transaction.verifier,
    });
    if (!tokens.refresh_token) throw new Error('Login did not return a refresh token');
    clearSession();
    storeTokens(tokens);
}
