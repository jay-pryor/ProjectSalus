"""Viewer data export and packaging for the S14 interactive standalone viewer.

Pipeline:
  1. Call :func:`export_viewer_data` with a :class:`~salus.report.pdf.SimulationResults`
     to produce a :class:`ViewerData` containing GeoJSON coverage layers, sensor
     placement points, and Terrarium-encoded XYZ terrain tiles.
  2. Optionally pass the result through :func:`~salus.viewer.sanitise.sanitise_for_export`.
  3. Call :func:`package_viewer` to write a self-contained directory that opens
     directly in a browser via ``file://`` — no server required.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import mercantile
import numpy as np
import numpy.typing as npt
import yaml
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds as _transform_from_bounds
from rasterio.transform import from_origin as _transform_from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

if TYPE_CHECKING:
    from salus.engine.threat_corridor import CorridorResult
    from salus.models.saturation import SaturationResult
    from salus.models.scenario import KillChainResult
    from salus.report.pdf import SimulationResults

_log = logging.getLogger(__name__)

# Default zoom range for terrain tiles.  For a 1–5 m DEM these give good
# close-range detail; for coarser DEMs fewer zoom levels are generated.
_TERRAIN_MIN_ZOOM: int = 12
_TERRAIN_MAX_ZOOM: int = 16

# Tile size in pixels.
_TILE_SIZE: int = 256

# Simplification tolerance applied to GeoJSON polygons (degrees in WGS84).
# ~10 m at mid-latitudes is fine for display purposes.
_SIMPLIFY_TOLERANCE: float = 0.0001

# Path to the bundled MapLibreGL vendor files.
_STATIC_DIR: Path = Path(__file__).parent / "static"
_VENDOR_DIR: Path = _STATIC_DIR / "vendor"

# Path to the sensor/effector YAML data directory.
_DATA_DIR: Path = Path(__file__).parent.parent / "data"

# MapLibreGL v3 CDN fallback (used only if vendor files are missing).
_MAPLIBRE_VERSION: str = "3.6.2"
_MAPLIBRE_JS_URL: str = f"https://unpkg.com/maplibre-gl@{_MAPLIBRE_VERSION}/dist/maplibre-gl.js"
_MAPLIBRE_CSS_URL: str = f"https://unpkg.com/maplibre-gl@{_MAPLIBRE_VERSION}/dist/maplibre-gl.css"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ViewerData:
    """All pre-computed data required to render the interactive viewer.

    Produced by :func:`export_viewer_data`; consumed by :func:`package_viewer`.
    All geographic data is in WGS84 (EPSG:4326) for MapLibreGL compatibility.
    Terrain tiles are Terrarium-encoded 256×256 PNG images, base64-encoded and
    keyed as ``"z/x/y"`` strings for inline embedding without a tile server.
    """

    scenario_name: str
    """Human-readable scenario name (DEM file stem)."""

    generated_at: str
    """ISO-8601 UTC timestamp of export."""

    bounds_wgs84: tuple[float, float, float, float]
    """(west, south, east, north) bounding box in WGS84."""

    centre_wgs84: tuple[float, float]
    """(longitude, latitude) of the site centre in WGS84."""

    layers: dict[str, Any]
    """GeoJSON FeatureCollections keyed by layer name.
    Keys include ``"composite"``, ``"gaps"``, and one entry per sensor type."""

    sensor_placements: Any
    """GeoJSON FeatureCollection of sensor positions."""

    stats: dict[str, Any]
    """Coverage statistics (mirrors :class:`~salus.engine.coverage.CoverageStats`)."""

    corridor_results: list[dict[str, Any]]
    """Serialised :class:`~salus.engine.threat_corridor.CorridorResult` list."""

    kill_chain_results: list[dict[str, Any]]
    """Serialised :class:`~salus.models.scenario.KillChainResult` list."""

    saturation_result: dict[str, Any] | None
    """Serialised :class:`~salus.models.saturation.SaturationResult` or None."""

    terrain_tiles: dict[str, str]
    """Terrarium PNG tiles keyed as ``"z/x/y"`` → base64 PNG string."""

    terrain_min_zoom: int
    """Lowest zoom level at which terrain tiles are available."""

    terrain_max_zoom: int
    """Highest zoom level at which terrain tiles are available."""

    sanitised: bool = False
    """True after :func:`~salus.viewer.sanitise.sanitise_for_export` has been applied."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_viewer_data(
    sim_results: SimulationResults,
    *,
    skip_terrain_tiles: bool = False,
) -> ViewerData:
    """Convert simulation results to a :class:`ViewerData` suitable for the viewer.

    Performs three expensive operations:
    - Vectorises boolean raster coverage arrays into GeoJSON polygons.
    - Reprojects all coordinates to WGS84.
    - Generates Terrarium-encoded XYZ terrain tiles from the site DEM.

    Args:
        sim_results: Completed simulation results containing site DEM, coverage
            arrays, and optional analysis results.
        skip_terrain_tiles: When True, skip terrain tile generation entirely
            and return an empty ``terrain_tiles`` dict.  Used by the live
            interface (``/api/simulate``), which serves tiles through the
            dedicated ``/api/terrain/tiles`` endpoint rather than the
            simulate-complete SSE payload.  Default False preserves the
            existing ``salus viewer`` CLI behaviour.

    Returns:
        :class:`ViewerData` ready for optional sanitisation and packaging.
    """
    site = sim_results.site
    scenario = sim_results.scenario

    scenario_name = Path(scenario.site_dem_path).stem
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    _log.info("Exporting viewer data for '%s'", scenario_name)

    # Determine site CRS and affine transform
    src_crs = CRS.from_epsg(site.crs_epsg) if site.crs_epsg else CRS.from_epsg(4326)
    site_transform = _transform_from_origin(
        site.origin_x, site.origin_y, site.resolution, site.resolution
    )

    # Compute WGS84 bounds and centre
    min_x, max_x, min_y, max_y = site.extent
    bounds_wgs84 = transform_bounds(src_crs, CRS.from_epsg(4326), min_x, min_y, max_x, max_y)
    west, south, east, north = bounds_wgs84
    centre_wgs84 = ((west + east) / 2.0, (south + north) / 2.0)

    # Build coverage GeoJSON layers
    _log.info("Vectorising coverage layers…")
    layers: dict[str, Any] = {}
    try:
        layers["composite"] = _raster_to_geojson(sim_results.composite, site_transform, src_crs)
    except Exception as exc:
        _log.warning("Failed to vectorise composite coverage: %s", exc)
        layers["composite"] = _empty_feature_collection()

    for stype, arr in sim_results.layer_coverages.items():
        key = stype.value
        try:
            layers[key] = _raster_to_geojson(arr, site_transform, src_crs)
        except Exception as exc:
            _log.warning("Failed to vectorise layer '%s': %s", key, exc)
            layers[key] = _empty_feature_collection()

    # Gap layer
    if sim_results.gaps is not None:
        gaps_arr = sim_results.gaps
    else:
        gaps_arr = ~sim_results.composite
    try:
        layers["gaps"] = _raster_to_geojson(gaps_arr, site_transform, src_crs)
    except Exception as exc:
        _log.warning("Failed to vectorise gaps: %s", exc)
        layers["gaps"] = _empty_feature_collection()

    # Build lookup: sensor name → (type value, azimuth_coverage_deg)
    sensor_info_map: dict[str, tuple[str, float]] = {
        sdef.name: (sdef.type.value, sdef.azimuth_coverage_deg) for sdef in sim_results.sensor_defs
    }
    if not sensor_info_map and sim_results.scenario.sensor_placements:
        _log.warning(
            "sensor_info_map is empty; all sensor markers will show type='' "
            "and no bearing wedges will be drawn — check that sensor_defs are loaded"
        )

    # Sensor placement points
    try:
        sensor_placements = _build_sensor_geojson(
            sim_results.scenario.sensor_placements, src_crs, sensor_info_map
        )
    except Exception as exc:
        _log.warning("Failed to build sensor placement GeoJSON: %s", exc)
        sensor_placements = _empty_feature_collection()

    # Coverage statistics
    stats_dict: dict[str, Any] = {
        "total_coverage_pct": round(sim_results.stats.total_coverage_pct, 2),
        "per_layer_coverage_pct": {
            k.value: round(v, 2) for k, v in sim_results.stats.per_layer_coverage_pct.items()
        },
        "per_zone_coverage_pct": {
            k: round(v, 2) for k, v in sim_results.stats.per_zone_coverage_pct.items()
        },
        "gap_area_m2": round(sim_results.stats.gap_area_m2, 1),
        "largest_contiguous_gap_m2": round(sim_results.stats.largest_contiguous_gap_m2, 1),
    }

    # Worst corridor coverage — min coverage_pct across all corridor results.
    # The interface simulation-runner and scenario-comparison modules both
    # surface this as a single summary number; computing it here keeps those
    # modules from having to re-traverse corridor_results each render.
    if sim_results.corridor_results:
        corridor_cov_values = [
            float(r.coverage_pct)
            for r in sim_results.corridor_results
            if getattr(r, "coverage_pct", None) is not None
        ]
        if corridor_cov_values:
            stats_dict["worst_corridor_coverage_pct"] = round(min(corridor_cov_values), 2)

    # Threat corridors — compute WGS84 paths from corridor geometry
    import pyproj

    _transformer_to_wgs84 = pyproj.Transformer.from_crs(
        src_crs, CRS.from_epsg(4326), always_xy=True
    )
    protected_point = sim_results.scenario.protected_point
    corridor_list = [
        _serialise_corridor(
            r,
            _compute_corridor_path_wgs84(r, protected_point, _transformer_to_wgs84),
        )
        for r in sim_results.corridor_results
    ]

    # Kill-chain results
    kc_list = [_serialise_kill_chain(r) for r in sim_results.kill_chain_results]

    # Saturation result
    sat_dict = (
        _serialise_saturation(sim_results.saturation_result)
        if sim_results.saturation_result is not None
        else None
    )

    # Terrain tiles
    terrain_tiles: dict[str, str]
    if skip_terrain_tiles:
        _log.info("Skipping terrain tile generation (skip_terrain_tiles=True).")
        terrain_tiles = {}
    else:
        _log.info("Generating terrain tiles (zoom %d–%d)…", _TERRAIN_MIN_ZOOM, _TERRAIN_MAX_ZOOM)
        terrain_tiles = _generate_terrain_tiles(
            site, src_crs, site_transform, bounds_wgs84, _TERRAIN_MIN_ZOOM, _TERRAIN_MAX_ZOOM
        )
        _log.info("Generated %d terrain tiles", len(terrain_tiles))

    return ViewerData(
        scenario_name=scenario_name,
        generated_at=generated_at,
        bounds_wgs84=bounds_wgs84,
        centre_wgs84=centre_wgs84,
        layers=layers,
        sensor_placements=sensor_placements,
        stats=stats_dict,
        corridor_results=corridor_list,
        kill_chain_results=kc_list,
        saturation_result=sat_dict,
        terrain_tiles=terrain_tiles,
        terrain_min_zoom=_TERRAIN_MIN_ZOOM,
        terrain_max_zoom=_TERRAIN_MAX_ZOOM,
    )


