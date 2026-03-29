---
name: forge-plan
description: Create phase spec from task description. Generates full template with mandatory review gates. Validates against master plan dependencies.
---

# Forge Plan Skill

Create a new phase specification for a Forge-managed project.

## Steps

1. Read the master plan to understand phase dependencies
2. Gather requirements: objective, scope, acceptance criteria
3. Generate phase spec using the standard template:
   - Objective
   - Scope (in/out)
   - Invariants
   - File map
   - Task dependency DAG
   - Tasks with acceptance criteria (including review mandate)
   - Phase Gate Review task (T_REVIEW) — MANDATORY
   - Risk register
4. Validate: `forge phase plan-gate PHASE_ID`
5. Save to `phases/PHASE_ID.md`

## Template Structure

Each implementation task in the phase must have:
- Objective (one sentence)
- Scope (files affected)
- Acceptance criteria (checkbox list)
- **Review Gate line** (mandatory — see below)
- Test plan
- Standards applicable
- Parallel group assignment

### Review Gate Line (MANDATORY per task)

Every implementation task MUST include this line before the Test Plan:

```
**Review Gate:** Per forge policy — L1 static analysis + L2 CC plugin review required. All Critical/High/Medium findings logged in `.forge/defect-register.yaml` and resolved before task completion.
```

This is NOT optional. It is part of the task acceptance criteria. A task without this line fails plan-gate validation.

### Phase Gate Review Task (T_REVIEW) — MANDATORY

Every phase spec MUST end with a T_REVIEW task. This task:

1. **Audits prior task evidence** — verifies every task has a valid gate-proof and evidence file
2. **Runs L3 specialist agent panel** — 4 subagents with specific types
3. **Logs all findings as defects** — in `.forge/defect-register.yaml` before remediation
4. **Writes phase gate-proof** — with `gate_type: pr`

Template for T_REVIEW:

```markdown
### PHASE_ID.T_REVIEW — Phase Gate Review (PR Gate)
**Objective:** Verify all tasks were properly reviewed, then run full L3 specialist panel.
**This task CANNOT be skipped. It is a hard dependency for phase completion.**

**Step 1 — Verify Prior Task Evidence:**
- [ ] For EVERY task: gate-proof exists with quality_gates + review sections
- [ ] For EVERY task: evidence file exists with completed AC checklist
- [ ] All defects from task reviews are in `.forge/defect-register.yaml`
- [ ] If ANY task is missing evidence, STOP and complete that task first

**Step 2 — Run L3 Specialist Agent Panel (all 4 required):**
- [ ] forge_spec_compliance — `superpowers:code-reviewer` subagent
- [ ] forge_silent_failure_hunter — `pr-review-toolkit:silent-failure-hunter` subagent
- [ ] forge_code_simplifier — `code-simplifier:code-simplifier` subagent
- [ ] forge_regression_reviewer — `pr-review-toolkit:code-reviewer` subagent

**Step 3 — Log and Resolve Findings:**
- [ ] ALL Critical/High/Medium findings logged in defect register with D-### IDs
- [ ] ALL defects resolved with commit hash
- [ ] Gates re-run after fixes

**Step 4 — Write Phase Gate Proof:**
- [ ] `.forge/gate-proofs/PHASE_ID.phase.yaml` with gate_type: pr
- [ ] `evidence/PHASE_ID.phase.md`
```

A phase spec without T_REVIEW fails plan-gate validation.

## Validation

Run `forge phase plan-gate PHASE_ID` to validate:
- All tasks have review gate lines
- T_REVIEW task exists as final task
- Task dependency DAG is valid
- Objective and scope are defined
