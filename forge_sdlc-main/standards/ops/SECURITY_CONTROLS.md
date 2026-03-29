# SECURITY_CONTROLS.md

**Standard ID:** OPS-STD-002
**Version:** 1.0
**Status:** Draft
**Created:** 2026-03-14
**Scope:** All OnPulse FastAPI backends, Next.js frontends, Docker containers, and supporting infrastructure (nginx, PostgreSQL, Redis, SSH)
**Authoritative Frameworks:** OWASP Top 10 2025, OWASP API Security Top 10 2023, CIS Docker Benchmark, Australian Privacy Act 1988 (APP 11, NDB Scheme)

---

## 1. OWASP Alignment

### 1.1 OWASP Top 10 2025 Mapping

This standard aligns with OWASP Top 10 **2025** (not 2021). Key shifts relevant to OnPulse:

| OWASP 2025 Category | OnPulse Risk Pattern | Primary Controls |
|---|---|---|
| A01 Broken Access Control (absorbs SSRF) | Missing `Depends(auth)` on FastAPI routes; client-only auth gates; BOLA/BFLA | APP-AC-01 through APP-AC-05, APP-IV-06 |
| A02 Security Misconfiguration | Permissive CORS; debug in prod; open Redis; missing security headers; Docker misconfig | APP-HEADERS-01/02, INF-DOCKER-01–05, INF-REDIS-01–03 |
| A03 Vulnerable & Outdated Components (Supply Chain) | Known CVEs in pip/npm deps; typosquatting; React2Shell; outdated base images | APP-SCA-01/02, APP-SUPPLY-01/02, APP-SBOM-01, INF-IMAGE-01 |
| A04 Cryptographic Failures | Weak hashing; missing TLS; secrets in code; insecure algorithms | APP-CRYPTO-01–04, APP-SECRETS-01/02 |
| A05 Injection | SQL injection via SQLAlchemy misuse; SSTI in Jinja2; command injection | APP-IV-04/05, APP-XSS-03 |
| A06 Insecure Design | Missing rate limits; no threat model; insecure defaults | APP-RATE-01 |
| A07 Identification & Authentication Failures | Weak sessions; missing MFA for admin; insecure cookies | Cross-ref OPS-STD-001 (AUTH_SSO_STANDARD) |
| A08 Software & Data Integrity Failures | Untrusted build artefacts; unsafe CI; missing SBOM | APP-SBOM-01, APP-SUPPLY-01 |
| A09 Security Logging & Alerting Failures | Missing auth/access logs; log injection; no retention policy | LOG-01 through LOG-05 |
| A10 Mishandling of Exceptional Conditions | Verbose error responses; unhandled exceptions leaking stack traces | APP-ERR-01 |

### 1.2 OWASP API Security Top 10 2023 Mapping

| API Category | FastAPI Risk Pattern | Primary Controls |
|---|---|---|
| API1 BOLA | `/resource/{id}` returns another user's object | APP-AC-02 |
| API2 Broken Authentication | Weak token verification; missing expiry/issuer checks | Cross-ref OPS-STD-001 |
| API3 BOPLA | Over-posting / mass assignment; leaking private fields | APP-AC-04 |
| API4 Unrestricted Resource Consumption | No rate limits; unbounded pagination/uploads | APP-RATE-01, APP-IV-02 |
| API5 BFLA | Normal user hits admin endpoints | APP-AC-03 |
| API6 Sensitive Business Flows | Login/payment/export abuse | APP-RATE-01 |
| API7 SSRF | User-controlled URLs in server-side fetch | APP-IV-06 |
| API8 Security Misconfiguration | Permissive CORS; verbose errors; missing headers | APP-HEADERS-01/02, APP-ERR-01 |
| API9 Improper Inventory Management | Undocumented endpoints; shadow routes | APP-INV-01 |
| API10 Unsafe Consumption of APIs | Trusting Stripe/webhook payloads without signature verification | APP-WEBHOOK-01 |

---

## 2. Application Security Controls

