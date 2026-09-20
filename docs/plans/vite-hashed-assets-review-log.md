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

## Dispatch 4 — Qwen 3.8 max, failed; provisional findings triaged

- Workflow ad7dfb91-e96b-4482-8dee-3fb1a3948442; child 13a4fb25-ee40-4729-b462-8ae3c0c32a72 timed out after 1800000ms.
- Provisional report: /tmp/vite-qwen-review.nzZ2RW.md. This is useful evidence, not a completed review or clean gate.
- User-authorized resume ed06b532-0d21-4d25-b5f4-e3279a4d5ca1 failed before startup confirmation: `Timed out after 30000ms waiting for runner startup control 'confirm'`. No child session persisted; no replacement verdict.
- Working-tree snapshot after resume failure: /tmp/vite-review-startup-failure.KNbkCQ. Shared checkout was chore/format-yaml-hooks at 45664a96f9b03f937d62bcae88a561323ff32a08; unrelated changes left untouched.
- User approved local triage and subsequent independent review through the same governed protocol. Doctor reports async support/filesystem available, but that is not proof a new child can launch.
- Fix: explicitly require fresh-checkout/config-absent builds and externalization before filesystem resolution.
- Clarify: retain typeless root, document Node syntax detection rather than add another package solely for warnings; check both CJS and ESM.
- Fix: resolve manifest relative to package path; preserve cwd-independent page tests.
- Clarify: all new cutover phases stay inside deploy-cutover.sh and the existing lifecycle lock; update both operation and playbook-shape tests.
- Reject claim Caddy header cannot match response status: official header documentation shows `match status 2xx` and automatic deferred evaluation (https://caddyserver.com/docs/caddyfile/directives/header). Require validation against deployed version and real-server checks.
- Fix: exclude hashed paths from media cache matcher as well as JS/CSS matchers.
- Remove redundant Docker-ignore exception requirement; retain packaged-manifest verification.
- appUrl remains a preserved public field, not a new redirect behavior.
- Clarify atomic symlink rename and prune only explicitly recorded frontend-owned paths, never migration markers or arbitrary release-directory entries.

## Dispatch 5 — Grok 4.6 high, tooling contract failed

- Workflow 172b1195-972a-422f-a9c5-0ce61c98be78; child cdf6907b-4303-4e9c-a6b8-9d5fe477c6b4.
- Provisional output /tmp/vite-review-pass5.hb6Jvl.md reported clean, but the run failed: `Agent 'plan-reviewer' requested unavailable child tools: lsp_navigation, ast_grep_search.` This is not a passed review.
- Snapshot /tmp/vite-review-tools-failure.DYcXgt captured the shared checkout on chore/format-yaml-hooks at cb1e43e. No automatic model or protocol fallback was taken.

## Reconciliation after merged PRs — 2026-09-20

- User authorized an isolated workspace on current main. Created `/home/kurtt/cocktaildb/.worktrees/vite-assets`, branch `feat/vite-assets`, from origin/main at 0fd4cb0; restored only this log and the spec from wip/vite-docs-triage-2026-09-19 (cb1e43e).
- Shared checkout and unattributed changes were not modified. Parked draft refs remain available.
- Reviewed upstream changes: retain Docker cleanup from #73 separately from frontend retention; preserve #75 single-source configuration, #77 recipe identity and #78 Prettier/shfmt policy. Added explicit reconciliation section to spec.
- Baseline: `python -m pytest tests/test_group_inventory_deploy.py tests/test_deploy_config_sources.py tests/test_caddy_cache_headers.py tests/test_smoke_test_script.py --no-cov -q` using the cocktaildb environment: **40 passed**, three dependency deprecation warnings.
- Only docs changed. No application implementation or production deployment occurred.

Next: repair the reviewer tool-loading prerequisite before re-reviewing the reconciled subject. Failed dispatches remain failed; neither provisional report nor successful baseline tests substitute for independent review completion. User approval and implementation planning remain pending.
