---
name: forge-tier1-audit
description: Invoke with "forge Tier 1 codebase audit" from any directory. Dispatches parallel read-only subagents for exhaustive security, correctness, compliance, and deployment-readiness analysis. Produces structured findings report with alphanumeric IDs.
---

# Forge Tier 1 Codebase Audit

**Trigger:** User says "forge Tier 1 codebase audit", "Tier 1 audit", or "full codebase audit"
**Mode:** Read-only swarm. NO code changes. NO commits. Analysis only.
**Output:** Single structured markdown report at `{cwd}/.forge/audit-reports/T1-AUDIT-{YYYYMMDD-HHmmss}.md`

---

## Phase 0 — Discovery (Sequential, ~30 seconds)

Before dispatching agents, the orchestrator MUST profile the target codebase. This makes the audit universal across any project.

### 0.1 Codebase Profiling

Run these commands and capture output:

```bash
# Stack detection
ls -la package.json pyproject.toml Cargo.toml go.mod pom.xml Gemfile composer.json 2>/dev/null
ls -la tsconfig.json next.config.* vite.config.* tailwind.config.* 2>/dev/null
ls -la Dockerfile docker-compose.yml docker-compose.yaml 2>/dev/null
ls -la .env .env.* 2>/dev/null  # existence only, never read contents

# Structure
find . -maxdepth 3 -type d -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*' -not -path './__pycache__/*' | head -80

# Forge state (if present)
ls -la .forge/ 2>/dev/null
ls -la phases/ specs/ 2>/dev/null
ls -la .forge/defect-register.yaml 2>/dev/null
ls -la .forge/gate-proofs/ 2>/dev/null
cat .forge/tracker.yaml 2>/dev/null | head -40

# forge.project.yaml (if present)
cat forge.project.yaml 2>/dev/null | head -60

# Git state
git log --oneline -20 2>/dev/null
git branch -a 2>/dev/null
```

### 0.2 Classify Codebase

From the profiling output, determine:

| Property | Values | Purpose |
|----------|--------|---------|
| `stack` | `python`, `typescript`, `fullstack`, `go`, `rust`, `other` | Selects which standards apply |
| `framework` | `fastapi`, `django`, `nextjs`, `react`, `express`, `none` | Framework-specific checks |
| `has_forge` | `true`/`false` | Whether Forge SDLC is active |
| `has_docker` | `true`/`false` | Docker/infra standards apply |
| `has_phases` | `true`/`false` | Phase compliance checks apply |
| `has_tests` | `true`/`false` | Test coverage analysis relevant |
| `entry_points` | list of src dirs | Scope for agents |

### 0.3 Load Standards

Read ALL applicable standards from `/home/deploy/forge-sdlc/standards/`:

**Always applicable:**
- `security.md`
- `error-handling.md`
- `logging.md`
- `configuration.md`
- `dependency-management.md`

**Python projects:** add `type-safety.md`, `api-design.md`, `database.md`, `testing.md`
**TypeScript projects:** add `typescript-safety.md`, `frontend-design-system.md`, `component-testing.md`, `error-boundaries.md`, `api-client-contracts.md`
**Fullstack:** all of the above

**Always load ops standards:**
- `standards/ops/SECURITY_CONTROLS.md` (OPS-STD-002)
- `standards/ops/API_CONTRACT_STANDARD.md` (OPS-STD-003)
- `standards/ops/FORGE_GATE_POLICY.md` (OPS-STD-004) — if `has_forge`
- `standards/ops/AUTH_SSO_STANDARD.md` (OPS-STD-001) — if auth code present

---

## Phase 1 — Parallel Agent Swarm (8 Streams)

**CRITICAL:** Launch ALL applicable agents in a SINGLE message using the Agent tool. Each agent runs in parallel. Every agent is **read-only** — no edits, no writes, no commits.

Each agent prompt MUST include:
1. The codebase profile from Phase 0
2. The relevant standards content (paste the actual requirements)
3. The specific entry_points/src directories to scan
4. Instruction to return structured JSON findings

### Stream 1: Security Deep Scan
**Agent type:** `general-purpose`
**Purpose:** OWASP Top 10 2025, injection, auth/access control, secrets, SSRF, cryptographic failures, security headers, supply chain

