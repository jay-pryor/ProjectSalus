---
name: forge-execute
description: Execute task within phase. Reads spec, implements, runs gates, runs reviews, logs defects, stages evidence.
---

# Forge Execute Skill

Execute a task within a Forge-managed phase.

## Mandatory Sequence (ALL steps required — no skipping)

```
 1. Read spec     → Read phase spec, identify task's acceptance criteria
 2. Start task    → forge tracker start TASK_ID
 3. Implement     → Write code following acceptance criteria exactly
 4. Test          → Run ALL tests (unit + integration for changed modules)
 5. Quality gates → Run ALL 8 gates (G1-G8), record results
 6. Evidence stub → forge evidence create TASK_ID "description"
 6b. Pending CR  → Check .forge/pending-coderabbit-findings.json:
                    If non-empty, log each finding to .forge/defect-register.yaml
                    with next D-### ID, found_by: coderabbit-pending.
                    Clear the file after ingestion.
                    These are treated as pre-existing defects for step 9-10.
 7. L1 review     → forge check standards + forge check cross-cutting
 8. L2 review     → Invoke CC plugin subagent(s) on changed files:
                     - pr-review-toolkit:silent-failure-hunter (ALWAYS)
                     - Plus 1-2 relevant: coderabbit:code-review, code-simplifier:code-simplifier
 9. Log defects   → Add ALL Critical/High/Medium findings to .forge/defect-register.yaml
                     with next D-### ID, severity, file, description. Status: open.
                     DO THIS BEFORE FIXING ANYTHING.
10. Fix findings  → Remediate all Critical/High/Medium defects
11. Update defects→ Set status: resolved with commit hash in defect register
12. Re-run gates  → If fixes were made, re-run G1-G8
13. Gate-proof    → Write .forge/gate-proofs/{task_id}.yaml with:
                     - quality_gates section (G1-G8 results)
                     - review.l1_static section (forge check results)
                     - review.l2_plugins section (tools_used list, findings_count)
                     - defect_ids (list of D-### IDs found/resolved)
                     - overall: pass
14. Evidence      → Write evidence/{task_id}.md with completed AC checklist
15. Complete      → forge tracker complete TASK_ID --validation gate-proof
```

## Rules

- Read the spec BEFORE writing code
- NEVER skip the review steps (7-8). These catch real bugs every time.
- NEVER mark a task complete without gate-proof
- NEVER fix a finding without logging it as a defect first (step 9 before step 10)
- Evidence must be captured DURING implementation, not after
- If blocked: `forge tracker block TASK_ID --reason "..."`
- Commit with conventional commit format
- ONE task per session. Do not batch multiple tasks.
- ALWAYS check .forge/pending-coderabbit-findings.json before reviews. These are CodeRabbit findings from async PR comments that must be addressed.

## Quality Gates (Standard Profile — all 8 required)

| Gate | Command |
|------|---------|
| G1 Lint | `ruff check src/ tests/` |
| G2 Format | `ruff format --check src/ tests/` |
| G3 Import | `ruff check --select I src/` |
| G4 Type | `mypy src/MODULE` |
| G5 Security | `semgrep scan --config=auto src/` + `detect-secrets scan src/` |
| G6 Unit Test | `pytest tests/unit/ -v` |
| G7 Integration | `pytest tests/integration/ -v` |
| G8 Coverage | `pytest tests/ --cov=src/MODULE --cov-fail-under=80` |

## Defect Register

Location: `.forge/defect-register.yaml`

Every review finding at Critical/High/Medium severity MUST be logged here BEFORE remediation:

```yaml
- id: D-NNN
  severity: critical|high|medium
  phase: S##.P##
  found_by: agent_name
  file: path/to/file.py
  description: "What the finding is"
  resolution: ""
  status: open
  commit: ""
```

After fixing, update to `status: resolved` with commit hash.
