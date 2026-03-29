# AUTH_SSO_STANDARD.md

**Standard ID:** OPS-STD-001
**Version:** 1.0
**Status:** Draft
**Created:** 2026-03-14
**Scope:** All OnPulse FastAPI backends and Next.js frontends
**Authoritative RFCs:** RFC 9700 (OAuth 2.0 Security BCP), RFC 9068 (JWT Access Token Profile), RFC 8725 (JWT BCP), RFC 7662 (Token Introspection), RFC 7009 (Token Revocation), RFC 8037 (EdDSA for JOSE)

---

## 1. Architecture

### 1.1 Identity Provider

| Decision | Standard |
|----------|----------|
| IdP selection | Authentik (self-hosted, Docker-native) |
| Protocol | OpenID Connect (OIDC) over OAuth 2.0 |
| Deployment | Dedicated `docker-compose.yml` stack with persistent database volumes |
| Discovery | All services MUST use `/.well-known/openid-configuration` for endpoint discovery |

**Why Authentik over Keycloak:** Authentik is Python/Django + Go, Docker-native, ~200-300MB RAM vs Keycloak's 700MB-1GB JVM baseline. Visual policy builder suits a 1-2 person team. Full OIDC/OAuth2/SAML support.

**Why not Zitadel:** API-first/Terraform configuration model adds friction for teams that prefer visual administration.

### 1.2 Topology: Hybrid Gateway + Distributed Validation

```
┌─────────────┐     ┌──────────┐     ┌──────────────────┐
│   Browser    │────▶│  Nginx   │────▶│  FastAPI / Next.js│
│  (httpOnly   │     │ (edge)   │     │  (app boundary)   │
│   cookies)   │     └──────────┘     └──────────────────┘
└─────────────┘          │                     │
                    Coarse-grained:       Fine-grained:
                    - Rate limiting       - JWT signature validation
                    - IP filtering        - Audience/issuer checks
                    - CORS termination    - RBAC/scope enforcement
                    - Header sanitisation - Business-logic authz
```

**MUST:** Nginx handles coarse-grained edge security (rate limiting, CORS preflight, IP filtering). Nginx is the authoritative layer for CORS `Access-Control-Allow-Origin` headers and preflight responses. Application-layer CORS configuration MUST NOT contradict Nginx CORS policy — drift is prevented by validating both configs reference the same allowed-origins list (environment variable or shared config file).
**MUST:** Each FastAPI/Next.js service independently validates tokens at the application boundary.
**MUST NOT:** Push fine-grained RBAC or business logic into Nginx.
**MUST NOT:** Treat gateway auth as sufficient without application-layer checks (RFC 9700 warns against trusting reverse proxy headers blindly).

### 1.3 Canonical Request Path

The standard browser-to-backend request path is **Next.js BFF (Backend-for-Frontend)**:

```
Browser  ──cookie──▶  Next.js (BFF)  ──Bearer token──▶  FastAPI
                      Auth.js manages                    Validates JWT
                      session cookies                    via JWKS
                      + OIDC flows                       Enforces RBAC
```

- **Browser → Next.js:** httpOnly session cookies (set by Auth.js). No tokens exposed to client JavaScript.
- **Next.js → FastAPI:** Server-side API calls using the user's access token as a Bearer token in the `Authorization` header. Next.js acts as a confidential client.
- **Service → Service:** OAuth 2.0 Client Credentials Grant with dedicated service accounts (see Section 2.2).

**MUST NOT:** Send Bearer tokens directly from browser JavaScript to FastAPI. All browser traffic flows through Next.js.
**MUST NOT:** Implement a separate session system in FastAPI for browser users — Next.js is the session authority for browser traffic.

### 1.3 Token Strategy

**Level 1 — Baseline (all services):**
- Short-lived JWT access tokens (15 min TTL) validated locally via JWKS
- Rotating opaque refresh tokens managed by Authentik
- httpOnly/Secure/SameSite cookies for browser sessions

**Level 2 — Enhanced (admin actions, payments, data export):**
- Token introspection (RFC 7662) for immediate revocation checks
- Sender-constrained tokens via DPoP (RFC 9449) or mTLS (RFC 8705) when IdP supports it

