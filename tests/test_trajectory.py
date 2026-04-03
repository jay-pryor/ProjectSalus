"""Tests for engine/trajectory.py — sensor_can_detect_point, DetectionEvent,
TrajectoryResult, and analyse_trajectory."""

from __future__ import annotations

import math

import numpy as np
import pytest

from salus.engine.trajectory import (
    DetectionEvent,
    TrajectoryResult,
    analyse_trajectory,
    find_worst_trajectories,
    sensor_can_detect_point,
)
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.models.site import SiteModel
from salus.models.threat import DroneTrajectory, ThreatProfile, TrajectoryWaypoint

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


# ---------------------------------------------------------------------------
# DetectionEvent and TrajectoryResult dataclass tests (S6.3-1)
# ---------------------------------------------------------------------------


class TestDetectionEvent:
    def test_construction(self):
        evt = DetectionEvent(
            sensor_name="Radar A",
            time_s=3.5,
            position_x=500050.0,
            position_y=6100050.0,
            position_z_agl=20.0,
            distance_to_asset_m=150.0,
            segment_index=0,
        )
        assert evt.sensor_name == "Radar A"
        assert evt.time_s == pytest.approx(3.5)
        assert evt.segment_index == 0

    def test_frozen(self):
        evt = DetectionEvent(
            sensor_name="X",
            time_s=1.0,
            position_x=0.0,
            position_y=0.0,
            position_z_agl=10.0,
            distance_to_asset_m=50.0,
            segment_index=0,
        )
        with pytest.raises((AttributeError, TypeError)):
            evt.time_s = 2.0  # type: ignore[misc]

    def test_zero_time_allowed(self):
        evt = DetectionEvent(
            sensor_name="X",
            time_s=0.0,
            position_x=0.0,
            position_y=0.0,
            position_z_agl=0.0,
            distance_to_asset_m=0.0,
            segment_index=0,
        )
        assert evt.time_s == 0.0


class TestTrajectoryResult:
    def test_construction_with_no_events(self):
        result = TrajectoryResult(
            detection_events=(),
            first_detection=None,
            time_to_asset_s=10.0,
            time_in_detection_s=0.0,
            time_undetected_s=10.0,
            asset_reached_undetected=True,
            last_gap_before_asset_m=100.0,
        )
        assert result.first_detection is None
        assert result.asset_reached_undetected is True
        assert len(result.detection_events) == 0

    def test_construction_with_events(self):
        evt = DetectionEvent(
            sensor_name="A",
            time_s=2.0,
            position_x=1.0,
            position_y=2.0,
            position_z_agl=5.0,
            distance_to_asset_m=80.0,
            segment_index=0,
        )
        result = TrajectoryResult(
            detection_events=(evt,),
            first_detection=evt,
            time_to_asset_s=10.0,
            time_in_detection_s=8.0,
            time_undetected_s=2.0,
            asset_reached_undetected=False,
            last_gap_before_asset_m=0.0,
        )
        assert result.first_detection is evt
        assert result.asset_reached_undetected is False

    def test_frozen(self):
        result = TrajectoryResult(
            detection_events=(),
            first_detection=None,
            time_to_asset_s=5.0,
            time_in_detection_s=0.0,
            time_undetected_s=5.0,
            asset_reached_undetected=True,
            last_gap_before_asset_m=50.0,
        )
        with pytest.raises((AttributeError, TypeError)):
            result.time_to_asset_s = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# analyse_trajectory tests (S6.3-2)
# ---------------------------------------------------------------------------


def _omni_sensor(**overrides) -> SensorDefinition:
    base: dict = {
        "name": "Omni Radar",
        "type": SensorType.Radar,
        "max_range_m": 5000.0,
        "min_range_m": 1.0,
        "azimuth_coverage_deg": 360.0,
        "elevation_coverage_deg": 180.0,
        "elevation_boresight_deg": 0.0,
        "requires_los": False,  # non-LOS for simplicity in trajectory tests
        "mounting_height_m": 5.0,
    }
    base.update(overrides)
    return SensorDefinition(**base)


def _make_placement(site, col: int, row: int) -> SensorPlacement:
    x = site.origin_x + col * site.resolution
    y = site.origin_y - row * site.resolution
    return SensorPlacement(sensor_name="Omni Radar", position_x=x, position_y=y, bearing_deg=0.0)


