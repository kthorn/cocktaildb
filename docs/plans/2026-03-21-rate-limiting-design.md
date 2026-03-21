# Rate Limiting and Cache Headers Design

## Goal

Protect the single EC2 instance (2 uvicorn workers, 10 DB connections) from being overwhelmed by public API traffic, while keeping the experience frictionless for authenticated users. This is a prerequisite before listing the API in public directories.

## Threat model

Runaway scrapers and overeager AI agents — legitimate-but-heavy automated traffic. Not DoS protection (that would require Caddy-level or AWS-level controls, which can be added later if needed).

## Approach: `slowapi` with auth-aware exemption

Use [`slowapi`](https://github.com/laurentS/slowapi) (FastAPI-friendly wrapper around `limits`) with in-memory storage. No Redis needed for a single-instance deployment.

### Rate limit tiers

| Tier | Who | Limit | Rationale |
|------|-----|-------|-----------|
| Authenticated | JWT present | No limit | Authenticated users are site owners/editors |
| Anonymous read | Public GET requests | 60/minute per IP | ~1 req/sec sustained; enough for browsing or moderate scripting |
| Anonymous write | Public POST/PUT/DELETE | N/A | All write routes already require auth |

### Key function

The rate limit key function determines whether to apply limits:

1. Check for `Authorization: Bearer <token>` header
2. If present and valid JWT → return an exempt key (no limit applied)
3. Otherwise → return client IP from `X-Real-IP` header (set by Caddy) or fall back to `request.client.host`

### Implementation location

- `Limiter` instance created in `main.py` with a global default of `60/minute`
- No per-route decorators needed — the global default covers all endpoints
- Authenticated users exempted via the key function
- `429 Too Many Requests` response with `Retry-After` header (handled automatically by `slowapi`)

### Why not per-route decorators

All write endpoints require auth (via `require_editor_access` or `require_authentication`). Since authenticated users are exempt from limits, a single global default handles everything. No need to differentiate read vs write limits.

## Cache headers via Caddy

Add `Cache-Control` headers to read-only API responses at the Caddy reverse proxy layer. This reduces repeat fetches from well-behaved clients without touching FastAPI code.

| Path pattern | Cache-Control | Rationale |
|---|---|---|
| `/api/v1/stats`, `/api/v1/analytics/*` | `public, max-age=3600` | Changes infrequently (refreshes on mutation) |
| `GET /api/v1/recipes/*`, `GET /api/v1/ingredients/*` | `public, max-age=300` | Stable but could change |
| `/api/v1/openapi.json` | `public, max-age=86400` | Changes only on deploy |
| POST/PUT/DELETE, `/api/v1/auth/*` | No header | Writes should not be cached |

Implemented as Caddy path matchers and header directives — easy to adjust without redeploying the app.

## What this does NOT cover

- DDoS protection (would need Caddy `rate_limit` plugin or AWS WAF)
- Per-user rate limits for authenticated users (not needed while the only authenticated users are site owners)
- Rate limiting by API key (no API key system exists; could be added later if the API is monetized or gets heavy use from specific consumers)