---

## 2. Authentication Flows

### 2.1 Browser-Based Authentication (Next.js → Authentik)

| Requirement | Standard |
|-------------|----------|
| Flow | Authorization Code + PKCE (S256 challenge method) |
| Client library | Auth.js (next-auth) v5.x configured as OIDC client |
| Session storage | Server-set httpOnly + Secure + SameSite=Lax cookies |
| Token handling | Access/refresh tokens MUST NOT be exposed to client JavaScript |

**MUST:** Use Authorization Code + PKCE for all browser flows (RFC 9700).
**MUST NOT:** Use OAuth Implicit flow — removed from OAuth 2.1 direction (RFC 9700).
**MUST NOT:** Use ROPC/direct password grant — exposes credentials to apps (RFC 9700).

### 2.2 Service-to-Service Authentication (Backend → Backend)

| Requirement | Standard |
|-------------|----------|
| Flow | OAuth 2.0 Client Credentials Grant (RFC 6749 §4.4) |
| Identity | Dedicated Authentik Service Account per calling service |
| Credentials | `client_id` + `client_secret` from Docker Secrets (`/run/secrets/`) |
| Token caching | Cache access token in memory until ~30s before expiry |
| Validation | Receiving service validates `aud` claim matches its own `API_AUDIENCE` |

**MUST:** Each service has its own Authentik Service Account with scoped permissions.
**MUST NOT:** Share a single service account across multiple callers.
**MUST NOT:** Use static API keys for internal service-to-service calls as the default pattern.

### 2.3 External API Keys (Stripe, Sentry, Cal.com, etc.)

**MUST:** Store via Docker Secrets mounted at `/run/secrets/<secret_name>` with 0400 permissions.
**MUST:** Load via Pydantic `BaseSettings` with `secrets_dir="/run/secrets"`.
**MUST NOT:** Pass secrets via `docker-compose.yml` `environment:` block (exposed by `docker inspect`).
**MUST NOT:** Commit `.env` files containing secrets to version control.

---

## 3. SSO Session Lifecycle

### 3.1 Session Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Access token TTL | 15 minutes | Limits exposure window; refresh handles UX |
| Refresh token | Rotating, opaque | Replay detection: reuse invalidates entire token family |
| ID token | Used only at login for identity claims | Not for API authorization |
| Session cookie | httpOnly, Secure, SameSite=Lax, Path=/ | XSS-immune, CSRF-resistant |

### 3.2 Refresh Token Rotation

**MUST:** Enable strict refresh token rotation in Authentik.
- Each refresh request issues a new refresh token and invalidates the previous one
- If a previously-used refresh token is presented (replay), Authentik MUST revoke the entire token family and force re-authentication

### 3.3 Logout

**SHOULD:** Implement OIDC Back-Channel Logout 1.0 specification. Promote to MUST once the deployed IdP (Authentik) and all relying parties are validated to support it in GA (not preview).

Logout flow:
1. User clicks logout → Next.js clears local session cookie
2. Next.js initiates RP-Initiated Logout with Authentik
3. Authentik sends signed Logout Token (HTTP POST) to all registered relying parties' back-channel logout URIs
4. Each RP validates the Logout Token (`iss`, `aud`, `sid`), destroys the matching local session

**MUST:** Each Next.js app exposes `/api/auth/backchannel-logout` route handler.
**MUST:** Store `sid` (Session ID) from ID token in local session store (Redis/DB) at login.
**MUST:** On security events (password change, account compromise), revoke all refresh tokens via RFC 7009.
**MUST NOT:** Rely on Front-Channel Logout — fails on browser close, network drops, tracking protection.

---

## 4. FastAPI Backend Standards

### 4.1 Authentication Enforcement: Default-On

**MUST** use one of these patterns to make auth "default on":

**Pattern A — Global dependency:**
```python
app = FastAPI(dependencies=[Depends(verify_token)])
# Then create a separate public_router for /health, /ready, /docs
```

**Pattern B — Protected router convention:**
```python
protected_router = APIRouter(dependencies=[Depends(verify_token)])
public_router = APIRouter()  # Only for /health, /ready
```