### 2.1 Access Control

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| APP-AC-01 | Every FastAPI route MUST be explicitly classified as `public` or `authenticated`. Public routes MUST be declared in a single allowlist file referenced in gate reviews. | Semgrep route scan + allowlist diff | High | Python |
| APP-AC-02 | Any route that reads/updates/deletes an object by identifier MUST enforce object-level authorisation (`tenant_id`/owner check) before returning or mutating data. | Semgrep custom rule requiring `authorise_*` call preceding response | Critical | Python |
| APP-AC-03 | Admin/ops actions MUST enforce function-level authorisation (role/permission check), not just authentication. | Semgrep requiring `require_role(...)` or policy decorator | Critical | Both |
| APP-AC-04 | API responses MUST use explicit response models/schemas. Returning ORM objects or raw `dict` dumps is forbidden unless fields are explicitly allowlisted. | Semgrep: ban `return model.__dict__`, `jsonable_encoder(model)` without schema | High | Python |
| APP-AC-05 | Client-side checks (Next.js) MUST NOT be the sole gate for sensitive actions. The server MUST independently enforce authorisation. | Semgrep: flag admin conditions only in UI without corresponding API auth (best-effort) | High | TypeScript |

### 2.2 Input Validation

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| APP-IV-01 | All inbound JSON payloads MUST be validated against Pydantic models (Python) or strict TypeScript schemas (server actions). Unknown fields SHOULD be rejected for sensitive models (`model_config = {"extra": "forbid"}`). | Semgrep + unit tests for schema strictness | High | Both |
| APP-IV-02 | File upload endpoints MUST: allowlist extensions; validate real file type via magic bytes (not `Content-Type` header); enforce size limits; require auth; store outside webroot; scan (AV/CDR) where feasible. | Semgrep: any `UploadFile` must call `validate_upload()`; config lint for max body size | Critical | Both |
| APP-IV-03 | Path traversal protection: user input MUST NOT be concatenated into filesystem paths. Paths MUST be resolved/canonicalised and verified under an allowed base directory using a `safe_join(base, user)` helper. | Semgrep taint: user input to open()/Path()/fs | High | Both |
| APP-IV-04 | SQL injection protection: MUST NOT build SQL strings using interpolation. Raw SQL MUST use bound parameters. `literal_binds=True` is forbidden in production code paths. | Semgrep: forbid f-strings in `text()`/`.execute()` | Critical | Python |
| APP-IV-05 | Dynamic sort/filter fields MUST use allowlists. MUST NOT accept arbitrary column names from user input (identifiers cannot be parameterised safely). | Semgrep custom rule for `order_by(text(...))` or `literal_column(user)` | High | Python |
| APP-IV-06 | SSRF prevention: any server-side HTTP client call using user-influenced URLs MUST enforce a domain allowlist and block private/link-local/metadata IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `fd00::/8`). Redirects MUST be disabled unless explicitly allowed. | Semgrep taint: request params to `requests.get`/`httpx`/`fetch`; require `safe_fetch()` | Critical | Both |

### 2.3 XSS & Output Encoding

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| APP-XSS-01 | Any use of React's unsafe innerHTML property MUST be preceded by sanitisation via `DOMPurify.sanitize()` or an approved equivalent. Raw HTML rendering without sanitisation is forbidden. | Semgrep: flag unsafe innerHTML without sanitiser | High | TypeScript |
| APP-XSS-02 | User-influenced `href`/`src` attributes MUST be validated to prevent `javascript:` and `data:` URL injection. A `validate_url()` helper is required. | Semgrep: user input to URL sinks | High | TypeScript |
| APP-XSS-03 | Server-side templates (Jinja2): autoescape MUST be enabled via `select_autoescape`. `autoescape=False` and `|safe` filter on untrusted content are forbidden. `render_template_string` with user-controlled input is forbidden. | Semgrep: detect dangerous Jinja environment config | High | Python |