def package_viewer(
    viewer_data: ViewerData,
    output_dir: Path,
    *,
    zip_output: bool = False,
) -> Path:
    """Write a self-contained interactive viewer to *output_dir*.

    The resulting directory contains HTML, JS, CSS, GeoJSON/stats embedded as
    inline JavaScript, and terrain tiles written as individual PNG files under
    ``tiles/{z}/{x}/{y}.png``.  The viewer requires an HTTP server (e.g.
    ``python -m http.server 8080``); it cannot be opened via ``file://`` due to
    browser restrictions on cross-origin file requests.

    Args:
        viewer_data: Exported (and optionally sanitised) viewer data.
        output_dir: Destination directory (created if absent).
        zip_output: If True, also write a ``{output_dir}.zip`` archive.

    Returns:
        Resolved path to the output directory (or zip if *zip_output* is True
        and zipping succeeds).
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write terrain tiles as PNG files (tiles/{z}/{x}/{y}.png) first so the
    #    tile count is available for the viewer_data.js payload.
    terrain_tile_count = _write_terrain_tile_files(viewer_data, output_dir)

    # 2. Load sensor/effector library YAMLs so the interactive panel is populated.
    sensor_library = _load_sensor_library(_DATA_DIR / "sensors")
    effector_library = _load_sensor_library(_DATA_DIR / "effectors")
    _log.info(
        "Library loaded: %d sensor types, %d effector types",
        len(sensor_library),
        len(effector_library),
    )

    # 3. Write embedded data JS (GeoJSON, stats, library — tile count for JS guard)
    _write_viewer_data_js(
        viewer_data,
        output_dir / "viewer_data.js",
        terrain_tile_count,
        sensor_library=sensor_library,
        effector_library=effector_library,
    )

    # 4. Copy static assets (HTML, app.js, style.css)
    _copy_static_assets(output_dir)

    # 5. Bundle MapLibreGL vendor files
    _ensure_vendor_files(output_dir)

    _log.info("Viewer packaged → %s", output_dir)

    if zip_output:
        zip_path = Path(str(output_dir) + ".zip")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fpath in sorted(output_dir.rglob("*")):
                    if fpath.is_file():
                        zf.write(fpath, fpath.relative_to(output_dir.parent))
            _log.info("Viewer zip → %s", zip_path)
            return zip_path
        except OSError as exc:
            _log.warning("Could not write zip: %s", exc)

    return output_dir


# ---------------------------------------------------------------------------
# Terrain tile generation
# ---------------------------------------------------------------------------


def _generate_terrain_tiles(
    site: Any,
    src_crs: CRS,
    site_transform: Any,
    bounds_wgs84: tuple[float, float, float, float],
    min_zoom: int,
    max_zoom: int,
) -> dict[str, str]:
    """Generate Terrarium-encoded terrain tiles for all zoom levels.

    Returns a dict mapping ``"z/x/y"`` keys to base64-encoded PNG strings.
    Tiles outside the DEM extent have their out-of-bounds pixels filled with
    the DEM minimum elevation (avoids nodata artefacts at tile edges).
    """
    west, south, east, north = bounds_wgs84
    dst_crs = CRS.from_epsg(3857)  # Web Mercator — standard tile CRS
    dem = site.dem.astype(np.float32)
    finite_mask = np.isfinite(dem)
    if not np.any(finite_mask):
        _log.warning("DEM contains no finite values — terrain tiles will use fill elevation 0 m")
        fill_value = 0.0
    else:
        fill_value = float(np.nanmin(dem))

    tiles: dict[str, str] = {}

    for zoom in range(min_zoom, max_zoom + 1):
        tile_list = list(mercantile.tiles(west, south, east, north, zooms=zoom))
        for tile in tile_list:
            xy = mercantile.xy_bounds(tile)
            dst_transform = _transform_from_bounds(
                xy.left, xy.bottom, xy.right, xy.top, _TILE_SIZE, _TILE_SIZE
            )

            dst_data = np.full((_TILE_SIZE, _TILE_SIZE), fill_value, dtype=np.float32)
            try:
                reproject(
                    source=dem,
                    destination=dst_data,
                    src_transform=site_transform,
                    src_crs=src_crs,
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear,
                    src_nodata=None,
                    dst_nodata=fill_value,
                )
            except Exception as exc:
                _log.warning("Tile %d/%d/%d reproject failed: %s", zoom, tile.x, tile.y, exc)
                # Still emit tile (filled with fill_value) so the viewer doesn't error
            finally:
                # Replace any remaining nodata artefacts
                dst_data = np.where(np.isfinite(dst_data), dst_data, fill_value)

            rgb = _encode_terrarium(dst_data)
            png_bytes = _rgb_to_png(rgb)
            b64 = base64.b64encode(png_bytes).decode("ascii")
            tiles[f"{tile.z}/{tile.x}/{tile.y}"] = b64

    return tiles


def _encode_terrarium(elevation: npt.NDArray[np.float32]) -> npt.NDArray[np.uint8]:
    """Encode an elevation array (metres) as Terrarium RGB.

    Terrarium decode formula: elevation = (R * 256 + G + B / 256) − 32768
    """
    val = (elevation.astype(np.float64) + 32768.0).clip(0.0, 65535.999)
    int_val = val.astype(np.int32)
    frac_val = val - int_val.astype(np.float64)
    r = (int_val >> 8).astype(np.uint8)
    g = (int_val & 0xFF).astype(np.uint8)
    b = (frac_val * 256).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def _rgb_to_png(rgb: npt.NDArray[np.uint8]) -> bytes:
    """Encode a (H, W, 3) uint8 array as PNG bytes using rasterio MemoryFile."""
    h, w = rgb.shape[:2]
    with MemoryFile() as mf:
        with mf.open(driver="PNG", width=w, height=h, count=3, dtype=np.uint8) as ds:
            ds.write(rgb.transpose(2, 0, 1))  # HWC → CHW
        return bytes(mf.read())


# ---------------------------------------------------------------------------
# GeoJSON helpers
# ---------------------------------------------------------------------------


def _raster_to_geojson(
    coverage: npt.NDArray[np.bool_],
    src_transform: Any,
    src_crs: CRS,
) -> dict[str, Any]:
    """Vectorise a boolean coverage raster to a GeoJSON FeatureCollection.

    Covered cells (True) are merged into simplified polygons and reprojected
    to WGS84.  Returns an empty FeatureCollection if no cells are covered.
    """
    import pyproj
    import rasterio.features
    from shapely.geometry import mapping, shape
    from shapely.ops import transform as shapely_transform
    from shapely.ops import unary_union

    covered = coverage.astype(np.uint8)
    polys = [
        shape(geom)
        for geom, val in rasterio.features.shapes(covered, transform=src_transform)
        if val == 1
    ]
    if not polys:
        return _empty_feature_collection()

    merged = unary_union(polys)
    merged = merged.simplify(_SIMPLIFY_TOLERANCE * _degrees_per_metre(src_crs))

    # Reproject to WGS84
    transformer = pyproj.Transformer.from_crs(src_crs, CRS.from_epsg(4326), always_xy=True)
    merged_wgs84 = shapely_transform(transformer.transform, merged)

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(merged_wgs84),
                "properties": {},
            }
        ],
    }


def _degrees_per_metre(crs: CRS) -> float:
    """Approximate degrees-per-metre scaling factor for simplification."""
    if crs.is_geographic:
        return 1.0  # already in degrees
    # Approximate: 1 degree ≈ 111 km at mid-latitudes
    return 1.0 / 111_000.0


def _empty_feature_collection() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


def _build_sensor_geojson(
    placements: list[Any],
    src_crs: CRS,
    sensor_info_map: dict[str, tuple[str, float]] | None = None,
) -> dict[str, Any]:
    """Build a GeoJSON FeatureCollection of sensor placement points (WGS84).

    Args:
        placements: List of :class:`~salus.models.scenario.SensorPlacement` instances.
        src_crs: CRS of the source coordinates; output is always WGS84.
        sensor_info_map: Optional mapping of sensor name to ``(type_value,
            azimuth_coverage_deg)`` for enriching feature properties.  When
            absent or when a sensor name is not present in the map, ``sensor_type``
            defaults to ``""`` and ``azimuth_coverage_deg`` defaults to ``360``.
    """
    import pyproj

    transformer = pyproj.Transformer.from_crs(src_crs, CRS.from_epsg(4326), always_xy=True)
    features = []
    for p in placements:
        if p.position_x is None or p.position_y is None:
            _log.warning("Skipping sensor placement with missing coordinates: %s", p.sensor_name)
            continue
        lon, lat = transformer.transform(p.position_x, p.position_y)
        if not (math.isfinite(lon) and math.isfinite(lat)):
            _log.warning(
                "Sensor '%s' produced non-finite WGS84 coordinates (%.6g, %.6g); skipping",
                p.sensor_name,
                lon,
                lat,
            )
            continue
        sensor_type = ""
        azimuth_coverage_deg: float = 360.0
        if sensor_info_map and p.sensor_name in sensor_info_map:
            sensor_type, azimuth_coverage_deg = sensor_info_map[p.sensor_name]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": {
                    "sensor_name": p.sensor_name,
                    "sensor_type": sensor_type,
                    "azimuth_coverage_deg": azimuth_coverage_deg,
                    "bearing_deg": p.bearing_deg,
                    "height_override_m": p.height_override_m,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _compute_corridor_path_wgs84(
    result: CorridorResult,
    protected_point: tuple[float, float] | None,
    transformer: Any,
) -> list[list[float]]:
    """Compute a two-point WGS84 LineString for a threat corridor approach path."""
    if protected_point is None:
        return []
    import math

    bearing_rad = math.radians(result.corridor.bearing_deg)
    dist = result.corridor.start_distance_m
    # Drone approaches FROM start_point TOWARDS protected_point along bearing_deg.
    # Start point is start_distance_m in the OPPOSITE direction from the asset.
    start_x = protected_point[0] - math.sin(bearing_rad) * dist
    start_y = protected_point[1] - math.cos(bearing_rad) * dist
    try:
        lon_start, lat_start = transformer.transform(start_x, start_y)
        lon_end, lat_end = transformer.transform(protected_point[0], protected_point[1])
        return [
            [round(lon_start, 6), round(lat_start, 6)],
            [round(lon_end, 6), round(lat_end, 6)],
        ]
    except Exception as exc:
        _log.warning("Failed to compute WGS84 corridor path: %s", exc)
        return []


def _serialise_corridor(
    result: CorridorResult,
    path_wgs84: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Serialise a CorridorResult to a JSON-safe dict."""
    try:
        return {
            "threat_name": result.threat_name,
            "coverage_pct": round(result.coverage_pct, 2),
            "first_detection_distance_m": (
                round(result.first_detection_distance_m, 1)
                if result.first_detection_distance_m is not None
                else None
            ),
            "last_gap_before_target_m": round(result.last_gap_before_target_m, 1),
            "time_in_coverage_s": round(result.time_in_coverage_s, 2),
            "covered_cells": result.covered_cells,
            "total_cells": result.total_cells,
            "path_wgs84": path_wgs84 if path_wgs84 is not None else [],
        }
    except Exception as exc:
        _log.warning(
            "_serialise_corridor failed for '%s': %s", getattr(result, "threat_name", "?"), exc
        )
        return {}


