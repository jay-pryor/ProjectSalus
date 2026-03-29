# FORGE_GATE_POLICY.md

**Standard ID:** OPS-STD-004
**Version:** 1.0
**Status:** Draft
**Created:** 2026-03-14
**Scope:** All OnPulse repositories using Forge SDLC, AI-driven development pipelines (Cline, Claude Code, OpenClaw), and automated quality gates
**Authoritative Standards:** OPS-STD-002 (Security Controls), OPS-STD-003 (API Contract Standard), OWASP Top 10 2025, OWASP API Security Top 10 2023

---

## 1. Gate Architecture

### 1.1 Gate Types

Three gate types enforce quality at different stages of the development lifecycle:

| Gate Type | When | Scope | Rigor | Purpose |
|---|---|---|---|---|
| **Phase Gate** | End of S##.P##.T## session | Changed files + impacted areas | Light | Rapid feedback; prevent broken code entering integration branch |
| **PR Gate** | PR into main | Full diff + context | Full | Comprehensive multi-agent review; block defective code from main |
| **Release Gate** | Before production deploy | Diff since last release | Deep | Final hardening; compliance evidence; immutable audit trail |

### 1.2 Progressive Rigor Model

Gates MUST enforce progressively stricter thresholds:

```
Phase Gate (light)
  -> PR Gate (full)
    -> Release Gate (deep)

Rigor increases:
  - More tools enabled
  - More agent perspectives
  - Stricter severity thresholds
  - Higher-tier models for AI review
  - Evidence requirements increase
```

**MUST:** Technical debt tolerated at Phase Gates MUST be resolved before Release Gate passes.

**MUST:** Baseline tracking separates legacy debt from new regressions. Only new issues fail gates (delta analysis).

---

## 2. Multi-Agent Review Pipeline

### 2.1 Architecture: Fan-Out/Gather Pattern

**MUST:** Use parallel specialist agents (Fan-Out) with a final Synthesizer agent (Gather). Sequential chains are prohibited for primary review due to compound hallucination risk — each sequential step compounds errors, degrading overall output quality.

```
PR Diff + CI Results
        |
        v
  Review Orchestrator
        |
   ┌────┼────┬────────┬──────────┬──────────┐
   v    v    v        v          v          v
 Security  Silent   Type     Perf &    Contract   Test
 Agent     Failure  Safety   Scale     & Schema   Coverage
           Hunter   Agent    Agent     Agent      Agent
   |    |    |        |          |          |
   └────┼────┴────────┴──────────┴──────────┘
        v
  Synthesizer Agent
  (deduplicate, resolve conflicts, assign confidence)
        |
        v
  Structured JSON + Markdown Report
```

### 2.2 Specialist Agent Roles

| Agent | Primary Focus | Recommended Tier | Deterministic Tools |
|---|---|---|---|
| **Security Reviewer** | OWASP Top 10, injection, auth/access control, secrets, SSRF, CORS, cookie flags. Adversarial mindset — construct hypothetical exploit chains. | Frontier | Semgrep (OWASP rules), detect-secrets, pip-audit, npm audit |
| **Silent Failure Hunter** | Empty catch blocks, swallowed exceptions, unhandled Promise rejections, missing logging, ignored futures/awaitables, resource leaks. Zero tolerance for hidden failures. | Mid-Tier | ruff, eslint |
| **Type Safety & Correctness** | Missing type annotations, dangerous casts, `Any` abuse, incorrect return types, missing `await`, runtime type mismatches. | Mid-Tier (or deterministic-only) | mypy, tsc (`--noEmit`) |
| **Performance & Scalability** | N+1 DB queries, synchronous work in async paths, unbounded loops, heavy computation on request path, missing DB index hints, unnecessary allocations. | Frontier | Profiling annotations if available |
| **Contract & Schema Reviewer** | FastAPI/Pydantic models vs OpenAPI spec, Next.js API routes vs client types, response shape consistency, backward compatibility. | Frontier | oasdiff, Schemathesis |
| **Test Coverage Reviewer** | Critical paths lacking tests, changed code with no new tests, missing assertions for failure states, fragile test patterns. | Mid-Tier | Coverage reports (pytest-cov, istanbul) |

