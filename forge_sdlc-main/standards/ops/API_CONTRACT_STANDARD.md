# API_CONTRACT_STANDARD.md

**Standard ID:** OPS-STD-003
**Version:** 1.0
**Status:** Draft
**Created:** 2026-03-14
**Scope:** All OnPulse FastAPI backends, Next.js frontends, WebSocket connections, async pipelines, external API integrations, and shared PostgreSQL schema
**Authoritative Standards:** OpenAPI 3.1, AsyncAPI 3.1, RFC 9457 (Problem Details for HTTP APIs), RFC 2119 (Requirement Levels), JSON Schema Draft 2020-12

---

## 1. Contract Architecture

### 1.1 Core Principles

1. **Code-first, spec-as-artefact:** FastAPI's auto-generated OpenAPI is the source of truth for all synchronous HTTP APIs. Specs are exported, versioned, linted, and diffed in CI — not hand-maintained.
2. **AsyncAPI for async:** WebSocket channels and event-driven pipelines (EVGP triggers, pub/sub) are documented via AsyncAPI 3.1.
3. **Generated clients, never hand-written:** TypeScript types and API clients are generated from OpenAPI specs. Frontend code MUST NOT hand-write endpoint URLs or payload types.
4. **Breaking changes are mechanical gates:** OpenAPI diff checks in CI block breaking changes within a major version.
5. **RFC-style language:** This standard uses MUST/SHOULD/MAY per RFC 2119.

### 1.2 Contract Format Matrix

| Interface Type | Contract Format | Source of Truth | Consumers |
|---|---|---|---|
| HTTP REST APIs | OpenAPI 3.1 (JSON) | FastAPI auto-generation | TypeScript codegen, Schemathesis, oasdiff |
| WebSocket channels | AsyncAPI 3.1 (YAML) | Hand-maintained alongside service | Documentation, payload validation |
| Async pipeline triggers | OpenAPI (if HTTP) or AsyncAPI (if event-driven) | Depends on transport | Contract tests |
| External API integrations | Integration Record (Markdown + pinned version) | Integration wrapper module | Smoke tests, schema monitoring |
| Database schema | Alembic migrations + ownership map | Owning service's migration project | Per-service DB roles |

### 1.3 Integration Points (OnPulse Services)

| Producer | Consumer | Transport | Contract |
|---|---|---|---|
| CC backend | CC frontend | REST | OpenAPI (auto-generated) |
| EVGP-1 backend | EVGP-1 frontend | REST | OpenAPI (auto-generated) |
| EVGP-1 | EVGP-2 | HTTP trigger | OpenAPI (auto-generated) |
| CC backend | OpenClaw | HTTP polling (localhost:18793) | OpenAPI or Integration Record |
| ERS backend | ERS frontend | REST | OpenAPI (auto-generated) |
| CC backend | CC frontend | WebSocket | AsyncAPI |
| All backends | PostgreSQL | SQL | Alembic migrations + ownership map |
| Multiple services | Stripe, Sentry, Langfuse, Cal.com | REST | Integration Records |

---

## 2. API Documentation Standards

### 2.1 OpenAPI Specification

**MUST:** Use OpenAPI 3.1 (JSON Schema Draft 2020-12 aligned). FastAPI generates OpenAPI 3.1 by default.

**MUST:** Treat the FastAPI-generated OpenAPI as the canonical HTTP contract. MUST NOT maintain separate hand-written spec files for internal services.

**MUST:** Enrich OpenAPI via Pydantic model metadata:
- `Field(description="...", examples=[...])` on all public-facing fields
- `json_schema_extra` for complex examples
- Tags on all route operations for grouping
- Security scheme declarations

**MUST:** Export `/openapi.json` in CI to a central `contracts/` directory, versioned per service. CI MUST regenerate the spec and fail if the checked-in artefact is stale (diff-based freshness check). CI MUST NOT commit spec changes as part of validation — developers commit updated specs before pushing.

**SHOULD:** Consider contract-first (hand-maintained OpenAPI) only for externally exposed APIs or the most critical cross-team boundaries.

