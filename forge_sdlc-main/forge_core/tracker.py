"""Forge task tracker — YAML-backed task lifecycle management.

v1.0.0 improvements:
- Dependency graph validation (detect circular deps in task DAGs)
- Uses new skipped/reopened states from state machine
"""

import glob
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from forge_core.state_machine import TaskStatus, validate_task_transition
from forge_core.utils import PHASE_ID_PATTERN, TASK_ID_PATTERN, to_snake_case
from forge_core.yaml_io import atomic_save, locked_update, safe_load


def parse_task_id(task_id: str) -> dict:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError(f"Invalid task ID '{task_id}': expected format S##.P##.T##")
    parts = task_id.split(".")
    return {"section": parts[0], "phase": parts[1], "task": parts[2]}


class TaskTracker:
    def __init__(self, project_dir: Path | None = None) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir)
        else:
            env_dir = os.environ.get("FORGE_PROJECT_DIR")
            self._project_dir = Path(env_dir) if env_dir else Path.cwd()
        self._store_dir = self._project_dir / ".forge"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self._store_dir / "tracker.yaml"

    _TRACKER_DEFAULTS: dict = {
        "schema_version": "1.0.0",
        "last_updated": None,
        "last_session": None,
        "sections": {},
    }

    def _load(self) -> dict:
        return safe_load(self._store_path, self._TRACKER_DEFAULTS)

    def _save(self, data: dict) -> None:
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        atomic_save(self._store_path, data)

    def _ensure_path(self, data: dict, parsed: dict) -> dict:
        sections = data.setdefault("sections", {})
        section = sections.setdefault(parsed["section"], {"phases": {}})
        phases = section.setdefault("phases", {})
        phase = phases.setdefault(parsed["phase"], {"tasks": {}})
        tasks = phase.setdefault("tasks", {})
        return tasks.setdefault(parsed["task"], {})

    def _get_task(self, data: dict, parsed: dict) -> dict | None:
        return (
            data.get("sections", {})
            .get(parsed["section"], {})
            .get("phases", {})
            .get(parsed["phase"], {})
            .get("tasks", {})
            .get(parsed["task"])
        )

    def start_task(self, task_id: str, name: str = "") -> dict:
        parsed = parse_task_id(task_id)
        result_holder: list[dict] = []

        def _updater(data: dict) -> dict:
            task = self._ensure_path(data, parsed)
            current_status = task.get("status", TaskStatus.NOT_STARTED.value)

            if current_status == TaskStatus.IN_PROGRESS.value:
                result_holder.append({
                    "success": True, "action": "tracker.start",
                    "task_id": task_id, "status": TaskStatus.IN_PROGRESS.value,
                    "warning": "Task already in_progress",
                })
                return data

            transition = validate_task_transition(current_status, TaskStatus.IN_PROGRESS.value)
            if not transition.valid:
                result_holder.append({"success": False, "action": "tracker.start", "task_id": task_id, "error": transition.message})
                return data

            task["status"] = TaskStatus.IN_PROGRESS.value
            task["started_at"] = datetime.now(timezone.utc).isoformat()
            if name:
                task["name"] = name
            result_holder.append({"success": True, "action": "tracker.start", "task_id": task_id, "status": TaskStatus.IN_PROGRESS.value})
            return data

        locked_update(self._store_path, self._TRACKER_DEFAULTS, _updater)
        return result_holder[0]

    _REQUIRED_GATES = {"G1", "G4", "G6"}
    _EVIDENCE_MARKERS = {"PASS", "FAIL", "pass", "fail", "assert", "error:", "warning:"}
    _MIN_EVIDENCE_LINES = 10
    _MIN_ESCAPE_REASON_LEN = 20

    def _validate_completion(self, task_id: str) -> list[str]:
        """Validate that gate-proof and evidence artifacts exist and are sufficient.

        Returns a list of error strings. Empty list means validation passed.
        """
        errors: list[str] = []

        # --- Gate-proof validation ---
        proof_path = self._store_dir / "gate-proofs" / f"{task_id}.yaml"
        if not proof_path.exists():
            errors.append(f"Gate-proof file missing: {proof_path}")
            # No point checking contents if file is missing
        else:
            proof = safe_load(proof_path, {})
            escape = proof.get("escape_hatch", False)

            if escape:
                reason = proof.get("escape_reason", "")
                if len(reason) < self._MIN_ESCAPE_REASON_LEN:
                    errors.append(
                        f"escape_reason must be >= {self._MIN_ESCAPE_REASON_LEN} chars, got {len(reason)}"
                    )
            else:
                # Must have required gates
                recorded_gates = {g.get("gate_id") for g in proof.get("gates", []) if isinstance(g, dict)}
                missing = self._REQUIRED_GATES - recorded_gates
                if missing:
                    errors.append(f"Missing required quality gates: {sorted(missing)}")

                # Must have non-empty reviews
                reviews = proof.get("reviews", {})
                if not reviews:
                    errors.append("Gate-proof has no reviews recorded")

                # Overall must be pass
                if proof.get("overall") != "pass":
                    errors.append(
                        f"Gate-proof overall status is '{proof.get('overall')}', expected 'pass'"
                    )

        # --- Evidence file validation ---
        evidence_dir = self._project_dir / "evidence"
        matches = sorted(evidence_dir.glob(f"{task_id}*")) if evidence_dir.is_dir() else []
        if not matches:
            errors.append(f"No evidence file found matching evidence/{task_id}*")
        else:
            evidence_path = matches[0]
            try:
                content = evidence_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append(f"Cannot read evidence file {evidence_path}: {exc}")
                return errors

            non_empty_lines = [ln for ln in content.splitlines() if ln.strip()]
            if len(non_empty_lines) < self._MIN_EVIDENCE_LINES:
                errors.append(
                    f"Evidence file has {len(non_empty_lines)} non-empty lines, need >= {self._MIN_EVIDENCE_LINES}"
                )

            has_marker = any(marker in content for marker in self._EVIDENCE_MARKERS)
            if not has_marker:
                errors.append(
                    f"Evidence file has no verification markers (expected one of {sorted(self._EVIDENCE_MARKERS)})"
                )

        return errors

    def complete_task(self, task_id: str, validation: str = "manual") -> dict:
        parsed = parse_task_id(task_id)

        # Validate completion artifacts BEFORE acquiring the lock
        validation_errors = self._validate_completion(task_id)
        if validation_errors:
            return {
                "success": False,
                "action": "tracker.complete",
                "task_id": task_id,
                "error": "Completion blocked: artifacts failed validation",
                "validation_errors": validation_errors,
            }

        result_holder: list[dict] = []

        def _updater(data: dict) -> dict:
            task = self._get_task(data, parsed)
            if task is None:
                result_holder.append({"success": False, "action": "tracker.complete", "task_id": task_id, "error": f"Task {task_id} does not exist."})
                return data

            current_status = task.get("status", TaskStatus.NOT_STARTED.value)
            transition = validate_task_transition(current_status, TaskStatus.COMPLETED.value)
            if not transition.valid:
                result_holder.append({"success": False, "action": "tracker.complete", "task_id": task_id, "error": transition.message})
                return data

            task["status"] = TaskStatus.COMPLETED.value
            task["completed_at"] = datetime.now(timezone.utc).isoformat()
            task["validation"] = validation

            task_name = task.get("name", "")
            snake_name = to_snake_case(task_name) if task_name else ""
            task["evidence"] = f"evidence/{task_id}_{snake_name}_evidence.md" if snake_name else f"evidence/{task_id}_evidence.md"

            result_holder.append({"success": True, "action": "tracker.complete", "task_id": task_id, "status": TaskStatus.COMPLETED.value})
            return data

        locked_update(self._store_path, self._TRACKER_DEFAULTS, _updater)
        return result_holder[0]

    def complete_phase(self, phase_id: str) -> dict:
        """Complete a phase after verifying all tasks are done and defect policy is met.

        Blocks if:
        - Any tasks are not completed or skipped
        - Any open Critical or High defects exist for this phase
        - More than 3 open Medium defects exist for this phase

        Warns (but allows) if 1-3 open Medium defects exist, logging them
        to .forge/accepted-debt.yaml.
        """
        if not PHASE_ID_PATTERN.fullmatch(phase_id):
            return {
                "success": False,
                "action": "tracker.complete_phase",
                "phase_id": phase_id,
                "error": f"Invalid phase ID '{phase_id}': expected format S##.P##",
            }

        parts = phase_id.split(".")
        section_key = parts[0]
        phase_key = parts[1]

        data = self._load()

        # --- Check all tasks in this phase are completed or skipped ---
        phase_data = (
            data.get("sections", {})
            .get(section_key, {})
            .get("phases", {})
            .get(phase_key, {})
        )
        tasks = phase_data.get("tasks", {})
        if not tasks:
            return {
                "success": False,
                "action": "tracker.complete_phase",
                "phase_id": phase_id,
                "error": f"Phase {phase_id} has no tasks.",
            }

        done_statuses = {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
        incomplete = []
        for t_key, task in tasks.items():
            status = task.get("status", TaskStatus.NOT_STARTED.value)
            if status not in done_statuses:
                incomplete.append(f"{section_key}.{phase_key}.{t_key} ({status})")

        if incomplete:
            return {
                "success": False,
                "action": "tracker.complete_phase",
                "phase_id": phase_id,
                "error": f"Incomplete tasks: {', '.join(incomplete)}",
            }

        # --- Check defect register ---
        defect_path = self._store_dir / "defect-register.yaml"
        open_defects: list[dict] = []
        if defect_path.is_file():
            try:
                with open(defect_path) as f:
                    raw = yaml.safe_load(f)
            except Exception:
                raw = None

            if isinstance(raw, list):
                all_defects = raw
            elif isinstance(raw, dict):
                all_defects = raw.get("defects", [])
            else:
                all_defects = []

            for d in all_defects:
                if not isinstance(d, dict):
                    continue
                if (
                    d.get("phase") == phase_id
                    and str(d.get("status", "")).lower() == "open"
                ):
                    open_defects.append(d)

        # Count by severity
        severity_counts: dict[str, int] = {}
        for d in open_defects:
            sev = str(d.get("severity", "unknown")).lower()
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        critical_count = severity_counts.get("critical", 0)
        high_count = severity_counts.get("high", 0)
        medium_count = severity_counts.get("medium", 0)

        # Block on critical
        if critical_count > 0:
            return {
                "success": False,
                "action": "tracker.complete_phase",
                "phase_id": phase_id,
                "error": f"CRITICAL: {critical_count} open critical defect(s) block phase completion.",
            }

        # Block on high
        if high_count > 0:
            return {
                "success": False,
                "action": "tracker.complete_phase",
                "phase_id": phase_id,
                "error": f"HIGH: {high_count} open high-severity defect(s) block phase completion.",
            }

        # Block on >3 medium
        if medium_count > 3:
            return {
                "success": False,
                "action": "tracker.complete_phase",
                "phase_id": phase_id,
                "error": f"MEDIUM: {medium_count} open medium defects exceed threshold of 3.",
            }

        # Warn on 1-3 medium — log as accepted debt
        warnings: list[str] = []
        if 1 <= medium_count <= 3:
            warnings.append(
                f"{medium_count} open medium defect(s) accepted as technical debt."
            )
            debt_path = self._store_dir / "accepted-debt.yaml"
            existing_debt: list[dict] = []
            if debt_path.is_file():
                try:
                    with open(debt_path) as f:
                        raw_debt = yaml.safe_load(f)
                    if isinstance(raw_debt, list):
                        existing_debt = raw_debt
                    elif isinstance(raw_debt, dict):
                        existing_debt = raw_debt.get("entries", [])
                except Exception:
                    existing_debt = []

            medium_defects = [
                d for d in open_defects
                if str(d.get("severity", "")).lower() == "medium"
            ]
            existing_debt.append({
                "phase": phase_id,
                "accepted_at": datetime.now(timezone.utc).isoformat(),
                "defects": [
                    {"id": d.get("id"), "description": d.get("description")}
                    for d in medium_defects
                ],
            })
            atomic_save(debt_path, existing_debt)

        # --- Update phase status ---
        now = datetime.now(timezone.utc).isoformat()
        phase_data["status"] = "completed"
        phase_data["completed_at"] = now
        self._save(data)

        result: dict = {
            "success": True,
            "action": "tracker.complete_phase",
            "phase_id": phase_id,
            "status": "completed",
        }
        if warnings:
            result["warnings"] = warnings
        return result

    def block_task(self, task_id: str, reason: str) -> dict:
        parsed = parse_task_id(task_id)
        result_holder: list[dict] = []

        def _updater(data: dict) -> dict:
            task = self._get_task(data, parsed)
            if task is None:
                result_holder.append({"success": False, "action": "tracker.block", "task_id": task_id, "error": f"Task {task_id} does not exist."})
                return data

            current_status = task.get("status", TaskStatus.NOT_STARTED.value)
            transition = validate_task_transition(current_status, TaskStatus.BLOCKED.value)
            if not transition.valid:
                result_holder.append({"success": False, "action": "tracker.block", "task_id": task_id, "error": transition.message})
                return data

            task["status"] = TaskStatus.BLOCKED.value
            task["blocked_reason"] = reason
            task["blocked_at"] = datetime.now(timezone.utc).isoformat()
            result_holder.append({"success": True, "action": "tracker.block", "task_id": task_id, "reason": reason})
            return data

        locked_update(self._store_path, self._TRACKER_DEFAULTS, _updater)
        return result_holder[0]

    def skip_task(self, task_id: str, reason: str) -> dict:
        """Mark a task as skipped (v1.0.0)."""
        parsed = parse_task_id(task_id)
        result_holder: list[dict] = []

        def _updater(data: dict) -> dict:
            task = self._ensure_path(data, parsed)
            current_status = task.get("status", TaskStatus.NOT_STARTED.value)
            transition = validate_task_transition(current_status, TaskStatus.SKIPPED.value)
            if not transition.valid:
                result_holder.append({"success": False, "action": "tracker.skip", "task_id": task_id, "error": transition.message})
                return data

            task["status"] = TaskStatus.SKIPPED.value
            task["skip_reason"] = reason
            task["skipped_at"] = datetime.now(timezone.utc).isoformat()
            result_holder.append({"success": True, "action": "tracker.skip", "task_id": task_id, "reason": reason})
            return data

        locked_update(self._store_path, self._TRACKER_DEFAULTS, _updater)
        return result_holder[0]

    def reopen_task(self, task_id: str, reason: str) -> dict:
        """Reopen a completed or skipped task (v1.0.0)."""
        parsed = parse_task_id(task_id)
        result_holder: list[dict] = []

        def _updater(data: dict) -> dict:
            task = self._get_task(data, parsed)
            if task is None:
                result_holder.append({"success": False, "action": "tracker.reopen", "task_id": task_id, "error": f"Task {task_id} does not exist."})
                return data

            current_status = task.get("status", TaskStatus.NOT_STARTED.value)
            transition = validate_task_transition(current_status, TaskStatus.REOPENED.value)
            if not transition.valid:
                result_holder.append({"success": False, "action": "tracker.reopen", "task_id": task_id, "error": transition.message})
                return data

            task["status"] = TaskStatus.REOPENED.value
            task["reopen_reason"] = reason
            task["reopened_at"] = datetime.now(timezone.utc).isoformat()
            result_holder.append({"success": True, "action": "tracker.reopen", "task_id": task_id, "reason": reason})
            return data

        locked_update(self._store_path, self._TRACKER_DEFAULTS, _updater)
        return result_holder[0]

    def get_status(self) -> dict:
        data = self._load()
        counts: dict[str, int] = {}
        total = 0
        current_task = None

        for sec_key, section in data.get("sections", {}).items():
            for ph_key, phase in section.get("phases", {}).items():
                for t_key, task in phase.get("tasks", {}).items():
                    total += 1
                    status = task.get("status", "unknown")
                    counts[status] = counts.get(status, 0) + 1
                    if status == "in_progress" and current_task is None:
                        current_task = f"{sec_key}.{ph_key}.{t_key}"

        return {
            "success": True, "action": "tracker.status",
            "total": total, "by_status": counts,
            "current_task": current_task, "last_updated": data.get("last_updated"),
        }

    def list_tasks(self, status_filter: str | None = None) -> dict:
        data = self._load()
        tasks: list[dict] = []

        for sec_key, section in data.get("sections", {}).items():
            for ph_key, phase in section.get("phases", {}).items():
                for t_key, task in phase.get("tasks", {}).items():
                    task_id = f"{sec_key}.{ph_key}.{t_key}"
                    status = task.get("status", "unknown")
                    if status_filter is not None and status != status_filter:
                        continue
                    tasks.append({"task_id": task_id, **task})

        return {"success": True, "action": "tracker.list", "tasks": tasks, "count": len(tasks)}

    def validate_dependencies(self, dependencies: dict[str, list[str]]) -> dict:
        """Validate a task dependency graph for circular dependencies (v1.0.0).

        Parameters
        ----------
        dependencies : dict
            Mapping of task_id -> list of task_ids it depends on.
        """
        visited: set[str] = set()
        path: set[str] = set()
        cycles: list[list[str]] = []

        def _dfs(node: str, current_path: list[str]) -> None:
            if node in path:
                cycle_start = current_path.index(node)
                cycles.append(current_path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            path.add(node)
            current_path.append(node)
            for dep in dependencies.get(node, []):
                _dfs(dep, current_path)
            current_path.pop()
            path.remove(node)

        for task_id in dependencies:
            if task_id not in visited:
                _dfs(task_id, [])

        return {
            "success": True,
            "action": "tracker.validate_deps",
            "valid": len(cycles) == 0,
            "cycles": cycles,
        }
