"""Greedy sensor placement optimisation engine (S9).

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
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel
from salus.models.zone import Zone, ZoneType

_log = logging.getLogger(__name__)

# Steep-slope gradient threshold (m/m). Candidate positions where the DEM
# gradient magnitude exceeds this value are excluded as impractical deployment
# sites.  tan(45°) = 1.0 — slopes steeper than 45° are filtered out.
_STEEP_SLOPE_THRESHOLD: float = 1.0

# Default bearing (degrees, compass) assigned to all placed sensors.
# Omnidirectional sensors (azimuth_coverage_deg == 360) are unaffected.
# For directional sensors the user should adjust bearing after optimisation.
_DEFAULT_BEARING_DEG: float = 0.0


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


def greedy_place_sensors(
    site: SiteModel,
    sensors_to_place: list[SensorDefinition],
    candidates: list[Position],
    existing_coverage: npt.NDArray[np.bool_] | None = None,
    coverage_threshold_pct: float = 100.0,
    weights: PlacementWeights | None = None,
) -> list[SensorPlacement]:
    """Greedily select sensor placements that maximise zone-weighted coverage.

    For each sensor in *sensors_to_place*, evaluates every candidate position
    and selects the one that covers the most previously-uncovered area,
    weighted by zone type.  After placing each sensor the composite coverage
    is updated before scoring the next sensor.

    The loop stops early when the weighted coverage fraction reaches
    *coverage_threshold_pct* (computed as
    ``sum(weight_map[covered_cells]) / sum(weight_map) * 100``).

    All placed sensors are assigned a bearing of :data:`_DEFAULT_BEARING_DEG`
    (0° / north).  For sensors with ``azimuth_coverage_deg < 360`` the user
    should manually adjust the bearing in the output scenario.

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

    Returns:
        List of :class:`~salus.models.scenario.SensorPlacement` objects in
        placement order.  May be shorter than *sensors_to_place* if the
        coverage threshold is reached before all sensors are placed, or if no
        valid position exists for a sensor.

    Raises:
        ValueError: If *coverage_threshold_pct* is outside [0.0, 100.0].
        ValueError: If *existing_coverage* shape does not match
            ``(site.rows, site.cols)``.
    """
    if not (0.0 <= coverage_threshold_pct <= 100.0):
        raise ValueError(
            f"coverage_threshold_pct must be in [0.0, 100.0], got {coverage_threshold_pct}"
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
        best_coverage: npt.NDArray[np.bool_] | None = None

        failed_candidates = 0
        for pos in candidates:
            candidate_placement = SensorPlacement(
                sensor_name=sensor.name,
                position_x=pos.x,
                position_y=pos.y,
                bearing_deg=_DEFAULT_BEARING_DEG,
                height_override_m=None,
            )
            try:
                cov = compute_sensor_coverage(site, sensor, candidate_placement)
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

            newly_covered: npt.NDArray[np.bool_] = cov.astype(bool) & ~composite
            score = float(np.sum(weight_map[newly_covered]))

            if score > best_score:
                best_score = score
                best_position = pos
                best_coverage = cov.astype(bool)

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

        # D-180: warn when best_score is zero — the sensor adds no weighted coverage.
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
            bearing_deg=_DEFAULT_BEARING_DEG,
            height_override_m=None,
        )
        placements.append(placed)
        composite |= best_coverage

        composite_pct = float(composite.sum()) / float(composite.size) * 100.0
        _log.info(
            "Placed '%s' at (%.1f, %.1f) — weighted score %.0f, composite coverage %.1f%%",
            sensor.name,
            best_position.x,
            best_position.y,
            best_score,
            composite_pct,
        )

    return placements
