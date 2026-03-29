"""Tests for forge_core.cross_cutting — 25 check categories."""
import tempfile
from pathlib import Path

import pytest

from forge_core.cross_cutting import CrossCuttingAuditor, AVAILABLE_CHECKS


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir)
        # Init git repo for file discovery
        import subprocess
        subprocess.run(["git", "init"], cwd=str(d), capture_output=True)
        yield d


class TestCheckRegistry:
    def test_all_25_checks_registered(self):
        assert len(AVAILABLE_CHECKS) == 25

    def test_auditor_has_all_methods(self):
        auditor = CrossCuttingAuditor()
        for check in AVAILABLE_CHECKS:
            assert check in auditor._CHECK_METHODS


class TestLoggingConsistency:
    def test_print_detected(self, project_dir):
        src = project_dir / "app.py"
        src.write_text("def run():\n    print('hello')\n")
        import subprocess
        subprocess.run(["git", "add", "app.py"], cwd=str(project_dir), capture_output=True)

        auditor = CrossCuttingAuditor(project_dir)
        result = auditor.audit(files=["app.py"], checks=["logging_consistency"])
        assert result["finding_count"] >= 1


class TestSqlInjection:
    def test_fstring_sql_detected(self, project_dir):
        src = project_dir / "repo.py"
        src.write_text('def query(name):\n    db.execute(f"SELECT * FROM users WHERE name={name}")\n')
        auditor = CrossCuttingAuditor(project_dir)
        result = auditor.audit(files=["repo.py"], checks=["sql_injection"])
        assert result["finding_count"] >= 1


class TestDockerPortConflicts:
    def test_duplicate_port_detected(self, project_dir):
        compose = project_dir / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  web:\n    ports:\n      - '8080:80'\n"
            "  api:\n    ports:\n      - '8080:3000'\n"
        )
        auditor = CrossCuttingAuditor(project_dir)
        result = auditor.audit(files=["docker-compose.yml"], checks=["docker_port_conflicts"])
        assert result["finding_count"] >= 1


class TestAuditAll:
    def test_runs_all_checks(self, project_dir):
        auditor = CrossCuttingAuditor(project_dir)
        result = auditor.audit(files=[])
        assert result["success"]
        assert result["checks_available"] == 25