def _straight_trajectory(
    site,
    start_col: int,
    start_row: int,
    end_col: int,
    end_row: int,
    z_agl: float = 10.0,
    speed: float = 10.0,
) -> DroneTrajectory:
    """Build a two-waypoint trajectory along the grid."""
    return DroneTrajectory(
        waypoints=[
            TrajectoryWaypoint(
                x=site.origin_x + start_col * site.resolution,
                y=site.origin_y - start_row * site.resolution,
                z_agl=z_agl,
            ),
            TrajectoryWaypoint(
                x=site.origin_x + end_col * site.resolution,
                y=site.origin_y - end_row * site.resolution,
                z_agl=z_agl,
            ),
        ],
        speed_ms=speed,
    )


class TestAnalyseTrajectoryFullyUndetected:
    """No sensor → drone reaches asset undetected."""

    def test_no_sensors_no_events(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        traj = _straight_trajectory(site, 0, 50, 99, 50)
        result = analyse_trajectory(site, [], traj, segment_length_m=1.0)
        assert result.asset_reached_undetected is True
        assert result.first_detection is None
        assert len(result.detection_events) == 0

    def test_no_sensors_time_to_asset_positive(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        result = analyse_trajectory(site, [], traj)
        assert result.time_to_asset_s > 0.0

    def test_no_sensors_time_undetected_equals_time_to_asset(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        result = analyse_trajectory(site, [], traj)
        assert result.time_in_detection_s == pytest.approx(0.0)
        assert result.time_undetected_s == pytest.approx(result.time_to_asset_s)

    def test_no_sensors_last_gap_equals_trajectory_length(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        result = analyse_trajectory(site, [], traj)
        expected = result.time_to_asset_s * 10.0  # length = time * speed
        assert result.last_gap_before_asset_m == pytest.approx(expected, rel=0.05)

    def test_sensor_out_of_range_no_events(self, flat_dem_path):
        """Sensor far from trajectory → not detected."""
        site = load_dem(flat_dem_path)
        sensor = _omni_sensor(max_range_m=5.0)  # tiny range
        placement = _make_placement(site, col=50, row=50)
        # Trajectory far from sensor at col=50
        traj = _straight_trajectory(site, 0, 0, 10, 0, z_agl=10.0, speed=10.0)
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=1.0)
        assert result.asset_reached_undetected is True


class TestAnalyseTrajectoryFullyDetected:
    """Sensor with huge range covers entire trajectory."""

    def test_all_in_detection_no_undetected_gap(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _omni_sensor(max_range_m=5000.0)
        # Sensor at centre
        placement = _make_placement(site, col=50, row=50)
        # Short trajectory fully within sensor range
        traj = _straight_trajectory(site, 40, 50, 60, 50, speed=10.0)
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=1.0)
        assert result.last_gap_before_asset_m == pytest.approx(0.0, abs=1.0)
        assert result.time_in_detection_s == pytest.approx(result.time_to_asset_s, rel=0.05)

    def test_asset_reached_not_undetected(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _omni_sensor(max_range_m=5000.0)
        placement = _make_placement(site, col=50, row=50)
        traj = _straight_trajectory(site, 40, 50, 60, 50, speed=10.0)
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=1.0)
        assert result.asset_reached_undetected is False

    def test_time_in_detection_positive(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        sensor = _omni_sensor(max_range_m=5000.0)
        placement = _make_placement(site, col=50, row=50)
        traj = _straight_trajectory(site, 40, 50, 60, 50, speed=10.0)
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=1.0)
        assert result.time_in_detection_s > 0.0


class TestAnalyseTrajectoryDetectionMidPath:
    """Sensor covers only part of the trajectory."""

    def test_detection_mid_path_has_event(self, flat_dem_path):
        """Drone enters sensor range partway through trajectory."""
        site = load_dem(flat_dem_path)
        # Sensor with 30m range at col=80
        sensor = _omni_sensor(max_range_m=30.0, min_range_m=0.5)
        placement = _make_placement(site, col=80, row=50)
        # Trajectory from col=0 to col=99 (left to right) at row=50
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=1.0)
        # Drone should enter detection range at some point
        assert not result.asset_reached_undetected
        assert result.first_detection is not None
        assert result.first_detection.distance_to_asset_m > 0.0

    def test_first_detection_distance_reasonable(self, flat_dem_path):
        """Detection occurs when drone enters the 30m sensor bubble.

        Sensor at col=80, asset at col=99 (19m past sensor).  The drone
        enters range at ~col=50 (30m before the sensor), which is ~49m
        from the asset at col=99.  distance_to_asset_m should be between
        0 and start_distance (99m).
        """
        site = load_dem(flat_dem_path)
        sensor = _omni_sensor(max_range_m=30.0, min_range_m=0.5)
        placement = _make_placement(site, col=80, row=50)
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=1.0)
        if result.first_detection:
            # distance_to_asset_m must be positive and within the trajectory length
            assert 0.0 < result.first_detection.distance_to_asset_m < 99.0

    def test_time_undetected_positive(self, flat_dem_path):
        """Partial coverage → some undetected time."""
        site = load_dem(flat_dem_path)
        sensor = _omni_sensor(max_range_m=30.0, min_range_m=0.5)
        placement = _make_placement(site, col=80, row=50)
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=1.0)
        assert result.time_undetected_s > 0.0

    def test_segment_index_valid(self, flat_dem_path):
        """DetectionEvent.segment_index is a valid trajectory segment index."""
        site = load_dem(flat_dem_path)
        sensor = _omni_sensor(max_range_m=30.0, min_range_m=0.5)
        placement = _make_placement(site, col=80, row=50)
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=1.0)
        n_segments = len(traj.waypoints) - 1
        for evt in result.detection_events:
            assert 0 <= evt.segment_index < n_segments


