# Codex Standards Review

This review captures the issues identified in one pass across the current draft standards as of 2026-03-14. It focuses on internal consistency, implementation risk, maintenance burden, and a small number of externally verified factual issues.

## Cross-Cutting Themes

- The draft set is stronger than average on specificity and operational intent, but several documents mix stable standards with volatile implementation detail such as exact package versions, specific tool choices, model vendors, and current deployment patterns.
- The three strongest recurring risks are ambiguity at system boundaries, stale or incorrect cross-references, and requirements that are written as universal `MUST` statements when they are really environment-dependent implementation choices.
- The AI provenance appendices should be removed from normative standards. They weaken authority, create maintenance noise, and invite readers to debate drafting inputs instead of the control itself.

## API_CONTRACT_STANDARD.md

### Strengths

- The overall contract strategy is sound: code-first OpenAPI for FastAPI, AsyncAPI for async interfaces, generated clients, and diff-based breakage detection.
- The document has good instincts around RFC 9457 problem details, integration records, and database schema ownership.

### Issues

- Lines 61 and 615-620: the document says OpenAPI artefacts are exported in CI and committed by CI. CI should verify that committed contract artefacts are current, not mutate the repo as part of normal validation. A safer standard is "generate in CI, fail if the checked-in artefact is stale."
- Lines 144-146: the standard requires custom headers to use the `X-` prefix. That is outdated guidance. RFC 6648 deprecated the practice for new parameters. The standard should move to plain names such as `Correlation-Id` or a vendor namespace if needed.
- Lines 175-188: "all collection endpoints MUST return a standard pagination envelope" is too absolute. Some endpoints are naturally bounded or lookup-like, and some interfaces may need cursor pagination rather than offset pagination. This should allow explicitly documented exceptions.
- Lines 217-226, 271-277, 611-676: large parts of the document are really implementation guidance rather than stable standard. Exact tool and package choices such as Orval, openapi-fetch, pact-python, and specific CI stage shapes should live in a reference implementation guide or playbook.
- Lines 522-537: timestamp-based Alembic revision identifiers and schema-targeted migration mechanics are reasonable patterns, but they are implementation decisions rather than universal contract policy. They should likely be moved to a database migration guide.
- Lines 713-728: the AI source-alignment appendix should not be in the authoritative standard.

### Recommended Changes

- Keep the normative core: contract source of truth, compatibility rules, error format, versioning policy, and database ownership expectations.
- Move tool version matrices, exact codegen recommendations, and CI sequence details into an implementation guide.
- Replace the `X-` header rule with a modern naming rule aligned to RFC 6648.

## AUTH_SSO_STANDARD.md

### Strengths

- The default-on authentication posture is good.
- The document correctly pushes authz decisions to the application layer rather than the gateway.
- The Next.js DAL pattern, cookie handling, and service-account separation are directionally strong.

### Issues

- Lines 62-69, 152-179, and 224-253: the standard does not define one coherent browser-to-backend trust model. It simultaneously specifies browser cookie sessions, Bearer-token validation in FastAPI, and a Next.js DAL/BFF-style pattern without explicitly choosing how browser traffic reaches FastAPI. This is the most important gap in the set because different teams will implement materially different auth paths.
- Lines 117-128: OIDC back-channel logout is written as a baseline `MUST`, but this is too strong for a default standard unless the full stack is proven to support it. Authentik documents OIDC back-channel logout as `2025.8.0+ Preview` and notes RP support requirements. This should be downgraded to a conditional requirement or moved to a higher-assurance profile.
- Lines 181-184: the requirement that all crypto and network auth dependencies use `async def` is technically over-broad. Async is appropriate for non-blocking network I/O, but CPU-bound crypto executed inside `async def` can still block the event loop. The standard should require non-blocking implementations and benchmarking, not `async def` as a proxy.
- Lines 272 and the related Next.js pin in OPS-STD-002 line 127: the document treats a historical minimum Next.js patch version as if it were durable security policy. As of 2026-03-14, later 2025 advisories required higher patched versions than `15.2.3`. The standard should define an update policy, not a frozen minimum.
- Lines 42-45 and 325-328: CORS ownership is split between Nginx and FastAPI. That may be workable, but the standard should clearly state which layer is authoritative for preflight handling, which layer is authoritative for allowed origins, and how drift is prevented.
- Lines 496-506: the AI source-alignment appendix should not be in the authoritative standard.

