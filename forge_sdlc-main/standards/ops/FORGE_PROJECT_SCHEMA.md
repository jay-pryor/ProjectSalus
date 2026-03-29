# FORGE_PROJECT_SCHEMA.md

**Standard ID:** OPS-STD-005
**Version:** 1.0
**Status:** Draft
**Created:** 2026-03-14
**Scope:** All OnPulse repositories registered with Forge SDLC on EX44
**Depends on:** OPS-STD-002 (Security Controls), OPS-STD-003 (API Contract Standard), OPS-STD-004 (Forge Gate Policy)

---

## 1. Purpose

Every repository managed by Forge MUST contain a `forge.project.yaml` at its root. This file is the single machine-readable profile that tells all Forge operations — audits, gates, remediation, contract sync, reverse documentation — what the repo contains, how to build/test/lint it, and which quality policies apply.

Without `forge.project.yaml`, Forge operations fall back to generic heuristics. With it, they execute the exact tools, agents, and thresholds appropriate to the repo's stack.

---

## 2. Schema Version

**MUST:** Every `forge.project.yaml` begins with a `schema_version` field. This enables migration tooling when the schema evolves.

```yaml
schema_version: "1.0"
```

Breaking changes to this schema MUST increment the major version. Additive fields increment the minor version. The auto-detection tool (S01.P04) MUST refuse to overwrite a file with a newer schema version than it understands.

---

## 3. Complete Schema Definition

