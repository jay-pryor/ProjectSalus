"""Saturation analysis data models (S8).

Models for multi-target engagement and saturation analysis.  A saturation
scenario describes a set of simultaneous drone threats approaching from
different vectors; the analysis determines when the defender's effector
network becomes overwhelmed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, field_validator

_BEARING_MAX_DEG: float = 360.0  # exclusive upper bound for compass bearing
_MIN_DISTANCE_M: float = 0.0  # exclusive lower bound for approach distance


class PriorityRule(StrEnum):
    """Target engagement priority ordering rule.

    Determines which targets are engaged first when effector capacity is limited.
    """

    CLOSEST_TO_ASSET = "CLOSEST_TO_ASSET"
    """Engage threats nearest the protected asset first (smallest distance_m)."""

    HIGHEST_THREAT = "HIGHEST_THREAT"
    """Engage fastest-moving threats first (largest speed_ms)."""

    USER_DEFINED = "USER_DEFINED"
    """Preserve the order in which targets were specified."""


class ApproachVector(BaseModel):
    """Direction and distance of a threat approach relative to the protected asset.

    ``bearing_deg`` is the compass bearing of the drone's flight path (towards
    the asset).  ``distance_m`` is how far the drone is from the asset along
    that bearing when the scenario begins.
    """

    bearing_deg: float
    """Compass bearing of approach (towards asset), in degrees [0, 360)."""

    distance_m: float
    """Distance from the protected asset in metres (> 0)."""

    @field_validator("bearing_deg")
    @classmethod
    def _bearing_valid(cls, v: float) -> float:
        if not math.isfinite(v) or not (0.0 <= v < _BEARING_MAX_DEG):
            raise ValueError(f"bearing_deg must be a finite value in [0, 360), got {v}")
        return v

    @field_validator("distance_m")
    @classmethod
    def _distance_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= _MIN_DISTANCE_M:
            raise ValueError(f"distance_m must be a finite value > 0, got {v}")
        return v


class SaturationTarget(BaseModel):
    """A single simultaneous threat in a saturation scenario.

    Each target is placed at a specific approach vector relative to the
    protected asset, flying at a given altitude and speed.
    """

    approach_vector: ApproachVector
    """Direction and distance from the protected asset."""

    altitude_m: float
    """Drone flight altitude AGL in metres (>= 0)."""

    speed_ms: float
    """Drone approach speed in metres per second (> 0)."""

    threat_profile_ref: str = ""
    """Name of the threat profile this target represents (informational)."""

    @field_validator("altitude_m")
    @classmethod
    def _altitude_non_negative(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0.0:
            raise ValueError(f"altitude_m must be a finite value >= 0, got {v}")
        return v

    @field_validator("speed_ms")
    @classmethod
    def _speed_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError(f"speed_ms must be a finite value > 0, got {v}")
        return v


class SaturationScenario(BaseModel):
    """A multi-target simultaneous engagement scenario.

    Groups a set of simultaneous threats with the priority rule used to
    determine which targets the defender engages first when capacity is limited.
    """

    targets: list[SaturationTarget]
    """Simultaneous threat targets.  At least one required."""

    priority_rule: PriorityRule = PriorityRule.CLOSEST_TO_ASSET
    """Engagement priority ordering rule."""

    @field_validator("targets")
    @classmethod
    def _targets_non_empty(cls, v: list[SaturationTarget]) -> list[SaturationTarget]:
        if not v:
            raise ValueError("targets must not be empty — at least one target is required")
        return v


@dataclass(frozen=True)
class AllocationResult:
    """Outcome of a single effector allocation pass for a saturation scenario.

    Attributes:
        engaged_indices: Indices (into the scenario's target list) of targets
            that were successfully assigned to an effector.
        unengaged_indices: Indices of targets that could not be assigned
            (no effector available, out of range, no LOS, or capacity
            exhausted).
        assignments: Mapping from target index to the name of the effector
            assigned to defeat it.
    """

    engaged_indices: list[int]
    unengaged_indices: list[int]
    assignments: dict[int, str]


@dataclass(frozen=True)
class SaturationResult:
    """Summary of a saturation threshold sweep.

    Attributes:
        simultaneous_engagement_capacity: Total simultaneous engagement slots
            across all effector placements (sum of simultaneous_engagements
            across all placements).
        saturation_threshold_n: The smallest target count N at which at least
            one target goes unengaged.  Equal to ``max_targets + 1`` when the
            threshold is never reached within the sweep.
        unengaged_count_at_threshold: Number of unengaged targets at
            ``saturation_threshold_n``.  0 if threshold was not reached.
        per_effector_utilisation: Fraction of each effector's capacity used
            at the last fully-handled scenario (threshold − 1, or
            ``max_targets`` when no saturation occurred).  Keys are effector
            names; values are in [0, 1].
    """

    simultaneous_engagement_capacity: int
    saturation_threshold_n: int
    unengaged_count_at_threshold: int
    per_effector_utilisation: dict[str, float]


@dataclass(frozen=True)
class ReengagementResult:
    """Summary of the temporal re-engagement capacity over a fixed window.

    Attributes:
        window_s: Length of the engagement window modelled (seconds).
        total_engagements_possible: Total target engagements possible across
            all effector placements within ``window_s``, accounting for
            reload time between shots and simultaneous engagement capacity.
        reengagement_cycle_time_s: Minimum engagement cycle time across all
            placements (reaction_time_s + reload_time_s for the fastest
            effector).
        per_effector_engagements: Number of engagements possible per effector
            name within ``window_s``.  Placements sharing a name are
            aggregated.
    """

    window_s: float
    total_engagements_possible: int
    reengagement_cycle_time_s: float
    per_effector_engagements: dict[str, int]