**Note:** "Frontier" and "Mid-Tier" are capability tiers, not vendor prescriptions. Actual model-to-role mapping is configured in `review_models.yaml` and selected based on cost, latency, and quality trade-offs. The tier indicates the minimum reasoning capability required — not a specific product.

### 2.3 Agent Prompt Design

Each specialist agent prompt MUST:
- State a **single responsibility** and definition of "done"
- Explicitly list what **not** to report (no scope creep)
- Require **structured JSON output**: `{kind, severity, confidence, file, line, summary, rationale, suggested_fix}`
- Provide deterministic tool outputs as additional context (e.g., "Semgrep found X, verify if exploitable")

### 2.4 Finding Aggregation & Deduplication

**MUST:** Use a canonical finding key: `(tool, rule_id, file, primary_location_span)` + hash of message category.

**MUST:** Merge findings sharing the same key, unioning:
- Tools/agents that reported it
- Evidence snippets
- Suggested fixes

**MUST:** Store a stable `finding_id` across runs so suppression and accepted-risk tracking persists.

### 2.5 Confidence Scoring

**MUST:** Each finding carries a confidence score (0.0–1.0):
- Tool reliability (taint-mode Semgrep > regex-only rule)
- Model tier (frontier > mid-tier > small)
- Multi-agent agreement (2+ agents flagging same location = higher confidence)

**MUST:** Findings below the confidence threshold are excluded from blocking decisions before the Synthesizer compiles the final report. The default threshold is tau = 0.8 (i.e., findings with confidence < 0.8 are treated as informational, not gate-blocking). Confidence is calibrated from: tool reliability weight (e.g., taint-mode Semgrep scores higher than regex-only), model tier, and multi-agent agreement. Threshold is configurable per-repo via `forge.project.yaml`.

**MUST:** When agents disagree, prefer the more conservative assessment for security-critical categories. Require explicit override to downgrade severity.

### 2.6 Conflict Resolution Hierarchy

When agents produce conflicting recommendations, the Synthesizer resolves using this deterministic hierarchy:

1. **Security and correctness** override performance optimisations
2. **Performance optimisations** override style and readability suggestions
3. For equally weighted domain conflicts: escalate to human review or initiate secondary evaluation with a frontier model

---

## 3. Iterative Audit Methodology

### 3.1 Three-Round Remediation Policy

**MUST:** Automated audits re-run up to **3 times** after each remediation attempt. Three rounds balances thoroughness against diminishing returns and cost — most genuine issues surface in Rounds 1-2, with Round 3 catching edge cases introduced during fixes.

| Round | Purpose | Focus |
|---|---|---|
| **Round 1** | Initial audit | Full tool + agent scan on gate scope |
| **Round 2** | Re-check after fix | Delta analysis on changed files + impacted areas. Tag findings as `fixed`, `persistent`, or `new` |
| **Round 3** | Final pass | Resolve edge cases or issues introduced during Round 2. Last opportunity before escalation |

### 3.2 Exit Criteria

Gate passes when:
- All Critical/High findings resolved OR explicitly accepted by policy owner
- Medium findings tracked (issues created) and none in critical components (auth, payments, PII) without approval
- No `new` findings introduced in the final round

### 3.3 Escalation After Round 3

If High/Critical issues persist after 3 rounds:
- **MUST:** Hard block the change
- **MUST:** Escalate to Tier 3 (human-gated review)
- **MUST NOT:** Continue AI remediation loops beyond 3 rounds — additional rounds risk fix churn without meaningful quality improvement

For Medium issues persisting after 3 rounds:
- Create tracking issues
- Allow merge behind feature flags if business risk is acceptable and explicitly documented

### 3.4 Fix Churn Detection

**MUST:** Monitor for fix churn — agents repeatedly introducing semantic variations of the same flawed logic:

Indicators of unhealthy churn:
- Medium+ findings per round flat or increasing across iterations
- New issue classes appear in code touched only to fix previous findings
- Same finding signature (same rule ID on same line) persists across consecutive rounds

**SHOULD:** Use AST similarity analysis to detect structural non-progress beyond simple text diffs.

**MUST:** If churn is detected, immediately terminate the loop and escalate.

### 3.5 Round Tracking Metadata

Each finding MUST carry per-round metadata:

```json
{
  "finding_id": "f-abc123",
  "rule_id": "fastapi-route-missing-auth",
  "file": "src/api/endpoints.py",
  "line": 42,
  "severity": "High",
  "confidence": 0.92,
  "first_seen_round": 1,
  "last_seen_round": 2,
  "fix_round": 3,
  "status": "fixed"
}
```