```yaml
# forge.project.yaml — Full Schema Reference
# All fields marked [REQUIRED] must be present. All others are optional with documented defaults.

schema_version: "1.0"                    # [REQUIRED] Schema version for migration compatibility

# ─── 3.1 Project Identity ────────────────────────────────────────────────────

project:
  name: "ers"                            # [REQUIRED] Machine-readable project identifier (lowercase, hyphens)
  display_name: "Exit Readiness Snapshot" # [REQUIRED] Human-readable project name
  description: "AI-powered business assessment tool" # Short description for reports
  owner: "liam"                          # Primary owner (maps to GitHub / notification routing)
  repo_url: "https://github.com/onpulse/ers" # GitHub repository URL
  service_map_ref: "ers"                 # Key in Forge service_map.yaml (omit if not in service map)

# ─── 3.2 Stack Declaration ───────────────────────────────────────────────────

stack:
  languages:                             # [REQUIRED] List of primary languages
    - python
  language_versions:                     # Pinned versions for tooling compatibility
    python: "3.12"
  frameworks:                            # [REQUIRED] Frameworks in use
    - fastapi
    - langgraph
  service_type: "api"                    # [REQUIRED] One of: api | frontend | fullstack | pipeline | library | cli | infrastructure
  runtime: "docker"                      # One of: docker | bare | serverless | lambda
  package_managers:                      # Auto-detected if omitted
    - pip

# ─── 3.3 Directory Layout ────────────────────────────────────────────────────

paths:
  source: "src/"                         # Primary source directory. Default: "src/"
  tests: "tests/"                        # Test directory. Default: "tests/"
  docs: "docs/"                          # Documentation directory. Default: "docs/"
  forge_sdlc: "05_SDLC/"                # Forge SDLC artefact directory (phase specs, evidence)
  openapi_spec: "openapi.json"           # OpenAPI spec path (auto-generated or hand-written)
  asyncapi_spec: null                    # AsyncAPI spec path (null = not applicable)
  alembic: "alembic/"                    # Database migration directory
  docker_compose: "docker-compose.yml"   # Docker Compose file path
  dockerfile: "Dockerfile"               # Dockerfile path (null if not containerised)
  nginx_config: null                     # Nginx config directory (null if no nginx)
  ci_config: null                        # CI/CD config path (.github/workflows/, .gitlab-ci.yml)

# ─── 3.4 Build & Run Commands ────────────────────────────────────────────────

commands:
  install: "pip install -e '.[dev]'"     # Dependency installation
  build: null                            # Build step (null = no build required)
  test: "pytest -x -q"                   # [REQUIRED] Test runner command
  test_coverage: "pytest --cov=src --cov-report=term-missing" # Coverage command
  lint: "ruff check ."                   # Lint command
  format: "ruff format ."               # Format command
  typecheck: "mypy src/"                 # Type-checking command
  serve: "uvicorn src.main:app --reload" # Local dev server
  migrate: "alembic upgrade head"        # Database migration command

# ─── 3.5 Toolchain Configuration ─────────────────────────────────────────────
# Maps tool names to their activation status and config overrides.
# Tools not listed here inherit defaults from the gate policy (OPS-STD-004).

tools:
  ruff:
    enabled: true
    config: "pyproject.toml"             # Config file path (relative to repo root)
  mypy:
    enabled: true
    config: "pyproject.toml"
  eslint:
    enabled: false                       # Disabled — no JS/TS in this repo
  tsc:
    enabled: false
    config: "tsconfig.json"              # TypeScript config file
  prettier:
    enabled: false                       # Code formatter for JS/TS/CSS/JSON
    config: ".prettierrc"                # Prettier config file
  semgrep:
    enabled: true
    rulesets:
      - "p/python"
      - "p/owasp-top-ten"
      - "p/fastapi"
    custom_rules: ".semgrep/"            # Path to repo-specific custom rules
  detect_secrets:
    enabled: true
    baseline: ".secrets.baseline"
  pip_audit:
    enabled: true
  npm_audit:
    enabled: false
  trivy:
    enabled: true
  pytest:
    enabled: true
    coverage_threshold: 80               # Minimum coverage percentage for gate pass
  jest:
    enabled: false

# ─── 3.6 Gate Policy Overrides ────────────────────────────────────────────────
# Per-repo overrides to the global gate policy (OPS-STD-004).
# Only deviations from the default policy need to be specified here.

gates:
  trust_tier: 2                          # Default trust tier: 1 (auto-merge) | 2 (supervised) | 3 (human-gated)
  critical_modules:                      # Modules where Medium findings also block at Release Gate
    - "src/auth/"
    - "src/payments/"
  commit_gate:
    extra_tools: []                      # Additional tools beyond the global commit gate default
    disabled_tools: []                   # Tools to skip at this gate (e.g., slow tools for rapid iteration)
    extra_agents: []                     # Additional specialist agents
    disabled_agents: []                  # Agents to skip
  pr_gate:
    extra_tools:
      - oasdiff                          # Enable contract diff checking for API repos
    disabled_tools: []
    extra_agents: []
    disabled_agents: []
    coverage_threshold_override: null    # Override the global coverage threshold (null = use global)
  release_gate:
    extra_tools: []
    disabled_tools: []
    extra_agents: []
    disabled_agents: []
    require_sbom: true                   # Generate SBOM at release (default: true)

# ─── 3.7 Security Profile ────────────────────────────────────────────────────
# Declares which security control families from OPS-STD-002 apply to this repo.

security:
  handles_pii: true                      # Triggers APP-AC, LOG controls, Australian Privacy Act compliance
  handles_payments: false                # Triggers payment-specific controls
  handles_auth: true                     # Triggers AUTH_SSO_STANDARD (OPS-STD-001) compliance checks
  exposed_to_internet: true              # Triggers APP-HEADERS, APP-RATE, infrastructure hardening
  has_file_uploads: false                # Triggers APP-IV-02 upload validation controls
  has_webhooks: false                    # Triggers APP-WEBHOOK-01 controls

# ─── 3.8 API Contract Configuration ──────────────────────────────────────────
# Declares API contract obligations per OPS-STD-003.

api:
  role: "producer"                       # One of: producer | consumer | both | none
  versioning_strategy: "path"            # One of: path (/api/v1/) | header | query | none
  current_version: "v1"
  contract_testing:
    oasdiff: true                        # Enable breaking-change detection
    schemathesis: true                   # Enable property-based API testing
    pact: false                          # Enable consumer-driven contract testing (selective)
  consumers:                             # Services that consume this API (for contract sync)
    - "command-centre"
  producers_consumed:                    # APIs this service consumes (for contract sync)
    - "stripe"
    - "cal-com"

# ─── 3.9 Database Configuration ──────────────────────────────────────────────

database:
  engine: "postgresql"                   # One of: postgresql | sqlite | none
  schema_namespace: "ers"                # PostgreSQL schema namespace (per OPS-STD-003 Section 9)
  migration_tool: "alembic"              # One of: alembic | prisma | knex | none
  has_views_as_contracts: false          # Whether cross-service views are defined (OPS-STD-003 Section 9.3)

# ─── 3.10 Deployment Configuration ───────────────────────────────────────────

deploy:
  target: "ops_vps"                      # Deploy target key from service_map.yaml
  method: "docker-compose"               # One of: docker-compose | kubernetes | bare | manual
  health_check: "/health"                # Health check endpoint path
  rollback_strategy: "docker"            # One of: docker (previous image) | git (revert) | manual

# ─── 3.11 Forge SDLC Metadata ────────────────────────────────────────────────

forge:
  sdlc_enabled: true                     # Whether this repo uses Forge SDLC phase structure
  naming_convention: "S##.P##.T##"       # Phase naming convention
  branch_pattern: "s##-p##-description"  # Branch naming pattern
  evidence_required: true                # Whether phase completion requires evidence files
  review_models:                         # Model overrides for this repo (overrides review_models.yaml)
    security: null                       # null = use default from review_models.yaml
    silent_failure: null
    type_safety: null
    performance: null
    contract: null
    test_coverage: null
    synthesizer: null

# ─── 3.12 Provenance Metadata ────────────────────────────────────────────────
# Tracks which fields were auto-detected vs manually set.
# Used by the auto-detection tool to avoid overwriting manual values on re-runs.

_meta:
  auto_detected:                         # Fields populated by the profiler
    - "stack.languages"
    - "stack.frameworks"
    - "stack.package_managers"
    - "paths.source"
    - "paths.tests"
    - "commands.test"
    - "commands.lint"
    - "tools.ruff.enabled"
    - "tools.mypy.enabled"
    - "database.engine"
  manual:                                # Fields explicitly set by the user (never overwritten)
    - "security.handles_pii"
    - "security.handles_auth"
    - "gates.trust_tier"
    - "gates.critical_modules"
  requires_confirmation:                 # Low-confidence auto-detections awaiting user review
    - "security.handles_auth"
  last_profiled: "2026-03-14"           # ISO 8601 date of last auto-detection run
```