### 2.4 Security Headers

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| APP-HEADERS-01 | A Content Security Policy MUST be deployed. For Next.js, CSP MUST use per-request nonces (`'nonce-<value>'` + `'strict-dynamic'`). `'unsafe-inline'` for scripts is forbidden. `'unsafe-eval'` is forbidden. | Config lint + integration test | Medium | Both |
| APP-HEADERS-02 | Minimum security headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN` (or `frame-ancestors 'self'` in CSP), `Permissions-Policy` restricting camera/geolocation/microphone. | Integration test (curl or Playwright) | Medium | Both |

**Recommended CSP baseline:**
```
default-src 'self';
script-src 'self' 'nonce-{REQUEST_NONCE}' 'strict-dynamic';
style-src 'self' 'nonce-{REQUEST_NONCE}';
img-src 'self' data: blob: https:;
font-src 'self' https://fonts.gstatic.com;
connect-src 'self' https://api.stripe.com;
object-src 'none';
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
upgrade-insecure-requests;
```

### 2.5 Cryptography

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| APP-CRYPTO-01 | Password hashing MUST use Argon2id with OWASP minimum parameters: `m=46 MiB (47,104 KB)`, `t=1`, `p=1`. For highly sensitive systems (admin gateways): `m=128 MiB`, `t=3`. Bcrypt (cost >= 14) is acceptable only as a documented legacy fallback; no new implementations. | Semgrep: approved hashing wrapper only; dependency checks | Critical | Both |
| APP-CRYPTO-02 | Weak/deprecated cryptography is forbidden: MD5, SHA-1 (for security purposes), DES, 3DES, RC4, AES-ECB, home-grown crypto. Build MUST fail on detection. | Semgrep rules for imports/usages | High | Both |
| APP-CRYPTO-03 | Symmetric encryption (when used) MUST use an AEAD mode (AES-256-GCM) with unique nonces per operation and proper key separation. | Semgrep: enforce use of approved wrapper; unit tests for nonce handling | High | Both |
| APP-CRYPTO-04 | JWT/token signing MUST use modern algorithms (EdDSA/Ed25519 preferred, ES256 acceptable, RS256 baseline). Verification MUST validate `exp`, `iss`, and `aud` claims. `alg: none` is forbidden. `jwt.decode(..., verify=False)` is forbidden. | Semgrep: forbid decode-without-verify patterns | High | Both |

**Note:** SHA-256/SHA-512 remain acceptable for non-password purposes (checksums, HMAC, content hashing).

### 2.6 Secrets Management

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| APP-SECRETS-01 | Secrets MUST NOT appear in code, tests, config files, or build artefacts. Dual-gate secrets scanning is mandatory: Gitleaks pre-commit (fast, millisecond-speed) + TruffleHog in CI (deep scanning with active credential verification). | Gitleaks + TruffleHog + git history scan | Critical | Both |
| APP-SECRETS-02 | All secrets MUST be loaded from environment variables or Docker Secrets (`/run/secrets/`). `.env` files MUST NOT be copied into Docker images. Private keys MUST have file permissions restricting access to the application user only (`chmod 600`). | Semgrep on Dockerfiles + compose files; config lint | High | Both |
| APP-SECRETS-03 | Logging MUST NOT include Authorization headers, cookies, tokens, passwords, API keys, or Stripe secrets. | Semgrep for `logger` calls containing sensitive field names | High | Both |

### 2.7 Supply Chain & Dependency Security

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| APP-SCA-01 | Python dependencies MUST pass `pip-audit` in CI. Build MUST fail on High/Critical CVEs unless explicitly waived with documented justification. | Tool: pip-audit | High | Python |
| APP-SCA-02 | Node dependencies MUST pass `npm audit` on a lockfile-driven install (`npm ci`). Builds MUST NOT run audits without lockfiles. | Tool: npm audit with `package-lock.json` enforcement | High | TypeScript |
| APP-SUPPLY-01 | Typosquatting/malicious package detection: CI MUST detect suspicious dependency metadata (install scripts, new packages). Socket CLI (or equivalent) is recommended for behavioural analysis beyond CVE-only tools. | Tool: Socket CLI + policy checks | High | Both |
| APP-SUPPLY-02 | **React2Shell mitigation (Critical):** Next.js MUST be maintained on the latest supported patch version. Security advisories (including CVE-2025-66478 / CVE-2025-55182 RSC Flight protocol RCE) MUST be patched within 48 hours of publication for Critical/High, 7 days for Medium. CI MUST fail if the pinned version has known unpatched Critical/High CVEs. Do not rely on static minimum version floors — successive advisories supersede earlier patches. | Version check + advisory feed in CI | Critical | TypeScript |
| APP-SBOM-01 | SBOM (CycloneDX or SPDX) MUST be generated per build for both application source and container image. SBOMs are stored as build artefacts. | Tool: Syft (images/filesystems) + pip-audit SBOM output | Medium | Both |

### 2.8 API Inventory & Error Handling

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| APP-INV-01 | OpenAPI spec MUST be generated each build. Build MUST fail if endpoints are added without tags, owners, or versioning notes. | Spec generation + diff gate | Medium | Python |
| APP-WEBHOOK-01 | Inbound webhooks (Stripe, Cal.com, etc.) MUST verify signatures before processing payloads. Strict schema validation on webhook bodies is required. | Semgrep pattern + integration tests | High | Both |
| APP-RATE-01 | Rate limiting is required on: authentication, password reset, OTP, payment, upload, and export endpoints. Limits MUST be configurable per-endpoint. | Config lint + integration tests | High | Both |
| APP-ERR-01 | Production error responses MUST NOT include stack traces, internal paths, or debug information. Errors MUST return generic messages with correlation IDs for internal tracking. | Semgrep: flag `debug=True` in prod config; integration test for error format | Medium | Both |

---

## 3. Infrastructure Security Controls

### 3.1 Docker Container Hardening

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| INF-DOCKER-01 | Containers MUST NOT run as root. Dockerfiles MUST set a non-root `USER` directive before `CMD`/`ENTRYPOINT` unless explicitly justified and documented. | Trivy config scan + Semgrep Dockerfile rule + Hadolint | High | Infra |
| INF-DOCKER-02 | Root filesystem MUST be read-only at runtime (`read_only: true` in Compose). Writable paths only via explicit `tmpfs` mounts or named volumes. | Compose lint + runtime inspect check | High | Infra |
| INF-DOCKER-03 | Linux capabilities MUST be dropped (`--cap-drop ALL`). Only strictly required capabilities MUST be re-added explicitly (e.g., `NET_BIND_SERVICE`). `--privileged` is forbidden. | Compose lint + policy checks | High | Infra |
| INF-DOCKER-04 | `no-new-privileges` MUST be enforced (`security_opt: ["no-new-privileges:true"]`). | Compose lint | High | Infra |
| INF-DOCKER-05 | Resource limits (CPU, memory, PIDs) MUST be defined for all internet-facing services. | Compose lint (`pids_limit`, `mem_limit`, `cpus`) | Medium | Infra |

**Docker Compose enforcement example:**
```yaml
services:
  api:
    user: "1000:1000"
    read_only: true
    security_opt:
      - "no-new-privileges:true"
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE  # only if needed
    tmpfs:
      - /tmp
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 512M
          pids: 256
