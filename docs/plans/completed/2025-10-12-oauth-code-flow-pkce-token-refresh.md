# OAuth Authorization Code Flow with PKCE and Token Refresh Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Replace implicit OAuth flow with authorization code flow + PKCE and implement automatic token refresh to keep users logged in for 30 days without re-authentication.

**Architecture:** Use OAuth 2.0 Authorization Code Flow with PKCE (Proof Key for Code Exchange). Generate cryptographic code verifier/challenge on client, exchange authorization code for tokens (including refresh token) server-side, store refresh token securely in localStorage, automatically refresh access/ID tokens before expiration using stored refresh token.

**Tech Stack:** AWS Cognito, vanilla JavaScript, Web Crypto API (for PKCE), Cognito Token endpoint

---

## Task 1: Create PKCE Utility Module

**Files:**
- Create: `src/web/js/pkce.js`

**Step 1: Create PKCE utility file with code verifier generation**

```javascript
// PKCE (Proof Key for Code Exchange) utilities for OAuth 2.0
// Implements RFC 7636

/**
 * Generate a cryptographically random code verifier
 * Must be 43-128 characters from [A-Z][a-z][0-9]-._~
 */
export function generateCodeVerifier() {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return base64URLEncode(array);
}

/**
 * Generate code challenge from code verifier using SHA-256
 * @param {string} verifier - The code verifier
 * @returns {Promise<string>} The base64url-encoded SHA-256 hash
 */
export async function generateCodeChallenge(verifier) {
    const encoder = new TextEncoder();
    const data = encoder.encode(verifier);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return base64URLEncode(new Uint8Array(hash));
}

/**
 * Base64URL encode (without padding)
 * @param {Uint8Array} buffer - The buffer to encode
 * @returns {string} Base64URL encoded string
 */
function base64URLEncode(buffer) {
    // Convert buffer to base64
    const base64 = btoa(String.fromCharCode(...buffer));
    // Convert to base64url (replace +/= with -_)
    return base64
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=/g, '');
}

/**
 * Store PKCE verifier in session storage (temporary, for callback)
 * @param {string} verifier - The code verifier to store
 */
export function storeCodeVerifier(verifier) {
    sessionStorage.setItem('pkce_code_verifier', verifier);
}

/**
 * Retrieve and remove PKCE verifier from session storage
 * @returns {string|null} The stored code verifier
 */
export function getAndClearCodeVerifier() {
    const verifier = sessionStorage.getItem('pkce_code_verifier');
    sessionStorage.removeItem('pkce_code_verifier');
    return verifier;
}
```

**Step 2: Commit PKCE utilities**

```bash
git add src/web/js/pkce.js
git commit -m "feat(auth): add PKCE utility functions for OAuth code flow"
```

---

## Task 2: Create Token Refresh Module

**Files:**
- Create: `src/web/js/token-refresh.js`

**Step 1: Create token refresh utility with automatic refresh logic**

```javascript
// Token refresh utilities for maintaining user sessions
import config from './config.js';

/**
 * Check if a token is expired or will expire soon
 * @param {string} token - JWT token
 * @param {number} bufferSeconds - Refresh this many seconds before expiration (default 5 min)
 * @returns {boolean} True if token needs refresh
 */
export function needsRefresh(token, bufferSeconds = 300) {
    if (!token) return true;

    try {
        const parts = token.split('.');
        if (parts.length !== 3) return true;

        const payload = JSON.parse(atob(parts[1]));
        const currentTime = Math.floor(Date.now() / 1000);

        // Check if expired or will expire within buffer time
        return !payload.exp || payload.exp < (currentTime + bufferSeconds);
    } catch (e) {
        console.error('Error checking token expiration:', e);
        return true;
    }
}

/**
 * Refresh access and ID tokens using refresh token
 * @returns {Promise<boolean>} True if refresh succeeded
 */
export async function refreshTokens() {
    const refreshToken = localStorage.getItem('refresh_token');

    if (!refreshToken) {
        console.log('No refresh token available');
        return false;
    }

    try {
        // Call Cognito token endpoint
        const response = await fetch(`${config.cognitoDomain}/oauth2/token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                grant_type: 'refresh_token',
                client_id: config.clientId,
                refresh_token: refreshToken,
            }),
        });

        if (!response.ok) {
            console.error('Token refresh failed:', response.status);
            return false;
        }

        const data = await response.json();

        // Update tokens in localStorage
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('id_token', data.id_token);

        // If a new refresh token was issued, update it
        if (data.refresh_token) {
            localStorage.setItem('refresh_token', data.refresh_token);
        }

        console.log('Tokens refreshed successfully');
        return true;
    } catch (error) {
        console.error('Error refreshing tokens:', error);
        return false;
    }
}