---

## 4. Field Reference

### 4.1 `service_type` Values

| Value | Description | Example Repos | Default Tools |
|---|---|---|---|
| `api` | FastAPI or similar REST/WebSocket backend | ers, evgp-system, evgp-2-processing | ruff, mypy, semgrep, pip-audit, detect-secrets, pytest |
| `frontend` | Next.js or React SPA | command-centre (frontend) | eslint, tsc, semgrep, npm-audit, jest |
| `fullstack` | Monorepo containing both backend and frontend | command-centre | All Python + All JS/TS tools |
| `pipeline` | Data processing / ETL / batch pipeline | evgp-2-processing, blog-automation | ruff, mypy, semgrep, pip-audit, pytest |
| `library` | Shared library / SDK | forge-sdlc | ruff, mypy, pytest (no deploy/infra checks) |
| `cli` | Command-line tool | openclaw scripts | ruff, mypy, detect-secrets |
| `infrastructure` | Deployment configs, IaC, docker configs | infrastructure | trivy, detect-secrets, Dockerfile lint |

### 4.2 `trust_tier` Values

Per OPS-STD-004 Section 6:

| Tier | Policy | When to Use |
|---|---|---|
| `1` | Auto-merge after all gates pass | Dependency updates, localised bug fixes, isolated components |
| `2` | Supervised — queued for optional human review | Most feature work, API changes, moderate-risk changes |
| `3` | Human-gated — requires manual sign-off | Auth/payment flows, DB schema changes, architecture redesigns |

### 4.3 `security` Flags → Control Families

Each security flag activates specific control families from OPS-STD-002:

| Flag | Control Families Activated |
|---|---|
| `handles_pii: true` | APP-AC, LOG-01 through LOG-04, Australian Privacy Act retention controls |
| `handles_payments: true` | APP-AC, APP-CRYPTO, APP-IV (strict), APP-WEBHOOK |
| `handles_auth: true` | Full OPS-STD-001 compliance check, APP-AC, APP-CRYPTO |
| `exposed_to_internet: true` | APP-HEADERS, APP-RATE, APP-XSS, INF-NGINX, INF-DOCKER |
| `has_file_uploads: true` | APP-IV-02 (file type validation via magic bytes, size limits, sandboxed storage) |
| `has_webhooks: true` | APP-WEBHOOK-01 (signature verification, strict schema validation) |

### 4.4 `api.role` Values

