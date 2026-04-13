# Project Salus — Claude Code Instructions

## Project Context

Project Salus is a Python cUAS (counter-Unmanned Aerial Systems) site coverage simulation tool. It computes sensor viewsheds over terrain, evaluates sensor network coverage, and produces PDF reports for defence proposals.

**Stack:** Python 3.11+, GDAL/rasterio, NumPy, Pydantic v2, Click, Matplotlib, ReportLab
**Layout:** `src/salus/` (source), `tests/` (pytest), `.forge/` (quality tracking)

---

## Mandatory Task Workflow

**Every task follows this exact sequence. No steps may be skipped. No exceptions.**

```
 1. Read spec      → Read the task's acceptance criteria from docs/ProjectPath.md
 2. Implement      → Write code that satisfies those criteria exactly — no more, no less
 3. Run tests      → pytest tests/ -v (all must pass)
 4. Quality gates  → Run ALL 8 gates below (G1–G8), record each result
 5. L1 review      → Self-review against .salus/standards/ (testing, error-handling, logging, security)
 6. L2 review      → Invoke specialist review agents (see Agent Review section)
 7. Log defects    → Write ALL Critical/High/Medium findings to .forge/defect-register.yaml BEFORE fixing
 8. Fix findings   → Remediate all Critical/High/Medium defects
 9. Update defects → Mark resolved with commit hash in .forge/defect-register.yaml
10. Re-run gates   → If fixes were made, re-run G1–G8
11. Gate-proof     → Write .forge/gate-proofs/{task_id}.yaml (see Gate-Proof format)
12. Commit         → git commit with conventional commit message
```

**You MUST NOT mark a task complete without:**
- All 8 gates passing (or explicitly documented as N/A with reason)
- L1 and L2 reviews completed
- Gate-proof YAML written
- Defect register updated

---

## Quality Gates (G1–G8)

Run these in order. Record pass/fail for each.

| Gate | Command |
|------|---------|
| G1 Lint | `ruff check src/ tests/` |
| G2 Format | `ruff format --check src/ tests/` |
| G3 Import order | `ruff check --select I src/` |
| G4 Type check | `mypy src/salus/` |
| G5 Security scan | `python -m bandit -r src/ -ll -q` |
| G6 Unit tests | `pytest tests/ -v` |
| G7 Coverage | `pytest tests/ --cov=src/salus --cov-fail-under=80 -q` |
| G8 Secret scan | `detect-secrets scan src/` (if installed; else document N/A) |

If a gate command is not yet installed, document it as `N/A — not installed` in the gate-proof.
G4 (mypy) and G5 (bandit) warnings are informational unless they indicate clear correctness errors.

**JS-only tasks:** G1–G7 are Python-specific. If the task touches only `.js`,
`.html`, or `manifest.json` files under `src/salus/viewer/static/` or
`modules/` and no Python files changed, record G1–G7 as `N/A — JS-only task`.

---

## Agent Review (L2 — MANDATORY)

After quality gates pass, you MUST invoke these agents as Claude Code subagents using the Agent tool. Do not summarise, skip, or abbreviate this step.

### Required on every task:
- **`.claude/agents/silent-failure-hunter.md`** — Hunt swallowed exceptions, unchecked returns, missing guards

### Required on every task that introduces or modifies Python modules:
- **`.claude/agents/spec-compliance.md`** — Verify implementation matches acceptance criteria exactly

### Required when type annotations are added or modified:
- **`.claude/agents/type-design-analyzer.md`** — Check annotation completeness, Any abuse, interface design

### Required when modifying existing working code (not new modules):
- **`.claude/agents/regression-reviewer.md`** — Check for regressions, behaviour changes, removed tests

### Required when any `.js`, `.html`, or `manifest.json` file under `src/salus/viewer/static/` or `modules/` changed:
- **`.claude/agents/module-architecture-reviewer.md`** — Verify module isolation, state contracts, reactive read patterns (`watch()` not `get()` after `set()`), event contracts, and map layer scoping. Pass the full content of every changed JS/HTML/manifest file plus any associated `manifest.json` files.

**How to invoke:** Use the Agent tool with `subagent_type: "general-purpose"` and the agent's full system prompt as context, passing the changed files' content. Record how many findings each agent returned.

---