### 2.2 WebSocket & Async Contracts (AsyncAPI)

**MUST:** Document WebSocket endpoints using AsyncAPI 3.1. OpenAPI MUST NOT be used for WebSocket semantics.

AsyncAPI documents MUST include:
- Connection URL(s) and auth handshake
- Client-to-server message types (with JSON Schema payloads)
- Server-to-client event message types
- Ordering guarantees, replay behaviour, and error frames
- Heartbeat/ping strategy and disconnect semantics

**SHOULD:** Reuse Pydantic-derived JSON Schemas for message payloads (DRY principle — same models for REST and WebSocket payloads where applicable).

**MUST:** Maintain `asyncapi.yaml` files alongside each service's OpenAPI file, or in a `contracts/async/` folder per service.

### 2.3 Webhook & Callback Contracts

OpenAPI 3.1 supports top-level `webhooks` and `callbacks` sections for out-of-band HTTP requests.

**SHOULD:** Use OpenAPI `webhooks` to document any service-initiated HTTP requests to consumer endpoints.

**SHOULD:** Use OpenAPI `callbacks` for request/response patterns where the service calls back to a client-provided URL.

---

## 3. API Versioning

### 3.1 Strategy

**MUST:** Default to backwards compatibility as the normal mode of API evolution. Add fields, do not remove or rename them. Keep response objects extensible.

**MUST:** Use path-based major versioning when incompatible changes are unavoidable: `/api/v1/...`, `/api/v2/...`.

**MUST:** Keep minor, backward-compatible changes within a major version (additive fields, new optional parameters, non-breaking behaviour changes).

**MUST:** Deprecate old major versions on a documented schedule with minimum 90-day notice.

**SHOULD:** Version async API channels at the channel level (e.g., `user.signed_up.v1`) or embed version in message schemas.

### 3.2 What Constitutes a Breaking Change

The following changes are **breaking** within a major version and MUST be blocked by CI:

| Change Type | Breaking? | Example |
|---|---|---|
| Remove endpoint | Yes | DELETE `/api/v1/assessments` removed |
| Remove response field | Yes | `scores` field dropped from response |
| Make optional field required | Yes | `company_name` becomes required in request |
| Change field type | Yes | `id` changes from integer to string |
| Change enum values (remove) | Yes | Status `"pending"` removed |
| Add optional request field | No | New optional `notes` field |
| Add response field | No | New `created_at` in response |
| Add new endpoint | No | New GET `/api/v1/reports` |
| Add enum value | No (if consumers handle unknown) | New status `"archived"` |

### 3.3 External API Versioning

**MUST:** Pin external API versions explicitly (e.g., Stripe `Stripe-Version` header, Cal.com v2 header). MUST NOT rely on account defaults.

---

## 4. Naming Conventions

### 4.1 Endpoint Paths

| Rule | Standard | Example |
|---|---|---|
| Case | kebab-case | `/api/v1/user-profiles` |
| Nouns | Plural | `/assessments`, `/reports` |
| Trailing slashes | Forbidden | `/api/v1/users` not `/api/v1/users/` |
| Version prefix | `/api/v{major}/` | `/api/v1/assessments/{id}` |
| Nested resources | Max 2 levels | `/api/v1/assessments/{id}/scores` |

### 4.2 Field Names

| Context | Convention | Example |
|---|---|---|
| JSON request/response payloads | camelCase | `companyName`, `createdAt` |
| Query parameters | snake_case | `?sort_by=created_at&page_size=20` |
| HTTP headers (custom) | Kebab-Case (no `X-` prefix per RFC 6648) | `Correlation-Id`, `Request-Id` |

**MUST:** Configure Pydantic models with `alias_generator=to_camel` to serialize Python snake_case attributes as camelCase in JSON responses.

```python
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

class AssessmentResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
    company_name: str
    created_at: datetime
    # Serializes as {"companyName": "...", "createdAt": "..."}
```

### 4.3 HTTP Methods & Status Codes

