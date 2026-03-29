"""GeoJSON boundary and zone loader."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union

from salus.models.zone import Zone, ZoneType

# GeoJSON geometry type names that are polygon-like.
_POLYGON_GEOM_TYPES: frozenset[str] = frozenset({"Polygon", "MultiPolygon"})


def load_boundary(path: str | Path, site_epsg: int | None = None) -> Polygon:
    """Load a site boundary polygon from a GeoJSON file.

    Accepts a GeoJSON Feature, FeatureCollection, or bare Polygon/MultiPolygon
    geometry. If the file contains multiple polygon features they are unioned;
    if the union is still a MultiPolygon the largest part by area is returned.

    If the file's CRS does not match ``site_epsg``, the boundary geometry is
    reprojected automatically and a :class:`UserWarning` is emitted.

    Args:
        path: Path to the GeoJSON file.
        site_epsg: EPSG code of the site CRS. If provided and the file's CRS
            differs, the geometry is reprojected to match. Pass ``None`` to
            skip reprojection.

    Returns:
        A :class:`~shapely.geometry.Polygon` representing the site boundary.

    Raises:
        FileNotFoundError: If the GeoJSON file does not exist.
        OSError: If the file cannot be read.
        ValueError: If the file is invalid GeoJSON, contains no polygon
            geometries, or has an unparseable/non-EPSG CRS member.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Boundary file not found: {path}")

    data = _read_geojson(path)
    file_epsg = _resolve_file_epsg(data, path)

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
        result: Polygon = largest
    elif isinstance(union, Polygon):
        result = union
    else:
        raise ValueError(
            f"Union of boundary geometries is not a polygon (got {type(union).__name__}): {path}"
        )

    if site_epsg is not None and file_epsg != site_epsg:
        warnings.warn(
            f"Boundary GeoJSON CRS (EPSG:{file_epsg}) does not match site CRS "
            f"(EPSG:{site_epsg}); reprojecting boundary geometry.",
            UserWarning,
            stacklevel=2,
        )
        result = _reproject_geometry(result, file_epsg, site_epsg)

    return result


def load_zones(path: str | Path, site_epsg: int | None = None) -> list[Zone]:
    """Load zone definitions from a GeoJSON FeatureCollection.

    Each feature must have ``name`` (str) and ``type`` (one of ``perimeter``,
    ``inner``, ``critical_asset``, ``exclusion``) in its ``properties``, and a
    Polygon or MultiPolygon geometry.

    If the file's CRS does not match ``site_epsg``, all zone geometries are
    reprojected automatically and a :class:`UserWarning` is emitted.

    Args:
        path: Path to the GeoJSON FeatureCollection file.
        site_epsg: EPSG code of the site CRS. If provided and the file's CRS
            differs, geometries are reprojected to match. Pass ``None`` to
            skip reprojection.

    Returns:
        List of :class:`~salus.models.zone.Zone` objects, one per feature.

    Raises:
        FileNotFoundError: If the GeoJSON file does not exist.
        OSError: If the file cannot be read.
        ValueError: If the file is not a FeatureCollection, has no features,
            a feature is missing required properties, has an unsupported
            geometry type, or has an unparseable/non-EPSG CRS member.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Zones file not found: {path}")

    data = _read_geojson(path)

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            f"Zones GeoJSON must be a FeatureCollection, got '{data.get('type')}': {path}"
        )

    file_epsg = _resolve_file_epsg(data, path)

    needs_reproject = site_epsg is not None and file_epsg != site_epsg
    if needs_reproject:
        warnings.warn(
            f"Zones GeoJSON CRS (EPSG:{file_epsg}) does not match site CRS "
            f"(EPSG:{site_epsg}); reprojecting zone geometries.",
            UserWarning,
            stacklevel=2,
        )

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

        if needs_reproject and site_epsg is not None:
            geom = _reproject_geometry(geom, file_epsg, site_epsg)

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


def _resolve_file_epsg(data: dict[str, Any], path: Path) -> int:
    """Return the EPSG code of the GeoJSON file's CRS.

    - No ``crs`` member → 4326 (RFC 7946 WGS84 default).
    - ``crs`` member present → parse and return EPSG.

    Raises:
        ValueError: If the ``crs`` member is present but cannot be parsed,
            or is valid but not mappable to an EPSG code.
    """
    crs = data.get("crs")
    if crs is None:
        return 4326  # RFC 7946: GeoJSON without crs member is implicitly WGS84

    if not isinstance(crs, dict):
        raise ValueError(
            f"GeoJSON 'crs' member must be a JSON object, got {type(crs).__name__}: {path}"
        )

    name: str = (crs.get("properties") or {}).get("name", "")
    if not name:
        raise ValueError(f"GeoJSON has a 'crs' member but no parseable CRS name property: {path}")

    from pyproj import CRS
    from pyproj.exceptions import CRSError

    try:
        epsg = CRS.from_user_input(name).to_epsg()
    except CRSError as exc:
        raise ValueError(f"Cannot parse CRS from GeoJSON 'crs' member '{name}': {path}") from exc

    if epsg is None:
        raise ValueError(
            f"GeoJSON CRS '{name}' is valid but not mappable to an EPSG code — "
            f"only EPSG-coded CRS are supported: {path}"
        )
    return epsg


def _reproject_geometry(
    geom: Polygon | MultiPolygon,
    from_epsg: int,
    to_epsg: int,
) -> Polygon | MultiPolygon:
    """Reproject a Shapely geometry between two EPSG CRS."""
    from pyproj import Transformer
    from pyproj.exceptions import CRSError

    try:
        transformer = Transformer.from_crs(from_epsg, to_epsg, always_xy=True)
    except CRSError as exc:
        raise ValueError(
            f"Cannot create transformer from EPSG:{from_epsg} to EPSG:{to_epsg}: {exc}"
        ) from exc

    reprojected = shapely_transform(transformer.transform, geom)
    if not isinstance(reprojected, (Polygon, MultiPolygon)):
        raise ValueError(
            f"Reprojection of {type(geom).__name__} from EPSG:{from_epsg} to "
            f"EPSG:{to_epsg} produced unexpected type {type(reprojected).__name__}"
        )
    if reprojected.is_empty:
        raise ValueError(
            f"Reprojection of geometry from EPSG:{from_epsg} to EPSG:{to_epsg} "
            "produced an empty geometry — check that the coordinates are valid for "
            "the target CRS"
        )
    return reprojected


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