## Gate-Proof Format

Write this file to `.forge/gate-proofs/{task_id}.yaml` before committing:

```yaml
task_id: S##-##          # e.g. S1-3 (Slice 1, task 3)
timestamp: ISO8601        # e.g. 2026-03-29T14:30:00Z
quality_gates:
  G1_lint: pass           # pass | fail | N/A
  G2_format: pass
  G3_import: pass
  G4_type: pass
  G5_security: pass
  G6_unit_test: pass
  G7_coverage: pass       # include coverage_pct
  G8_secrets: N/A
  coverage_pct: 84
review:
  l1_standards:
    testing: pass
    error_handling: pass
    logging: pass
    security: pass
    interface_modules: N/A  # pass | fail | N/A — N/A if no JS/HTML/manifest files changed
  l2_agents:
    silent_failure_hunter: {status: pass, findings: 0}
    spec_compliance: {status: pass, findings: 1}
    type_design_analyzer: N/A
    regression_reviewer: N/A
    module_architecture_reviewer: N/A  # pass | fail | N/A — N/A if no JS/HTML/manifest files changed
defect_ids: []            # D-NNN IDs of findings logged and resolved
overall: pass
```

---

## Defect Register

Location: `.forge/defect-register.yaml`

**Log BEFORE fixing.** Format:

```yaml
- id: D-001
  severity: critical | high | medium
  task: S##-##
  found_by: agent_name | gate_name
  file: path/to/file.py
  line: 42
  description: "What the finding is"
  resolution: ""
  status: open
  commit: ""
```

After fixing:
```yaml
  resolution: "Added None guard at line 42"
  status: resolved
  commit: abc1234
```

---

## Standards

Apply these standards when writing and reviewing code. Full definitions in `.salus/standards/`.

| Standard | When it applies |
|----------|----------------|
| `testing.md` | Any test file, conftest, or pytest fixture |
| `error-handling.md` | Any exception handling, file I/O, external calls |
| `logging.md` | Any module that reports state or errors |
| `security.md` | Any file I/O, path handling, user input, external data |
| `interface-modules.md` | Any `.js`, `.html`, or `manifest.json` file under `src/salus/viewer/static/` or `modules/` |

---

## Rules

- **ONE task per session.** Do not batch multiple tasks.
- **Read before writing.** Read every file you will modify before modifying it.
- **No scope creep.** Only implement what the acceptance criteria require.
- **No skipping reviews.** L1 and L2 reviews catch real bugs every time. They are not optional and are not a formality.
- **Log defects before fixing.** The register is the audit trail. A finding that is fixed without being logged did not happen officially.
- **Gate-proof is the exit condition.** If you cannot write a passing gate-proof, the task is not done.
- **Conventional commits.** Format: `type(scope): description` — e.g. `feat(viewshed): add max_range clipping`
- **Commit message method.** Always write multi-line commit messages to `/tmp/salus_commit_msg.txt` using the Write tool, then run `git commit -F /tmp/salus_commit_msg.txt`. Never use heredoc (`<<'EOF'`) in git commit commands — it triggers Claude Code's security scanner.
- **No magic numbers.** Extract named constants for any numeric threshold used in simulation logic.
- **Type-annotate everything.** Every function must have complete type annotations on parameters and return values.

---

## Project Structure

```
src/salus/
  cli.py          — Click entry point
  models/         — Pydantic data models (SiteModel, SensorModel, etc.)
  ingest/         — Data ingestion (terrain.py, sensors.py)
  engine/         — Simulation engine (viewshed.py, coverage.py, optimizer.py)
  report/         — Report generation (maps.py, pdf.py)
  viewer/         — Interactive viewer (future)
tests/
  conftest.py     — Shared fixtures (flat_dem_path, ridge_dem_path)
  test_terrain.py
  test_viewshed.py
  ...
.forge/
  defect-register.yaml
  gate-proofs/
.salus/
  standards/
.claude/
  commands/       — Skills (salus-execute, salus-review)
  agents/         — Specialist review agents
```

---

## Slice Reference (docs/ProjectPath.md shorthand)

Tasks are identified as `S{slice}-{index}` matching docs/ProjectPath.md:
- S1 = Slice 1: Core Pipeline
- S2 = Slice 2: Sensor Models
- etc.
