"""Scenario data models — sensor and effector placements on a site."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

_BEARING_MAX_DEG: float = 360.0  # exclusive upper bound for compass bearing


class SensorPlacement(BaseModel):
    """A single sensor deployed at a specific position and orientation on a site.

    Associates a sensor definition (by name) with a physical deployment:
    map coordinates, boresight bearing, and optional height override.

    Coordinates are in projected CRS units (metres). Bearing is a compass
    bearing (0 = north, 90 = east, 180 = south, 270 = west), clockwise.
    """

    sensor_name: str
    """Name of the sensor definition this placement refers to."""

    position_x: float
    """Easting of the sensor in CRS units (metres)."""

    position_y: float
    """Northing of the sensor in CRS units (metres)."""

    bearing_deg: float
    """Boresight direction as a compass bearing in degrees [0, 360)."""

    height_override_m: float | None = None
    """Override the sensor's default mounting height in metres. None = use sensor default."""

    @field_validator("sensor_name")
    @classmethod
    def _sensor_name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("sensor_name must not be empty or whitespace")
        return v

    @field_validator("bearing_deg")
    @classmethod
    def _bearing_valid(cls, v: float) -> float:
        if not (0.0 <= v < _BEARING_MAX_DEG):
            raise ValueError(f"bearing_deg must be in [0, 360), got {v}")
        return v

    @field_validator("height_override_m")
    @classmethod
    def _height_override_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0.0:
            raise ValueError(f"height_override_m must be >= 0, got {v}")
        return v
