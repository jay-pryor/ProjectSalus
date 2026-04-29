"""Tests for clip_viewshed_to_sensor — range and azimuth masking."""

from __future__ import annotations

import numpy as np
import pytest

from salus.engine.viewshed import clip_viewshed_to_sensor
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.models.site import SiteModel

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RESOLUTION = 1.0  # 1 m per cell
ROWS, COLS = 100, 100
ORIGIN_X = 0.0
ORIGIN_Y = float(ROWS)  # top-left cell at y=100; cell (r,c) → y = 100 - r


@pytest.fixture
def flat_site() -> SiteModel:
    """100×100 site, 1 m resolution, origin at (0, 100)."""
    dem = np.zeros((ROWS, COLS), dtype=float)
    return SiteModel(dem=dem, resolution=RESOLUTION, origin_x=ORIGIN_X, origin_y=ORIGIN_Y)


@pytest.fixture
def all_visible(flat_site: SiteModel) -> np.ndarray:
    """Viewshed with every cell visible."""
    return np.ones((flat_site.rows, flat_site.cols), dtype=bool)


def _sensor(
    *,
    max_range_m: float = 50.0,
    min_range_m: float = 0.0,
    azimuth_coverage_deg: float = 360.0,
) -> SensorDefinition:
    return SensorDefinition(
        name="Test Sensor",
        type=SensorType.RF,
        max_range_m=max_range_m,
        min_range_m=min_range_m,
        azimuth_coverage_deg=azimuth_coverage_deg,
        elevation_coverage_deg=90.0,
    )


def _placement(
    *,
    x: float = 50.0,
    y: float = 50.0,
    bearing_deg: float = 0.0,
) -> SensorPlacement:
    return SensorPlacement(
        sensor_name="Test Sensor",
        position_x=x,
        position_y=y,
        bearing_deg=bearing_deg,
    )


# ---------------------------------------------------------------------------
# Range masking
# ---------------------------------------------------------------------------