| Value | Meaning | Contract Obligations (OPS-STD-003) |
|---|---|---|
| `producer` | This repo serves APIs consumed by others | MUST maintain OpenAPI spec, MUST run oasdiff on changes, MUST notify consumers of breaking changes |
| `consumer` | This repo consumes external APIs | SHOULD validate against producer specs, MAY use Pact for critical integrations |
| `both` | This repo both produces and consumes APIs | All producer + consumer obligations apply |
| `none` | No API surface | Contract testing tools disabled |

---

## 5. Auto-Detection Logic

The repo profiler (S01.P04) MUST auto-detect field values using these heuristics. Manual overrides in the YAML always take precedence.

### 5.1 Detection Rules

| Field | Detection Method | Confidence |
|---|---|---|
| `stack.languages` | Presence of `pyproject.toml` / `setup.py` → Python; `package.json` → JavaScript/TypeScript; `tsconfig.json` → TypeScript; `go.mod` → Go | High |
| `stack.language_versions` | Parse `pyproject.toml` `[project] requires-python`, parse `.python-version`, parse `package.json` `engines.node` | High |
| `stack.frameworks` | Grep imports: `from fastapi` → FastAPI; `from django` → Django; `"next"` in package.json deps → Next.js; `from langgraph` → LangGraph | High |
| `stack.service_type` | FastAPI + no frontend → `api`; Next.js + no backend → `frontend`; both → `fullstack`; Dockerfile/Compose present AND no application source code (no `src/`, no `app/`, no Python/TS packages) → `infrastructure`; `[project.scripts]` in pyproject.toml with no web framework → `cli` or `library` | Medium |
| `stack.package_managers` | `pyproject.toml` / `requirements.txt` → pip; `package-lock.json` → npm; `yarn.lock` → yarn; `pnpm-lock.yaml` → pnpm | High |
| `paths.source` | Scan for `src/`, `app/`, `lib/`, or top-level Python packages | Medium |
| `paths.tests` | Scan for `tests/`, `test/`, `__tests__/`, `spec/` | High |
| `paths.alembic` | Presence of `alembic.ini` → parse `script_location` | High |
| `paths.openapi_spec` | Scan for `openapi.json`, `openapi.yaml`, `docs/openapi.json` | Medium |
| `paths.docker_compose` | Scan for `docker-compose.yml`, `docker-compose.yaml`, `compose.yml` | High |
| `commands.test` | `pyproject.toml` `[tool.pytest]` → `pytest`; `package.json` `scripts.test` → parse value | High |
| `commands.lint` | `pyproject.toml` `[tool.ruff]` → `ruff check .`; `package.json` → parse `scripts.lint` | High |
| `tools.*.enabled` | Tool config file exists (e.g., `pyproject.toml` has `[tool.ruff]` → ruff enabled; `.eslintrc.*` exists → eslint enabled) | High |
| `security.handles_auth` | Grep for `oauth`, `jwt`, `authentik`, `login`, `session` in source | Medium |
| `security.handles_pii` | Grep for `email`, `phone`, `address`, `date_of_birth`, `ssn`, `tax` in models/schemas | Low |
| `database.engine` | Parse `DATABASE_URL` or `sqlalchemy.url` patterns; presence of `prisma/schema.prisma` | High |
| `deploy.target` | Cross-reference `service_map.yaml` by project name | High |
| `api.role` | FastAPI app with `/api/` routes → `producer`; `fetch`, `axios`, `httpx.AsyncClient` in source → `consumer` | Medium |

### 5.2 Confidence and Overrides

**MUST:** Auto-detected values with Low confidence MUST be flagged for manual review in the generation output.

**MUST:** The generator MUST track provenance via a `_meta` section in the YAML file (not via YAML comments, which are unreliable when LLMs edit the file):

```yaml
_meta:
  auto_detected:
    - "stack.languages"
    - "stack.frameworks"
    - "paths.source"
    - "commands.test"
  manual:
    - "security.handles_pii"
    - "gates.trust_tier"
  requires_confirmation:
    - "security.handles_auth"     # Low confidence — flagged for review
  last_profiled: "2026-03-14"
```

**MUST NOT:** The auto-detection tool MUST NOT overwrite fields listed in `_meta.manual` on re-runs.

**SHOULD:** On re-detection (e.g., after adding a new framework), the tool SHOULD show a diff of proposed changes for approval rather than silently updating.

