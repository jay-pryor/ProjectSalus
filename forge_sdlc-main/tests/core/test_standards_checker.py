"""Tests for forge_core.standards_checker — 15 standards enforcement."""
import tempfile
from pathlib import Path

import pytest

from forge_core.standards_checker import StandardsChecker


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestErrorHandling:
    def test_bare_except_detected(self, project_dir):
        (project_dir / "bad.py").write_text("try:\n    pass\nexcept:\n    pass\n")
        checker = StandardsChecker(project_dir)
        result = checker.check("T01", ["bad.py"], ["error-handling"])
        violations = result["results"][0]["violations"]
        assert len(violations) >= 1
        assert violations[0]["rule"] == "error-handling.bare-except"

    def test_clean_code_passes(self, project_dir):
        (project_dir / "good.py").write_text(
            "try:\n    pass\nexcept ValueError as exc:\n    raise RuntimeError('x') from exc\n"
        )
        checker = StandardsChecker(project_dir)
        result = checker.check("T01", ["good.py"], ["error-handling"])
        assert result["results"][0]["passed"]


class TestSecurity:
    def test_hardcoded_secret_detected(self, project_dir):
        (project_dir / "bad.py").write_text('api_key = "sk-1234567890abcdef"\n')
        checker = StandardsChecker(project_dir)
        result = checker.check("T01", ["bad.py"], ["security"])
        violations = result["results"][0]["violations"]
        assert len(violations) >= 1
        assert violations[0]["rule"] == "security.hardcoded-secret"


class TestTypescriptSafety:
    def test_any_usage_detected(self, project_dir):
        (project_dir / "bad.ts").write_text("const x: any = 'test';\n")
        checker = StandardsChecker(project_dir)
        result = checker.check("T01", ["bad.ts"], ["typescript-safety"], project_type="frontend")
        violations = result["results"][0]["violations"]
        assert len(violations) >= 1
        assert violations[0]["rule"] == "typescript-safety.any-usage"


class TestProjectTypeDetection:
    def test_python_project(self, project_dir):
        (project_dir / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        checker = StandardsChecker(project_dir)
        result = checker.check("T01", [], project_type=None)
        assert result["project_type"] == "python"

    def test_fullstack_project(self, project_dir):
        (project_dir / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (project_dir / "package.json").write_text('{"name": "test"}\n')
        checker = StandardsChecker(project_dir)
        result = checker.check("T01", [], project_type=None)
        assert result["project_type"] == "fullstack"
