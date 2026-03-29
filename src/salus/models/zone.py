"""Zone data model — named, typed polygonal regions within a site."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator
from shapely.geometry import MultiPolygon, Polygon


class ZoneType(StrEnum):
    """Classification of a zone's role on the site."""

    perimeter = "perimeter"
    inner = "inner"
    critical_asset = "critical_asset"
    exclusion = "exclusion"


class Zone(BaseModel):
    """A named polygonal region within a site, classified by operational role.

    Coordinates are in the same projected CRS as the site DEM (metres).
    Geometry is stored as a Shapely Polygon or MultiPolygon and is not
    validated against the site extent — callers should ensure the zone
    overlaps the DEM before performing coverage analysis.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    """Human-readable label for the zone (e.g. 'Main Perimeter', 'Comms Tower')."""

    zone_type: ZoneType
    """Operational classification of the zone."""

    geometry: Polygon | MultiPolygon
    """Shapely geometry defining the zone boundary."""

    @field_validator("name")
    @classmethod
    def _name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty or whitespace")
        return v
