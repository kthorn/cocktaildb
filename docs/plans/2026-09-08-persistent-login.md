# Persistent Cognito Login Implementation Plan

**Goal:** Retain browser login for the configured 30-day refresh-token lifetime.

**Architecture:** Use authorization code with S256 PKCE and a per-tab state/verifier. Persist refresh tokens alongside existing tokens; refresh before authenticated requests and on page visibility/periodic checks. Deduplicate refresh within a tab and prevent pending refresh from restoring a logged-out session. Keep transient failures recoverable; clear sessions on invalid_grant. Existing implicit sessions continue until expiry, then require one new login.

**Tech stack:** Vanilla JavaScript, Cognito hosted UI, dependency-free Node tests invoked by pytest.

1. Add failing tests in tests/test_auth_session.js for PKCE, callback state, refresh, failures, logout races, and authenticated requests. Run node tests/test_auth_session.js.
2. Implement session lifecycle in src/web/js/auth.js and share callback handling between callback.html and login.html. Clear all session credentials in logout.html.
3. Await refresh in src/web/js/api.js for ordinary authenticated requests and authenticated search. Keep synchronous UI checks compatible with a refreshable session.
4. Run new tests, existing frontend regression tests, and repository formatting checks. Review the diff for credential leakage and stale-token paths.

No infrastructure change is needed: template.yaml already enables code grants and a 30-day refresh lifetime. Keep implicit grants during migration. Deploy frontend normally; verify real hosted login, refresh, and logout in a browser after deployment.