This enables:
- Effectiveness metrics per round (fraction of issues found only in rounds 2 or 3)
- Analysis of whether late rounds mostly find noise
- Diminishing returns quantification to justify the 3-round cap

---

## 4. Severity Classification & Gate Mapping

### 4.1 Severity Definitions

| Severity | Definition | Examples |
|---|---|---|
| **Critical** | Direct system compromise, unauthorized data access, RCE, or severe outage without user interaction | SQL injection on PII path, secret in repo, auth bypass, React2Shell, unauthenticated API access to financial data |
| **High** | Serious exploitability requiring specific conditions, or major architectural flaw guaranteeing fragility | Missing auth on non-public endpoint, weak crypto, Docker running as root, unsafe file uploads, N+1 on hot path |
| **Medium** | Inefficient logic, unhandled edge cases under specific load, or minor misconfiguration not posing immediate threat | Missing some security headers, incomplete logging coverage, SBOM missing, unoptimised query, minor CSP gap |
| **Low/Info** | Minor deviations from guidelines with negligible impact | Style nitpicks, non-optimal syntax, documentation gaps |

### 4.2 Gate Blocking Policy

| Severity | Phase Gate | PR Gate | Release Gate |
|---|---|---|---|
| **Critical** | Block. Immediate remediation. | Block. Immediate remediation. | Block. Incident-style workflow. |
| **High** | Block. Must fix before phase passes. | Block. Must fix or explicit policy-owner acceptance. | Block. No exceptions without documented compensating controls. |
| **Medium** | Track (create issue). Allow merge to integration branch. | Block for security-relevant Mediums in auth/payment/PII. Allow others with acknowledgement. | All must be resolved or explicitly accepted with documented rationale. |
| **Low/Info** | Do not block. Informational only. | Do not block. PR comments only. | Do not block. Refactoring backlog. |

### 4.3 Severity Escalation Protocol

Medium findings MUST be automatically escalated to High when:
- Same Medium issue appears across **3+ critical services** (cross-service systemic risk)
- Same pattern exceeds a **volumetric threshold** of 20+ instances within a single repo or 50+ across the fleet
- Medium issue occurs in **sensitive components** as defined by `gates.critical_modules` in `forge.project.yaml`
- Medium issue persists beyond **one release cycle** (defined as 2 calendar weeks) without remediation or explicit deferral

Escalation thresholds are configurable per-repo via `forge.project.yaml` gate overrides. This prevents silent accumulation of technical debt by treating aggregate risk as collective High severity.

### 4.4 Suppression & Accepted Risk

**MUST:** Allow per-finding actions: `suppress_false_positive`, `accept_risk_until_date`, `defer_with_reason`.

**MUST:** Require comments and approver role for accepted risk. Log all suppressions with justification.

**MUST:** Set expiration on accepted-risk items (maximum 90 days). Periodically review and re-validate.

**MUST:** Suppressed findings carry `nosemgrep` or standardised comment pragmas. The pipeline reads these and skips re-alerting on that specific code block.

---

## 5. Gate Specifications

### 5.1 Phase Gate (End of S##.P##.T## Session)

**Purpose:** Rapid feedback; prevent fundamentally broken code from entering integration.

**Deterministic Tools (parallel):**
- ruff (lint) + mypy (Python)
- eslint + `tsc --noEmit` (TypeScript)
- Semgrep (security + critical correctness rules — changed files only)
- detect-secrets (pre-commit hook)
- pip-audit / npm audit (`--audit-level=high`)
- pytest / Jest (targeted — changed modules)
- Coverage check (changed modules)

**AI Review (narrow scope, cost-effective models):**
- Security agent (mid-tier model, focused on changed files, using Semgrep + audit outputs as context)
- Silent failure / type-safety agent (pattern-based)

**Gate Policy:**
- Fail on Critical/High
- Track Medium security issues (create issue); allow merge to integration
- Up to 3 remediation rounds; escalate on failure

**Evidence produced:**
- Machine-readable JSON summary of findings by severity
- Links to tool logs (Semgrep, ruff, mypy, eslint, tsc, detect-secrets, pip-audit, npm audit)

### 5.2 PR Gate (Into Main)

