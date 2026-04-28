"""FastAPI backend API for the Salus interactive interface (S14.2).

Exposes the existing Salus Python engine behind a thin HTTP/SSE layer that
browser modules can call.  No new simulation logic — this is a JSON/SSE
wrapper around the engine's existing Pydantic models and CLI functions.

The server is a localhost-only service: CORS is restricted to localhost
origins.  No authentication is required.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import os
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

# Paths outside these directories must not be opened via /api/simulate or
# /api/optimise.  The canonical source of DEM/DSM files at runtime is
# ``_TERRAIN_DATA_DIR`` (populated by ``/api/terrain/load``).  Additional
# trusted roots can be registered via the ``SALUS_ALLOWED_DEM_DIRS``
# environment variable (colon-separated list of absolute directory paths) —
# used by tests and demo runners that serve DEMs from fixture locations.
_ALLOWED_DEM_DIRS: list[Path] = [_TERRAIN_DATA_DIR]
_env_dirs = os.environ.get("SALUS_ALLOWED_DEM_DIRS", "")
for _d in _env_dirs.split(os.pathsep):
    _d = _d.strip()
    if not _d:
        continue
    try:
        _ALLOWED_DEM_DIRS.append(Path(_d).resolve(strict=False))
    except (OSError, ValueError) as _exc:
        _log.warning("Ignoring SALUS_ALLOWED_DEM_DIRS entry %r: %s", _d, _exc)


def _register_allowed_dem_dir(path: Path) -> None:
    """Add a directory to the DEM/DSM path allowlist at runtime.

    Used by pytest fixtures so that DEMs created under ``tmp_path`` pass the
    path-traversal guard.  Callers supply an absolute directory; duplicates
    are accepted and skipped transparently.
    """
    try:
        resolved = path.resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot register allowed DEM dir {path!r}: {exc}") from exc
    if resolved not in _ALLOWED_DEM_DIRS:
        _ALLOWED_DEM_DIRS.append(resolved)


def _validate_dem_path(raw_path: str | Path | None) -> Path | None:
    """Resolve *raw_path* and ensure it lives under an allowed directory.

    Returns the resolved Path on success, ``None`` if *raw_path* is ``None``.
    Raises :class:`fastapi.HTTPException` 400 for malformed input, 403 for
    paths that escape the allowlist (path-traversal guard).
    """
    if raw_path is None:
        return None
    try:
        resolved = Path(raw_path).resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid path {raw_path!r}: {exc}")

    for allowed in _ALLOWED_DEM_DIRS:
        try:
            resolved.relative_to(allowed)
            return resolved
        except ValueError:
            continue

    # Log the attempted path (not the full filesystem structure) — useful to
    # spot recon probes without leaking layout via response bodies.
    _log.warning("Rejected DEM path outside allowlist: %s", resolved)
    raise HTTPException(
        status_code=403,
        detail="DEM path is outside the allowed directories.",
    )


# Maximum accepted DEM/DSM upload size (500 MB).  Prevents OOM on oversized
# uploads that would otherwise buffer entirely in memory (D-327).
_MAX_DEM_UPLOAD_BYTES: int = 500 * 1024 * 1024

# Per-session terrain state shared between the load endpoint and the tile
# generation background thread.  The map is keyed by session_id so two
# concurrent loads do not clobber each other's progress / tile_dir / dem_path.
# ``_terrain_latest_session_id`` is only used by the legacy (unqualified)
# tile endpoints — new clients pass session_id explicitly.
# Both are protected by ``_terrain_session_lock``.
_terrain_session_lock: threading.Lock = threading.Lock()
_sensor_cache_lock: threading.Lock = threading.Lock()
_effector_cache_lock: threading.Lock = threading.Lock()
_terrain_sessions: dict[str, dict[str, Any]] = {}
_terrain_latest_session_id: str | None = None


def _new_terrain_session_state() -> dict[str, Any]:
    """Default per-session state record — created once per /api/terrain/load call."""
    return {
        "dem_path": None,
        "dsm_path": None,
        "metadata": None,
        "progress_pct": 0,
        "done": False,
        "error": None,
        "tile_dir": None,
    }


def _resolve_terrain_session_id(session_id: str | None) -> str | None:
    """Return *session_id* if it identifies a live session, else the most recent
    one (legacy clients that omit the session_id query param).  Returns ``None``
    when no terrain sessions have ever been loaded."""
    with _terrain_session_lock:
        if session_id is not None and session_id in _terrain_sessions:
            return session_id
        return _terrain_latest_session_id


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

    zones: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    """Zone definitions (used for weighted placement scoring).

    Accepted as either the canonical ``{priority: PriorityZone[], exclusion: ExclusionZone[]}``
    interface shape (zone-editor's writer since I-6/D-410) or the legacy flat
    list.  Optimiser flow does not currently consume zones server-side, but
    accepting the canonical shape avoids 422-ing every request from the live UI."""

    constraints: OptimiserConstraints = Field(default_factory=OptimiserConstraints)
    """Placement and coverage constraints."""

    objective: str = "maximise_coverage"
    """Scoring objective. One of 'maximise_coverage', 'maximise_critical_zone_coverage',
    'minimise_cost'."""


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
    Section 6.  The report POST body is assembled by the client from live
    interface state, so all scenario-side fields are dicts-of-unknown-shape
    here: the backend normalises them (see :func:`_parse_report_request`).
    """

    report_config: dict[str, Any] = Field(default_factory=dict)
    """UI report configuration: ``{client_name, sanitise_level, include_modules, logo_path}``.
    Not a ScenarioConfig — the interface does not carry a site DEM path in
    this payload, and the scenario is reconstructed from ``placements``
    server-side."""

    sim_results: dict[str, Any] = Field(default_factory=dict)
    """Pre-computed simulation results from ``POST /api/simulate``.  Accepted
    in either the interface schema (nested ``stats``) or the legacy flat
    :class:`SimResultsPayload` shape — :func:`_extract_sim_stats` handles both."""

    placements: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=list)
    """Sensor/effector placements.  Accepted as either the canonical
    ``{sensors, effectors}`` interface shape or a legacy flat list."""

    zones: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    """Zone definitions (informational; used in appendix).  Either the
    canonical ``{priority, exclusion}`` shape or a legacy flat list."""

    threat_corridors: list[dict[str, Any]] = Field(default_factory=list)
    """Threat corridor results (informational; unused if not in sim_results)."""

    map_screenshot: str | None = None
    """Optional base64-encoded PNG map capture from the interface."""