```

**Note:** `deploy.resources` requires Docker Swarm mode or `docker compose --compatibility` flag. In standalone Compose, use `mem_limit`, `cpus`, and `pids_limit` top-level service keys instead. Verify enforcement in your target environment.

### 3.2 Container Image Security

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| INF-IMAGE-01 | All container images MUST be scanned with Trivy (or Grype). High+ vulnerabilities block deployment. Base images MUST be pinned to specific digests (not `latest`). | Trivy in CI pipeline | High | Infra |

### 3.3 Nginx

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| INF-NGINX-01 | HTTPS everywhere. HTTP MUST redirect to HTTPS. HSTS MUST be enabled (`Strict-Transport-Security: max-age=31536000; includeSubDomains`). | Integration test + nginx config lint | High | Infra |
| INF-NGINX-02 | Security headers baseline MUST be present: CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN`, `Permissions-Policy`. | Integration test (curl) in pipeline | Medium | Infra |

### 3.4 PostgreSQL

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| INF-DB-01 | Least-privilege roles. No application role MUST be SUPERUSER, CREATEROLE, or CREATEDB unless explicitly justified. | SQL checks in migration pipeline | High | Infra |
| INF-DB-02 | Network access MUST be restricted via `pg_hba.conf`. Remote connections MUST use `hostssl`. Authentication MUST use SCRAM-SHA-256 (`md5` is forbidden for new deployments). | Config lint + runtime connection tests | High | Infra |
| INF-DB-03 | **pgAudit MUST be enabled** for session- and object-level auditing of DDL/DML operations on tables containing PII or financial data. This provides an irrefutable audit trail of which service account/user queried, altered, or deleted sensitive records. Required for SOC 2 readiness and APP 11 compliance. | Config check for `shared_preload_libraries = 'pgaudit'` | High | Infra |

### 3.5 Redis

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| INF-REDIS-01 | Redis MUST NOT be exposed to the internet. Bind to loopback (`127.0.0.1`) or private network only. Firewall the port. | Port scan test + config lint | Critical | Infra |
| INF-REDIS-02 | Redis auth MUST be enabled using ACLs (Redis 6+, preferred) or at minimum `requirepass`. Dangerous commands (`FLUSHALL`, `FLUSHDB`, `DEBUG`, `CONFIG`) MUST be disabled or ACL-restricted for non-admin clients. | Config lint + ACL policy tests | High | Infra |
| INF-REDIS-03 | If Redis is accessed over a network (not loopback), TLS MUST be enabled and non-TLS port disabled (`port 0`). | Config lint + runtime TLS check | High | Infra |

### 3.6 SSH

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| INF-SSH-01 | SSH hardening: disable root login (`PermitRootLogin no`), disable password auth (`PasswordAuthentication no`), restrict login users via `AllowUsers`, use Ed25519 keys only. Fail2Ban MUST be active with an sshd jail. | Config lint (`sshd -T`) + Fail2Ban status check | High | Infra |

---

