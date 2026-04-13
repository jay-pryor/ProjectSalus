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
import json
import logging
import queue as _queue
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

import numpy as np
from fastapi import FastAPI
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
