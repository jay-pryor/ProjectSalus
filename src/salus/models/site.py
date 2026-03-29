"""Site model — the foundational terrain data structure."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    resolution: float
    """Metres per grid cell."""

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
