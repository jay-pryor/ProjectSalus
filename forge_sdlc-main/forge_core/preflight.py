"""Forge preflight — environment diagnostics and tool version checks.

v1.0.0 improvements:
- Tool version checks (ruff, pytest, node, npm)
- Structured diagnostic report
"""

import os
import subprocess
from pathlib import Path


class PreflightDiagnostic:
    def __init__(self, project_dir: Path | None = None) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir)
        else:
            env_dir = os.environ.get("FORGE_PROJECT_DIR")
            self._project_dir = Path(env_dir) if env_dir else Path.cwd()

    def run(self) -> dict:
        """Run full environment diagnostic."""
        checks: list[dict] = []

        # Python
        checks.append(self._check_tool("python3", "--version"))
        checks.append(self._check_tool("pip", "--version"))

        # Dev tools
        checks.append(self._check_tool("ruff", "--version"))
        checks.append(self._check_tool("pytest", "--version"))

        # Node (optional)
        checks.append(self._check_tool("node", "--version"))
        checks.append(self._check_tool("npm", "--version"))

        # Git
        checks.append(self._check_tool("git", "--version"))

        # Docker
        checks.append(self._check_tool("docker", "--version"))

        # Project structure
        checks.append(self._check_path(".forge", "Forge state directory"))
        checks.append(self._check_path("evidence", "Evidence directory"))

        passed = sum(1 for c in checks if c["status"] == "pass")
        failed = sum(1 for c in checks if c["status"] == "fail")
        skipped = sum(1 for c in checks if c["status"] == "skip")

        return {
            "success": True,
            "action": "preflight.run",
            "checks": checks,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "overall": "pass" if failed == 0 else "fail",
        }

    def _check_tool(self, tool: str, version_flag: str) -> dict:
        try:
            result = subprocess.run(
                [tool, version_flag],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip().split("\n")[0]
                return {"check": tool, "status": "pass", "version": version}
            return {"check": tool, "status": "fail", "error": f"Exit code {result.returncode}"}
        except FileNotFoundError:
            return {"check": tool, "status": "skip", "error": "Not installed"}
        except subprocess.TimeoutExpired:
            return {"check": tool, "status": "fail", "error": "Timeout"}

    def _check_path(self, relative: str, label: str) -> dict:
        path = self._project_dir / relative
        if path.exists():
            return {"check": label, "status": "pass", "path": str(path)}
        return {"check": label, "status": "skip", "error": f"{relative} not found"}
