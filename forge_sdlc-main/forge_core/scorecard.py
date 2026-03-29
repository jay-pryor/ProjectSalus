"""Autonomy KPI scorecard from telemetry and audit data.

v1.0.0 improvements:
- Per-project scoring support
"""
from pathlib import Path

from forge_core.audit import AuditLog
from forge_core.log import safe_log
from forge_core.telemetry import Telemetry, compute_gate_pass_rate


class Scorecard:
    def __init__(self, project_dir: Path):
        self._project_dir = project_dir
        self._telemetry = Telemetry(project_dir)
        self._audit = AuditLog(project_dir)

    def generate(self, config: dict | None = None) -> dict:
        all_events = self._telemetry.read_all()
        gate_events = [e for e in all_events if e.get("type") == "gate"]
        task_events = [e for e in all_events if e.get("type") == "task"]

        gate_pass_rate = compute_gate_pass_rate(gate_events)
        audit_result = self._audit.verify_chain()
        audit_events = self._audit.read_all()

        unique_tasks = set(e["task_id"] for e in task_events if "task_id" in e)
        completed = set(e["task_id"] for e in task_events if e.get("action") == "complete" and "task_id" in e)
        total = len(unique_tasks)
        autonomous_completion_rate = len(completed) / total if total > 0 else 1.0

        overrides = [e for e in audit_events if e.get("category") == "override"]
        total_ops = len([e for e in audit_events if e.get("category") == "state"])
        human_intervention_rate = len(overrides) / total_ops if total_ops > 0 else 0

        rework = [e for e in audit_events if e.get("action") == "task.start" and e.get("data", {}).get("from_status") == "failed"]
        rework_rate = len(rework) / max(total, 1)

        mttr_s = self._calculate_mttr(gate_events)

        escaped = [e for e in audit_events if e.get("action") == "task.start" and e.get("data", {}).get("from_status") == "completed"]
        escaped_defect_rate = len(escaped) / max(total, 1)

        scorecard = {
            "autonomous_completion_rate": round(autonomous_completion_rate, 3),
            "human_intervention_rate": round(human_intervention_rate, 3),
            "rework_rate": round(rework_rate, 3),
            "mean_time_to_recovery_s": round(mttr_s, 1),
            "escaped_defect_rate": round(escaped_defect_rate, 3),
            "gate_pass_rate": round(gate_pass_rate, 3) if gate_pass_rate is not None else None,
            "total_tasks": total,
            "total_overrides": len(overrides),
            "audit_valid": audit_result.get("valid", False),
        }

        thresholds = (config or {}).get("scorecard_thresholds", {})
        violations = []
        for kpi, value in scorecard.items():
            if kpi in thresholds and isinstance(value, (int, float)):
                threshold = thresholds[kpi]
                if not isinstance(threshold, (int, float)):
                    continue
                high_is_good = kpi in ("autonomous_completion_rate", "gate_pass_rate")
                if high_is_good and value < threshold:
                    violations.append({"kpi": kpi, "actual": value, "threshold": threshold, "direction": "below minimum"})
                elif not high_is_good and value > threshold:
                    violations.append({"kpi": kpi, "actual": value, "threshold": threshold, "direction": "above maximum"})

        scorecard["violations"] = violations
        scorecard["release_ready"] = len(violations) == 0
        return scorecard

    def _calculate_mttr(self, gate_events: list[dict]) -> float:
        by_gate: dict[str, list[dict]] = {}
        for e in gate_events:
            gid = e.get("gate_id")
            if gid:
                by_gate.setdefault(gid, []).append(e)
        recovery_times: list[float] = []
        for events in by_gate.values():
            events.sort(key=lambda e: e.get("ts", 0))
            last_failure_ts: float | None = None
            for event in events:
                if not event.get("passed") and last_failure_ts is None:
                    last_failure_ts = event.get("ts", 0)
                elif event.get("passed") and last_failure_ts is not None:
                    rt = event.get("ts", 0) - last_failure_ts
                    if rt > 0:
                        recovery_times.append(rt)
                    elif rt < 0:
                        safe_log("mttr_negative_recovery_time", level="warning", recovery_time=rt)
                    last_failure_ts = None
        return sum(recovery_times) / len(recovery_times) if recovery_times else 0