/**
 * Start automatic token refresh interval
 * Checks every 4 minutes and refreshes if needed
 */
export function startTokenRefreshInterval() {
    // Check every 4 minutes (tokens valid for 4 hours)
    const intervalMs = 4 * 60 * 1000;

    setInterval(async () => {
        const accessToken = localStorage.getItem('token');

        if (accessToken && needsRefresh(accessToken)) {
            console.log('Access token expiring soon, refreshing...');
            const success = await refreshTokens();

            if (!success) {
                console.log('Token refresh failed, user will need to re-login');
                // Clear tokens to trigger login prompt
                localStorage.removeItem('token');
                localStorage.removeItem('id_token');
                localStorage.removeItem('refresh_token');
                localStorage.removeItem('username');

                // Reload page to show login state
                window.location.reload();
            }
        }
    }, intervalMs);
}
```

**Step 2: Commit token refresh utilities**

```bash
git add src/web/js/token-refresh.js
git commit -m "feat(auth): add token refresh utilities with automatic refresh"
```

---

## Task 3: Update CloudFormation Template for Code Flow

**Files:**
- Modify: `template.yaml:1058-1102`

**Step 1: Remove implicit flow and ensure code flow is supported**

In `template.yaml`, verify the `CognitoUserPoolV3Client` already has `AllowedOAuthFlows` including `code`. The current configuration should already support it (line 1090-1091), but we need to ensure we're not relying on implicit flow.

Current config already has:
```yaml
AllowedOAuthFlows:
  - code
  - implicit
```

This is fine - we can keep both. The client will determine which flow to use.

**Step 2: Verify and commit if any changes needed**

```bash
# No changes needed to template.yaml - it already supports code flow
git status
# If no changes, no commit needed
```

---

## Task 4: Update Login Flow in auth.js

**Files:**
- Modify: `src/web/js/auth.js:1-146`

**Step 1: Import PKCE and token refresh utilities**

At the top of `src/web/js/auth.js` (after line 2), add:

```javascript
import config from './config.js';
import { generateCodeVerifier, generateCodeChallenge, storeCodeVerifier } from './pkce.js';
import { needsRefresh, refreshTokens, startTokenRefreshInterval } from './token-refresh.js';
```

**Step 2: Update login button handler to use code flow**

Replace lines 21-24 in `src/web/js/auth.js`:

```javascript
    // Setup login button
    loginButton.addEventListener('click', async () => {
        // Generate PKCE parameters
        const codeVerifier = generateCodeVerifier();
        const codeChallenge = await generateCodeChallenge(codeVerifier);

        // Store verifier for callback
        storeCodeVerifier(codeVerifier);

        // Redirect to Cognito hosted UI for login with code flow + PKCE
        const params = new URLSearchParams({
            client_id: config.clientId,
            response_type: 'code',  // Changed from 'token' to 'code'
            scope: 'email openid profile',
            redirect_uri: window.location.origin + '/callback.html',
            code_challenge: codeChallenge,
            code_challenge_method: 'S256'
        });

        window.location.href = `${config.cognitoDomain}/login?${params.toString()}`;
    });
