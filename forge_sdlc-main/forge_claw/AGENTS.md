# Forge Review Agents — Cline Configuration

## Agent Definitions

### forge_spec_compliance
- **Role:** Validates implementation matches phase spec acceptance criteria
- **Model:** moonshotai/kimi-k2.5 (OpenRouter)
- **Cost tier:** Low
- **Trigger:** Always (every task review)
- **Input:** Phase spec + git diff
- **Output:** JSON findings with severity, file, line, category, message, recommendation

### forge_silent_failure_hunter
- **Role:** Detects missing error handling, swallowed exceptions, silent failures
- **Model:** google/gemini-3.2 (Vertex AI)
- **Cost tier:** Medium
- **Trigger:** Always
- **Input:** Full file content for modified files
- **Output:** JSON findings

### forge_type_design_analyzer
- **Role:** Analyses type safety, interface contracts, type design quality
- **Model:** google/gemini-3.2 (Vertex AI)
- **Cost tier:** Medium
- **Trigger:** On type-heavy changes (models, schemas, interfaces)
- **Input:** Diff + type definition files

### forge_code_simplifier
- **Role:** Detects over-engineering, unnecessary abstraction, premature complexity
- **Model:** zhipu/glm-4-flash (OpenRouter)
- **Cost tier:** Low
- **Trigger:** Always
- **Input:** Git diff

### forge_regression_reviewer
- **Role:** Detects breaking changes, dependency impacts, behavioral regressions
- **Model:** zhipu/glm-4-flash (OpenRouter)
- **Cost tier:** Low
- **Trigger:** Always
- **Input:** Git diff + function signatures before/after

### forge_repo_scale_reviewer
- **Role:** Cross-repo contract consistency, multi-service impact
- **Model:** google/gemini-3.2 (Vertex AI)
- **Cost tier:** Medium
- **Trigger:** On changes affecting service contracts or shared types
- **Input:** Service map + git diff

### forge_frontend_design_reviewer
- **Role:** Design system compliance, accessibility, component quality
- **Model:** zhipu/glm-4-flash (OpenRouter)
- **Cost tier:** Low
- **Trigger:** Only on .tsx/.ts/.css/.scss/.jsx changes
- **Input:** Modified frontend files

## Gate-Proof Integration

After running agents, write results to `.forge/gate-proofs/{task_id}.yaml`.
All required agents must pass before task completion is allowed.

## Escape Hatch

Use `--force-skip-review --reason "..."` when genuinely blocked.
Minimum 10 character reason required. Logged in audit trail.
