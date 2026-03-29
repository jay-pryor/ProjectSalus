"""Tests for coverage map rendering."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image

matplotlib.use("Agg")  # Non-interactive backend — must be set before importing pyplot

from shapely.geometry import Polygon

from salus.ingest.terrain import load_dem
from salus.report.maps import _hillshade, render_coverage_map


class TestHillshade:
    def test_flat_dem_uniform_shading(self):
        """A perfectly flat DEM should produce uniform hillshade values."""
        dem = np.full((50, 50), 100.0)
        hs = _hillshade(dem)
        assert hs.shape == dem.shape
        # All values should be identical on flat terrain
        assert np.allclose(hs, hs[0, 0])

    def test_output_range_clamped(self):
        """Hillshade values must always be in [0, 1]."""
        rng = np.random.default_rng(42)
        dem = rng.uniform(0, 500, (100, 100))
        hs = _hillshade(dem)
        assert hs.min() >= 0.0
        assert hs.max() <= 1.0

    def test_shape_preserved(self):
        """Output shape must match input shape."""
        dem = np.zeros((30, 70))
        hs = _hillshade(dem)
        assert hs.shape == (30, 70)


class TestRenderCoverageMap:
    def test_returns_path_to_png(self, flat_dem_path, tmp_path):
        """render_coverage_map must return the output path and the file must exist."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "coverage.png"

        result = render_coverage_map(site, coverage, out)

        assert result == out
        assert out.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        """The output file must be a readable PNG image."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "coverage.png"

        render_coverage_map(site, coverage, out)

        img = Image.open(out)
        assert img.format == "PNG"
        assert img.size[0] > 0
        assert img.size[1] > 0

    def test_no_coverage_still_renders(self, flat_dem_path, tmp_path):
        """An all-False coverage array (nothing covered) must still produce a valid PNG."""
        site = load_dem(flat_dem_path)
        coverage = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "no_coverage.png"

        result = render_coverage_map(site, coverage, out)

        assert result.exists()
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.size[0] > 0

    def test_partial_coverage_renders(self, flat_dem_path, tmp_path):
        """Partial coverage (some True, some False) must render without error."""
        site = load_dem(flat_dem_path)
        coverage = np.zeros(site.dem.shape, dtype=bool)
        coverage[:50, :50] = True  # Top-left quadrant covered
        out = tmp_path / "partial.png"

        result = render_coverage_map(site, coverage, out)

        assert result.exists()

    def test_custom_title_accepted(self, flat_dem_path, tmp_path):
        """Custom title must not raise — rendering still produces a file."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "titled.png"

        render_coverage_map(site, coverage, out, title="Site Alpha — Radar Coverage")

        assert out.exists()

    def test_sensor_positions_render(self, flat_dem_path, tmp_path):
        """Providing sensor positions must not raise and must produce a file."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "sensors.png"

        cx = site.origin_x + 50 * site.resolution
        cy = site.origin_y - 50 * site.resolution
        render_coverage_map(site, coverage, out, sensor_positions=[(cx, cy)])

        assert out.exists()

    def test_multiple_sensor_positions(self, flat_dem_path, tmp_path):
        """Multiple sensor positions must all be accepted."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "multi_sensors.png"

        positions = [
            (site.origin_x + 25 * site.resolution, site.origin_y - 25 * site.resolution),
            (site.origin_x + 75 * site.resolution, site.origin_y - 75 * site.resolution),
        ]
        render_coverage_map(site, coverage, out, sensor_positions=positions)

        assert out.exists()

    def test_accepts_string_output_path(self, flat_dem_path, tmp_path):
        """output_path may be a str — must be coerced to Path and work correctly."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = str(tmp_path / "str_path.png")

        result = render_coverage_map(site, coverage, out)

        assert isinstance(result, Path)
        assert result.exists()

    def test_ridge_dem_renders(self, ridge_dem_path, tmp_path):
        """Rendering on non-flat terrain (ridge DEM) must produce a valid file."""
        site = load_dem(ridge_dem_path)
        coverage = np.zeros(site.dem.shape, dtype=bool)
        coverage[:100, :] = True  # Front half covered
        out = tmp_path / "ridge_coverage.png"

        result = render_coverage_map(site, coverage, out)

        assert result.exists()
        img = Image.open(out)
        assert img.format == "PNG"

    def test_boundary_outline_renders(self, flat_dem_path, tmp_path):
        """Providing a boundary polygon must not raise and must produce a valid file."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
        out = tmp_path / "boundary.png"

        result = render_coverage_map(site, coverage, out, boundary=boundary)

        assert result.exists()
        img = Image.open(out)
        assert img.format == "PNG"
