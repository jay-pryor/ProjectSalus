# Forge Workflow Rules

## Task Lifecycle

Every task MUST follow this sequence. NO STEPS MAY BE SKIPPED.

```
 1. Read spec      → Read phase spec, identify acceptance criteria
 2. Start task     → forge tracker start TASK_ID
 3. Implement      → Write code following acceptance criteria
 4. Test           → Run ALL tests (unit + integration)
 5. Quality gates  → Run ALL 8 gates (G1-G8)
 6. Evidence stub  → forge evidence create TASK_ID "description"
 7. L1 review      → forge check standards + forge check cross-cutting
 8. L2 review      → Invoke CC plugin subagent(s) — forge-silent-failure-hunter ALWAYS required
 9. Log defects    → Add findings to .forge/defect-register.yaml BEFORE fixing
10. Fix findings   → Remediate Critical/High/Medium defects
11. Update defects → Set status: resolved in defect register
12. Re-run gates   → If fixes made, re-run G1-G8
13. Gate-proof     → Write .forge/gate-proofs/{task_id}.yaml with actual results
14. Evidence       → Write evidence/{task_id}.md with completed AC checklist
15. Complete       → forge tracker complete TASK_ID --validation gate-proof
```

## Rules

- NEVER skip steps in the lifecycle — especially steps 7-9 (reviews + defect logging)
- NEVER mark a task complete without gate-proof
- NEVER fix a finding without logging it as a defect first (step 9 before step 10)
- ALWAYS read the spec before writing code
- ALWAYS run tests before review
- ONE task at a time — do not batch multiple tasks
- If blocked: `forge tracker block TASK_ID --reason "..."`
- If skipping: `forge tracker skip TASK_ID --reason "..."` (requires justification)

## Phase Completion

Every phase has a T_REVIEW task that MUST be completed last:
1. Audits evidence trail of all tasks in the phase
2. Runs L3 specialist agent panel (4 subagents)
3. Logs all findings as defects
4. Writes phase gate-proof with gate_type: pr
A phase CANNOT be marked COMPLETED without T_REVIEW done.

## Quality Gates

Standard profile: All 8 gates required.

| Gate | Command |
|------|---------|
| G1 Lint | `ruff check src/ tests/` |
| G2 Format | `ruff format --check src/ tests/` |
| G3 Import | `ruff check --select I src/` |
| G4 Type | `mypy src/MODULE` |
| G5 Security | `semgrep scan --config=auto src/` |
| G6 Unit Test | `pytest tests/unit/ -v` |
| G7 Integration | `pytest tests/integration/ -v` |
| G8 Coverage | `pytest tests/ --cov --cov-fail-under=80` |

## Defect Register

Location: `.forge/defect-register.yaml`
Every Critical/High/Medium finding → logged here BEFORE remediation.
Gate-proof must reference defect IDs.

## Commit Convention

Format: `type(scope): description`
Types: feat, fix, refactor, test, docs, chore
