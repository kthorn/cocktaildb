# Vite hashed-assets design refinement

Subject: `docs/superpowers/specs/2026-09-19-vite-hashed-assets-design.md`

## Dispatch 1 — Grok 4.6 high

- User authorized replacing unavailable `opencode-go/grok-4.5:high` with `opencode-go/grok-4.6:high`; persistent settings roster and global AGENTS guidance updated.
- Workflow: `ecfb965b-6e2f-4214-9eb3-a7302c7cc375`; child: `493a7d49-a353-4adb-a00d-b4d5d023204b`.
- Report: `/tmp/vite-design-review.4kG9Kp.md`.
- Result: findings; refinement not converged.

### Dispositions

1. Reject claimed root-absolute CSS blocker: Vite's guide explicitly resolves absolute source URLs against project root and processes HTML stylesheet links (<https://vite.dev/guide/>). Clarified source CSS must stay out of public directory; retain actual-build coverage.
2. User accepts a breaking first deployment. Remove legacy serving bridge; retain old directory only as rollback input.
3. Clarify status-aware immutable headers, HTTP/domain parity, and stripped asset path/storage layout; retain real-Caddy tests.
4. Omit root module type, use vite.config.mjs, preserve CJS tests; explicitly unignore npm manifest/lockfile.
5. User approved retaining localhost:8000 and remote dev API. Local SSR integration remains optional on a separate backend port.
6. Dedicated asset mode independent of application environment; router-only tests explicitly select source mode.
7. Make unresolved-publication marker a hard deployment/cleanup gate with identity reconciliation.
8. Pin staged manifest to api/frontend-manifest.json and require image-content verification.
9. Retain existing initialize-once acceptance checks. No speculative module rewrite.
10. Clarify ingredient/404 template CSS inheritance.
11. Name existing smoke script and tests for built-reference migration.
12. Existing config generators must use JSON serialization consistently; no new configuration service.
13. Shared asset directory created before Caddy restart.
14. Existing two-Caddy parity requirement retained.
15. D3 remains external and unchanged.

Next: claim next roster slot and re-review amended subject. No application implementation is authorized yet.
