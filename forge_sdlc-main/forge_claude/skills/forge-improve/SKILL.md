---
name: forge-improve
description: Weekly improvement cycle. Analyses escape-hatch usage, review agent effectiveness, hook failure patterns.
---

# Forge Improve Skill

Run weekly improvement analysis on the Forge workflow.

## Analysis Areas

1. **Escape hatch usage:** Count gate-proofs with `escape_hatch: true`, reasons
2. **Review agent effectiveness:** Which agents find the most issues? False positive rates?
3. **Hook failure patterns:** Which hooks block most often? Are they catching real issues?
4. **Gate timing:** Average time per gate, bottlenecks
5. **Defect recurrence:** Repeated defects in same files/categories

## Data Sources

- `.forge/gate-proofs/*.yaml` — review results
- `.forge/audit.jsonl` — audit trail
- `.forge/defect_ledger.jsonl` — defect history
- `.forge/telemetry.jsonl` — timing data

## Output

Generate improvement report with:
- Metrics summary
- Top 3 actionable improvements
- Standards that may need updating
- Agents that may need prompt tuning

Save to `evidence/forge_improvement_YYYYMMDD.md`
