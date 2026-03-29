"""GeoJSON boundary and zone loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

from salus.models.zone import Zone, ZoneType

# GeoJSON geometry type names that are polygon-like.
_POLYGON_GEOM_TYPES: frozenset[str] = frozenset({"Polygon", "MultiPolygon"})


def load_boundary(path: str | Path, site_epsg: int | None = None) -> Polygon:
    """Load a site boundary polygon from a GeoJSON file.

    Accepts a GeoJSON Feature, FeatureCollection, or bare Polygon/MultiPolygon
    geometry. If the file contains multiple polygon features they are unioned;
    if the union is still a MultiPolygon the largest part by area is returned.

    Args:
        path: Path to the GeoJSON file.
        site_epsg: EPSG code of the site DEM CRS. If provided, the file's CRS
            must match; raises :class:`ValueError` on mismatch. Pass ``None``
            to skip CRS validation.

    Returns:
        A :class:`~shapely.geometry.Polygon` representing the site boundary.

    Raises:
        FileNotFoundError: If the GeoJSON file does not exist.
        OSError: If the file cannot be read.
        ValueError: If the file is invalid GeoJSON, contains no polygon
            geometries, or its CRS does not match ``site_epsg``.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Boundary file not found: {path}")

    data = _read_geojson(path)
    _validate_crs(_extract_epsg(data), site_epsg, path)

    polys = _collect_polygons(data, path)
    if not polys:
        raise ValueError(f"No polygon geometries found in boundary file: {path}")

    union = unary_union(polys)
    if isinstance(union, MultiPolygon):
        largest = max(union.geoms, key=lambda g: g.area)
        if not isinstance(largest, Polygon):
            raise ValueError(
                f"Largest component of boundary MultiPolygon is not a Polygon"
                f" (got {type(largest).__name__}): {path}"
            )
        return largest
    if isinstance(union, Polygon):
        return union
    raise ValueError(
        f"Union of boundary geometries is not a polygon (got {type(union).__name__}): {path}"
    )


def load_zones(path: str | Path, site_epsg: int | None = None) -> list[Zone]:
    """Load zone definitions from a GeoJSON FeatureCollection.

    Each feature must have ``name`` (str) and ``type`` (one of ``perimeter``,
    ``inner``, ``critical_asset``, ``exclusion``) in its ``properties``, and a
    Polygon or MultiPolygon geometry.

    Args:
        path: Path to the GeoJSON FeatureCollection file.
        site_epsg: EPSG code of the site DEM CRS. If provided, the file's CRS
            must match; raises :class:`ValueError` on mismatch.

    Returns:
        List of :class:`~salus.models.zone.Zone` objects, one per feature.

    Raises:
        FileNotFoundError: If the GeoJSON file does not exist.
        OSError: If the file cannot be read.
        ValueError: If the file is not a FeatureCollection, has no features,
            a feature is missing required properties, has an unsupported geometry
            type, or its CRS does not match ``site_epsg``.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Zones file not found: {path}")

    data = _read_geojson(path)

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            f"Zones GeoJSON must be a FeatureCollection, got '{data.get('type')}': {path}"
        )

    _validate_crs(_extract_epsg(data), site_epsg, path)

    features: list[dict[str, Any]] = data.get("features") or []
    if not features:
        raise ValueError(f"No features found in zones file: {path}")

    zones: list[Zone] = []
    for i, feat in enumerate(features):
        props: dict[str, Any] = feat.get("properties") or {}
        geom_dict: dict[str, Any] | None = feat.get("geometry")

        name: str | None = props.get("name")
        zone_type_str: str | None = props.get("type")

        if not name:
            raise ValueError(f"Zone feature {i} missing required 'name' property: {path}")
        if not zone_type_str:
            raise ValueError(
                f"Zone feature {i} ('{name}') missing required 'type' property: {path}"
            )
        if geom_dict is None:
            raise ValueError(f"Zone feature {i} ('{name}') has null geometry: {path}")

        geom = shape(geom_dict)
        if not isinstance(geom, (Polygon, MultiPolygon)):
            raise ValueError(
                f"Zone feature {i} ('{name}') geometry must be Polygon or MultiPolygon,"
                f" got {type(geom).__name__}: {path}"
            )

        try:
            zone = Zone(name=name, zone_type=ZoneType(zone_type_str), geometry=geom)
        except ValueError as exc:
            raise ValueError(
                f"Invalid zone definition at feature {i} ('{name}') in {path}: {exc}"
            ) from exc

        zones.append(zone)

    return zones


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_geojson(path: Path) -> dict[str, Any]:
    """Read and parse a GeoJSON file, raising typed errors."""
    try:
        with path.open(encoding="utf-8") as fh:
            raw: Any = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid GeoJSON in {path}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"Cannot read GeoJSON file {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"GeoJSON file must be a JSON object, got {type(raw).__name__}: {path}")
    return raw


def _extract_epsg(data: dict[str, Any]) -> int | None:
    """Extract EPSG code from an old-style GeoJSON ``crs`` member, or None.

    Standard RFC 7946 GeoJSON has no ``crs`` member and is implicitly WGS84.
    Non-standard files (e.g. written by QGIS / GDAL) may include one.
    """
    crs = data.get("crs")
    if crs is None:
        return None
    name: str = (crs.get("properties") or {}).get("name", "")
    if not name:
        return None
    from pyproj import CRS
    from pyproj.exceptions import CRSError

    try:
        return CRS.from_user_input(name).to_epsg()
    except CRSError:
        return None


def _validate_crs(file_epsg: int | None, site_epsg: int | None, path: Path) -> None:
    """Raise ValueError if the file CRS does not match the site CRS.

    When the file has no CRS member, WGS84 (EPSG:4326) is assumed.
    Validation is skipped when ``site_epsg`` is None.
    """
    if site_epsg is None:
        return
    effective: int = file_epsg if file_epsg is not None else 4326
    if effective != site_epsg:
        file_label = (
            f"EPSG:{file_epsg}"
            if file_epsg is not None
            else "WGS84/EPSG:4326 (assumed — no CRS member in file)"
        )
        raise ValueError(
            f"GeoJSON CRS ({file_label}) does not match site CRS (EPSG:{site_epsg}): {path}"
        )


def _collect_polygons(data: dict[str, Any], path: Path) -> list[Polygon | MultiPolygon]:
    """Extract all Polygon/MultiPolygon geometries from a GeoJSON dict."""
    geom_type: str | None = data.get("type")

    if geom_type == "FeatureCollection":
        features: list[dict[str, Any]] = data.get("features") or []
    elif geom_type == "Feature":
        features = [data]
    elif geom_type in _POLYGON_GEOM_TYPES:
        geom = shape(data)
        if not isinstance(geom, (Polygon, MultiPolygon)):
            raise ValueError(f"Expected polygon geometry, got {type(geom).__name__}: {path}")
        return [geom]
    else:
        raise ValueError(f"Unsupported GeoJSON type '{geom_type}': {path}")

    polys: list[Polygon | MultiPolygon] = []
    for feat in features:
        geom_dict = feat.get("geometry")
        if geom_dict is None:
            continue
        geom = shape(geom_dict)
        if isinstance(geom, (Polygon, MultiPolygon)):
            polys.append(geom)
    return polys
