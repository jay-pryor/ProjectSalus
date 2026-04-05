"""Tests for the configuration comparison engine (S10)."""

from __future__ import annotations

import numpy as np
import pytest

from salus.engine.comparison import (
    DELTA_A_ONLY,
    DELTA_B_ONLY,
    DELTA_BOTH,
    DELTA_NEITHER,
    ConfigurationResult,
    compare_configs,
)
from salus.engine.coverage import CoverageStats

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stats(
    total: float = 50.0,
    zones: dict[str, float] | None = None,
) -> CoverageStats:
    shape = (4, 4)
    return CoverageStats(
        total_coverage_pct=total,
        per_layer_coverage_pct={},
        per_zone_coverage_pct=zones or {},
        gap_area_m2=0.0,
        redundancy_map=np.zeros(shape, dtype=np.intp),
        largest_contiguous_gap_m2=0.0,
    )


def _make_config(
    label: str,
    composite: np.ndarray,
    total_pct: float = 50.0,
    zones: dict[str, float] | None = None,
    cost: float | None = None,
    sat_n: int | None = None,
    capacity: int | None = None,
) -> ConfigurationResult:
    return ConfigurationResult(
        label=label,
        composite=composite,
        stats=_make_stats(total=total_pct, zones=zones),
        cost_estimate=cost,
        saturation_threshold_n=sat_n,
        engagement_capacity=capacity,
    )


# ---------------------------------------------------------------------------
# ConfigurationResult defaults
# ---------------------------------------------------------------------------