**MUST NOT:** Rely on developers remembering to add `Depends(verify_token)` to each route individually.

### 4.2 Token Validation Dependency Chain

```python
# Pseudocode — implement in shared auth library
async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> TokenPayload:
    """Validate JWT from Authorization: Bearer header."""
    token = credentials.credentials
    payload = jwt.decode(
        token,
        key=await get_jwks_public_key(token),  # Dynamic JWKS fetch
        algorithms=ALLOWED_ALGORITHMS,          # Explicit allowlist
        audience=settings.API_AUDIENCE,         # Audience restriction
        issuer=settings.OIDC_ISSUER,           # Issuer validation
    )
    return TokenPayload(**payload)

async def get_current_user(
    token: TokenPayload = Depends(verify_token)
) -> User:
    """Return typed User model from validated token."""
    return User(
        id=token.sub,
        roles=token.get("roles", []),
        scopes=token.get("scope", "").split(),
    )
```

**MUST:** Authentication middleware MUST NOT block the event loop. Network I/O (JWKS fetch, token introspection, IdP calls) MUST use async I/O. CPU-bound crypto (signature verification) SHOULD use async wrappers or be benchmarked to confirm sub-millisecond execution before inlining in `async def`.
**MUST:** Validate `iss`, `aud`, `exp`, and signature on every request.
**MUST:** Enforce algorithm allowlist in `jwt.decode()` — prevents Algorithm Confusion (RS256→HS256) attacks (RFC 8725).
**MUST:** Reject `alg: "none"`.

### 4.3 RBAC / Scope Enforcement

**Claims contract (managed in Authentik):**
- Scopes follow namespace convention: `app:<service>:<action>` (e.g., `app:revenue-intelligence:read`)
- Roles/groups in Authentik map to scopes included in access tokens
- Each FastAPI app defines `API_AUDIENCE` that MUST match token `aud`

```python
# Route-level scope enforcement
@router.get("/admin/settings", dependencies=[Security(get_current_user, scopes=["admin:write"])])
async def admin_settings(): ...
```

**MUST:** Use audience restriction to limit token scope to intended API(s) (RFC 9700).

### 4.4 Shared Auth Library

**MUST:** Package auth models, JWKS fetching, token validation, and RBAC dependencies into a shared internal library (e.g., `onpulse-auth-core`).

**Distribution:** Git over SSH with version pinning via tags:
```
pip install git+ssh://git@github.com/onpulse/onpulse-auth-core.git@v1.0.0
```

**MUST NOT:** Duplicate auth logic across repositories.
**MUST NOT:** Use a private PyPI server (unnecessary infrastructure for a small team).

### 4.5 Error Responses

**MUST:** Return generic error messages to prevent user enumeration:
- `401 Unauthorized` — do not distinguish between "user not found" and "wrong password"
- `403 Forbidden` — insufficient permissions
- `422 Unprocessable Entity` — for validation errors only

---

## 5. Next.js Frontend Standards

### 5.1 Defense-in-Depth: Data Access Layer (DAL) Pattern

Authentication MUST be enforced at two layers:

**Layer 1 — Middleware (optimistic routing):**
- Checks for cookie presence only (fast, runs at edge)
- Redirects to `/login` if no session cookie
- MUST NOT be the sole authorization mechanism (ref: CVE-2025-29927 middleware bypass)

**Layer 2 — Server Components / Server Actions / Route Handlers (secure validation):**
- Calls `verifySession()` DAL function before any data access or mutation
- Validates token payload, checks roles, verifies session not revoked
- Wrap in `React.cache()` to memoize per-request (prevents redundant DB lookups in nested components)

```typescript
// lib/auth.ts
import { cache } from 'react';
import { cookies } from 'next/headers';

export const verifySession = cache(async () => {
  const session = cookies().get('session');
  if (!session) redirect('/login');
  // Validate token, check roles, verify not revoked
  return await validateAndDecodeSession(session.value);
});
```

**MUST:** Server Actions call `verifySession()` at the start of every mutation.
**MUST:** Route Handlers validate session in-handler, not only via middleware.
**MUST:** Server Components call `verifySession()` before fetching protected data.

