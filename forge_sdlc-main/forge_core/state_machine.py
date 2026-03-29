"""Formal state machines for task, phase, and session lifecycles.

v1.0.0 improvements over v0.4.0:
- Added SKIPPED and REOPENED task states
- Added REOPENED phase state for post-completion fixes
- Transition validation includes entity labels in all paths
- replay_check supports filtering by entity_id
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"
    REOPENED = "reopened"


class PhaseStatus(str, Enum):
    PLANNING = "planning"
    PLAN_APPROVED = "plan_approved"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    REOPENED = "reopened"


class SessionStatus(str, Enum):
    ACTIVE = "in_progress"
    ENDED = "completed"
    INTERRUPTED = "interrupted"


TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.NOT_STARTED: {TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.SKIPPED},
    TaskStatus.IN_PROGRESS: {TaskStatus.COMPLETED, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.BLOCKED: {TaskStatus.IN_PROGRESS, TaskStatus.NOT_STARTED, TaskStatus.SKIPPED},
    TaskStatus.COMPLETED: {TaskStatus.REOPENED},
    TaskStatus.FAILED: {TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS},
    TaskStatus.SKIPPED: {TaskStatus.REOPENED, TaskStatus.NOT_STARTED},
    TaskStatus.REOPENED: {TaskStatus.IN_PROGRESS},
}

PHASE_TRANSITIONS: dict[PhaseStatus, set[PhaseStatus]] = {
    PhaseStatus.PLANNING: {PhaseStatus.PLAN_APPROVED, PhaseStatus.BLOCKED},
    PhaseStatus.PLAN_APPROVED: {PhaseStatus.IN_PROGRESS},
    PhaseStatus.IN_PROGRESS: {PhaseStatus.REVIEW, PhaseStatus.BLOCKED},
    PhaseStatus.REVIEW: {PhaseStatus.COMPLETED, PhaseStatus.IN_PROGRESS},
    PhaseStatus.COMPLETED: {PhaseStatus.REOPENED},
    PhaseStatus.BLOCKED: {PhaseStatus.PLANNING, PhaseStatus.IN_PROGRESS},
    PhaseStatus.REOPENED: {PhaseStatus.IN_PROGRESS},
}

SESSION_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.ACTIVE: {SessionStatus.ENDED, SessionStatus.INTERRUPTED},
    SessionStatus.ENDED: set(),
    SessionStatus.INTERRUPTED: {SessionStatus.ACTIVE},
}


@dataclass(frozen=True)
class TransitionResult:
    valid: bool
    from_status: str
    to_status: str
    error_code: str | None = None
    message: str | None = None


def _validate_transition(
    current: str,
    target: str,
    enum_class: type[Enum],
    transitions: dict[Any, set[Any]],
    label: str = "",
) -> TransitionResult:
    prefix = f"{label} " if label else ""
    try:
        current_enum = enum_class(current)
        target_enum = enum_class(target)
    except ValueError as e:
        return TransitionResult(
            valid=False,
            from_status=current,
            to_status=target,
            error_code="INVALID_STATUS",
            message=f"Unknown {prefix}status value: {e}",
        )

    allowed = transitions.get(current_enum, set())
    if target_enum not in allowed:
        return TransitionResult(
            valid=False,
            from_status=current,
            to_status=target,
            error_code="INVALID_TRANSITION",
            message=(
                f"Cannot transition {prefix}from '{current}' to '{target}'. "
                f"Allowed: {sorted(s.value for s in allowed) or 'none (terminal state)'}"
            ),
        )
    return TransitionResult(valid=True, from_status=current, to_status=target)


def validate_task_transition(current: str, target: str) -> TransitionResult:
    return _validate_transition(current, target, TaskStatus, TASK_TRANSITIONS, "task")


def validate_phase_transition(current: str, target: str) -> TransitionResult:
    return _validate_transition(current, target, PhaseStatus, PHASE_TRANSITIONS, "phase")


def validate_session_transition(current: str, target: str) -> TransitionResult:
    return _validate_transition(current, target, SessionStatus, SESSION_TRANSITIONS, "session")


def replay_check(
    events: list[dict],
    entity_type: str = "task",
    entity_id: str | None = None,
) -> list[dict]:
    """Detect historical illegal transitions from an event sequence.

    If entity_id is provided, only events matching that ID are checked.
    """
    validators = {
        "task": validate_task_transition,
        "phase": validate_phase_transition,
        "session": validate_session_transition,
    }
    if entity_type not in validators:
        raise ValueError(f"Unknown entity_type '{entity_type}'. Must be one of: {sorted(validators)}")

    validate = validators[entity_type]

    if entity_id is not None:
        events = [e for e in events if e.get("entity_id") == entity_id]

    violations = []
    for i in range(1, len(events)):
        prev_status = events[i - 1].get("status")
        curr_status = events[i].get("status")
        if prev_status is None or curr_status is None:
            violations.append({
                "event_index": i,
                "from": prev_status or "",
                "to": curr_status or "",
                "error_code": "MISSING_STATUS",
                "message": f"Event at index {i - 1 if prev_status is None else i} is missing a 'status' field.",
                "event": events[i],
            })
            continue
        if prev_status == curr_status:
            continue
        result = validate(prev_status, curr_status)
        if not result.valid:
            violations.append({
                "event_index": i,
                "from": prev_status,
                "to": curr_status,
                "error_code": result.error_code,
                "message": result.message,
                "event": events[i],
            })
    return violations