class TestRangeMask:
    def test_full_arc_clips_beyond_max_range(self, flat_site, all_visible):
        """Cells further than max_range_m must be False."""
        sensor = _sensor(max_range_m=20.0)
        placement = _placement(x=50.0, y=50.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell at (r=0, c=0) → x=0, y=100; dist from (50,50) ≈ 70.7 m > 20 m
        assert clipped[0, 0] is np.False_

    def test_cells_within_max_range_retained(self, flat_site, all_visible):
        """Cells within max_range_m are not removed by the range mask."""
        sensor = _sensor(max_range_m=50.0)
        placement = _placement(x=50.0, y=50.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell at (r=50, c=50) → x=50, y=50; dist=0 <= 50 m
        assert clipped[50, 50] is np.True_

    def test_min_range_creates_dead_zone(self, flat_site, all_visible):
        """Cells closer than min_range_m must be False."""
        sensor = _sensor(max_range_m=50.0, min_range_m=10.0)
        placement = _placement(x=50.0, y=50.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell at exact placement position → dist=0 < 10 m (in dead zone)
        assert clipped[50, 50] is np.False_

    def test_cells_at_max_range_boundary_included(self, flat_site, all_visible):
        """A cell exactly at max_range_m distance is included (boundary inclusive)."""
        max_r = 30.0
        sensor = _sensor(max_range_m=max_r)
        # Place sensor at (50, 50); cell directly north at (r=20, c=50) →
        # cell coords: x=50, y=80; dy = 80-50 = 30 = max_r exactly
        placement = _placement(x=50.0, y=50.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        assert clipped[20, 50] is np.True_

    def test_output_shape_matches_input(self, flat_site, all_visible):
        """Output shape must equal input viewshed shape."""
        sensor = _sensor()
        placement = _placement()

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        assert clipped.shape == all_visible.shape

    def test_already_false_cells_stay_false(self, flat_site):
        """Cells that were False in the input viewshed remain False after clipping."""
        viewshed = np.zeros((flat_site.rows, flat_site.cols), dtype=bool)
        sensor = _sensor(max_range_m=50.0)
        placement = _placement(x=50.0, y=50.0)

        clipped = clip_viewshed_to_sensor(viewshed, flat_site, sensor, placement)

        assert not clipped.any()


# ---------------------------------------------------------------------------
# Azimuth masking
# ---------------------------------------------------------------------------


class TestAzimuthMask:
    def test_360_arc_no_azimuth_clipping(self, flat_site, all_visible):
        """A 360° sensor arc does not remove any cells that passed the range mask."""
        sensor = _sensor(max_range_m=50.0, azimuth_coverage_deg=360.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=0.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Sensor at (50,50), max 50 m — ring of cells exactly 40 m north should survive
        assert clipped[10, 50] is np.True_  # r=10,c=50 → x=50,y=90; dist=40 m, in 360° arc

    def test_90_arc_north_clips_east_cells(self, flat_site, all_visible):
        """A 90° arc facing north (bearing=0) should exclude cells to the east."""
        sensor = _sensor(max_range_m=40.0, azimuth_coverage_deg=90.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=0.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell directly east at (r=50, c=80) → bearing from sensor = 90°
        # 90° is exactly at the arc boundary (±45° from boresight=0°); excluded
        assert clipped[50, 80] is np.False_

    def test_90_arc_north_retains_north_cells(self, flat_site, all_visible):
        """A 90° arc facing north retains cells directly ahead."""
        sensor = _sensor(max_range_m=40.0, azimuth_coverage_deg=90.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=0.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell directly north: (r=20, c=50) → bearing=0°, in arc
        assert clipped[20, 50] is np.True_

    def test_bearing_90_east_retains_east_cells(self, flat_site, all_visible):
        """A 90° arc facing east (bearing=90) should retain cells due east."""
        sensor = _sensor(max_range_m=40.0, azimuth_coverage_deg=90.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=90.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell directly east: (r=50, c=80) → bearing=90°, in arc
        assert clipped[50, 80] is np.True_

    def test_bearing_90_east_clips_north_cells(self, flat_site, all_visible):
        """A 90° arc facing east should exclude cells due north (outside arc)."""
        sensor = _sensor(max_range_m=40.0, azimuth_coverage_deg=90.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=90.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell due north: (r=20, c=50) → bearing=0°, 90° away from boresight → outside
        assert clipped[20, 50] is np.False_

    def test_bearing_270_west_retains_west_cells(self, flat_site, all_visible):
        """A 90° arc facing west (bearing=270) should retain cells due west."""
        sensor = _sensor(max_range_m=40.0, azimuth_coverage_deg=90.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=270.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell directly west: (r=50, c=20) → bearing=270°, in arc
        assert clipped[50, 20] is np.True_

    def test_180_arc_facing_north_clips_south(self, flat_site, all_visible):
        """A 180° arc facing north should not include cells directly south."""
        sensor = _sensor(max_range_m=40.0, azimuth_coverage_deg=180.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=0.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell directly south: (r=80, c=50) → bearing=180°, at boundary (±90°) → excluded
        assert clipped[80, 50] is np.False_

    def test_wrap_around_bearing_near_north(self, flat_site, all_visible):
        """Arc centred just west of north wraps correctly across 0/360 boundary."""
        # bearing=350° → arc spans [305°, 395°] ≡ [305°, 360°) ∪ [0°, 35°)
        sensor = _sensor(max_range_m=40.0, azimuth_coverage_deg=90.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=350.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell due north (bearing=0°) is 10° from boresight — inside arc
        assert clipped[20, 50] is np.True_
        # Cell due east (bearing=90°) is 100° from boresight — outside arc
        assert clipped[50, 80] is np.False_


# ---------------------------------------------------------------------------
# Input validation guards
# ---------------------------------------------------------------------------


class TestInputGuards:
    def test_non_2d_viewshed_raises(self, flat_site, all_visible):
        """A 1D viewshed array must raise ValueError with a clear message."""
        bad_array = np.ones(100, dtype=bool)
        sensor = _sensor()
        placement = _placement()

        with pytest.raises(ValueError, match="2D"):
            clip_viewshed_to_sensor(bad_array, flat_site, sensor, placement)

    def test_zero_resolution_raises(self, all_visible):
        """site.resolution == 0.0 must raise ValueError — now caught by SiteModel validation."""
        with pytest.raises(ValueError, match="resolution"):
            SiteModel(
                dem=np.zeros((ROWS, COLS), dtype=float),
                resolution=0.0,
                origin_x=ORIGIN_X,
                origin_y=ORIGIN_Y,
            )

    def test_integer_viewshed_array_normalised_to_bool(self, flat_site):
        """Passing an integer array (e.g. from raw GDAL read) must not silently corrupt results."""
        integer_array = np.ones((flat_site.rows, flat_site.cols), dtype=np.int32)
        sensor = _sensor(max_range_m=50.0)
        placement = _placement(x=50.0, y=50.0)

        clipped = clip_viewshed_to_sensor(integer_array, flat_site, sensor, placement)

        assert clipped.dtype == bool


# ---------------------------------------------------------------------------
# Combined range + azimuth
# ---------------------------------------------------------------------------


class TestCombinedMask:
    def test_cell_must_satisfy_both_range_and_azimuth(self, flat_site, all_visible):
        """A cell in range but outside the arc must be False."""
        sensor = _sensor(max_range_m=40.0, azimuth_coverage_deg=90.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=0.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell at (r=50, c=80): dist≈30 m (in range) but bearing=90° (outside 90° north arc)
        assert clipped[50, 80] is np.False_

    def test_cell_in_arc_but_beyond_max_range_is_false(self, flat_site, all_visible):
        """A cell in the correct azimuth but beyond max_range must be False."""
        sensor = _sensor(max_range_m=20.0, azimuth_coverage_deg=90.0)
        placement = _placement(x=50.0, y=50.0, bearing_deg=0.0)

        clipped = clip_viewshed_to_sensor(all_visible, flat_site, sensor, placement)

        # Cell due north at r=10: dist=40 m > 20 m max_range
        assert clipped[10, 50] is np.False_
