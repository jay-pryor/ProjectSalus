"""Tests for viewshed computation."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from salus.engine.viewshed import compute_viewshed
from salus.ingest.terrain import load_dem


class TestViewshed:
    def test_flat_terrain_all_visible(self, flat_dem_path):
        """On flat terrain, every cell within range should be visible."""
        site = load_dem(flat_dem_path)
        # Observer at centre, 10m above ground
        cx = site.origin_x + 50 * site.resolution
        cy = site.origin_y - 50 * site.resolution
        vis = compute_viewshed(site, cx, cy, observer_height=10.0)

        assert vis.shape == site.dem.shape
        # Vast majority should be visible on flat terrain
        pct_visible = vis.sum() / vis.size
        assert pct_visible > 0.9

    def test_ridge_blocks_visibility(self, ridge_dem_path):
        """Observer on one side of a ridge should not see the other side."""
        site = load_dem(ridge_dem_path)
        # Observer at row 10 (north of ridge), col 100 (centre), 2m height
        obs_x = site.origin_x + 100 * site.resolution
        obs_y = site.origin_y - 10 * site.resolution
        vis = compute_viewshed(site, obs_x, obs_y, observer_height=2.0)

        # Cells well behind the ridge (row 150+) should mostly NOT be visible
        behind_ridge = vis[150:, :]
        pct_behind_visible = behind_ridge.sum() / behind_ridge.size
        assert pct_behind_visible < 0.2, f"Too much visible behind ridge: {pct_behind_visible:.1%}"

        # Cells in front of the ridge (row 0-90) should mostly be visible
        in_front = vis[:90, :]
        pct_front_visible = in_front.sum() / in_front.size
        assert pct_front_visible > 0.5

    def test_max_range_limits_visibility(self, flat_dem_path):
        """max_range should limit how far visibility extends."""
        site = load_dem(flat_dem_path)
        cx = site.origin_x + 50 * site.resolution
        cy = site.origin_y - 50 * site.resolution

        vis_short = compute_viewshed(site, cx, cy, observer_height=10.0, max_range=20.0)
        vis_long = compute_viewshed(site, cx, cy, observer_height=10.0, max_range=80.0)

        assert vis_short.sum() < vis_long.sum()

    def test_observer_cell_always_visible(self, flat_dem_path):
        """The observer's own cell should always be visible."""
        site = load_dem(flat_dem_path)
        cx = site.origin_x + 50 * site.resolution
        cy = site.origin_y - 50 * site.resolution
        vis = compute_viewshed(site, cx, cy, observer_height=10.0)

        obs_row = int((site.origin_y - cy) / site.resolution)
        obs_col = int((cx - site.origin_x) / site.resolution)
        assert vis[obs_row, obs_col] is np.True_

    def test_max_range_zero_treated_as_unlimited(self, flat_dem_path):
        """max_range=0.0 should behave identically to max_range=None (unlimited)."""
        site = load_dem(flat_dem_path)
        cx = site.origin_x + 50 * site.resolution
        cy = site.origin_y - 50 * site.resolution

        vis_none = compute_viewshed(site, cx, cy, observer_height=10.0, max_range=None)
        vis_zero = compute_viewshed(site, cx, cy, observer_height=10.0, max_range=0.0)

        np.testing.assert_array_equal(vis_none, vis_zero)

    def test_max_range_negative_treated_as_unlimited(self, flat_dem_path):
        """max_range <= 0.0 should be normalised to unlimited, same as None."""
        site = load_dem(flat_dem_path)
        cx = site.origin_x + 50 * site.resolution
        cy = site.origin_y - 50 * site.resolution

        vis_none = compute_viewshed(site, cx, cy, observer_height=10.0, max_range=None)
        vis_neg = compute_viewshed(site, cx, cy, observer_height=10.0, max_range=-50.0)

        np.testing.assert_array_equal(vis_none, vis_neg)

    def test_observer_outside_raster_raises(self, flat_dem_path):
        """Observer position outside the raster extent must raise ValueError."""
        site = load_dem(flat_dem_path)
        with pytest.raises(ValueError, match="outside"):
            compute_viewshed(site, 0.0, 0.0, observer_height=2.0)


class TestDSMViewshed:
    """Tests for dual-surface (DSM) viewshed behaviour."""

    def _write_tif(self, path: Path, data: np.ndarray) -> None:
        transform = from_bounds(500000, 6100000, 500100, 6100100, 100, 100)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=100,
            width=100,
            count=1,
            dtype="float64",
            crs=CRS.from_epsg(28354),
            transform=transform,
        ) as dst:
            dst.write(data, 1)

    def test_dsm_wall_blocks_los(self, tmp_path: Path) -> None:
        """A DSM wall must block LOS to targets directly behind it."""
        dem = np.full((100, 100), 50.0)
        dsm = dem.copy()
        # Wall at column 50 spanning all rows — 30m above ground (80m absolute)
        dsm[:, 50] = 80.0

        dem_path = tmp_path / "dem.tif"
        dsm_path = tmp_path / "dsm.tif"
        self._write_tif(dem_path, dem)
        self._write_tif(dsm_path, dsm)

        site = load_dem(dem_path, dsm_path=dsm_path)
        obs_x = site.origin_x + 10 * site.resolution  # col 10
        obs_y = site.origin_y - 50 * site.resolution  # row 50

        vis = compute_viewshed(site, obs_x, obs_y, observer_height=2.0)

        # Cell directly behind the wall along the same row must not be visible
        assert not vis[50, 60], "Target behind DSM wall should not be visible"
        # Cell in front of the wall along the same row must be visible
        assert vis[50, 30], "Target in front of DSM wall should be visible"

    def test_no_dsm_flat_terrain_visible(self, tmp_path: Path) -> None:
        """Without DSM, flat terrain must be visible on both sides of the same column."""
        dem = np.full((100, 100), 50.0)
        dem_path = tmp_path / "dem.tif"
        self._write_tif(dem_path, dem)

        site = load_dem(dem_path)  # No DSM — wall is not present
        obs_x = site.origin_x + 10 * site.resolution
        obs_y = site.origin_y - 50 * site.resolution

        vis = compute_viewshed(site, obs_x, obs_y, observer_height=2.0)

        # Without a DSM wall, the far side should be visible on flat terrain
        assert vis[50, 60], "Target should be visible on flat DEM without DSM"

    def test_observer_below_dsm_surface_raises(self, tmp_path: Path) -> None:
        """Observer placed below the DSM surface at its position must raise ValueError."""
        dem = np.full((100, 100), 50.0)
        dsm = dem.copy()
        dsm[50, 10] = 100.0  # 50m building at observer's cell

        dem_path = tmp_path / "dem.tif"
        dsm_path = tmp_path / "dsm.tif"
        self._write_tif(dem_path, dem)
        self._write_tif(dsm_path, dsm)

        site = load_dem(dem_path, dsm_path=dsm_path)
        obs_x = site.origin_x + 10 * site.resolution  # col 10
        obs_y = site.origin_y - 50 * site.resolution  # row 50

        # 2m above DEM = 52m absolute; DSM = 100m → sensor is inside the building
        with pytest.raises(ValueError, match="below"):
            compute_viewshed(site, obs_x, obs_y, observer_height=2.0)
