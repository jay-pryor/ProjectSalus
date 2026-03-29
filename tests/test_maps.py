"""Tests for coverage map rendering."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pytest
from PIL import Image

matplotlib.use("Agg")  # Non-interactive backend — must be set before importing pyplot

from shapely.geometry import MultiPolygon, Polygon

from salus.ingest.terrain import load_dem
from salus.models.zone import Zone, ZoneType
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


class TestRenderCoverageMapZones:
    def _make_zone(
        self,
        name: str,
        zone_type: ZoneType,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> Zone:
        geom = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
        return Zone(name=name, zone_type=zone_type, geometry=geom)

    def test_single_zone_renders(self, flat_dem_path, tmp_path):
        """A single zone should render without error and produce a valid PNG."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        zone = self._make_zone("Alpha", ZoneType.critical_asset, min_x, min_y, mid_x, mid_y)
        out = tmp_path / "zone_single.png"

        result = render_coverage_map(site, coverage, out, zones=[zone])

        assert result.exists()
        assert Image.open(out).format == "PNG"

    def test_all_zone_types_render(self, flat_dem_path, tmp_path):
        """All four zone types must render without error."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        # Four small non-overlapping squares in each quadrant
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        zones = [
            self._make_zone("Perimeter", ZoneType.perimeter, min_x, mid_y, mid_x, max_y),
            self._make_zone("Inner", ZoneType.inner, mid_x, mid_y, max_x, max_y),
            self._make_zone("Asset", ZoneType.critical_asset, min_x, min_y, mid_x, mid_y),
            self._make_zone("Exclusion", ZoneType.exclusion, mid_x, min_y, max_x, mid_y),
        ]
        out = tmp_path / "zone_all_types.png"

        result = render_coverage_map(site, coverage, out, zones=zones)

        assert result.exists()
        assert Image.open(out).format == "PNG"

    def test_empty_zones_list_renders(self, flat_dem_path, tmp_path):
        """An empty zones list must not raise and must produce a valid file."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "zone_empty.png"

        result = render_coverage_map(site, coverage, out, zones=[])

        assert result.exists()

    def test_zones_none_renders(self, flat_dem_path, tmp_path):
        """zones=None (default) must not raise."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "zone_none.png"

        result = render_coverage_map(site, coverage, out, zones=None)

        assert result.exists()

    def test_multipolygon_zone_renders(self, flat_dem_path, tmp_path):
        """A zone with MultiPolygon geometry must render without error."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        poly1 = Polygon([(min_x, min_y), (mid_x, min_y), (mid_x, mid_y), (min_x, mid_y)])
        poly2 = Polygon([(mid_x, mid_y), (max_x, mid_y), (max_x, max_y), (mid_x, max_y)])
        zone = Zone(
            name="Split Asset",
            zone_type=ZoneType.critical_asset,
            geometry=MultiPolygon([poly1, poly2]),
        )
        out = tmp_path / "zone_multi.png"

        result = render_coverage_map(site, coverage, out, zones=[zone])

        assert result.exists()

    def test_zones_and_boundary_combined(self, flat_dem_path, tmp_path):
        """zones and boundary can be rendered together without error."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        zone = self._make_zone("HQ", ZoneType.critical_asset, min_x, min_y, mid_x, mid_y)
        out = tmp_path / "zone_and_boundary.png"

        result = render_coverage_map(site, coverage, out, boundary=boundary, zones=[zone])

        assert result.exists()

    def test_duplicate_zone_types_single_legend_entry(self, flat_dem_path, tmp_path):
        """Two zones of the same type produce only one legend entry (no error)."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        mid_x = (min_x + max_x) / 2
        zone1 = self._make_zone("Asset A", ZoneType.critical_asset, min_x, min_y, mid_x, max_y)
        zone2 = self._make_zone("Asset B", ZoneType.critical_asset, mid_x, min_y, max_x, max_y)
        out = tmp_path / "zone_dup_type.png"

        result = render_coverage_map(site, coverage, out, zones=[zone1, zone2])

        assert result.exists()

    def test_unknown_zone_type_warns_and_skips(self, flat_dem_path, tmp_path, monkeypatch):
        """A zone type with no entry in _ZONE_STYLE emits a warning and skips that zone."""
        import salus.report.maps as maps_module

        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        min_x, max_x, min_y, max_y = site.extent
        mid_x = (min_x + max_x) / 2
        zone = self._make_zone("Test", ZoneType.inner, min_x, min_y, mid_x, max_y)
        # Remove inner from the style dict to simulate an unknown/future type
        patched = {k: v for k, v in maps_module._ZONE_STYLE.items() if k != ZoneType.inner}
        monkeypatch.setattr(maps_module, "_ZONE_STYLE", patched)
        out = tmp_path / "unknown_type.png"

        with pytest.warns(UserWarning, match="No render style defined"):
            result = render_coverage_map(site, coverage, out, zones=[zone])

        assert result.exists()
