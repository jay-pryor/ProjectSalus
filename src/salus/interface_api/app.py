"""FastAPI backend API for the Salus interactive interface (S14.2).

Exposes the existing Salus Python engine behind a thin HTTP/SSE layer that
browser modules can call.  No new simulation logic — this is a JSON/SSE
wrapper around the engine's existing Pydantic models and CLI functions.

The server is a localhost-only service: CORS is restricted to localhost
origins.  No authentication is required.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import math
import queue as _queue
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from salus import __version__
from salus.engine.coverage import (
    CoverageStats,
    boundary_mask,
    compute_composite_coverage,
    compute_coverage_stats,
    compute_gaps,
    compute_layer_coverage,
)
from salus.ingest.boundaries import load_boundary
from salus.ingest.sensors import load_effectors, load_sensors
from salus.ingest.terrain import load_dem
from salus.models.scenario import ScenarioConfig, SensorPlacement
from salus.models.sensor import EffectorDefinition, SensorDefinition, SensorType
from salus.report.pdf import (
    ReportData,
    render_pdf,
)

_log = logging.getLogger(__name__)

# Default sensor and effector directories bundled with the package.
_DEFAULT_SENSOR_DIR: Path = Path(__file__).parent.parent / "data" / "sensors"
_DEFAULT_EFFECTOR_DIR: Path = Path(__file__).parent.parent / "data" / "effectors"

# In-process caches — the database is read-only at runtime so we load once.
# Only set when a successful load has occurred; never set on failure so that
# transient errors (e.g. permission denied) are retried on the next request.
_sensor_cache: list[SensorDefinition] | None = None
_effector_cache: list[EffectorDefinition] | None = None

# SSE stream termination event types.
_SSE_TERMINAL_TYPES: frozenset[str] = frozenset({"complete", "error"})

# ---------------------------------------------------------------------------
# Terrain session state (S14.3)
# ---------------------------------------------------------------------------

# Root directory for uploaded DEM/DSM files and pre-generated tile sets.
_TERRAIN_DATA_DIR: Path = Path(tempfile.gettempdir()) / "salus_terrain"

# Maximum accepted DEM/DSM upload size (500 MB).  Prevents OOM on oversized
# uploads that would otherwise buffer entirely in memory (D-327).
_MAX_DEM_UPLOAD_BYTES: int = 500 * 1024 * 1024

# Per-request terrain state shared between the load endpoint and the tile
# generation background thread.  Protected by _terrain_session_lock.
_terrain_session_lock: threading.Lock = threading.Lock()
_terrain_session: dict[str, Any] = {
    "dem_path": None,
    "dsm_path": None,
    "metadata": None,
    "progress_pct": 0,
    "done": False,
    "error": None,
    "tile_dir": None,
}

# Maximum seconds to wait on the SSE queue before emitting a timeout error.
# Prevents the connection from hanging forever if a worker thread exits
# without pushing a terminal event.
_QUEUE_TIMEOUT_S: float = 300.0

app = FastAPI(
    title="Salus Interface API",
    version=__version__,
    description="Backend API for the Salus interactive cUAS planning interface.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost(:\d+)?",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SimResultsPayload(BaseModel):
    """JSON-serialisable simulation results payload.

    Returned by ``POST /api/simulate``; accepted by ``POST /api/report``.
    Contains coverage statistics and pre-rendered map images as base64 PNGs.
    """

    scenario_name: str = ""
    generated_at: str = ""
    total_coverage_pct: float = 0.0
    gap_area_m2: float = 0.0
    largest_contiguous_gap_m2: float = 0.0
    per_layer_coverage_pct: dict[str, float] = Field(default_factory=dict)
    per_zone_coverage_pct: dict[str, float] = Field(default_factory=dict)
    composite_map_b64: str | None = None
    gap_map_b64: str | None = None
    layer_maps_b64: dict[str, str] = Field(default_factory=dict)
    kill_chain_chart_b64: str | None = None
    saturation_chart_b64: str | None = None
    executive_summary: str = ""
    assumptions: dict[str, list[str]] = Field(default_factory=dict)


class OptimiserConstraints(BaseModel):
    """Coverage and placement constraints for the optimiser."""

    coverage_threshold_pct: float = Field(default=80.0, ge=0.0, le=100.0)
    """Coverage percentage at which the greedy loop exits early."""

    step_m: float = Field(default=100.0, gt=0.0)
    """Candidate grid spacing in metres."""

    weights: dict[str, float] | None = None
    """Zone-type weighting overrides.  Keys must match :class:`PlacementWeights` fields."""


class OptimiserRequest(BaseModel):
    """Request body for ``POST /api/optimise``.

    Field names follow the spec-defined schema from InterfaceArchitecture.md
    Section 6.
    """

    terrain: str
    """Absolute path to the site DEM GeoTIFF."""

    sensor_library_filter: list[str] = Field(default_factory=list)
    """Names of sensors from the bundled library to place."""

    effector_library_filter: list[str] = Field(default_factory=list)
    """Names of effectors from the bundled library (informational; unused in placement)."""

    zones: list[dict[str, Any]] = Field(default_factory=list)
    """Zone definitions (used for weighted placement scoring)."""

    constraints: OptimiserConstraints = Field(default_factory=OptimiserConstraints)
    """Placement and coverage constraints."""


class OptimiserResultsPayload(BaseModel):
    """JSON-serialisable optimiser results payload."""

    proposed_placements: list[dict[str, Any]] = Field(default_factory=list)
    score: float = 0.0
    coverage_pct: float = 0.0
    total_cost_aud: float = 0.0
    satisfied_constraints: list[str] = Field(default_factory=list)
    violated_constraints: list[str] = Field(default_factory=list)


class ReportRequest(BaseModel):
    """Request body for ``POST /api/report``.

    Field names follow the spec-defined schema from InterfaceArchitecture.md
    Section 6.
    """

    report_config: dict[str, Any]
    """ScenarioConfig-compatible JSON object (scenario metadata for the report)."""

    sim_results: SimResultsPayload
    """Pre-computed simulation results from ``POST /api/simulate``."""

    placements: list[dict[str, Any]] = Field(default_factory=list)
    """Additional sensor placements (merged with scenario placements)."""

    zones: list[dict[str, Any]] = Field(default_factory=list)
    """Zone definitions (informational; used in appendix)."""

    threat_corridors: list[dict[str, Any]] = Field(default_factory=list)
    """Threat corridor results (informational; unused if not in sim_results)."""


# ---------------------------------------------------------------------------
# Library cache helpers
# ---------------------------------------------------------------------------


def _get_sensor_defs() -> list[SensorDefinition]:
    """Return sensor definitions, loading from disk on first successful call.

    On load failure the exception is logged as a warning and an empty list is
    returned *without* caching the failure, so the next request will retry
    the actual directory.
    """
    global _sensor_cache
    if _sensor_cache is None:
        try:
            result = load_sensors(_DEFAULT_SENSOR_DIR)
            _sensor_cache = result  # Only cache on success
        except Exception as exc:
            _log.warning("Could not load sensor library: %s", exc)
            return []
    return _sensor_cache


def _get_effector_defs() -> list[EffectorDefinition]:
    """Return effector definitions, loading from disk on first successful call.

    On load failure the exception is logged as a warning and an empty list is
    returned *without* caching the failure, so the next request will retry
    the actual directory.
    """
    global _effector_cache
    if _effector_cache is None:
        try:
            result = load_effectors(_DEFAULT_EFFECTOR_DIR)
            _effector_cache = result  # Only cache on success
        except Exception as exc:
            _log.warning("Could not load effector library: %s", exc)
            return []
    return _effector_cache


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse_event(data: dict[str, Any]) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


def _queue_get_with_timeout(
    q: _queue.Queue[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    """Blocking queue.get with timeout; returns an error event on timeout."""
    try:
        return q.get(timeout=timeout)
    except _queue.Empty:
        return {"type": "error", "message": "Pipeline timed out waiting for result."}


async def _drain_queue(q: _queue.Queue[dict[str, Any]]) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted strings from *q* until terminal event.

    Uses a timeout on each ``queue.get`` call so that a worker thread that
    exits without pushing a terminal event (e.g. killed by a signal) does not
    hang the HTTP connection indefinitely.
    """
    loop = asyncio.get_running_loop()
    while True:
        event: dict[str, Any] = await loop.run_in_executor(
            None, _queue_get_with_timeout, q, _QUEUE_TIMEOUT_S
        )
        yield _sse_event(event)
        if event.get("type") in _SSE_TERMINAL_TYPES:
            break


