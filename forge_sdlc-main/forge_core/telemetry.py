"""Operational telemetry for forge gate execution and build health."""

import time
from pathlib import Path

from forge_core.jsonl_io import append_jsonl, read_jsonl


def compute_gate_pass_rate(gate_events: list[dict]) -> float | None:
    if not gate_events:
        return None
    return sum(1 for e in gate_events if e.get("passed")) / len(gate_events)


class Telemetry:
    def __init__(self, project_dir: Path):
        self._path = project_dir / ".forge" / "telemetry.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record_gate(self, gate_id: str, phase_id: str, passed: bool, duration_ms: float, attempt: int = 1) -> None:
        self._append({"type": "gate", "gate_id": gate_id, "phase_id": phase_id, "passed": passed, "duration_ms": duration_ms, "attempt": attempt, "ts": time.time()})

    def record_task(self, task_id: str, action: str, duration_ms: float | None = None) -> None:
        self._append({"type": "task", "task_id": task_id, "action": action, "duration_ms": duration_ms, "ts": time.time()})

    def summary(self, slos: dict | None = None) -> dict:
        events = self.read_all()
        gate_events = [e for e in events if e.get("type") == "gate"]
        task_events = [e for e in events if e.get("type") == "task"]

        gate_pass_rate = compute_gate_pass_rate(gate_events)
        retry_count = sum(1 for e in gate_events if e.get("attempt", 1) > 1)

        gate_outcomes: dict[str, set[bool]] = {}
        for e in gate_events:
            gid = e.get("gate_id")
            if gid:
                gate_outcomes.setdefault(gid, set()).add(e.get("passed", False))
        flaky_gates = sorted(gid for gid, outcomes in gate_outcomes.items() if True in outcomes and False in outcomes)

        breaches: list[dict] = []
        if slos:
            min_pass_rate = slos.get("gate_pass_rate")
            if min_pass_rate is not None and gate_pass_rate is not None and gate_pass_rate < min_pass_rate:
                breaches.append({"slo": "gate_pass_rate", "threshold": min_pass_rate, "actual": round(gate_pass_rate, 3), "severity": "high"})
            max_flaky = slos.get("max_flaky_gates")
            if max_flaky is not None and len(flaky_gates) > max_flaky:
                breaches.append({"slo": "max_flaky_gates", "threshold": max_flaky, "actual": len(flaky_gates), "severity": "medium"})

        return {
            "success": len(breaches) == 0,
            "action": "telemetry.summary",
            "gate_pass_rate": round(gate_pass_rate, 3) if gate_pass_rate is not None else None,
            "total_gate_runs": len(gate_events),
            "total_task_events": len(task_events),
            "retry_count": retry_count,
            "flaky_gates": flaky_gates,
            "slo_breaches": breaches,
            "slo_status": "pass" if not breaches else "breach",
        }

    def read_all(self) -> list[dict]:
        return read_jsonl(self._path)

    def _append(self, event: dict) -> None:
        append_jsonl(self._path, event)
