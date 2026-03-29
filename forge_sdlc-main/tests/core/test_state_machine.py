"""Tests for forge_core.state_machine — state transitions."""
import pytest
from forge_core.state_machine import (
    TaskStatus, PhaseStatus,
    validate_task_transition, validate_phase_transition,
    replay_check,
)


class TestTaskTransitions:
    def test_not_started_to_in_progress(self):
        result = validate_task_transition(TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS)
        assert result.valid

    def test_in_progress_to_review_to_completed(self):
        result = validate_task_transition(TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED)
        assert result.valid

    def test_not_started_to_completed_invalid(self):
        result = validate_task_transition(TaskStatus.NOT_STARTED, TaskStatus.COMPLETED)
        assert not result.valid

    def test_in_progress_to_blocked(self):
        result = validate_task_transition(TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
        assert result.valid

    def test_blocked_to_in_progress(self):
        result = validate_task_transition(TaskStatus.BLOCKED, TaskStatus.IN_PROGRESS)
        assert result.valid

    def test_not_started_to_skipped(self):
        result = validate_task_transition(TaskStatus.NOT_STARTED, TaskStatus.SKIPPED)
        assert result.valid

    def test_completed_to_reopened(self):
        result = validate_task_transition(TaskStatus.COMPLETED, TaskStatus.REOPENED)
        assert result.valid

    def test_reopened_to_in_progress(self):
        result = validate_task_transition(TaskStatus.REOPENED, TaskStatus.IN_PROGRESS)
        assert result.valid

    def test_completed_to_in_progress_invalid(self):
        result = validate_task_transition(TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS)
        assert not result.valid

    def test_in_progress_to_skipped_invalid(self):
        result = validate_task_transition(TaskStatus.IN_PROGRESS, TaskStatus.SKIPPED)
        assert not result.valid


class TestPhaseTransitions:
    def test_planning_to_in_progress(self):
        result = validate_phase_transition(PhaseStatus.PLAN_APPROVED, PhaseStatus.IN_PROGRESS)
        assert result.valid

    def test_in_progress_to_review_to_completed(self):
        result = validate_phase_transition(PhaseStatus.IN_PROGRESS, PhaseStatus.REVIEW)
        assert result.valid
        result = validate_phase_transition(PhaseStatus.REVIEW, PhaseStatus.COMPLETED)
        assert result.valid

    def test_completed_to_reopened(self):
        result = validate_phase_transition(PhaseStatus.COMPLETED, PhaseStatus.REOPENED)
        assert result.valid


class TestReplayCheck:
    def test_replay_empty_events(self):
        history = replay_check([])
        assert isinstance(history, list)
        assert len(history) == 0

    def test_replay_with_events(self):
        events = [
            {"entity_type": "task", "entity_id": "T01", "from": "not_started", "to": "in_progress"},
            {"entity_type": "task", "entity_id": "T01", "from": "in_progress", "to": "completed"},
        ]
        history = replay_check(events)
        assert isinstance(history, list)