class TestAnalyseTrajectoryTerrainMasking:
    """Terrain blocks detection; drone detected only after clearing the ridge."""

    def test_ridge_blocks_detection_initially(self, ridge_dem_path):
        """LOS sensor cannot detect drone on far side of ridge."""
        site = load_dem(ridge_dem_path)
        # LOS sensor at row=10, col=10
        sensor = _omni_sensor(max_range_m=300.0, requires_los=True)
        placement = SensorPlacement(
            sensor_name="Omni Radar",
            position_x=site.origin_x + 10 * site.resolution,
            position_y=site.origin_y - 10 * site.resolution,
            bearing_deg=0.0,
        )
        # Trajectory from far side of ridge (row=180) to near sensor (row=20)
        # at 5m AGL — ridge at rows 95-105 (peak=150m) blocks LOS at ground
        traj = DroneTrajectory(
            waypoints=[
                TrajectoryWaypoint(
                    x=site.origin_x + 10 * site.resolution,
                    y=site.origin_y - 180 * site.resolution,
                    z_agl=5.0,
                ),
                TrajectoryWaypoint(
                    x=site.origin_x + 10 * site.resolution,
                    y=site.origin_y - 20 * site.resolution,
                    z_agl=5.0,
                ),
            ],
            speed_ms=10.0,
        )
        result = analyse_trajectory(site, [(sensor, placement)], traj, segment_length_m=2.0)
        # Ridge should block detection for part of the trajectory
        if result.first_detection is not None:
            # Detection event should occur near the sensor (after clearing ridge)
            assert result.first_detection.distance_to_asset_m < 120.0

    def test_invalid_segment_length_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        with pytest.raises(ValueError, match="segment_length_m"):
            analyse_trajectory(site, [], traj, segment_length_m=0.0)

    def test_negative_segment_length_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        traj = _straight_trajectory(site, 0, 50, 99, 50, speed=10.0)
        with pytest.raises(ValueError, match="segment_length_m"):
            analyse_trajectory(site, [], traj, segment_length_m=-1.0)


# ---------------------------------------------------------------------------
# find_worst_trajectories tests (S6.4-1)
# ---------------------------------------------------------------------------

# 100×100 flat DEM constants (same as test_threat_corridor)
_FWT_ROWS: int = 100
_FWT_COLS: int = 100
_FWT_RESOLUTION: float = 10.0
_FWT_ORIGIN_X: float = 500000.0
_FWT_ORIGIN_Y: float = 6100000.0


def _fwt_site() -> SiteModel:
    """100×100 flat DEM at 10 m resolution."""
    dem = np.full((_FWT_ROWS, _FWT_COLS), 50.0)
    return SiteModel(
        dem=dem,
        resolution=_FWT_RESOLUTION,
        origin_x=_FWT_ORIGIN_X,
        origin_y=_FWT_ORIGIN_Y,
    )


def _fwt_threat(typical_altitude_m: float = 50.0, max_speed_ms: float = 20.0) -> ThreatProfile:
    return ThreatProfile(
        name="FWT Threat",
        rcs_m2=0.01,
        rf_signature="2.4 GHz",
        max_speed_ms=max_speed_ms,
        typical_altitude_m=typical_altitude_m,
    )