class CompareRequest(BaseModel):
    """Request body for ``POST /api/compare``.

    Two composite coverage GeoJSON FeatureCollections.  The endpoint returns
    the spatial A-only, B-only, and intersection FeatureCollections computed
    via Shapely polygon boolean operations.
    """

    a_composite: dict[str, Any] = Field(
        default_factory=lambda: {"type": "FeatureCollection", "features": []}
    )
    """Scenario A composite coverage FeatureCollection."""

    b_composite: dict[str, Any] = Field(
        default_factory=lambda: {"type": "FeatureCollection", "features": []}
    )
    """Scenario B composite coverage FeatureCollection."""


class CompareResponse(BaseModel):
    """Response body for ``POST /api/compare``.

    Three GeoJSON FeatureCollections representing the spatial diff of the
    two input composite coverage layers.
    """

    a_only: dict[str, Any]
    """Features covered by A but not B (rendered red in the overlay view)."""

    b_only: dict[str, Any]
    """Features covered by B but not A (rendered green in the overlay view)."""

    both: dict[str, Any]
    """Features covered by both scenarios (rendered grey in the overlay view)."""


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
    with _sensor_cache_lock:
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
    with _effector_cache_lock:
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
    """Format a dict as a complete SSE event.

    The JS parser in simulation-runner/optimiser reads ``event:`` to dispatch
    on type; without this line every event would default to ``'message'`` and
    be silently dropped by the dispatch branches (D-404).
    """
    event_type = str(data.get("type", "message"))
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ui_zones(
    zones_payload: dict[str, Any] | list[dict[str, Any]],
    site_crs_epsg: int | None,
) -> list[Any]:
    """Parse the UI canonical zones payload into Zone objects for coverage analysis.

    Accepts the canonical {priority: [...], exclusion: [...]} dict shape from the
    zone-editor, or an empty/legacy value. Returns [] if the payload cannot be parsed.
    """
    from salus.models.zone import Zone, ZoneType

    if not isinstance(zones_payload, dict):
        return []

    zones: list[Zone] = []
    transformer = None

    try:
        import pyproj
        from shapely.geometry import shape as shapely_shape
        from shapely.ops import transform as shapely_transform

        if site_crs_epsg is not None and site_crs_epsg != 4326:
            transformer = pyproj.Transformer.from_crs(4326, site_crs_epsg, always_xy=True)
    except ImportError:
        _log.warning("pyproj/shapely not available — zone coverage stats will be skipped.")
        return []

    used_names: set[str] = set()

    def _make_unique_name(base: str) -> str:
        name = base
        counter = 1
        while name in used_names:
            name = f"{base}_{counter}"
            counter += 1
        used_names.add(name)
        return name

    def _parse_entry(entry: dict[str, Any], zone_type: Any) -> "Zone | None":
        if not isinstance(entry, dict):
            return None
        geom_dict = entry.get("geometry")
        if not geom_dict or not isinstance(geom_dict, dict):
            return None
        try:
            geom = shapely_shape(geom_dict)
            if transformer is not None:
                geom = shapely_transform(transformer.transform, geom)
            raw_name = entry.get("label") or entry.get("name") or zone_type.value
            name = _make_unique_name(str(raw_name))
            return Zone(name=name, zone_type=zone_type, geometry=geom)
        except Exception as exc:
            _log.warning("Skipping unparseable zone entry: %s", exc)
            return None

    for entry in zones_payload.get("priority") or []:
        z = _parse_entry(entry, ZoneType.critical_asset)
        if z is not None:
            zones.append(z)

    for entry in zones_payload.get("exclusion") or []:
        z = _parse_entry(entry, ZoneType.exclusion)
        if z is not None:
            zones.append(z)

    if zones:
        _log.info("Parsed %d zone(s) from UI payload for coverage analysis.", len(zones))
    return zones


