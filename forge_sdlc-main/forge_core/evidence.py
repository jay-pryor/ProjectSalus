"""Forge evidence manager — structured evidence capture for SDLC tasks.

v1.0.0 improvements:
- verify_review_completeness checks gate-proofs for all required agents
- Gate-proof schema includes agent model info and duration
- Escape hatch support in gate-proofs
"""

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from forge_core.log import safe_log
from forge_core.utils import TASK_ID_PATTERN, PHASE_ID_PATTERN, to_snake_case
from forge_core.yaml_io import locked_update, safe_load

_VALID_GATE_STATUSES = frozenset({"pass", "fail", "skip", "na", "n/a", "pending"})

_DEFAULT_TEMPLATE = """\
# Evidence: {task_id} — {task_name}

## Task Summary
<!-- Brief description of what was implemented -->

## Quality Gates

| Gate | Status | Output |
|------|--------|--------|
| G1 Lint | PENDING | |
| G2 Format | PENDING | |
| G3 Import | PENDING | |
| G4 Type | PENDING | |
| G5 Security | PENDING | |
| G6 Unit Test | PENDING | |
| G7 Integration | PENDING | |
| G8 Coverage | PENDING | |
| G9 Standards | PENDING | |

## Acceptance Criteria
<!-- AC verification results -->

## Commits
<!-- Git commits for this task -->

## Findings
<!-- Review findings and resolutions -->

## Summary
<!-- Overall task summary, written at completion -->
"""

# Required review agents for gate-proof completeness
DEFAULT_REQUIRED_AGENTS = [
    "forge_spec_compliance",
    "forge_silent_failure_hunter",
    "forge_code_simplifier",
    "forge_regression_reviewer",
]