**Prompt template:**
```
You are a security auditor performing a READ-ONLY audit. Do NOT edit any files. Only read and analyze.

Perform an exhaustive security review of the codebase at {cwd}.

Stack: {stack} | Framework: {framework}

YOUR SCOPE — check ALL of these against OPS-STD-002 (SECURITY_CONTROLS.md):

ACCESS CONTROL (APP-AC-01 through APP-AC-05):
- Every route must be classified public/authenticated
- Object-level authorization (BOLA/BFLA)
- Function-level authorization (role checks)
- No ORM object dumps without explicit schemas
- Server-side auth enforcement (not client-only)

INPUT VALIDATION (APP-IV-01 through APP-IV-06):
- Pydantic/schema validation on all inputs
- File upload controls (type, size, auth, storage)
- Path traversal prevention
- SQL injection (no string interpolation in queries)
- Dynamic sort/filter allowlists
- SSRF prevention (domain allowlist, block private IPs)

XSS (APP-XSS-01 through APP-XSS-03):
- innerHTML usage requires sanitization via DOMPurify.sanitize() or equivalent
- href/src URL validation
- Jinja2 autoescape enabled

SECURITY HEADERS (APP-HEADERS-01/02):
- CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- CORS configuration (no wildcard in prod)

CRYPTOGRAPHY (APP-CRYPTO-01 through APP-CRYPTO-04):
- No weak algorithms (MD5, SHA1 for security)
- TLS enforcement
- Secure random generation

SECRETS (APP-SECRETS-01/02):
- No hardcoded secrets, tokens, passwords, API keys
- Secrets via env vars only

LOGGING (LOG-01 through LOG-05):
- Auth events logged
- No sensitive data in logs
- Structured logging format

DOCKER/INFRA (INF-DOCKER-01 through INF-DOCKER-05, INF-REDIS, INF-SSH):
- Non-root containers
- No latest tags
- Redis auth + bind
- SSH hardened

Also check: webhook signature verification, rate limiting, error response information leakage.

IMPORTANT: Read every source file. Do NOT just sample. Check every route, every handler, every model.

Return findings as JSON array:
[{"id": "SEC-NNN", "severity": "critical|high|medium|low|info", "category": "OWASP category or control ID", "file": "path", "line": N, "title": "Short title", "description": "Detailed finding", "standard_ref": "APP-AC-01 etc", "recommendation": "How to fix"}]
```

### Stream 2: Silent Failure & Error Handling Hunt
**Agent type:** `pr-review-toolkit:silent-failure-hunter`
**Purpose:** Swallowed exceptions, missing error handling, unchecked returns, fire-and-forget, silent fallbacks

**Prompt template:**
```
Perform an exhaustive silent failure hunt across the entire codebase at {cwd}. This is a READ-ONLY audit — do NOT edit any files.

Check EVERY file for:
1. Bare except/catch blocks that swallow errors
2. except blocks that only pass/continue without logging
3. API/HTTP calls without response status checks
4. Async calls without await or error callbacks
5. Optional/nullable values used without guards
6. Default values that mask real failures (e.g., `or {}`, `or []`, `or ""`)
7. Functions that return None on error instead of raising
8. Missing finally blocks for resource cleanup
9. Unclosed file handles, DB connections, HTTP sessions
10. Fire-and-forget background tasks without error handling
11. Missing try/catch around external service calls
12. Empty error handlers in React components
13. Promises without .catch()
14. Missing error boundaries in React component trees

Apply standards from error-handling.md: {paste error-handling.md content}

Return ALL findings. Do not skip files. Do not summarize — list every instance.
```

### Stream 3: Type Safety & Correctness Analysis
**Agent type:** `pr-review-toolkit:type-design-analyzer`
**Purpose:** Missing types, Any abuse, incorrect return types, runtime type mismatches, None safety

**Prompt template:**
```
Perform exhaustive type safety analysis of {cwd}. READ-ONLY — do NOT edit any files.

For Python: check against type-safety.md standards
For TypeScript: check against typescript-safety.md standards

Check for:
1. Functions missing return type annotations
2. Parameters missing type annotations
3. Use of Any/any where specific types are possible
4. Incorrect return types (function says X, returns Y)
5. Missing None/null/undefined checks before access
6. Unsafe type casts/assertions
7. Generic types that should be constrained
8. Inconsistent typing of the same concept across files
9. Missing discriminated unions for state management
10. Pydantic models missing field validators
11. TypeScript types that should be interfaces (or vice versa)
12. Missing strict mode in tsconfig/mypy

Read every source file. Return all findings.
```

### Stream 4: Spec & Design Compliance
**Agent type:** `dev-workflows:code-verifier`
**Condition:** Only if `has_forge == true` AND phase specs exist
**Purpose:** Verify implementation matches phase specs, acceptance criteria, and design docs

