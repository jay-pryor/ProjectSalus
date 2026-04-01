"""Threat corridor coverage analysis.

Samples the composite coverage map along a straight-line drone approach
corridor and computes detection metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from salus.models.site import SiteModel
from salus.models.threat import ThreatCorridor, ThreatProfile

# Minimum number of samples along a corridor (includes the protected point itself).
_MIN_SAMPLES: int = 1


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

    # World coordinates for each sample along the corridor.
    # As distance d increases from 0, the position moves away from the asset
    # in the direction OPPOSITE to the approach bearing.
    sample_xs = px - distances * sin_b
    sample_ys = py - distances * cos_b

    # Convert world coordinates to grid cell indices.
    # origin_x/y is the top-left corner; row increases downward.
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
