"""Configuration comparison engine (S10).

Compares two cUAS sensor configuration results to identify coverage gains,
losses, and operational differences.  Intended for procurement "what-if"
analysis: "Config B costs $200K more but closes the NE gap and raises
saturation threshold from 5 to 9."

Workflow:
    1. Run the coverage pipeline for configuration A and B separately.
    2. Wrap each result in a :class:`ConfigurationResult`.
    3. Call :func:`compare_configs` to compute the :class:`ComparisonResult`.
    4. Pass the result to the rendering functions in ``report.maps`` and
       ``report.charts`` to produce the delta map and comparison bar chart.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from salus.engine.coverage import CoverageStats
from salus.models.sensor import SensorType

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Delta grid encoding — values stored in ComparisonResult.delta_grid
# ---------------------------------------------------------------------------

#: Neither configuration covers this cell.
DELTA_NEITHER: int = 0

#: Both configuration A and B cover this cell.
DELTA_BOTH: int = 1

#: Only configuration A covers this cell (A-only gap in B).
DELTA_A_ONLY: int = 2

#: Only configuration B covers this cell (B-only gain over A).
DELTA_B_ONLY: int = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurationResult:
    """Everything known about one sensor configuration's coverage simulation.

    Pass one of these for each configuration to :func:`compare_configs`.

    Attributes:
        label: Human-readable name for this configuration (e.g. "Config A").
        composite: Boolean grid ``(rows, cols)`` — True where at least one
            sensor covers the cell.
        layer_coverages: Per-sensor-type boolean coverage arrays (output of
            :func:`~salus.engine.coverage.compute_layer_coverage`).
        stats: Aggregate coverage statistics (output of
            :func:`~salus.engine.coverage.compute_coverage_stats`).
        saturation_threshold_n: Simultaneous-target saturation threshold from
            S8 analysis.  ``None`` if saturation analysis was not performed.
        engagement_capacity: Total simultaneous engagement capacity from
            S8 analysis.  ``None`` if saturation analysis was not performed.
        cost_estimate: Total configuration cost in currency units (e.g. USD).
            ``None`` if not supplied by the caller.
    """

    label: str
    composite: npt.NDArray[np.bool_]
    layer_coverages: dict[SensorType, npt.NDArray[np.bool_]] = field(default_factory=dict)
    stats: CoverageStats = field(
        default_factory=lambda: CoverageStats(
            total_coverage_pct=0.0,
            per_layer_coverage_pct={},
            per_zone_coverage_pct={},
            gap_area_m2=0.0,
            redundancy_map=np.zeros((0, 0), dtype=np.intp),
            largest_contiguous_gap_m2=0.0,
        )
    )
    saturation_threshold_n: int | None = None
    engagement_capacity: int | None = None
    cost_estimate: float | None = None


@dataclass(frozen=True)
class ComparisonResult:
    """Output of :func:`compare_configs`.

    Attributes:
        label_a: Label of configuration A.
        label_b: Label of configuration B.
        delta_grid: Integer array ``(rows, cols)`` encoded with :data:`DELTA_*`
            constants: 0=neither, 1=both, 2=A-only, 3=B-only.
        coverage_pct_a: Total coverage percentage for configuration A.
        coverage_pct_b: Total coverage percentage for configuration B.
        coverage_delta_pct: ``coverage_pct_b − coverage_pct_a``.  Positive
            means B covers more than A.
        per_zone_coverage_pct_a: Per-zone coverage percentages for A.
        per_zone_coverage_pct_b: Per-zone coverage percentages for B.
        per_zone_delta_pct: ``B − A`` per zone (zones present in both).
        cost_delta: ``cost_b − cost_a``.  ``None`` if either cost is absent.
        engagement_capacity_delta: ``capacity_b − capacity_a``.  ``None`` if
            either value is absent.
        saturation_threshold_delta: ``threshold_b − threshold_a``.  Positive
            means B saturates later (better).  ``None`` if either value is absent.
    """

    label_a: str
    label_b: str
    delta_grid: npt.NDArray[np.int8]
    coverage_pct_a: float
    coverage_pct_b: float
    coverage_delta_pct: float
    per_zone_coverage_pct_a: dict[str, float]
    per_zone_coverage_pct_b: dict[str, float]
    per_zone_delta_pct: dict[str, float]
    cost_delta: float | None
    engagement_capacity_delta: int | None
    saturation_threshold_delta: int | None


# ---------------------------------------------------------------------------
# Core comparison function
# ---------------------------------------------------------------------------


def compare_configs(
    a: ConfigurationResult,
    b: ConfigurationResult,
) -> ComparisonResult:
    """Compare two configuration results and compute coverage delta metrics.

    Both configurations must share the same site grid shape.  The per-zone
    delta is computed only for zone names that appear in both A and B
    ``stats.per_zone_coverage_pct`` dictionaries.

    Args:
        a: Coverage results for configuration A.
        b: Coverage results for configuration B.

    Returns:
        :class:`ComparisonResult` with cell-level delta grid, percentage
        deltas, and optional cost / saturation deltas.

    Raises:
        ValueError: If ``a.composite`` and ``b.composite`` have different shapes.
        ValueError: If either composite has zero cells.
        ValueError: If ``a.label`` or ``b.label`` is empty or whitespace.
    """
    if not a.label.strip():
        raise ValueError("ConfigurationResult label_a must not be empty or whitespace")
    if not b.label.strip():
        raise ValueError("ConfigurationResult label_b must not be empty or whitespace")

    # D-198/D-200: require 2-D composites.
    if a.composite.ndim != 2:
        raise ValueError(
            f"ConfigurationResult '{a.label}' composite must be 2-D; got ndim={a.composite.ndim}"
        )
    if b.composite.ndim != 2:
        raise ValueError(
            f"ConfigurationResult '{b.label}' composite must be 2-D; got ndim={b.composite.ndim}"
        )

    shape_a = a.composite.shape
    shape_b = b.composite.shape
    if shape_a != shape_b:
        raise ValueError(
            f"Configuration composites must have the same shape; "
            f"got {shape_a} for '{a.label}' and {shape_b} for '{b.label}'"
        )
    if a.composite.size == 0:
        raise ValueError(
            f"Configuration composites must be non-empty; got shape {shape_a} (zero cells)"
        )

    # D-196/D-215: guard against NaN cells before bool cast — dtype-agnostic.
    # Integer dtypes cannot contain NaN; object/non-numeric dtypes are rejected explicitly.
    for cfg_label, comp_arr in ((a.label, a.composite), (b.label, b.composite)):
        if not (np.issubdtype(comp_arr.dtype, np.number) or comp_arr.dtype == np.bool_):
            raise TypeError(
                f"ConfigurationResult '{cfg_label}' composite must have a numeric dtype; "
                f"got {comp_arr.dtype}"
            )
        if np.issubdtype(comp_arr.dtype, np.floating) and np.isnan(comp_arr).any():
            nan_count = int(np.isnan(comp_arr).sum())
            _log.warning(
                "compare_configs: composite for '%s' contains %d NaN cell(s) — "
                "they will be treated as uncovered.",
                cfg_label,
                nan_count,
            )

    comp_a = np.nan_to_num(a.composite, nan=0.0).astype(bool)
    comp_b = np.nan_to_num(b.composite, nan=0.0).astype(bool)

    # Build cell-level delta grid.
    delta_grid = np.full(shape_a, DELTA_NEITHER, dtype=np.int8)
    delta_grid[comp_a & comp_b] = DELTA_BOTH
    delta_grid[comp_a & ~comp_b] = DELTA_A_ONLY
    delta_grid[~comp_a & comp_b] = DELTA_B_ONLY

    # D-195: validate coverage percentages before arithmetic.
    cov_a = a.stats.total_coverage_pct
    cov_b = b.stats.total_coverage_pct
    for label, cov in ((a.label, cov_a), (b.label, cov_b)):
        if not np.isfinite(cov):
            raise ValueError(
                f"ConfigurationResult '{label}' total_coverage_pct is not finite: {cov}"
            )
    coverage_delta_pct = cov_b - cov_a

    # Per-zone delta — only zones common to both configurations.
    zone_names_a = set(a.stats.per_zone_coverage_pct)
    zone_names_b = set(b.stats.per_zone_coverage_pct)
    common_zones = zone_names_a & zone_names_b
    skipped_zones = (zone_names_a | zone_names_b) - common_zones
    if skipped_zones:
        _log.warning(
            "compare_configs: zones %s not present in both configurations — excluded from delta.",
            sorted(skipped_zones),
        )

    per_zone_delta_pct: dict[str, float] = {
        zone: b.stats.per_zone_coverage_pct[zone] - a.stats.per_zone_coverage_pct[zone]
        for zone in sorted(common_zones)
    }

    # Optional metric deltas.
    # D-214: guard against inf/nan cost values — pass the 'is not None' check
    # but would produce nonsense procurement figures if used in arithmetic.
    cost_delta: float | None = None
    if a.cost_estimate is not None and b.cost_estimate is not None:
        if not (math.isfinite(a.cost_estimate) and math.isfinite(b.cost_estimate)):
            _log.warning(
                "compare_configs: non-finite cost_estimate for '%s' or '%s' — "
                "cost_delta will not be computed.",
                a.label,
                b.label,
            )
        else:
            cost_delta = b.cost_estimate - a.cost_estimate

    engagement_capacity_delta: int | None = None
    if a.engagement_capacity is not None and b.engagement_capacity is not None:
        engagement_capacity_delta = b.engagement_capacity - a.engagement_capacity

    saturation_threshold_delta: int | None = None
    if a.saturation_threshold_n is not None and b.saturation_threshold_n is not None:
        saturation_threshold_delta = b.saturation_threshold_n - a.saturation_threshold_n

    _log.info(
        "compare_configs: '%s' vs '%s' — coverage delta %.1f%% (%d zones compared)",
        a.label,
        b.label,
        coverage_delta_pct,
        len(common_zones),
    )

    return ComparisonResult(
        label_a=a.label,
        label_b=b.label,
        delta_grid=delta_grid,
        coverage_pct_a=cov_a,
        coverage_pct_b=cov_b,
        coverage_delta_pct=coverage_delta_pct,
        per_zone_coverage_pct_a=dict(a.stats.per_zone_coverage_pct),
        per_zone_coverage_pct_b=dict(b.stats.per_zone_coverage_pct),
        per_zone_delta_pct=per_zone_delta_pct,
        cost_delta=cost_delta,
        engagement_capacity_delta=engagement_capacity_delta,
        saturation_threshold_delta=saturation_threshold_delta,
    )
