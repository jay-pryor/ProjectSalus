# Review Gate Rules

## Required Review Agents

Every task must be reviewed by these agents before completion:

| Agent | Role | Model |
|-------|------|-------|
| forge_spec_compliance | Spec vs implementation drift | Kimi K2.5 |
| forge_silent_failure_hunter | Missing error handling | Gemini 3.2 |
| forge_code_simplifier | Over-engineering detection | GLM-4 Flash |
| forge_regression_reviewer | Breaking change detection | GLM-4 Flash |

## Conditional Agents

| Agent | Trigger | Model |
|-------|---------|-------|
| forge_frontend_design_reviewer | .tsx/.css/.scss changes | GLM-4 Flash |
| forge_type_design_analyzer | Type-heavy changes | Gemini 3.2 |
| forge_repo_scale_reviewer | Cross-repo changes | Gemini 3.2 |

## Gate-Proof Format

Write to `.forge/gate-proofs/{task_id}.yaml` after review:

```yaml
task_id: TASK_ID
timestamp: ISO8601
reviews:
  agent_name:
    status: pass|fail
    findings: N
    resolved: true|false
    model: model/name
    duration_s: N
overall: pass|fail
escape_hatch: false
```

## Escape Hatch

`--force-skip-review --reason "minimum 10 characters"`
- Sets escape_hatch: true in gate-proof
- Logged in audit trail
- Visible in weekly improvement reports
