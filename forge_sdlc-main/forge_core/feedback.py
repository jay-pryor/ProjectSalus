"""Forge feedback engine — aggregates data into structured feedback.

v1.0.0 improvements:
- Feedback categorisation (bug, enhancement, process)
"""

import os
from collections import defaultdict
from pathlib import Path

from forge_core.audit import AuditLog
from forge_core.defect_ledger import DefectLedger
from forge_core.telemetry import Telemetry


class FeedbackEngine:
    def __init__(self, project_dir: Path | None = None) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir)
        else:
            env_dir = os.environ.get("FORGE_PROJECT_DIR")
            self._project_dir = Path(env_dir) if env_dir else Path.cwd()
        self._telemetry = Telemetry(self._project_dir)
        self._audit = AuditLog(self._project_dir)

    def generate(self) -> dict:
        all_events = self._telemetry.read_all()
        gate_events = [e for e in all_events if e.get("type") == "gate"]
        task_events = [e for e in all_events if e.get("type") == "task"]

        # Gate patterns
        gate_patterns: dict[str, dict] = {}
        for e in gate_events:
            gid = e.get("gate_id", "unknown")
            pat = gate_patterns.setdefault(gid, {"pass": 0, "fail": 0, "total_ms": 0, "attempts": 0})
            pat["pass" if e.get("passed") else "fail"] += 1
            pat["total_ms"] += e.get("duration_ms", 0)
            pat["attempts"] += 1

        for gid, pat in gate_patterns.items():
            total = pat["pass"] + pat["fail"]
            pat["pass_rate"] = round(pat["pass"] / total, 3) if total > 0 else 0
            pat["avg_duration_ms"] = round(pat["total_ms"] / pat["attempts"], 1) if pat["attempts"] > 0 else 0

        # Task velocity
        task_durations = [e.get("duration_ms", 0) for e in task_events if e.get("action") == "complete" and e.get("duration_ms")]
        avg_duration = round(sum(task_durations) / len(task_durations), 1) if task_durations else 0

        return {
            "success": True,
            "action": "feedback.generate",
            "gate_patterns": gate_patterns,
            "task_velocity": {
                "avg_duration_ms": avg_duration,
                "total_completed": len(task_durations),
            },
        }

    def get_planner_context(self) -> dict:
        """Returns feedback formatted for planner agent context injection."""
        feedback = self.generate()
        return {
            "gate_patterns": feedback.get("gate_patterns", {}),
            "task_velocity": feedback.get("task_velocity", {}),
        }