### 5.2 Default-Deny Routing

**MUST:** Use negative-lookahead matcher in `middleware.ts` to protect all routes by default:

```typescript
export const config = {
  matcher: ['/((?!api/public|_next/static|_next/image|favicon.ico|login).*)'],
};
```

New routes are automatically protected. Developers MUST explicitly modify the matcher to expose public endpoints.

### 5.3 Session Storage

**MUST:** httpOnly + Secure + SameSite cookies (set server-side).
**MUST NOT:** Store access tokens, refresh tokens, or session data in `localStorage` or `sessionStorage` (XSS-vulnerable).
**MUST:** Use Auth.js (next-auth v5.x) to automatically enforce secure cookie policies.
**MUST:** Maintain Next.js on the latest supported patch version. Security advisories MUST be applied within 48 hours of publication for Critical/High severity, and within 7 days for Medium. Do not pin to a static minimum version floor — advisory history shows successive patches supersede earlier fixes.

### 5.4 CSRF Protection

**MUST:** Set `SameSite=Lax` or `SameSite=Strict` for session cookies.
**MUST:** For state-changing operations, enforce at least one of:
  - CSRF token pattern (synchroniser token or double-submit)
  - Origin/Referer header validation as defense-in-depth
**MUST NOT:** Use GET for state-changing operations.

---

## 6. Cryptographic Standards

### 6.1 Algorithm Selection

| Priority | Algorithm | Use Case |
|----------|-----------|----------|
| **Preferred** | EdDSA (Ed25519) | All new token signing — deterministic (no RNG dependency), fastest verification |
| **Acceptable** | ES256 (P-256 ECDSA) | When IdP/library doesn't support EdDSA end-to-end |
| **Baseline** | RS256 (RSA-2048+) | Required for RFC 9068 interoperability; acceptable for existing systems |
| **Prohibited** | HS256 (symmetric) for cross-service tokens | Shared-secret model expands blast radius |
| **Prohibited** | `none` | Must be rejected unconditionally |

**MUST:** Configure Authentik to sign tokens with EdDSA (Ed25519) when supported.
**MUST:** Set explicit `algorithms=` allowlist in all `jwt.decode()` calls.
**MUST:** Use `typ: at+jwt` header for access tokens per RFC 9068 when IdP supports it.

### 6.2 Key Management: JWKS

**MUST:** Use JWKS (JSON Web Key Sets) for public key distribution.
- Authentik publishes keys at `/.well-known/jwks.json`
- FastAPI services fetch and cache JWKS in memory
- On unknown `kid` (Key ID) in token header → invalidate cache, re-fetch JWKS (zero-downtime rotation)

**MUST NOT:** Hardcode public keys in environment variables or application code.
**MUST NOT:** Share signing keys across services.

### 6.3 Token Replay Prevention

| Mechanism | Level |
|-----------|-------|
| Short TTL (15 min) + refresh rotation | Level 1 (all services) |
| Token introspection (RFC 7662) | Level 2 (high-assurance endpoints) |
| DPoP sender-constraining (RFC 9449) | Level 3 (future hardening) |
| mTLS sender-constraining (RFC 8705) | Level 3 (future hardening) |

---

## 7. Cross-Cutting Security Controls

### 7.1 CORS

**MUST:** Explicit origin allowlist in production — no `*` for authenticated APIs.
**MUST:** If `allow_credentials=true`, origin MUST NOT be wildcard.
**MUST:** Nginx handles OPTIONS preflight directly (204 No Content) to avoid consuming FastAPI workers.
**MUST:** FastAPI `CORSMiddleware` configured with explicit `allow_origins` matching known frontend domains.

### 7.2 Rate Limiting

**MUST:** Nginx `limit_req_zone` keyed on `$binary_remote_addr`:
- Auth endpoints (`/api/auth/*`, `/token`): strict limit (e.g., 5r/m)
- General API endpoints: higher threshold (e.g., 20r/s)
- Use `burst` + `nodelay` for legitimate spike absorption