class TestConfigurationResult:
    def test_default_stats_zero(self):
        comp = np.zeros((3, 3), dtype=bool)
        cfg = ConfigurationResult(label="X", composite=comp)
        assert cfg.stats.total_coverage_pct == 0.0

    def test_optional_fields_none_by_default(self):
        comp = np.zeros((3, 3), dtype=bool)
        cfg = ConfigurationResult(label="X", composite=comp)
        assert cfg.saturation_threshold_n is None
        assert cfg.engagement_capacity is None
        assert cfg.cost_estimate is None

    def test_frozen(self):
        comp = np.zeros((3, 3), dtype=bool)
        cfg = ConfigurationResult(label="X", composite=comp)
        with pytest.raises((AttributeError, TypeError)):
            cfg.label = "Y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestCompareConfigsValidation:
    def test_empty_label_a_raises(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("   ", comp)
        b = _make_config("B", comp)
        with pytest.raises(ValueError, match="label_a"):
            compare_configs(a, b)

    def test_empty_label_b_raises(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp)
        b = _make_config("", comp)
        with pytest.raises(ValueError, match="label_b"):
            compare_configs(a, b)

    def test_shape_mismatch_raises(self):
        a = _make_config("A", np.ones((4, 4), dtype=bool))
        b = _make_config("B", np.ones((4, 5), dtype=bool))
        with pytest.raises(ValueError, match="shape"):
            compare_configs(a, b)

    def test_zero_cells_raises(self):
        comp = np.zeros((0, 0), dtype=bool)
        a = _make_config("A", comp)
        b = _make_config("B", comp)
        with pytest.raises(ValueError, match="zero cells"):
            compare_configs(a, b)

    def test_1d_composite_raises(self):
        a = _make_config("A", np.ones(16, dtype=bool))
        b = _make_config("B", np.ones((4, 4), dtype=bool))
        with pytest.raises(ValueError, match="2-D"):
            compare_configs(a, b)

    def test_nan_coverage_pct_raises(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, total_pct=float("nan"))
        b = _make_config("B", comp, total_pct=50.0)
        with pytest.raises(ValueError, match="not finite"):
            compare_configs(a, b)

    def test_nan_float_composite_warned(self, caplog):
        import logging

        comp_a = np.array([[True, False], [True, False]], dtype=bool)
        comp_b = np.array([[np.nan, 0.0], [1.0, np.nan]], dtype=float)
        a = _make_config("A", comp_a)
        b = _make_config("B", comp_b)
        with caplog.at_level(logging.WARNING, logger="salus.engine.comparison"):
            result = compare_configs(a, b)
        assert any("NaN" in rec.message for rec in caplog.records)
        # NaN cells in B treated as uncovered.
        assert result.delta_grid.shape == (2, 2)


# ---------------------------------------------------------------------------
# Delta grid
# ---------------------------------------------------------------------------


class TestDeltaGrid:
    def _grid(self) -> tuple[np.ndarray, np.ndarray]:
        """
        4-cell composite:
          A covers top-left (0,0) and top-right (0,1).
          B covers top-right (0,1) and bottom-left (1,0).

        Expected delta:
          (0,0) → A-only
          (0,1) → both
          (1,0) → B-only
          (1,1) → neither
        """
        comp_a = np.array([[True, True], [False, False]], dtype=bool)
        comp_b = np.array([[False, True], [True, False]], dtype=bool)
        return comp_a, comp_b

    def test_delta_neither(self):
        comp_a, comp_b = self._grid()
        a = _make_config("A", comp_a)
        b = _make_config("B", comp_b)
        result = compare_configs(a, b)
        assert result.delta_grid[1, 1] == DELTA_NEITHER

    def test_delta_both(self):
        comp_a, comp_b = self._grid()
        a = _make_config("A", comp_a)
        b = _make_config("B", comp_b)
        result = compare_configs(a, b)
        assert result.delta_grid[0, 1] == DELTA_BOTH

    def test_delta_a_only(self):
        comp_a, comp_b = self._grid()
        a = _make_config("A", comp_a)
        b = _make_config("B", comp_b)
        result = compare_configs(a, b)
        assert result.delta_grid[0, 0] == DELTA_A_ONLY

    def test_delta_b_only(self):
        comp_a, comp_b = self._grid()
        a = _make_config("A", comp_a)
        b = _make_config("B", comp_b)
        result = compare_configs(a, b)
        assert result.delta_grid[1, 0] == DELTA_B_ONLY

    def test_delta_grid_dtype_int8(self):
        comp = np.ones((5, 5), dtype=bool)
        a = _make_config("A", comp)
        b = _make_config("B", comp)
        result = compare_configs(a, b)
        assert result.delta_grid.dtype == np.int8

    def test_delta_grid_shape_matches_composite(self):
        comp_a = np.ones((6, 7), dtype=bool)
        comp_b = np.zeros((6, 7), dtype=bool)
        a = _make_config("A", comp_a)
        b = _make_config("B", comp_b)
        result = compare_configs(a, b)
        assert result.delta_grid.shape == (6, 7)

    def test_identical_coverage_all_both_or_neither(self):
        comp = np.array([[True, False], [True, False]], dtype=bool)
        a = _make_config("A", comp)
        b = _make_config("B", comp)
        result = compare_configs(a, b)
        assert np.all((result.delta_grid == DELTA_BOTH) | (result.delta_grid == DELTA_NEITHER))

    def test_no_coverage_all_neither(self):
        comp = np.zeros((4, 4), dtype=bool)
        a = _make_config("A", comp)
        b = _make_config("B", comp)
        result = compare_configs(a, b)
        assert np.all(result.delta_grid == DELTA_NEITHER)


# ---------------------------------------------------------------------------
# Coverage percentage deltas
# ---------------------------------------------------------------------------


class TestCoveragePercentageDelta:
    def test_coverage_delta_positive_when_b_higher(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, total_pct=40.0)
        b = _make_config("B", comp, total_pct=65.0)
        result = compare_configs(a, b)
        assert result.coverage_delta_pct == pytest.approx(25.0)

    def test_coverage_delta_negative_when_b_lower(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, total_pct=70.0)
        b = _make_config("B", comp, total_pct=55.0)
        result = compare_configs(a, b)
        assert result.coverage_delta_pct == pytest.approx(-15.0)

    def test_coverage_delta_zero_when_equal(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, total_pct=60.0)
        b = _make_config("B", comp, total_pct=60.0)
        result = compare_configs(a, b)
        assert result.coverage_delta_pct == pytest.approx(0.0)

    def test_coverage_pct_a_and_b_preserved(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, total_pct=33.3)
        b = _make_config("B", comp, total_pct=77.7)
        result = compare_configs(a, b)
        assert result.coverage_pct_a == pytest.approx(33.3)
        assert result.coverage_pct_b == pytest.approx(77.7)


# ---------------------------------------------------------------------------
# Per-zone delta
# ---------------------------------------------------------------------------


class TestPerZoneDelta:
    def test_common_zones_computed(self):
        comp = np.ones((4, 4), dtype=bool)
        zones_a = {"north": 40.0, "south": 60.0}
        zones_b = {"north": 55.0, "south": 50.0}
        a = _make_config("A", comp, zones=zones_a)
        b = _make_config("B", comp, zones=zones_b)
        result = compare_configs(a, b)
        assert result.per_zone_delta_pct["north"] == pytest.approx(15.0)
        assert result.per_zone_delta_pct["south"] == pytest.approx(-10.0)

    def test_zones_only_in_a_excluded(self):
        comp = np.ones((4, 4), dtype=bool)
        zones_a = {"north": 40.0, "east": 30.0}
        zones_b = {"north": 55.0}
        a = _make_config("A", comp, zones=zones_a)
        b = _make_config("B", comp, zones=zones_b)
        result = compare_configs(a, b)
        assert "east" not in result.per_zone_delta_pct
        assert "north" in result.per_zone_delta_pct

    def test_zones_only_in_b_excluded(self):
        comp = np.ones((4, 4), dtype=bool)
        zones_a = {"north": 40.0}
        zones_b = {"north": 55.0, "west": 20.0}
        a = _make_config("A", comp, zones=zones_a)
        b = _make_config("B", comp, zones=zones_b)
        result = compare_configs(a, b)
        assert "west" not in result.per_zone_delta_pct

    def test_no_zones_empty_delta(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp)
        b = _make_config("B", comp)
        result = compare_configs(a, b)
        assert result.per_zone_delta_pct == {}

    def test_zone_dicts_copied_not_aliased(self):
        comp = np.ones((4, 4), dtype=bool)
        zones = {"north": 50.0}
        a = _make_config("A", comp, zones=zones)
        b = _make_config("B", comp, zones={"north": 70.0})
        result = compare_configs(a, b)
        zones["north"] = 0.0  # mutate original
        assert result.per_zone_coverage_pct_a["north"] == pytest.approx(50.0)

    def test_per_zone_delta_sorted_keys(self):
        comp = np.ones((4, 4), dtype=bool)
        zones_a = {"zulu": 10.0, "alpha": 20.0, "mike": 30.0}
        zones_b = {"zulu": 15.0, "alpha": 25.0, "mike": 35.0}
        a = _make_config("A", comp, zones=zones_a)
        b = _make_config("B", comp, zones=zones_b)
        result = compare_configs(a, b)
        assert list(result.per_zone_delta_pct.keys()) == sorted(zones_a.keys())


# ---------------------------------------------------------------------------
# Optional metric deltas
# ---------------------------------------------------------------------------


class TestOptionalMetricDeltas:
    def test_cost_delta_computed(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, cost=100_000.0)
        b = _make_config("B", comp, cost=250_000.0)
        result = compare_configs(a, b)
        assert result.cost_delta == pytest.approx(150_000.0)

    def test_cost_delta_none_when_a_missing(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, cost=None)
        b = _make_config("B", comp, cost=250_000.0)
        result = compare_configs(a, b)
        assert result.cost_delta is None

    def test_cost_delta_none_when_b_missing(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, cost=100_000.0)
        b = _make_config("B", comp, cost=None)
        result = compare_configs(a, b)
        assert result.cost_delta is None

    def test_cost_delta_none_when_both_missing(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp)
        b = _make_config("B", comp)
        result = compare_configs(a, b)
        assert result.cost_delta is None

    def test_saturation_threshold_delta_computed(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, sat_n=5)
        b = _make_config("B", comp, sat_n=9)
        result = compare_configs(a, b)
        assert result.saturation_threshold_delta == 4

    def test_saturation_threshold_delta_none_when_missing(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, sat_n=5)
        b = _make_config("B", comp)
        result = compare_configs(a, b)
        assert result.saturation_threshold_delta is None

    def test_engagement_capacity_delta_computed(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, capacity=8)
        b = _make_config("B", comp, capacity=12)
        result = compare_configs(a, b)
        assert result.engagement_capacity_delta == 4

    def test_engagement_capacity_delta_none_when_missing(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, capacity=8)
        b = _make_config("B", comp)
        result = compare_configs(a, b)
        assert result.engagement_capacity_delta is None


# ---------------------------------------------------------------------------
# Result labels
# ---------------------------------------------------------------------------


class TestResultLabels:
    def test_labels_passed_through(self):
        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("Alpha Config", comp)
        b = _make_config("Bravo Config", comp)
        result = compare_configs(a, b)
        assert result.label_a == "Alpha Config"
        assert result.label_b == "Bravo Config"


# ---------------------------------------------------------------------------
# Skipped-zone logging (warning check)
# ---------------------------------------------------------------------------


class TestSkippedZoneWarning:
    def test_skipped_zones_trigger_warning(self, caplog):
        import logging

        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, zones={"north": 40.0, "east": 30.0})
        b = _make_config("B", comp, zones={"north": 55.0})
        with caplog.at_level(logging.WARNING, logger="salus.engine.comparison"):
            compare_configs(a, b)
        assert any("east" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# D-214: cost_estimate inf/nan guard
# ---------------------------------------------------------------------------


class TestCostEstimateFiniteGuard:
    def test_cost_delta_none_when_cost_is_inf(self, caplog):
        import logging

        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, cost=float("inf"))
        b = _make_config("B", comp, cost=250_000.0)
        with caplog.at_level(logging.WARNING, logger="salus.engine.comparison"):
            result = compare_configs(a, b)
        assert result.cost_delta is None
        assert any("non-finite" in rec.message for rec in caplog.records)

    def test_cost_delta_none_when_cost_is_nan(self, caplog):
        import logging

        comp = np.ones((4, 4), dtype=bool)
        a = _make_config("A", comp, cost=float("nan"))
        b = _make_config("B", comp, cost=250_000.0)
        with caplog.at_level(logging.WARNING, logger="salus.engine.comparison"):
            result = compare_configs(a, b)
        assert result.cost_delta is None
        assert any("non-finite" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# D-215: non-numeric composite dtype guard
# ---------------------------------------------------------------------------


class TestNonNumericCompositeGuard:
    def test_object_dtype_composite_raises(self):
        """Object-dtype composite must raise TypeError, not silently corrupt delta grid."""
        comp_a = np.ones((4, 4), dtype=bool)
        comp_b = np.empty((4, 4), dtype=object)
        comp_b[:] = True
        a = _make_config("A", comp_a)
        b = _make_config("B", comp_b)
        with pytest.raises(TypeError, match="numeric dtype"):
            compare_configs(a, b)

    def test_b_composite_1d_raises(self):
        """B composite being 1-D must raise ValueError (symmetric with A)."""
        a = _make_config("A", np.ones((4, 4), dtype=bool))
        b = _make_config("B", np.ones(16, dtype=bool))
        with pytest.raises(ValueError, match="2-D"):
            compare_configs(a, b)
