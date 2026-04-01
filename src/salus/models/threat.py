"""Threat profile and corridor models for cUAS threat analysis."""

from __future__ import annotations

import math
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

_BEARING_MAX_DEG: float = 360.0  # exclusive upper bound for compass bearing
_MIN_WIDTH_M: float = 1.0  # minimum corridor width in metres
_MIN_DISTANCE_M: float = 0.0  # minimum corridor start distance in metres


class EvasionCapability(StrEnum):
    """Threat platform evasion / counter-detection capability level."""

    none = "none"
    """No evasion — predictable GPS-controlled flight, full RF emissions."""

    basic = "basic"
    """Basic evasion — pre-programmed waypoints, reduced RF emissions windows."""

    advanced = "advanced"
    """Advanced evasion — RF-silent autonomous flight, terrain-masking, GPS-denied."""


class ThreatProfile(BaseModel):
    """Capability template for a threat platform type.

    Captures the key detection-relevant characteristics of a drone type,
    independent of any specific approach direction or site.

    Speed is in metres per second. Altitude is AGL (above ground level)
    in metres. RCS (radar cross-section) is in square metres.
    """

    name: str
    """Human-readable threat name (e.g. 'DJI Mavic 3 — Low Slow')."""

    rcs_m2: float
    """Radar cross-section in m² (used by radar coverage assessment)."""

    rf_signature: str
    """Description of the RF signature, e.g. '2.4 GHz / 5.8 GHz control link'."""

    max_speed_ms: float
    """Maximum operational speed in metres per second."""

    typical_altitude_m: float
    """Typical operating altitude AGL in metres."""

    approach_vectors: list[str] = Field(default_factory=list)
    """Common approach directions for this threat type (informational only).

    Examples: ['NE', 'E', 'NW']. Used to annotate YAML profiles; the
    corridor analysis engine tests all bearings systematically.
    """

    evasion_capability: EvasionCapability = EvasionCapability.none
    """Counter-detection evasion capability level."""

    @field_validator("name")
    @classmethod
    def _name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty or whitespace")
        return v

    @field_validator("rf_signature")
    @classmethod
    def _rf_signature_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rf_signature must not be empty or whitespace")
        return v

    @field_validator("rcs_m2")
    @classmethod
    def _rcs_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError(f"rcs_m2 must be a finite value > 0, got {v}")
        return v

    @field_validator("max_speed_ms")
    @classmethod
    def _max_speed_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError(f"max_speed_ms must be a finite value > 0, got {v}")
        return v

    @field_validator("typical_altitude_m")
    @classmethod
    def _altitude_non_negative(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0.0:
            raise ValueError(f"typical_altitude_m must be a finite value >= 0, got {v}")
        return v


class ThreatCorridor(BaseModel):
    """A single drone approach corridor for coverage sampling.

    Defines one straight-line approach path from a start distance to the
    protected asset. The bearing is the direction *towards* the asset
    (i.e. the direction the drone is travelling).

    All distances are in metres; bearing in degrees.
    """

    bearing_deg: float
    """Compass bearing of approach (towards asset), in degrees [0, 360)."""

    altitude_m: float
    """Drone altitude AGL for this corridor in metres (>= 0)."""

    width_m: float = 50.0
    """Corridor width in metres used for sampling (>= 1)."""

    start_distance_m: float = 3000.0
    """Distance from the protected asset at which the corridor begins (>= 0)."""

    @field_validator("bearing_deg")
    @classmethod
    def _bearing_valid(cls, v: float) -> float:
        if not (0.0 <= v < _BEARING_MAX_DEG):
            raise ValueError(f"bearing_deg must be in [0, 360), got {v}")
        return v

    @field_validator("altitude_m")
    @classmethod
    def _altitude_non_negative(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0.0:
            raise ValueError(f"altitude_m must be a finite value >= 0, got {v}")
        return v

    @field_validator("width_m")
    @classmethod
    def _width_valid(cls, v: float) -> float:
        if not math.isfinite(v) or v < _MIN_WIDTH_M:
            raise ValueError(f"width_m must be a finite value >= {_MIN_WIDTH_M}, got {v}")
        return v

    @field_validator("start_distance_m")
    @classmethod
    def _start_distance_non_negative(cls, v: float) -> float:
        if not math.isfinite(v) or v < _MIN_DISTANCE_M:
            raise ValueError(f"start_distance_m must be a finite value >= 0, got {v}")
        return v
