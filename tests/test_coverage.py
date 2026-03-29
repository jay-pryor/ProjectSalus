"""Tests for coverage boundary masking and percentage computation."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon

from salus.engine.coverage import boundary_mask, clip_coverage_to_boundary, coverage_percentage
from salus.ingest.terrain import load_dem


class TestBoundaryMask:
    def test_full_site_boundary_all_true(self, flat_dem_path):
        """A boundary that covers the entire raster extent should produce an all-True mask."""
        site = load_dem(flat_dem_path)
        # Boundary slightly larger than raster extent
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon(
            [
                (min_x - 1, min_y - 1),
                (max_x + 1, min_y - 1),
                (max_x + 1, max_y + 1),
                (min_x - 1, max_y + 1),
            ]
        )
        mask = boundary_mask(site, boundary)
        assert mask.shape == (site.rows, site.cols)
        assert mask.dtype == bool
        assert mask.all()

    def test_boundary_outside_raster_all_false(self, flat_dem_path):
        """A boundary entirely outside the raster extent should produce an all-False mask."""
        site = load_dem(flat_dem_path)
        min_x, max_x, min_y, max_y = site.extent
        # Boundary placed far to the east, no overlap
        boundary = Polygon(
            [
                (max_x + 1000, min_y),
                (max_x + 2000, min_y),
                (max_x + 2000, max_y),
                (max_x + 1000, max_y),
            ]
        )
        mask = boundary_mask(site, boundary)
        assert mask.shape == (site.rows, site.cols)
        assert not mask.any()

    def test_partial_boundary_partial_mask(self, flat_dem_path):
        """A boundary covering half the raster should produce a mask that is ~50% True."""
        site = load_dem(flat_dem_path)
        min_x, max_x, min_y, max_y = site.extent
        mid_x = (min_x + max_x) / 2
        # Left half only
        boundary = Polygon(
            [
                (min_x, min_y),
                (mid_x, min_y),
                (mid_x, max_y),
                (min_x, max_y),
            ]
        )
        mask = boundary_mask(site, boundary)
        frac = mask.sum() / mask.size
        assert 0.4 < frac < 0.6

    def test_mask_shape_matches_site_grid(self, flat_dem_path):
        """Output shape must equal (site.rows, site.cols)."""
        site = load_dem(flat_dem_path)
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
        mask = boundary_mask(site, boundary)
        assert mask.shape == (site.rows, site.cols)

    def test_multipolygon_boundary(self, flat_dem_path):
        """A MultiPolygon boundary should be accepted and produce a valid mask."""
        site = load_dem(flat_dem_path)
        min_x, max_x, min_y, max_y = site.extent
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        # Two non-overlapping quadrants
        poly1 = Polygon([(min_x, min_y), (mid_x, min_y), (mid_x, mid_y), (min_x, mid_y)])
        poly2 = Polygon([(mid_x, mid_y), (max_x, mid_y), (max_x, max_y), (mid_x, max_y)])
        boundary = MultiPolygon([poly1, poly2])
        mask = boundary_mask(site, boundary)
        assert mask.shape == (site.rows, site.cols)
        assert mask.any()


class TestClipCoverageToBoundary:
    def test_full_boundary_preserves_coverage(self, flat_dem_path):
        """Clipping with a boundary that covers the whole raster preserves True values."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon(
            [
                (min_x - 1, min_y - 1),
                (max_x + 1, min_y - 1),
                (max_x + 1, max_y + 1),
                (min_x - 1, max_y + 1),
            ]
        )
        clipped = clip_coverage_to_boundary(coverage, site, boundary)
        assert clipped.dtype == bool
        assert clipped.all()

    def test_outside_boundary_zeroes_coverage(self, flat_dem_path):
        """Coverage outside the boundary is set to False."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon(
            [
                (min_x + 1000, min_y + 1000),
                (min_x + 2000, min_y + 1000),
                (min_x + 2000, min_y + 2000),
                (min_x + 1000, min_y + 2000),
            ]
        )
        clipped = clip_coverage_to_boundary(coverage, site, boundary)
        # Boundary is outside raster — all False
        assert not clipped.any()

    def test_partial_boundary_clips_correctly(self, flat_dem_path):
        """Only cells inside the boundary and covered remain True."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        mid_x = (min_x + max_x) / 2
        # Left half boundary
        boundary = Polygon([(min_x, min_y), (mid_x, min_y), (mid_x, max_y), (min_x, max_y)])
        clipped = clip_coverage_to_boundary(coverage, site, boundary)
        frac = clipped.sum() / clipped.size
        assert 0.4 < frac < 0.6

    def test_shape_mismatch_raises(self, flat_dem_path):
        """Passing a coverage array with wrong shape must raise ValueError."""
        site = load_dem(flat_dem_path)
        wrong_shape = np.ones((50, 50), dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
        with pytest.raises(ValueError, match="shape"):
            clip_coverage_to_boundary(wrong_shape, site, boundary)

    def test_false_coverage_stays_false(self, flat_dem_path):
        """All-False coverage remains all-False even inside the boundary."""
        site = load_dem(flat_dem_path)
        coverage = np.zeros(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon(
            [
                (min_x - 1, min_y - 1),
                (max_x + 1, min_y - 1),
                (max_x + 1, max_y + 1),
                (min_x - 1, max_y + 1),
            ]
        )
        clipped = clip_coverage_to_boundary(coverage, site, boundary)
        assert not clipped.any()


class TestCoveragePercentage:
    def test_full_coverage_no_mask(self):
        """All-True array with no mask returns 100.0."""
        cov = np.ones((10, 10), dtype=bool)
        assert coverage_percentage(cov) == pytest.approx(100.0)

    def test_no_coverage_no_mask(self):
        """All-False array with no mask returns 0.0."""
        cov = np.zeros((10, 10), dtype=bool)
        assert coverage_percentage(cov) == pytest.approx(0.0)

    def test_half_coverage_no_mask(self):
        """Half-True array with no mask returns 50.0."""
        cov = np.zeros((10, 10), dtype=bool)
        cov[:5, :] = True
        assert coverage_percentage(cov) == pytest.approx(50.0)

    def test_full_coverage_with_full_mask(self):
        """All-True coverage with all-True mask returns 100.0."""
        cov = np.ones((10, 10), dtype=bool)
        mask = np.ones((10, 10), dtype=bool)
        assert coverage_percentage(cov, mask) == pytest.approx(100.0)

    def test_full_coverage_with_half_mask(self):
        """All-True coverage restricted to half-mask returns 100.0 within mask."""
        cov = np.ones((10, 10), dtype=bool)
        mask = np.zeros((10, 10), dtype=bool)
        mask[:5, :] = True
        assert coverage_percentage(cov, mask) == pytest.approx(100.0)

    def test_partial_coverage_within_mask(self):
        """50% of masked cells covered returns 50.0."""
        cov = np.zeros((10, 10), dtype=bool)
        cov[:5, :5] = True  # 25 cells True
        mask = np.zeros((10, 10), dtype=bool)
        mask[:5, :] = True  # 50 cells in mask
        pct = coverage_percentage(cov, mask)
        assert pct == pytest.approx(50.0)

    def test_coverage_outside_mask_excluded(self):
        """Coverage outside the mask does not count in the percentage."""
        cov = np.zeros((10, 10), dtype=bool)
        cov[8:, :] = True  # Bottom rows covered — outside mask
        mask = np.zeros((10, 10), dtype=bool)
        mask[:5, :] = True  # Top half is the mask
        assert coverage_percentage(cov, mask) == pytest.approx(0.0)

    def test_empty_mask_returns_zero_with_warning(self):
        """All-False mask (zero denominator) returns 0.0 and emits a UserWarning."""
        cov = np.ones((10, 10), dtype=bool)
        mask = np.zeros((10, 10), dtype=bool)
        with pytest.warns(UserWarning, match="boundary mask contains no True cells"):
            result = coverage_percentage(cov, mask)
        assert result == pytest.approx(0.0)

    def test_result_in_range(self):
        """Result must always be in [0.0, 100.0]."""
        rng = np.random.default_rng(0)
        cov = rng.choice([True, False], size=(50, 50))
        mask = rng.choice([True, False], size=(50, 50))
        pct = coverage_percentage(cov, mask)
        assert 0.0 <= pct <= 100.0
