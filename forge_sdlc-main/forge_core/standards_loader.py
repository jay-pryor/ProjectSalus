"""Forge standards loader — loads standard definitions from markdown files.

Standards are markdown fragments in the standards/ directory. Each defines
purpose, applicability, MUST/SHOULD rules, patterns, and verification.
Maps source files to applicable standards based on directory conventions.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = [
    "StandardsLoader",
    "FILE_STANDARD_MAP",
    "FRONTEND_FILE_STANDARD_MAP",
]

# Python file → standards mapping based on directory
FILE_STANDARD_MAP: dict[str, tuple[str, ...]] = {
    "routers/": ("api-design", "error-handling", "security"),
    "endpoints/": ("api-design", "error-handling", "security"),
    "api/": ("api-design", "error-handling", "security"),
    "services/": ("error-handling", "logging", "type-safety"),
    "models/": ("database", "type-safety", "testing"),
    "repositories/": ("database", "error-handling"),
    "migrations/": ("database",),
    "auth/": ("security", "error-handling", "testing"),
    "config/": ("configuration",),
    "settings/": ("configuration",),
    "tests/": ("testing",),
}

# Frontend file → standards mapping
FRONTEND_FILE_STANDARD_MAP: dict[str, tuple[str, ...]] = {
    "components/": ("typescript-safety", "component-testing", "frontend-design-system", "error-boundaries"),
    "pages/": ("typescript-safety", "component-testing", "error-boundaries"),
    "hooks/": ("typescript-safety", "component-testing"),
    "services/": ("typescript-safety", "api-client-contracts"),
    "api/": ("typescript-safety", "api-client-contracts"),
    "utils/": ("typescript-safety",),
    "types/": ("typescript-safety",),
    "styles/": ("frontend-design-system",),
    "__tests__/": ("component-testing",),
}


class StandardsLoader:
    """Load, parse, and query engineering standard fragments.

    Standard fragments are markdown files in a standards directory.
    Each follows a structured format with Purpose, Loaded for,
    MUST/SHOULD rules, Key Pattern, and Verification sections.
    """

    def __init__(self, standards_dir: Path | None = None) -> None:
        if standards_dir is None:
            self.standards_dir = Path(__file__).resolve().parent.parent / "standards"
        else:
            self.standards_dir = Path(standards_dir)

    def list_standards(self) -> dict:
        """List all available standard names."""
        if not self.standards_dir.is_dir():
            return {
                "success": True,
                "action": "standards.list",
                "standards": [],
                "count": 0,
            }
        names = sorted(p.stem for p in self.standards_dir.glob("*.md"))
        return {
            "success": True,
            "action": "standards.list",
            "standards": names,
            "count": len(names),
        }

    def load(self, name: str) -> dict:
        """Load and parse a single standard fragment by name."""
        filepath = self.standards_dir / f"{name}.md"
        if not filepath.is_file():
            return {
                "success": False,
                "action": "standards.load",
                "error": f"Standard '{name}' not found",
            }
        try:
            content = filepath.read_text(encoding="utf-8")
        except OSError as exc:
            return {
                "success": False,
                "action": "standards.load",
                "error": f"Cannot read standard '{name}': {exc}",
            }
        parsed = self._parse_fragment(content)
        return {
            "success": True,
            "action": "standards.load",
            "name": name,
            "standard": parsed,
        }

    def check_file(self, path: str, *, project_type: str = "python") -> dict:
        """Determine which standards apply to a file path.

        Parameters
        ----------
        path : str
            File path (relative or absolute) to check.
        project_type : str
            One of 'python', 'fullstack', 'frontend'.
        """
        normalised = path.replace("\\", "/")
        segments = set(normalised.split("/"))
        applicable: list[str] = []

        # Python standards for .py files
        if normalised.endswith(".py") and project_type in ("python", "fullstack"):
            for pattern, standards in FILE_STANDARD_MAP.items():
                segment = pattern.rstrip("/")
                if segment in segments:
                    for s in standards:
                        if s not in applicable:
                            applicable.append(s)

        # Frontend standards for TS/TSX/CSS files
        if project_type in ("fullstack", "frontend"):
            is_frontend = normalised.endswith((".ts", ".tsx", ".jsx", ".css", ".scss"))
            if is_frontend:
                for pattern, standards in FRONTEND_FILE_STANDARD_MAP.items():
                    segment = pattern.rstrip("/")
                    if segment in segments:
                        for s in standards:
                            if s not in applicable:
                                applicable.append(s)

        return {
            "success": True,
            "action": "standards.check",
            "file": path,
            "applicable_standards": applicable,
        }

    def detect_project_type(self, project_dir: Path) -> str:
        """Detect project type from filesystem markers."""
        has_python = (project_dir / "pyproject.toml").is_file() or (project_dir / "setup.py").is_file()
        has_frontend = (project_dir / "package.json").is_file() or (project_dir / "tsconfig.json").is_file()

        if has_python and has_frontend:
            return "fullstack"
        elif has_frontend:
            return "frontend"
        return "python"

    def _parse_fragment(self, content: str) -> dict:
        purpose = self._extract_blockquote_field(content, "Purpose")
        loaded_for = self._extract_blockquote_field(content, "Loaded for")
        must_rules = self._extract_numbered_list(content, "MUST Rules")
        should_rules = self._extract_numbered_list(content, "SHOULD Rules")
        key_pattern = self._extract_section(content, "Key Pattern")
        verification = self._extract_section(content, "Verification")
        return {
            "purpose": purpose,
            "loaded_for": loaded_for,
            "must_rules": must_rules,
            "should_rules": should_rules,
            "key_pattern": key_pattern,
            "verification": verification,
        }

    @staticmethod
    def _extract_blockquote_field(content: str, field: str) -> str:
        pattern = rf">\s*{re.escape(field)}:\s*(.+)"
        match = re.search(pattern, content)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_numbered_list(content: str, heading: str) -> list[str]:
        pattern = rf"##\s+{re.escape(heading)}\s*\n((?:\s*\d+\.\s+.+\n?)*)"
        match = re.search(pattern, content)
        if not match:
            return []
        block = match.group(1)
        return [item.strip() for item in re.findall(r"\d+\.\s+(.+)", block)]

    @staticmethod
    def _extract_section(content: str, heading: str) -> str:
        pattern = rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else ""
