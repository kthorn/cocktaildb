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

## Dispatch 2 — Paseo Claude Opus 5 high, Plan Mode

- Workspace: `wks_0da1e71c03f7622c`; agent: `c313a1db-f789-4ee9-a488-1bacdae24771`.
- Provider diagnostic ready; model registry confirmed high effort. Completed idle, exactly one RESULT marker.
- Report: `/tmp/vite-opus-review.GfN4WI.md`.
- Result: findings; refinement not converged.
- Fix: explicitly place stable public files/icons in public/ and test webmanifest icon references; metadata stays outside the served tree.
- Fix: define type-aware CSS manifest handling based on the pinned Vite's actual output. Do not accept the reviewer's unverified claim that every CSS-only entry necessarily emits an empty JS sibling.
- Simplification: preserve relative config imports in source/tests; externalize the exact module and map its built URL instead of rewriting Node tests. Verify built import text.
- Fix: manifest staged after delete-enabled API sync and before image build, only in remote release context.
- Fix: ignore node_modules; select mpa app type; specify disposable configured preview copy.
- Fix: include standalone Caddy deploy path, stable web-root symlink handling, and concrete formatting/documentation targets.
- Existing tests must retain coverage when updating hardcoded task/header/output assertions; no assertion deletion to hide failures.
- Do not rely on the reviewer's unverified claim that Ansible template creates missing parent directories: deployment staging must create runtime-config parent directories explicitly.

## Dispatch 3 — Kimi K3 max

- Workflow: `67a96c42-4dbc-4470-9b4a-835e277a99b6`; child: `08a71a04-c975-435a-958a-9925e6a87cda`.
- Report: `/tmp/vite-kimi-review.kfSUA9.md`.
- Result: findings, no critical blockers.
- Reject claimed proxy-origin contradiction: browser requests through Vite remain on Vite's origin. Clarified root-absolute source URLs and that direct browser access to backend-port HTML is unsupported; no origin-injection machinery added.
- Clarify exact CSS and JS template entry keys, executable module tags, and per-template inheritance.
- Reject claimed appUrl change: appUrl intentionally stays localhost:8000; apiUrl remains remote, not a remote API on local port 8000. Made that distinction explicit.
- Clarify unchanged webmanifest contents; add relocated robots/llms Git ignore exceptions identified during parent synthesis.

Next: claim next roster slot and re-review amended subject. No application implementation is authorized yet.