## 4. Security Logging & Privacy

### 4.1 Mandatory Security Events

The following events MUST be logged in structured JSON format with correlation IDs:

| Event Category | Examples |
|---|---|
| Authentication | Successful/failed logins, session creation/expiry, token validation failures, MFA attempts |
| Access control | Allow/deny decisions for sensitive objects, admin actions, role changes |
| Input validation | Rejected payloads, blocked uploads (type/size/AV results), rate limit triggers |
| Data lifecycle | Create/update/delete/export of sensitive records (PII, financial data) |
| Security errors | Unhandled exceptions, permission escalation attempts, suspicious patterns |

### 4.2 Logging Controls

| Control ID | Requirement | Automation | Severity | Stack |
|---|---|---|---|---|
| LOG-01 | Security events MUST be emitted in structured JSON with: timestamp (ISO 8601), correlation ID, user ID, source IP, action, resource, and outcome (allow/deny/error). | Log schema validation tests | Medium | Both |
| LOG-02 | Log injection prevention: MUST NOT concatenate user input into log messages. MUST use parameterised/structured logging APIs. CR/LF and delimiter characters MUST be sanitised before logging. | Semgrep: flag string concatenation in logger calls | Medium | Both |
| LOG-03 | Sensitive data exclusion: MUST NOT log Authorization headers, cookies, tokens, passwords, API keys, Stripe secrets, or raw PII. | Semgrep for `logger` calls containing sensitive field names | High | Both |
| LOG-04 | pgAudit logs (INF-DB-03) MUST capture DDL/DML on sensitive tables with service account attribution. | Config check + audit log presence test | High | Infra |
| LOG-05 | Log retention policy MUST be declared and enforced. See section 4.3. | Policy-as-code check on logging backend | Medium | Both |

### 4.3 Retention & Privacy (Australian Privacy Act)

**APP 11 (Security of personal information):** Mandates "reasonable steps" to protect personal data. Recent Federal Court rulings (AIC v ACL) codified that this includes robust access logging, continuous monitoring, MFA, network segmentation, and timely patching.

**NDB Scheme (Notifiable Data Breaches):** 72-hour notification window to OAIC from becoming aware of an eligible data breach. Structured security logs are essential for rapid breach investigation and meeting this timeline.

**APP 11.2 Retention vs. Destruction Paradox:**
- MUST destroy or de-identify PII when no longer needed for permitted purposes
- Security teams need 1-2 year log retention for forensic audits
- **Resolution:** Logs MUST NOT contain cleartext PII. User activity is logged against immutable UUIDs. Underlying PII can be destroyed/de-identified independently while audit logs are retained.

**Retention schedule (minimum):**

| Log Type | Minimum Retention | Maximum Retention | Notes |
|---|---|---|---|
| Application security logs | 12 months | 24 months | UUID-based, no cleartext PII |
| Access logs (nginx) | 6 months | 12 months | IP addresses are PII under Privacy Act |
| Database audit logs (pgAudit) | 12 months | 24 months | Service account attribution |
| Backup logs | 6 months | 12 months | |

**MUST NOT** destroy logs before minimum retention period. **MUST NOT** retain beyond maximum without documented legal basis. Periodic purge/de-identification process is required.

**Potential penalties:** Fines up to $50 million for failing to maintain defensible security practices. Statutory tort allows individuals to sue directly for serious privacy invasions.

---

## 5. Severity Model & Deployment Gates

### 5.1 Severity Classification

| Severity | Definition | Deployment Gate |
|---|---|---|
| **Critical** | Direct compromise likely: authz bypass, SSRF to internal services, secret in repo, SQL injection on sensitive data path, RCE (React2Shell), unauthenticated access to PII/financial data | **Block deployment. Immediate remediation.** |
| **High** | Serious exploitability or major data exposure: unsafe uploads, missing auth on non-public endpoints, weak crypto primitives, missing TLS, Docker running as root | **Block deployment.** |
| **Medium** | Exploit requires preconditions or limited impact: missing some security headers, incomplete logging coverage, SBOM generation missing, informational CSP gaps | **Create tracked issue. Allow deploy only with explicit risk acceptance (documented).** |
| **Low/Info** | Hard to exploit or hygiene: minor best practices, cosmetic header improvements | **Track opportunistically.** |

### 5.2 Scoring Method

- **Dependency vulnerabilities:** Use CVSS v4.0 vendor/advisory scores (standardised cross-ecosystem comparability)
- **Code/config findings:** Use OWASP-style likelihood x impact model (more contextual for app-specific control failures)