# ---------------------------------------------------------------------------
# Simulation pipeline helpers
# ---------------------------------------------------------------------------


def _render_to_b64_api(render_func: Any, *args: Any, **kwargs: Any) -> str | None:
    """Call a render function with a temp file and return base64-encoded PNG."""
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = Path(f.name)
        render_func(*args, output_path=tmp_path, **kwargs)
        data = tmp_path.read_bytes()
        return base64.b64encode(data).decode()
    except Exception as exc:
        _log.warning("Map render failed (%s): %s", getattr(render_func, "__name__", "?"), exc)
        return None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_simulate_pipeline(
    config: ScenarioConfig,
    q: _queue.Queue[dict[str, Any]],
) -> None:
    """Run the full simulation pipeline in a background thread.

    Emits SSE progress events to *q* and finishes with a ``complete`` or
    ``error`` event containing a :class:`SimResultsPayload`-compatible dict.
    """
    try:
        from salus.report.maps import render_composite_coverage_map, render_gap_map
        from salus.report.pdf import generate_executive_summary

        q.put({"type": "progress", "message": "Loading sensor library…", "pct": 5})
        sensor_defs = _get_sensor_defs()
        sensor_map = {s.name: s for s in sensor_defs}

        q.put({"type": "progress", "message": "Loading effector library…", "pct": 10})
        effector_defs = _get_effector_defs()
        if not effector_defs:
            _log.warning("Effector library is empty — effector-dependent analysis will be skipped.")

        q.put({"type": "progress", "message": "Loading terrain model…", "pct": 15})
        site = load_dem(config.site_dem_path, dsm_path=config.site_dsm_path)

        q.put({"type": "progress", "message": "Loading site boundary…", "pct": 20})
        if config.boundary_path is not None:
            loaded_boundary = load_boundary(config.boundary_path, site_epsg=site.crs_epsg)
            bitmask = boundary_mask(site, loaded_boundary)
        else:
            bitmask = np.ones((site.rows, site.cols), dtype=bool)

        # Build placements_by_type for coverage computation.
        placements_by_type: dict[SensorType, list[tuple[SensorDefinition, SensorPlacement]]] = {}
        for placement in config.sensor_placements:
            sensor = sensor_map.get(placement.sensor_name)
            if sensor is None:
                _log.warning(
                    "Sensor '%s' not in library — skipping placement.", placement.sensor_name
                )
                continue
            placements_by_type.setdefault(sensor.type, []).append((sensor, placement))

        n_placements = sum(len(v) for v in placements_by_type.values())
        q.put(
            {
                "type": "progress",
                "message": f"Computing coverage for {n_placements} sensor placement(s)…",
                "pct": 30,
            }
        )

        if placements_by_type:
            layer_coverages = compute_layer_coverage(site, placements_by_type)
        else:
            layer_coverages = {}

        q.put({"type": "progress", "message": "Computing composite coverage…", "pct": 60})

        if layer_coverages:
            composite = compute_composite_coverage(layer_coverages)
        else:
            composite = np.zeros((site.rows, site.cols), dtype=bool)

        gaps = compute_gaps(composite, bitmask)

        q.put({"type": "progress", "message": "Computing coverage statistics…", "pct": 70})
        stats = compute_coverage_stats(site, layer_coverages, composite, gaps, site.zones)

        q.put({"type": "progress", "message": "Rendering coverage maps…", "pct": 80})
        sensor_positions = [
            (p.position_x, p.position_y)
            for p in config.sensor_placements
            if sensor_map.get(p.sensor_name) is not None
        ]

        composite_map_b64 = (
            _render_to_b64_api(
                render_composite_coverage_map,
                site,
                layer_coverages,
                title="Composite Coverage",
                sensor_positions=sensor_positions,
            )
            if layer_coverages
            else None
        )

        # D-312 fix: initialise tmp_gap before the try block to avoid NameError in finally.
        gap_map_b64 = (
            _render_to_b64_api(
                render_gap_map,
                site,
                composite,
                gaps,
                title="Coverage Gap Analysis",
                sensor_positions=sensor_positions,
            )
            if layer_coverages
            else None
        )

        layer_maps_b64: dict[str, str] = {}
        for stype, arr in layer_coverages.items():
            b64 = _render_to_b64_api(
                render_composite_coverage_map,
                site,
                {stype: arr},
                title=f"{stype.value} Layer Coverage",
                sensor_positions=sensor_positions,
            )
            if b64 is not None:
                layer_maps_b64[stype.value] = b64

        executive_summary = generate_executive_summary(stats, [], None)
        assumptions = _build_minimal_assumptions(config)

        q.put({"type": "progress", "message": "Simulation complete.", "pct": 100})

        per_layer_pct = {k.value: v for k, v in stats.per_layer_coverage_pct.items()}

        result: dict[str, Any] = {
            "scenario_name": Path(config.site_dem_path).stem,
            "generated_at": _now_iso(),
            "total_coverage_pct": stats.total_coverage_pct,
            "gap_area_m2": stats.gap_area_m2,
            "largest_contiguous_gap_m2": stats.largest_contiguous_gap_m2,
            "per_layer_coverage_pct": per_layer_pct,
            "per_zone_coverage_pct": dict(stats.per_zone_coverage_pct),
            "composite_map_b64": composite_map_b64,
            "gap_map_b64": gap_map_b64,
            "layer_maps_b64": layer_maps_b64,
            "kill_chain_chart_b64": None,
            "saturation_chart_b64": None,
            "executive_summary": executive_summary,
            "assumptions": assumptions,
        }
        q.put({"type": "complete", "result": result})

    except Exception as exc:
        _log.exception("Simulation pipeline failed")
        q.put({"type": "error", "message": str(exc)})


