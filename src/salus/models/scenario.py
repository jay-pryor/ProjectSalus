"""Scenario data models — placements and top-level scenario configuration."""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from salus.models.threat import DroneTrajectory

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


class EffectorPlacement(BaseModel):
    """A single effector deployed at a specific position and orientation on a site.

    Associates an effector definition (by name) with a physical deployment:
    map coordinates, boresight bearing, and optional height override.

    Coordinates are in projected CRS units (metres). Bearing is a compass
    bearing (0 = north, 90 = east, 180 = south, 270 = west), clockwise.
    """

    effector_name: str
    """Name of the effector definition this placement refers to."""

    position_x: float
    """Easting of the effector in CRS units (metres)."""

    position_y: float
    """Northing of the effector in CRS units (metres)."""

    bearing_deg: float
    """Boresight direction as a compass bearing in degrees [0, 360)."""

    height_override_m: float | None = None
    """Override the effector's default mounting height in metres. None = use effector default."""

    @field_validator("effector_name")
    @classmethod
    def _effector_name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("effector_name must not be empty or whitespace")
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


class ScenarioConfig(BaseModel):
    """Top-level configuration for a cUAS simulation scenario.

    Loaded from a YAML scenario file. Path fields are resolved relative to the
    scenario file's parent directory during loading (see load_scenario).

    All path fields store absolute, resolved paths after loading.
    """

    site_dem_path: Path
    """Path to the site Digital Elevation Model (GeoTIFF)."""

    site_dsm_path: Path | None = None
    """Path to the site Digital Surface Model (GeoTIFF). None = DEM used for occlusion."""

    boundary_path: Path | None = None
    """Path to the site boundary GeoJSON file. None = no boundary clipping."""

    sensor_placements: list[SensorPlacement] = Field(default_factory=list)
    """Sensor deployments on the site."""

    effector_placements: list[EffectorPlacement] = Field(default_factory=list)
    """Effector deployments on the site."""

    threat_profiles: list[str] = Field(default_factory=list)
    """Threat type names to evaluate (e.g. 'DJI Phantom 4'). Empty = no threat analysis."""

    protected_point: tuple[float, float] | None = None
    """CRS coordinates (x, y) of the protected asset for corridor analysis.
    Required when threat_profiles is non-empty; ignored otherwise."""

    trajectory_path: Path | None = None
    """Path to a DroneTrajectory YAML file for engagement-calc runs.
    None = corridor-sweep planning mode only."""

    trajectory: DroneTrajectory | None = None
    """Loaded DroneTrajectory instance. Populated by load_scenario when
    trajectory_path is set; not read directly from the scenario YAML."""

    sweep_altitudes_m: list[float] | None = None
    """Altitudes AGL (metres) to sweep in find_worst_trajectories.
    All values must be non-negative finite.  None = use threat default altitude."""

    sweep_dive_angles_deg: list[float] | None = None
    """Descent angles (degrees) to sweep in find_worst_trajectories.
    All values must be in [-90, 0]: 0 = horizontal, -90 = vertical dive.
    None = horizontal only ([0])."""

    sweep_segment_length_m: float = 5.0
    """Sampling interval for the trajectory sweep (metres, > 0).  Smaller values
    increase fidelity and computation time.  Default 5.0 for planning fidelity."""

    @field_validator("site_dem_path", mode="before")
    @classmethod
    def _site_dem_path_non_empty(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            raise ValueError("site_dem_path must not be empty or whitespace")
        elif isinstance(v, Path) and not v.parts:
            raise ValueError("site_dem_path must not be an empty path")
        elif not isinstance(v, (str, Path)):
            raise ValueError(f"site_dem_path must be a string or Path, got {type(v).__name__}")
        return v

    @field_validator("threat_profiles")
    @classmethod
    def _threat_profiles_non_empty(cls, v: list[str]) -> list[str]:
        for i, entry in enumerate(v):
            if not entry.strip():
                raise ValueError(f"threat_profiles[{i}] must not be empty or whitespace")
        return v

    @field_validator("protected_point")
    @classmethod
    def _protected_point_finite(cls, v: tuple[float, float] | None) -> tuple[float, float] | None:
        if v is not None:
            x, y = v
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"protected_point coordinates must be finite, got ({x}, {y})")
        return v

    @field_validator("trajectory_path", mode="before")
    @classmethod
    def _trajectory_path_valid(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, str) and not v.strip():
            raise ValueError("trajectory_path must not be empty or whitespace")
        elif isinstance(v, Path) and not v.parts:
            raise ValueError("trajectory_path must not be an empty path")
        elif not isinstance(v, (str, Path)):
            raise ValueError(f"trajectory_path must be a string or Path, got {type(v).__name__}")
        return v

    @field_validator("sweep_altitudes_m")
    @classmethod
    def _sweep_altitudes_valid(cls, v: list[float] | None) -> list[float] | None:
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError("sweep_altitudes_m must not be an empty list")
        for i, alt in enumerate(v):
            if not math.isfinite(alt) or alt < 0.0:
                raise ValueError(
                    f"sweep_altitudes_m[{i}] must be a non-negative finite value, got {alt}"
                )
        return v

    @field_validator("sweep_dive_angles_deg")
    @classmethod
    def _sweep_dive_angles_valid(cls, v: list[float] | None) -> list[float] | None:
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError("sweep_dive_angles_deg must not be an empty list")
        for i, angle in enumerate(v):
            if not math.isfinite(angle) or not (-90.0 <= angle <= 0.0):
                raise ValueError(f"sweep_dive_angles_deg[{i}] must be in [-90, 0], got {angle}")
        return v

    @field_validator("sweep_segment_length_m")
    @classmethod
    def _sweep_segment_length_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError(f"sweep_segment_length_m must be a finite value > 0, got {v}")
        return v