### Recommended Changes

- Add an explicit "request path and token transport model" section that chooses one of: Next.js BFF, direct browser bearer tokens, or same-site cookie auth to FastAPI.
- Move back-channel logout into an advanced profile unless the deployed IdP and all relying parties are validated to support it.
- Replace exact security version pins with an update-SLA rule.

## SECURITY_CONTROLS.md

### Strengths

- This is the strongest document in the set.
- The control IDs, automation columns, severity mapping, and waiver process make it substantially more actionable than a typical policy document.
- The coverage across application, infra, and logging/privacy concerns is good.

### Issues

- Lines 124-128 and the related auth standard line 272: the Next.js vulnerability rule is too static. Security standards should not hardcode one historical safe floor and assume it stays sufficient. This needs to become "maintain latest supported patch within defined SLA after a security advisory."
- Lines 236-258: the legal/privacy section contains high-stakes compliance claims, retention requirements, and penalty language without citing primary legal or regulator sources inline. If this document is going to be treated as authoritative, the legal sections should either cite counsel-approved sources directly or be moved behind a policy/legal review note.
- Lines 153-173: the Docker Compose example includes `deploy.resources`, which is often treated differently across environments and can create a false sense of enforcement if readers assume the example is universally effective. The standard should call out environment-specific enforcement expectations.
- Lines 316 onward and the tool/version material more broadly: the document mixes stable control expectations with exact tool choices and current package versions. The control statements should remain in the standard; the toolchain should move to a supporting implementation document.
- Lines 558-573: the AI source-alignment appendix should not be in the authoritative standard.

### Recommended Changes

- Keep the control catalog mostly intact.
- Separate legal interpretation, toolchain guidance, and example implementations from the normative control statements.
- Introduce a single security patching policy that other standards can reference instead of duplicating framework-specific version floors.

## FORGE_GATE_POLICY.md

### Strengths

- The fan-out/gather review shape is sensible.
- The distinction between phase, PR, and release gates is clear.
- The document usefully separates suppression, accepted risk, escalation, and metrics.

### Issues

- Lines 51-52, 129-130, and 146-149: the standard makes strong empirical claims such as "up to 70% output degradation," "optimal threshold," and "diminishing returns are empirically proven" without citing any source. Those claims are too strong to carry normative weight unless they are referenced and reproducible.
- Lines 78-83, 251-253, 276, and 313: specific model vendors and model tiers are hardcoded into the standard. That is operational configuration, not stable policy. This will age quickly and force standard edits for routine tooling changes.
- Line 111: `tau >= 0.8` is ambiguous as written. If `tau` is the minimum accepted confidence, then findings below `0.8` are discarded. The text should say exactly that and define how confidence is calibrated.
- Lines 216-220: automatic escalation of Medium findings to High based on volume or age is directionally reasonable, but the thresholds are underspecified and could create unstable gate behavior across repos. This needs either hard definitions or repo-level override points.
- Line 232: using `nosemgrep` or comment pragmas as a generalized suppression mechanism couples the whole gate policy to one tool and encourages source-level suppression sprawl. Suppression should be centrally tracked, with code comments only as an exception.
- Lines 337-343: "default to Tier 1 for the majority of changes" is too aggressive for a new AI-heavy gate system. Defaulting most changes to auto-merge should come only after reliability is demonstrated with production metrics.
- Lines 372-379: some metric definitions are not yet rigorous enough to guide policy. For example, the signal-to-noise numerator of "Accepted Tier 1 + Tier 2 findings" is unclear and does not map cleanly to actionable findings or true positives.