| Method | Success Status | Body |
|---|---|---|
| GET (single) | 200 OK | Resource object |
| GET (collection) | 200 OK | Pagination envelope (see section 4.4) |
| POST (create) | 201 Created | Created resource + `Location` header |
| PUT (replace) | 200 OK | Updated resource |
| PATCH (partial update) | 200 OK | Updated resource |
| DELETE | 204 No Content | Empty body |

### 4.4 Pagination Envelope

All collection endpoints MUST return a standard pagination envelope unless explicitly documented as bounded (e.g., lookup endpoints returning a fixed-size result set):

```json
{
  "data": [...],
  "totalCount": 142,
  "limit": 20,
  "offset": 0
}
```

**MUST:** Enforce maximum page size (default: 100, configurable per endpoint).

**MUST NOT:** Allow unbounded queries (no limit). Default limit MUST be applied if omitted.

---

## 5. Schema Consistency

### 5.1 Type Generation Pipeline

```
FastAPI + Pydantic models
        |
        v
  /openapi.json (auto-generated, OpenAPI 3.1)
        |
        v
  CI export to contracts/{service}/openapi.json
        |
        v
  TypeScript codegen (Orval or openapi-typescript)
        |
        v
  Generated types + clients + React Query hooks
        |
        v
  Frontend imports generated package (never hand-writes types)
```

### 5.2 Code Generation Tools

| Tool | Use Case | Version (March 2026) |
|---|---|---|
| **Orval** | Client-side React code: generates TanStack Query hooks + MSW mocks from OpenAPI | v8.5.2 |
| **openapi-typescript** | Runtime-free TypeScript type generation from OpenAPI 3.0/3.1 | v7.13.0 |
| **openapi-fetch** | Typed fetch client built on openapi-typescript types | v0.17.0 |
| **@hey-api/openapi-ts** | Server-side Next.js: standard fetch clients + precise types | v0.94.0 |

**Recommended split:**
- **Client-side React (React Query hooks):** Orval
- **Server-side Next.js (Server Components, no hooks):** @hey-api/openapi-ts or openapi-fetch

### 5.3 Optional, Nullable, and Enum Conventions

**Optional vs Nullable distinction (Pydantic v2 → OpenAPI 3.1 → TypeScript):**

| Python (Pydantic) | OpenAPI 3.1 | TypeScript | When to Use |
|---|---|---|---|
| `field: str` | required, non-nullable | `field: string` | Always present, always has value |
| `field: str \| None = None` | optional, nullable | `field?: string \| null` | May be omitted; if present, may be null |
| `field: str \| None` (no default) | required, nullable | `field: string \| null` | Must be present, but may be null |

**MUST:** Only use "optional + nullable" when you genuinely have three states (present value, explicit null, omitted). Common valid case: PATCH semantics where omitted = "don't change" and null = "clear."

**MUST:** Use string-based enums derived from `str, Enum` in Python to ensure code generators produce strict TypeScript string literal union types (not generic strings).

```python
from enum import Enum

class AssessmentStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "inProgress"
    COMPLETE = "complete"
```

**MUST:** Keep the default FastAPI "separate I/O schemas" behaviour (e.g., `Item-Input` vs `Item-Output`) for correctness.

### 5.4 Validation at System Boundaries

| Boundary | Validation Approach |
|---|---|
| Inbound HTTP to FastAPI | Pydantic models (automatic via FastAPI). MUST be the primary validation layer. |
| Outbound to internal services | Typed client with generated types. SHOULD validate responses if correctness is critical. |
| Async messages (WebSocket, events) | JSON Schema validation against Pydantic-derived schemas at boundary. |
| Frontend forms | Zod schemas, ideally generated from OpenAPI (via ts-to-zod or Orval). |
| API gateway (if introduced) | Augments service validation (rate limiting, basic schema). MUST NOT replace service-level validation. |

---

## 6. Contract Testing

### 6.1 Minimum Viable Contract Testing Stack

For a small team (1-2 developers, 7+ services), the recommended stack in priority order:

