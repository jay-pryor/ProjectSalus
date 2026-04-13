Execute a Salus task end-to-end following the mandatory quality workflow.

Usage: /salus-execute <task_id>
Example: /salus-execute S1-3

## What this skill does

Runs the complete 12-step task lifecycle for Project Salus. Every step is mandatory.

## Step-by-step execution

**Step 1 — Read spec**
Read the task's acceptance criteria from ProjectPath.md. Identify exactly what must be true when the task is done. Write it out explicitly before touching any code.

**Step 2 — Implement**
Write code that satisfies the acceptance criteria. No more than required. Read every file before modifying it.

**Step 3 — Run all tests**
```bash
pytest tests/ -v
```
All tests must pass before proceeding.

**Step 4 — Quality gates (G1–G8)**
Run each gate in sequence and record the result. Do not proceed past a failing Critical gate.

```bash
ruff check src/ tests/                                    # G1 Lint
ruff format --check src/ tests/                           # G2 Format
ruff check --select I src/                                # G3 Import order
mypy src/salus/                                           # G4 Type check
python -m bandit -r src/ -ll -q                           # G5 Security
pytest tests/ -v                                          # G6 Unit tests
pytest tests/ --cov=src/salus --cov-fail-under=80 -q      # G7 Coverage
```

G1–G7 apply to Python files only. If the task touches only `.js`, `.html`, or
`manifest.json` files under `src/salus/viewer/static/` or `modules/` and no
Python files changed, record G1–G7 as N/A with reason "JS-only task".

**Step 5 — L1 Self-review**
Read `.salus/standards/` and check the changed files against each applicable standard:
- `testing.md` — if test files changed
- `error-handling.md` — if exception handling changed
- `logging.md` — if any logging added
- `security.md` — if file I/O or external data handling changed
- `interface-modules.md` — if any `.js`, `.html`, or `manifest.json` files
  under `src/salus/viewer/static/` or `modules/` changed

Document any violations found.

**Step 6 — L2 Agent review (MANDATORY — DO NOT SKIP)**
Invoke the following agents using the Agent tool. Pass the changed file contents and acceptance criteria as context.

Always invoke:
- `.claude/agents/silent-failure-hunter.md`
- `.claude/agents/spec-compliance.md`

Also invoke if applicable:
- `.claude/agents/type-design-analyzer.md` — if type annotations changed
- `.claude/agents/regression-reviewer.md` — if modifying existing working code
- `.claude/agents/module-architecture-reviewer.md` — if any `.js`, `.html`,
  or `manifest.json` files under `src/salus/viewer/static/` or `modules/`
  changed. Pass the full content of every changed JS/HTML/manifest file and
  the content of any associated `manifest.json` files for context.

Record each agent's findings count.

**Step 7 — Log defects (BEFORE fixing)**
Write ALL Critical/High/Medium findings to `.forge/defect-register.yaml` with status: open.
Do this BEFORE fixing anything.

**Step 8 — Fix findings**
Remediate all Critical and High findings. Address Medium findings unless there is a documented reason not to.

**Step 9 — Update defect register**
Set status: resolved and add commit hash for each fixed finding.

**Step 10 — Re-run gates**
If any code was changed during fixing, re-run G1–G8.

**Step 11 — Write gate-proof**
Write `.forge/gate-proofs/{task_id}.yaml` with all gate results and agent findings. See CLAUDE.md for format.

**Step 12 — Commit**
```bash
git add -p  # stage only relevant changes
git commit -m "type(scope): description"
```

## Rules

- You MUST NOT skip Steps 5 and 6. These are not a formality.
- You MUST write the gate-proof before committing.
- You MUST log defects before fixing them.
- If a gate fails and cannot be resolved: document the blocker and stop — do not work around it.