def _run_simulate_pipeline(
    config: ScenarioConfig,
    q: _queue.Queue[dict[str, Any]],
) -> None:
    """Run the full simulation pipeline in a background thread.

    Emits SSE progress events to *q* and finishes with a ``complete`` event
    containing the *interface schema* defined in
    docs/Technical/InterfaceArchitecture.md §3 (``layers``, ``sensor_placements``,
    ``stats``, ``corridor_results``, ``kill_chain_results``, ``saturation_result``,
    ``sanitised``, ``generated_at``).  Base64 PNGs are NOT produced here — the
    live interface renders coverage client-side from vectorised GeoJSON layers,
    and the PDF report endpoint (``/api/report``) renders its own PNGs
    independently from the data the caller posts to it.
    """
    try:
        from salus.report.pdf import SimulationResults
        from salus.viewer.export import export_viewer_data

        q.put({"type": "progress", "message": "Loading sensor library…", "pct": 5})
        sensor_defs = _get_sensor_defs()
        sensor_map = {s.name: s for s in sensor_defs}

        q.put({"type": "progress", "message": "Loading effector library…", "pct": 10})
        effector_defs = _get_effector_defs()
        if not effector_defs:
            _log.warning("Effector library is empty — effector-dependent analysis will be skipped.")

        q.put({"type": "progress", "message": "Loading terrain model…", "pct": 15})
        site = load_dem(config.site_dem_path, dsm_path=config.site_dsm_path)
        ui_zones = _parse_ui_zones(config.zones, site.crs_epsg)

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

        # After the placements_by_type loop
        skipped_sensor_names = [
            p.sensor_name for p in config.sensor_placements if sensor_map.get(p.sensor_name) is None
        ]
        if skipped_sensor_names:
            q.put(
                {
                    "type": "progress",
                    "message": (
                        f"Warning: {len(skipped_sensor_names)} sensor(s) not found in "
                        f"library and skipped: {', '.join(skipped_sensor_names)}"
                    ),
                    "pct": 30,
                    "sensor_skip_count": len(skipped_sensor_names),
                    "skipped_sensor_names": skipped_sensor_names,
                }
            )

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
        stats = compute_coverage_stats(site, layer_coverages, composite, gaps, ui_zones)

        # Build the full SimulationResults so the viewer-export path can
        # vectorise coverage layers and build the sensor_placements
        # FeatureCollection in the canonical interface schema (D-405).
        sim_bundle = SimulationResults(
            site=site,
            scenario=config,
            composite=composite,
            layer_coverages=layer_coverages,
            stats=stats,
            sensor_defs=sensor_defs,
            effector_defs=effector_defs,
            gaps=gaps,
        )

        q.put(
            {"type": "progress", "message": "Vectorising coverage layers…", "pct": 85},
        )
        # skip_terrain_tiles=True — the interface serves terrain via /api/terrain
        viewer_data = export_viewer_data(sim_bundle, skip_terrain_tiles=True)

        q.put({"type": "progress", "message": "Simulation complete.", "pct": 100})

        # Build the interface-schema result.  We include BOTH naming variants
        # for coverage and largest-gap so both simulation-runner (reads
        # ``stats.coverage_pct``/``stats.largest_gap_area_m2``) and
        # scenario-comparison (reads ``stats.total_coverage_pct`` from loaded
        # viewer_data.js files) find what they expect without extra adapters.
        stats_payload: dict[str, Any] = dict(viewer_data.stats)
        total_coverage = stats_payload.get("total_coverage_pct")
        if total_coverage is not None and "coverage_pct" not in stats_payload:
            stats_payload["coverage_pct"] = total_coverage
        largest_contig = stats_payload.get("largest_contiguous_gap_m2")
        if largest_contig is not None and "largest_gap_area_m2" not in stats_payload:
            stats_payload["largest_gap_area_m2"] = largest_contig

        result: dict[str, Any] = {
            "scenario_name": viewer_data.scenario_name,
            "generated_at": viewer_data.generated_at,
            "bounds_wgs84": list(viewer_data.bounds_wgs84),
            "centre_wgs84": list(viewer_data.centre_wgs84),
            "layers": viewer_data.layers,
            "sensor_placements": viewer_data.sensor_placements,
            "stats": stats_payload,
            "corridor_results": viewer_data.corridor_results,
            "kill_chain_results": viewer_data.kill_chain_results,
            "saturation_result": viewer_data.saturation_result,
            "sanitised": viewer_data.sanitised,
            "sensor_skip_count": len(skipped_sensor_names),
        }
        q.put({"type": "complete", "result": result})

    except Exception as exc:
        _log.exception("Simulation pipeline failed")
        q.put({"type": "error", "message": str(exc)})


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

        _log.info("Optimiser objective: %s", request.objective)

        q.put({"type": "progress", "message": "Loading terrain model…", "pct": 10})
        site = load_dem(Path(request.terrain))
        ui_zones = _parse_ui_zones(getattr(request, "zones", {}), site.crs_epsg)

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
            objective=request.objective,
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
            stats = compute_coverage_stats(site, layer_coverages, composite, gaps, ui_zones)
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

    from salus.viewer.export import _encode_terrarium

    rgb = _encode_terrarium(dst_elevation.astype(np.float32))

    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _run_tile_generation(
    session_id: str,
    dem_path: Path,
    tile_dir: Path,
    min_zoom: int,
    max_zoom: int,
    bounds_wgs84: list[float],
    total_tiles: int,
) -> None:
    """Pre-generate all tiles in background; update progress for *session_id*.

    Two concurrent /api/terrain/load calls now update disjoint session
    records — previously both threads updated the single global
    ``_terrain_session`` dict which produced interleaved progress values
    and a dangling tile_dir for the losing load.
    """
    import mercantile  # lazy — avoid adding to app startup time

    def _update(key: str, value: object) -> None:
        """Atomically update one field of this session, if the session still exists."""
        with _terrain_session_lock:
            session = _terrain_sessions.get(session_id)
            if session is not None:
                session[key] = value

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
                _update("progress_pct", pct)

        # Guard against silent total failure (D-326): if all tiles were skipped
        # (e.g. DEM CRS incompatible with EPSG:3857 reproject), report an error
        # instead of falsely claiming completion.
        if written == 0 and total_tiles > 0:
            _log.warning(
                "Terrain tile generation wrote 0/%d tiles — all reprojects failed.",
                total_tiles,
            )
            with _terrain_session_lock:
                session = _terrain_sessions.get(session_id)
                if session is not None:
                    session["error"] = (
                        "All terrain tiles failed to generate (0 of "
                        f"{total_tiles} written). Check DEM CRS compatibility."
                    )
                    session["done"] = True
            return

        with _terrain_session_lock:
            session = _terrain_sessions.get(session_id)
            if session is not None:
                session["progress_pct"] = 100
                session["done"] = True

    except Exception as exc:
        _log.exception("Terrain tile generation failed")
        _update("error", str(exc))
        _update("done", True)


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
    # Path-traversal guard — refuse requests that reference files outside
    # the DEM allowlist before any background work begins.  We pin the
    # resolved (canonical) path back onto the config so the worker thread
    # opens the same file the validator inspected (closes a small TOCTOU
    # window where a symlink could be swapped between validate and open).
    resolved_dem = _validate_dem_path(config.site_dem_path)
    if resolved_dem is not None:
        config.site_dem_path = resolved_dem
    if config.site_dsm_path is not None:
        resolved_dsm = _validate_dem_path(config.site_dsm_path)
        if resolved_dsm is not None:
            config.site_dsm_path = resolved_dsm
    if config.boundary_path is not None:
        resolved_bdy = _validate_dem_path(config.boundary_path)
        if resolved_bdy is not None:
            config.boundary_path = resolved_bdy

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
    # Path-traversal guard — same policy as /api/simulate.  Pin the resolved
    # path back onto the request so the worker opens the validated file.
    resolved_terrain = _validate_dem_path(request.terrain)
    if resolved_terrain is not None:
        request.terrain = str(resolved_terrain)

    q: _queue.Queue[dict[str, Any]] = _queue.Queue()
    thread = threading.Thread(
        target=_run_optimise_pipeline,
        args=(request, q),
        daemon=True,
    )
    thread.start()
    return StreamingResponse(_drain_queue(q), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# S14.12: Spatial diff helpers
# ---------------------------------------------------------------------------


def _geometries_from_features(
    features: list[dict[str, Any]],
    scenario_label: str,
) -> list[Any]:
    """Convert a GeoJSON Feature list into Shapely geometries.

    Invalid features are skipped with a warning; a malformed collection never
    raises, which means a partially-corrupt scenario still yields a best-effort
    diff rather than a 500.  ``scenario_label`` is only used in log messages.
    """
    from shapely.geometry import shape as _shape

    geoms: list[Any] = []
    for idx, feat in enumerate(features):
        if not isinstance(feat, dict):
            _log.warning("%s: feature %d is not a dict, skipping.", scenario_label, idx)
            continue
        geom_dict = feat.get("geometry")
        if not geom_dict:
            continue
        try:
            g = _shape(geom_dict)
        except Exception as exc:
            _log.warning(
                "%s: feature %d geometry could not be parsed (%s), skipping.",
                scenario_label,
                idx,
                exc,
            )
            continue
        if g.is_empty:
            continue
        # Buffer(0) cleans up self-intersections that would otherwise break diffs.
        # D-403: if buffer(0) fails on an invalid geometry we SKIP the feature
        # rather than appending the raw invalid shape; keeping a known-invalid
        # geometry risks silently corrupting the downstream polygon booleans.
        if not g.is_valid:
            try:
                g = g.buffer(0)
            except Exception as exc:
                _log.warning(
                    "%s: feature %d is invalid and buffer(0) cleanup failed "
                    "(%s); skipping feature rather than risking diff corruption.",
                    scenario_label,
                    idx,
                    exc,
                )
                continue
            if g.is_empty:
                continue
        geoms.append(g)
    return geoms


def _geometry_to_feature_collection(geom: Any) -> dict[str, Any]:
    """Wrap a Shapely geometry as a GeoJSON FeatureCollection.

    An empty or None geometry yields an empty FeatureCollection rather than
    a feature with a null geometry.
    """
    from shapely.geometry import mapping as _mapping

    if geom is None or geom.is_empty:
        return {"type": "FeatureCollection", "features": []}

    # Multi-part geometries → one feature per component (keeps polygon boundaries
    # distinct for MapLibre rendering).  Single geometries become a single feature.
    geom_type = geom.geom_type
    features: list[dict[str, Any]]
    if geom_type in {"MultiPolygon", "MultiLineString", "MultiPoint", "GeometryCollection"}:
        features = []
        for sub in geom.geoms:
            if sub.is_empty:
                continue
            features.append(
                {"type": "Feature", "geometry": _mapping(sub), "properties": {}},
            )
    else:
        features = [{"type": "Feature", "geometry": _mapping(geom), "properties": {}}]

    return {"type": "FeatureCollection", "features": features}


@app.post("/api/compare")
async def compare(request: CompareRequest) -> CompareResponse:
    """Compute the spatial diff between two composite coverage FeatureCollections.

    Request body: :class:`CompareRequest` JSON with ``a_composite`` and
    ``b_composite`` GeoJSON FeatureCollections.

    Response: :class:`CompareResponse` JSON containing three FeatureCollections
    (``a_only``, ``b_only``, ``both``).  Empty inputs are supported — an empty
    scenario yields empty diff layers rather than an error.
    """
    from shapely.geometry import GeometryCollection
    from shapely.ops import unary_union

    a_features = request.a_composite.get("features", []) if request.a_composite else []
    b_features = request.b_composite.get("features", []) if request.b_composite else []

    if not isinstance(a_features, list) or not isinstance(b_features, list):
        raise HTTPException(
            status_code=422,
            detail="a_composite/b_composite.features must be a list.",
        )

    try:
        a_geoms = _geometries_from_features(a_features, "scenario A")
        b_geoms = _geometries_from_features(b_features, "scenario B")

        a_union: Any = unary_union(a_geoms) if a_geoms else GeometryCollection()
        b_union: Any = unary_union(b_geoms) if b_geoms else GeometryCollection()

        # difference() and intersection() short-circuit on empty inputs
        a_only = a_union.difference(b_union) if not a_union.is_empty else GeometryCollection()
        b_only = b_union.difference(a_union) if not b_union.is_empty else GeometryCollection()
        both = (
            a_union.intersection(b_union)
            if (not a_union.is_empty and not b_union.is_empty)
            else GeometryCollection()
        )
    except Exception as exc:
        _log.exception("Compare spatial operation failed")
        raise HTTPException(status_code=500, detail=f"Compare failed: {exc}")

    return CompareResponse(
        a_only=_geometry_to_feature_collection(a_only),
        b_only=_geometry_to_feature_collection(b_only),
        both=_geometry_to_feature_collection(both),
    )


def _extract_sim_stats(sim_results: dict[str, Any]) -> dict[str, Any]:
    """Extract coverage stats from either the interface schema or the legacy payload.

    The interface schema nests the stats fields under ``stats``; the legacy
    :class:`SimResultsPayload` shape keeps them at the top level.  We accept both.
    A non-empty nested ``stats`` dict is authoritative; an empty nested dict
    (``{"stats": {}}``) falls back to top-level fields rather than silently
    returning an empty dict (D-416).
    """
    nested = sim_results.get("stats")
    if isinstance(nested, dict) and nested:
        return dict(nested)
    return dict(sim_results)


def _parse_sensor_placements(
    raw: dict[str, Any] | list[dict[str, Any]],
) -> tuple[list[SensorPlacement], int]:
    """Normalise a placements payload (dict or list) into validated SensorPlacement objects.

    Invalid entries are logged and skipped rather than rejecting the whole request —
    a single malformed placement should not block report generation — but we also
    return the count of skipped entries so the caller can raise if every entry was
    invalid (D-414, prevents the silent empty-PDF failure).
    """
    if isinstance(raw, dict):
        entries = raw.get("sensors", []) or []
    elif isinstance(raw, list):
        entries = raw
    else:
        _log.warning(
            "placements payload is not dict|list (got %s) — treating as empty.",
            type(raw).__name__,
        )
        entries = []

    placements: list[SensorPlacement] = []
    skipped = 0
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            _log.warning("Placement %d is not a dict (got %s) — skipping.", i, type(entry).__name__)
            skipped += 1
            continue
        try:
            placements.append(SensorPlacement.model_validate(entry))
        except Exception as exc:
            _log.warning("Placement %d failed validation (%s) — skipping.", i, exc)
            skipped += 1
    return placements, skipped


@app.post("/api/report")
async def report(request: ReportRequest) -> Response:
    """Generate a PDF report from pre-computed simulation results.

    Request body: :class:`ReportRequest` JSON containing ``report_config``
    (UI config), ``sim_results`` (from a prior ``/api/simulate`` call), and
    the placement / zone / corridor state from the interface.

    The ScenarioConfig that :class:`ReportData` requires is reconstructed
    here from the placements field and a placeholder DEM path — the interface
    does not upload a DEM alongside the report and the PDF renderer only
    needs ``scenario.sensor_placements`` plus ``scenario.site_dem_path``
    (used for the scenario-name stem fallback).

    Response: PDF binary stream (``application/pdf``).
    """
    sim_results = request.sim_results or {}
    stats_raw = _extract_sim_stats(sim_results)
    placements, skipped_placements = _parse_sensor_placements(request.placements)

    # If every placement entry failed validation we refuse the request rather
    # than emit a clean PDF with zero placements (D-414 — silent-fail trap).
    raw_count = (
        len(request.placements.get("sensors", []) or [])
        if isinstance(request.placements, dict)
        else len(request.placements)
        if isinstance(request.placements, list)
        else 0
    )
    if raw_count > 0 and not placements:
        return Response(
            content=json.dumps(
                {
                    "error": "All sensor placements failed validation; refusing to "
                    f"render a PDF with zero placements (input had {raw_count})."
                }
            ),
            status_code=422,
            media_type="application/json",
        )
    if skipped_placements > 0:
        _log.warning(
            "report request: %d of %d placements skipped due to validation errors.",
            skipped_placements,
            raw_count,
        )

    # Reconstruct CoverageStats from whichever keys appear.  Both the
    # interface schema (total_coverage_pct / largest_contiguous_gap_m2) and
    # the D-405 aliases (coverage_pct / largest_gap_area_m2) are accepted.
    per_layer_raw = stats_raw.get("per_layer_coverage_pct") or {}
    per_layer_pct: dict[SensorType, float] = {}
    if isinstance(per_layer_raw, dict):
        for k, v in per_layer_raw.items():
            try:
                per_layer_pct[SensorType(k)] = float(v)
            except (ValueError, TypeError):
                _log.warning("Unknown sensor type key '%s' in sim_results — skipping.", k)
    elif per_layer_raw:
        # Truthy but not a dict (e.g. a list) — log so the silent drop is visible (D-417).
        _log.warning(
            "per_layer_coverage_pct is not a dict (got %s) — coverage by layer dropped.",
            type(per_layer_raw).__name__,
        )

    per_zone_raw = stats_raw.get("per_zone_coverage_pct") or {}

    def _num(*keys: str, default: float = 0.0) -> float:
        for key in keys:
            val = stats_raw.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        return default

    stats = CoverageStats(
        total_coverage_pct=_num("total_coverage_pct", "coverage_pct"),
        per_layer_coverage_pct=per_layer_pct,
        per_zone_coverage_pct=dict(per_zone_raw) if isinstance(per_zone_raw, dict) else {},
        gap_area_m2=_num("gap_area_m2"),
        redundancy_map=np.zeros((1, 1), dtype=np.intp),
        largest_contiguous_gap_m2=_num("largest_contiguous_gap_m2", "largest_gap_area_m2"),
    )

    sensor_defs = _get_sensor_defs()
    effector_defs = _get_effector_defs()

    scenario_name = sim_results.get("scenario_name") or stats_raw.get("scenario_name") or "scenario"
    generated_at = sim_results.get("generated_at") or _now_iso()

    # Build a minimal ScenarioConfig for the ReportData.scenario field.
    # render_pdf does not open the DEM; it only reads scenario.sensor_placements
    # and (at most) scenario.site_dem_path.stem for a name fallback.
    placeholder_dem = Path(tempfile.gettempdir()) / f"{scenario_name}.tif"
    scenario = ScenarioConfig(
        site_dem_path=placeholder_dem,
        sensor_placements=placements,
    )

    # Legacy SimResultsPayload-style pre-rendered PNG fields, if the client
    # happened to send them (most interface callers do not — the PDF re-renders
    # its own maps).  None values are tolerated downstream.
    composite_b64 = sim_results.get("composite_map_b64")
    gap_b64 = sim_results.get("gap_map_b64")
    layer_b64_raw = sim_results.get("layer_maps_b64") or {}
    layer_maps_b64 = dict(layer_b64_raw) if isinstance(layer_b64_raw, dict) else {}
    kill_chain_b64 = sim_results.get("kill_chain_chart_b64")
    saturation_b64 = sim_results.get("saturation_chart_b64")
    executive_summary = sim_results.get("executive_summary") or ""
    assumptions_raw = sim_results.get("assumptions") or {}
    assumptions = dict(assumptions_raw) if isinstance(assumptions_raw, dict) else {}

    report_data = ReportData(
        scenario_name=scenario_name,
        generated_at=generated_at,
        stats=stats,
        executive_summary=executive_summary,
        assumptions=assumptions,
        sensor_defs=sensor_defs,
        effector_defs=effector_defs,
        sensor_placements=placements,
        scenario=scenario,
        composite_map_b64=composite_b64 if isinstance(composite_b64, str) else None,
        gap_map_b64=gap_b64 if isinstance(gap_b64, str) else None,
        layer_maps_b64=layer_maps_b64,
        kill_chain_chart_b64=kill_chain_b64 if isinstance(kill_chain_b64, str) else None,
        saturation_chart_b64=saturation_b64 if isinstance(saturation_b64, str) else None,
        map_screenshot=request.map_screenshot if isinstance(request.map_screenshot, str) else None,
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
        "session_id": session_id,
        "dem_path": str(dem_path),
        "dsm_path": str(dsm_path) if dsm_path is not None else None,
        "crs_epsg": crs_epsg,
        "bounds_wgs84": bounds_wgs84,
        "centre_wgs84": centre_wgs84,
        "resolution_m": resolution_m,
        # Session-qualified tile URL — avoids the pre-S14 race where a second
        # /api/terrain/load would redirect the first session's tile requests to
        # the second session's DEM.
        "tile_url_template": f"/api/terrain/sessions/{session_id}/tiles/{{z}}/{{x}}/{{y}}.png",
        # Session-qualified progress URL — the legacy unsessioned endpoint
        # would report the latest session's progress to every client (D-426).
        "tile_progress_url": f"/api/terrain/sessions/{session_id}/tile-progress",
        "terrain_tile_count": total_tiles,
        "terrain_min_zoom": min_zoom,
        "terrain_max_zoom": max_zoom,
    }

    global _terrain_latest_session_id
    with _terrain_session_lock:
        session_state = _new_terrain_session_state()
        session_state.update(
            {
                "dem_path": dem_path,
                "dsm_path": dsm_path,
                "metadata": metadata,
                "tile_dir": tile_dir,
            }
        )
        _terrain_sessions[session_id] = session_state
        _terrain_latest_session_id = session_id

    thread = threading.Thread(
        target=_run_tile_generation,
        args=(session_id, dem_path, tile_dir, min_zoom, max_zoom, bounds_wgs84, total_tiles),
        daemon=True,
    )
    thread.start()

    return metadata


def _read_session_progress(session_id: str) -> tuple[int, bool, str | None]:
    """Snapshot (progress_pct, done, error) for *session_id* under the lock.

    Uses ``.get()`` rather than bracket lookup so a future change to the
    session-state schema cannot kill the SSE connection mid-stream (D-418).
    """
    with _terrain_session_lock:
        session = _terrain_sessions.get(session_id)
        if session is None:
            return 0, True, "Session no longer exists."
        return (
            int(session.get("progress_pct", 0)),
            bool(session.get("done", False)),
            session.get("error"),
        )


def _read_session_tile_paths(session_id: str) -> tuple[Path | None, Path | None]:
    """Snapshot (tile_dir, dem_path) for *session_id* under the lock."""
    with _terrain_session_lock:
        session = _terrain_sessions.get(session_id)
        if session is None:
            return None, None
        return session.get("tile_dir"), session.get("dem_path")


async def _stream_terrain_progress(session_id: str | None) -> AsyncGenerator[str, None]:
    """Yield SSE progress events for *session_id* (or the latest session)."""
    resolved = _resolve_terrain_session_id(session_id)
    if resolved is None:
        yield _sse_event({"type": "error", "message": "No terrain session active."})
        return

    while True:
        pct, done, error = _read_session_progress(resolved)
        if error:
            yield _sse_event({"type": "error", "message": error})
            return
        if done:
            yield _sse_event({"type": "complete", "pct": 100})
            return
        yield _sse_event({"type": "progress", "pct": pct})
        await asyncio.sleep(0.25)


async def _serve_terrain_tile(session_id: str | None, z: int, x: int, y: int) -> Response:
    """Serve a tile for *session_id* (or the latest session) — disk first, then on-demand."""
    resolved = _resolve_terrain_session_id(session_id)
    if resolved is None:
        return Response(status_code=404)

    tile_dir, dem_path = _read_session_tile_paths(resolved)
    if tile_dir is None:
        return Response(status_code=404)

    tile_path = tile_dir / str(z) / str(x) / f"{y}.png"
    if tile_path.exists():
        return Response(content=tile_path.read_bytes(), media_type="image/png")

    if dem_path is None:
        return Response(status_code=404)

    loop = asyncio.get_running_loop()
    tile_data: bytes | None = await loop.run_in_executor(
        None, _generate_terrain_tile, dem_path, z, x, y
    )
    if tile_data is None:
        return Response(status_code=404)
    return Response(content=tile_data, media_type="image/png")


@app.get("/api/terrain/tile-progress")
async def terrain_tile_progress() -> StreamingResponse:
    """SSE stream for the most recently loaded terrain session's tile generation.

    Emits ``{"type": "progress", "pct": N}`` events (N = 0–99) until the
    background generation thread is complete, then emits
    ``{"type": "complete", "pct": 100}`` and closes the stream.

    If tile generation fails, emits ``{"type": "error", "message": "..."}`` and
    closes the stream.

    Concurrent ``/api/terrain/load`` calls now write into per-session records
    (D-406); use the sessioned variant below if you need a specific session.
    """
    return StreamingResponse(_stream_terrain_progress(None), media_type="text/event-stream")


@app.get("/api/terrain/sessions/{session_id}/tile-progress")
async def terrain_tile_progress_sessioned(session_id: str) -> StreamingResponse:
    """SSE progress stream scoped to *session_id*.  See ``terrain_tile_progress``."""
    return StreamingResponse(_stream_terrain_progress(session_id), media_type="text/event-stream")


@app.get("/api/terrain/tiles/{z}/{x}/{y}.png")
async def terrain_tile(z: int, x: int, y: int) -> Response:
    """Serve a Terrarium-encoded PNG tile for the most recently loaded terrain.

    Returns 404 if no terrain session has been loaded or the tile is outside
    the DEM.  Prefer the sessioned endpoint below — concurrent loads tag tile
    URLs with their session id so a slow client cannot read another client's
    DEM (D-406).
    """
    return await _serve_terrain_tile(None, z, x, y)


@app.get("/api/terrain/sessions/{session_id}/tiles/{z}/{x}/{y}.png")
async def terrain_tile_sessioned(session_id: str, z: int, x: int, y: int) -> Response:
    """Serve a Terrarium tile scoped to *session_id*.  See ``terrain_tile``."""
    return await _serve_terrain_tile(session_id, z, x, y)