**Prompt template:**
```
You are a spec compliance auditor for a Forge SDLC project at {cwd}. READ-ONLY — do NOT edit any files.

1. Read ALL phase specs in phases/ or specs/ directory
2. Read ALL evidence files in evidence/ directory
3. Read ALL gate-proofs in .forge/gate-proofs/
4. Read the tracker state in .forge/tracker.yaml

For each task marked as "complete" or "done":
a) Verify EVERY acceptance criterion is actually implemented in the code
b) Verify gate-proof exists and shows overall: pass
c) Verify evidence file exists with completed AC checklist
d) Check for scope creep — code changes beyond spec
e) Check for missing requirements — spec items not addressed

For each phase:
a) Verify T_REVIEW task was completed (not skipped)
b) Verify phase gate-proof exists with gate_type: pr
c) Cross-check defect register — are all logged defects resolved?

Also verify:
- Task dependency DAG was respected (no out-of-order completion)
- Review gate lines present in all task specs
- Escape hatches documented and justified (if any)

Return findings as JSON with category: missing_requirement|incomplete_implementation|missing_evidence|missing_gate_proof|scope_creep|skipped_review|unresolved_defect
```

### Stream 5: Infrastructure Standards Compliance
**Agent type:** `general-purpose`
**Purpose:** Check against ALL forge standards (not just security)

**Prompt template:**
```
You are a standards compliance auditor. READ-ONLY — do NOT edit any files.
Check the codebase at {cwd} against every applicable Forge standard.

{Paste ALL applicable standards content from Phase 0.3}

For EACH standard requirement that contains MUST/SHOULD/MUST NOT:
1. Search the codebase for code that is subject to this requirement
2. Verify compliance or note the violation
3. Record file, line, and the specific standard clause

Categories to check:
- API design patterns (api-design.md)
- Error handling patterns (error-handling.md)
- Logging standards (logging.md)
- Configuration management (configuration.md)
- Dependency management (dependency-management.md)
- Database patterns (database.md)
- Testing standards (testing.md)
- Documentation standards (documentation.md)

For each standard document, go requirement by requirement. Do not skip any MUST or SHOULD clause.

Return findings grouped by standard document.
```

### Stream 6: Test Coverage & Quality Gaps
**Agent type:** `pr-review-toolkit:pr-test-analyzer`
**Purpose:** Missing tests, inadequate assertions, untested edge cases, test quality

**Prompt template:**
```
Perform exhaustive test coverage and quality analysis of {cwd}. READ-ONLY — do NOT edit any files.

1. Map all source modules/components to their test files
2. Identify modules/components with NO tests at all
3. For tested code, check:
   a) Are failure/error paths tested?
   b) Are edge cases covered (empty input, null, boundary values)?
   c) Are assertions meaningful (not just "doesn't throw")?
   d) Are integration points tested (API calls, DB queries)?
   e) Are security-critical paths tested (auth, access control)?
4. Check test infrastructure:
   a) Is there a test runner configured?
   b) Are there CI/test scripts?
   c) Is coverage reporting set up?
   d) Are there flaky test patterns (timeouts, sleep, order-dependent)?

Apply standards from testing.md: {paste testing.md content}

Return: untested modules list, weak test list, missing edge case list, test quality issues
```

### Stream 7: Code Quality & Architecture Review
**Agent type:** `coderabbit:code-reviewer`
**Purpose:** Bugs, logic errors, dead code, complexity, architecture issues, code smells

**Prompt template:**
```
Perform a thorough code quality and architecture review of {cwd}. READ-ONLY — do NOT edit any files.

Check for:
1. Logic errors (off-by-one, wrong comparisons, inverted conditions)
2. Dead code (unreachable branches, unused imports/functions/variables)
3. Race conditions (shared state without locks, TOCTOU)
4. Resource leaks (unclosed handles, missing cleanup)
5. Performance anti-patterns (N+1 queries, unbounded loops, sync in async)
6. Excessive complexity (deeply nested code, god classes, long methods)
7. Copy-paste code that should be abstracted
8. Inconsistent patterns across similar modules
9. Missing or incorrect error propagation
10. Hardcoded values that should be configurable
11. Circular dependencies
12. API response shape inconsistencies

Focus on bugs and correctness issues over style preferences.
Return all findings with file and line references.
```

### Stream 8: Deployment Readiness Check
**Agent type:** `general-purpose`
**Purpose:** Environment config, Docker, CI/CD, migrations, dependency vulnerabilities