def _serialise_kill_chain(result: KillChainResult) -> dict[str, Any]:
    """Serialise a KillChainResult to a JSON-safe dict."""
    try:
        return {
            "available_time_s": round(result.available_time_s, 2),
            "required_time_s": round(result.required_time_s, 2),
            "margin_s": round(result.margin_s, 2),
            "first_detection_range_m": (
                round(result.first_detection_range_m, 1)
                if result.first_detection_range_m is not None
                else None
            ),
            "engagement_feasible": result.engagement_feasible,
            "second_engagement_possible": result.second_engagement_possible,
        }
    except Exception as exc:
        _log.warning("_serialise_kill_chain failed: %s", exc)
        return {}


def _serialise_saturation(result: SaturationResult) -> dict[str, Any]:
    """Serialise a SaturationResult to a JSON-safe dict."""
    try:
        return {
            "simultaneous_engagement_capacity": result.simultaneous_engagement_capacity,
            "saturation_threshold_n": result.saturation_threshold_n,
            "unengaged_count_at_threshold": result.unengaged_count_at_threshold,
            "per_effector_utilisation": {
                k: round(v, 4) for k, v in result.per_effector_utilisation.items()
            },
        }
    except Exception as exc:
        _log.warning("_serialise_saturation failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Packaging helpers
# ---------------------------------------------------------------------------


def _write_viewer_data_js(
    viewer_data: ViewerData,
    dest: Path,
    terrain_tile_count: int,
    *,
    sensor_library: dict[str, list[dict[str, Any]]] | None = None,
    effector_library: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    """Write viewer data as a single inline JavaScript file.

    Assigns ``window.SALUS_DATA`` (coverage GeoJSON, stats, corridor/kill-chain
    results, and sensor/effector library) which is read by ``app.js`` at startup.
    Terrain tiles are written as individual PNG files (see
    :func:`_write_terrain_tile_files`) and served by the HTTP server.

    Args:
        viewer_data: Exported viewer data.
        dest: Destination path for ``viewer_data.js``.
        terrain_tile_count: Number of terrain tile PNG files successfully written
            to disk.  Passed through to the JS payload so ``app.js`` can guard
            the terrain source on whether tiles actually exist.
        sensor_library: Sensor YAML data grouped by type, as returned by
            :func:`_load_sensor_library`.  Embedded as ``SALUS_DATA.sensor_library``
            for the interactive library panel.
        effector_library: Effector YAML data grouped by type.  Embedded as
            ``SALUS_DATA.effector_library``.
    """
    data_payload: dict[str, Any] = {
        "scenario_name": viewer_data.scenario_name,
        "generated_at": viewer_data.generated_at,
        "bounds_wgs84": list(viewer_data.bounds_wgs84),
        "centre_wgs84": list(viewer_data.centre_wgs84),
        "layers": viewer_data.layers,
        "sensor_placements": viewer_data.sensor_placements,
        "stats": viewer_data.stats,
        "corridor_results": viewer_data.corridor_results,
        "kill_chain_results": viewer_data.kill_chain_results,
        "saturation_result": viewer_data.saturation_result,
        "terrain_min_zoom": viewer_data.terrain_min_zoom,
        "terrain_max_zoom": viewer_data.terrain_max_zoom,
        "terrain_tile_count": terrain_tile_count,
        "sanitised": viewer_data.sanitised,
        "sensor_library": sensor_library if sensor_library is not None else {},
        "effector_library": effector_library if effector_library is not None else {},
    }

    data_json = json.dumps(data_payload, separators=(",", ":"))
    dest.write_text(f"window.SALUS_DATA={data_json};\n", encoding="utf-8")


def _write_terrain_tile_files(viewer_data: ViewerData, output_dir: Path) -> int:
    """Write terrain tiles as individual PNG files under ``output_dir/tiles/``.

    Each tile is written to ``tiles/{z}/{x}/{y}.png`` so MapLibreGL can fetch
    them directly over HTTP without a custom protocol handler.  This avoids the
    Web Worker / main-thread boundary that prevents ``addProtocol`` from working
    with ``raster-dem`` sources in MapLibreGL v3.

    Returns:
        Number of tiles successfully written.
    """
    tiles_dir = output_dir / "tiles"
    written = 0
    total = len(viewer_data.terrain_tiles)
    for key, b64 in viewer_data.terrain_tiles.items():
        parts = key.split("/")
        if len(parts) != 3:  # noqa: PLR2004
            _log.warning("Skipping malformed terrain tile key %r (expected z/x/y)", key)
            continue
        z, x, y = parts
        tile_dir = tiles_dir / z / x
        try:
            tile_dir.mkdir(parents=True, exist_ok=True)
            (tile_dir / f"{y}.png").write_bytes(base64.b64decode(b64))
            written += 1
        except Exception as exc:
            _log.warning("Failed to write terrain tile %s: %s", key, exc)
    if written == 0 and total > 0:
        _log.error("All %d terrain tile(s) failed to write — viewer terrain will not render", total)
    else:
        _log.info("Written %d/%d terrain tile files → %s", written, total, tiles_dir)
    return written


def _load_sensor_library(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Load all YAML files from *data_dir* and group them by their ``type`` field.

    Each YAML file that contains a mapping with a ``type`` key is parsed and
    added to the corresponding group.  Files that are missing, malformed, or
    that do not produce a dict are skipped with a warning.

    Args:
        data_dir: Directory containing ``*.yaml`` sensor or effector definitions.

    Returns:
        Dict mapping type string → list of entry dicts, sorted by type key.
        Returns an empty dict if *data_dir* does not exist.
    """
    if not data_dir.is_dir():
        _log.warning("Library data directory not found: %s", data_dir)
        return {}

    library: dict[str, list[dict[str, Any]]] = {}
    for yaml_path in sorted(data_dir.glob("*.yaml")):
        try:
            raw = yaml_path.read_text(encoding="utf-8")
            entry = yaml.safe_load(raw)
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            _log.warning("Failed to parse library YAML %s: %s", yaml_path.name, exc)
            continue
        if not isinstance(entry, dict):
            _log.warning("Library YAML %s is not a mapping — skipping", yaml_path.name)
            continue
        sensor_type = str(entry.get("type") or "Unknown")
        library.setdefault(sensor_type, []).append(entry)

    return dict(sorted(library.items()))


def _copy_static_assets(output_dir: Path) -> None:
    """Copy HTML, JS, and CSS from the bundled static directory."""
    for asset in ("index.html", "app.js", "style.css"):
        src = _STATIC_DIR / asset
        if src.exists():
            shutil.copy2(src, output_dir / asset)
        else:
            _log.warning("Static asset missing: %s", src)


def _ensure_vendor_files(output_dir: Path) -> None:
    """Copy bundled MapLibreGL vendor files, downloading from CDN if absent."""
    vendor_out = output_dir / "vendor"
    vendor_out.mkdir(exist_ok=True)

    js_src = _VENDOR_DIR / "maplibre-gl.js"
    css_src = _VENDOR_DIR / "maplibre-gl.css"

    if js_src.exists() and css_src.exists():
        shutil.copy2(js_src, vendor_out / "maplibre-gl.js")
        shutil.copy2(css_src, vendor_out / "maplibre-gl.css")
        return

    # Attempt to download from CDN (requires network)
    _log.info("Vendor files not cached — downloading MapLibreGL %s from CDN…", _MAPLIBRE_VERSION)
    try:
        import urllib.request

        for url, fname in [
            (_MAPLIBRE_JS_URL, "maplibre-gl.js"),
            (_MAPLIBRE_CSS_URL, "maplibre-gl.css"),
        ]:
            dest_file = vendor_out / fname
            _log.info("  Downloading %s", url)
            urllib.request.urlretrieve(url, dest_file)  # noqa: S310  # nosec B310 — trusted CDN URL hardcoded above

        # Also cache for next time
        _VENDOR_DIR.mkdir(exist_ok=True)
        shutil.copy2(vendor_out / "maplibre-gl.js", js_src)
        shutil.copy2(vendor_out / "maplibre-gl.css", css_src)

    except Exception as exc:
        _log.warning(
            "Could not download MapLibreGL vendor files (%s). "
            "The viewer will fall back to CDN — internet access required.",
            exc,
        )
        # Write a placeholder that injects the CDN script via DOM (document.write
        # is blocked after page load, including on file:// pages).
        (vendor_out / "maplibre-gl.js").write_text(
            f"// CDN fallback — vendor files could not be downloaded.\n"
            f"(function(){{var s=document.createElement('script');"
            f"s.src='{_MAPLIBRE_JS_URL}';"
            f"document.head.appendChild(s);}})();\n",
            encoding="utf-8",
        )
        (vendor_out / "maplibre-gl.css").write_text(
            f"/* CDN fallback — link from: {_MAPLIBRE_CSS_URL} */\n",
            encoding="utf-8",
        )