| Layer | Tool | Purpose | Effort |
|---|---|---|---|
| 1. OpenAPI diff | **oasdiff** | Detect breaking changes between PR and main branch | Very low |
| 2. OpenAPI lint | **Spectral** or **Redocly CLI** | Enforce naming, structure, and completeness rules | Low |
| 3. Schema-driven fuzz | **Schemathesis** (v4.12.0) | Property-based testing: generates test cases from OpenAPI, validates responses match spec | Low |
| 4. Type-safe clients | **Orval** / **openapi-typescript** | TypeScript compiler becomes a contract validator — wrong endpoint or payload is a compile error | Medium |
| 5. Consumer-driven (selective) | **Pact** (pact-js + pact-python) | Only for highest-risk cross-service links | Higher |

**MUST NOT** start with Pact. Start with OpenAPI diff + Schemathesis, which catch most real issues with minimal overhead. Add Pact selectively later for:
- CC frontend <> CC backend
- EVGP-1 frontend <> EVGP-1 backend
- EVGP-1 <> EVGP-2 pipeline boundary

### 6.2 Breaking Change Detection (CI)

**MUST:** Run oasdiff (or openapi-diff) on every PR that modifies a FastAPI service:

```bash
# Compare PR spec against main branch spec
oasdiff breaking ./contracts/service/openapi-main.json ./contracts/service/openapi-pr.json
```

Build MUST fail if breaking changes are detected within a major version.

### 6.3 Schemathesis Provider Testing

**MUST:** Run Schemathesis on core services (CC, EVGP-1, ERS) to validate implementation matches OpenAPI spec:

```python
import schemathesis
from myapp import app

schema = schemathesis.openapi.from_asgi("/openapi.json", app)

@schema.parametrize()
def test_api_conforms(case):
    case.call_and_validate()
```

This catches 500s, schema violations, and edge-case validation bugs without network calls (ASGI transport).

### 6.4 Pact Consumer-Driven Testing (Selective)

When applied to high-risk links:

**Consumer (Next.js, pact-js):**
- Define expected interactions using `@pact-foundation/pact` PactV3
- Point API client at Pact mock server during tests
- Generates `pacts/{consumer}-{provider}.json` contract files

**Provider (FastAPI, pact-python):**
- Verify contracts against running FastAPI instance
- Blocks deployment if verification fails

---

## 7. Error Response Standardisation

### 7.1 RFC 9457 Problem Details

**MUST:** All FastAPI services MUST return errors in RFC 9457 (Problem Details for HTTP APIs) format. This supersedes RFC 7807.

**Content-Type:** `application/problem+json`

**Required fields:**

```json
{
  "type": "https://errors.onpulse.com.au/auth/invalid-credentials",
  "title": "Invalid credentials",
  "status": 401,
  "detail": "Email or password is incorrect.",
  "instance": "urn:uuid:550e8400-e29b-41d4-a716-446655440000"
}
```

**Extension fields (standard across OnPulse services):**

```json
{
  "type": "https://errors.onpulse.com.au/validation/payload-invalid",
  "title": "Unprocessable Entity",
  "status": 422,
  "detail": "The payload contains validation errors.",
  "instance": "/api/v1/assessments",
  "code": "VALIDATION_PAYLOAD_INVALID",
  "correlationId": "req-abc123",
  "errors": [
    {"field": "companyName", "message": "Field is required"},
    {"field": "revenue", "message": "Must be a positive number"}
  ]
}
```

### 7.2 FastAPI Implementation

**MUST:** Use `fastapi-problem-details` to override default FastAPI exception handlers with RFC 9457 compliant payloads.

**MUST:** All custom exceptions inherit from a base `ProblemDetailsException` class.

**MUST NOT:** Return stack traces, internal paths, or debug information in production error responses (cross-ref OPS-STD-002 APP-ERR-01).

### 7.3 Error Code Registry

**MUST:** Maintain a central error code registry as versioned YAML:

```yaml
# contracts/error-registry.yaml
errors:
  AUTH_INVALID_CREDENTIALS:
    service: auth
    status: 401
    type: "https://errors.onpulse.com.au/auth/invalid-credentials"
    description: "Email or password is incorrect"
    retryable: false

  EVGP_PIPELINE_TIMEOUT:
    service: evgp-2
    status: 504
    type: "https://errors.onpulse.com.au/evgp/pipeline-timeout"
    description: "Processing pipeline exceeded timeout"
    retryable: true

  ERS_ASSESSMENT_NOT_FOUND:
    service: ers
    status: 404
    type: "https://errors.onpulse.com.au/ers/assessment-not-found"
    description: "Assessment with given ID does not exist"
    retryable: false
```

**MUST:** Include `retryable` flag to guide frontend retry logic.

### 7.4 Frontend Error Handling

**MUST:** Parse Problem Details responses and map to internal error type union (`UserError`, `SystemError`, `NetworkError`).

**MUST:** Use `code` field for programmatic handling, `detail` for user-facing messages.

**SHOULD:** Implement a shared TanStack Query error handler that:
- Distinguishes validation/user errors (no retry) from transient/system errors (retry with backoff)
- Integrates with toast notifications and error boundaries

### 7.5 Retry & Resilience Patterns

**MUST:** Use exponential backoff with jitter for cross-service and external API retries (not static retry loops).

**SHOULD:** Implement circuit breaker pattern for critical integrations:
- After N consecutive failures, trip to "open" state and fail fast
- During open state, execute fallback (dead-letter queue or graceful degradation)
- Prevents thundering herd on recovering services

**MUST:** Define per-endpoint retry policies based on idempotency:

| Method | Idempotent | Safe to Retry |
|---|---|---|
| GET | Yes | Yes |
| PUT | Yes | Yes |
| DELETE | Yes | Yes (with caution) |
| POST | No (unless idempotency key) | Only with idempotency key |
| PATCH | Depends | Only if idempotent |

**SHOULD:** Use idempotency keys for non-idempotent operations (payments, pipeline triggers).

---

## 8. External API Contract Management

### 8.1 Integration Records

**MUST:** For each external API integration, maintain an integration record at `docs/integrations/{service}.md` containing:

| Field | Content |
|---|---|
| Base URLs | Sandbox and production endpoints |
| API version | Pinned version and how configured (header, dashboard) |
| Authentication | Mechanism and secrets location (reference secrets manager, not inline) |
| Endpoints used | List with links to provider docs |
| Rate limits | Global and per-key limits; backoff strategy |
| Error formats | Provider error structure and mapping to internal error codes |
| Retry rules | Idempotency expectations; max retries; backoff parameters |
| Failure modes | What happens when provider is down; alerting thresholds |

### 8.2 Typed Wrapper/Adapter Pattern

**MUST:** Every external API call MUST go through a typed wrapper module:

```
integrations/
  stripe.py        # Stripe API adapter
  calcom.py        # Cal.com adapter
  sentry_client.py # Sentry API adapter
  apollo.py        # Apollo enrichment adapter
  langfuse.py      # Langfuse adapter
```

Each wrapper MUST:
- Centralise authentication and retry/backoff logic
- Map external response structures to internal Pydantic models (Adapter Pattern)
- Isolate vendor SDK changes from core application logic
- Provide a single place for observability (logging, metrics, tracing)

**MUST NOT:** Expose raw external API data structures directly to internal application logic.

### 8.3 External Change Detection

**SHOULD:** Implement scheduled smoke tests (daily/weekly) against external APIs:
- Hit critical endpoints with safe test data (e.g., zero-dollar Stripe authorisation)
- Validate response structure against expected JSON schema
- Alert on unexpected changes

**SHOULD:** Monitor provider changelogs (Stripe, Cal.com, Sentry) via automated monitoring or RSS feeds.

### 8.4 Rate Limit Enforcement

**MUST:** Rate limit enforcement MUST be localised within the adapter module (not downstream clients).

**SHOULD:** Implement proactive throttling (Token Bucket or Leaky Bucket algorithm with Redis state) before dispatching requests to external providers.