class TestFindWorstTrajectories:
    """Tests for find_worst_trajectories (S6.4-1)."""

    def test_single_bearing_returns_one_result(self):
        """num_bearings=1 with one altitude and one dive angle → exactly 1 result."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        results = find_worst_trajectories(
            site,
            [],
            threat,
            protected_point=(px, py),
            num_bearings=1,
        )
        assert len(results) == 1

    def test_full_sweep_count(self):
        """Result count equals num_bearings × len(altitudes) × len(dive_angles)."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        num_bearings = 8
        altitudes = [30.0, 60.0]
        dive_angles = [0.0, -30.0]
        results = find_worst_trajectories(
            site,
            [],
            threat,
            protected_point=(px, py),
            num_bearings=num_bearings,
            altitudes_m=altitudes,
            dive_angles_deg=dive_angles,
        )
        assert len(results) == num_bearings * len(altitudes) * len(dive_angles)

    def test_default_altitudes_uses_threat_altitude(self):
        """altitudes_m=None defaults to [threat.typical_altitude_m]."""
        site = _fwt_site()
        threat = _fwt_threat(typical_altitude_m=75.0)
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        results = find_worst_trajectories(
            site,
            [],
            threat,
            protected_point=(px, py),
            num_bearings=4,
        )
        # 4 bearings × 1 altitude × 1 dive angle = 4
        assert len(results) == 4

    def test_worst_has_lowest_time_in_detection(self):
        """First result has the lowest time_in_detection_s across all results."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        # Sensor with limited range — some bearings will be partially undetected
        sensor = _omni_sensor(max_range_m=150.0, min_range_m=1.0)
        placement = _make_placement(site, col=50, row=50)
        results = find_worst_trajectories(
            site,
            [(sensor, placement)],
            threat,
            protected_point=(px, py),
            num_bearings=8,
        )
        assert len(results) == 8
        min_det = min(r.time_in_detection_s for r in results)
        assert results[0].time_in_detection_s == pytest.approx(min_det)

    def test_sorted_ascending_by_time_in_detection(self):
        """Results are sorted by time_in_detection_s ascending."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        sensor = _omni_sensor(max_range_m=150.0, min_range_m=1.0)
        placement = _make_placement(site, col=50, row=50)
        results = find_worst_trajectories(
            site,
            [(sensor, placement)],
            threat,
            protected_point=(px, py),
            num_bearings=12,
        )
        for i in range(len(results) - 1):
            assert results[i].time_in_detection_s <= results[i + 1].time_in_detection_s

    def test_no_sensors_all_undetected(self):
        """With no sensors, all results have time_in_detection_s=0 and undetected=True."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        results = find_worst_trajectories(
            site,
            [],
            threat,
            protected_point=(px, py),
            num_bearings=4,
        )
        for r in results:
            assert r.time_in_detection_s == pytest.approx(0.0)
            assert r.asset_reached_undetected is True

    def test_num_bearings_zero_raises(self):
        """num_bearings=0 raises ValueError."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        with pytest.raises(ValueError, match="num_bearings"):
            find_worst_trajectories(site, [], threat, protected_point=(px, py), num_bearings=0)

    def test_negative_altitude_raises(self):
        """Negative altitude in altitudes_m raises ValueError."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        with pytest.raises(ValueError, match="altitudes_m"):
            find_worst_trajectories(
                site,
                [],
                threat,
                protected_point=(px, py),
                altitudes_m=[-10.0],
            )

    def test_dive_angle_out_of_range_raises(self):
        """dive_angles_deg value > 0 raises ValueError."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        with pytest.raises(ValueError, match="dive_angles_deg"):
            find_worst_trajectories(
                site,
                [],
                threat,
                protected_point=(px, py),
                dive_angles_deg=[10.0],  # positive angle: invalid
            )

    def test_non_finite_protected_point_raises(self):
        """Non-finite protected_point raises ValueError."""
        site = _fwt_site()
        threat = _fwt_threat()
        with pytest.raises(ValueError, match="protected_point"):
            find_worst_trajectories(
                site,
                [],
                threat,
                protected_point=(math.inf, 0.0),
            )

    def test_empty_altitudes_list_raises(self):
        """altitudes_m=[] raises ValueError — would silently return empty list."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        with pytest.raises(ValueError, match="altitudes_m"):
            find_worst_trajectories(
                site,
                [],
                threat,
                protected_point=(px, py),
                altitudes_m=[],
            )

    def test_empty_dive_angles_list_raises(self):
        """dive_angles_deg=[] raises ValueError — would silently return empty list."""
        site = _fwt_site()
        threat = _fwt_threat()
        px = _FWT_ORIGIN_X + 50 * _FWT_RESOLUTION
        py = _FWT_ORIGIN_Y - 50 * _FWT_RESOLUTION
        with pytest.raises(ValueError, match="dive_angles_deg"):
            find_worst_trajectories(
                site,
                [],
                threat,
                protected_point=(px, py),
                dive_angles_deg=[],
            )
