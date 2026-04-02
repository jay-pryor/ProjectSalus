"""Tests for engine/trajectory.py — sensor_can_detect_point."""

from __future__ import annotations

import math

import pytest

from salus.engine.trajectory import sensor_can_detect_point
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _sensor(**overrides) -> SensorDefinition:
    """Return a valid omni radar sensor, with optional field overrides."""
    base: dict = {
        "name": "Test Radar",
        "type": SensorType.Radar,
        "max_range_m": 5000.0,
        "min_range_m": 10.0,
        "azimuth_coverage_deg": 360.0,
        "elevation_coverage_deg": 90.0,
        "elevation_boresight_deg": 0.0,
        "requires_los": True,
        "mounting_height_m": 0.0,
    }
    base.update(overrides)
    return SensorDefinition(**base)


def _placement(site, *, col: int = 50, row: int = 50, bearing: float = 0.0) -> SensorPlacement:
    """Place sensor at a specific grid cell."""
    x = site.origin_x + col * site.resolution
    y = site.origin_y - row * site.resolution
    return SensorPlacement(
        sensor_name="Test Radar",
        position_x=x,
        position_y=y,
        bearing_deg=bearing,
    )


# ---------------------------------------------------------------------------
# LOS gating
# ---------------------------------------------------------------------------


class TestLOSGating:
    def test_unobstructed_flat_terrain_detects(self, flat_dem_path):
        """Clear LOS on flat terrain → detected."""
        site = load_dem(flat_dem_path)
        sensor = _sensor()
        pl = _placement(site, col=10, row=10)
        # Target 20 cells away at 10 m AGL
        tx = site.origin_x + 30 * site.resolution
        ty = site.origin_y - 10 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 10.0) is True

    def test_ridge_blocks_los_returns_false(self, ridge_dem_path):
        """Ridge between sensor and target → False when requires_los=True."""
        site = load_dem(ridge_dem_path)
        sensor = _sensor(max_range_m=500.0)
        pl = _placement(site, col=10, row=10)
        # Target on far side of ridge (row 190)
        tx = site.origin_x + 10 * site.resolution
        ty = site.origin_y - 190 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 0.0) is False

    def test_requires_los_false_ignores_ridge(self, ridge_dem_path):
        """RF sensor (requires_los=False) detects across ridge."""
        site = load_dem(ridge_dem_path)
        sensor = _sensor(
            type=SensorType.RF,
            max_range_m=500.0,
            requires_los=False,
            elevation_coverage_deg=180.0,
        )
        pl = _placement(site, col=10, row=10)
        tx = site.origin_x + 10 * site.resolution
        ty = site.origin_y - 190 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 0.0) is True

    def test_elevated_target_clears_ridge(self, ridge_dem_path):
        """Target elevated above ridge is detected despite ridge."""
        site = load_dem(ridge_dem_path)
        # Wide elevation arc so the high-angle target is not gated out.
        # Sensor at row=10, target at row=190 → 180 m apart; target 250 m AGL
        # → elevation angle ≈ 59°. Use 180° arc to include it.
        sensor = _sensor(max_range_m=500.0, elevation_coverage_deg=180.0)
        pl = _placement(site, col=10, row=10)
        tx = site.origin_x + 10 * site.resolution
        ty = site.origin_y - 190 * site.resolution
        # Target at 250 m AGL (absolute ~300 m) clears 150 m ridge
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 250.0) is True


# ---------------------------------------------------------------------------
# Range gating
# ---------------------------------------------------------------------------


class TestRangeGating:
    def test_within_range_detects(self, flat_dem_path):
        """Target well within max_range_m → detected."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(min_range_m=1.0, max_range_m=200.0)
        pl = _placement(site, col=10, row=50)
        tx = site.origin_x + 20 * site.resolution  # 10 m away
        ty = site.origin_y - 50 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 0.0) is True

    def test_beyond_max_range_not_detected(self, flat_dem_path):
        """Target beyond max_range_m → False."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(min_range_m=1.0, max_range_m=5.0)
        pl = _placement(site, col=10, row=50)
        tx = site.origin_x + 50 * site.resolution  # 40 m away
        ty = site.origin_y - 50 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 0.0) is False

    def test_within_min_range_not_detected(self, flat_dem_path):
        """Target inside dead zone (< min_range_m) → False."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(min_range_m=100.0, max_range_m=5000.0)
        pl = _placement(site, col=50, row=50)
        # Sensor and target at same cell — slant range ≈ 0 < min_range_m
        tx = site.origin_x + 51 * site.resolution  # 1 m away
        ty = site.origin_y - 50 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 0.0) is False


# ---------------------------------------------------------------------------
# Azimuth gating
# ---------------------------------------------------------------------------


class TestAzimuthGating:
    def test_omni_sensor_detects_any_bearing(self, flat_dem_path):
        """360° azimuth coverage detects in all directions."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(azimuth_coverage_deg=360.0, max_range_m=200.0)
        pl = _placement(site, col=50, row=50, bearing=0.0)
        # Target to the south
        tx = site.origin_x + 50 * site.resolution
        ty = site.origin_y - 80 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 5.0) is True

    def test_sector_sensor_detects_within_arc(self, flat_dem_path):
        """Target within 90° arc centred north → detected."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(azimuth_coverage_deg=90.0, max_range_m=200.0)
        pl = _placement(site, col=50, row=50, bearing=0.0)
        # Target directly north (bearing 0° from sensor) — within ±45°
        tx = site.origin_x + 50 * site.resolution
        ty = site.origin_y - 20 * site.resolution  # north
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 5.0) is True

    def test_sector_sensor_misses_outside_arc(self, flat_dem_path):
        """Target outside azimuth arc → False."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(azimuth_coverage_deg=90.0, max_range_m=200.0)
        pl = _placement(site, col=50, row=50, bearing=0.0)  # boresight north
        # Target to the south — bearing 180° from sensor, outside ±45° arc
        tx = site.origin_x + 50 * site.resolution
        ty = site.origin_y - 80 * site.resolution  # south
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 5.0) is False