### 5.3 Waiver Process

High/Critical findings MAY be temporarily waived only with:
1. Written justification documenting compensating controls
2. Time-bound waiver (maximum 30 days for High, 7 days for Critical)
3. Tracked issue with assigned owner
4. Approval from project lead

---

## 6. Automation Matrix

### 6.1 Static vs Dynamic vs Manual

| Control Family | Static Analysis (Semgrep/Tools) | Dynamic Tests | Manual Review Required |
|---|---|---|---|
| Access Control (BOLA/BFLA) | Strong for "presence of auth hooks"; weaker for semantic correctness | Integration tests for access matrices | Complex tenancy/ownership rules |
| Injection (SQL/command/template) | Strong (pattern + taint) | Optional DAST | Complex query builders; approved raw SQL modules |
| XSS/CSP | Strong for known sinks (unsafe innerHTML, unsafe URLs) | Browser-based CSP tests | Justified CSP relaxations |
| SSRF | Strong for "user input to HTTP client" | Runtime egress tests | Proxy-like features |
| Cryptography | Strong for weak algorithm detection | N/A | Key lifecycle, rotation scope |
| Supply Chain | Strong (SCA + SBOM + image scanning) | N/A | Risk acceptance where no fix exists |
| Secrets | Strong (Gitleaks + TruffleHog) | N/A | Key storage review |
| Logging/Retention | Moderate: log call presence + sanitisation helpers | Verify logs emitted in staging | Alerting/IR readiness |
| Docker/Infra | Strong (Trivy misconfig + compose lint) | Runtime inspect checks | Exceptional capability additions |

### 6.2 Automation Confidence

Controls with **high automation confidence** (machine-verifiable, low false positive):
- APP-IV-04 (SQL injection patterns), APP-CRYPTO-02 (weak crypto), APP-SECRETS-01 (secrets in code), APP-XSS-01 (unsafe innerHTML), INF-DOCKER-01-04, APP-SUPPLY-02 (version pinning)

Controls requiring **human judgement** (flag for review):
- APP-AC-02 (object-level authz semantic correctness), APP-AC-03 (function-level authz completeness), APP-RATE-01 (appropriate limit values), LOG-01 (log coverage completeness)

---

## 7. Toolchain

### 7.1 Recommended Tools (versions as of March 2026)

**Static Analysis & Rule Enforcement:**
| Tool | Version | Purpose |
|---|---|---|
| Semgrep CE | v1.154.0 | Custom rules + registry rules (AST parsing + taint tracking) |
| Bandit | v1.9.4 | Python security lint (dangerous stdlib usage) |
| Hadolint | latest | Dockerfile best-practice linting |

**Dependency & Vulnerability Scanning:**
| Tool | Version | Purpose |
|---|---|---|
| pip-audit | v2.10.0 | Python SCA (Python Packaging Advisory DB) |
| npm audit | built-in | Node.js SCA (lockfile-driven) |
| Socket CLI | latest | Behavioural analysis, typosquatting detection |
| OSV-Scanner | v2.x | Optional cross-ecosystem vulnerability matching |

**Secrets Scanning (Dual-Gate):**
| Tool | Version | Gate | Purpose |
|---|---|---|---|
| Gitleaks | v8.30.0 | Pre-commit | Fast PR scanning (millisecond-speed) |
| TruffleHog | v3.93.5 | CI pipeline | Deep scanning + active credential verification |

**Container & Infrastructure Scanning:**
| Tool | Version | Purpose |
|---|---|---|
| Trivy | v0.69.3 | Container vuln + misconfig scanning |
| Syft | v1.42.2 | SBOM generation (images/filesystems) |
| Grype | v0.105.0 | Vulnerability scanning of images/SBOMs |

### 7.2 CI Pipeline Integration Order

```
1. Pre-commit hooks:
   - Gitleaks (secrets)
   - Semgrep (custom rules subset - fast)
   - Ruff (lint + format)

2. CI pipeline (on PR):
   - Semgrep (full rule set)
   - Bandit (Python)
   - pip-audit (Python SCA)
   - npm audit (Node SCA)
   - Socket CLI (supply chain)
   - TruffleHog (secrets - deep scan)
   - Version pinning checks (React2Shell, etc.)
   - OpenAPI spec diff

3. Docker build gate:
   - Hadolint (Dockerfile lint)
   - Trivy (image scan)
   - Syft (SBOM generation)
   - Compose lint (security_opt, cap_drop, etc.)

4. Post-deploy verification:
   - Security header integration tests
   - TLS/HSTS verification
   - Port scan (Redis not exposed)
   - sshd_config verification
```