**MUST:** Log and alert on rate limit breaches; surface to calling services via standardised error codes (e.g., `UPSTREAM_RATE_LIMITED`).

---

## 9. Database Schema as Contract

### 9.1 Shared Database Governance

The shared PostgreSQL database is an implicit cross-service contract. Without governance, schema changes by one service can break others.

**MUST:** Define table ownership — each table/view has an owning service responsible for schema changes.

**MUST:** Enforce access boundaries with PostgreSQL roles:
- Per-service DB users with least privilege
- Each service accesses only its own schema namespace

**SHOULD:** Move toward schema-per-service within the same PostgreSQL cluster:

```
onpulse_db/
  schema_cc/        # Command Centre owns these tables
  schema_evgp1/     # EVGP-1 owns these tables
  schema_evgp2/     # EVGP-2 owns these tables
  schema_ers/       # ERS owns these tables
  schema_outreach/  # Outreach owns these tables
  schema_common/    # Shared lookup tables (central migration project)
```

**MUST:** When another service needs data from a different service's schema, expose a stable SQL View rather than granting direct table access. Views act as database-level API contracts.

### 9.2 Alembic Migration Coordination

**MUST:** Use timestamp-based revision identifiers (e.g., `202603140130_add_user_field`) instead of random hash identifiers. Reduces merge conflicts in multi-developer environments.

**MUST:** Configure Alembic `env.py` to target specific logical schemas based on the service initiating migration. Each service maintains its own independent `alembic_version` tracking table within its designated schema namespace.

**MUST:** Run migration CI check that executes `alembic check` or applies migrations against an ephemeral shadow database. Blocks PR merge if migration files produce conflicting heads.

**Migration review checklist:**
- [ ] Are any columns dropped or made non-nullable?
- [ ] Are there data-migration steps that need coordination with application releases?
- [ ] Does any other service read/write this table/column?
- [ ] Is the migration idempotent and reversible where possible?
- [ ] Has the table ownership map been updated?

### 9.3 Future Direction

**SHOULD:** Incrementally adopt "logical database per service" on the same PostgreSQL server (separate schemas + separate DB users). Full database-per-service migration is deferred until justified by scale or isolation requirements.

---

## 10. Documentation & Discovery

### 10.1 Per-Service Documentation

**MUST:** Ensure `/docs` (Swagger UI), `/redoc`, and `/openapi.json` are enabled in non-production environments.

**MUST:** Use Swagger UI for interactive endpoint testing during development.

**SHOULD:** Use ReDoc for rich 3-panel documentation layout in developer portals.

### 10.2 Central API Catalogue

**SHOULD:** Aggregate all OpenAPI and AsyncAPI specs into a centralised internal developer portal (Backstage or similar) that shows:
- All services and their APIs
- `providesApi` / `consumesApi` relationships
- Cross-service dependency graph

For a small team, a static site rendering ReDoc or Swagger UI per spec file is sufficient initially.

### 10.3 Cross-Service API Map

**SHOULD:** Maintain a `contracts/system-map.yaml` annotating:
- Producer-consumer relationships for all HTTP integrations
- Non-HTTP dependencies (DB schemas, queues, cron jobs)
- External API integrations

Once generated TypeScript clients are fully adopted, the OpenAPI specs themselves effectively serve as the producer-consumer map.

### 10.4 Per-Service Contract Document Template

```markdown
# {SERVICE_NAME} API Contract

## Overview
- Service: {SERVICE_NAME}
- Owner: {TEAM/ENGINEER}
- Base URL(s): Internal: https://internal.example.com/{service}
- Primary consumers: {list of frontends/services}

## Specifications
- OpenAPI: ./contracts/{service}/openapi.v{major}.json
- AsyncAPI (if applicable): ./contracts/{service}/asyncapi.yaml
- API versioning policy: v1 in path, 90-day deprecation minimum.

## Authentication & Authorization
- Auth scheme, required headers, scopes.

## API Invariants
- Idempotency expectations per endpoint
- Timeouts and pagination conventions
- Backwards compatibility rules

## Data Model Rules
- Null vs omitted semantics (PATCH)
- Enum extensibility policy

## Error Contract
- Error format (RFC 9457) and error codes (link to registry)

## Operational Contract
- Rate limits (internal and external)
- SLOs (latency/availability)
- Observability: correlation IDs, log fields, tracing

## Consumer Guidance
- Example flows, common mistakes, migration notes
```

