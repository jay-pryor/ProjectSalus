"""Tests for threat corridor coverage analysis (S6-2, S6-3)."""

from __future__ import annotations

import numpy as np
import pytest

from salus.engine.threat_corridor import (
    CorridorResult,
    analyse_corridor,
    find_worst_corridors,
)
from salus.models.site import SiteModel
from salus.models.threat import ThreatCorridor, ThreatProfile

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RESOLUTION = 10.0  # 10 m per cell
_ROWS, _COLS = 100, 100
_ORIGIN_X = 500000.0
_ORIGIN_Y = 6101000.0  # top-left northing (max_y)

# Centre of grid in world coords
_CENTRE_X = _ORIGIN_X + (_COLS / 2) * _RESOLUTION  # 500500
_CENTRE_Y = _ORIGIN_Y - (_ROWS / 2) * _RESOLUTION  # 6100500


@pytest.fixture
def site_10m() -> SiteModel:
    """100×100 flat DEM at 10 m resolution."""
    dem = np.full((_ROWS, _COLS), 50.0)
    return SiteModel(
        dem=dem,
        resolution=_RESOLUTION,
        origin_x=_ORIGIN_X,
        origin_y=_ORIGIN_Y,
    )


@pytest.fixture
def all_covered(site_10m: SiteModel) -> np.ndarray:
    """Composite coverage array: all cells covered."""
    return np.ones((site_10m.rows, site_10m.cols), dtype=bool)


@pytest.fixture
def none_covered(site_10m: SiteModel) -> np.ndarray:
    """Composite coverage array: no cells covered."""
    return np.zeros((site_10m.rows, site_10m.cols), dtype=bool)


@pytest.fixture
def threat_fast() -> ThreatProfile:
    return ThreatProfile(
        name="Test Threat",
        rcs_m2=0.01,
        rf_signature="2.4 GHz",
        max_speed_ms=20.0,
        typical_altitude_m=50.0,
    )


@pytest.fixture
def corridor_north() -> ThreatCorridor:
    """Corridor approaching from the south (bearing=0, north), 500 m start."""
    return ThreatCorridor(bearing_deg=0.0, altitude_m=50.0, start_distance_m=500.0)


# ---------------------------------------------------------------------------
# Return type and structure
# ---------------------------------------------------------------------------