### Recommended Changes

- Strip out uncited benchmarking claims or move them into a rationale appendix with sources.
- Move model/vendor selections into Forge configuration, not the policy standard.
- Make confidence semantics, suppression workflow, and tier defaults much more precise before this is treated as binding.

## FORGE_PROJECT_SCHEMA.md

### Strengths

- The schema direction is good. A machine-readable repo profile is a strong idea and would simplify gating, profiling, and automation.
- The separation between schema, autodetection, validation, and examples is helpful.

### Issues

- Lines 163 and 252-253: the schema references control IDs that do not exist or do not match the security standard. `APP-SUPPLY-03` is not defined in OPS-STD-002; file upload validation is `APP-IV-02`. `APP-WEBHOOK-01 through APP-WEBHOOK-03` is also inconsistent with OPS-STD-002, which currently defines `APP-WEBHOOK-01` only.
- Lines 187-189: the database cross-references to OPS-STD-003 are wrong. Database governance and views-as-contracts are in section 9 of the API contract standard, not section 8.
- Lines 287-288 and 295-301: low-confidence keyword grep is being used to infer compliance-significant flags such as `handles_auth` and `handles_pii`. Those fields should never silently drive policy obligations from heuristics. At most, the tool should propose a value and require explicit confirmation.
- Lines 297-299: encoding ownership state in YAML comments such as `# AUTO-DETECTED` and `# MANUAL` is brittle. Comments are not stable machine metadata and are easy to lose during formatting or user edits. This state should live in tool metadata or in explicit schema fields.
- Lines 316-317: requiring `stack.frameworks` to contain at least one entry is too strict for some repositories, especially low-level libraries, simple utilities, or infra-only repos with no framework in the usual sense.
- Line 343: making `detect_secrets.enabled: true` an error only when `security.exposed_to_internet: true` is inconsistent with OPS-STD-002, which treats secrets scanning as mandatory generally. Secret scanning should not depend on internet exposure.
- Lines 79-88 and the example commands later in the document: the schema models commands as opaque shell strings. That is easy to author, but it is weak as a machine-readable contract because it bakes in shell semantics, quoting behavior, and platform assumptions. If Forge is going to execute these, an argument-array form or execution profile would be safer.
- Line 277: "presence of Dockerfile only -> infrastructure" is too weak as a detection rule and will misclassify many normal application repos.
- Line 291: `api.role` detection by spotting `fetch`, `axios`, or `httpx.AsyncClient` is also too weak to drive policy decisions reliably.

### Recommended Changes

- Fix the broken cross-references before using the schema as a generator or validator source.
- Treat `security.*` flags and similar policy-driving fields as explicitly confirmed metadata, not inferred truth.
- Decide whether this schema is a human-authored contract or an auto-generated profile. Right now it is trying to be both, and the comment-based ownership model is a symptom of that confusion.

## External Verifications Used In This Review

- RFC 6648 deprecates the `X-` prefix convention for new protocol parameters: <https://www.rfc-editor.org/rfc/rfc6648>
- Authentik documents OIDC back-channel logout as `2025.8.0+ Preview`: <https://docs.goauthentik.io/add-secure-apps/providers/oauth2/backchannel-logout/>
- Next.js advisory history shows later patched versions beyond the minima cited in the standards, including `GHSA-f82v-jwr5-mffw`, `GHSA-4342-x723-ch2f`, and `GHSA-xv57-4mr9-wg8v`:
  - <https://github.com/advisories/GHSA-f82v-jwr5-mffw>
  - <https://github.com/advisories/GHSA-4342-x723-ch2f>
  - <https://github.com/advisories/GHSA-xv57-4mr9-wg8v>

## Suggested Next Step

Split each document into:

- A short normative standard containing only stable policy and cross-references.
- A separate implementation guide containing tools, versions, model choices, CI examples, and environment-specific recommendations.
