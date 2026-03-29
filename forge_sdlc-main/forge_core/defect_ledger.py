"""Forge defect ledger — track defects and analyze framework gaps.

v1.0.0 improvements:
- Severity trend tracking
- Recurrence detection (same file_path + category = recurrence)
"""

import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from forge_core.audit import AuditLog
from forge_core.yaml_io import locked_update, safe_load

_TASK_ID_PATTERN = re.compile(r"^S\d+\.P\d+\.T\d+$")
_DEFECT_ID_PATTERN = re.compile(r"^D\d{3,}$")
_PHASE_ID_PATTERN = re.compile(r"^S\d+\.P\d+$")

VALID_CATEGORIES = frozenset({"logic", "security", "performance", "style", "test-gap", "integration", "config"})
VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low"})
VALID_STAGES = frozenset({"G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "L2", "L3", "L4", "manual", "production"})
VALID_ROOT_CAUSES = frozenset({"missing-test", "missing-edge-case", "wrong-assumption", "spec-ambiguity", "pattern-drift", "dependency-gap", "config-error"})
_STAGE_ORDER = {"G1": 1, "G2": 2, "G3": 3, "G4": 4, "G5": 5, "G6": 6, "G7": 7, "G8": 8, "G9": 9, "L2": 10, "L3": 11, "L4": 12, "manual": 13, "production": 14}
_MAX_DEFECTS = 2000
_LEDGER_DEFAULTS = {"defects": [], "next_seq": 1}


class DefectLedger:
    def __init__(self, project_dir: Path | None = None) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir).resolve()
        else:
            env_dir = os.environ.get("FORGE_PROJECT_DIR")
            self._project_dir = Path(env_dir).resolve() if env_dir else Path.cwd().resolve()
        self._ledger_path = self._project_dir / ".forge" / "defect-ledger.yaml"

    @staticmethod
    def _validate_inputs(task_id, file_path, category, severity, discovery_stage, ideal_catch_stage, root_cause_class):
        if not _TASK_ID_PATTERN.fullmatch(task_id):
            return {"success": False, "action": "defect.record", "error": f"Invalid task_id: {task_id!r}"}
        if "\x00" in file_path or "\\" in file_path:
            return {"success": False, "action": "defect.record", "error": f"Invalid file_path: {file_path!r}"}
        fp = PurePosixPath(file_path)
        if fp.is_absolute() or ".." in fp.parts:
            return {"success": False, "action": "defect.record", "error": f"file_path must be relative, no '..'"}
        for name, val, valid_set in [("category", category, VALID_CATEGORIES), ("severity", severity, VALID_SEVERITIES), ("discovery_stage", discovery_stage, VALID_STAGES), ("ideal_catch_stage", ideal_catch_stage, VALID_STAGES), ("root_cause_class", root_cause_class, VALID_ROOT_CAUSES)]:
            if val not in valid_set:
                return {"success": False, "action": "defect.record", "error": f"Invalid {name}: {val!r}"}
        return None

    def record(self, task_id, file_path, category, severity, discovery_stage, ideal_catch_stage, root_cause_class, description=""):
        err = self._validate_inputs(task_id, file_path, category, severity, discovery_stage, ideal_catch_stage, root_cause_class)
        if err:
            return err
        description = (description or "")[:500]

        def _updater(data):
            defects = data.get("defects", [])
            if len(defects) >= _MAX_DEFECTS:
                raise ValueError(f"Defect ledger full ({_MAX_DEFECTS} entries)")
            seq = data.get("next_seq", 1)
            defect_id = f"D{seq:03d}"

            # Recurrence detection (v1.0.0)
            recurrence = any(
                d.get("file_path") == file_path and d.get("category") == category
                for d in defects
            )

            entry = {
                "defect_id": defect_id, "task_id": task_id,
                "file_path": file_path, "category": category,
                "severity": severity, "discovery_stage": discovery_stage,
                "ideal_catch_stage": ideal_catch_stage, "root_cause_class": root_cause_class,
                "description": description, "resolved": False,
                "recurrence": recurrence,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            defects.append(entry)
            data["defects"] = defects
            data["next_seq"] = seq + 1
            return data

        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            updated = locked_update(self._ledger_path, _LEDGER_DEFAULTS, _updater)
        except ValueError as exc:
            return {"success": False, "action": "defect.record", "error": str(exc)}
        except RuntimeError as exc:
            return {"success": False, "action": "defect.record", "error": str(exc)}

        defect_id = f"D{updated['next_seq'] - 1:03d}"
        try:
            AuditLog(self._project_dir).emit("defect", "defect.recorded", {
                "defect_id": defect_id, "task_id": task_id, "category": category, "severity": severity,
            })
        except Exception:
            pass
        return {"success": True, "action": "defect.record", "defect_id": defect_id, "task_id": task_id}

    def resolve(self, defect_id):
        if not _DEFECT_ID_PATTERN.fullmatch(defect_id):
            return {"success": False, "action": "defect.resolve", "error": f"Invalid defect_id: {defect_id!r}"}
        found = False
        def _updater(data):
            nonlocal found
            for d in data.get("defects", []):
                if d["defect_id"] == defect_id:
                    d["resolved"] = True
                    d["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    found = True
                    return data
            return data
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        locked_update(self._ledger_path, _LEDGER_DEFAULTS, _updater)
        if not found:
            return {"success": False, "action": "defect.resolve", "error": f"Defect {defect_id} not found"}
        return {"success": True, "action": "defect.resolve", "defect_id": defect_id}

    def list_defects(self, phase_id=None, task_id=None, resolved=None):
        data = safe_load(self._ledger_path, _LEDGER_DEFAULTS)
        defects = data.get("defects", [])
        if phase_id:
            defects = [d for d in defects if d.get("task_id", "").startswith(phase_id + ".")]
        if task_id:
            defects = [d for d in defects if d.get("task_id") == task_id]
        if resolved is not None:
            defects = [d for d in defects if d.get("resolved", False) == resolved]
        return {"success": True, "action": "defect.list", "defects": defects, "total": len(defects)}

    def analyze(self, phase_id):
        if not _PHASE_ID_PATTERN.fullmatch(phase_id):
            return {"success": False, "action": "defect.analyze", "error": f"Invalid phase_id: {phase_id!r}"}
        data = safe_load(self._ledger_path, _LEDGER_DEFAULTS)
        defects = [d for d in data.get("defects", []) if d.get("task_id", "").startswith(phase_id + ".")]
        total = len(defects)
        if total == 0:
            return {"success": True, "action": "defect.analyze", "phase_id": phase_id, "analysis": {"total_defects": 0, "late_catch_rate": 0.0, "recurrence_rate": 0.0, "escapees": [], "root_cause_clusters": [], "gate_effectiveness": [], "severity_trend": {}, "recommendations": []}}

        # Late catches
        late_count = 0
        escapees = []
        for d in defects:
            disc, ideal = _STAGE_ORDER.get(d.get("discovery_stage", ""), 0), _STAGE_ORDER.get(d.get("ideal_catch_stage", ""), 0)
            if disc > ideal:
                late_count += 1
                if disc - ideal >= 2:
                    escapees.append({"defect_id": d["defect_id"], "discovery_stage": d["discovery_stage"], "ideal_catch_stage": d["ideal_catch_stage"], "stages_late": disc - ideal})

        # Root cause clusters
        rc_counts: dict[str, int] = defaultdict(int)
        for d in defects:
            rc_counts[d.get("root_cause_class", "unknown")] += 1
        root_cause_clusters = [{"class": rc, "count": cnt, "pct": round(cnt / total, 3)} for rc, cnt in sorted(rc_counts.items(), key=lambda x: -x[1])]

        # Severity trend (v1.0.0)
        sev_counts: dict[str, int] = defaultdict(int)
        for d in defects:
            sev_counts[d.get("severity", "unknown")] += 1
        severity_trend = dict(sev_counts)

        # Recurrence rate (v1.0.0)
        recurrences = sum(1 for d in defects if d.get("recurrence"))
        recurrence_rate = round(recurrences / total, 3)

        # Gate effectiveness
        gate_caught: dict[str, int] = defaultdict(int)
        gate_missed: dict[str, int] = defaultdict(int)
        for d in defects:
            disc_s, ideal_s = d.get("discovery_stage", ""), d.get("ideal_catch_stage", "")
            if disc_s in _STAGE_ORDER:
                gate_caught[disc_s] += 1
            if disc_s in _STAGE_ORDER and ideal_s in _STAGE_ORDER and _STAGE_ORDER[disc_s] > _STAGE_ORDER[ideal_s]:
                gate_missed[ideal_s] += 1
        gate_effectiveness = [{"gate": g, "caught": gate_caught.get(g, 0), "missed": gate_missed.get(g, 0)} for g in sorted(set(gate_caught) | set(gate_missed))]

        return {"success": True, "action": "defect.analyze", "phase_id": phase_id, "analysis": {
            "total_defects": total, "late_catch_rate": round(late_count / total, 3),
            "recurrence_rate": recurrence_rate, "severity_trend": severity_trend,
            "escapees": escapees, "root_cause_clusters": root_cause_clusters,
            "gate_effectiveness": gate_effectiveness, "recommendations": [],
        }}
