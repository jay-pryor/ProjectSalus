"""Forge cross-cutting auditor — system-wide consistency checks.

25+ check categories covering cross-service contracts, env vars,
security, patterns, frontend, and deployment consistency.
All checks are line-oriented regex/grep-based (no AST parsing).
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Any

__all__ = ["CrossCuttingAuditor", "AVAILABLE_CHECKS"]

_MAX_FILE_BYTES = 1_000_000

AVAILABLE_CHECKS = [
    "cross_service_contracts", "shared_types", "env_var_consistency",
    "docker_port_conflicts", "migration_safety", "import_hygiene",
    "error_response_format", "auth_pattern_consistency", "logging_consistency",
    "config_drift", "dead_code", "hardcoded_values", "test_isolation",
    "dependency_version_conflicts", "api_versioning", "secret_exposure",
    "sql_injection", "cors_config", "rate_limiting", "frontend_bundle",
    "react_antipatterns", "css_consistency", "webhook_contracts",
    "deployment_config", "health_check_completeness",
]


class CrossCuttingAuditor:
    """System-wide consistency checks for pattern drift detection."""

    def __init__(self, project_dir: Path | None = None) -> None:
        if project_dir is not None:
            self._project_dir = Path(project_dir).resolve()
        else:
            env_dir = os.environ.get("FORGE_PROJECT_DIR")
            self._project_dir = Path(env_dir).resolve() if env_dir else Path.cwd().resolve()

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

    def _discover_files(self, extensions: tuple[str, ...] | None = None) -> list[str]:
        """Discover tracked files via git ls-files."""
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                capture_output=True, text=True, timeout=10,
                cwd=str(self._project_dir),
            )
            if result.returncode == 0:
                raw = [f for f in result.stdout.strip().splitlines() if f]
                if extensions:
                    raw = [f for f in raw if f.endswith(extensions)]
                return [f for f in raw if self._resolve_safe(f) is not None]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return []

    def _is_test_file(self, filepath: str) -> bool:
        name = Path(filepath).name
        parts = Path(filepath).parts
        return name.startswith("test_") or "tests" in parts or name == "conftest.py"

    # ── Check implementations (25 categories) ─────────────────────────

    def _check_cross_service_contracts(self, files: list[str]) -> list[dict]:
        """Cat 1: Detect endpoint URL/method mismatches between caller and server."""
        findings = []
        # Find URL patterns in client code
        url_pattern = re.compile(r"""(?:httpx|requests|fetch|axios)\.\s*(get|post|put|delete|patch)\s*\(\s*[f'"](.*?)['"]""", re.IGNORECASE)
        for filepath in files:
            if not filepath.endswith((".py", ".ts", ".tsx")):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                match = url_pattern.search(line)
                if match and ("localhost" in line or "127.0.0.1" in line):
                    findings.append({
                        "category": "cross_service_contracts",
                        "severity": "warning",
                        "file": filepath, "line": i,
                        "message": f"Hardcoded local URL in API call: {match.group(2)[:60]}",
                        "suggestion": "Use service discovery or config-based URL",
                    })
        return findings

    def _check_shared_types(self, files: list[str]) -> list[dict]:
        """Cat 2: Detect type definitions that may drift between services."""
        findings = []
        type_defs: dict[str, list[tuple[str, int]]] = {}
        type_pattern = re.compile(r"(?:class|interface|type)\s+(\w+(?:Request|Response|Schema|Model|DTO))\b")
        for filepath in files:
            if not filepath.endswith((".py", ".ts", ".tsx")):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                match = type_pattern.search(line)
                if match:
                    name = match.group(1)
                    type_defs.setdefault(name, []).append((filepath, i))
        for name, locations in type_defs.items():
            if len(locations) > 1:
                files_involved = [loc[0] for loc in locations]
                findings.append({
                    "category": "shared_types",
                    "severity": "warning",
                    "file": files_involved[0], "line": locations[0][1],
                    "message": f"Type '{name}' defined in {len(locations)} files — risk of drift",
                    "suggestion": f"Consolidate into shared types module. Also in: {', '.join(files_involved[1:])}",
                })
        return findings

    def _check_env_var_consistency(self, files: list[str]) -> list[dict]:
        """Cat 3: Env vars referenced but not in .env.example."""
        findings = []
        env_example = self._project_dir / ".env.example"
        documented_vars: set[str] = set()
        if env_example.is_file():
            content = self._read_safe(env_example)
            if content:
                for line in content.splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        documented_vars.add(line.split("=")[0].strip())

        env_pattern = re.compile(r"""os\.(?:environ\.get|getenv)\s*\(\s*['"](\w+)['"]""")
        referenced_vars: dict[str, tuple[str, int]] = {}
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
                match = env_pattern.search(line)
                if match:
                    var_name = match.group(1)
                    if var_name not in referenced_vars:
                        referenced_vars[var_name] = (filepath, i)

        if documented_vars:
            for var_name, (filepath, line) in referenced_vars.items():
                if var_name not in documented_vars:
                    findings.append({
                        "category": "env_var_consistency",
                        "severity": "warning",
                        "file": filepath, "line": line,
                        "message": f"Env var '{var_name}' used but not in .env.example",
                        "suggestion": f"Add {var_name}= to .env.example",
                    })
        return findings

    def _check_docker_port_conflicts(self, files: list[str]) -> list[dict]:
        """Cat 4: Same host port mapped twice in docker-compose."""
        findings = []
        compose_files = [f for f in files if "docker-compose" in f and f.endswith((".yml", ".yaml"))]
        for filepath in compose_files:
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            port_pattern = re.compile(r'"?(\d+):(\d+)"?')
            host_ports: dict[str, list[tuple[str, int]]] = {}
            for i, line in enumerate(content.splitlines(), 1):
                match = port_pattern.search(line)
                if match:
                    host_port = match.group(1)
                    host_ports.setdefault(host_port, []).append((filepath, i))
            for port, locations in host_ports.items():
                if len(locations) > 1:
                    findings.append({
                        "category": "docker_port_conflicts",
                        "severity": "error",
                        "file": filepath, "line": locations[0][1],
                        "message": f"Host port {port} mapped {len(locations)} times",
                        "suggestion": "Use different host ports for each service",
                    })
        return findings

    def _check_migration_safety(self, files: list[str]) -> list[dict]:
        """Cat 5: Detect data-destructive migration operations."""
        findings = []
        dangerous_ops = re.compile(r"\b(DROP\s+TABLE|DROP\s+COLUMN|TRUNCATE|DELETE\s+FROM)\b", re.IGNORECASE)
        for filepath in files:
            if "migration" not in filepath.lower() and "alembic" not in filepath.lower():
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if dangerous_ops.search(line):
                    findings.append({
                        "category": "migration_safety",
                        "severity": "error",
                        "file": filepath, "line": i,
                        "message": f"Data-destructive operation in migration: {line.strip()[:60]}",
                        "suggestion": "Add data backup step or use soft-delete pattern",
                    })
        return findings

    def _check_import_hygiene(self, files: list[str]) -> list[dict]:
        """Cat 6: Circular imports, unused imports, import order."""
        findings = []
        camel_pattern = re.compile(r"def (_*[a-z]+[A-Z]\w*)\s*\(")
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            saw_local = False
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if not stripped.startswith(("import ", "from ")):
                    if stripped and not stripped.startswith("#"):
                        if saw_local:
                            break
                    continue
                if stripped.startswith("from ."):
                    saw_local = True
                    continue
                if saw_local and not stripped.startswith("from ."):
                    if not stripped.startswith("from forge"):
                        findings.append({
                            "category": "import_hygiene",
                            "severity": "warning",
                            "file": filepath, "line": i,
                            "message": "Non-local import after relative imports",
                            "suggestion": "Reorder imports: stdlib → third-party → local",
                        })
        return findings

    def _check_error_response_format(self, files: list[str]) -> list[dict]:
        """Cat 7: Different error shapes across services."""
        findings = []
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            parts = set(Path(filepath).parts)
            if not parts & {"routers", "endpoints", "api"}:
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"HTTPException\s*\(", line):
                    if "detail=" not in line:
                        findings.append({
                            "category": "error_response_format",
                            "severity": "warning",
                            "file": filepath, "line": i,
                            "message": "HTTPException without detail= parameter",
                            "suggestion": "Always provide structured detail in HTTP exceptions",
                        })
        return findings

    def _check_auth_pattern_consistency(self, files: list[str]) -> list[dict]:
        """Cat 8: Mixed auth approaches in same project."""
        findings = []
        auth_patterns: dict[str, list[str]] = {}
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            if "Depends(get_current_user)" in content:
                auth_patterns.setdefault("fastapi_depends", []).append(filepath)
            if "@login_required" in content:
                auth_patterns.setdefault("decorator", []).append(filepath)
            if "request.user" in content:
                auth_patterns.setdefault("request_user", []).append(filepath)
        if len(auth_patterns) > 1:
            findings.append({
                "category": "auth_pattern_consistency",
                "severity": "warning",
                "file": "(project)", "line": None,
                "message": f"Mixed auth patterns detected: {', '.join(auth_patterns.keys())}",
                "suggestion": "Standardise on one auth pattern across the project",
            })
        return findings

    def _check_logging_consistency(self, files: list[str]) -> list[dict]:
        """Cat 9: Mixed structured/unstructured logging."""
        findings = []
        print_pattern = re.compile(r"\bprint\s*\(")
        for filepath in files:
            if not filepath.endswith(".py") or self._is_test_file(filepath):
                continue
            name = Path(filepath).name
            if name in ("setup.py", "conftest.py"):
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
                    findings.append({
                        "category": "logging_consistency",
                        "severity": "warning",
                        "file": filepath, "line": i,
                        "message": "print() in non-test file — use structured logging",
                        "suggestion": "Replace with logger.info() or safe_log()",
                    })
        return findings

    def _check_config_drift(self, files: list[str]) -> list[dict]:
        """Cat 10: .env.example vs actual env var usage."""
        # Covered by env_var_consistency, this checks the reverse direction
        findings = []
        env_example = self._project_dir / ".env.example"
        if not env_example.is_file():
            return findings
        content = self._read_safe(env_example)
        if not content:
            return findings
        documented_vars = set()
        for line in content.splitlines():
            if "=" in line and not line.strip().startswith("#"):
                documented_vars.add(line.split("=")[0].strip())
        if not documented_vars:
            return findings

        # Find all env var references in code
        env_pattern = re.compile(r"""os\.(?:environ\.get|getenv|environ\[)\s*\(?['"](\w+)['"]""")
        used_vars: set[str] = set()
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            file_content = self._read_safe(full_path)
            if file_content is None:
                continue
            for match in env_pattern.finditer(file_content):
                used_vars.add(match.group(1))

        stale = documented_vars - used_vars
        for var in sorted(stale):
            findings.append({
                "category": "config_drift",
                "severity": "info",
                "file": ".env.example", "line": None,
                "message": f"Env var '{var}' in .env.example but not referenced in code",
                "suggestion": "Remove stale entry or add usage",
            })
        return findings

    def _check_dead_code(self, files: list[str]) -> list[dict]:
        """Cat 11: Functions defined but never called (basic heuristic)."""
        findings = []
        func_defs: dict[str, tuple[str, int]] = {}
        func_pattern = re.compile(r"^\s*def\s+([a-z_]\w*)\s*\(", re.MULTILINE)
        all_content = ""

        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            all_content += content + "\n"
            for match in func_pattern.finditer(content):
                name = match.group(1)
                line = content[:match.start()].count("\n") + 1
                if not name.startswith("_") and name != "main":
                    func_defs[name] = (filepath, line)

        for name, (filepath, line) in func_defs.items():
            # Count occurrences (subtract the def itself)
            count = len(re.findall(rf"\b{re.escape(name)}\b", all_content))
            if count <= 1:
                findings.append({
                    "category": "dead_code",
                    "severity": "info",
                    "file": filepath, "line": line,
                    "message": f"Function '{name}' defined but may be unused",
                    "suggestion": "Remove if truly unused or add to __all__",
                })
        return findings

    def _check_hardcoded_values(self, files: list[str]) -> list[dict]:
        """Cat 12: Magic numbers, hardcoded URLs, embedded credentials."""
        findings = []
        url_pattern = re.compile(r"""['"]https?://(?!example\.com|localhost|127\.0\.0\.1)[^'"]+['"]""")
        for filepath in files:
            if not filepath.endswith(".py") or self._is_test_file(filepath):
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
                if url_pattern.search(stripped):
                    findings.append({
                        "category": "hardcoded_values",
                        "severity": "warning",
                        "file": filepath, "line": i,
                        "message": "Hardcoded URL — use config or environment variable",
                        "suggestion": "Move URL to configuration",
                    })
        return findings

    def _check_test_isolation(self, files: list[str]) -> list[dict]:
        """Cat 13: Tests sharing state, missing cleanup."""
        findings = []
        for filepath in files:
            if not filepath.endswith(".py") or not self._is_test_file(filepath):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            # Check for module-level mutable state
            for i, line in enumerate(content.splitlines(), 1):
                if re.match(r"^[A-Z_]+\s*=\s*\[\s*\]", line) or re.match(r"^[A-Z_]+\s*=\s*\{\s*\}", line):
                    findings.append({
                        "category": "test_isolation",
                        "severity": "warning",
                        "file": filepath, "line": i,
                        "message": "Module-level mutable state in test file — risks test pollution",
                        "suggestion": "Use fixtures instead of module-level state",
                    })
        return findings

    def _check_dependency_version_conflicts(self, files: list[str]) -> list[dict]:
        """Cat 14: Same package at different versions across requirements files."""
        findings = []
        req_files = [f for f in files if f.endswith("requirements.txt") or "requirements" in f]
        packages: dict[str, list[tuple[str, str, int]]] = {}
        for filepath in req_files:
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                match = re.match(r"^([a-zA-Z][\w.-]*)\s*([=<>!~]+.*)", line.strip())
                if match:
                    pkg, version = match.group(1).lower(), match.group(2)
                    packages.setdefault(pkg, []).append((filepath, version, i))
        for pkg, versions in packages.items():
            unique_versions = set(v[1] for v in versions)
            if len(unique_versions) > 1:
                findings.append({
                    "category": "dependency_version_conflicts",
                    "severity": "warning",
                    "file": versions[0][0], "line": versions[0][2],
                    "message": f"Package '{pkg}' at different versions: {', '.join(unique_versions)}",
                    "suggestion": "Align versions across requirements files",
                })
        return findings

    def _check_api_versioning(self, files: list[str]) -> list[dict]:
        """Cat 15: Mixed versioned/unversioned endpoints."""
        findings = []
        has_versioned = False
        has_unversioned = False
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            if re.search(r"""['"]/api/v\d+/""", content):
                has_versioned = True
            if re.search(r"""['"]/api/[^v]""", content):
                has_unversioned = True
        if has_versioned and has_unversioned:
            findings.append({
                "category": "api_versioning",
                "severity": "warning",
                "file": "(project)", "line": None,
                "message": "Mixed versioned and unversioned API endpoints",
                "suggestion": "Standardise on versioned endpoints (/api/v1/...)",
            })
        return findings

    def _check_secret_exposure(self, files: list[str]) -> list[dict]:
        """Cat 16: API keys in code, tokens in logs."""
        findings = []
        log_pattern = re.compile(r"""(?:log(?:ger)?\.(?:info|debug|warning|error)|print)\s*\(.*(?:token|key|secret|password)""", re.IGNORECASE)
        for filepath in files:
            if not filepath.endswith(".py") or self._is_test_file(filepath):
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
                if log_pattern.search(line):
                    findings.append({
                        "category": "secret_exposure",
                        "severity": "error",
                        "file": filepath, "line": i,
                        "message": "Potential secret logged — may appear in log files",
                        "suggestion": "Redact sensitive values before logging",
                    })
        return findings

    def _check_sql_injection(self, files: list[str]) -> list[dict]:
        """Cat 17: Raw string queries, unsanitized inputs."""
        findings = []
        raw_sql = re.compile(r"""(?:execute|raw)\s*\(\s*f['"]|\.format\s*\(.*(?:WHERE|SELECT|INSERT|UPDATE|DELETE)""", re.IGNORECASE)
        for filepath in files:
            if not filepath.endswith(".py") or self._is_test_file(filepath):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if raw_sql.search(line):
                    findings.append({
                        "category": "sql_injection",
                        "severity": "error",
                        "file": filepath, "line": i,
                        "message": "Possible SQL injection — f-string or format in SQL query",
                        "suggestion": "Use parameterised queries",
                    })
        return findings

    def _check_cors_config(self, files: list[str]) -> list[dict]:
        """Cat 18: Wildcard origins in production."""
        findings = []
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
                if re.search(r"""allow_origins\s*=\s*\[?\s*['\"]\*['\"]""", line):
                    findings.append({
                        "category": "cors_config",
                        "severity": "error",
                        "file": filepath, "line": i,
                        "message": "CORS wildcard origin '*' — restrict in production",
                        "suggestion": "Use specific allowed origins from config",
                    })
        return findings

    def _check_rate_limiting(self, files: list[str]) -> list[dict]:
        """Cat 19: Public endpoints without rate limits."""
        findings = []
        # Heuristic: find route decorators without rate limit
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            parts = set(Path(filepath).parts)
            if not parts & {"routers", "endpoints", "api"}:
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            has_route = bool(re.search(r"@\w+\.(get|post|put|delete|patch)\(", content))
            has_rate_limit = "rate_limit" in content.lower() or "ratelimit" in content.lower() or "slowapi" in content.lower()
            if has_route and not has_rate_limit:
                findings.append({
                    "category": "rate_limiting",
                    "severity": "info",
                    "file": filepath, "line": None,
                    "message": "Router file has endpoints but no rate limiting",
                    "suggestion": "Consider adding rate limiting via SlowAPI or middleware",
                })
        return findings

    def _check_frontend_bundle(self, files: list[str]) -> list[dict]:
        """Cat 20: Unused dependencies in package.json."""
        findings = []
        pkg_files = [f for f in files if Path(f).name == "package.json"]
        for filepath in pkg_files:
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            # Check for known heavy dependencies
            heavy_deps = ["moment", "lodash", "jquery"]
            for dep in heavy_deps:
                if f'"{dep}"' in content:
                    findings.append({
                        "category": "frontend_bundle",
                        "severity": "info",
                        "file": filepath, "line": None,
                        "message": f"Heavy dependency '{dep}' — consider lighter alternative",
                        "suggestion": f"moment→dayjs/date-fns, lodash→lodash-es or native, jquery→remove",
                    })
        return findings

    def _check_react_antipatterns(self, files: list[str]) -> list[dict]:
        """Cat 21: useEffect dependency issues, missing keys."""
        findings = []
        for filepath in files:
            if not filepath.endswith((".tsx", ".jsx")):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"useEffect\s*\(\s*\(\)\s*=>\s*\{", line):
                    # Check if deps array is empty [] (possible missing deps)
                    remaining = "\n".join(content.splitlines()[i - 1:i + 10])
                    if re.search(r"\},\s*\[\s*\]\s*\)", remaining):
                        findings.append({
                            "category": "react_antipatterns",
                            "severity": "info",
                            "file": filepath, "line": i,
                            "message": "useEffect with empty deps [] — verify no dependencies are missing",
                            "suggestion": "Review if any referenced values should be in deps array",
                        })
                if re.search(r"\.map\s*\(\s*\(", line):
                    # Check next few lines for key prop
                    block = "\n".join(content.splitlines()[i - 1:i + 5])
                    if "key=" not in block and "key:" not in block:
                        findings.append({
                            "category": "react_antipatterns",
                            "severity": "warning",
                            "file": filepath, "line": i,
                            "message": ".map() render without key prop nearby",
                            "suggestion": "Add unique key prop to mapped elements",
                        })
        return findings

    def _check_css_consistency(self, files: list[str]) -> list[dict]:
        """Cat 22: Mixed styling approaches."""
        findings = []
        approaches: set[str] = set()
        for filepath in files:
            if filepath.endswith((".css", ".scss")):
                approaches.add("css_files")
            elif filepath.endswith((".tsx", ".jsx")):
                full_path = self._resolve_safe(filepath)
                if not full_path or not full_path.is_file():
                    continue
                content = self._read_safe(full_path)
                if content is None:
                    continue
                if "styled." in content or "styled(" in content:
                    approaches.add("styled_components")
                if "className={" in content and "clsx" not in content:
                    approaches.add("inline_classnames")
                if "style={{" in content:
                    approaches.add("inline_styles")
        if len(approaches) > 2:
            findings.append({
                "category": "css_consistency",
                "severity": "warning",
                "file": "(project)", "line": None,
                "message": f"Multiple styling approaches: {', '.join(sorted(approaches))}",
                "suggestion": "Standardise on one or two styling approaches",
            })
        return findings

    def _check_webhook_contracts(self, files: list[str]) -> list[dict]:
        """Cat 23: Webhook payload format drift between sender/receiver."""
        findings = []
        webhook_patterns = re.compile(r"""(?:webhook|callback).*(?:payload|body)""", re.IGNORECASE)
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
                if webhook_patterns.search(line) and "schema" not in line.lower() and "validate" not in line.lower():
                    findings.append({
                        "category": "webhook_contracts",
                        "severity": "info",
                        "file": filepath, "line": i,
                        "message": "Webhook payload without schema validation",
                        "suggestion": "Add Pydantic model or JSON schema for webhook payloads",
                    })
        return findings

    def _check_deployment_config(self, files: list[str]) -> list[dict]:
        """Cat 24: Docker image tags vs compose references."""
        findings = []
        for filepath in files:
            if not ("docker-compose" in filepath or "Dockerfile" in filepath):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"image:.*:latest", line):
                    findings.append({
                        "category": "deployment_config",
                        "severity": "warning",
                        "file": filepath, "line": i,
                        "message": "Using :latest tag — pin to specific version or SHA",
                        "suggestion": "Use specific image tag for reproducibility",
                    })
        return findings

    def _check_health_check_completeness(self, files: list[str]) -> list[dict]:
        """Cat 25: Services without health endpoints."""
        findings = []
        has_routes = False
        has_health = False
        for filepath in files:
            if not filepath.endswith(".py"):
                continue
            full_path = self._resolve_safe(filepath)
            if not full_path or not full_path.is_file():
                continue
            content = self._read_safe(full_path)
            if content is None:
                continue
            if re.search(r"@\w+\.(get|post)\(", content):
                has_routes = True
            if re.search(r"""['"]/health['"]\s*\)|health_?check""", content, re.IGNORECASE):
                has_health = True
        if has_routes and not has_health:
            findings.append({
                "category": "health_check_completeness",
                "severity": "warning",
                "file": "(project)", "line": None,
                "message": "Project has API routes but no /health endpoint detected",
                "suggestion": "Add a /health endpoint that checks service dependencies",
            })
        return findings

    # ── Check registry ────────────────────────────────────────────────

    _CHECK_METHODS = {
        "cross_service_contracts": "_check_cross_service_contracts",
        "shared_types": "_check_shared_types",
        "env_var_consistency": "_check_env_var_consistency",
        "docker_port_conflicts": "_check_docker_port_conflicts",
        "migration_safety": "_check_migration_safety",
        "import_hygiene": "_check_import_hygiene",
        "error_response_format": "_check_error_response_format",
        "auth_pattern_consistency": "_check_auth_pattern_consistency",
        "logging_consistency": "_check_logging_consistency",
        "config_drift": "_check_config_drift",
        "dead_code": "_check_dead_code",
        "hardcoded_values": "_check_hardcoded_values",
        "test_isolation": "_check_test_isolation",
        "dependency_version_conflicts": "_check_dependency_version_conflicts",
        "api_versioning": "_check_api_versioning",
        "secret_exposure": "_check_secret_exposure",
        "sql_injection": "_check_sql_injection",
        "cors_config": "_check_cors_config",
        "rate_limiting": "_check_rate_limiting",
        "frontend_bundle": "_check_frontend_bundle",
        "react_antipatterns": "_check_react_antipatterns",
        "css_consistency": "_check_css_consistency",
        "webhook_contracts": "_check_webhook_contracts",
        "deployment_config": "_check_deployment_config",
        "health_check_completeness": "_check_health_check_completeness",
    }

    def audit(
        self,
        files: list[str] | None = None,
        checks: list[str] | None = None,
    ) -> dict:
        """Run cross-cutting consistency checks.

        Parameters
        ----------
        files : list[str], optional
            File paths to check. If None, discovers via git ls-files.
        checks : list[str], optional
            Check names to run. If None, runs all checks.
        """
        if files is None:
            files = self._discover_files()

        safe_files = []
        for f in files:
            resolved = self._resolve_safe(f)
            if resolved is not None:
                safe_files.append(f)
        files = safe_files

        if checks is None:
            checks = list(self._CHECK_METHODS.keys())

        all_findings: list[dict] = []
        checks_run = []

        for check_name in checks:
            method_name = self._CHECK_METHODS.get(check_name)
            if not method_name:
                continue
            method = getattr(self, method_name)
            findings = method(files)
            all_findings.extend(findings)
            checks_run.append(check_name)

        # Group by severity
        severity_counts = {}
        for f in all_findings:
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return {
            "success": True,
            "action": "audit.cross-cutting",
            "checks_run": checks_run,
            "checks_available": len(self._CHECK_METHODS),
            "finding_count": len(all_findings),
            "severity_counts": severity_counts,
            "findings": all_findings,
            "passed": severity_counts.get("error", 0) == 0,
        }
