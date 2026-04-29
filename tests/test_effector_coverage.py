"""Tests for effector coverage computation (S11-1).

Covers:
- RF jammer produces range circle not blocked by terrain (non-LOS)
- Kinetic effector produces viewshed-based zone (blocked by terrain ridge)
- Range max clipping: cells beyond max_range are False
- Min-range dead zone: cells within min_range are False
- Engagement arc clipping: cells outside arc are False
- 360° arc: no arc masking applied
- Union of multiple effectors
- Empty effector list returns all-False array
- Non-finite height raises ValueError
"""

from __future__ import annotations

import numpy as np
import pytest

from salus.engine.effector_coverage import (
    compute_effector_layer_coverage,
    compute_single_effector_coverage,
)
from salus.models.scenario import EffectorPlacement
from salus.models.sensor import EffectorDefinition, EffectorType
from salus.models.site import SiteModel

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def flat_site() -> SiteModel:
    """50×50 flat DEM at 1 m resolution, 50 m elevation.

    CRS origin: origin_x=0.0, origin_y=50.0 (top-left corner).
    """
    dem = np.full((50, 50), 50.0, dtype=np.float64)
    return SiteModel(dem=dem, resolution=1.0, origin_x=0.0, origin_y=50.0)


@pytest.fixture
def ridge_site() -> SiteModel:
    """100×100 DEM with a ridge at rows 45–55 (peak 150 m at row 50).

    The ridge creates a terrain shadow south of the observer (placed at
    row 10 from the top = y=40 in CRS).  Cells south of the ridge (rows>55)
    are not visible from an observer on the north side.
    """
    dem = np.full((100, 100), 50.0, dtype=np.float64)
    for r in range(45, 56):
        height = 150.0 - abs(r - 50) * 10.0
        dem[r, :] = max(height, 50.0)
    return SiteModel(dem=dem, resolution=1.0, origin_x=0.0, origin_y=100.0)


@pytest.fixture
def rf_jammer() -> EffectorDefinition:
    """RF jammer — omnidirectional, 30 m max range, no LOS required."""
    return EffectorDefinition(
        name="TestJammer",
        type=EffectorType.RF_Jammer,
        max_range_m=30.0,
        min_range_m=0.0,
        engagement_arc_deg=360.0,
        reaction_time_s=0.5,
        defeat_probability=0.9,
        requires_los=False,
        defeat_mechanism="RF jamming",
    )


@pytest.fixture
def kinetic_effector() -> EffectorDefinition:
    """Kinetic effector — 40 m max range, LOS required, full 360° arc."""
    return EffectorDefinition(
        name="TestKinetic",
        type=EffectorType.Kinetic,
        max_range_m=40.0,
        min_range_m=0.0,
        engagement_arc_deg=360.0,
        reaction_time_s=1.0,
        defeat_probability=0.85,
        requires_los=True,
        defeat_mechanism="Kinetic intercept",
    )


@pytest.fixture
def directional_effector() -> EffectorDefinition:
    """Kinetic effector with a 90° engagement arc, 20 m range."""
    return EffectorDefinition(
        name="DirectionalKinetic",
        type=EffectorType.Kinetic,
        max_range_m=20.0,
        min_range_m=0.0,
        engagement_arc_deg=90.0,
        reaction_time_s=1.0,
        defeat_probability=0.8,
        requires_los=True,
        defeat_mechanism="Kinetic intercept",
    )


def _centre_placement(site: SiteModel, bearing: float = 0.0) -> EffectorPlacement:
    """Place effector at the approximate CRS centre of the site."""
    cx = site.origin_x + site.cols * site.resolution / 2.0
    cy = site.origin_y - site.rows * site.resolution / 2.0
    return EffectorPlacement(
        effector_name="test",
        position_x=cx,
        position_y=cy,
        bearing_deg=bearing,
    )


# ---------------------------------------------------------------------------
# RF jammer (non-LOS) tests
# ---------------------------------------------------------------------------


