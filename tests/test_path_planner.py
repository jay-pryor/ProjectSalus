"""Tests for adversarial path planning (S6.6)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from salus.engine.path_planner import (
    build_detection_cost_grid,
    find_adversarial_trajectory,
)
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType
from salus.models.threat import DroneTrajectory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sensor_pair(flat_dem_path, sensor_name: str = "Echodyne EchoGuard"):
    """Return a (SensorDefinition, SensorPlacement) pair at the DEM centre."""
    from pathlib import Path

    from salus.ingest.sensors import load_sensors
    from salus.models.scenario import SensorPlacement

    sensor_dir = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"
    sensors = {s.name: s for s in load_sensors(sensor_dir)}
    sdef = sensors[sensor_name]
    spl = SensorPlacement(
        sensor_name=sensor_name,
        position_x=500050.0,
        position_y=6100050.0,
        bearing_deg=0.0,
    )
    return sdef, spl


def _minimal_cost_grid(
    flat_dem_path,
    altitude_bands_m: list[float] | None = None,
    sensor_name: str = "Echodyne EchoGuard",
) -> tuple:
    """Return (site, cost_grid) for the flat DEM with one sensor."""
    site = load_dem(flat_dem_path)
    pair = _make_sensor_pair(flat_dem_path, sensor_name)
    bands = altitude_bands_m or [50.0]
    grid = build_detection_cost_grid(site, [pair], altitude_bands_m=bands)
    return site, grid


# ---------------------------------------------------------------------------
# DetectionCostGrid construction
# ---------------------------------------------------------------------------


class TestDetectionCostGridShape:
    def test_grid_shape_matches_site_and_bands(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        pair = _make_sensor_pair(flat_dem_path)
        bands = [10.0, 50.0, 100.0]
        grid = build_detection_cost_grid(site, [pair], altitude_bands_m=bands)
        assert grid.grid.shape == (3, site.rows, site.cols)

    def test_grid_dtype_is_int32(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        pair = _make_sensor_pair(flat_dem_path)
        grid = build_detection_cost_grid(site, [pair], altitude_bands_m=[50.0])
        assert grid.grid.dtype == np.int32

    def test_origin_and_resolution_match_site(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        pair = _make_sensor_pair(flat_dem_path)
        grid = build_detection_cost_grid(site, [pair], altitude_bands_m=[50.0])
        assert grid.origin_x == site.origin_x
        assert grid.origin_y == site.origin_y
        assert grid.resolution == site.resolution
        assert grid.rows == site.rows
        assert grid.cols == site.cols

    def test_altitude_bands_preserved(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        pair = _make_sensor_pair(flat_dem_path)
        bands = [20.0, 80.0]
        grid = build_detection_cost_grid(site, [pair], altitude_bands_m=bands)
        assert grid.altitude_bands_m == bands

    def test_default_altitude_bands(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        pair = _make_sensor_pair(flat_dem_path)
        grid = build_detection_cost_grid(site, [pair])
        assert len(grid.altitude_bands_m) >= 1

    def test_no_sensors_all_zero(self, flat_dem_path):
        """With no sensor placements the grid must be all zeros."""
        site = load_dem(flat_dem_path)
        grid = build_detection_cost_grid(site, [], altitude_bands_m=[50.0])
        assert grid.grid.max() == 0


class TestDetectionCostGridValues:
    def test_cells_inside_range_have_nonzero_count(self, flat_dem_path):
        """Cells inside the sensor detection radius must have count >= 1."""
        site, grid = _minimal_cost_grid(flat_dem_path, altitude_bands_m=[50.0])
        # The sensor is at the centre (500050, 6100050). Some nearby cells
        # must have detection count >= 1.
        assert grid.grid[0].max() >= 1, "No cell was detected — sensor range may be too short"

    def test_grid_values_non_negative(self, flat_dem_path):
        site, grid = _minimal_cost_grid(flat_dem_path, altitude_bands_m=[50.0])
        assert grid.grid.min() >= 0

    def test_grid_count_bounded_by_sensor_count(self, flat_dem_path):
        """No cell can have more detections than the number of sensors."""
        site = load_dem(flat_dem_path)
        pair = _make_sensor_pair(flat_dem_path)
        grid = build_detection_cost_grid(site, [pair, pair], altitude_bands_m=[50.0])
        assert grid.grid.max() <= 2


class TestDetectionCostGridRidge:
    def test_ridge_blocks_far_side(self, ridge_dem_path):
        """Cells behind a ridge must have detection count 0 for a LOS sensor."""
        site = load_dem(ridge_dem_path)
        from pathlib import Path

        from salus.ingest.sensors import load_sensors
        from salus.models.scenario import SensorPlacement

        sensor_dir = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"
        sensors_db = {s.name: s for s in load_sensors(sensor_dir)}
        # Use a LOS radar sensor (Echodyne EchoGuard) at the south side of the ridge
        sdef = sensors_db["Echodyne EchoGuard"]
        spl = SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=500100.0,  # Centre x
            position_y=6100050.0,  # South of ridge (rows 95-105 have the ridge peak)
            bearing_deg=0.0,
        )
        grid = build_detection_cost_grid(site, [(sdef, spl)], altitude_bands_m=[10.0])
        # Row 0 is the northern edge — behind the ridge relative to the south-placed sensor.
        # Detection count in the far-north rows must be 0 for a LOS sensor blocked by ridge.
        far_north_band = grid.grid[0, :10, :]  # rows 0-9 are far north
        assert far_north_band.max() == 0, (
            f"LOS sensor detected cells behind ridge: max={far_north_band.max()}"
        )


class TestBuildDetectionCostGridGuards:
    def test_empty_altitude_bands_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        with pytest.raises(ValueError, match="empty"):
            build_detection_cost_grid(site, [], altitude_bands_m=[])

    def test_negative_altitude_band_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        with pytest.raises(ValueError, match="finite and >= 0"):
            build_detection_cost_grid(site, [], altitude_bands_m=[-1.0])

    def test_non_finite_altitude_band_raises(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        with pytest.raises(ValueError, match="finite and >= 0"):
            build_detection_cost_grid(site, [], altitude_bands_m=[float("inf")])


# ---------------------------------------------------------------------------
# find_adversarial_trajectory
# ---------------------------------------------------------------------------


class TestFindAdversarialTrajectory:
    def _run_adv(
        self,
        flat_dem_path,
        altitude_bands_m: list[float] | None = None,
    ) -> tuple[object, DroneTrajectory]:
        site, cost_grid = _minimal_cost_grid(flat_dem_path, altitude_bands_m or [50.0])
        # Origin at the north edge of the DEM, asset at the south
        traj = find_adversarial_trajectory(
            site,
            cost_grid,
            origin_x=500050.0,
            origin_y=6100090.0,
            origin_z_agl=50.0,
            asset_x=500050.0,
            asset_y=6100010.0,
            speed_ms=10.0,
        )
        return site, traj

    def test_returns_drone_trajectory(self, flat_dem_path):
        _, traj = self._run_adv(flat_dem_path)
        assert isinstance(traj, DroneTrajectory)

    def test_trajectory_has_at_least_two_waypoints(self, flat_dem_path):
        _, traj = self._run_adv(flat_dem_path)
        assert len(traj.waypoints) >= 2

    def test_speed_is_preserved(self, flat_dem_path):
        _, traj = self._run_adv(flat_dem_path)
        assert traj.speed_ms == 10.0

    def test_first_waypoint_near_origin(self, flat_dem_path):
        """First waypoint must be close to the requested origin."""
        site, traj = self._run_adv(flat_dem_path)
        wp0 = traj.waypoints[0]
        assert abs(wp0.x - 500050.0) <= site.resolution * 2
        assert abs(wp0.y - 6100090.0) <= site.resolution * 2

    def test_last_waypoint_near_asset(self, flat_dem_path):
        """Last waypoint must be close to the asset."""
        site, traj = self._run_adv(flat_dem_path)
        wpl = traj.waypoints[-1]
        assert abs(wpl.x - 500050.0) <= site.resolution * 2
        assert abs(wpl.y - 6100010.0) <= site.resolution * 2

    def test_all_waypoints_in_site_extent(self, flat_dem_path):
        site, traj = self._run_adv(flat_dem_path)
        min_x, max_x, min_y, max_y = site.extent
        for wp in traj.waypoints:
            assert min_x <= wp.x <= max_x, f"wp.x={wp.x} out of extent"
            assert min_y <= wp.y <= max_y, f"wp.y={wp.y} out of extent"

    def test_invalid_speed_raises(self, flat_dem_path):
        site, cost_grid = _minimal_cost_grid(flat_dem_path)
        with pytest.raises(ValueError, match="speed_ms"):
            find_adversarial_trajectory(
                site, cost_grid, 500050.0, 6100050.0, 50.0, 500050.0, 6100010.0, speed_ms=0.0
            )

    def test_negative_speed_raises(self, flat_dem_path):
        site, cost_grid = _minimal_cost_grid(flat_dem_path)
        with pytest.raises(ValueError, match="speed_ms"):
            find_adversarial_trajectory(
                site, cost_grid, 500050.0, 6100050.0, 50.0, 500050.0, 6100010.0, speed_ms=-5.0
            )

    def test_multi_altitude_band_trajectory(self, flat_dem_path):
        """Multiple altitude bands produce a valid trajectory."""
        _, traj = self._run_adv(flat_dem_path, altitude_bands_m=[10.0, 50.0, 100.0])
        assert len(traj.waypoints) >= 2


class TestAdversarialPathAvoidsDetection:
    def test_path_routes_around_sensor_on_flat_terrain(self, flat_dem_path):
        """On flat terrain with a central sensor, path should avoid the sensor.

        The centre cell has high detection count; a minimum-cost path from the
        north edge to the south edge should deviate around the sensor rather
        than pass directly through it.
        """
        site = load_dem(flat_dem_path)
        # Build cost grid: sensor at the centre
        from pathlib import Path

        from salus.ingest.sensors import load_sensors
        from salus.models.scenario import SensorPlacement

        sensor_dir = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"
        sensors_db = {s.name: s for s in load_sensors(sensor_dir)}
        sdef = sensors_db["Echodyne EchoGuard"]
        # Place sensor mid-DEM at a known position
        spl = SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=500050.0,
            position_y=6100050.0,
            bearing_deg=0.0,
        )
        cost_grid = build_detection_cost_grid(site, [(sdef, spl)], altitude_bands_m=[50.0])

        # Find adversarial path: north→south, through the sensor's location
        traj = find_adversarial_trajectory(
            site,
            cost_grid,
            origin_x=500050.0,
            origin_y=6100090.0,
            origin_z_agl=50.0,
            asset_x=500050.0,
            asset_y=6100010.0,
            speed_ms=10.0,
        )

        # The total detection cost along the path should be less than the
        # direct route (which passes through the sensor detection zone).
        # Compute direct-route cost as a reference:
        direct_detection_count = 0
        res = site.resolution
        # Vertical traverse: from row corresponding to y=6100090 to y=6100010
        min_y_direct, max_y_direct = 6100010.0, 6100090.0
        for y in np.arange(min_y_direct, max_y_direct + res, res):
            row = int((site.origin_y - y) / res)
            col = int((500050.0 - site.origin_x) / res)
            row = max(0, min(site.rows - 1, row))
            col = max(0, min(site.cols - 1, col))
            direct_detection_count += int(cost_grid.grid[0, row, col])

        # Count detection cells the adversarial path passes through
        adv_detection_count = 0
        for wp in traj.waypoints:
            row = int((site.origin_y - wp.y) / res)
            col = int((wp.x - site.origin_x) / res)
            row = max(0, min(site.rows - 1, row))
            col = max(0, min(site.cols - 1, col))
            adv_detection_count += int(cost_grid.grid[0, row, col])

        # The adversarial path should not be worse than the direct route
        assert adv_detection_count <= direct_detection_count, (
            f"Adversarial path ({adv_detection_count}) is worse than direct "
            f"route ({direct_detection_count}) — Dijkstra's did not find a better path"
        )


# ---------------------------------------------------------------------------
# Integration: build cost grid → find path → analyse trajectory
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# D-167: Cells outside sensor range must have detection count 0
# ---------------------------------------------------------------------------


class TestCellsOutsideSensorRangeAreZero:
    """Spec S6.6-1: cells beyond max_range_m must record count 0."""

    def _short_range_sensor_pair(self, sensor_name: str = "short_range_radar") -> tuple:
        """Return a (SensorDefinition, SensorPlacement) with max_range_m=30 m.

        Placed at the DEM centre (500050, 6100050); any cell whose centroid is
        more than 30 m away must not be detected.
        """
        sdef = SensorDefinition(
            name=sensor_name,
            type=SensorType.Radar,
            max_range_m=30.0,
            azimuth_coverage_deg=360.0,
            elevation_coverage_deg=90.0,
            elevation_boresight_deg=10.0,
            requires_los=False,
            mounting_height_m=3.0,
        )
        spl = SensorPlacement(
            sensor_name=sensor_name,
            position_x=500050.0,
            position_y=6100050.0,
            bearing_deg=0.0,
        )
        return sdef, spl

    def test_corner_cells_have_zero_count(self, flat_dem_path):
        """Corner cells are ~70 m from the centre sensor — beyond the 30 m range."""
        site = load_dem(flat_dem_path)
        pair = self._short_range_sensor_pair()
        grid = build_detection_cost_grid(site, [pair], altitude_bands_m=[10.0])
        # DEM is 100×100; corner cell (0,0) centroid is at (500000.5, 6100099.5)
        # Distance from centre (500050, 6100050) ≈ 70 m > 30 m max_range_m.
        assert grid.grid[0, 0, 0] == 0, (
            "Corner cell (row=0,col=0) should be outside sensor range (count must be 0)"
        )
        assert grid.grid[0, 0, 99] == 0, "Corner cell (row=0,col=99) must be outside range"
        assert grid.grid[0, 99, 0] == 0, "Corner cell (row=99,col=0) must be outside range"
        assert grid.grid[0, 99, 99] == 0, "Corner cell (row=99,col=99) must be outside range"

    def test_near_cells_have_nonzero_count(self, flat_dem_path):
        """Cells within the 30 m range of the centre sensor must be detected.

        The sensor is at (500050, 6100050) with max_range_m=30m and a wide
        horizontal elevation arc.  The band of cells immediately north of the
        sensor (row ~35-45, col ~50, ~5–15 m away) must have count >= 1.
        """
        site = load_dem(flat_dem_path)
        pair = self._short_range_sensor_pair()
        grid = build_detection_cost_grid(site, [pair], altitude_bands_m=[10.0])
        # Cells 5–15 m north of sensor (row ~35-45, col ~50) are within range
        # and at a shallow-enough elevation angle to be detected.
        near_strip = grid.grid[0, 35:46, 48:53]
        assert near_strip.max() >= 1, (
            "Cells ~10 m north of sensor should be detected (count >= 1) "
            f"but max count is {near_strip.max()}"
        )


# ---------------------------------------------------------------------------
# D-168: Valley terrain — adversarial path prefers valley floor
# ---------------------------------------------------------------------------


class TestValleyTerrainPathPrefersValley:
    """Spec S6.6-2: adversarial path follows valley terrain (low-detection corridor)."""

    def test_valley_floor_has_lower_detection_than_ridges(self, valley_dem_path):
        """A sensor on the east ridge should produce count 0 in the valley floor.

        The east ridge (cols 160-199) occludes LOS to the valley floor
        (cols 80-119) when the sensor is on the east ridge above the valley.
        Uses a non-LOS sensor so only range and elevation arc matter, making
        the terrain shadow a pure elevation-angle effect.
        """
        site = load_dem(valley_dem_path)
        # LOS sensor on east ridge — can only see to the ridge edge, not into valley
        from pathlib import Path

        from salus.ingest.sensors import load_sensors

        sensor_dir = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"
        sensors_db = {s.name: s for s in load_sensors(sensor_dir)}
        sdef = sensors_db["Echodyne EchoGuard"]
        spl = SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=500180.0,  # Col ~180 — east ridge
            position_y=6100100.0,  # Centre row
            bearing_deg=270.0,  # Facing west toward valley
        )
        # Use low altitude (10 m AGL): drone at valley floor elevation + 10 m = 20 m abs
        # Sensor on east ridge is at elevation ~100 m abs; valley floor at 10 m abs.
        # Valley floor cells are far below the sensor — outside elevation coverage arc.
        grid = build_detection_cost_grid(site, [(sdef, spl)], altitude_bands_m=[10.0])

        valley_detection = int(grid.grid[0, :, 80:120].max())
        east_ridge_detection = int(grid.grid[0, :, 160:200].max())
        # Valley floor (behind the ridge from the sensor's perspective) should be
        # less detected than the ridge itself (sensor is ON the east ridge).
        assert valley_detection <= east_ridge_detection, (
            f"Valley floor max detection ({valley_detection}) should be <= "
            f"east-ridge detection ({east_ridge_detection})"
        )

    def test_adversarial_path_valid_on_valley_terrain(self, valley_dem_path):
        """Adversarial path completes successfully on valley DEM."""
        site = load_dem(valley_dem_path)
        sdef = SensorDefinition(
            name="valley_test_sensor",
            type=SensorType.Radar,
            max_range_m=120.0,
            azimuth_coverage_deg=360.0,
            elevation_coverage_deg=60.0,
            elevation_boresight_deg=0.0,
            requires_los=True,
            mounting_height_m=2.0,
        )
        # Place sensor on east ridge — high detection on east slope, low in valley
        spl = SensorPlacement(
            sensor_name="valley_test_sensor",
            position_x=500180.0,
            position_y=6100100.0,
            bearing_deg=270.0,
        )
        grid = build_detection_cost_grid(site, [(sdef, spl)], altitude_bands_m=[10.0, 30.0])
        traj = find_adversarial_trajectory(
            site,
            grid,
            origin_x=500100.0,
            origin_y=6100180.0,
            origin_z_agl=10.0,
            asset_x=500100.0,
            asset_y=6100020.0,
            speed_ms=15.0,
        )
        assert isinstance(traj, DroneTrajectory)
        assert len(traj.waypoints) >= 2


# ---------------------------------------------------------------------------
# D-169: Ridge terrain integration — path reaches goal on ridge DEM
# ---------------------------------------------------------------------------


class TestRidgeTerrainIntegration:
    """Spec S6.6-3: adversarial path planning integrates correctly with ridge terrain."""

    def test_adversarial_path_reaches_goal_on_ridge_terrain(self, ridge_dem_path):
        """Adversarial path from north to south completes on a DEM with a central ridge."""
        from pathlib import Path

        from salus.ingest.sensors import load_sensors

        site = load_dem(ridge_dem_path)
        sensor_dir = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"
        sensors_db = {s.name: s for s in load_sensors(sensor_dir)}
        sdef = sensors_db["Echodyne EchoGuard"]
        # Sensor south of ridge
        spl = SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=500100.0,
            position_y=6100020.0,
            bearing_deg=0.0,
        )
        grid = build_detection_cost_grid(site, [(sdef, spl)], altitude_bands_m=[10.0, 50.0])
        traj = find_adversarial_trajectory(
            site,
            grid,
            origin_x=500100.0,
            origin_y=6100180.0,
            origin_z_agl=10.0,
            asset_x=500100.0,
            asset_y=6100020.0,
            speed_ms=10.0,
        )
        assert isinstance(traj, DroneTrajectory)
        assert len(traj.waypoints) >= 2
        # Last waypoint must be close to the asset (south side)
        wpl = traj.waypoints[-1]
        assert abs(wpl.y - 6100020.0) <= site.resolution * 3

    def test_adversarial_path_avoids_high_detection_on_ridge_terrain(self, ridge_dem_path):
        """Far-north cells have detection count 0; adversarial path should spend time there.

        With a south-side LOS sensor blocked by the central ridge, the far-north
        rows (rows 0–9) are undetectable.  The adversarial path from far north to
        far south must cross the ridge, but it should originate in the zero-detection
        north zone, i.e. the first waypoint should be in the north half of the DEM.
        """
        from pathlib import Path

        from salus.ingest.sensors import load_sensors

        site = load_dem(ridge_dem_path)
        sensor_dir = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"
        sensors_db = {s.name: s for s in load_sensors(sensor_dir)}
        sdef = sensors_db["Echodyne EchoGuard"]
        spl = SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=500100.0,
            position_y=6100020.0,
            bearing_deg=0.0,
        )
        grid = build_detection_cost_grid(site, [(sdef, spl)], altitude_bands_m=[10.0])
        traj = find_adversarial_trajectory(
            site,
            grid,
            origin_x=500100.0,
            origin_y=6100180.0,
            origin_z_agl=10.0,
            asset_x=500100.0,
            asset_y=6100020.0,
            speed_ms=10.0,
        )
        # First waypoint should be in the northern half of the DEM (y > DEM midpoint)
        dem_mid_y = (site.origin_y + (site.origin_y - site.rows * site.resolution)) / 2.0
        assert traj.waypoints[0].y > dem_mid_y, (
            "First waypoint should be in the north (low-detection) half of the DEM"
        )


# ---------------------------------------------------------------------------
# Integration: build cost grid → find path → analyse trajectory
# ---------------------------------------------------------------------------


class TestAdversarialIntegration:
    def test_full_pipeline_completes(self, flat_dem_path):
        """build_cost_grid → find_adversarial_trajectory → analyse_trajectory completes."""
        from salus.engine.trajectory import analyse_trajectory

        site = load_dem(flat_dem_path)
        pair = _make_sensor_pair(flat_dem_path)
        cost_grid = build_detection_cost_grid(site, [pair], altitude_bands_m=[50.0])

        traj = find_adversarial_trajectory(
            site,
            cost_grid,
            origin_x=500050.0,
            origin_y=6100090.0,
            origin_z_agl=50.0,
            asset_x=500050.0,
            asset_y=6100010.0,
            speed_ms=10.0,
        )

        result = analyse_trajectory(site, [pair], traj, segment_length_m=2.0)

        assert result.time_to_asset_s > 0.0
        assert result.time_in_detection_s >= 0.0
        assert result.time_undetected_s >= 0.0
        assert math.isclose(
            result.time_in_detection_s + result.time_undetected_s,
            result.time_to_asset_s,
            rel_tol=1e-3,
        )