---

## 11. Automation & CI Integration

### 11.1 Backend CI Pipeline (FastAPI)

```
On every PR:
  1. Start FastAPI app in test mode
  2. Export /openapi.json
  3. Lint spec (Spectral / Redocly CLI)
  4. Diff spec against main (oasdiff breaking)
     -> FAIL if breaking changes detected
  5. Run Schemathesis tests
     -> FAIL if responses violate spec
  6. Commit spec to contracts/{service}/openapi.json
  7. Run Pact provider verification (if contracts exist)
     -> FAIL if provider can't satisfy consumer expectations
```

### 11.2 Frontend CI Pipeline (Next.js)

```
On every PR:
  1. Download backend OpenAPI specs from contracts/
  2. Generate TypeScript types + clients (Orval / openapi-typescript)
  3. TypeScript compile
     -> FAIL if generated types don't match usage
  4. Run Pact consumer tests (if configured)
     -> Generate pact contract files
  5. Build
```

### 11.3 Toolchain Summary

| Tool | Version (March 2026) | Purpose | Gate |
|---|---|---|---|
| FastAPI | latest | OpenAPI 3.1 auto-generation | - |
| Schemathesis | v4.12.0 | Property-based API testing | CI (backend) |
| oasdiff | latest | Breaking change detection (300+ rules) | CI (backend) |
| Spectral | latest | OpenAPI linting against custom rulesets | CI (backend) |
| Orval | v8.5.2 | React Query hooks + MSW mocks from OpenAPI | CI (frontend) |
| openapi-typescript | v7.13.0 | TypeScript types from OpenAPI | CI (frontend) |
| openapi-fetch | v0.17.0 | Typed fetch client | CI (frontend) |
| @hey-api/openapi-ts | v0.94.0 | Server-side Next.js fetch clients | CI (frontend) |
| pact-js | latest | Consumer-driven contracts (JS consumer) | CI (frontend, selective) |
| pact-python | v3.0.0a1 / v2.x | Consumer-driven contracts (Python provider) | CI (backend, selective) |
| fastapi-problem-details | latest | RFC 9457 error responses | Runtime |
| Alembic | v1.18.4 | Database migrations | CI (migration check) |

---

## 12. Implementation Roadmap

### Phase 1: Visible Contracts (Week 1-2)
- [ ] Enable and standardise OpenAPI publishing for all FastAPI services
- [ ] Add CI step to export `/openapi.json` to `contracts/` directory
- [ ] Lint specs with Spectral
- [ ] Standardise error responses with `fastapi-problem-details` (RFC 9457) on one service
- [ ] Define error code registry (initial entries)
- [ ] Configure Pydantic `alias_generator=to_camel` across all services

### Phase 2: Prevent Breakage (Week 3-4)
- [ ] Add oasdiff breaking change detection to all backend PRs
- [ ] Add Schemathesis to CC and EVGP-1 backend CI
- [ ] Establish deprecation policy and changelog process
- [ ] Define pagination envelope standard across all collection endpoints

### Phase 3: Type-Safe Clients (Week 5-6)
- [ ] Introduce Orval in CC frontend; generate React Query hooks from OpenAPI
- [ ] Introduce @hey-api/openapi-ts for server-side Next.js data fetching
- [ ] Refactor frontend to import from generated packages (eliminate hand-written URLs/types)
- [ ] TypeScript compiler becomes contract validator

### Phase 4: Documentation & Discovery (Week 7-8)
- [ ] Document CC WebSocket channels in AsyncAPI
- [ ] Create integration records for all external APIs (Stripe, Cal.com, Sentry, etc.)
- [ ] Deploy central API catalogue (Backstage or static ReDoc site)
- [ ] Create cross-service system map