class TestRfJammerCoverage:
    def test_rf_jammer_is_not_blocked_by_ridge(
        self, ridge_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """RF jammer range circle must not be blocked by terrain."""
        # Place jammer on north side of ridge (row ~10 in raster = y ~90)
        placement = EffectorPlacement(
            effector_name="test",
            position_x=50.0,
            position_y=90.0,
            bearing_deg=0.0,
        )
        cov = compute_single_effector_coverage(ridge_site, rf_jammer, placement)
        # Cells south of the ridge at y=55 (row 45 from top) should still be True
        # if within 30 m range.  y=90 - 30 = 60 (row 40 from top).
        # The ridge peak is at row 50 (y=50).  A cell at row 40 (y=60) is 30 m away.
        assert cov[40, 50], "RF jammer should cover cells within range despite ridge"

    def test_rf_jammer_circle_shape(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """RF jammer coverage should be approximately circular."""
        placement = _centre_placement(flat_site)
        cov = compute_single_effector_coverage(flat_site, rf_jammer, placement)
        assert cov.any(), "RF jammer should have some coverage"
        # Check cells at exactly 30 m in 4 compass directions are covered
        cx, cy = 25.0, 25.0  # centre
        # Cell at (25, 55) = 30 m north of centre
        # origin_y=50, so row for y=55: row = (50 - 55) / 1 = -5 — outside raster
        # Use cell at y=25+25=50: row = (50-50)/1=0 — top edge, 25 m away
        row_north = int((flat_site.origin_y - (cy + 20.0)) / flat_site.resolution)
        col_centre = int((cx - flat_site.origin_x) / flat_site.resolution)
        assert 0 <= row_north < flat_site.rows, "row_north fixture check"
        assert cov[row_north, col_centre], "Cell 20 m north should be covered"

    def test_rf_jammer_beyond_max_range_is_false(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """Cells beyond max_range_m must not be covered."""
        # Place jammer at top-left corner so cells far to the right are beyond range
        placement = EffectorPlacement(
            effector_name="test",
            position_x=0.0,
            position_y=50.0,
            bearing_deg=0.0,
        )
        cov = compute_single_effector_coverage(flat_site, rf_jammer, placement)
        # Cell at col 49 (49 m away) is beyond 30 m range
        assert not cov[0, 49], "Cell 49 m away must not be covered by 30 m jammer"


# ---------------------------------------------------------------------------
# Kinetic/DE (LOS-required) tests
# ---------------------------------------------------------------------------


class TestKineticEffectorCoverage:
    def test_kinetic_is_blocked_by_ridge(
        self, ridge_site: SiteModel, kinetic_effector: EffectorDefinition
    ) -> None:
        """Kinetic effector must not cover cells hidden behind a terrain ridge."""
        # Effector at (x=50, y=85) → row=15, col=50 — north side of ridge.
        # Ridge peak at row 50 (y=50).  A cell at row 65 (y=35) is in the
        # terrain shadow behind the ridge and within 50 m (kinetic max_range=40 m).
        # Distance from effector to row 65: |85-35|=50 m → just at/beyond max_range.
        # Use a longer-range kinetic effector to reach beyond the ridge.
        long_range_kinetic = EffectorDefinition(
            name="LongKinetic",
            type=EffectorType.Kinetic,
            max_range_m=80.0,
            min_range_m=0.0,
            engagement_arc_deg=360.0,
            reaction_time_s=1.0,
            defeat_probability=0.85,
            requires_los=True,
            defeat_mechanism="Kinetic intercept",
        )
        placement = EffectorPlacement(
            effector_name="test",
            position_x=50.0,
            position_y=85.0,
            bearing_deg=0.0,
        )
        cov = compute_single_effector_coverage(ridge_site, long_range_kinetic, placement)
        # row 65 = y=35, distance from effector (y=85) is 50 m — within 80 m range
        # but behind the ridge (ridge peak at row 50, y=50) — must NOT be visible
        assert not cov[65, 50], "Cell behind ridge must not be in kinetic engagement zone"

    def test_kinetic_covers_visible_cells(
        self, flat_site: SiteModel, kinetic_effector: EffectorDefinition
    ) -> None:
        """Kinetic effector must cover nearby visible cells on flat terrain."""
        placement = _centre_placement(flat_site)
        cov = compute_single_effector_coverage(flat_site, kinetic_effector, placement)
        assert cov.any(), "Kinetic effector on flat terrain should have coverage"
        # The effector is at (25, 25) — a cell 5 m away should be covered
        row_near = int((flat_site.origin_y - (25.0 + 5.0)) / flat_site.resolution)
        col_centre = int((25.0 - flat_site.origin_x) / flat_site.resolution)
        if 0 <= row_near < flat_site.rows:
            assert cov[row_near, col_centre], "Visible cell 5 m away should be covered"

    def test_kinetic_max_range_clipping(
        self, flat_site: SiteModel, kinetic_effector: EffectorDefinition
    ) -> None:
        """Cells beyond kinetic max_range_m must not be covered."""
        # flat_site is 50×50; place effector at (x=25, y=25) — the centre.
        # kinetic max_range=40 m.  A cell at x=25, y=25+45=70 is outside the
        # site, so use a diagonal: cell at (row=3, col=3) = x=3,y=47.
        # Distance from (25,25): sqrt(22²+22²) ≈ 31 m — within range.  Use row=0, col=0:
        # distance = sqrt(25²+25²) ≈ 35.4 m — still within range.
        # For a cell clearly outside 40 m: place effector at corner and check distant cell.
        # On a 50×50 grid centred at (25,25), all cells are within ≈35.4 m of centre —
        # within the 40 m kinetic range.  Use a smaller-range effector instead.
        short_kinetic = EffectorDefinition(
            name="ShortKinetic",
            type=EffectorType.Kinetic,
            max_range_m=10.0,
            min_range_m=0.0,
            engagement_arc_deg=360.0,
            reaction_time_s=1.0,
            defeat_probability=0.85,
            requires_los=True,
            defeat_mechanism="Kinetic intercept",
        )
        placement_corner = EffectorPlacement(
            effector_name="test",
            position_x=0.0,
            position_y=50.0,  # top-left corner (row=0, col=0)
            bearing_deg=0.0,
        )
        cov2 = compute_single_effector_coverage(flat_site, short_kinetic, placement_corner)
        # Cell at (row=0, col=15) → x=15, y=50. Distance = 15 m > 10 m.
        assert not cov2[0, 15], "Cell 15 m away must not be in 10 m kinetic zone"


# ---------------------------------------------------------------------------
# Min-range dead zone tests
# ---------------------------------------------------------------------------


class TestMinRangeDeadZone:
    def test_cells_within_min_range_excluded(self, flat_site: SiteModel) -> None:
        """Cells within min_range_m must not be in the engagement zone."""
        effector = EffectorDefinition(
            name="DeadZoneEffector",
            type=EffectorType.RF_Jammer,
            max_range_m=20.0,
            min_range_m=5.0,
            engagement_arc_deg=360.0,
            reaction_time_s=0.5,
            defeat_probability=0.9,
            requires_los=False,
            defeat_mechanism="RF jamming",
        )
        placement = _centre_placement(flat_site)
        cov = compute_single_effector_coverage(flat_site, effector, placement)
        # Cell at effector position (dist = 0) must be False (within dead zone)
        cx = int((25.0 - flat_site.origin_x) / flat_site.resolution)
        cy_row = int((flat_site.origin_y - 25.0) / flat_site.resolution)
        assert not cov[cy_row, cx], "Effector cell itself must be in dead zone"

    def test_cells_at_exactly_min_range_included(self, flat_site: SiteModel) -> None:
        """The range mask is inclusive: cells at exactly min_range_m are covered."""
        effector = EffectorDefinition(
            name="ExactMinRange",
            type=EffectorType.RF_Jammer,
            max_range_m=20.0,
            min_range_m=5.0,
            engagement_arc_deg=360.0,
            reaction_time_s=0.5,
            defeat_probability=0.9,
            requires_los=False,
            defeat_mechanism="RF jamming",
        )
        placement = EffectorPlacement(
            effector_name="test",
            position_x=25.0,
            position_y=25.0,
            bearing_deg=0.0,
        )
        cov = compute_single_effector_coverage(flat_site, effector, placement)
        # Cell exactly 5 m east: col = 25+5=30, row = (50-25)/1=25
        row_at_min = int((flat_site.origin_y - 25.0) / flat_site.resolution)
        col_at_min = int((30.0 - flat_site.origin_x) / flat_site.resolution)
        if 0 <= row_at_min < flat_site.rows and 0 <= col_at_min < flat_site.cols:
            assert cov[row_at_min, col_at_min], "Cell at exactly min_range_m should be included"


# ---------------------------------------------------------------------------
# Engagement arc tests
# ---------------------------------------------------------------------------


class TestEngagementArc:
    def test_directional_effector_excludes_rear_cells(
        self, flat_site: SiteModel, directional_effector: EffectorDefinition
    ) -> None:
        """A 90° north-facing effector must not cover cells directly to the south."""
        # Bearing 0 = north; 90° arc covers ±45° around north
        placement = EffectorPlacement(
            effector_name="test",
            position_x=25.0,
            position_y=25.0,
            bearing_deg=0.0,  # facing north
        )
        cov = compute_single_effector_coverage(flat_site, directional_effector, placement)
        # Cell 10 m south (bearing 180°) should be outside the ±45° arc
        row_south = int((flat_site.origin_y - (25.0 - 10.0)) / flat_site.resolution)
        col_centre = int((25.0 - flat_site.origin_x) / flat_site.resolution)
        if 0 <= row_south < flat_site.rows:
            assert not cov[row_south, col_centre], "Cell to south must be outside 90° north arc"

    def test_directional_effector_covers_forward_cells(
        self, flat_site: SiteModel, directional_effector: EffectorDefinition
    ) -> None:
        """A 90° north-facing effector must cover cells directly to the north."""
        placement = EffectorPlacement(
            effector_name="test",
            position_x=25.0,
            position_y=25.0,
            bearing_deg=0.0,  # facing north
        )
        cov = compute_single_effector_coverage(flat_site, directional_effector, placement)
        # Cell 10 m north (bearing 0°) should be inside the ±45° arc
        row_north = int((flat_site.origin_y - (25.0 + 10.0)) / flat_site.resolution)
        col_centre = int((25.0 - flat_site.origin_x) / flat_site.resolution)
        if 0 <= row_north < flat_site.rows:
            assert cov[row_north, col_centre], "Cell to north must be inside 90° north arc"

    def test_360_arc_does_not_restrict_coverage(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """360° arc should produce same result as no arc mask at all."""
        placement = _centre_placement(flat_site)
        cov = compute_single_effector_coverage(flat_site, rf_jammer, placement)
        # Coverage should exist in all directions
        assert cov.any()
        # South cell and north cell both covered if within range
        cx = 25.0
        cy = 25.0
        row_n = int((flat_site.origin_y - (cy + 10.0)) / flat_site.resolution)
        row_s = int((flat_site.origin_y - (cy - 10.0)) / flat_site.resolution)
        col_c = int((cx - flat_site.origin_x) / flat_site.resolution)
        if 0 <= row_n < flat_site.rows:
            assert cov[row_n, col_c], "North cell within range must be covered"
        if 0 <= row_s < flat_site.rows:
            assert cov[row_s, col_c], "South cell within range must be covered"


# ---------------------------------------------------------------------------
# Union (layer) tests
# ---------------------------------------------------------------------------


class TestEffectorLayerCoverage:
    def test_empty_list_returns_all_false(self, flat_site: SiteModel) -> None:
        """Empty effector list must return all-False array."""
        result = compute_effector_layer_coverage(flat_site, [])
        assert result.shape == (flat_site.rows, flat_site.cols)
        assert not result.any(), "Empty list must produce all-False layer"

    def test_union_covers_both_effectors(self, flat_site: SiteModel) -> None:
        """Union of two spatially separated effectors should cover both zones."""
        jammer_a = EffectorDefinition(
            name="JammerA",
            type=EffectorType.RF_Jammer,
            max_range_m=8.0,
            min_range_m=0.0,
            engagement_arc_deg=360.0,
            reaction_time_s=0.5,
            defeat_probability=0.9,
            requires_los=False,
            defeat_mechanism="RF jamming",
        )
        jammer_b = EffectorDefinition(
            name="JammerB",
            type=EffectorType.RF_Jammer,
            max_range_m=8.0,
            min_range_m=0.0,
            engagement_arc_deg=360.0,
            reaction_time_s=0.5,
            defeat_probability=0.9,
            requires_los=False,
            defeat_mechanism="RF jamming",
        )
        # Place A in northwest corner, B in southeast corner
        placement_a = EffectorPlacement(
            effector_name="JammerA", position_x=5.0, position_y=45.0, bearing_deg=0.0
        )
        placement_b = EffectorPlacement(
            effector_name="JammerB", position_x=45.0, position_y=5.0, bearing_deg=0.0
        )
        cov_a = compute_single_effector_coverage(flat_site, jammer_a, placement_a)
        cov_b = compute_single_effector_coverage(flat_site, jammer_b, placement_b)
        union = compute_effector_layer_coverage(
            flat_site, [(jammer_a, placement_a), (jammer_b, placement_b)]
        )

        # Union must be superset of both individual coverages
        assert np.all(union | ~cov_a), "Union must include all of A's coverage"
        assert np.all(union | ~cov_b), "Union must include all of B's coverage"
        assert union.sum() >= max(cov_a.sum(), cov_b.sum()), "Union >= largest single coverage"

    def test_single_effector_same_as_layer(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """Layer with one effector must equal single effector result."""
        placement = _centre_placement(flat_site)
        single = compute_single_effector_coverage(flat_site, rf_jammer, placement)
        layer = compute_effector_layer_coverage(flat_site, [(rf_jammer, placement)])
        np.testing.assert_array_equal(single, layer)


# ---------------------------------------------------------------------------
# Edge cases and error handling
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_non_finite_height_raises(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """Non-finite height_override_m must raise ValueError."""
        placement = EffectorPlacement(
            effector_name="test",
            position_x=25.0,
            position_y=25.0,
            bearing_deg=0.0,
            height_override_m=float("nan"),
        )
        with pytest.raises(ValueError, match="non-finite"):
            compute_single_effector_coverage(flat_site, rf_jammer, placement)

    def test_height_override_used_when_set(
        self, flat_site: SiteModel, kinetic_effector: EffectorDefinition
    ) -> None:
        """height_override_m=0.0 should work the same as no override on flat terrain."""
        placement_no_override = EffectorPlacement(
            effector_name="test",
            position_x=25.0,
            position_y=25.0,
            bearing_deg=0.0,
            height_override_m=None,
        )
        placement_zero_override = EffectorPlacement(
            effector_name="test",
            position_x=25.0,
            position_y=25.0,
            bearing_deg=0.0,
            height_override_m=0.0,
        )
        cov_none = compute_single_effector_coverage(
            flat_site, kinetic_effector, placement_no_override
        )
        cov_zero = compute_single_effector_coverage(
            flat_site, kinetic_effector, placement_zero_override
        )
        np.testing.assert_array_equal(cov_none, cov_zero)

    def test_non_finite_position_x_raises(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """Non-finite position_x must raise ValueError (D-193)."""
        placement = EffectorPlacement(
            effector_name="test",
            position_x=float("inf"),
            position_y=25.0,
            bearing_deg=0.0,
        )
        with pytest.raises(ValueError, match="finite"):
            compute_single_effector_coverage(flat_site, rf_jammer, placement)

    def test_non_finite_position_y_raises(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """Non-finite position_y must raise ValueError (D-193)."""
        placement = EffectorPlacement(
            effector_name="test",
            position_x=25.0,
            position_y=float("nan"),
            bearing_deg=0.0,
        )
        with pytest.raises(ValueError, match="finite"):
            compute_single_effector_coverage(flat_site, rf_jammer, placement)

    def test_zero_resolution_raises(self, rf_jammer: EffectorDefinition) -> None:
        """site.resolution=0 must raise ValueError — now caught by SiteModel validation."""
        with pytest.raises(ValueError, match="resolution"):
            SiteModel(
                dem=np.full((10, 10), 50.0),
                resolution=0.0,
                origin_x=0.0,
                origin_y=10.0,
            )

    def test_empty_effector_list_warns(
        self, flat_site: SiteModel, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Empty effector list must emit a WARNING log (D-196)."""
        import logging

        with caplog.at_level(logging.WARNING, logger="salus.engine.effector_coverage"):
            result = compute_effector_layer_coverage(flat_site, [])
        assert not result.any(), "Empty list must produce all-False layer"
        assert any("no effectors" in r.message.lower() for r in caplog.records), (
            "Expected a warning log for empty effector list"
        )

    def test_layer_catches_per_effector_error(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """RuntimeError from a failing effector must include the effector name (D-195).

        rf_jammer has name='TestJammer'; a bad placement triggers a ValueError which
        compute_effector_layer_coverage wraps into a RuntimeError naming the effector.
        """
        bad_placement = EffectorPlacement(
            effector_name="TestJammer",
            position_x=float("nan"),
            position_y=25.0,
            bearing_deg=0.0,
        )
        with pytest.raises(RuntimeError, match="TestJammer"):
            compute_effector_layer_coverage(flat_site, [(rf_jammer, bad_placement)])

    def test_coverage_shape_matches_site(
        self, flat_site: SiteModel, rf_jammer: EffectorDefinition
    ) -> None:
        """Coverage array shape must match site dimensions."""
        placement = _centre_placement(flat_site)
        cov = compute_single_effector_coverage(flat_site, rf_jammer, placement)
        assert cov.shape == (flat_site.rows, flat_site.cols)
        assert cov.dtype == bool
