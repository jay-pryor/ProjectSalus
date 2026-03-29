---
name: forge-complete
description: Mark task/phase complete. Validates gate-proofs, runs cross-checks, updates state machine.
---

# Forge Complete Skill

Mark a task or phase as complete after validation.

## Pre-completion Checklist

1. **Gate-proofs:** Verify `.forge/gate-proofs/{task_id}.yaml` exists with `overall: pass`
2. **Evidence:** Run `forge evidence verify --phase PHASE_ID`
3. **Standards:** Run `forge check standards` on all modified files
4. **Cross-cutting:** Run `forge check cross-cutting`
5. **Tests:** All tests pass (`pytest -x -q`)

## Task Completion

```bash
forge tracker complete TASK_ID --validation "all-gates-passed"
```

## Phase Completion

Only after ALL tasks in phase are complete:

```bash
forge phase complete PHASE_ID
```

## Blocking Conditions

This skill REFUSES to complete if:
- Gate-proofs are missing for any task
- Gate-proof overall status is not "pass"
- Evidence verification fails
- Standards check has "must" violations

Use escape hatch only when genuinely blocked.