### Phase 5: Database & Advanced (Week 9-10)
- [ ] Define table ownership map for shared PostgreSQL
- [ ] Migrate to schema-per-service with per-service DB roles
- [ ] Configure Alembic timestamp-based revisions
- [ ] Add Alembic migration CI checks
- [ ] Add selective Pact contracts for highest-risk links

---

## Appendices

### A. Standards References

| Standard | Relevance |
|---|---|
| OpenAPI 3.1 Specification | HTTP API contract format |
| AsyncAPI 3.1 Specification | WebSocket/event-driven contract format |
| JSON Schema Draft 2020-12 | Schema validation (aligned with OpenAPI 3.1) |
| RFC 9457 (Problem Details) | Error response format (supersedes RFC 7807) |
| RFC 2119 (Requirement Levels) | MUST/SHOULD/MAY keyword definitions |
| Zalando REST API Guidelines | Naming, versioning, and compatibility rules |
| Google AIP-185 | Major version in URI path for REST |
| api.gov.au Naming Conventions | Australian government API naming reference |

### B. Source Alignment

This standard synthesises research from three independent AI providers:

| Source | Unique Contributions |
|---|---|
| **Perplexity** | Most comprehensive tool version matrix; detailed Pact consumer/provider code examples (pact-js + pact-python); per-service contract document template; priority roadmap (8 phases); Schemathesis ASGI integration example; optional/nullable/enum handling detail |
| **GPT 5.4** | Strongest on versioning trade-offs (Zalando vs Google AIP-185 vs Microsoft); AsyncAPI webhooks/callbacks detail; shared DB governance patterns (views as contracts); Schemathesis + oasdiff as recommended first tools (Pact deferred); CI pipeline patterns; Backstage API catalogue; RFC 9457 over RFC 7807 |
| **Gemini Pro 3.1** | Adapter Pattern for external APIs (isolation of vendor SDK churn); rate limit enforcement in adapter modules (Token Bucket/Leaky Bucket with Redis); circuit breaker + exponential backoff with jitter; DRY principle for AsyncAPI payloads from Pydantic; database views as database-level API contracts; PostgreSQL schema namespaces for logical service isolation; Alembic timestamp-based revision IDs; Orval vs @hey-api/openapi-ts split (client vs server); Zod generation from OpenAPI; RFC 9457 `fastapi-problem-details` package |

**Divergences resolved:**
- **Versioning strategy:** Zalando recommends avoiding versioning; Google mandates `/v1` in URL. **This standard adopts path-based major versioning** as most practical for internal services, but defaults to backwards compatibility first.
- **Contract testing first tool:** GPT recommends oasdiff + Schemathesis first, Pact later. Perplexity recommends Pact from the start for critical links. **This standard follows GPT's phased approach** — oasdiff + Schemathesis first, Pact selectively later.
- **Code generation tool:** All sources recommend openapi-typescript/Orval. Gemini adds @hey-api/openapi-ts for server-side. **This standard recommends the split** (Orval for client React, @hey-api for server-side Next.js).
- **Error format:** All sources converge on RFC 9457. Perplexity notes `fastapi-rfc7807` (v0.5.0) as alternative. **This standard uses RFC 9457** via `fastapi-problem-details` as the newer spec.
- **Field naming:** Gemini mandates camelCase for JSON. Perplexity/GPT allow snake_case in query params. **This standard uses camelCase for JSON bodies, snake_case for query params** — matching JavaScript conventions for bodies and Python conventions for URL params.

### C. Cross-References

| Related Standard | Relationship |
|---|---|
| OPS-STD-001 (AUTH_SSO_STANDARD) | Authentication mechanisms referenced by API contract auth sections |
| OPS-STD-002 (SECURITY_CONTROLS) | APP-ERR-01 (no debug info in errors), APP-INV-01 (OpenAPI spec diffing), APP-AC-04 (response schemas) defined there, enforced here |
| OPS-STD-004 (FORGE_GATE_POLICY) | Gate review process that validates contract compliance |