**Prompt template:**
```
You are a deployment readiness auditor. READ-ONLY — do NOT edit any files.
Check if {cwd} is 100% ready for production deployment.

CHECK LIST:

ENVIRONMENT & CONFIG:
- All secrets via env vars (no hardcoded values)
- .env.example or equivalent documents all required vars
- No debug/development flags that could leak to prod
- Database URLs use env vars
- CORS configured for production domains only
- Rate limiting configured

DOCKER (if present):
- Non-root user in Dockerfile
- No .env files copied into image
- Multi-stage build (no build tools in prod image)
- Health check defined
- No latest tags for base images
- .dockerignore exists and is comprehensive
- docker-compose has restart policies
- Volumes configured for persistent data

DEPENDENCIES:
- Lock file present and committed (poetry.lock / package-lock.json / etc)
- No known critical CVEs (check package versions against known vulns)
- No unnecessary dev dependencies in production

DATABASE:
- Migrations are up to date
- No pending schema changes
- Connection pooling configured
- Backup strategy documented

CI/CD:
- Test pipeline exists and would pass
- Build scripts work
- Deploy scripts/configs present

MONITORING:
- Error tracking configured (Sentry or equivalent)
- Structured logging to stdout
- Health check endpoint exists

Return findings with clear pass/fail for each checklist item.
```

---

## Phase 2 — Report Synthesis (Sequential)

After ALL agents complete, the orchestrator synthesizes findings into a single report.

### 2.1 Finding ID Schema

Every finding gets a unique alphanumeric ID:

| Prefix | Stream | Example |
|--------|--------|---------|
| `SEC-` | Security Deep Scan | SEC-001, SEC-002 |
| `SFH-` | Silent Failure Hunt | SFH-001, SFH-002 |
| `TYP-` | Type Safety | TYP-001, TYP-002 |
| `SPC-` | Spec Compliance | SPC-001, SPC-002 |
| `STD-` | Standards Compliance | STD-001, STD-002 |
| `TST-` | Test Coverage | TST-001, TST-002 |
| `CQA-` | Code Quality/Architecture | CQA-001, CQA-002 |
| `DPL-` | Deployment Readiness | DPL-001, DPL-002 |

Numbers are sequential within each prefix, starting at 001.

### 2.2 Severity Classification

| Severity | Definition | Gate Impact |
|----------|-----------|-------------|
| **CRITICAL** | Exploitable vulnerability, data loss risk, auth bypass, production crash | MUST fix before deploy |
| **HIGH** | Security weakness, missing error handling on critical path, spec violation | MUST fix before deploy |
| **MEDIUM** | Standards non-compliance, missing tests for important paths, code quality issue | SHOULD fix, track if deferred |
| **LOW** | Minor standards deviation, style issue, optimization opportunity | Track, fix when convenient |
| **INFO** | Observation, best practice suggestion, technical debt note | Document only |

### 2.3 Deduplication

Before writing the report:
1. Group findings by `(file, line_range)` — if two agents flag the same location, merge into ONE finding
2. When merging, keep the HIGHER severity
3. Note which streams identified the finding (shows multi-agent agreement = higher confidence)
4. Remove pure duplicates (same file, same issue, different wording)

### 2.4 Report Structure

Write the report to `.forge/audit-reports/T1-AUDIT-{YYYYMMDD-HHmmss}.md`:

```markdown
# Forge Tier 1 Codebase Audit Report

**Project:** {project name from cwd}
**Audit Date:** {ISO 8601 timestamp}
**Auditor:** Forge Tier 1 Automated Audit Swarm
**Codebase Path:** {cwd}
**Stack:** {stack} | **Framework:** {framework}
**Forge SDLC Active:** {yes/no}

---

## Executive Summary

- **Total Findings:** N
- **Critical:** N | **High:** N | **Medium:** N | **Low:** N | **Info:** N
- **Deployment Ready:** YES / NO (with blocking reason)
- **Streams Executed:** N/8
- **Standards Checked:** {list of standard IDs}

### Deployment Blockers

{List any CRITICAL or HIGH findings that prevent deployment. If none, state "No deployment blockers identified."}

---

## Findings by Severity

### CRITICAL

| ID | Category | File | Line | Title | Standard Ref | Detected By |
|----|----------|------|------|-------|-------------|-------------|
| SEC-001 | Access Control | src/api/routes.py | 42 | Missing auth on admin endpoint | APP-AC-01 | Security, CodeRabbit |

#### SEC-001 — Missing auth on admin endpoint
**Severity:** CRITICAL | **File:** `src/api/routes.py:42` | **Standard:** APP-AC-01
**Detected by:** Stream 1 (Security), Stream 7 (Code Quality)

**Description:** {Detailed description of the finding}

**Evidence:** {Code snippet or reference}

**Recommendation:** {Specific remediation steps}

---

### HIGH
{Same format as CRITICAL}

### MEDIUM
{Same format}

### LOW
{Same format}

### INFO
{Same format}

---

## Findings by Stream

### Stream 1: Security Deep Scan
- Findings: N (C: N, H: N, M: N, L: N, I: N)
- {Brief summary of security posture}

### Stream 2: Silent Failure Hunt
- Findings: N
- {Brief summary}

{... repeat for all 8 streams}

---

## Standards Compliance Matrix

| Standard | Document | Clauses Checked | Compliant | Non-Compliant | N/A |
|----------|----------|----------------|-----------|---------------|-----|
| OPS-STD-002 | SECURITY_CONTROLS.md | 48 | 35 | 8 | 5 |
| - | error-handling.md | 12 | 10 | 2 | 0 |
| - | testing.md | 8 | 3 | 5 | 0 |
{... all applicable standards}

---

## Spec Compliance Summary (if Forge active)

| Phase | Tasks Complete | Evidence Present | Gate-Proofs Valid | Defects Resolved | Status |
|-------|---------------|-----------------|-------------------|-----------------|--------|
| S01.P01 | 5/5 | 5/5 | 5/5 | 12/12 | PASS |
| S01.P02 | 3/4 | 2/4 | 2/4 | 5/8 | FAIL |

---

## Deployment Readiness Checklist

| Category | Status | Blocking Issues |
|----------|--------|----------------|
| Environment Config | PASS/FAIL | {list} |
| Docker | PASS/FAIL/N/A | {list} |
| Dependencies | PASS/FAIL | {list} |
| Database | PASS/FAIL | {list} |
| CI/CD | PASS/FAIL | {list} |
| Monitoring | PASS/FAIL | {list} |

---

## Remediation Priority

Ordered list of findings to fix, grouped by priority:

### Immediate (CRITICAL — fix before any deployment)
1. SEC-001 — Missing auth on admin endpoint
2. ...

### Urgent (HIGH — fix before next release)
1. SFH-003 — Swallowed database exception in payment handler
2. ...

### Planned (MEDIUM — schedule within sprint)
1. STD-005 — Missing structured logging in webhook handler
2. ...

### Backlog (LOW/INFO — track for continuous improvement)
1. CQA-012 — Consider extracting shared validation logic
2. ...

---

## Appendix A: Files Analyzed

{List of all source files scanned, grouped by directory}

## Appendix B: Standards Referenced

{List of all standards documents consulted with version/date}

## Appendix C: Agent Execution Metadata

| Stream | Agent Type | Duration | Findings | Status |
|--------|-----------|----------|----------|--------|
| 1 | general-purpose | Ns | N | complete |
| 2 | silent-failure-hunter | Ns | N | complete |
{... all streams}
```

---

## Phase 3 — Output Summary

After writing the report file, print to the user:

```
Forge Tier 1 Codebase Audit Complete
=====================================
Report: .forge/audit-reports/T1-AUDIT-{timestamp}.md

Summary:
  CRITICAL: N  |  HIGH: N  |  MEDIUM: N  |  LOW: N  |  INFO: N
  Deployment Ready: YES/NO

Top 5 Priority Findings:
  1. {ID} — {title} ({severity})
  2. ...

{If deployment blockers exist, list them prominently}
```

---

## Conditional Stream Logic

Not all streams apply to all codebases. The orchestrator MUST skip inapplicable streams:

| Stream | Skip Condition |
|--------|---------------|
| Stream 4 (Spec Compliance) | Skip if `has_forge == false` OR no phase specs found |
| Stream 6 (Test Coverage) | Always run, but adapt scope if `has_tests == false` (report as finding) |
| Stream 8 (Deployment) | Always run — deployment readiness matters for every project |

If a stream is skipped, note it in the report as "N/A — {reason}".

---

## Rules

1. **READ-ONLY.** No agent may edit, write, or commit. Violation = audit invalid.
2. **EXHAUSTIVE.** Agents must read every source file, not sample. The point is thoroughness.
3. **SPECIFIC.** Every finding must reference a file and line number. Vague findings are useless.
4. **ACTIONABLE.** Every finding must include a specific remediation recommendation.
5. **STANDARDS-BACKED.** Where a Forge standard applies, cite the specific control ID.
6. **DEDUPLICATED.** Same issue found by multiple agents = one finding with multi-agent attribution.
7. **NO FALSE CONFIDENCE.** If uncertain about a finding, flag it as INFO with a note, do not omit it.
8. **UNIVERSAL.** This audit works on any codebase. Standards that don't apply get N/A, not forced compliance.
