"""Threat corridor coverage analysis.

Provides both 2D composite-based corridor analysis (analyse_corridor) and
the 3D sensor-based worst-corridor sweep (find_worst_corridors).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from salus.engine.trajectory import analyse_trajectory
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition
from salus.models.site import SiteModel
from salus.models.threat import DroneTrajectory, ThreatCorridor, ThreatProfile, TrajectoryWaypoint

# Minimum number of samples along a corridor (includes the protected point itself).
_MIN_SAMPLES: int = 1

# Default number of compass bearings to sweep in find_worst_corridors.
_DEFAULT_NUM_BEARINGS: int = 36  # every 10 degrees

# Default segment length for the 3D corridor sweep (planning fidelity).
_DEFAULT_SEGMENT_LENGTH_M: float = 5.0


@dataclass(frozen=True)
class CorridorResult:
    """Result of a single corridor coverage analysis.

    Attributes:
        corridor: The ThreatCorridor that was analysed.
        threat_name: Name of the threat profile used.
        coverage_pct: Percentage of in-bounds corridor cells covered by at
            least one sensor (0–100). 0.0 if no in-bounds cells were sampled.
        first_detection_distance_m: Distance from the protected point (m) at
            which the drone first enters coverage, walking from the far end
            towards the asset.  None if no covered cell was found.
        last_gap_before_target_m: Length of the last contiguous uncovered
            segment immediately before the protected point in metres.
            0.0 if the protected point itself (and the cells around it) are
            covered, or if the corridor has no in-bounds cells.
        time_in_coverage_s: Total time the drone spends inside covered cells,
            calculated as ``covered_distance_m / threat.max_speed_ms``.
        covered_cells: Number of in-bounds corridor cells with coverage.
        total_cells: Total number of in-bounds corridor cells sampled.
    """

    corridor: ThreatCorridor
    threat_name: str
    coverage_pct: float
    first_detection_distance_m: float | None
    last_gap_before_target_m: float
    time_in_coverage_s: float
    covered_cells: int
    total_cells: int


def analyse_corridor(
    site: SiteModel,
    composite_coverage: npt.NDArray[np.bool_],
    corridor: ThreatCorridor,
    threat: ThreatProfile,
    protected_point: tuple[float, float],
) -> CorridorResult:
    """Analyse the composite coverage along a single drone approach corridor.

    Samples the coverage grid at ``site.resolution``-metre intervals along the
    corridor centreline from ``corridor.start_distance_m`` down to zero
    (the protected point).  All metrics are derived from in-bounds cells only;
    out-of-bounds portions of the corridor are silently excluded.

    Args:
        site: Site model providing the grid geometry and resolution.
        composite_coverage: Boolean 2D array (True = covered) with the same
            shape as ``site.dem``.
        corridor: Corridor definition — bearing, altitude, width and start
            distance.  Bearing is the direction of drone travel (towards asset).
        threat: Threat profile — used only for ``max_speed_ms`` to compute
            ``time_in_coverage_s``.
        protected_point: (x, y) CRS coordinates of the asset being protected;
            this is the near end (distance = 0) of the corridor.

    Returns:
        CorridorResult with coverage statistics for the corridor.

    Raises:
        ValueError: If ``composite_coverage`` is not a 2D non-empty array
            whose shape matches ``site.dem``, or if ``protected_point``
            contains non-finite coordinates.
    """
    if composite_coverage.ndim != 2:
        raise ValueError(f"composite_coverage must be 2D, got {composite_coverage.ndim}D")
    if composite_coverage.size == 0:
        raise ValueError("composite_coverage must not be empty")
    if composite_coverage.shape != site.dem.shape:
        raise ValueError(
            f"composite_coverage shape {composite_coverage.shape} does not match "
            f"site.dem shape {site.dem.shape}"
        )

    px, py = protected_point
    if not (math.isfinite(px) and math.isfinite(py)):
        raise ValueError(f"protected_point coordinates must be finite, got ({px}, {py})")
    bearing_rad = math.radians(corridor.bearing_deg)
    sin_b = math.sin(bearing_rad)
    cos_b = math.cos(bearing_rad)

    # Generate sample distances: d=0 is at protected_point; d=start_distance_m
    # is at the far end of the corridor.
    num_samples = max(_MIN_SAMPLES, int(corridor.start_distance_m / site.resolution) + 1)
    distances = np.linspace(0.0, corridor.start_distance_m, num_samples)

    # World coordinates: d=0 is at protected_point; d increases away from asset
    sample_xs = px - distances * sin_b
    sample_ys = py - distances * cos_b

    # Convert world coordinates to grid cell indices.
    # origin_y is top-left (max northing); row increases downward.
    cols = ((sample_xs - site.origin_x) / site.resolution).astype(int)
    rows = ((site.origin_y - sample_ys) / site.resolution).astype(int)

    # Boolean mask for samples that fall within the grid bounds.
    in_bounds: npt.NDArray[np.bool_] = (
        (rows >= 0) & (rows < site.rows) & (cols >= 0) & (cols < site.cols)
    )

    # Look up coverage for in-bounds samples.
    covered_along_path = np.zeros(num_samples, dtype=bool)
    if in_bounds.any():
        covered_along_path[in_bounds] = composite_coverage[rows[in_bounds], cols[in_bounds]]

    # --- Aggregate statistics (in-bounds cells only) ---

    total_cells = int(in_bounds.sum())
    covered_cells = int(covered_along_path[in_bounds].sum()) if total_cells > 0 else 0
    coverage_pct = (covered_cells / total_cells * 100.0) if total_cells > 0 else 0.0

    # First detection distance: highest d where coverage is True (drone first
    # enters coverage when approaching from the far end).
    first_detection_distance_m: float | None = None
    for i in range(num_samples - 1, -1, -1):
        if in_bounds[i] and covered_along_path[i]:
            first_detection_distance_m = float(distances[i])
            break

    # Last gap before target: contiguous uncovered cells from d=0 (index 0)
    # outward.  Stops at the first covered cell or the first out-of-bounds cell.
    gap_cells = 0
    for i in range(num_samples):
        if not in_bounds[i]:
            break
        if not covered_along_path[i]:
            gap_cells += 1
        else:
            break
    last_gap_before_target_m = gap_cells * site.resolution

    # Time in coverage = (covered distance) / (threat max speed).
    covered_distance_m = covered_cells * site.resolution
    time_in_coverage_s = covered_distance_m / threat.max_speed_ms

    return CorridorResult(
        corridor=corridor,
        threat_name=threat.name,
        coverage_pct=coverage_pct,
        first_detection_distance_m=first_detection_distance_m,
        last_gap_before_target_m=last_gap_before_target_m,
        time_in_coverage_s=time_in_coverage_s,
        covered_cells=covered_cells,
        total_cells=total_cells,
    )


def find_worst_corridors(
    site: SiteModel,
    sensor_placements: list[tuple[SensorDefinition, SensorPlacement]],
    threat: ThreatProfile,
    protected_point: tuple[float, float],
    num_bearings: int = _DEFAULT_NUM_BEARINGS,
    segment_length_m: float = _DEFAULT_SEGMENT_LENGTH_M,
) -> list[CorridorResult]:
    """Test all approach bearings and return corridors ranked worst-to-best.

    Constructs a two-waypoint ``DroneTrajectory`` for each bearing and
    delegates to ``analyse_trajectory`` for 3D sensor-based detection.
    Results are sorted by ``coverage_pct`` ascending (lowest coverage first,
    i.e. worst-case approach first).

    The corridor for each bearing runs from a start point at
    ``start_distance_m`` in the reverse-bearing direction, to the asset at
    ``threat.typical_altitude_m`` AGL.  Start distance defaults to half the
    site's shorter axis, clamped to a minimum of one grid cell.

    Args:
        site: Site model providing grid geometry and resolution.
        sensor_placements: All active sensors as ``(SensorDefinition,
            SensorPlacement)`` pairs.
        threat: Threat profile — provides altitude and speed.
        protected_point: (x, y) CRS coordinates of the asset being protected.
        num_bearings: Number of evenly-spaced bearings to test (default 36 =
            every 10 degrees).  Must be >= 1.
        segment_length_m: Sampling interval passed to ``analyse_trajectory``
            (metres, default 5.0 for planning fidelity).

    Returns:
        List of ``CorridorResult`` sorted by ``coverage_pct`` ascending.
        The first element is the worst-case approach corridor.  The list has
        exactly ``num_bearings`` entries.

    Raises:
        ValueError: If ``num_bearings`` < 1, or if ``protected_point``
            contains non-finite coordinates.
    """
    if num_bearings < 1:
        raise ValueError(f"num_bearings must be >= 1, got {num_bearings}")

    px, py = protected_point
    if not (math.isfinite(px) and math.isfinite(py)):
        raise ValueError(f"protected_point coordinates must be finite, got ({px}, {py})")

    # Default start distance: half the site's shorter axis, minimum 1 cell.
    min_axis_m = min(site.rows, site.cols) * site.resolution
    start_distance_m = max(site.resolution, min_axis_m / 2.0)

    step_deg = 360.0 / num_bearings
    results: list[CorridorResult] = []
    speed = threat.max_speed_ms
    altitude = threat.typical_altitude_m

    for i in range(num_bearings):
        bearing = (i * step_deg) % 360.0
        bearing_rad = math.radians(bearing)
        sin_b = math.sin(bearing_rad)
        cos_b = math.cos(bearing_rad)

        # Start point: distance from asset in the reverse-bearing direction.
        start_x = px - sin_b * start_distance_m
        start_y = py - cos_b * start_distance_m

        traj = DroneTrajectory(
            waypoints=[
                TrajectoryWaypoint(x=start_x, y=start_y, z_agl=altitude),
                TrajectoryWaypoint(x=px, y=py, z_agl=altitude),
            ],
            speed_ms=speed,
        )
        tr = analyse_trajectory(site, sensor_placements, traj, segment_length_m)

        # Map TrajectoryResult → CorridorResult for backward compatibility.
        corridor = ThreatCorridor(
            bearing_deg=bearing,
            altitude_m=altitude,
            start_distance_m=start_distance_m,
        )
        coverage_pct = (
            (tr.time_in_detection_s / tr.time_to_asset_s * 100.0)
            if tr.time_to_asset_s > 0.0
            else 0.0
        )
        first_detection_m: float | None = (
            tr.first_detection.distance_to_asset_m if tr.first_detection else None
        )
        # Approximate cell counts from timing and resolution (clamped non-negative).
        covered_cells: int = max(0, round(tr.time_in_detection_s * speed / site.resolution))
        total_cells: int = max(0, round(tr.time_to_asset_s * speed / site.resolution))

        results.append(
            CorridorResult(
                corridor=corridor,
                threat_name=threat.name,
                coverage_pct=coverage_pct,
                first_detection_distance_m=first_detection_m,
                last_gap_before_target_m=tr.last_gap_before_asset_m,
                time_in_coverage_s=tr.time_in_detection_s,
                covered_cells=covered_cells,
                total_cells=total_cells,
            )
        )

    # Sort ascending by coverage_pct — worst (least covered) first.
    results.sort(key=lambda r: r.coverage_pct)
    return results
