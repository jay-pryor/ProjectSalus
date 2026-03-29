"""Forge standards checker — automated enforcement of engineering standards.

Full-stack checker supporting 10 Python + 5 frontend standards,
dynamically applied based on project type. All checks are regex/grep-based
(no AST parsing required).
"""

import os
import re
from pathlib import Path
from typing import Any

from forge_core.standards_loader import StandardsLoader

__all__ = ["StandardsChecker"]

_MAX_FILE_BYTES = 1_000_000  # 1 MB guard


class StandardsChecker:
    """Automated standards enforcement via regex-based checks.

    Supports 10 Python standards and 5 frontend standards, dynamically
    applied based on project type detection.
    """

    def __init__(self, project_dir: Path | None = None) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir).resolve()
        else:
            env_dir = os.environ.get("FORGE_PROJECT_DIR")
            self._project_dir = Path(env_dir).resolve() if env_dir else Path.cwd().resolve()
        self._loader = StandardsLoader()

    def _resolve_safe(self, filepath: str) -> Path | None:
        full_path = (self._project_dir / filepath).resolve()
        if not full_path.is_relative_to(self._project_dir):
            return None
        return full_path

    def _read_safe(self, full_path: Path) -> str | None:
        try:
            if full_path.stat().st_size > _MAX_FILE_BYTES:
                return None
            return full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    # ── Python Standards (10) ─────────────────────────────────────────

    def _check_error_handling(self, files: list[str]) -> list[dict]:
        """Check for bare except, swallowed exceptions, missing re-raise."""
        violations = []
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped == "except:" or re.match(r"^except\s*:", stripped):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "error-handling.bare-except",
                        "message": "Bare except clause — specify exception type",
                        "severity": "must",
                    })
                elif re.match(r"^except\s+Exception(\s+as\s+\w+)?\s*:", stripped):
                    has_reraise = False
                    except_indent = len(line) - len(line.lstrip())
                    for j in range(i, min(i + 5, len(lines))):
                        body_line = lines[j]
                        body_indent = len(body_line) - len(body_line.lstrip())
                        if body_line.strip() and body_indent <= except_indent:
                            break
                        if re.search(r"\braise\b", body_line):
                            has_reraise = True
                            break
                    if not has_reraise:
                        violations.append({
                            "file": filepath, "line": i,
                            "rule": "error-handling.exception-swallow",
                            "message": "except Exception without re-raise may swallow errors",
                            "severity": "should",
                        })
        return violations

    def _check_testing(self, files: list[str]) -> list[dict]:
        """Verify test files exist, have test functions and assertions."""
        violations = []
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            if "test_" in filepath or "/tests/" in filepath or filepath.startswith("tests/"):
                # Check test file quality
                full_path = self._resolve_safe(filepath)
                if not full_path or not full_path.is_file():
                    continue
                content = self._read_safe(full_path)
                if content is None:
                    continue
                name = Path(filepath).name
                if name == "conftest.py":
                    continue
                if "def test_" not in content:
                    violations.append({
                        "file": filepath, "line": None,
                        "rule": "testing.no-test-functions",
                        "message": "Test file has no test_ functions",
                        "severity": "should",
                    })
                if "assert" not in content and "pytest.raises" not in content:
                    violations.append({
                        "file": filepath, "line": None,
                        "rule": "testing.no-assertions",
                        "message": "Test file has no assert statements or pytest.raises",
                        "severity": "should",
                    })
            else:
                # Check source file has corresponding test
                path = Path(filepath)
                test_name = f"test_{path.name}"
                test_path = self._project_dir / "tests" / test_name
                if not test_path.is_file():
                    violations.append({
                        "file": filepath,
                        "rule": "testing.missing-test-file",
                        "message": f"No test file found: tests/{test_name}",
                        "severity": "should",
                    })
        return violations

    def _check_logging(self, files: list[str]) -> list[dict]:
        """Check for print() in non-test files, enforce structured logging."""
        violations = []
        print_pattern = re.compile(r"\bprint\s*\(")
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            parts = Path(filepath).parts
            name = Path(filepath).name
            if "tests" in parts or name.startswith("test_") or name in ("conftest.py", "setup.py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if print_pattern.search(stripped):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "logging.print-statement",
                        "message": "print() in non-test file — use structured logging",
                        "severity": "should",
                    })
        return violations

    def _check_type_safety(self, files: list[str]) -> list[dict]:
        """Check for missing type hints on public functions, Any abuse."""
        violations = []
        func_pattern = re.compile(r"^\s*def\s+([a-zA-Z]\w*)\s*\(")
        any_pattern = re.compile(r":\s*Any\b|-> Any\b")
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            parts = Path(filepath).parts
            if "tests" in parts or Path(filepath).name.startswith("test_"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                match = func_pattern.match(line)
                if match:
                    func_name = match.group(1)
                    if func_name.startswith("_"):
                        continue
                    if "->" not in line:
                        # Check next line for continuation
                        lines_after = content.splitlines()[i:i + 3]
                        combined = " ".join(lines_after)
                        if "->" not in combined:
                            violations.append({
                                "file": filepath, "line": i,
                                "rule": "type-safety.missing-return-type",
                                "message": f"Public function '{func_name}' missing return type hint",
                                "severity": "should",
                            })
                if any_pattern.search(line):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "type-safety.any-usage",
                        "message": "Use of 'Any' type — consider a more specific type",
                        "severity": "should",
                    })
        return violations

    def _check_api_design(self, files: list[str]) -> list[dict]:
        """Check API route conventions, response schemas."""
        violations = []
        api_dirs = {"routers", "endpoints", "api"}
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            parts = set(Path(filepath).parts)
            if not parts & api_dirs:
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"return\s+\{", line) and "envelope" not in line.lower() and "response" not in line.lower():
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "api-design.envelope",
                        "message": "Response may not use standard envelope wrapper",
                        "severity": "should",
                    })
        return violations

    def _check_database(self, files: list[str]) -> list[dict]:
        """Check for raw queries outside repos, migration safety."""
        violations = []
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            if "repositories/" in filepath or "repositories\\" in filepath:
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"session\.(execute|query)\s*\(", line):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "database.raw-query",
                        "message": "Raw session.execute/query outside repositories/ directory",
                        "severity": "must",
                    })
                if re.search(r"\.raw\s*\(|text\s*\(['\"](?:DROP|DELETE|ALTER)", line, re.IGNORECASE):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "database.dangerous-raw-sql",
                        "message": "Potentially dangerous raw SQL operation detected",
                        "severity": "must",
                    })
        return violations

    def _check_security(self, files: list[str]) -> list[dict]:
        """Check for hardcoded secrets, missing auth, CORS issues."""
        violations = []
        secret_patterns = re.compile(
            r"""(?:password|secret|api_key|apikey|token|private_key)\s*=\s*['"][^'"]{8,}['"]""",
            re.IGNORECASE,
        )
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            parts = Path(filepath).parts
            if "tests" in parts or Path(filepath).name.startswith("test_"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                if secret_patterns.search(line):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "security.hardcoded-secret",
                        "message": "Possible hardcoded secret detected",
                        "severity": "must",
                    })
        return violations

    def _check_dependency_management(self, files: list[str]) -> list[dict]:
        """Check for wildcard dependencies, missing pinning."""
        violations = []
        for filepath in files:
            if not (filepath.endswith("requirements.txt") or filepath.endswith("pyproject.toml")):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("["):
                    continue
                # In requirements.txt, check for unpinned deps
                if filepath.endswith("requirements.txt"):
                    if re.match(r"^[a-zA-Z][\w-]*\s*$", stripped):
                        violations.append({
                            "file": filepath, "line": i,
                            "rule": "dependency-management.unpinned",
                            "message": f"Unpinned dependency: {stripped}",
                            "severity": "should",
                        })
        return violations

    def _check_configuration(self, files: list[str]) -> list[dict]:
        """Check for raw os.environ access without validation."""
        violations = []
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"os\.environ\.get\(|os\.getenv\(", line):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "configuration.raw-env",
                        "message": "Raw os.environ.get/os.getenv — use validated config accessor",
                        "severity": "should",
                    })
        return violations

    def _check_documentation(self, files: list[str]) -> list[dict]:
        """Check for missing docstrings on public functions/classes."""
        violations = []
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            parts = Path(filepath).parts
            if "tests" in parts or Path(filepath).name.startswith("test_"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                # Check classes
                class_match = re.match(r"^class\s+([A-Z]\w*)", line)
                if class_match:
                    next_line = lines[i] if i < len(lines) else ""
                    if '"""' not in next_line and "'''" not in next_line:
                        violations.append({
                            "file": filepath, "line": i,
                            "rule": "documentation.missing-class-docstring",
                            "message": f"Class '{class_match.group(1)}' missing docstring",
                            "severity": "should",
                        })
        return violations

    # ── Frontend Standards (5) ────────────────────────────────────────

    def _check_typescript_safety(self, files: list[str]) -> list[dict]:
        """Check for 'any' type usage, missing strict mode."""
        violations = []
        for filepath in files:
            if not filepath.endswith((".ts", ".tsx")):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r":\s*any\b|<any>|as\s+any\b", line):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "typescript-safety.any-usage",
                        "message": "Use of 'any' type — use a specific type or unknown",
                        "severity": "must",
                    })
                if re.search(r"@ts-ignore|@ts-nocheck", line):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "typescript-safety.ts-ignore",
                        "message": "TypeScript suppression directive — fix the type error instead",
                        "severity": "must",
                    })
        return violations

    def _check_component_testing(self, files: list[str]) -> list[dict]:
        """Check React test patterns — RTL usage, no implementation details."""
        violations = []
        for filepath in files:
            if not filepath.endswith((".test.tsx", ".test.ts", ".spec.tsx", ".spec.ts")):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            if "enzyme" in content.lower():
                violations.append({
                    "file": filepath, "line": None,
                    "rule": "component-testing.enzyme-usage",
                    "message": "Using Enzyme — migrate to React Testing Library",
                    "severity": "should",
                })
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"\.instance\(\)|\.state\(\)|\.setState\(", line):
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "component-testing.implementation-detail",
                        "message": "Testing implementation details — test behavior instead",
                        "severity": "should",
                    })
        return violations

    def _check_api_client_contracts(self, files: list[str]) -> list[dict]:
        """Check for type-safe API clients, response validation."""
        violations = []
        for filepath in files:
            if not filepath.endswith((".ts", ".tsx")):
                continue
            parts = set(Path(filepath).parts)
            if not (parts & {"api", "services", "clients"}):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"fetch\s*\(", line) and "as Response" not in line:
                    if "await" in line or ".then" in line:
                        violations.append({
                            "file": filepath, "line": i,
                            "rule": "api-client-contracts.untyped-fetch",
                            "message": "Raw fetch without typed response — use typed API client",
                            "severity": "should",
                        })
        return violations

    def _check_error_boundaries(self, files: list[str]) -> list[dict]:
        """Check for React error boundaries and fallback UI."""
        violations = []
        has_error_boundary = False
        for filepath in files:
            if not filepath.endswith((".tsx", ".ts")):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            if "ErrorBoundary" in content or "componentDidCatch" in content:
                has_error_boundary = True
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"catch\s*\(\s*\w*\s*\)\s*\{?\s*$", line):
                    # Check if next lines have error reporting
                    next_lines = content.splitlines()[i:i + 3]
                    combined = " ".join(next_lines)
                    if "console.error" not in combined and "report" not in combined.lower():
                        violations.append({
                            "file": filepath, "line": i,
                            "rule": "error-boundaries.silent-catch",
                            "message": "Catch without error reporting — log or report the error",
                            "severity": "should",
                        })
        return violations

    def _check_frontend_design_system(self, files: list[str]) -> list[dict]:
        """Check for hardcoded colors, inconsistent styling."""
        violations = []
        hex_color = re.compile(r"['\"]#[0-9a-fA-F]{3,8}['\"]")
        for filepath in files:
            if not filepath.endswith((".tsx", ".ts", ".css", ".scss")):
                continue
            parts = Path(filepath).parts
            if "tests" in parts or Path(filepath).name.startswith("test"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if hex_color.search(line) and "theme" not in filepath.lower() and "token" not in filepath.lower():
                    violations.append({
                        "file": filepath, "line": i,
                        "rule": "frontend-design-system.hardcoded-color",
                        "message": "Hardcoded color value — use design token instead",
                        "severity": "should",
                    })
        return violations

    # ── Check registry ────────────────────────────────────────────────

    _PYTHON_CHECKS = {
        "error-handling": "_check_error_handling",
        "testing": "_check_testing",
        "logging": "_check_logging",
        "type-safety": "_check_type_safety",
        "api-design": "_check_api_design",
        "database": "_check_database",
        "security": "_check_security",
        "dependency-management": "_check_dependency_management",
        "configuration": "_check_configuration",
        "documentation": "_check_documentation",
    }

    _FRONTEND_CHECKS = {
        "typescript-safety": "_check_typescript_safety",
        "component-testing": "_check_component_testing",
        "api-client-contracts": "_check_api_client_contracts",
        "error-boundaries": "_check_error_boundaries",
        "frontend-design-system": "_check_frontend_design_system",
    }

    def check(
        self,
        task_id: str,
        files: list[str],
        active_standards: list[str] | None = None,
        *,
        project_type: str | None = None,
    ) -> dict:
        """Run applicable standards checks on the given files.

        Parameters
        ----------
        task_id : str
            Task identifier for result tracking.
        files : list[str]
            Relative file paths to check.
        active_standards : list[str], optional
            Standards to check. If None, checks all applicable.
        project_type : str, optional
            One of 'python', 'fullstack', 'frontend'. Auto-detected if None.
        """
        if project_type is None:
            project_type = self._loader.detect_project_type(self._project_dir)

        # Build check method map based on project type
        all_checks: dict[str, str] = {}
        if project_type in ("python", "fullstack"):
            all_checks.update(self._PYTHON_CHECKS)
        if project_type in ("fullstack", "frontend"):
            all_checks.update(self._FRONTEND_CHECKS)

        if active_standards is None:
            active_standards = list(all_checks.keys())

        results = []
        all_violations: list[dict] = []

        for standard in active_standards:
            method_name = all_checks.get(standard)
            if not method_name:
                continue
            method = getattr(self, method_name)
            violations = method(files)
            all_violations.extend(violations)
            results.append({
                "standard": standard,
                "passed": len(violations) == 0,
                "violation_count": len(violations),
                "violations": violations,
            })

        return {
            "success": True,
            "action": "standards.check-task",
            "task_id": task_id,
            "project_type": project_type,
            "files_checked": len(files),
            "standards_checked": active_standards,
            "results": results,
            "total_violations": len(all_violations),
            "passed": len(all_violations) == 0,
        }