def _build_minimal_assumptions(config: ScenarioConfig) -> dict[str, list[str]]:
    """Build a minimal assumptions dict from a scenario config."""
    return {
        "Terrain Model": [
            f"DEM source: {Path(config.site_dem_path).name}",
            "Binary detection model (no Pd curves)",
        ],
        "Propagation Model": [
            "No multipath or atmospheric effects modelled",
            "Straight-line LOS only",
        ],
    }


def _run_optimise_pipeline(
    request: OptimiserRequest,
    q: _queue.Queue[dict[str, Any]],
) -> None:
    """Run the greedy placement optimiser in a background thread."""
    try:
        from salus.engine.placement import (
            PlacementWeights,
            generate_candidate_positions,
            greedy_place_sensors,
        )

        q.put({"type": "progress", "message": "Loading terrain model…", "pct": 10})
        site = load_dem(Path(request.terrain))

        q.put({"type": "progress", "message": "Loading sensor library…", "pct": 20})
        sensor_defs = _get_sensor_defs()
        sensor_map = {s.name: s for s in sensor_defs}

        sensors_to_place: list[SensorDefinition] = []
        for name in request.sensor_library_filter:
            sd = sensor_map.get(name)
            if sd is None:
                _log.warning("Sensor '%s' not found in library — skipping.", name)
            else:
                sensors_to_place.append(sd)

        if not sensors_to_place:
            q.put({"type": "error", "message": "No valid sensors to place after library lookup."})
            return

        q.put({"type": "progress", "message": "Generating candidate positions…", "pct": 30})
        candidates = generate_candidate_positions(
            site,
            boundary=None,
            step_m=request.constraints.step_m,
            exclusion_zones=[],
        )

        placement_weights: PlacementWeights | None = None
        if request.constraints.weights:
            placement_weights = PlacementWeights(**request.constraints.weights)

        q.put(
            {
                "type": "progress",
                "message": f"Placing {len(sensors_to_place)} sensor(s) on "
                f"{len(candidates)} candidate positions…",
                "pct": 40,
            }
        )

        placed = greedy_place_sensors(
            site,
            sensors_to_place=sensors_to_place,
            candidates=candidates,
            coverage_threshold_pct=request.constraints.coverage_threshold_pct,
            weights=placement_weights,
        )

        q.put({"type": "progress", "message": "Computing final coverage…", "pct": 80})

        placements_by_type: dict[SensorType, list[tuple[SensorDefinition, SensorPlacement]]] = {}
        for placement in placed:
            sensor = sensor_map.get(placement.sensor_name)
            if sensor is not None:
                placements_by_type.setdefault(sensor.type, []).append((sensor, placement))

        if placed and not placements_by_type:
            _log.warning(
                "Post-placement sensor lookup failed for all placed sensors — "
                "coverage_pct will be 0.0"
            )

        coverage_pct = 0.0
        if placements_by_type:
            layer_coverages = compute_layer_coverage(site, placements_by_type)
            composite = compute_composite_coverage(layer_coverages)
            bitmask = np.ones((site.rows, site.cols), dtype=bool)
            gaps = compute_gaps(composite, bitmask)
            stats = compute_coverage_stats(site, layer_coverages, composite, gaps, site.zones)
            coverage_pct = stats.total_coverage_pct

        q.put({"type": "progress", "message": "Optimisation complete.", "pct": 100})

        result: dict[str, Any] = {
            "proposed_placements": [p.model_dump(mode="json") for p in placed],
            "score": coverage_pct,
            "coverage_pct": coverage_pct,
            "total_cost_aud": 0.0,
            "satisfied_constraints": (
                [f"coverage >= {request.constraints.coverage_threshold_pct}%"]
                if coverage_pct >= request.constraints.coverage_threshold_pct
                else []
            ),
            "violated_constraints": (
                [f"coverage < {request.constraints.coverage_threshold_pct}%"]
                if coverage_pct < request.constraints.coverage_threshold_pct
                else []
            ),
        }
        q.put({"type": "complete", "result": result})

    except Exception as exc:
        _log.exception("Optimiser pipeline failed")
        q.put({"type": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# Terrain tile helpers (S14.3)
# ---------------------------------------------------------------------------


def _compute_zoom_levels(resolution_m: float) -> tuple[int, int]:
    """Return (min_zoom, max_zoom) for an XYZ tile pyramid at *resolution_m*.

    Targets the zoom level where the WebMercator pixel size is closest to the
    DEM pixel size.  Clamped to [5, 13] to keep tile counts manageable.
    """
    # Pixel size at zoom Z (WebMercator) = 40_075_016.686 / (256 * 2^Z) metres
    z_ideal = math.log2(max(40_075_016.686 / (256.0 * max(resolution_m, 0.1)), 1.0))
    max_zoom = int(max(5, min(13, round(z_ideal))))
    min_zoom = max(0, max_zoom - 5)
    return min_zoom, max_zoom


def _compute_dem_bounds_wgs84(
    dem_path: Path,
) -> tuple[list[float], list[float], float, int | None]:
    """Return WGS84 bounds, centre, resolution (m), and CRS EPSG from a GeoTIFF.

    Returns:
        (bounds_wgs84, centre_wgs84, resolution_m, crs_epsg)
        where bounds_wgs84 = [west, south, east, north] (degrees).

    Raises:
        ValueError: if the DEM has no CRS.
    """
    import rasterio  # lazy — avoid adding to app startup time
    import rasterio.crs
    import rasterio.warp

    with rasterio.open(dem_path) as src:
        if src.crs is None:
            raise ValueError(f"DEM has no CRS defined: {dem_path}")

        # Convert pixel size to metres.  For projected CRS the transform unit is
        # already metres; for geographic CRS it is degrees — multiply by the
        # approximate metres-per-degree at the equator so _compute_zoom_levels
        # receives a consistent unit (D-323).
        raw_pixel_size = float(abs(src.transform.a))
        if src.crs.is_geographic:
            # 1° latitude ≈ 111 320 m (Earth circumference / 360)
            resolution_m = raw_pixel_size * 111_320.0
        else:
            resolution_m = raw_pixel_size
        wgs84 = rasterio.crs.CRS.from_epsg(4326)
        west, south, east, north = rasterio.warp.transform_bounds(
            src.crs,
            wgs84,
            src.bounds.left,
            src.bounds.bottom,
            src.bounds.right,
            src.bounds.top,
        )

        crs_epsg: int | None = None
        try:
            crs_epsg = src.crs.to_epsg()
        except Exception as _epsg_exc:
            _log.debug("DEM CRS has no EPSG code (%s): %s", dem_path, _epsg_exc)

    bounds_wgs84 = [float(west), float(south), float(east), float(north)]
    centre_wgs84 = [float((west + east) / 2.0), float((south + north) / 2.0)]
    return bounds_wgs84, centre_wgs84, resolution_m, crs_epsg


def _generate_terrain_tile(dem_path: Path, z: int, x: int, y: int) -> bytes | None:
    """Generate a Terrarium-encoded PNG for one XYZ tile from a DEM GeoTIFF.

    Returns None if the tile is entirely outside the DEM extent.
    Terrarium encoding: height = R * 256 + G + B/256 − 32768 (metres).
    """
    import mercantile  # lazy — avoid adding to app startup time
    import rasterio
    import rasterio.crs
    import rasterio.transform
    import rasterio.warp
    from PIL import Image

    tile_bounds = mercantile.xy_bounds(x, y, z)  # (left, bottom, right, top) EPSG:3857
    tile_size = 256

    dst_crs = rasterio.crs.CRS.from_epsg(3857)
    dst_transform = rasterio.transform.from_bounds(
        tile_bounds.left,
        tile_bounds.bottom,
        tile_bounds.right,
        tile_bounds.top,
        tile_size,
        tile_size,
    )
    dst_elevation = np.full((tile_size, tile_size), np.nan, dtype=np.float64)

    try:
        with rasterio.open(dem_path) as src:
            rasterio.warp.reproject(
                source=rasterio.band(src, 1),
                destination=dst_elevation,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=rasterio.warp.Resampling.bilinear,
                src_nodata=src.nodata,
                dst_nodata=np.nan,
            )
    except Exception as exc:
        _log.debug("Tile (%d/%d/%d) reproject failed: %s", z, x, y, exc)
        return None

    # Tile entirely outside DEM extent — return no-content signal
    if np.all(np.isnan(dst_elevation)):
        return None

    # Replace nodata (NaN) with sea level before encoding
    dst_elevation = np.where(np.isnan(dst_elevation), 0.0, dst_elevation)

    # Encode elevation as Terrarium RGB:
    #   R = floor(h / 256),  G = floor(h) % 256,  B = floor(h * 256) % 256
    #   where h = elevation + 32768  (ensures h ≥ 0 for elevations ≥ −32768 m)
    #   Decoding: height = R*256 + G + B/256 − 32768
    # Use floor-based encoding throughout (D-324: np.round uses banker's rounding
    # which introduces systematic error; floor matches the Terrarium reference).
    h = dst_elevation + 32768.0
    h_floor = np.floor(h).astype(np.int64)
    r = (h_floor // 256).clip(0, 255).astype(np.uint8)
    g = (h_floor % 256).astype(np.uint8)
    b = (np.floor(h * 256.0).astype(np.int64) % 256).astype(np.uint8)
    rgb = np.stack([r, g, b], axis=-1)

    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _run_tile_generation(
    dem_path: Path,
    tile_dir: Path,
    min_zoom: int,
    max_zoom: int,
    bounds_wgs84: list[float],
    total_tiles: int,
) -> None:
    """Pre-generate all tiles in background; update session progress."""
    import mercantile  # lazy — avoid adding to app startup time

    try:
        west, south, east, north = bounds_wgs84
        generated = 0
        written = 0

        for z in range(min_zoom, max_zoom + 1):
            tiles = list(mercantile.tiles(west, south, east, north, zooms=z))

            for tile in tiles:
                tile_data = _generate_terrain_tile(dem_path, tile.z, tile.x, tile.y)
                if tile_data is not None:
                    tile_file = tile_dir / str(tile.z) / str(tile.x) / f"{tile.y}.png"
                    tile_file.parent.mkdir(parents=True, exist_ok=True)
                    tile_file.write_bytes(tile_data)
                    written += 1

                generated += 1
                pct = int(generated * 100 / max(total_tiles, 1))
                with _terrain_session_lock:
                    _terrain_session["progress_pct"] = pct

        # Guard against silent total failure (D-326): if all tiles were skipped
        # (e.g. DEM CRS incompatible with EPSG:3857 reproject), report an error
        # instead of falsely claiming completion.
        if written == 0 and total_tiles > 0:
            _log.warning(
                "Terrain tile generation wrote 0/%d tiles — all reprojects failed.",
                total_tiles,
            )
            with _terrain_session_lock:
                _terrain_session["error"] = (
                    "All terrain tiles failed to generate (0 of "
                    f"{total_tiles} written). Check DEM CRS compatibility."
                )
                _terrain_session["done"] = True
            return

        with _terrain_session_lock:
            _terrain_session["progress_pct"] = 100
            _terrain_session["done"] = True

    except Exception as exc:
        _log.exception("Terrain tile generation failed")
        with _terrain_session_lock:
            _terrain_session["error"] = str(exc)
            _terrain_session["done"] = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Return service health and version."""
    return {"status": "ok", "version": __version__}


@app.get("/api/sensors")
async def sensors() -> dict[str, list[dict[str, Any]]]:
    """Return sensor definitions grouped by type."""
    defs = _get_sensor_defs()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sd in defs:
        grouped.setdefault(sd.type.value, []).append(sd.model_dump(mode="json"))
    return grouped


@app.get("/api/effectors")
async def effectors() -> dict[str, list[dict[str, Any]]]:
    """Return effector definitions grouped by type."""
    defs = _get_effector_defs()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ed in defs:
        grouped.setdefault(ed.type.value, []).append(ed.model_dump(mode="json"))
    return grouped


@app.post("/api/simulate")
async def simulate(config: ScenarioConfig) -> StreamingResponse:
    """Run the full simulation pipeline with SSE progress stream.

    Request body: ScenarioConfig-compatible JSON.

    Response: ``text/event-stream`` SSE.  Each event is a JSON object with a
    ``type`` field (``"progress"`` | ``"complete"`` | ``"error"``).  The
    ``"complete"`` event carries a ``result`` field containing a
    :class:`SimResultsPayload`-compatible dict.
    """
    q: _queue.Queue[dict[str, Any]] = _queue.Queue()
    thread = threading.Thread(
        target=_run_simulate_pipeline,
        args=(config, q),
        daemon=True,
    )
    thread.start()
    return StreamingResponse(_drain_queue(q), media_type="text/event-stream")


@app.post("/api/optimise")
async def optimise(request: OptimiserRequest) -> StreamingResponse:
    """Run the greedy placement optimiser with SSE progress stream.

    Request body: :class:`OptimiserRequest` JSON.

    Response: ``text/event-stream`` SSE terminating in a ``"complete"`` event
    with ``result`` containing :class:`OptimiserResultsPayload`-compatible dict.
    """
    q: _queue.Queue[dict[str, Any]] = _queue.Queue()
    thread = threading.Thread(
        target=_run_optimise_pipeline,
        args=(request, q),
        daemon=True,
    )
    thread.start()
    return StreamingResponse(_drain_queue(q), media_type="text/event-stream")


@app.post("/api/report")
async def report(request: ReportRequest) -> Response:
    """Generate a PDF report from pre-computed simulation results.

    Request body: :class:`ReportRequest` JSON containing ``report_config`` and
    ``sim_results`` (from a prior ``/api/simulate`` call).

    Response: PDF binary stream (``application/pdf``).
    """
    try:
        scenario = ScenarioConfig.model_validate(request.report_config)
    except Exception as exc:
        return Response(
            content=json.dumps({"error": f"Invalid report_config: {exc}"}),
            status_code=422,
            media_type="application/json",
        )

    sr = request.sim_results

    # Reconstruct CoverageStats from the serialisable payload.
    # redundancy_map is not used in PDF templates — a 1×1 zero array is sufficient.
    per_layer_pct: dict[SensorType, float] = {}
    for k, v in sr.per_layer_coverage_pct.items():
        try:
            per_layer_pct[SensorType(k)] = v
        except ValueError:
            _log.warning("Unknown sensor type key '%s' in sim_results — skipping.", k)

    stats = CoverageStats(
        total_coverage_pct=sr.total_coverage_pct,
        per_layer_coverage_pct=per_layer_pct,
        per_zone_coverage_pct=dict(sr.per_zone_coverage_pct),
        gap_area_m2=sr.gap_area_m2,
        redundancy_map=np.zeros((1, 1), dtype=np.intp),
        largest_contiguous_gap_m2=sr.largest_contiguous_gap_m2,
    )

    sensor_defs = _get_sensor_defs()
    effector_defs = _get_effector_defs()

    scenario_name = sr.scenario_name or Path(str(scenario.site_dem_path)).stem
    generated_at = sr.generated_at or _now_iso()

    report_data = ReportData(
        scenario_name=scenario_name,
        generated_at=generated_at,
        stats=stats,
        executive_summary=sr.executive_summary or "",
        assumptions=dict(sr.assumptions),
        sensor_defs=sensor_defs,
        effector_defs=effector_defs,
        sensor_placements=scenario.sensor_placements,
        scenario=scenario,
        composite_map_b64=sr.composite_map_b64,
        gap_map_b64=sr.gap_map_b64,
        layer_maps_b64=dict(sr.layer_maps_b64),
        kill_chain_chart_b64=sr.kill_chain_chart_b64,
        saturation_chart_b64=sr.saturation_chart_b64,
        corridor_results=[],
        kill_chain_results=[],
        saturation_result=None,
        kill_chain_config=None,
    )

    tmp_pdf: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_pdf = Path(f.name)
        render_pdf(report_data, tmp_pdf)
        pdf_bytes = tmp_pdf.read_bytes()
    except Exception as exc:
        _log.exception("PDF render failed")
        return Response(
            content=json.dumps({"error": f"PDF render failed: {exc}"}),
            status_code=500,
            media_type="application/json",
        )
    finally:
        if tmp_pdf is not None:
            tmp_pdf.unlink(missing_ok=True)

    return Response(content=pdf_bytes, media_type="application/pdf")


# ---------------------------------------------------------------------------
# Terrain endpoints (S14.3)
# ---------------------------------------------------------------------------


@app.post("/api/terrain/load")
async def terrain_load(
    dem_file: UploadFile = File(...),
    dsm_file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    """Upload a DEM (and optional DSM) and start terrain tile generation.

    Saves the uploaded GeoTIFF(s) to a persistent temporary directory,
    extracts WGS84 bounds and zoom levels, starts background tile generation,
    and returns the terrain metadata immediately.

    The browser module should poll GET /api/terrain/tile-progress for progress.
    Tiles are served at GET /api/terrain/tiles/{z}/{x}/{y}.png.

    Returns:
        Terrain metadata dict matching the ``terrain`` state key schema.
    """
    _TERRAIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    session_dir = _TERRAIN_DATA_DIR / session_id
    session_dir.mkdir(parents=True)
    tile_dir = session_dir / "tiles"
    tile_dir.mkdir()

    # Persist DEM file — guard against oversized uploads (D-327)
    dem_path = session_dir / "dem.tif"
    dem_contents = await dem_file.read()
    if len(dem_contents) > _MAX_DEM_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"DEM file too large: {len(dem_contents) // (1024 * 1024)} MB "
                f"exceeds {_MAX_DEM_UPLOAD_BYTES // (1024 * 1024)} MB limit."
            ),
        )
    dem_path.write_bytes(dem_contents)

    # Persist optional DSM file
    dsm_path: Path | None = None
    if dsm_file is not None:
        dsm_path = session_dir / "dsm.tif"
        dsm_contents = await dsm_file.read()
        if len(dsm_contents) > _MAX_DEM_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"DSM file too large: {len(dsm_contents) // (1024 * 1024)} MB "
                    f"exceeds {_MAX_DEM_UPLOAD_BYTES // (1024 * 1024)} MB limit."
                ),
            )
        dsm_path.write_bytes(dsm_contents)

    # Extract metadata from the DEM
    try:
        bounds_wgs84, centre_wgs84, resolution_m, crs_epsg = _compute_dem_bounds_wgs84(dem_path)
    except Exception as exc:
        _log.warning("terrain_load: failed to read DEM metadata: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))

    import mercantile  # lazy — avoid adding to app startup time

    min_zoom, max_zoom = _compute_zoom_levels(resolution_m)
    west, south, east, north = bounds_wgs84

    total_tiles = sum(
        len(list(mercantile.tiles(west, south, east, north, zooms=z)))
        for z in range(min_zoom, max_zoom + 1)
    )

    metadata: dict[str, Any] = {
        "dem_path": str(dem_path),
        "dsm_path": str(dsm_path) if dsm_path is not None else None,
        "crs_epsg": crs_epsg,
        "bounds_wgs84": bounds_wgs84,
        "centre_wgs84": centre_wgs84,
        "resolution_m": resolution_m,
        "tile_url_template": "/api/terrain/tiles/{z}/{x}/{y}.png",
        "terrain_tile_count": total_tiles,
        "terrain_min_zoom": min_zoom,
        "terrain_max_zoom": max_zoom,
    }

    with _terrain_session_lock:
        _terrain_session.update(
            {
                "dem_path": dem_path,
                "dsm_path": dsm_path,
                "metadata": metadata,
                "progress_pct": 0,
                "done": False,
                "error": None,
                "tile_dir": tile_dir,
            }
        )

    thread = threading.Thread(
        target=_run_tile_generation,
        args=(dem_path, tile_dir, min_zoom, max_zoom, bounds_wgs84, total_tiles),
        daemon=True,
    )
    thread.start()

    return metadata


@app.get("/api/terrain/tile-progress")
async def terrain_tile_progress() -> StreamingResponse:
    """SSE stream for terrain tile generation progress.

    Emits ``{"type": "progress", "pct": N}`` events (N = 0–99) until the
    background generation thread is complete, then emits
    ``{"type": "complete", "pct": 100}`` and closes the stream.

    If tile generation fails, emits ``{"type": "error", "message": "..."}`` and
    closes the stream.
    """

    async def _generate() -> AsyncGenerator[str, None]:
        # Guard: if no terrain session is active, report an error immediately
        # rather than streaming infinite progress=0 events (D-328).
        with _terrain_session_lock:
            no_session = _terrain_session["dem_path"] is None

        if no_session:
            yield _sse_event({"type": "error", "message": "No terrain session active."})
            return

        while True:
            with _terrain_session_lock:
                pct = _terrain_session["progress_pct"]
                done = _terrain_session["done"]
                error = _terrain_session["error"]

            if error:
                yield _sse_event({"type": "error", "message": error})
                break
            if done:
                yield _sse_event({"type": "complete", "pct": 100})
                break
            yield _sse_event({"type": "progress", "pct": pct})
            await asyncio.sleep(0.25)

    return StreamingResponse(_generate(), media_type="text/event-stream")


@app.get("/api/terrain/tiles/{z}/{x}/{y}.png")
async def terrain_tile(z: int, x: int, y: int) -> Response:
    """Serve a Terrarium-encoded PNG tile for the current terrain session.

    Serves pre-generated tiles from disk when available; falls back to
    on-demand generation for tiles requested before the background thread
    has written them.

    Returns 404 if no terrain session is active or the tile is outside the DEM.
    """
    with _terrain_session_lock:
        tile_dir = _terrain_session["tile_dir"]
        dem_path = _terrain_session["dem_path"]

    if tile_dir is None:
        return Response(status_code=404)

    # Fast path: serve pre-generated tile from disk
    tile_path = tile_dir / str(z) / str(x) / f"{y}.png"
    if tile_path.exists():
        return Response(content=tile_path.read_bytes(), media_type="image/png")

    # On-demand fallback for tiles requested before pre-generation completes
    if dem_path is None:
        return Response(status_code=404)

    loop = asyncio.get_running_loop()
    tile_data: bytes | None = await loop.run_in_executor(
        None, _generate_terrain_tile, dem_path, z, x, y
    )

    if tile_data is None:
        return Response(status_code=404)

    return Response(content=tile_data, media_type="image/png")