class EvidenceManager:
    def __init__(self, project_dir: Path | None = None) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir)
        else:
            env_dir = os.environ.get("FORGE_PROJECT_DIR")
            self._project_dir = Path(env_dir) if env_dir else Path.cwd()
        self._evidence_dir = self._project_dir / "evidence"

    def _load_template(self) -> str:
        template_path = self._project_dir / "forge" / "templates" / "evidence.md"
        if template_path.is_file():
            return template_path.read_text()
        return _DEFAULT_TEMPLATE

    def _evidence_path(self, task_id: str, task_name: str) -> Path:
        snake_name = to_snake_case(task_name)
        filename = f"{task_id}_{snake_name}_evidence.md"
        return self._evidence_dir / filename

    def create(self, task_id: str, task_name: str) -> dict:
        if not TASK_ID_PATTERN.fullmatch(task_id):
            return {
                "success": False,
                "action": "evidence.create",
                "error": f"Invalid task_id: {task_id!r}. Expected format S##.P##.T##",
            }
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        filepath = self._evidence_path(task_id, task_name)
        relative_path = filepath.relative_to(self._project_dir)

        if filepath.exists():
            return {
                "success": True,
                "action": "evidence.create",
                "path": str(relative_path),
                "task_id": task_id,
                "already_exists": True,
            }

        template = self._load_template()
        content = template.replace("{task_id}", task_id).replace("{task_name}", task_name)
        filepath.write_text(content)

        return {
            "success": True,
            "action": "evidence.create",
            "path": str(relative_path),
            "task_id": task_id,
        }

    def verify_phase(self, phase_id: str) -> dict:
        if not PHASE_ID_PATTERN.fullmatch(phase_id):
            return {
                "success": False,
                "action": "evidence.verify",
                "phase_id": phase_id,
                "error": f"Invalid phase_id: {phase_id!r}. Expected format SN.PN",
            }

        results: list[dict] = []
        if not self._evidence_dir.is_dir():
            return {
                "success": True,
                "action": "evidence.verify",
                "phase_id": phase_id,
                "results": results,
                "all_verified": False,
                "warning": "Evidence directory does not exist",
            }

        phase_prefix = phase_id + "."
        for filepath in sorted(self._evidence_dir.iterdir()):
            if not filepath.name.startswith(phase_prefix):
                continue
            if not filepath.name.endswith("_evidence.md"):
                continue

            try:
                content = filepath.read_text()
            except OSError:
                results.append({
                    "file": filepath.name,
                    "verified": False,
                    "issues": [f"cannot read file: {filepath.name}"],
                })
                continue

            issues: list[str] = []

            if "PENDING" in content:
                issues.append("has PENDING quality gates")

            gate_table_rows = re.findall(
                r"^\|\s*G\d+\s+\w+\s*\|\s*(\w[\w/]*)\s*\|",
                content,
                re.MULTILINE,
            )
            if gate_table_rows:
                invalid_statuses = [
                    s for s in gate_table_rows if s.lower() not in _VALID_GATE_STATUSES
                ]
                if invalid_statuses:
                    issues.append(f"gate table has invalid statuses: {invalid_statuses}")
            else:
                issues.append("gate table missing or has no gate rows")

            summary_text = self._extract_section(content, "Summary")
            if not summary_text.strip():
                issues.append("summary section is empty")
            else:
                word_count = len(summary_text.split())
                if word_count < 50:
                    issues.append(f"summary section too brief ({word_count} words, minimum 50)")

            commits_text = self._extract_section(content, "Commits")
            if not commits_text.strip():
                issues.append("commits section is empty")
            elif not re.search(r"[a-f0-9]{7,}", commits_text):
                issues.append("commits section has no commit hash")

            ac_text = self._extract_section(content, "Acceptance Criteria")
            if not ac_text.strip():
                issues.append("acceptance criteria section is empty")

            results.append({
                "file": filepath.name,
                "verified": len(issues) == 0,
                "issues": issues,
            })

        # Check gate proofs
        proofs_dir = self._project_dir / ".forge" / "gate-proofs"
        if proofs_dir.is_dir():
            for r in results:
                task_id = r["file"].split("_")[0]
                proof_path = proofs_dir / f"{task_id}.yaml"
                if not proof_path.is_file():
                    r["issues"].append("no gate proofs recorded")
                    r["verified"] = False
                else:
                    proof_data = safe_load(proof_path, {})
                    reviews = proof_data.get("reviews", {})
                    if not reviews:
                        r["issues"].append("gate proofs file has no reviews")
                        r["verified"] = False
                    elif proof_data.get("overall") != "pass" and not proof_data.get("escape_hatch"):
                        r["issues"].append("gate proofs overall status is not pass")
                        r["verified"] = False

        all_verified = all(r["verified"] for r in results) if results else False

        result = {
            "success": True,
            "action": "evidence.verify",
            "phase_id": phase_id,
            "results": results,
            "all_verified": all_verified,
        }
        if not results:
            result["warning"] = f"No evidence files found for phase {phase_id}"
        return result

    def extract_findings(self, task_id: str) -> dict:
        content = self._read_evidence_by_task_id(task_id)
        if content is None:
            return {
                "success": False,
                "action": "evidence.extract_findings",
                "task_id": task_id,
                "error": f"No evidence file found for task {task_id}",
            }
        return {
            "success": True,
            "action": "evidence.extract_findings",
            "task_id": task_id,
            "findings": self._extract_section(content, "Findings"),
        }

    def summarise(self, task_id: str) -> dict:
        content = self._read_evidence_by_task_id(task_id)
        if content is None:
            return {
                "success": False,
                "action": "evidence.summarise",
                "task_id": task_id,
                "error": f"No evidence file found for task {task_id}",
            }
        return {
            "success": True,
            "action": "evidence.summarise",
            "task_id": task_id,
            "summary": self._extract_section(content, "Summary"),
        }

    # ── Gate Proof API (v1.0.0 — agent-based) ─────────────────────────

    def _gate_proofs_path(self, task_id: str) -> Path:
        return self._project_dir / ".forge" / "gate-proofs" / f"{task_id}.yaml"

    def record_review_agent(
        self,
        task_id: str,
        agent_name: str,
        status: str,
        findings: int,
        model: str = "",
        duration_s: float = 0.0,
        resolved: bool = True,
    ) -> dict:
        """Record a review agent result in the gate-proof file."""
        if not TASK_ID_PATTERN.fullmatch(task_id):
            return {"success": False, "action": "evidence.record-review-agent", "error": f"Invalid task_id: {task_id!r}"}
        if status not in ("pass", "fail"):
            return {"success": False, "action": "evidence.record-review-agent", "error": f"Invalid status: {status!r}"}

        proof_path = self._gate_proofs_path(task_id)
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        defaults = {
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reviews": {},
            "overall": "pending",
            "escape_hatch": False,
        }

        def _updater(data: dict) -> dict:
            data.setdefault("reviews", {})[agent_name] = {
                "status": status,
                "findings": findings,
                "resolved": resolved,
                "model": model,
                "duration_s": duration_s,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            # Update overall status
            reviews = data["reviews"]
            all_pass = all(
                r["status"] == "pass" or (r["status"] == "fail" and r.get("resolved"))
                for r in reviews.values()
            )
            data["overall"] = "pass" if all_pass else "pending"
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
            return data

        try:
            locked_update(proof_path, defaults, _updater)
        except RuntimeError as exc:
            return {"success": False, "action": "evidence.record-review-agent", "error": str(exc)}

        return {
            "success": True,
            "action": "evidence.record-review-agent",
            "task_id": task_id,
            "agent": agent_name,
            "status": status,
        }

    def record_escape_hatch(self, task_id: str, reason: str) -> dict:
        """Record an escape hatch (skipping reviews) with mandatory reason."""
        if not TASK_ID_PATTERN.fullmatch(task_id):
            return {"success": False, "action": "evidence.escape-hatch", "error": f"Invalid task_id: {task_id!r}"}
        if not reason or len(reason) < 10:
            return {"success": False, "action": "evidence.escape-hatch", "error": "Reason must be at least 10 characters"}

        proof_path = self._gate_proofs_path(task_id)
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        defaults = {
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reviews": {},
            "overall": "pass",
            "escape_hatch": True,
            "escape_reason": reason,
        }

        def _updater(data: dict) -> dict:
            data["escape_hatch"] = True
            data["escape_reason"] = reason
            data["overall"] = "pass"
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
            return data

        try:
            locked_update(proof_path, defaults, _updater)
        except RuntimeError as exc:
            return {"success": False, "action": "evidence.escape-hatch", "error": str(exc)}

        return {
            "success": True,
            "action": "evidence.escape-hatch",
            "task_id": task_id,
            "reason": reason,
        }

    def verify_review_completeness(
        self,
        task_id: str,
        required_agents: list[str] | None = None,
    ) -> dict:
        """Verify that all required review agents have passed for a task."""
        if not TASK_ID_PATTERN.fullmatch(task_id):
            return {"success": False, "action": "evidence.verify-review", "error": f"Invalid task_id: {task_id!r}"}

        if required_agents is None:
            required_agents = DEFAULT_REQUIRED_AGENTS

        proof_path = self._gate_proofs_path(task_id)
        if not proof_path.is_file():
            return {
                "success": True,
                "action": "evidence.verify-review",
                "task_id": task_id,
                "review_complete": False,
                "missing_agents": required_agents,
                "message": "No gate-proof file found",
            }

        data = safe_load(proof_path, {})

        # Escape hatch bypasses review requirements
        if data.get("escape_hatch"):
            return {
                "success": True,
                "action": "evidence.verify-review",
                "task_id": task_id,
                "review_complete": True,
                "escape_hatch": True,
                "escape_reason": data.get("escape_reason", ""),
            }

        reviews = data.get("reviews", {})
        missing = [a for a in required_agents if a not in reviews]
        failed = [
            a for a in required_agents
            if a in reviews and reviews[a]["status"] == "fail" and not reviews[a].get("resolved")
        ]

        return {
            "success": True,
            "action": "evidence.verify-review",
            "task_id": task_id,
            "review_complete": len(missing) == 0 and len(failed) == 0,
            "missing_agents": missing,
            "failed_agents": failed,
            "completed_agents": [a for a in required_agents if a in reviews],
            "overall": data.get("overall", "pending"),
        }

    # ── Legacy gate recording (backwards compat) ──────────────────────

    _VALID_PROOF_STATUSES = frozenset({"pass", "fail", "skip"})

    def record_gate(
        self, task_id: str, gate_id: str, status: str,
        output_hash: str, output_excerpt: str = "",
    ) -> dict:
        """Record a structured gate proof for a task (legacy G1-G9 gates)."""
        if not TASK_ID_PATTERN.fullmatch(task_id):
            return {"success": False, "action": "evidence.record-gate", "error": f"Invalid task_id: {task_id!r}"}
        if status.lower() not in self._VALID_PROOF_STATUSES:
            return {"success": False, "action": "evidence.record-gate", "error": f"Invalid status: {status!r}"}
        if not re.fullmatch(r"G\d{1,2}", gate_id):
            return {"success": False, "action": "evidence.record-gate", "error": f"Invalid gate_id: {gate_id!r}"}
        if not output_hash or len(output_hash) > 128:
            return {"success": False, "action": "evidence.record-gate", "error": "output_hash must be non-empty, max 128 chars"}

        proof_path = self._gate_proofs_path(task_id)
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        defaults = {"task_id": task_id, "gates": []}

        entry = {
            "gate_id": gate_id,
            "status": status.lower(),
            "output_hash": output_hash,
            "output_excerpt": output_excerpt[:500],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        def _updater(data: dict) -> dict:
            data["task_id"] = task_id
            data.setdefault("gates", []).append(entry)
            return data

        try:
            locked_update(proof_path, defaults, _updater)
        except RuntimeError as exc:
            return {"success": False, "action": "evidence.record-gate", "error": str(exc)}

        try:
            from forge_core.audit import AuditLog
            audit = AuditLog(self._project_dir)
            audit.emit("evidence", "gate.recorded", {
                "task_id": task_id, "gate_id": gate_id,
                "status": status.lower(), "output_hash": output_hash,
            })
        except Exception:
            pass

        return {
            "success": True,
            "action": "evidence.record-gate",
            "task_id": task_id,
            "gate_id": gate_id,
            "status": status.lower(),
        }

    def verify_commit(self, task_id: str, commit_hash: str) -> dict:
        """Verify a commit exists in git and its message contains the task ID."""
        if not TASK_ID_PATTERN.fullmatch(task_id):
            return {"success": False, "action": "evidence.verify-commit", "error": f"Invalid task_id: {task_id!r}"}
        if not re.fullmatch(r"[0-9a-f]{7,40}", commit_hash):
            return {"success": False, "action": "evidence.verify-commit", "error": f"Invalid commit hash: {commit_hash!r}"}

        try:
            result = subprocess.run(
                ["git", "log", "--format=%s", "-1", commit_hash],
                capture_output=True, text=True, timeout=10,
                cwd=str(self._project_dir),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {"success": False, "action": "evidence.verify-commit", "error": f"Git command failed: {exc}"}

        if result.returncode != 0:
            return {
                "success": True, "action": "evidence.verify-commit",
                "commit_hash": commit_hash, "task_id": task_id,
                "verified": False, "message_contains_task_id": False,
            }

        message = result.stdout.strip()
        return {
            "success": True, "action": "evidence.verify-commit",
            "commit_hash": commit_hash, "task_id": task_id,
            "verified": True, "message_contains_task_id": task_id in message,
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _read_evidence_by_task_id(self, task_id: str) -> str | None:
        if not TASK_ID_PATTERN.fullmatch(task_id):
            return None
        if not self._evidence_dir.is_dir():
            return None
        prefix = task_id + "_"
        for filepath in self._evidence_dir.iterdir():
            if filepath.name.startswith(prefix) and filepath.name.endswith("_evidence.md"):
                try:
                    return filepath.read_text()
                except OSError as exc:
                    safe_log("evidence_read_error", level="warning", task_id=task_id, error=str(exc))
                    return None
        return None

    @staticmethod
    def _extract_section(content: str, heading: str) -> str:
        pattern = rf"## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return ""
        text = match.group(1).strip()
        if re.fullmatch(r"<!--.*?-->", text, re.DOTALL):
            return ""
        return text