**Purpose:** Comprehensive review; block defective code from main branch.

**Deterministic Tools (parallel):**
- Full test suite (backend + frontend)
- Coverage threshold gate (>= 80% for modified files)
- Semgrep full ruleset (Python/FastAPI + TypeScript/Next.js, excluding legacy areas via baselines)
- detect-secrets, pip-audit, npm audit
- oasdiff (OpenAPI breaking change detection — cross-ref OPS-STD-003)

**AI Multi-Agent Review (parallel specialist agents on diff + context):**
- Security agent (frontier model) with Semgrep findings and dependency reports
- Correctness / type-safety agent using mypy/tsc logs
- Performance agent focusing on DB access, loops, async blocking
- Contract & test agent checking API schemas vs code and test adequacy
- Silent failure hunter

**Synthesizer Agent:**
- Merges all findings
- Assigns severity and confidence
- Outputs structured JSON + markdown summary
- Resolves conflicts using hierarchy (section 2.6)

**Gate Policy:**
- Block merge on unresolved High/Critical
- Require tracking + accept-risk annotation for Mediums
- Up to 3 remediation iterations; beyond that, require Tier 2/3 handling

**Evidence produced:**
- Structured JSON findings report
- Human-readable markdown report (attached to PR or stored per phase)
- Suppression report listing who suppressed what, when, why
- AI review summary with confidence scores

### 5.3 Release Gate (Before Production Deploy)

**Purpose:** Final hardening; compliance evidence; immutable audit trail.

**Deterministic Tools:**
- Semgrep security rulesets on full service (not just diff)
- pip-audit / npm audit with stricter thresholds (no Highs; Mediums in critical deps reviewed)
- Trivy container scan (cross-ref OPS-STD-002 INF-IMAGE-01)
- Syft SBOM generation
- Optional focused dynamic tests on critical endpoints

**AI Review (deep):**
- Security + Architecture agent: whole-service pass on diff since last release, focusing on auth flows and data boundaries
- Contract reviewer: verify no DB schema mutations or API response structures violate external expectations
- Uses frontier models exclusively

**Gate Policy:**
- No unresolved Critical/High security or correctness issues
- No un-reviewed Mediums in auth, payment, or PII modules
- All accumulated Phase Gate Medium issues must be resolved or explicitly accepted
- Document exceptions in a release risk log

**Evidence produced (immutable):**
- Manifest of all executed tests
- Cryptographic hash of approved code
- Software Bill of Materials (SBOM)
- Finalized audit log with findings, confidence scores, and agent attributions
- Release risk log (any accepted exceptions)
- Coverage report

---

## 6. Human-in-the-Loop Integration

### 6.1 Progressive Trust Tiers

| Trust Tier | Scope | Human Involvement | Merge Policy |
|---|---|---|---|
| **Tier 1: Auto-Merge** | Routine tasks, dependency updates, localised bug fixes, isolated component additions | None. Full autonomy. | All gates pass, no Critical/High, no net new Medium+. Auto-merge and deploy. |
| **Tier 2: Supervised** | Complex business logic, cross-file refactoring, moderate API adjustments | Validation only. Human reviews synthesised audit summary, not raw code. | AI handles generation + review. Human verifies behavioural intent via audit log. |
| **Tier 3: Human-Gated** | Foundational architecture changes, DB schema redesigns, high-risk security changes, auth/payment flows | Manual audit. Senior engineering sign-off required. | AI provides deep threat models + context. Deployment strictly gated. |

**MUST:** Default to Tier 2 (supervised) until the gate system has demonstrated reliability through production metrics (escaped defect rate < 2% over 30 days). Once reliability is proven, progressively promote proven-safe change categories (dependency updates, localised bug fixes) to Tier 1. Push changes to Tier 3 when risk criteria are met.

**MUST:** Track metrics on escaped defects per tier to continuously shrink the Tier 3 surface area.

### 6.2 Escalation Triggers

Escalate from automated to human review when:
- Iteration cap (3 rounds) exceeded with unresolved High/Critical
- Patterns of recurring Medium issues in critical areas
- Agents explicitly mark a finding as "uncertain" with possible high impact
- Fix churn detected (section 3.4)
- AI-generated code fails quality gates after 3 attempts (model is stuck in local optimum)

### 6.3 Alert Fatigue Prevention

