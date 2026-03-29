---
name: forge-status
description: Dashboard — current phase, task states, gate-proof coverage, blockers, recent audit entries.
---

# Forge Status Skill

Display current project status dashboard.

## Information Gathered

1. **Session:** `forge session status`
2. **Tracker:** `forge tracker status`
3. **Health:** `forge health check`
4. **Gate-proof coverage:** Count proofs vs tasks
5. **Recent audit:** Last 5 entries from `.forge/log.md`

## Output Format

```
=== Forge Status ===
Session: active (agent: claude, started: HH:MM)
Phase: P03 — Forge v1.0.0
  Tasks: 5/17 complete, 1 in-progress, 2 blocked
  Gate-proofs: 5/5 (100% coverage)
  Blockers: T08 — waiting for hookify dep
Health: PASS (8/8 checks)
Next action: Execute T06 (parallel group 2)
```

## Recommended Next Action

Based on:
- Task dependency DAG
- Current blocked tasks
- Parallel group assignments
