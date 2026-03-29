---
name: forge-review
description: Trigger review gate. Invokes CC plugins and specialist agents. Logs defects. Writes gate-proof YAML.
---

# Forge Review Skill

Trigger the review gate for a completed task.

## Review Layers

### Per-Task (Phase Gate — light rigor)

1. **L1 — Automated:** `forge check standards` + `forge check cross-cutting`
2. **L2 — CC Plugins:** Invoke subagent(s) on changed files:
   - `pr-review-toolkit:silent-failure-hunter` (ALWAYS required)
   - Pick 1-2 more relevant: `coderabbit:code-review`, `code-simplifier:code-simplifier`

### Per-Phase (PR Gate — full rigor, via T_REVIEW task)

L1 + L2 as above, PLUS:

3. **L3 — Specialist Agents (all 4 required):**
   - `forge_spec_compliance` → `superpowers:code-reviewer` subagent type
   - `forge_silent_failure_hunter` → `pr-review-toolkit:silent-failure-hunter` subagent type
   - `forge_code_simplifier` → `code-simplifier:code-simplifier` subagent type
   - `forge_regression_reviewer` → `pr-review-toolkit:code-reviewer` subagent type
4. **L4 — Human:** Only for Tier 3 items (auth, SSO, schema changes, execution/)

### Conditional Agents

- `forge_frontend_design_reviewer` — Only on .tsx/.css/.scss changes
- `forge_type_design_analyzer` — On type-heavy changes

## CRITICAL: Defect Logging BEFORE Remediation

**Every finding at Critical/High/Medium severity MUST be logged in `.forge/defect-register.yaml` BEFORE any fix is attempted.**

```yaml
- id: D-NNN          # Next sequential ID
  severity: critical  # critical|high|medium
  phase: S##.P##
  found_by: agent_name
  file: path/to/file.py
  description: "What the finding is"
  resolution: ""      # Filled after fix
  status: open        # open → resolved
  commit: ""          # Commit hash after fix
```

This is NOT optional. The gate-proof must reference defect IDs. The enforcement hooks validate this.

## Gate-Proof Output

After all agents pass, write gate-proof to `.forge/gate-proofs/{task_id}.yaml`:

```yaml
task_id: TASK_ID
timestamp: ISO8601
gate_type: phase|pr
quality_gates:
  G1_lint: pass|fail
  G2_format: pass|fail
  G3_import: pass|fail
  G4_type: pass|fail
  G5_security: pass|fail
  G6_unit_test: pass|fail
  G7_integration: pass|fail
  G8_coverage: pass|fail
  coverage_pct: N
review:
  l1_static:
    forge_standards: pass|fail
    forge_cross_cutting: pass|fail
  l2_plugins:
    tools_used: [list of subagent types actually invoked]
    findings_count: N
    all_resolved: true|false
  l3_agents:           # Only for PR Gate (T_REVIEW)
    forge_spec_compliance: {status: pass|fail, findings: N}
    forge_silent_failure_hunter: {status: pass|fail, findings: N}
    forge_code_simplifier: {status: pass|fail, findings: N}
    forge_regression_reviewer: {status: pass|fail, findings: N}
defect_ids: [D-NNN, ...]   # All defects found and resolved in this review
overall: pass|fail
escape_hatch: false
```

## Escape Hatch

Use `--force-skip-review --reason "..."` only when genuinely blocked.
Requires minimum 10 character reason. Logged in audit trail.
Escape hatches are tracked and must be resolved before release gate.