**MUST:** The Synthesizer agent filters findings before presenting to human reviewers:
- Strip all Low/Info noise
- Group related findings by endpoint/module with narrative explanation
- Highlight only Critical/High and uncertain Mediums
- Show executive summary: count of Critical/High/Medium, changed files at risk

**MUST NOT:** Dump raw agent output to human reviewers.

---

## 7. Metrics & Continuous Improvement

### 7.1 Core Metrics

| Metric | Definition | Target |
|---|---|---|
| **Signal-to-Noise Ratio** | (True positives: findings accepted as actionable by developer or auto-remediated) / (Total generated findings across all agents and tools) | >= 85% (i.e., false positive rate < 15%) |
| **Finding Rate per Round** | Defects caught in initial scan vs Round 2/3 | Diminishing: Round 1 > Round 2 > Round 3 |
| **Gate Pass Rate (first attempt)** | PRs that pass all gates on first submission | > 70% as systems mature |
| **Mean Iterations to Pass** | Average remediation rounds before gate passes | < 2.0 |
| **Cost per Review** | Total API token expenditure + tool runtime per PR | Track and optimise |
| **Time to Review** | End-to-end latency from PR creation to gate verdict | Track and optimise |
| **Escaped Defects** | Issues found in production (Sentry, incidents) that could have been caught | Minimise; use to add new rules |
| **False Positive Rate** | Per agent/tool: percentage of findings later suppressed or marked accepted risk | < 15% per agent |

### 7.2 Metrics-Driven Tuning

**MUST:** Iteratively adjust the pipeline based on metrics:
- Disable or tighten consistently noisy rules (high false positive rate)
- Add rules for recurring escaped defects
- Upgrade model tier for agents with high escaped-defect rates
- Reduce/increase iteration cap based on observed marginal value of extra rounds
- Reduce agent count if false-positive rates spike without corresponding reduction in escaped defects

### 7.3 A/B Testing

**SHOULD:** Support shadow-mode A/B testing of agent configurations:
- Route PRs to both baseline and experimental configurations
- Compare: false positive rate, token cost, task success rate within 3-round limit
- Gradually roll out improvements via feature flags

---

## 8. Static Analysis Integration

### 8.1 Tool Layering

Static analysis runs **before** AI agents. AI agents receive static tool outputs as context.

```
Layer 1 (Deterministic, Fast):
  ruff, eslint, mypy, tsc, detect-secrets
  -> Fail fast on lint/type errors

Layer 2 (Pattern + Data Flow):
  Semgrep (custom + registry rules)
  pip-audit, npm audit
  -> Catch known vulnerability patterns

Layer 3 (Semantic, AI):
  Specialist review agents
  -> Reason about business logic, auth, multi-module interactions
  -> Re-evaluate static findings ("is this Semgrep match exploitable?")
  -> Reduce false positives with contextual understanding

Layer 4 (Synthesis):
  Synthesizer agent
  -> Deduplicate, resolve conflicts, assign confidence
  -> Produce final report
```

### 8.2 Semgrep Configuration

**MUST:** Maintain custom rules under version control with test cases for each rule.

**MUST:** Use `.semgrepignore` to exclude test fixtures, migrations, and generated code.

**MUST:** Focus on high-impact patterns:
- FastAPI routes missing auth dependency
- SQLAlchemy injection patterns
- React unsafe innerHTML without sanitiser
- Unvalidated user input reaching dangerous sinks
- Next.js hydration mismatches and RSC payload handling

**SHOULD:** Use taint-mode and data-flow features for injection and sensitive-data flows.

### 8.3 CodeRabbit Integration

**SHOULD:** Integrate CodeRabbit as a GitHub Action on PRs to main:
- Configure via `coderabbit.yaml` to focus on architecture, maintainability, and design
- Feed CodeRabbit findings into the orchestrator, mapping to the internal severity schema
- Run primarily at PR Gate or for Tier 2/3 changes to control cost

### 8.4 SAST + LLM Synergy

The most effective pipeline uses SAST as a deterministic pre-filter:
1. Static tools (Semgrep, ruff, eslint) execute first, generating raw violations
2. Violations are injected into AI agent context windows
3. AI evaluates static findings against semantic reality — filters false positives, enriches true positives with actionable remediation
4. This leverages SAST's 100% recall and LLM's contextual understanding