# ---------------------------------------------------------------------------
# Elevation gating
# ---------------------------------------------------------------------------


class TestElevationGating:
    def test_target_within_elevation_arc_detected(self, flat_dem_path):
        """Target at elevation angle within sensor arc → detected."""
        site = load_dem(flat_dem_path)
        # Arc: boresight 0°, coverage 90° → covers -45° to +45°
        sensor = _sensor(
            elevation_boresight_deg=0.0,
            elevation_coverage_deg=90.0,
            max_range_m=1000.0,
        )
        pl = _placement(site, col=10, row=50)
        # Target 30 m away horizontally, 30 m above sensor → elevation ~45°
        tx = site.origin_x + 40 * site.resolution
        ty = site.origin_y - 50 * site.resolution
        # Target AGL chosen so elevation angle < 45°
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 5.0) is True

    def test_target_above_elevation_arc_not_detected(self, flat_dem_path):
        """Target elevation angle above arc → False."""
        site = load_dem(flat_dem_path)
        # Arc: boresight 0°, coverage 10° → covers -5° to +5°
        sensor = _sensor(
            elevation_boresight_deg=0.0,
            elevation_coverage_deg=10.0,
            max_range_m=1000.0,
        )
        pl = _placement(site, col=10, row=50)
        # Target 5 m away, 50 m above sensor → elevation ~84° — far above arc
        tx = site.origin_x + 15 * site.resolution
        ty = site.origin_y - 50 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 50.0) is False

    def test_target_below_elevation_arc_not_detected(self, flat_dem_path):
        """Target elevation angle below arc → False."""
        site = load_dem(flat_dem_path)
        # Arc: boresight +30°, coverage 10° → covers +25° to +35°
        sensor = _sensor(
            elevation_boresight_deg=30.0,
            elevation_coverage_deg=10.0,
            max_range_m=1000.0,
        )
        pl = _placement(site, col=10, row=50)
        # Target far away at ground level → elevation near 0° < +25°
        tx = site.origin_x + 50 * site.resolution
        ty = site.origin_y - 50 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 0.0) is False

    def test_elevation_boresight_default_zero(self, flat_dem_path):
        """Sensor with default elevation_boresight_deg=0 accepts horizontal targets."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(
            elevation_coverage_deg=30.0,
            max_range_m=200.0,
        )
        pl = _placement(site, col=10, row=50)
        # Target at same height as sensor — elevation angle = 0° → within ±15°
        tx = site.origin_x + 25 * site.resolution
        ty = site.origin_y - 50 * site.resolution
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 0.0) is True


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------


class TestBoundaryConditions:
    def test_target_outside_dem_returns_false(self, flat_dem_path):
        """Target outside DEM extent → False (not ValueError)."""
        site = load_dem(flat_dem_path)
        sensor = _sensor()
        pl = _placement(site, col=50, row=50)
        assert sensor_can_detect_point(site, sensor, pl, 0.0, 0.0, 0.0) is False

    def test_sensor_outside_dem_raises(self, flat_dem_path):
        """Sensor placed outside DEM → ValueError."""
        site = load_dem(flat_dem_path)
        sensor = _sensor()
        pl = SensorPlacement(
            sensor_name="Test Radar",
            position_x=0.0,
            position_y=0.0,
            bearing_deg=0.0,
        )
        with pytest.raises(ValueError, match="outside the site DEM"):
            sensor_can_detect_point(site, sensor, pl, site.origin_x + 50, site.origin_y - 50, 0.0)

    def test_non_finite_tz_agl_raises(self, flat_dem_path):
        """Non-finite tz_agl raises ValueError."""
        site = load_dem(flat_dem_path)
        sensor = _sensor()
        pl = _placement(site)
        tx = site.origin_x + 60 * site.resolution
        ty = site.origin_y - 50 * site.resolution
        with pytest.raises(ValueError, match="finite"):
            sensor_can_detect_point(site, sensor, pl, tx, ty, math.nan)

    def test_height_override_used_over_mounting_height(self, flat_dem_path):
        """placement.height_override_m takes precedence over sensor.mounting_height_m."""
        site = load_dem(flat_dem_path)
        # Sensor with tall mounting height but override of 0 — same elevation as ground
        sensor = _sensor(
            mounting_height_m=50.0,
            elevation_coverage_deg=10.0,
            elevation_boresight_deg=0.0,
            max_range_m=200.0,
        )
        pl = SensorPlacement(
            sensor_name="Test Radar",
            position_x=site.origin_x + 10 * site.resolution,
            position_y=site.origin_y - 50 * site.resolution,
            bearing_deg=0.0,
            height_override_m=0.0,  # override: sensor at ground level
        )
        # Target at same height (0 AGL) horizontally — elevation angle = 0°
        tx = site.origin_x + 30 * site.resolution
        ty = site.origin_y - 50 * site.resolution
        # With override=0, sensor at 50m absolute. Target at 50m absolute.
        # Elevation = 0° → within ±5° arc → True
        assert sensor_can_detect_point(site, sensor, pl, tx, ty, 0.0) is True