---

## 8. Example Semgrep Rules

### 8.1 FastAPI Route Missing Auth Dependency

```yaml
rules:
  - id: fastapi-route-missing-auth-dependency
    message: >
      FastAPI route missing auth dependency. Add Depends(get_current_user)
      or declare route in public allowlist.
    languages: [python]
    severity: ERROR
    patterns:
      - pattern-either:
          - pattern: |
              @app.$METHOD(...)
              def $FUNC(...):
                ...
          - pattern: |
              @$ROUTER.$METHOD(...)
              def $FUNC(...):
                ...
      - metavariable-regex:
          metavariable: $METHOD
          regex: "get|post|put|patch|delete"
      - pattern-not: |
          def $FUNC(..., $X=Depends($AUTH), ...):
            ...
      - pattern-not: |
          @app.$METHOD(..., dependencies=[..., Depends($AUTH), ...])
          def $FUNC(...):
            ...
      - pattern-not: |
          @$ROUTER.$METHOD(..., dependencies=[..., Depends($AUTH), ...])
          def $FUNC(...):
            ...
```

### 8.2 SQLAlchemy SQL Injection via f-string

```yaml
rules:
  - id: sqlalchemy-text-fstring
    message: >
      SQL injection: f-string used inside SQLAlchemy text(). Use bound parameters.
    languages: [python]
    severity: ERROR
    patterns:
      - pattern-either:
          - pattern: text(f"...{$X}...")
          - pattern: session.execute(f"...{$X}...")
          - pattern: session.execute("...%s..." % $VAR)
```

### 8.3 React Unsafe innerHTML Without Sanitisation

```yaml
rules:
  - id: react-unsafe-inner-html-requires-sanitization
    message: >
      Unsafe innerHTML property requires DOMPurify.sanitize() or approved sanitiser.
    languages: [typescript, javascript]
    severity: ERROR
    pattern: |
      dangerouslySetInnerHTML={{ __html: $HTML }}
    pattern-not: |
      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize($HTML) }}
```

### 8.4 Weak Crypto Detection

```yaml
rules:
  - id: python-weak-hash
    message: >
      Weak/deprecated crypto detected. Use Argon2id for passwords, AES-256-GCM
      for encryption, Ed25519 for signatures.
    languages: [python]
    severity: ERROR
    pattern-either:
      - pattern: hashlib.md5(...)
      - pattern: hashlib.new("md5", ...)
      - pattern: hashlib.sha1(...)
      - pattern: hashlib.new("sha1", ...)
      - pattern: DES.new(...)
      - pattern: AES.new(..., AES.MODE_ECB, ...)
```

### 8.5 Logger String Concatenation (Log Injection)

```yaml
rules:
  - id: python-logger-string-concat
    message: >
      Do not concatenate user input into log messages. Use structured/parameterised logging.
    languages: [python]
    severity: WARNING
    patterns:
      - pattern: logger.$LEVEL("$MSG" + $VAR)
      - metavariable-regex:
          metavariable: $LEVEL
          regex: "(debug|info|warning|error|critical)"
```

---

## 9. Prohibited Anti-Patterns

| Pattern | Why Prohibited | Detection |
|---|---|---|
| `jwt.decode(..., verify=False)` | Disables all JWT validation | Semgrep |
| `subprocess.run(..., shell=True)` with user input | Command injection | Semgrep taint |
| `text(f"...{user_input}...")` | SQL injection | Semgrep |
| React unsafe innerHTML without sanitiser | XSS | Semgrep |
| `autoescape=False` in Jinja2 | SSTI/XSS | Semgrep |
| `hashlib.md5()` / `hashlib.sha1()` for security | Weak crypto | Semgrep |
| `docker run --privileged` | Full host access | Compose lint |
| Secrets in source code / Dockerfiles | Credential exposure | Gitleaks + TruffleHog |
| `debug=True` / `DEBUG=1` in production config | Information disclosure | Semgrep + config lint |
| `CORS(allow_origins=["*"])` on authenticated endpoints | Cross-origin attacks | Semgrep |
| `logger.info(f"User {password} logged in")` | Credential logging | Semgrep |
| Next.js < 15.0.5 / < 14.2.25 | React2Shell RCE | Version check |
| Redis exposed to 0.0.0.0 without auth | Unauthenticated data access | Config lint |
| PostgreSQL `md5` auth method | Weak authentication | Config lint |

---

## 10. Implementation Checklist

