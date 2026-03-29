"""Forge session manager — YAML-backed session tracking with handoff context.

v1.0.0 improvements:
- Cost tracking integration point
- Session duration limits (configurable max hours)
"""

import copy
import os
from datetime import date, datetime, timezone
from pathlib import Path

from forge_core.yaml_io import atomic_save, safe_load


_EMPTY_STATE: dict = {
    "schema_version": "1.0.0",
    "session": {
        "id": None,
        "date": None,
        "status": None,
        "started_at": None,
        "ended_at": None,
    },
    "position": {
        "section": None,
        "phase": None,
        "task": None,
        "task_name": None,
    },
    "handoff": {
        "summary": "",
        "next_steps": [],
        "blockers": [],
        "decisions_pending": [],
    },
    "health": {
        "last_evidence_check": None,
        "evidence_passed": None,
        "last_test_run": None,
        "tests_passing": None,
    },
    "cost": {
        "session_tokens_in": 0,
        "session_tokens_out": 0,
        "session_cost_usd": 0.0,
    },
    "completed_this_session": [],
    "history": [],
}


class SessionManager:
    def __init__(self, project_dir: Path | None = None, max_hours: float = 0) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir)
        elif os.environ.get("FORGE_PROJECT_DIR"):
            self._project_dir = Path(os.environ["FORGE_PROJECT_DIR"])
        else:
            self._project_dir = Path.cwd()

        self._state_dir = self._project_dir / ".forge"
        self._state_path = self._state_dir / "state.yaml"
        self._max_hours = max_hours

    def _load(self) -> dict:
        return safe_load(self._state_path, copy.deepcopy(_EMPTY_STATE))

    def _save(self, data: dict) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        atomic_save(self._state_path, data)

    @staticmethod
    def _today_prefix() -> str:
        return date.today().strftime("%Y%m%d")

    def _next_session_id(self, data: dict) -> str:
        prefix = self._today_prefix()
        n = 1
        for entry in data.get("history", []):
            entry_id = entry.get("id", "")
            if isinstance(entry_id, str) and entry_id.startswith(prefix + "-"):
                try:
                    seq = int(entry_id.split("-", 1)[1])
                    n = max(n, seq + 1)
                except (ValueError, IndexError):
                    pass
        current_id = (data.get("session") or {}).get("id")
        if isinstance(current_id, str) and current_id.startswith(prefix + "-"):
            try:
                seq = int(current_id.split("-", 1)[1])
                n = max(n, seq + 1)
            except (ValueError, IndexError):
                pass
        return f"{prefix}-{n}"

    def start_session(self) -> dict:
        data = self._load()
        auto_archived = False
        archived_id: str | None = None

        current = data.get("session", {})
        if current.get("status") == "in_progress" and current.get("id"):
            auto_archived = True
            archived_id = current["id"]
            history_entry = {
                "id": current["id"],
                "date": current.get("date"),
                "completed": list(data.get("completed_this_session", [])),
                "abandoned": True,
            }
            data.setdefault("history", []).append(history_entry)

        session_id = self._next_session_id(data)
        now = datetime.now(timezone.utc).isoformat()

        data["session"] = {
            "id": session_id,
            "date": self._today_prefix(),
            "status": "in_progress",
            "started_at": now,
            "ended_at": None,
        }
        data["position"] = {"section": None, "phase": None, "task": None, "task_name": None}
        data["completed_this_session"] = []
        data["cost"] = {"session_tokens_in": 0, "session_tokens_out": 0, "session_cost_usd": 0.0}

        self._save(data)
        result = {"success": True, "action": "session.start", "session_id": session_id}
        if auto_archived:
            result["warning"] = f"Auto-archived active session {archived_id}"
        return result

    def end_session(
        self,
        context: str = "",
        next_steps: list[str] | None = None,
        blockers: list[str] | None = None,
    ) -> dict:
        data = self._load()
        session = data.get("session", {})
        session_id = session.get("id")

        if not session_id or session.get("status") != "in_progress":
            return {"success": False, "action": "session.end", "error": "No active session to end."}

        now = datetime.now(timezone.utc).isoformat()
        session["status"] = "completed"
        session["ended_at"] = now
        data["session"] = session

        data["handoff"] = {
            "summary": context,
            "next_steps": next_steps or [],
            "blockers": blockers or [],
            "decisions_pending": data.get("handoff", {}).get("decisions_pending", []),
        }

        history_entry = {
            "id": session_id,
            "date": session.get("date"),
            "completed": list(data.get("completed_this_session", [])),
            "cost": dict(data.get("cost", {})),
        }
        data.setdefault("history", []).append(history_entry)

        self._save(data)
        return {"success": True, "action": "session.end", "session_id": session_id}

    def get_status(self) -> dict:
        data = self._load()
        session = data.get("session", _EMPTY_STATE["session"])
        interrupted = (
            session.get("status") == "in_progress"
            and session.get("ended_at") is None
            and len(data.get("history", [])) > 0
        )
        return {
            "success": True,
            "action": "session.status",
            "session": dict(session),
            "interrupted": interrupted,
            "cost": dict(data.get("cost", {})),
        }

    def resume_session(self) -> dict:
        data = self._load()
        session = data.get("session", _EMPTY_STATE["session"])
        handoff = data.get("handoff", _EMPTY_STATE["handoff"])
        position = data.get("position", _EMPTY_STATE["position"])
        completed = data.get("completed_this_session", [])

        return {
            "success": True,
            "action": "session.resume",
            "previous_session": dict(session),
            "recovery": {
                "handoff": dict(handoff),
                "completed_tasks": list(completed),
                "position": dict(position),
            },
        }

    def record_cost(self, tokens_in: int, tokens_out: int, cost_usd: float) -> dict:
        """Record cost for the current session."""
        data = self._load()
        cost = data.get("cost", {"session_tokens_in": 0, "session_tokens_out": 0, "session_cost_usd": 0.0})
        cost["session_tokens_in"] = cost.get("session_tokens_in", 0) + tokens_in
        cost["session_tokens_out"] = cost.get("session_tokens_out", 0) + tokens_out
        cost["session_cost_usd"] = round(cost.get("session_cost_usd", 0.0) + cost_usd, 6)
        data["cost"] = cost
        self._save(data)
        return {"success": True, "action": "session.record_cost", "cost": cost}

    def check_duration_limit(self) -> dict:
        """Check if the session has exceeded its duration limit."""
        if self._max_hours <= 0:
            return {"success": True, "action": "session.check_duration", "exceeded": False}

        data = self._load()
        session = data.get("session", {})
        started = session.get("started_at")
        if not started:
            return {"success": True, "action": "session.check_duration", "exceeded": False}

        start_time = datetime.fromisoformat(started)
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() / 3600
        return {
            "success": True,
            "action": "session.check_duration",
            "exceeded": elapsed > self._max_hours,
            "elapsed_hours": round(elapsed, 2),
            "limit_hours": self._max_hours,
        }