class TestCorridorResultStructure:
    def test_returns_corridor_result(self, site_10m, all_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert isinstance(result, CorridorResult)

    def test_corridor_reference_preserved(self, site_10m, all_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.corridor is corridor_north

    def test_threat_name_stored(self, site_10m, all_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.threat_name == "Test Threat"


# ---------------------------------------------------------------------------
# All-covered corridor
# ---------------------------------------------------------------------------


class TestAllCovered:
    def test_coverage_pct_100(self, site_10m, all_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.coverage_pct == pytest.approx(100.0)

    def test_first_detection_at_start_distance(
        self, site_10m, all_covered, threat_fast, corridor_north
    ):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        # All cells covered — first detection is at the far end of the corridor.
        assert result.first_detection_distance_m == pytest.approx(
            corridor_north.start_distance_m, rel=0.05
        )

    def test_last_gap_zero(self, site_10m, all_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.last_gap_before_target_m == pytest.approx(0.0)

    def test_time_in_coverage_positive(self, site_10m, all_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.time_in_coverage_s > 0.0

    def test_time_equals_distance_over_speed(
        self, site_10m, all_covered, threat_fast, corridor_north
    ):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        expected_time = (result.covered_cells * _RESOLUTION) / threat_fast.max_speed_ms
        assert result.time_in_coverage_s == pytest.approx(expected_time)

    def test_covered_cells_equals_total_cells(
        self, site_10m, all_covered, threat_fast, corridor_north
    ):
        result = analyse_corridor(
            site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.covered_cells == result.total_cells


# ---------------------------------------------------------------------------
# None-covered corridor
# ---------------------------------------------------------------------------


class TestNoneCovered:
    def test_coverage_pct_zero(self, site_10m, none_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, none_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.coverage_pct == pytest.approx(0.0)

    def test_first_detection_none(self, site_10m, none_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, none_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.first_detection_distance_m is None

    def test_last_gap_equals_in_bounds_corridor_length(
        self, site_10m, none_covered, threat_fast, corridor_north
    ):
        result = analyse_corridor(
            site_10m, none_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        # All cells uncovered → last gap = total_cells * resolution
        expected_gap = result.total_cells * _RESOLUTION
        assert result.last_gap_before_target_m == pytest.approx(expected_gap, rel=0.05)

    def test_time_in_coverage_zero(self, site_10m, none_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, none_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.time_in_coverage_s == pytest.approx(0.0)

    def test_covered_cells_zero(self, site_10m, none_covered, threat_fast, corridor_north):
        result = analyse_corridor(
            site_10m, none_covered, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y)
        )
        assert result.covered_cells == 0


# ---------------------------------------------------------------------------
# Partial coverage
# ---------------------------------------------------------------------------


class TestPartialCoverage:
    def test_coverage_pct_between_zero_and_100(self, site_10m, threat_fast):
        # Asset in the east half (col=75); corridor approaches from west (bearing=90).
        # Only the east half (cols >= 50) is covered, giving partial coverage.
        partial = np.zeros((site_10m.rows, site_10m.cols), dtype=bool)
        partial[:, 50:] = True
        asset_x = _ORIGIN_X + 75 * _RESOLUTION  # col 75
        asset_y = _CENTRE_Y
        corridor = ThreatCorridor(bearing_deg=90.0, altitude_m=50.0, start_distance_m=300.0)
        result = analyse_corridor(site_10m, partial, corridor, threat_fast, (asset_x, asset_y))
        assert 0.0 < result.coverage_pct < 100.0

    def test_last_gap_nonzero_when_target_uncovered(self, site_10m, threat_fast):
        # Cover only far half of the corridor (far from asset)
        # Corridor approaches from the south (bearing=0), so we need coverage
        # in the UPPER rows (smaller row index = higher northing = farther from
        # the asset which is at the south of the corridor path).
        # Asset at bottom centre; corridor goes from bottom to top.
        # origin_y is the TOP of the grid (max northing).
        # If bearing=0 (north), drone approaches from south to north, but
        # "towards asset" means bearing points to asset.
        # Let's place the asset at the bottom centre and use bearing=0 (north).
        # Actually with bearing=0 (north), the drone is going north.
        # The drone starts at bottom (south) and moves north to reach the asset.
        # Wait — bearing is "towards asset". If bearing=0, asset is to the north.
        # So the asset is at the NORTH end of the corridor.
        # The drone starts SOUTH of the asset and moves north.
        # Asset position: top of grid (high northing)
        asset_x = _CENTRE_X
        asset_y = _ORIGIN_Y - 5 * _RESOLUTION  # row=5 from top
        # Drone starts 200m south (bearing=0 = north, so "away from asset" is south)
        corridor = ThreatCorridor(bearing_deg=0.0, altitude_m=50.0, start_distance_m=200.0)
        # Cover only far cells (row >=50): cells far from asset are not covered
        # The near cells (close to asset, top of grid, low row index) are uncovered.
        near_covered = np.zeros((site_10m.rows, site_10m.cols), dtype=bool)
        near_covered[50:, :] = True  # bottom half covered (far from asset)
        result = analyse_corridor(site_10m, near_covered, corridor, threat_fast, (asset_x, asset_y))
        assert result.last_gap_before_target_m > 0.0

    def test_first_detection_at_correct_distance(self, site_10m, threat_fast):
        # All-covered composite; simple check that first detection is at the far end.
        covered = np.ones((site_10m.rows, site_10m.cols), dtype=bool)
        corridor = ThreatCorridor(bearing_deg=90.0, altitude_m=50.0, start_distance_m=300.0)
        result = analyse_corridor(site_10m, covered, corridor, threat_fast, (_CENTRE_X, _CENTRE_Y))
        assert result.first_detection_distance_m == pytest.approx(300.0, rel=0.05)

    def test_different_bearings_produce_results(self, site_10m, all_covered, threat_fast):
        """Results are produced for all compass bearings."""
        for bearing in [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]:
            corridor = ThreatCorridor(bearing_deg=bearing, altitude_m=50.0, start_distance_m=200.0)
            result = analyse_corridor(
                site_10m, all_covered, corridor, threat_fast, (_CENTRE_X, _CENTRE_Y)
            )
            assert isinstance(result, CorridorResult)
            assert result.coverage_pct >= 0.0


# ---------------------------------------------------------------------------
# Out-of-bounds corridor
# ---------------------------------------------------------------------------


class TestOutOfBounds:
    def test_corridor_entirely_outside_grid_returns_zero_cells(
        self, site_10m, all_covered, threat_fast
    ):
        # Place asset far outside the grid.
        outside_x = _ORIGIN_X - 5000.0
        outside_y = _ORIGIN_Y + 5000.0
        corridor = ThreatCorridor(bearing_deg=0.0, altitude_m=50.0, start_distance_m=100.0)
        result = analyse_corridor(
            site_10m, all_covered, corridor, threat_fast, (outside_x, outside_y)
        )
        assert result.total_cells == 0
        assert result.coverage_pct == pytest.approx(0.0)
        assert result.first_detection_distance_m is None

    def test_partial_out_of_bounds_counts_only_in_bounds(self, site_10m, all_covered, threat_fast):
        # Asset near west edge (col=2); bearing=90 (east) so as d increases
        # the sample moves west and exits the grid quickly.
        # sin(90°)=1 → sample_x = (500020) - d; in bounds when d <= 20 (3 cells).
        asset_x = _ORIGIN_X + 2 * _RESOLUTION  # col 2
        asset_y = _CENTRE_Y
        corridor = ThreatCorridor(bearing_deg=90.0, altitude_m=50.0, start_distance_m=500.0)
        result = analyse_corridor(site_10m, all_covered, corridor, threat_fast, (asset_x, asset_y))
        assert result.total_cells < 10
        assert result.total_cells > 0
        assert result.total_cells > 0


# ---------------------------------------------------------------------------
# Guard validation
# ---------------------------------------------------------------------------


class TestGuards:
    def test_non_2d_composite_raises(self, site_10m, threat_fast, corridor_north):
        bad = np.ones((10,), dtype=bool)
        with pytest.raises(ValueError, match="2D"):
            analyse_corridor(site_10m, bad, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y))

    def test_empty_composite_raises(self, site_10m, threat_fast, corridor_north):
        bad = np.ones((0, 0), dtype=bool)
        with pytest.raises(ValueError, match="empty"):
            analyse_corridor(site_10m, bad, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y))

    def test_shape_mismatch_raises(self, site_10m, threat_fast, corridor_north):
        bad = np.ones((50, 50), dtype=bool)
        with pytest.raises(ValueError, match="shape"):
            analyse_corridor(site_10m, bad, corridor_north, threat_fast, (_CENTRE_X, _CENTRE_Y))

    def test_nan_protected_point_x_raises(self, site_10m, all_covered, threat_fast, corridor_north):
        with pytest.raises(ValueError, match="finite"):
            analyse_corridor(
                site_10m, all_covered, corridor_north, threat_fast, (float("nan"), _CENTRE_Y)
            )

    def test_inf_protected_point_y_raises(self, site_10m, all_covered, threat_fast, corridor_north):
        with pytest.raises(ValueError, match="finite"):
            analyse_corridor(
                site_10m, all_covered, corridor_north, threat_fast, (_CENTRE_X, float("inf"))
            )


# ---------------------------------------------------------------------------
# find_worst_corridors (S6-3)
# ---------------------------------------------------------------------------


class TestFindWorstCorridors:
    def test_returns_list_of_corridor_results(self, site_10m, all_covered, threat_fast):
        results = find_worst_corridors(site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y))
        assert isinstance(results, list)
        assert all(isinstance(r, CorridorResult) for r in results)

    def test_default_num_bearings_is_36(self, site_10m, all_covered, threat_fast):
        results = find_worst_corridors(site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y))
        assert len(results) == 36

    def test_custom_num_bearings(self, site_10m, all_covered, threat_fast):
        results = find_worst_corridors(
            site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y), num_bearings=8
        )
        assert len(results) == 8

    def test_sorted_ascending_by_coverage_pct(self, site_10m, all_covered, threat_fast):
        results = find_worst_corridors(site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y))
        pcts = [r.coverage_pct for r in results]
        assert pcts == sorted(pcts)

    def test_worst_case_is_first(self, site_10m, none_covered, threat_fast):
        # With no coverage, all corridors have 0% — worst is still first.
        results = find_worst_corridors(site_10m, none_covered, threat_fast, (_CENTRE_X, _CENTRE_Y))
        assert results[0].coverage_pct <= results[-1].coverage_pct

    def test_all_covered_all_100_pct(self, site_10m, all_covered, threat_fast):
        results = find_worst_corridors(site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y))
        for r in results:
            assert r.coverage_pct == pytest.approx(100.0)

    def test_bearings_cover_full_360(self, site_10m, all_covered, threat_fast):
        results = find_worst_corridors(
            site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y), num_bearings=4
        )
        bearings = {r.corridor.bearing_deg for r in results}
        assert len(bearings) == 4

    def test_threat_name_in_all_results(self, site_10m, all_covered, threat_fast):
        results = find_worst_corridors(site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y))
        for r in results:
            assert r.threat_name == threat_fast.name

    def test_partial_coverage_produces_mixed_results(self, site_10m, threat_fast):
        # Cover only the east half: corridors from the east should show higher
        # coverage than corridors from the west.
        partial = np.zeros((site_10m.rows, site_10m.cols), dtype=bool)
        partial[:, 50:] = True
        results = find_worst_corridors(
            site_10m, partial, threat_fast, (_CENTRE_X, _CENTRE_Y), num_bearings=36
        )
        pcts = [r.coverage_pct for r in results]
        assert min(pcts) < max(pcts)

    def test_zero_num_bearings_raises(self, site_10m, all_covered, threat_fast):
        with pytest.raises(ValueError, match="num_bearings"):
            find_worst_corridors(
                site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y), num_bearings=0
            )

    def test_negative_num_bearings_raises(self, site_10m, all_covered, threat_fast):
        with pytest.raises(ValueError, match="num_bearings"):
            find_worst_corridors(
                site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y), num_bearings=-1
            )

    def test_num_bearings_one_returns_single_result(self, site_10m, all_covered, threat_fast):
        results = find_worst_corridors(
            site_10m, all_covered, threat_fast, (_CENTRE_X, _CENTRE_Y), num_bearings=1
        )
        assert len(results) == 1
