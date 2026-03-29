"""Tests for forge_core.evidence — gate-proofs and review recording."""
import tempfile
from pathlib import Path

import pytest
import yaml

from forge_core.evidence import EvidenceManager, DEFAULT_REQUIRED_AGENTS


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir)
        forge_dir = d / ".forge"
        forge_dir.mkdir()
        gate_proofs = forge_dir / "gate-proofs"
        gate_proofs.mkdir()
        evidence_dir = d / "evidence"
        evidence_dir.mkdir()
        yield d


@pytest.fixture
def mgr(project_dir):
    return EvidenceManager(project_dir)


@pytest.fixture
def gate_proofs_dir(project_dir):
    return project_dir / ".forge" / "gate-proofs"


class TestRecordReviewAgent:
    def test_record_first_agent(self, mgr, gate_proofs_dir):
        result = mgr.record_review_agent(
            task_id="S00.P01.T01",
            agent_name="spec_compliance",
            status="pass", findings=0, model="kimi-k2.5", duration_s=30,
        )
        assert result["success"]
        proof_file = gate_proofs_dir / "S00.P01.T01.yaml"
        assert proof_file.is_file()
        data = yaml.safe_load(proof_file.read_text())
        assert data["reviews"]["spec_compliance"]["status"] == "pass"

    def test_record_multiple_agents(self, mgr, gate_proofs_dir):
        mgr.record_review_agent(
            task_id="S00.P01.T01",
            agent_name="spec_compliance",
            status="pass", findings=0, model="kimi-k2.5", duration_s=30,
        )
        mgr.record_review_agent(
            task_id="S00.P01.T01",
            agent_name="silent_failure_hunter",
            status="pass", findings=1, model="gemini-3.2", duration_s=45,
            resolved=True,
        )
        data = yaml.safe_load((gate_proofs_dir / "S00.P01.T01.yaml").read_text())
        assert len(data["reviews"]) == 2


class TestEscapeHatch:
    def test_escape_hatch_creates_proof(self, mgr, gate_proofs_dir):
        result = mgr.record_escape_hatch(
            task_id="S00.P01.T01",
            reason="Blocking dependency not available for testing",
        )
        assert result["success"]
        data = yaml.safe_load((gate_proofs_dir / "S00.P01.T01.yaml").read_text())
        assert data["escape_hatch"] is True
        assert data["overall"] == "pass"

    def test_escape_hatch_short_reason_fails(self, mgr, gate_proofs_dir):
        result = mgr.record_escape_hatch(
            task_id="S00.P01.T01",
            reason="short",
        )
        assert not result["success"]


class TestVerifyReviewCompleteness:
    def test_incomplete_reviews(self, mgr, gate_proofs_dir):
        mgr.record_review_agent(
            task_id="S00.P01.T01",
            agent_name="spec_compliance",
            status="pass", findings=0, model="kimi-k2.5", duration_s=30,
        )
        result = mgr.verify_review_completeness("S00.P01.T01")
        assert not result["review_complete"]

    def test_complete_reviews(self, mgr, gate_proofs_dir):
        for agent in DEFAULT_REQUIRED_AGENTS:
            mgr.record_review_agent(
                task_id="S00.P01.T01",
                agent_name=agent,
                status="pass", findings=0, model="test", duration_s=10,
            )
        result = mgr.verify_review_completeness("S00.P01.T01")
        assert result["review_complete"]

    def test_escape_hatch_bypasses(self, mgr, gate_proofs_dir):
        mgr.record_escape_hatch(
            task_id="S00.P01.T01",
            reason="Legitimate reason for skipping review",
        )
        result = mgr.verify_review_completeness("S00.P01.T01")
        assert result["review_complete"]
