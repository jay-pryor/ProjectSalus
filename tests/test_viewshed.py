"""Tests for viewshed computation."""

import numpy as np

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