**MUST:** Authentik configured with progressive delays (exponential backoff) after failed login attempts.
**MUST NOT:** Use absolute account lockout as the primary brute-force defense (creates DoS vector — attacker locks out legitimate users).

### 7.3 Audit Logging

**MUST:** Log all security events in structured JSON format:

```json
{
  "timestamp": "2026-03-14T10:30:00Z",
  "event_name": "AUTH_SUCCESS|AUTH_FAILURE|TOKEN_REFRESH|TOKEN_REVOKE|M2M_GRANT|SESSION_DESTROY",
  "actor": {
    "user_id": "...",
    "session_id": "...",
    "ip_address": "..."
  },
  "status": "success|failure",
  "error": null,
  "service": "ers|command-centre|evgp-1|..."
}
```

**MUST:** Nginx forwards true client IP via `X-Forwarded-For`.
**MUST:** Uvicorn configured with `--forwarded-allow-ips` trusting only the Nginx container IP.

### 7.4 Reverse Proxy Header Sanitisation

**MUST:** Nginx sanitises inbound headers — strip any client-supplied `X-Forwarded-For`, `X-Real-IP`, or internal routing headers before setting its own (RFC 9700).
**MUST:** Protect proxy ↔ upstream link against eavesdropping/injection (internal Docker network satisfies this for same-host deployments).

---

## 8. Prohibited Anti-Patterns

| Anti-Pattern | Risk | Standard Violation |
|-------------|------|-------------------|
| Custom "SSO" via shared symmetric JWT secret across repos | Blast radius expansion, weak-key confusion | §1.2, §6.1 |
| OAuth Implicit flow or tokens in URL fragments | Token leakage | §2.1 (RFC 9700) |
| ROPC/direct password grant | Credential exposure to apps, incompatible with MFA | §2.1 (RFC 9700) |
| Storing tokens in `localStorage`/`sessionStorage` | XSS exfiltration | §5.3 |
| Middleware-only authorization in Next.js | Bypass via header spoofing (CVE-2025-29927) | §5.1 |
| `jwt.decode()` without explicit `algorithms=` parameter | Algorithm Confusion attack | §6.1 (RFC 8725) |
| Wildcard (`*`) CORS origins on authenticated APIs | Unauthorized cross-origin access | §7.1 |
| Absolute account lockout as sole brute-force defense | DoS vector | §7.2 |
| Secrets in Docker `ENV`/`ARG` or committed `.env` files | Credential leakage via `docker inspect` | §2.3 |
| Starlette `BaseHTTPMiddleware` for JWT parsing | No routing context, brittle path matching | §4.1 |
| Synchronous `def` for crypto/network auth dependencies | Threadpool exhaustion under concurrency | §4.2 |
| Gateway-only auth without app-layer validation | Header spoofing bypasses | §1.2 |

---

## 9. Automated Enforcement

### 9.1 Semgrep Rules (CI/CD)

The following custom Semgrep rules MUST be implemented and run on every PR:

1. **FastAPI route protection:** Every `@router.*` / `@app.*` decorated function must include auth dependency
2. **Algorithm confusion prevention:** Every `jwt.decode()` call must include `algorithms=` parameter
3. **Next.js Server Action protection:** Every exported Server Action must call `verifySession()` before mutations
4. **Secrets scanning:** detect-secrets / Gitleaks in pre-commit hooks

### 9.2 PR Checklist

Every PR touching auth-related code MUST include attestation:

**Backend (FastAPI):**
- [ ] New endpoint uses shared `Depends(verify_token)` dependency
- [ ] Identity attributes come from validated token, not request body
- [ ] Crypto dependencies use `async def`
- [ ] Error responses are generic (no user enumeration)

**Frontend (Next.js):**
- [ ] Middleware uses default-deny negative lookahead
- [ ] Auth checks in DAL (Server Components), not middleware-only
- [ ] Session tokens in httpOnly/Secure/SameSite cookies only

**Infrastructure:**
- [ ] Secrets via Docker Secrets (`/run/secrets/`), not `.env`
- [ ] Nginx `limit_req_zone` applied to new auth endpoints
- [ ] CORS origins explicitly allowlisted

