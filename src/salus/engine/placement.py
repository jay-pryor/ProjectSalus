"""Greedy sensor placement optimisation engine (S9, S11.5).

Generates candidate deployment positions on a site grid and greedily
selects placements that maximise zone-weighted coverage.

The optimisation workflow:

1. Call :func:`generate_candidate_positions` to produce a grid of valid
   deployment points, filtered by boundary, exclusion zones, and slope.
2. Call :func:`greedy_place_sensors` with a list of sensors to place and
   the candidate grid.  The algorithm iterates over each sensor, scores
   every candidate by the weighted new coverage it would add, places the
   sensor at the best scoring position, and repeats.
3. The placement loop stops early when *coverage_threshold_pct* is reached.

Zone weighting (via :class:`PlacementWeights`) makes the optimiser prioritise
covering high-value zones before lower-priority areas:

- ``critical_asset``: 3× (default) — the zones that must not be exposed
- ``inner``: 2× (default)
- ``perimeter``: 1× (default)
- ``exclusion``: 0 — cells in exclusion zones are not scored
- ``unzoned``: 1× (default) — cells not covered by any named zone

Bearing-aware placement (S11.5):

For directional sensors (``azimuth_coverage_deg < 360``), each candidate
position is evaluated at multiple boresight bearings.  The underlying
viewshed (or propagation) is computed once per position; arc masks at each
bearing are then applied as cheap numpy operations.  The (position, bearing)
pair with the highest weighted score is selected.  Omnidirectional sensors
skip the bearing sweep entirely and are placed with bearing 0° (north).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import MultiPolygon, Point, Polygon

from salus.engine.dispatcher import compute_sensor_coverage
from salus.engine.viewshed import compute_viewshed
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.models.site import SiteModel
from salus.models.zone import Zone, ZoneType

_log = logging.getLogger(__name__)

# Steep-slope gradient threshold (m/m). Candidate positions where the DEM
# gradient magnitude exceeds this value are excluded as impractical deployment
# sites.  tan(45°) = 1.0 — slopes steeper than 45° are filtered out.
_STEEP_SLOPE_THRESHOLD: float = 1.0

# Default bearing (degrees, compass) assigned to omnidirectional sensors where
# the bearing sweep is skipped (azimuth_coverage_deg == 360).
_DEFAULT_BEARING_DEG: float = 0.0

# Full azimuth circle — sensors at or above this value are omnidirectional.
_FULL_ARC_DEG: float = 360.0

# Default bearing step for the bearing sweep in greedy_place_sensors.
# 10° gives 36 candidates per position — good balance of quality and speed.
_BEARING_STEP_DEG_DEFAULT: float = 10.0


@dataclass(frozen=True)
class Position:
    """A 2D candidate deployment point in CRS coordinates (metres)."""

    x: float
    """Easting in CRS units (metres)."""

    y: float
    """Northing in CRS units (metres)."""


class PlacementWeights(BaseModel):
    """Zone-type weighting factors for coverage scoring.

    Higher weights make the optimiser prioritise covering those zones
    over lower-weighted areas.  All weights must be finite and non-negative.

    Default values reflect operational priority:

    - ``critical_asset``: 3.0 (must cover first)
    - ``inner``: 2.0
    - ``perimeter``: 1.0
    - ``exclusion``: 0.0 (cells in exclusion zones are not scored)
    - ``unzoned``: 1.0 (cells not in any named zone score at baseline)
    """

    critical_asset: float = Field(default=3.0, ge=0.0)
    inner: float = Field(default=2.0, ge=0.0)
    perimeter: float = Field(default=1.0, ge=0.0)
    exclusion: float = Field(default=0.0, ge=0.0)
    unzoned: float = Field(default=1.0, ge=0.0)

    @field_validator("critical_asset", "inner", "perimeter", "exclusion", "unzoned")
    @classmethod
    def _weight_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"weight must be finite, got {v}")
        return v


def generate_candidate_positions(
    site: SiteModel,
    boundary: Polygon | MultiPolygon | None,
    step_m: float,
    exclusion_zones: list[Zone],
) -> list[Position]:
    """Generate a grid of candidate sensor deployment positions.

    Produces a regular grid of ``(x, y)`` positions across the site extent
    and filters out positions that are:

    - Outside the *boundary* polygon (when *boundary* is not ``None``).
    - Inside any of the *exclusion_zones*.
    - On steep terrain (DEM gradient magnitude > :data:`_STEEP_SLOPE_THRESHOLD`,
      approximately 45°).

    Water-body filtering is not applied — reliable water detection requires
    hydrological data that is not present in a bare DEM.

    Args:
        site: Site terrain model that defines the raster grid and extent.
        boundary: Optional boundary polygon. When provided, only positions
            inside the boundary are included.  Coordinates must be in the
            same CRS as the site DEM.
        step_m: Grid spacing in metres. Must be a finite positive number.
            Smaller values produce more candidates at greater computation cost.
        exclusion_zones: List of :class:`~salus.models.zone.Zone` objects
            whose interiors are excluded from the candidate set. Typically
            the ``exclusion``-type zones from the site.

    Returns:
        List of :class:`Position` objects.  May be empty if all grid points
        are filtered out (e.g. a very coarse step or a very small boundary).

    Raises:
        ValueError: If *step_m* is not a finite positive number.
    """
    if not math.isfinite(step_m) or step_m <= 0.0:
        raise ValueError(f"step_m must be a finite positive number, got {step_m}")

    min_x, max_x, min_y, max_y = site.extent

    xs = np.arange(min_x + step_m / 2.0, max_x, step_m)
    ys = np.arange(min_y + step_m / 2.0, max_y, step_m)

    if xs.size == 0 or ys.size == 0:
        _log.warning(
            "Step size %.1f m is larger than the site extent (%.1f × %.1f m); "
            "no candidate positions generated.",
            step_m,
            max_x - min_x,
            max_y - min_y,
        )
        return []

    # Pre-compute steep-slope mask from the DEM gradient.
    # np.gradient returns [d/d_row, d/d_col] — divide by resolution to get m/m.
    # D-177: Replace NaN (nodata cells) with a value above the threshold so that
    # positions that map to nodata pixels are treated as too steep and excluded.
    grad_row, grad_col = np.gradient(site.dem)
    gradient_magnitude: npt.NDArray[np.float64] = np.nan_to_num(
        np.sqrt((grad_row / site.resolution) ** 2 + (grad_col / site.resolution) ** 2),
        nan=_STEEP_SLOPE_THRESHOLD + 1.0,
    )

    # Build exclusion geometries once (avoid repeated attribute access in the loop).
    exclusion_geoms: list[Polygon | MultiPolygon] = [z.geometry for z in exclusion_zones]

    candidates: list[Position] = []

    for x in xs:
        for y in ys:
            pt = Point(x, y)

            # Boundary filter
            if boundary is not None and not boundary.contains(pt):
                continue

            # Exclusion zone filter
            if any(geom.contains(pt) for geom in exclusion_geoms):
                continue

            # Steep-slope filter — map CRS position to raster cell
            col = int((x - site.origin_x) / site.resolution)
            row = int((site.origin_y - y) / site.resolution)
            # Clamp to valid raster range (edge positions may land just outside)
            row = max(0, min(row, site.rows - 1))
            col = max(0, min(col, site.cols - 1))

            if gradient_magnitude[row, col] > _STEEP_SLOPE_THRESHOLD:
                continue

            candidates.append(Position(x=float(x), y=float(y)))

    _log.info(
        "Generated %d candidate positions (step=%.1f m, boundary=%s, exclusion_zones=%d).",
        len(candidates),
        step_m,
        "yes" if boundary is not None else "no",
        len(exclusion_zones),
    )
    return candidates


def _build_weight_map(
    site: SiteModel,
    weights: PlacementWeights,
) -> npt.NDArray[np.float64]:
    """Build a 2D weight array from the site's zone definitions.

    Each cell is assigned the weight corresponding to its highest-priority
    zone.  Zones are applied in ascending priority order so that
    ``critical_asset`` zones always override ``perimeter`` zones when they
    overlap.

    Cells not covered by any zone receive *weights.unzoned*.

    Args:
        site: Site terrain model (zones are read from ``site.zones``).
        weights: Zone-type weighting factors.

    Returns:
        Float64 2D array of shape ``(site.rows, site.cols)``.
    """
    from salus.engine.coverage import boundary_mask

    weight_map = np.full((site.rows, site.cols), weights.unzoned, dtype=np.float64)

    # Apply zones in ascending priority order so higher-priority zones win.
    zone_priority: list[tuple[ZoneType, float]] = [
        (ZoneType.exclusion, weights.exclusion),
        (ZoneType.perimeter, weights.perimeter),
        (ZoneType.inner, weights.inner),
        (ZoneType.critical_asset, weights.critical_asset),
    ]

    for zone_type, w in zone_priority:
        for zone in site.zones:
            if zone.zone_type == zone_type:
                # D-181: wrap per-zone rasterisation to include zone name in any failure.
                try:
                    mask = boundary_mask(site, zone.geometry)
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"Failed to rasterise zone '{zone.name}' ({zone.zone_type}): {exc}"
                    ) from exc
                weight_map[mask] = w

    return weight_map


def _precompute_bearing_grid(
    site: SiteModel,
    pos: Position,
) -> npt.NDArray[np.float64]:
    """Build compass-bearing-to-cell grid for *pos* (expensive; call once per candidate).

    Returns a 2D float64 array of shape ``(site.rows, site.cols)`` where each
    cell value is the compass bearing (degrees, [0, 360)) from *pos* to that
    cell.  Used by :func:`_build_arc_mask` to cheaply evaluate many boresight
    angles without recomputing the coordinate grids.
    """
    rows, cols = site.dem.shape
    col_coords = site.origin_x + np.arange(cols, dtype=np.float64) * site.resolution
    row_coords = site.origin_y - np.arange(rows, dtype=np.float64) * site.resolution
    cell_x, cell_y = np.meshgrid(col_coords, row_coords)
    dx: npt.NDArray[np.float64] = cell_x - pos.x
    dy: npt.NDArray[np.float64] = cell_y - pos.y
    return np.degrees(np.arctan2(dx, dy)) % _FULL_ARC_DEG


def _build_arc_mask(
    bearing_to_cell: npt.NDArray[np.float64],
    half_arc: float,
    bearing_deg: float,
) -> npt.NDArray[np.bool_]:
    """Apply an azimuth arc mask using a precomputed bearing grid.

    Args:
        bearing_to_cell: Per-cell compass bearing from the sensor position,
            as returned by :func:`_precompute_bearing_grid`.
        half_arc: Half-width of the sensor's azimuth arc in degrees
            (``azimuth_coverage_deg / 2``).
        bearing_deg: Boresight compass bearing for this candidate.

    Returns:
        Boolean array — True where the cell falls within the arc.
    """
    boresight = bearing_deg % _FULL_ARC_DEG
    diff: npt.NDArray[np.float64] = (bearing_to_cell - boresight + 180.0) % _FULL_ARC_DEG - 180.0
    return np.abs(diff) <= half_arc


def _compute_raw_coverage_no_arc(
    site: SiteModel,
    sensor: SensorDefinition,
    placement: SensorPlacement,
) -> npt.NDArray[np.bool_]:
    """Compute sensor coverage with range mask applied but no azimuth arc clipping.

    For Radar and EO_IR sensors: runs the viewshed (bearing-independent LOS)
    and applies range mask only.  The caller then sweeps arc masks for each
    bearing candidate.

    For all other sensor types (RF, Acoustic): delegates to the full
    :func:`~salus.engine.dispatcher.compute_sensor_coverage` which includes
    the arc mask.  This is correct because RF and Acoustic sensors in the
    current database are omnidirectional (``azimuth_coverage_deg == 360``),
    so the arc mask is a no-op.  Any future directional RF/Acoustic sensor
    would follow this slower-but-correct path automatically.

    Args:
        site: Site terrain model.
        sensor: Sensor capability definition.
        placement: Sensor position.  ``placement.bearing_deg`` is ignored for
            the arc-free path — the caller supplies bearings for the sweep.

    Returns:
        Boolean array of shape ``site.dem.shape``.

    Raises:
        ValueError: If the sensor height AGL is non-finite.
    """
    if sensor.type in (SensorType.Radar, SensorType.EO_IR):
        sensor_agl = (
            placement.height_override_m
            if placement.height_override_m is not None
            else sensor.mounting_height_m
        )
        # D-234: guard against mounting_height_m=None (not rejected by SensorDefinition
        # validator in all configurations) before math.isfinite which raises TypeError on None.
        if sensor_agl is None:
            raise ValueError(
                "sensor height AGL is None; set height_override_m on the placement or "
                "mounting_height_m on the sensor definition"
            )
        if not math.isfinite(sensor_agl):
            raise ValueError(
                f"sensor height AGL is non-finite ({sensor_agl}); "
                "check placement.height_override_m and sensor.mounting_height_m"
            )
        raw_vs = compute_viewshed(site, placement.position_x, placement.position_y, sensor_agl)
        # Range mask — no azimuth arc applied here.
        rows, cols = raw_vs.shape
        col_coords = site.origin_x + np.arange(cols, dtype=np.float64) * site.resolution
        row_coords = site.origin_y - np.arange(rows, dtype=np.float64) * site.resolution
        cell_x, cell_y = np.meshgrid(col_coords, row_coords)
        dx: npt.NDArray[np.float64] = cell_x - placement.position_x
        dy: npt.NDArray[np.float64] = cell_y - placement.position_y
        dist: npt.NDArray[np.float64] = np.sqrt(dx**2 + dy**2)
        range_mask: npt.NDArray[np.bool_] = (dist >= sensor.min_range_m) & (
            dist <= sensor.max_range_m
        )
        return raw_vs & range_mask
    # RF and Acoustic: fall back to full coverage (arc included).
    return compute_sensor_coverage(site, sensor, placement)


def greedy_place_sensors(
    site: SiteModel,
    sensors_to_place: list[SensorDefinition],
    candidates: list[Position],
    existing_coverage: npt.NDArray[np.bool_] | None = None,
    coverage_threshold_pct: float = 100.0,
    weights: PlacementWeights | None = None,
    bearing_step_deg: float = _BEARING_STEP_DEG_DEFAULT,
    objective: str = "maximise_coverage",
) -> list[SensorPlacement]:
    """Greedily select sensor placements that maximise zone-weighted coverage.

    For each sensor in *sensors_to_place*, evaluates every candidate position
    and selects the one that covers the most previously-uncovered area,
    weighted by zone type.  After placing each sensor the composite coverage
    is updated before scoring the next sensor.

    The loop stops early when the weighted coverage fraction reaches
    *coverage_threshold_pct* (computed as
    ``sum(weight_map[covered_cells]) / sum(weight_map) * 100``).

    **Bearing-aware placement (S11.5):** for directional sensors
    (``azimuth_coverage_deg < 360``), each candidate position is evaluated
    at ``ceil(360 / bearing_step_deg)`` boresight angles.  The viewshed is
    computed once per position; arc masks are applied cheaply per bearing.
    The (position, bearing) pair with the highest weighted score is selected.
    Omnidirectional sensors (``azimuth_coverage_deg >= 360``) skip the bearing
    sweep and are placed with bearing :data:`_DEFAULT_BEARING_DEG` (0°/north).

    Args:
        site: Site terrain model.
        sensors_to_place: Ordered list of sensor definitions to place.
            Each entry results in at most one :class:`~salus.models.scenario.SensorPlacement`
            in the output.
        candidates: Grid of candidate deployment positions (from
            :func:`generate_candidate_positions`).  An empty list produces
            an empty output with a warning.
        existing_coverage: Optional boolean array of shape
            ``(site.rows, site.cols)`` representing coverage that is
            already present before any new sensors are placed.  When
            ``None``, all cells are treated as uncovered.
        coverage_threshold_pct: Weighted coverage percentage [0.0, 100.0]
            at which the loop exits early.  Default 100.0 (never exit early).
        weights: Zone-type weighting factors.  ``None`` uses
            :class:`PlacementWeights` defaults (critical_asset=3×, inner=2×,
            perimeter=1×).
        bearing_step_deg: Angular step between boresight candidates for
            directional sensors (degrees, must be in (0, 360]).  Smaller
            values give finer bearing resolution at higher compute cost.
            Default :data:`_BEARING_STEP_DEG_DEFAULT` (10°, 36 candidates).

    Returns:
        List of :class:`~salus.models.scenario.SensorPlacement` objects in
        placement order.  May be shorter than *sensors_to_place* if the
        coverage threshold is reached before all sensors are placed, or if no
        valid position exists for a sensor.

    Raises:
        ValueError: If *coverage_threshold_pct* is outside [0.0, 100.0].
        ValueError: If *existing_coverage* shape does not match
            ``(site.rows, site.cols)``.
        ValueError: If *bearing_step_deg* is not a finite value in (0, 360].
    """
    if not (0.0 <= coverage_threshold_pct <= 100.0):
        raise ValueError(
            f"coverage_threshold_pct must be in [0.0, 100.0], got {coverage_threshold_pct}"
        )
    if not math.isfinite(bearing_step_deg) or bearing_step_deg <= 0.0 or bearing_step_deg > 360.0:
        raise ValueError(
            f"bearing_step_deg must be a finite value in (0, 360], got {bearing_step_deg}"
        )

    expected_shape = (site.rows, site.cols)

    if existing_coverage is not None and existing_coverage.shape != expected_shape:
        raise ValueError(
            f"existing_coverage shape {existing_coverage.shape} does not match "
            f"site shape {expected_shape}"
        )

    if not sensors_to_place:
        return []

    if not candidates:
        _log.warning(
            "greedy_place_sensors: no candidate positions supplied; returning empty placement list."
        )
        return []

    if weights is None:
        weights = PlacementWeights()

    weight_map = _build_weight_map(site, weights)
    total_weight = float(weight_map.sum())

    # D-179: warn when all weights are zero — scoring is degenerate.
    if total_weight == 0.0:
        _log.warning(
            "greedy_place_sensors: all placement weights are zero; "
            "coverage scoring is degenerate. All sensors will be placed at "
            "the first candidate that produces any coverage. "
            "Set at least one non-zero weight in PlacementWeights."
        )

    composite: npt.NDArray[np.bool_] = (
        existing_coverage.astype(bool).copy()
        if existing_coverage is not None
        else np.zeros(expected_shape, dtype=bool)
    )

    placements: list[SensorPlacement] = []

    for sensor in sensors_to_place:
        # Check coverage threshold before attempting to place next sensor.
        if total_weight > 0.0:
            current_weighted_pct = float(np.sum(weight_map[composite])) / total_weight * 100.0
            if current_weighted_pct >= coverage_threshold_pct:
                _log.info(
                    "Weighted coverage threshold %.1f%% reached after %d placement(s); "
                    "stopping early.",
                    coverage_threshold_pct,
                    len(placements),
                )
                break

        best_score: float = -1.0
        best_position: Position | None = None
        best_bearing: float = _DEFAULT_BEARING_DEG
        best_coverage: npt.NDArray[np.bool_] | None = None

        # Bearing sweep: directional sensors evaluate multiple boresight angles;
        # omnidirectional sensors skip the sweep (single no-op bearing pass).
        needs_sweep: bool = sensor.azimuth_coverage_deg < _FULL_ARC_DEG
        # D-231/D-236: initialise unconditionally so mypy and future refactors
        # cannot produce an unbound reference if the two guard sites diverge.
        half_arc: float = sensor.azimuth_coverage_deg / 2.0
        bearing_grid: npt.NDArray[np.float64] | None = None
        if needs_sweep:
            # D-232: use ceil so the full 360° arc is always covered even when
            # bearing_step_deg does not divide 360 exactly.
            n_steps = max(1, math.ceil(_FULL_ARC_DEG / bearing_step_deg))
            bearing_candidates: list[float] = [i * bearing_step_deg for i in range(n_steps)]
        else:
            bearing_candidates = [_DEFAULT_BEARING_DEG]

        failed_candidates = 0
        for pos in candidates:
            base_placement = SensorPlacement(
                sensor_name=sensor.name,
                position_x=pos.x,
                position_y=pos.y,
                bearing_deg=_DEFAULT_BEARING_DEG,
                height_override_m=None,
            )
            # Phase 1 — compute base coverage (viewshed + range, no arc).
            # For omnidirectional sensors this IS the final coverage.
            try:
                if needs_sweep:
                    base_cov: npt.NDArray[np.bool_] = _compute_raw_coverage_no_arc(
                        site, sensor, base_placement
                    )
                    bearing_grid = _precompute_bearing_grid(site, pos)
                else:
                    base_cov = compute_sensor_coverage(site, sensor, base_placement)
            except Exception as exc:  # noqa: BLE001
                failed_candidates += 1
                _log.debug(
                    "Coverage computation failed for '%s' at (%.1f, %.1f): %s",
                    sensor.name,
                    pos.x,
                    pos.y,
                    exc,
                )
                continue

            # Phase 2 — score over bearing candidates (cheap arc masks).
            for b_deg in bearing_candidates:
                if needs_sweep:
                    assert bearing_grid is not None  # guaranteed by Phase 1 above
                    arc: npt.NDArray[np.bool_] = _build_arc_mask(bearing_grid, half_arc, b_deg)
                    cov: npt.NDArray[np.bool_] = base_cov & arc
                else:
                    cov = base_cov

                newly_covered: npt.NDArray[np.bool_] = cov & ~composite
                score = float(np.sum(weight_map[newly_covered]))

                if score > best_score:
                    best_score = score
                    best_position = pos
                    best_bearing = b_deg
                    best_coverage = cov.astype(bool)

        # D-230: warn when some (but not all) candidates failed so the caller
        # can distinguish a systematic error from rare positional failures.
        if 0 < failed_candidates < len(candidates):
            _log.warning(
                "Coverage computation failed for %d of %d candidate(s) for sensor '%s'; "
                "placement may be suboptimal.",
                failed_candidates,
                len(candidates),
                sensor.name,
            )

        if best_position is None or best_coverage is None:
            # D-178: emit at WARNING so production logs surface the failure.
            if failed_candidates == len(candidates):
                _log.warning(
                    "No valid placement found for sensor '%s': all %d candidate(s) "
                    "raised an exception during coverage computation; skipping.",
                    sensor.name,
                    failed_candidates,
                )
            else:
                _log.warning(
                    "No valid placement found for sensor '%s'; skipping.",
                    sensor.name,
                )
            continue

        # D-180/D-233: warn and skip composite update when best_score is zero.
        # Updating composite with a no-op coverage array would prevent later
        # sensors from detecting those cells as uncovered.
        if best_score <= 0.0:
            _log.warning(
                "Sensor '%s' placed at (%.1f, %.1f) adds zero weighted coverage "
                "(every cell it covers may be in an exclusion zone). "
                "Review zone weights or candidate positions.",
                sensor.name,
                best_position.x,
                best_position.y,
            )

        placed = SensorPlacement(
            sensor_name=sensor.name,
            position_x=best_position.x,
            position_y=best_position.y,
            bearing_deg=best_bearing,
            height_override_m=None,
        )
        placements.append(placed)
        composite |= best_coverage

        if total_weight > 0.0:
            weighted_pct = float(np.sum(weight_map[composite])) / total_weight * 100.0
        else:
            weighted_pct = 0.0
        _log.info(
            "Placed '%s' at (%.1f, %.1f) bearing=%.1f° — weighted score %.0f, "
            "weighted coverage %.1f%%",
            sensor.name,
            best_position.x,
            best_position.y,
            best_bearing,
            best_score,
            weighted_pct,
        )

    return placements