---

## 6. Validation Rules

The following invariants MUST be enforced by `forge validate` when processing `forge.project.yaml`:

### 6.1 Structural Validation

| Rule | Error Level |
|---|---|
| `schema_version` is present and matches a known version | Error |
| `project.name` is lowercase, alphanumeric with hyphens only | Error |
| `stack.languages` contains at least one entry | Error |
| `stack.frameworks` contains at least one entry (unless `service_type` is `infrastructure`, `cli`, or `library`) | Error |
| `stack.service_type` is one of the allowed enum values | Error |
| `commands.test` is present and non-null | Error |
| All `paths.*` values that are non-null point to existing files/directories | Warning |
| `tools.*.config` paths point to existing files | Warning |

### 6.2 Cross-Reference Validation

| Rule | Error Level |
|---|---|
| `project.service_map_ref` matches a key in `service_map.yaml` (if provided) | Error |
| `deploy.target` matches a deploy target in `service_map.yaml` | Warning |
| `api.consumers` entries exist as project names in `service_map.yaml` | Warning |
| `api.producers_consumed` entries are documented (internal or known external) | Info |
| `gates.critical_modules` paths exist in the repo | Warning |
| `security` flags are consistent with `service_type` (e.g., `frontend` with `handles_pii: true` should warn) | Warning |

### 6.3 Tool Consistency Validation

| Rule | Error Level |
|---|---|
| Python repo (`python` in `stack.languages`) has `ruff.enabled: true` | Warning |
| Python repo has `mypy.enabled: true` | Warning |
| TypeScript repo (`typescript` in `stack.languages`) has `eslint.enabled: true` | Warning |
| TypeScript repo has `tsc.enabled: true` | Warning |
| API producer (`api.role` is `producer` or `both`) has `semgrep.enabled: true` | Warning |
| API producer has `oasdiff` in `gates.pr_gate.extra_tools` or globally enabled | Warning |
| Any repo has `detect_secrets.enabled: true` (secrets scanning is mandatory per OPS-STD-002 APP-SECRETS-01, regardless of internet exposure) | Error |
| Repo with `security.handles_auth: true` has `semgrep` enabled with OWASP ruleset | Warning |
| `tools.npm_audit.enabled` is `false` when `stack.languages` contains no JS/TS | Info |
| `tools.pip_audit.enabled` is `false` when `stack.languages` contains no Python | Info |

### 6.4 Unknown Keys

**MUST:** Validation MUST fail on unknown top-level keys or unknown keys within defined sections. This catches typos and prevents silent misconfiguration.

---

## 7. Minimal Valid File

The smallest valid `forge.project.yaml`:

```yaml
schema_version: "1.0"

project:
  name: "my-service"
  display_name: "My Service"

stack:
  languages:
    - python
  frameworks:
    - fastapi
  service_type: api

commands:
  test: "pytest -x -q"
```

All other fields fall back to auto-detection or defaults. This is the recommended starting point — run the auto-detection tool to populate the rest, then review and override.

---

## 8. Example Profiles

### 8.1 ERS (FastAPI API)

```yaml
schema_version: "1.0"

project:
  name: "ers"
  display_name: "Exit Readiness Snapshot"
  description: "AI-powered business assessment and exit readiness scoring"
  owner: "liam"
  service_map_ref: "ers"

stack:
  languages:
    - python
  language_versions:
    python: "3.12"
  frameworks:
    - fastapi
    - langgraph
  service_type: api
  runtime: docker
  package_managers:
    - pip

paths:
  source: "src/"
  tests: "tests/"
  forge_sdlc: "05_SDLC/"
  openapi_spec: "openapi.json"
  alembic: "alembic/"
  docker_compose: "docker-compose.yml"

commands:
  install: "pip install -e '.[dev]'"
  test: "pytest -x -q"
  test_coverage: "pytest --cov=src --cov-report=term-missing"
  lint: "ruff check ."
  format: "ruff format ."
  typecheck: "mypy src/"
  serve: "uvicorn src.main:app --reload"
  migrate: "alembic upgrade head"

tools:
  ruff: { enabled: true, config: "pyproject.toml" }
  mypy: { enabled: true, config: "pyproject.toml" }
  eslint: { enabled: false }
  tsc: { enabled: false }
  semgrep:
    enabled: true
    rulesets: ["p/python", "p/owasp-top-ten", "p/fastapi"]
  detect_secrets: { enabled: true, baseline: ".secrets.baseline" }
  pip_audit: { enabled: true }
  npm_audit: { enabled: false }
  pytest: { enabled: true, coverage_threshold: 80 }
  jest: { enabled: false }

gates:
  trust_tier: 2
  critical_modules: ["src/auth/"]

security:
  handles_pii: true
  handles_payments: false
  handles_auth: true
  exposed_to_internet: true
  has_file_uploads: false
  has_webhooks: false

api:
  role: producer
  versioning_strategy: path
  current_version: v1
  contract_testing: { oasdiff: true, schemathesis: true, pact: false }
  consumers: ["command-centre"]
  producers_consumed: ["stripe", "cal-com"]

database:
  engine: postgresql
  schema_namespace: ers
  migration_tool: alembic

deploy:
  target: ops_vps
  method: docker-compose
  health_check: "/health"
  rollback_strategy: docker

forge:
  sdlc_enabled: true
  naming_convention: "S##.P##.T##"
  branch_pattern: "s##-p##-description"
  evidence_required: true
```