---

## 10. Implementation Checklist

### Phase 1: Foundation
- [ ] Deploy Authentik via Docker Compose on EX44 with persistent volumes
- [ ] Configure Authentik as OIDC provider with EdDSA signing (or ES256 fallback)
- [ ] Enable refresh token rotation in Authentik
- [ ] Configure back-channel logout endpoints

### Phase 2: Shared Library
- [ ] Create `onpulse-auth-core` Python package with:
  - JWKS fetching + caching
  - `verify_token` async dependency
  - `get_current_user` dependency
  - RBAC scope enforcement
  - Pydantic token/user models
- [ ] Distribute via Git SSH with version tags

### Phase 3: Backend Integration
- [ ] Integrate `onpulse-auth-core` into all FastAPI services
- [ ] Apply global auth dependency (default-on pattern)
- [ ] Create Authentik Service Accounts for M2M flows
- [ ] Migrate secrets to Docker Secrets

### Phase 4: Frontend Integration
- [ ] Configure Auth.js v5 with Authentik OIDC provider in all Next.js apps
- [ ] Implement `verifySession()` DAL + `React.cache()` wrapper
- [ ] Configure default-deny middleware matcher
- [ ] Implement back-channel logout route handler
- [ ] Upgrade Next.js to >= 15.2.3

### Phase 5: Infrastructure
- [ ] Configure Nginx rate limiting for auth endpoints
- [ ] Configure Nginx CORS allowlists
- [ ] Configure Nginx header sanitisation
- [ ] Configure Uvicorn `--forwarded-allow-ips`
- [ ] Implement JSON audit logging schema

### Phase 6: Enforcement
- [ ] Write custom Semgrep rules for FastAPI Depends() and Next.js DAL enforcement
- [ ] Add Semgrep to CI pipeline (block PR on failure)
- [ ] Add PR template with security attestation checklist
- [ ] Secrets scanning in pre-commit hooks

---

## Appendix A: Recommended Libraries

| Component | Library | Version (as of Mar 2026) |
|-----------|---------|-------------------------|
| IdP | Authentik | Latest stable (2026.2+) |
| Next.js OIDC client | Auth.js (next-auth) | v5.x |
| FastAPI JWT validation | PyJWT | 2.12.0+ |
| FastAPI OAuth/OIDC primitives | Authlib | 1.6.9+ |
| JOSE/JWK (JS) | jose | 6.2.1+ |
| Policy engine (optional) | casbin | 1.43.0+ |
| Rate limiting (FastAPI) | fastapi-limiter | 0.2.0+ |
| Rate limiting (core) | limits | 5.8.0+ |

## Appendix B: Standards References

| Standard | Reference |
|----------|-----------|
| OAuth 2.0 Security BCP | RFC 9700 |
| JWT Access Token Profile | RFC 9068 |
| JWT Best Current Practices | RFC 8725 |
| Token Introspection | RFC 7662 |
| Token Revocation | RFC 7009 |
| EdDSA for JOSE | RFC 8037 |
| DPoP | RFC 9449 |
| mTLS for OAuth | RFC 8705 |
| OIDC Core 1.0 | OpenID Foundation |
| OIDC Back-Channel Logout 1.0 | OpenID Foundation |
| OWASP ASVS | V2 (Authentication), V3 (Session Management) |
| OWASP API Security Top 10 | 2023 edition |

## Appendix C: Source Alignment

This standard was synthesised from three independent research sources:

| Source | Key Contribution |
|--------|-----------------|
| Perplexity | RFC-grounded, standards-first perspective; detailed claim validation rules; comprehensive checklist format |
| GPT 5.4 | Strongest on RFC 9700/9068 specifics; detailed cross-cutting controls; practical algorithm selection rationale |
| Gemini Pro 3.1 | Strongest on Phantom Token Pattern; Next.js DAL/CVE-2025-29927; Semgrep enforcement rules; Docker Secrets detail |

All three sources achieved consensus on architecture (central IdP), token strategy (short-lived JWT + rotating refresh), and prohibited patterns. Divergences were resolved by adopting the more secure recommendation where sources disagreed.