```

**Step 3: Update signup button handler to use code flow**

Replace lines 27-32 in `src/web/js/auth.js`:

```javascript
    // Setup signup button (if it exists)
    if (signupButton) {
        signupButton.addEventListener('click', async () => {
            // Generate PKCE parameters
            const codeVerifier = generateCodeVerifier();
            const codeChallenge = await generateCodeChallenge(codeVerifier);

            // Store verifier for callback
            storeCodeVerifier(codeVerifier);

            // Redirect to Cognito hosted UI for signup with code flow + PKCE
            const params = new URLSearchParams({
                client_id: config.clientId,
                response_type: 'code',  // Changed from 'token' to 'code'
                scope: 'email openid profile',
                redirect_uri: window.location.origin + '/callback.html',
                code_challenge: codeChallenge,
                code_challenge_method: 'S256'
            });

            window.location.href = `${config.cognitoDomain}/signup?${params.toString()}`;
        });
    }
```

**Step 4: Start token refresh interval in initAuth**

Add after line 64 in `src/web/js/auth.js` (after the visibilitychange listener):

```javascript
    // Start automatic token refresh
    startTokenRefreshInterval();
```

**Step 5: Commit auth.js updates**

```bash
git add src/web/js/auth.js
git commit -m "feat(auth): update login/signup to use OAuth code flow with PKCE"
```

---

## Task 5: Update isAuthenticated to Support Token Refresh

**Files:**
- Modify: `src/web/js/auth.js:68-101`

**Step 1: Update isAuthenticated to attempt refresh before logout**

Replace the `isAuthenticated` function (lines 68-101):

```javascript
// Check if user is authenticated
export async function isAuthenticated() {
    const token = localStorage.getItem('token');
    const idToken = localStorage.getItem('id_token');

    if (!token || !idToken) {
        return false;
    }

    try {
        // Check if the ID token is expired or expiring soon
        if (needsRefresh(idToken)) {
            console.log('Token expired or expiring, attempting refresh...');
            const refreshed = await refreshTokens();

            if (!refreshed) {
                // Refresh failed, clear tokens
                localStorage.removeItem('token');
                localStorage.removeItem('id_token');
                localStorage.removeItem('refresh_token');
                localStorage.removeItem('username');
                return false;
            }

            // Refresh succeeded, user is still authenticated
            return true;
        }
    } catch (e) {
        console.error('Error checking token expiration:', e);
        // If we can't parse the token, consider it invalid
        localStorage.removeItem('token');
        localStorage.removeItem('id_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('username');
        return false;
    }

    return true;
}
```

**Step 2: Update function to be async**

Note: Since `isAuthenticated` is now async, we need to update all its callers to use `await`.

**Step 3: Update updateAuthUI to handle async isAuthenticated**

Replace the `updateAuthUI` function (lines 40-52) inside `initAuth`:

```javascript
    // Function to update the UI based on auth state
    async function updateAuthUI() {
        if (await isAuthenticated()) {
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
    }
```

**Step 4: Update interval callback to be async**

Replace lines 55-57:

```javascript
    // Check auth state periodically (every 30 seconds) to handle token expiration
    setInterval(async () => {
        await updateAuthUI();
    }, 30000);
```

**Step 5: Update visibility change listener to be async**

Replace lines 60-64:

```javascript
    // Also check when page becomes visible (e.g., switching tabs)
    document.addEventListener('visibilitychange', async () => {
        if (!document.hidden) {
            await updateAuthUI();
        }
    });
```

**Step 6: Commit isAuthenticated updates**

```bash
git add src/web/js/auth.js
git commit -m "feat(auth): update isAuthenticated to attempt token refresh before logout"
```

---

## Task 6: Update Logout to Clear Refresh Token

**Files:**
- Modify: `src/web/js/auth.js:134-146`

**Step 1: Update logout function to clear refresh token**

Replace the `logout` function (lines 135-146):

```javascript
// Log the user out
export function logout() {
    // Clear all tokens from localStorage
    localStorage.removeItem('token');
    localStorage.removeItem('id_token');
    localStorage.removeItem('refresh_token');  // Add this line
    localStorage.removeItem('username');

    // Redirect to Cognito logout
    window.location.href = `${config.cognitoDomain}/logout?client_id=${config.clientId}&logout_uri=${encodeURIComponent(window.location.origin + '/logout.html')}`;

    // Note: The page will be redirected, so the following code won't execute
    // window.location.reload();
}
```

**Step 2: Commit logout update**

```bash
git add src/web/js/auth.js
git commit -m "feat(auth): clear refresh token on logout"
```

---

## Task 7: Update Callback to Exchange Code for Tokens

**Files:**
- Modify: `src/web/callback.html:1-65`

**Step 1: Replace callback.html entirely with code exchange logic**

```html
<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Logging in...</title>
        <script type="module">
        import config from './js/config.js';
        import { getAndClearCodeVerifier } from './js/pkce.js';

        // Parse URL query parameters (code is in query, not hash)
        function parseQueryParams() {
            const params = new URLSearchParams(window.location.search);
            return Object.fromEntries(params.entries());
        }

        // Exchange authorization code for tokens
        async function exchangeCodeForTokens(code, codeVerifier) {
            try {
                const response = await fetch(`${config.cognitoDomain}/oauth2/token`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: new URLSearchParams({
                        grant_type: 'authorization_code',
                        client_id: config.clientId,
                        code: code,
                        redirect_uri: window.location.origin + '/callback.html',
                        code_verifier: codeVerifier,
                    }),
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    throw new Error(`Token exchange failed: ${response.status} - ${errorText}`);
                }

                return await response.json();
            } catch (error) {
                console.error('Error exchanging code for tokens:', error);
                throw error;
            }
        }

        document.addEventListener('DOMContentLoaded', async () => {
            try {
                // Get the authorization code from the URL
                const params = parseQueryParams();

                if (!params.code) {
                    throw new Error('No authorization code found in the response');
                }

                // Get the PKCE code verifier from session storage
                const codeVerifier = getAndClearCodeVerifier();

                if (!codeVerifier) {
                    throw new Error('No PKCE code verifier found. Please try logging in again.');
                }

                document.getElementById('status').textContent = 'Exchanging authorization code for tokens...';

                // Exchange code for tokens
                const tokens = await exchangeCodeForTokens(params.code, codeVerifier);

                // Store tokens in localStorage
                localStorage.setItem('token', tokens.access_token);
                localStorage.setItem('id_token', tokens.id_token);
                localStorage.setItem('refresh_token', tokens.refresh_token);  // Store refresh token!

                // Parse the ID token to get user info
                const payloadBase64 = tokens.id_token.split('.')[1];
                const payload = JSON.parse(atob(payloadBase64));

                // Store username (preferred_username or email or sub)
                const username = payload.preferred_username || payload.email || payload.sub;
                localStorage.setItem('username', username);

                document.getElementById('status').textContent = 'Login successful. Redirecting...';

                // Redirect back to the main page
                setTimeout(() => {
                    window.location.href = 'index.html';
                }, 1500);
            } catch (error) {
                console.error('Error processing authentication response:', error);
                document.getElementById('status').textContent = `Login failed: ${error.message}`;

                // Add a button to try again
                const button = document.createElement('button');
                button.textContent = 'Back to Home';
                button.style.marginTop = '1rem';
                button.style.padding = '0.5rem 1rem';
                button.style.cursor = 'pointer';
                button.addEventListener('click', () => {
                    window.location.href = 'index.html';
                });
                document.getElementById('container').appendChild(button);
            }
        });
    </script>
    </head>
    <body>
        <div id="container" class="login-callback">
            <h1>Authentication</h1>
            <p id="status">Processing login...</p>
        </div>
        <script type="module" src="js/common.js"></script>
    </body>
</html>
```

**Step 2: Commit callback.html update**

```bash
git add src/web/callback.html
git commit -m "feat(auth): exchange authorization code for tokens including refresh token"
```

---

## Task 8: Test the Complete Flow Locally

**Files:**
- None (testing only)

**Step 1: Start local development server**

```bash
cd src/web
python -m http.server 8000
```

Expected: Server starts on http://localhost:8000

**Step 2: Test login flow**

1. Open browser to http://localhost:8000
2. Click "Login" button
3. Should redirect to Cognito with `code_challenge` parameter in URL
4. Log in with test credentials
5. Should redirect to callback.html
6. Callback should exchange code for tokens
7. Should store access_token, id_token, AND refresh_token in localStorage
8. Should redirect to index.html
9. Should show logged-in state

**Step 3: Verify tokens in localStorage**

Open browser DevTools → Application → Local Storage:
- Should see: `token` (access token)
- Should see: `id_token`
- Should see: `refresh_token` ← **NEW!**
- Should see: `username`

**Step 4: Test automatic token refresh**

Option A: Wait 4 hours (not practical)
Option B: Manually expire token:
1. In DevTools console: `localStorage.setItem('token', 'expired')`
2. Wait 30 seconds for interval check OR switch browser tabs
3. Check DevTools console for "Token expired or expiring, attempting refresh..."
4. Verify new token in localStorage

**Step 5: Test logout**

1. Click "Logout" button
2. Should clear all tokens including refresh_token
3. Should redirect to Cognito logout page
4. Should redirect back to app showing logged-out state

---

## Task 9: Deploy and Test in Dev Environment

**Files:**
- None (deployment and testing)

**Step 1: Build and deploy to dev**

```bash
scripts\deploy.bat dev
```

Expected: Stack updates successfully with no errors

**Step 2: Get dev CloudFront URL from outputs**

```bash
aws cloudformation describe-stacks --stack-name cocktail-db-dev --query "Stacks[0].Outputs[?OutputKey=='CloudFrontURL'].OutputValue" --output text
```

Expected: Returns CloudFront URL

**Step 3: Test complete authentication flow in dev**

1. Open CloudFront URL
2. Click "Login"
3. Complete login flow
4. Verify all 3 tokens stored in localStorage
5. Verify user can access authenticated endpoints
6. Test logout

**Step 4: Verify Cognito User Pool Client configuration**

```bash
aws cognito-idp describe-user-pool-client --user-pool-id <USER_POOL_ID> --client-id <CLIENT_ID>
```

Expected: Should show:
- `AllowedOAuthFlows` includes `code`
- `AccessTokenValidity: 4`
- `IdTokenValidity: 4`
- `RefreshTokenValidity: 30`

---

## Task 10: Update API Client to Handle Token Refresh

**Files:**
- Modify: `src/web/js/api.js` (if exists, otherwise check for API client code)

**Step 1: Find API client code**

```bash
grep -r "getUserInfo\|getToken" src/web/js/ --include="*.js"
```

**Step 2: Update API request methods to ensure fresh tokens**

In the main API client class/module, before making API requests, call:

```javascript
import { isAuthenticated } from './auth.js';

// Before making authenticated API request:
if (!(await isAuthenticated())) {
    throw new Error('Not authenticated');
}

// Then proceed with request using fresh token from localStorage
```

**Step 3: Commit API client updates**

```bash
git add src/web/js/api.js
git commit -m "feat(auth): ensure API client uses fresh tokens via isAuthenticated"
```

---

## Success Criteria

✅ Login redirects with `response_type=code` and `code_challenge` parameters
✅ Callback exchanges code for tokens (access + id + refresh)
✅ All 3 tokens stored in localStorage
✅ Access token automatically refreshes before expiration
✅ User stays logged in for 30 days with automatic refresh
✅ After 30 days, refresh token expires and user must re-login
✅ Logout clears all tokens including refresh token
✅ No console errors during login/refresh/logout flows

---

## References

- OAuth 2.0 Authorization Code Flow: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1
- PKCE (RFC 7636): https://datatracker.ietf.org/doc/html/rfc7636
- AWS Cognito Token Endpoint: https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html
- Web Crypto API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API