### 8.2 Command Centre (Fullstack — Next.js + FastAPI)

```yaml
schema_version: "1.0"

project:
  name: "command-centre"
  display_name: "Command Centre"
  description: "Centralized operational dashboard with real-time metrics"
  owner: "liam"
  service_map_ref: "command-centre"

stack:
  languages:
    - python
    - typescript
  language_versions:
    python: "3.12"
    node: "20"
  frameworks:
    - fastapi
    - nextjs
  service_type: fullstack
  runtime: docker
  package_managers:
    - pip
    - npm

paths:
  source: "backend/"
  tests: "tests/"
  forge_sdlc: "05_SDLC/"
  openapi_spec: "backend/openapi.json"
  docker_compose: "docker-compose.yml"

commands:
  install: "pip install -e '.[dev]' && npm install"
  test: "pytest -x -q && npm test"
  lint: "ruff check backend/ && eslint frontend/"
  typecheck: "mypy backend/ && tsc --noEmit"

tools:
  ruff: { enabled: true }
  mypy: { enabled: true }
  eslint: { enabled: true }
  tsc: { enabled: true }
  semgrep:
    enabled: true
    rulesets: ["p/python", "p/typescript", "p/owasp-top-ten", "p/nextjs"]
  detect_secrets: { enabled: true }
  pip_audit: { enabled: true }
  npm_audit: { enabled: true }
  pytest: { enabled: true, coverage_threshold: 70 }
  jest: { enabled: true, coverage_threshold: 70 }

gates:
  trust_tier: 2
  critical_modules: ["backend/auth/", "backend/api/"]

security:
  handles_pii: false
  handles_payments: false
  handles_auth: true
  exposed_to_internet: true
  has_file_uploads: false
  has_webhooks: true

api:
  role: both
  versioning_strategy: path
  current_version: v1
  contract_testing: { oasdiff: true, schemathesis: true, pact: false }
  consumers: []
  producers_consumed: ["ers", "evgp-system", "evgp-2-processing"]

database:
  engine: postgresql
  schema_namespace: command_centre
  migration_tool: alembic

deploy:
  target: ops_vps
  method: docker-compose
  health_check: "/health"
  rollback_strategy: docker
```

### 8.3 Infrastructure (Deploy Configs Only)

```yaml
schema_version: "1.0"

project:
  name: "infrastructure"
  display_name: "Infrastructure"
  description: "Deployment configs, docker-compose files, nginx, monitoring"
  owner: "liam"

stack:
  languages:
    - yaml
  frameworks:
    - docker
  service_type: infrastructure
  runtime: bare

commands:
  test: "docker compose config --quiet"

tools:
  semgrep: { enabled: false }
  detect_secrets: { enabled: true }
  trivy: { enabled: true }
  ruff: { enabled: false }
  eslint: { enabled: false }

gates:
  trust_tier: 3

security:
  handles_pii: false
  handles_payments: false
  handles_auth: false
  exposed_to_internet: true
  has_file_uploads: false
  has_webhooks: false

deploy:
  target: ops_vps
  method: docker-compose
  rollback_strategy: manual
```

---

## 9. Defaults Table

When a field is omitted, these defaults apply:

| Field | Default Value |
|---|---|
| `project.description` | `null` (empty) |
| `project.owner` | `null` |
| `project.repo_url` | `null` |
| `project.service_map_ref` | Same as `project.name` |
| `stack.language_versions` | Auto-detected or `null` |
| `stack.runtime` | `"docker"` |
| `stack.package_managers` | Auto-detected from lock files |
| `paths.source` | `"src/"` |
| `paths.tests` | `"tests/"` |
| `paths.docs` | `"docs/"` |
| `paths.forge_sdlc` | `"05_SDLC/"` |
| `paths.openapi_spec` | Auto-detected or `null` |
| `paths.asyncapi_spec` | `null` |
| `paths.alembic` | Auto-detected or `null` |
| `paths.docker_compose` | Auto-detected or `null` |
| `commands.install` | `null` (manual) |
| `commands.build` | `null` (no build step) |
| `commands.test_coverage` | `null` |
| `commands.lint` | Auto-detected or `null` |
| `commands.format` | Auto-detected or `null` |
| `commands.typecheck` | Auto-detected or `null` |
| `commands.serve` | `null` |
| `commands.migrate` | `null` |
| `tools.*.enabled` | `true` for tools matching the repo's language; `false` otherwise |
| `tools.semgrep.rulesets` | `["p/python"]` for Python, `["p/typescript"]` for TS, both for fullstack |
| `tools.*.coverage_threshold` | `80` |
| `gates.trust_tier` | `2` |
| `gates.critical_modules` | `[]` |
| `gates.*.extra_tools` | `[]` |
| `gates.*.disabled_tools` | `[]` |
| `gates.*.extra_agents` | `[]` |
| `gates.*.disabled_agents` | `[]` |
| `gates.release_gate.require_sbom` | `true` |
| All `security.*` flags | `false` |
| `api.role` | `"none"` |
| `api.versioning_strategy` | `"path"` |
| `api.current_version` | `"v1"` |
| `api.contract_testing.*` | `false` |
| `api.consumers` | `[]` |
| `api.producers_consumed` | `[]` |
| `database.engine` | `"none"` |
| `database.schema_namespace` | Same as `project.name` (underscores replacing hyphens) |
| `database.migration_tool` | `"none"` |
| `database.has_views_as_contracts` | `false` |
| `deploy.method` | `"docker-compose"` |
| `deploy.health_check` | `"/health"` |
| `deploy.rollback_strategy` | `"docker"` |
| `forge.sdlc_enabled` | `true` |
| `forge.naming_convention` | `"S##.P##.T##"` |
| `forge.branch_pattern` | `"s##-p##-description"` |
| `forge.evidence_required` | `true` |
| `forge.review_models.*` | `null` (use global defaults from `review_models.yaml`) |

---

## 10. Integration Points

### 10.1 Consuming Operations

| Operation | Fields Consumed | Purpose |
|---|---|---|
| Codebase Audit (S02.P07) | `stack.*`, `tools.*`, `commands.*`, `paths.*`, `security.*` | Determines which tools to run, which source dirs to scan, which security checks apply |
| Forge Gate (OPS-STD-004) | `gates.*`, `tools.*`, `security.*`, `api.*` | Configures gate thresholds, tool selection, agent selection, trust tier |
| API Contract Sync (S02.P10) | `api.*`, `paths.openapi_spec`, `database.*` | Identifies producers/consumers, locates specs, maps schema ownership |
| Reverse Documentation (S02.P08) | `stack.*`, `paths.*`, `database.*` | Determines scan approach (backend vs frontend vs fullstack), locates source |
| Forge Structure (S02.P09) | `forge.*`, `paths.forge_sdlc` | Sets naming convention, branch pattern, evidence requirements |
| Security Subagent (S01.P03) | `security.*`, `tools.semgrep.*`, `stack.*` | Determines which security control families to check, which OWASP rules to apply |
| Remediation Pipeline (S01.P06) | `gates.trust_tier`, `deploy.*`, `commands.*` | Routes to correct remediation tier, knows how to deploy fixes |

### 10.2 Service Map Relationship

`forge.project.yaml` is the **per-repo** profile. `service_map.yaml` is the **cross-repo** dependency graph. They connect via `project.service_map_ref`:

```
forge.project.yaml (per repo)          service_map.yaml (global)
┌───────────────────────┐              ┌──────────────────────────┐
│ project:              │              │ services:                │
│   name: ers           │──────ref────▶│   ers:                   │
│   service_map_ref: ers│              │     deploy_target: ops   │
│                       │              │     depends_on: [...]     │
│ api:                  │              │     api_consumers: [cc]   │
│   consumers: [cc]     │──validates──▶│   command-centre:        │
│                       │              │     depends_on: [ers]     │
└───────────────────────┘              └──────────────────────────┘
```

The config sync validator (S01.P04.T03) cross-checks these references.

---

## 11. Implementation Roadmap

| Phase | Action | Depends On |
|---|---|---|
| S01.P04.T01 | Build auto-detection script using rules in Section 5 | This standard |
| S01.P04.T02 | Generate `forge.project.yaml` for all repos on EX44 | Auto-detection script |
| S01.P04.T03 | Manual review of Low-confidence auto-detected values | Generated files |
| S01.P04.T03 | Config sync validator cross-checks against `service_map.yaml` | Generated files + service map |
| S02.P07 | Codebase audit reads `forge.project.yaml` to configure tool/agent selection | All profiles validated |

---

## Appendix A: JSON Schema

The canonical JSON Schema for `forge.project.yaml` validation will be maintained at `forge/core/schemas/forge_project.json` in the Forge repo. It MUST be kept in sync with this standard. `forge validate` uses this schema as its primary validation source.

Key schema constraints beyond what YAML structure provides:
- `project.name`: pattern `^[a-z][a-z0-9-]*$`, maxLength 64
- `stack.service_type`: enum constraint
- `gates.trust_tier`: integer, minimum 1, maximum 3
- `tools.*.coverage_threshold`: integer, minimum 0, maximum 100
- `api.role`: enum constraint
- `database.engine`: enum constraint

## Appendix B: Design Decisions

This standard has no dedicated research prompt — it was derived from the master plan (00_MASTER_PLAN.md) and cross-references from the four preceding standards:

| Decision | Rationale |
|---|---|
| YAML over JSON/TOML | Consistency with `service_map.yaml`, `review_models.yaml`, and other Forge configs. |
| `_meta` section for provenance tracking (not YAML comments) | In an LLM-driven development environment, YAML comments are unreliable — LLMs routinely strip, reorder, or mangle them during edits. A structured `_meta` section survives automated edits and is machine-parseable by the auto-detection tool. |
| Flat `tools.*` map rather than per-gate tool lists | Reduces duplication. Gate-specific overrides use `extra_tools` / `disabled_tools` delta syntax against the global tool baseline. |
| `security.*` boolean flags rather than listing control IDs | Operations should not need to know individual control IDs. Boolean flags provide a semantic interface; the security subagent maps flags to OPS-STD-002 control families internally. |
| `gates.trust_tier` at project level, not per-gate | Trust tier is a property of the repo's risk profile, not of individual gates. All gates reference the same tier for escalation decisions. |
| `api.role` as enum, not a list of endpoints | Keeps the profile declarative. Individual endpoint details belong in the OpenAPI spec, not in the project profile. |
| `forge.review_models` as optional overrides | Most repos use the global `review_models.yaml`. Per-repo overrides exist for cases where a repo needs a frontier model for a normally mid-tier agent (e.g., complex auth logic). |
| Strict unknown-key rejection | Per EX44 P03 gotcha: "unknown keys should fail validation, not be silently ignored. This catches typos." |

## Appendix C: Cross-References

| Standard | Relationship |
|---|---|
| OPS-STD-001 (AUTH_SSO_STANDARD) | `security.handles_auth: true` triggers OPS-STD-001 compliance checks |
| OPS-STD-002 (SECURITY_CONTROLS) | `security.*` flags map to control families; `tools.semgrep.rulesets` reference OWASP rules from OPS-STD-002 |
| OPS-STD-003 (API_CONTRACT_STANDARD) | `api.*` section configures contract testing per OPS-STD-003; `database.*` maps to schema namespace rules |
| OPS-STD-004 (FORGE_GATE_POLICY) | `gates.*` section provides per-repo overrides to global gate policy; `tools.*` determines which tools run at each gate |
| `service_map.yaml` | `project.service_map_ref` links to service map entry; `api.consumers` / `api.producers_consumed` validated against service map |
| `review_models.yaml` | `forge.review_models.*` overrides global model assignments |