---

## 9. Gate Configuration as Code

### 9.1 Gate Policy Schema

Gate policies MUST be defined as machine-readable configuration, not embedded in prompts:

```yaml
# forge-gate-policy.yaml
gates:
  phase_gate:
    scope: changed_files
    tools:
      - ruff
      - mypy
      - eslint
      - tsc
      - semgrep:
          ruleset: security-critical
          scope: changed_files
      - detect-secrets
      - pip-audit:
          audit_level: high
      - npm-audit:
          audit_level: high
    agents:
      - security:
          model_tier: mid
          scope: changed_files
      - silent_failure:
          model_tier: mid
          scope: changed_files
    blocking:
      critical: block
      high: block
      medium: track
      low: ignore
    max_iterations: 3
    evidence:
      - findings_json
      - tool_logs

  pr_gate:
    scope: full_diff
    tools:
      - ruff
      - mypy
      - eslint
      - tsc
      - semgrep:
          ruleset: full
          baseline: true
      - detect-secrets
      - pip-audit
      - npm-audit
      - oasdiff
      - pytest:
          coverage_threshold: 80
      - jest:
          coverage_threshold: 80
    agents:
      - security:
          model_tier: frontier
      - correctness:
          model_tier: mid
      - performance:
          model_tier: frontier
      - contract:
          model_tier: frontier
      - test_coverage:
          model_tier: mid
      - silent_failure:
          model_tier: mid
    synthesizer:
      model_tier: frontier
      confidence_threshold: 0.8
    blocking:
      critical: block
      high: block
      medium: block_security_only
      low: ignore
    max_iterations: 3
    evidence:
      - findings_json
      - markdown_report
      - suppression_report
      - ai_review_summary

  release_gate:
    scope: diff_since_last_release
    tools:
      - semgrep:
          ruleset: full
          scope: full_service
      - pip-audit:
          audit_level: medium
      - npm-audit:
          audit_level: medium
      - trivy
      - syft
    agents:
      - security:
          model_tier: frontier
          scope: full_service
      - contract:
          model_tier: frontier
    blocking:
      critical: block
      high: block
      medium: block_in_critical_modules
      low: ignore
    critical_modules:
      - auth
      - payments
      - pii
    max_iterations: 3
    evidence:
      - findings_json
      - markdown_report
      - test_manifest
      - code_hash
      - sbom
      - audit_log
      - release_risk_log
      - coverage_report
```

### 9.2 Finding Output Schema

All agents and tools MUST emit findings in this normalised format:

```json
{
  "finding_id": "f-abc123",
  "tool": "semgrep",
  "agent": "security_reviewer",
  "rule_id": "fastapi-route-missing-auth",
  "kind": "security",
  "severity": "High",
  "confidence": 0.92,
  "file": "src/api/endpoints.py",
  "line": 42,
  "column": 5,
  "end_line": 50,
  "summary": "FastAPI route missing auth dependency",
  "rationale": "Endpoint /api/v1/reports is accessible without authentication",
  "suggested_fix": "Add Depends(get_current_user) to route decorator",
  "first_seen_round": 1,
  "last_seen_round": 1,
  "status": "open",
  "suppression": null
}
```

---

## 10. Implementation Checklist

### Phase 1: Foundation (Week 1–2)
- [ ] Define gate policy YAML for all 3 gate types
- [ ] Configure deterministic tools in CI (ruff, mypy, eslint, tsc, detect-secrets, Semgrep, pip-audit, npm audit)
- [ ] Implement finding output schema (JSON)
- [ ] Set up baseline tracking for legacy issues

### Phase 2: AI Review Pipeline (Week 3–4)
- [ ] Build Review Orchestrator (dispatch to parallel agents)
- [ ] Implement Security and Silent Failure agent prompts with structured output
- [ ] Build Synthesizer agent (deduplication, conflict resolution, confidence scoring)
- [ ] Implement 3-round iteration loop with round tracking metadata
- [ ] Integrate CodeRabbit as GitHub Action

### Phase 3: Gate Enforcement (Week 5–6)
- [ ] Enable Phase Gate on all repos (non-blocking initially for calibration)
- [ ] Enable PR Gate on main branch (blocking for High/Critical)
- [ ] Configure suppression workflow (nosemgrep pragmas, accept-risk with expiry)
- [ ] Implement severity escalation protocol (Medium aggregate -> High)

