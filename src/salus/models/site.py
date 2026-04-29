"""Site model — the foundational terrain data structure."""

from __future__ import annotations

import math
from typing import Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from salus.models.zone import Zone


class SiteModel(BaseModel):
    """Internal representation of a site's terrain.

    All coordinates are in projected CRS (metres). Arrays are NumPy 2D grids
    where each cell represents a `resolution` x `resolution` metre area.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dem: np.ndarray
    """Digital Elevation Model — ground elevation in metres."""

    dsm: np.ndarray | None = None
    """Digital Surface Model — surface elevation including structures/vegetation.
    If None, DEM is used for occlusion checks (no above-ground features)."""

    canopy_height_m: np.ndarray | None = None
    """Canopy Height Model — vegetation height above ground in metres (CHM = DSM − DEM).
    None when no LiDAR-derived CHM is available.  All finite values are >= 0 (negative
    DSM/DEM offsets are clamped to zero during derivation).  NaN cells represent nodata
    and are treated as canopy-free during viewshed attenuation."""

    resolution: float = Field(gt=0)
    """Metres per grid cell."""

    @field_validator("resolution")
    @classmethod
    def _validate_resolution(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"resolution must be a finite positive number, got {v!r}")
        return v

    origin_x: float
    """Easting of the top-left cell centre in CRS units (metres)."""

    origin_y: float
    """Northing of the top-left cell centre in CRS units (metres)."""

    crs_epsg: int | None = None
    """EPSG code of the coordinate reference system."""

    zones: list[Zone] = Field(default_factory=list)
    """Named polygonal zones loaded from a GeoJSON zones file. Empty = no zones defined."""

    @field_validator("dem", mode="before")
    @classmethod
    def _validate_dem(cls, v: np.ndarray) -> np.ndarray:
        if not isinstance(v, np.ndarray):
            raise ValueError("dem must be a numpy ndarray")
        if v.ndim != 2:
            raise ValueError(f"dem must be 2D, got {v.ndim}D")
        return v

    @field_validator("dsm", mode="before")
    @classmethod
    def _validate_dsm(cls, v: np.ndarray | None) -> np.ndarray | None:
        if v is None:
            return None
        if not isinstance(v, np.ndarray):
            raise ValueError("dsm must be a numpy ndarray")
        if v.ndim != 2:
            raise ValueError(f"dsm must be 2D, got {v.ndim}D")
        return v

    @field_validator("canopy_height_m", mode="before")
    @classmethod
    def _validate_canopy(cls, v: np.ndarray | None) -> np.ndarray | None:
        if v is None:
            return None
        if not isinstance(v, np.ndarray):
            raise ValueError("canopy_height_m must be a numpy ndarray")
        if v.ndim != 2:
            raise ValueError(f"canopy_height_m must be 2D, got {v.ndim}D")
        # Enforce >= 0 on finite values — NaN cells (nodata) are allowed.
        finite = v[np.isfinite(v)]
        if finite.size > 0 and float(finite.min()) < 0.0:
            raise ValueError(
                "canopy_height_m must have no negative finite values — "
                f"minimum finite value found: {float(finite.min()):.4f}"
            )
        return v

    @model_validator(mode="after")
    def _validate_dsm_shape(self) -> Self:
        if self.dsm is not None and self.dsm.shape != self.dem.shape:
            raise ValueError(
                f"dsm shape {self.dsm.shape} does not match dem shape {self.dem.shape}"
            )
        if self.canopy_height_m is not None and self.canopy_height_m.shape != self.dem.shape:
            raise ValueError(
                f"canopy_height_m shape {self.canopy_height_m.shape} does not match "
                f"dem shape {self.dem.shape}"
            )
        return self

    @property
    def rows(self) -> int:
        return self.dem.shape[0]

    @property
    def cols(self) -> int:
        return self.dem.shape[1]

    @property
    def extent(self) -> tuple[float, float, float, float]:
        """(min_x, max_x, min_y, max_y) in CRS units."""
        min_x = self.origin_x
        max_x = self.origin_x + self.cols * self.resolution
        max_y = self.origin_y
        min_y = self.origin_y - self.rows * self.resolution
        return (min_x, max_x, min_y, max_y)

    def surface_array(self) -> np.ndarray:
        """Return DSM if available, otherwise DEM. Used for LOS/occlusion checks."""
        return self.dsm if self.dsm is not None else self.dem
