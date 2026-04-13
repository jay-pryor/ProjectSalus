Run the full review sequence for the current task and produce a gate-proof.

Usage: /salus-review <task_id>
Example: /salus-review S1-3

This skill runs the complete L1 + L2 review pipeline and writes the gate-proof YAML.
Use this after implementation is complete and all tests pass.

## Review Sequence

### Phase 1 — Quality Gates (G1–G8)

Run all 8 gates. Record pass/fail for each:

```bash
ruff check src/ tests/                                    # G1
ruff format --check src/ tests/                           # G2
ruff check --select I src/                                # G3
mypy src/salus/                                           # G4
python -m bandit -r src/ -ll -q                           # G5
pytest tests/ -v                                          # G6
pytest tests/ --cov=src/salus --cov-fail-under=80 -q      # G7
```

G1–G7 apply to Python files only. If the task touches only `.js`, `.html`, or
`manifest.json` files under `src/salus/viewer/static/` or `modules/` and no
Python files changed, record G1–G7 as N/A with reason "JS-only task".

### Phase 2 — L1 Standards Review

Read the changed files against `.salus/standards/`. Check each applicable standard:

| Standard | Check if... |
|----------|-------------|
| `testing.md` | Any test file was added or modified |
| `error-handling.md` | Any exception handling exists in changed code |
| `logging.md` | Any module-level state reporting was added |
| `security.md` | File paths, external data, or user input is handled |
| `interface-modules.md` | Any `.js`, `.html`, or `manifest.json` file under `src/salus/viewer/static/` or `modules/` was changed |

Document any violations with file and line number.

### Phase 3 — L2 Agent Review (MANDATORY)

Invoke each applicable agent using the Agent tool with `subagent_type: "general-purpose"`.

**Always run:**

1. **Silent Failure Hunter** — Read `.claude/agents/silent-failure-hunter.md`, use its instructions as the agent prompt, pass the full content of every changed Python file.

2. **Spec Compliance** — Read `.claude/agents/spec-compliance.md`, pass the task's acceptance criteria from ProjectPath.md and the full diff.

**Run if applicable:**

3. **Type Design Analyzer** — Read `.claude/agents/type-design-analyzer.md` if type annotations were added or changed.

4. **Regression Reviewer** — Read `.claude/agents/regression-reviewer.md` if modifying previously working code (not new modules).

5. **Module Architecture Reviewer** — Read `.claude/agents/module-architecture-reviewer.md`
   if any `.js`, `.html`, or `manifest.json` files under `src/salus/viewer/static/`
   or `modules/` were changed. Pass the full content of every changed JS/HTML/manifest
   file and any associated `manifest.json` files for context.

Collect each agent's JSON output. Note findings count and severity.

### Phase 4 — Defect Logging

For every Critical/High/Medium finding from L1 or L2:

1. Assign the next D-NNN ID from `.forge/defect-register.yaml`
2. Write the defect entry with status: open
3. STOP — do not fix anything yet

All defects must be logged before any remediation begins.

### Phase 5 — Remediation

Fix Critical and High findings.
Address Medium findings unless a documented deferral reason exists.
Update each defect entry to status: resolved with commit hash.

### Phase 6 — Re-run Gates

Re-run G1–G8 after any code changes during remediation.

### Phase 7 — Gate-Proof

Write `.forge/gate-proofs/{task_id}.yaml`:

```yaml
task_id: S##-##
timestamp: 2026-03-29T14:30:00Z
quality_gates:
  G1_lint: pass
  G2_format: pass
  G3_import: pass
  G4_type: pass
  G5_security: pass
  G6_unit_test: pass
  G7_coverage: pass
  G8_secrets: N/A
  coverage_pct: 84
review:
  l1_standards:
    testing: pass
    error_handling: pass
    logging: N/A
    security: pass
    interface_modules: N/A    # set to pass/fail if JS files changed; N/A otherwise
  l2_agents:
    silent_failure_hunter: {status: pass, findings: 0}
    spec_compliance: {status: pass, findings: 1}
    type_design_analyzer: N/A
    regression_reviewer: N/A
    module_architecture_reviewer: N/A    # set to pass/fail/findings if JS files changed; N/A otherwise
defect_ids: [D-001]
overall: pass
```

Only set `overall: pass` when:
- All applicable gates pass
- All Critical/High defects are resolved
- Medium defects are tracked (resolved or deferred with reason)

## Escape Hatch

If genuinely blocked by a gate you cannot resolve, use:
```
SALUS_SKIP_REVIEW=true git commit -m "..."
```
This must be documented in `.forge/defect-register.yaml` as an open defect with reason.
Escape hatches must be resolved before the next phase is complete.
