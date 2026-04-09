"""Sensor and effector data models for cUAS simulation."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


class SensorType(StrEnum):
    """Sensor detection modality."""

    RF = "RF"
    Radar = "Radar"
    EO_IR = "EO_IR"
    Acoustic = "Acoustic"


class EffectorType(StrEnum):
    """Effector defeat mechanism category."""

    RF_Jammer = "RF_Jammer"
    Kinetic = "Kinetic"
    Directed_Energy = "Directed_Energy"
    Cyber = "Cyber"


class SensorDefinition(BaseModel):
    """Capability template for a sensor type.

    Represents the physical and operational characteristics of a sensor in
    isolation — no placement or deployment position. Use SensorPlacement
    (models/scenario.py) to associate a SensorDefinition with a site position.

    All range values are in metres; arc values in degrees.
    """

    name: str
    """Human-readable sensor name (e.g. 'DroneShield RfOne Mk2')."""

    type: SensorType
    """Detection modality."""

    max_range_m: float
    """Maximum effective detection range in metres."""

    min_range_m: float = 0.0
    """Minimum effective detection range in metres (dead-zone radius)."""

    azimuth_coverage_deg: float
    """Horizontal field of regard in degrees (1–360)."""

    elevation_coverage_deg: float
    """Vertical field of regard in degrees (1–180). Arc width centred on
    ``elevation_boresight_deg``."""

    elevation_boresight_deg: float = 0.0
    """Centre of the sensor's elevation arc in degrees.
    0 = horizontal, positive = upward, negative = downward.
    The sensor detects targets whose elevation angle from the sensor falls
    within ``[boresight - coverage/2, boresight + coverage/2]``."""

    frequency_bands: list[str] = Field(default_factory=list)
    """RF/radar frequency bands monitored (e.g. ['2.4 GHz', '5.8 GHz'])."""

    requires_los: bool = True
    """Whether the sensor requires line-of-sight to the target."""

    mounting_height_m: float = 0.0
    """Default mounting height above ground in metres."""

    vegetation_penetration: float = 0.0
    """Fraction of signal that passes through a unit of canopy (0.0–1.0).

    Models Bouguer–Lambert attenuation through vegetation:
    - 0.0 = fully blocked by canopy (EO/IR sensors)
    - 0.2–0.4 = high attenuation (radar through dense foliage)
    - 0.6 = partial penetration (RF — drone control signals through light canopy)
    - 0.9 = near-transparent (acoustic — sound diffracts around/through foliage)
    - 1.0 = fully transparent (hypothetical — no attenuation)

    When ``site.canopy_height_m`` is present and this value is > 0, the
    viewshed engine applies per-cell attenuation proportional to canopy height.
    """

    cost_aud: float | None = None
    """Approximate unit cost in AUD. None if not disclosed."""

    @field_validator("name")
    @classmethod
    def _name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty or whitespace")
        return v

    @field_validator("max_range_m")
    @classmethod
    def _max_range_positive(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError(f"max_range_m must be > 0, got {v}")
        return v

    @field_validator("min_range_m")
    @classmethod
    def _min_range_non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"min_range_m must be >= 0, got {v}")
        return v

    @field_validator("azimuth_coverage_deg")
    @classmethod
    def _azimuth_valid(cls, v: float) -> float:
        if not (0.0 < v <= 360.0):
            raise ValueError(f"azimuth_coverage_deg must be in (0, 360], got {v}")
        return v

    @field_validator("elevation_coverage_deg")
    @classmethod
    def _elevation_valid(cls, v: float) -> float:
        if not (0.0 < v <= 180.0):
            raise ValueError(f"elevation_coverage_deg must be in (0, 180], got {v}")
        return v

    @field_validator("elevation_boresight_deg")
    @classmethod
    def _elevation_boresight_valid(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError(f"elevation_boresight_deg must be in [-90, 90], got {v}")
        return v

    @field_validator("mounting_height_m")
    @classmethod
    def _mounting_height_non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"mounting_height_m must be >= 0, got {v}")
        return v

    @field_validator("vegetation_penetration")
    @classmethod
    def _veg_penetration_valid(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"vegetation_penetration must be in [0, 1], got {v}")
        return v

    @field_validator("cost_aud")
    @classmethod
    def _cost_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0.0:
            raise ValueError(f"cost_aud must be >= 0, got {v}")
        return v

    @model_validator(mode="after")
    def _min_less_than_max(self) -> Self:
        if self.min_range_m >= self.max_range_m:
            raise ValueError(
                f"min_range_m ({self.min_range_m}) must be < max_range_m ({self.max_range_m})"
            )
        return self


class EffectorDefinition(BaseModel):
    """Capability template for an effector type.

    Represents the physical and operational characteristics of a defeat system
    in isolation — no placement or deployment position.

    All range values are in metres; arc values in degrees; times in seconds.
    """

    name: str
    """Human-readable effector name (e.g. 'DroneShield DroneCannon')."""

    type: EffectorType
    """Defeat mechanism category."""

    max_range_m: float
    """Maximum effective engagement range in metres."""

    min_range_m: float = 0.0
    """Minimum effective engagement range in metres."""

    engagement_arc_deg: float
    """Horizontal engagement arc in degrees (1–360)."""

    reaction_time_s: float
    """Time from detection to engagement in seconds (must be > 0)."""

    simultaneous_engagements: int = 1
    """Number of targets that can be engaged at the same time."""

    reload_time_s: float = 0.0
    """Time between successive engagements in seconds."""

    defeat_probability: float
    """Probability of defeating a target per engagement (0–1)."""

    requires_los: bool = True
    """Whether the effector requires line-of-sight to the target."""

    defeat_mechanism: str
    """Plain-English description of the defeat mechanism."""

    @field_validator("name")
    @classmethod
    def _name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty or whitespace")
        return v

    @field_validator("defeat_mechanism")
    @classmethod
    def _defeat_mechanism_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("defeat_mechanism must not be empty or whitespace")
        return v

    @field_validator("max_range_m")
    @classmethod
    def _max_range_positive(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError(f"max_range_m must be > 0, got {v}")
        return v

    @field_validator("min_range_m")
    @classmethod
    def _min_range_non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"min_range_m must be >= 0, got {v}")
        return v

    @field_validator("engagement_arc_deg")
    @classmethod
    def _arc_valid(cls, v: float) -> float:
        if not (0.0 < v <= 360.0):
            raise ValueError(f"engagement_arc_deg must be in (0, 360], got {v}")
        return v

    @field_validator("reaction_time_s")
    @classmethod
    def _reaction_time_positive(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError(f"reaction_time_s must be > 0, got {v}")
        return v

    @field_validator("simultaneous_engagements")
    @classmethod
    def _simultaneous_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"simultaneous_engagements must be >= 1, got {v}")
        return v

    @field_validator("reload_time_s")
    @classmethod
    def _reload_non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"reload_time_s must be >= 0, got {v}")
        return v

    @field_validator("defeat_probability")
    @classmethod
    def _defeat_prob_valid(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"defeat_probability must be in [0, 1], got {v}")
        return v

    @model_validator(mode="after")
    def _min_less_than_max(self) -> Self:
        if self.min_range_m >= self.max_range_m:
            raise ValueError(
                f"min_range_m ({self.min_range_m}) must be < max_range_m ({self.max_range_m})"
            )
        return self