### Phase 4: Metrics & Tuning (Week 7–8)
- [ ] Instrument metrics collection (SNR, finding rate per round, cost per review, escaped defects)
- [ ] Set up dashboards for gate effectiveness
- [ ] First tuning pass: disable noisy rules, adjust thresholds
- [ ] Enable Release Gate for production deploys
- [ ] Begin A/B testing agent configurations (shadow mode)

### Phase 5: Autonomy Expansion (Week 9+)
- [ ] Define Tier 1/2/3 classification criteria
- [ ] Enable auto-merge for Tier 1 changes
- [ ] Track escaped defects per tier
- [ ] Progressively expand Tier 1 scope based on metrics

---

## Appendices

### A. Standards References

| Standard | Relevance |
|---|---|
| OPS-STD-002 (Security Controls) | Defines security controls enforced by gates; severity model |
| OPS-STD-003 (API Contract Standard) | Defines contract testing (oasdiff, Schemathesis) enforced at gates |
| OWASP Top 10 2025 | Security agent's primary framework |
| OWASP API Security Top 10 2023 | API-specific security checks |
| CIS Docker Benchmark | Infrastructure checks at Release Gate |

### B. Source Alignment

This standard synthesises research from three independent AI providers:

| Source | Unique Contributions |
|---|---|
| **Perplexity** | Most detailed end-to-end pipeline architecture (4 stages: Local/Phase/PR/Release); concrete iteration workflow template (5 steps); tool-specific integration guidance (Semgrep rule quality, CodeRabbit YAML, ruff/mypy/eslint/tsc); tiered merge policies (Tier 1/2/3); metrics-driven tuning framework; A/B testing approach; baseline management for legacy debt |
| **GPT 5.4** | Strongest on specialist agent roles and prompt design; iterative audit with "fix churn" detection; consensus/voting for confidence (multi-model cross-checking); phase gate vs final gate differentiation; human-in-the-loop as exception handler; CodeRabbit CLI/CI integration; Semgrep dataflow rules (84% true-positive rate); suppression workflow with expiration |
| **Gemini Pro 3.1** | Compound hallucination quantification (70% degradation in sequential chains); AST-based fix churn detection via Dynamic Time Warping; severity escalation protocol (volumetric threshold for Medium -> High); confidence scoring with tau >= 0.8 threshold; economic model allocation (agent -> model tier mapping); cryptographic audit logs at Final Gate; shadow-mode A/B testing infrastructure; circuit breaker safeguards (token budget limits, state mutation tracking); trust tiers as philosophical framework |

**Divergences resolved:**
- **Iteration cap:** All three sources converge on 3 rounds as optimal. **Adopted as standard.**
- **Agent count:** GPT suggests 6 named roles; Perplexity suggests 5 perspectives; Gemini suggests 4-6 before diminishing returns. **This standard uses 6 specialist agents** matching the union of recommendations.
- **Confidence threshold:** Only Gemini specifies tau >= 0.8. **Adopted** as it provides a concrete, enforceable criterion.
- **Sequential vs parallel:** Gemini quantifies sequential degradation (70%); GPT/Perplexity recommend parallel. **Parallel mandated, sequential prohibited for primary review.**
- **Severity escalation:** Only Gemini proposes automatic Medium -> High escalation via volumetric threshold. **Adopted** as it prevents silent debt accumulation.
- **Model allocation:** Gemini provides the most explicit economic mapping (Frontier/Mid-Tier/Low-Tier per agent). **Adopted** with specific recommendations.
- **CodeRabbit role:** GPT positions as CI Action; Perplexity as pipeline component. **This standard uses CodeRabbit at PR Gate, normalised into internal schema.**

### C. Cross-References

| Related Standard | Relationship |
|---|---|
| OPS-STD-001 (AUTH_SSO_STANDARD) | Auth patterns that Security Agent validates |
| OPS-STD-002 (SECURITY_CONTROLS) | Security controls checklist that gates enforce; Semgrep rules defined there |
| OPS-STD-003 (API_CONTRACT_STANDARD) | Contract testing tools (oasdiff, Schemathesis) run at PR and Release gates |
| OPS-STD-005 (FORGE_PROJECT_SCHEMA) | Per-repo `forge.project.yaml` that configures which gates and agents apply |