### Phase 1: Immediate (Week 1-2)
- [ ] Install Gitleaks pre-commit hook across all repos
- [ ] Add Semgrep CI job with rules: SQL injection, weak crypto, missing auth, unsafe innerHTML
- [ ] Pin Next.js versions above React2Shell threshold
- [ ] Verify Redis bind/auth configuration
- [ ] Verify PostgreSQL uses SCRAM-SHA-256

### Phase 2: Build Gate (Week 3-4)
- [ ] Add pip-audit and npm audit to CI with High/Critical blocking
- [ ] Add TruffleHog to CI pipeline
- [ ] Add Trivy container scanning to Docker build
- [ ] Add Hadolint to Dockerfile linting
- [ ] Configure Docker Compose security defaults (non-root, read-only, cap-drop)
- [ ] Deploy Syft SBOM generation

### Phase 3: Logging & Compliance (Week 5-6)
- [ ] Implement structured JSON logging with correlation IDs
- [ ] Enable pgAudit on sensitive tables
- [ ] Configure log retention/purge schedule
- [ ] Deploy security header integration tests
- [ ] Verify SSH hardening and Fail2Ban

### Phase 4: Advanced (Week 7-8)
- [ ] Add Socket CLI for supply chain monitoring
- [ ] Implement SSRF safe_fetch() helper
- [ ] Add OpenAPI spec diffing to CI
- [ ] Implement rate limiting on sensitive endpoints
- [ ] Full automation matrix validation

---

## Appendices

### A. Standards References

| Standard | Relevance |
|---|---|
| OWASP Top 10 2025 | Primary web application risk framework |
| OWASP API Security Top 10 2023 | API-specific risk framework |
| OWASP Password Storage Cheat Sheet | Argon2id parameters, hashing guidance |
| OWASP HTTP Headers Cheat Sheet | Security header requirements |
| OWASP SSRF Prevention Cheat Sheet | SSRF blocking patterns |
| OWASP File Upload Cheat Sheet | Upload validation requirements |
| CIS Docker Benchmark | Container hardening baseline |
| NIST SP 800-38D | AES-GCM specification |
| NIST SP 800-92 | Log management programme guidance |
| RFC 8032 | EdDSA/Ed25519 specification |
| Australian Privacy Act 1988 | APP 11, NDB Scheme (72-hour notification) |
| SQLAlchemy Security Guidelines | Bound parameters, unsafe literal_binds warnings |

### B. Source Alignment

This standard synthesises research from three independent AI providers:

| Source | Unique Contributions |
|---|---|
| **Perplexity** | Most structured control table (A1-A25 IDs); detailed per-control automation methods; strongest on toolchain comparisons (pip-audit vs Safety, Trivy vs Grype) |
| **GPT 5.4** | Most detailed OWASP 2025 mapping with automatable vs manual breakdown; 4 example Semgrep YAML rules; CVSS v4.0 hybrid severity model; control ID convention (APP-AC-##, APP-IV-##) |
| **Gemini Pro 3.1** | OWASP 2025 specific changes (Supply Chain at #3, Misconfiguration at #2); React2Shell CVEs (CVE-2025-66478, CVE-2025-55182); pgAudit for PostgreSQL auditing; Australian Privacy Act detail (AIC v ACL ruling, $50M fines, statutory tort); Argon2id OWASP parameters; dual-gate secrets scanning rationale |

**Divergences resolved:**
- OWASP version: Gemini uses 2025; GPT/Perplexity reference 2021/2023. **This standard aligns to 2025** as the most current.
- Severity model: GPT proposes CVSS v4.0 hybrid; Perplexity maps to CVSS v3.1 ranges. **This standard uses the GPT hybrid approach** (CVSS for dependencies, OWASP likelihood x impact for code findings).
- Control ID scheme: Perplexity uses simple A1-A25; GPT uses APP-AC-01 style. **This standard adopts the GPT convention** for clarity and extensibility.
- React2Shell: Only Gemini flagged this. **Included as Critical** given the RCE severity.
- pgAudit: Only Gemini recommended this. **Included** as it directly supports APP 11 and SOC 2 compliance requirements.

### C. Cross-References

| Related Standard | Relationship |
|---|---|
| OPS-STD-001 (AUTH_SSO_STANDARD) | Authentication flows, JWT validation, session management - referenced but not duplicated here |
| OPS-STD-003 (API_CONTRACT_STANDARD) | API versioning, schema validation, OpenAPI spec - will detail APP-INV-01 requirements |
| OPS-STD-004 (FORGE_GATE_POLICY) | Gate review process that enforces these controls - severity to gate mapping defined here |
