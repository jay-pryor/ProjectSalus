"""Forge verifier — spec-to-code traceability."""

import os
import re
from pathlib import Path

from forge_core.utils import TASK_ID_PATTERN


class Verifier:
    def __init__(self, project_dir: Path | None = None) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir).resolve()
        else:
            env_dir = os.environ.get("FORGE_PROJECT_DIR")
            self._project_dir = Path(env_dir).resolve() if env_dir else Path.cwd().resolve()

    def trace(self, spec_path: str, code_paths: list[str] | None = None) -> dict:
        """Build traceability matrix from spec file."""
        spec_file = self._project_dir / spec_path
        if not spec_file.is_file():
            return {"success": False, "action": "verify.trace", "error": f"Spec file not found: {spec_path}"}

        try:
            content = spec_file.read_text()
        except OSError as exc:
            return {"success": False, "action": "verify.trace", "error": str(exc)}

        # Extract ACs
        acs = self._extract_acceptance_criteria(content)
        if not acs:
            return {"success": True, "action": "verify.trace", "spec": spec_path, "criteria": [], "all_traced": True}

        # Trace each AC
        results = []
        for ac in acs:
            traced = self._find_trace(ac, code_paths)
            results.append({"ac": ac["text"], "task": ac.get("task", ""), "status": "traced" if traced else "untraced", "traces": traced})

        all_traced = all(r["status"] == "traced" for r in results)
        return {"success": True, "action": "verify.trace", "spec": spec_path, "criteria": results, "all_traced": all_traced}

    def _extract_acceptance_criteria(self, content: str) -> list[dict]:
        """Extract ACs from markdown checkboxes and inline patterns."""
        acs = []
        current_task = ""
        for line in content.split("\n"):
            task_match = re.match(r"^###\s+(T\d+)", line)
            if task_match:
                current_task = task_match.group(1)
            checkbox = re.match(r"^\s*-\s*\[[ x]\]\s*(.+)", line)
            if checkbox:
                acs.append({"text": checkbox.group(1).strip(), "task": current_task})
        return acs

    def _find_trace(self, ac: dict, code_paths: list[str] | None) -> list[str]:
        """Find code references that trace to this AC."""
        traces = []
        text = ac["text"].lower()

        # Extract key terms from AC
        terms = [w for w in re.findall(r"\w+", text) if len(w) > 3]
        if not terms:
            return traces

        # Search in code paths
        search_dirs = [self._project_dir / p for p in (code_paths or ["."])]
        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for py_file in search_dir.rglob("*.py"):
                if not py_file.is_relative_to(self._project_dir):
                    continue
                try:
                    file_content = py_file.read_text()
                    # Check if test functions reference AC terms
                    for match in re.finditer(r"def (test_\w+)", file_content):
                        func_name = match.group(1).lower()
                        if any(term in func_name for term in terms[:3]):
                            rel = py_file.relative_to(self._project_dir)
                            traces.append(f"{rel}::{match.group(1)}")
                except (OSError, UnicodeDecodeError):
                    continue
        return traces
