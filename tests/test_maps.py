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
from salus.models.sensor import SensorType
from salus.models.zone import Zone, ZoneType
from salus.report.maps import (
    _hillshade,
    render_composite_coverage_map,
    render_coverage_map,
    render_gap_map,
    render_layer_coverage_maps,
    render_redundancy_map,
)


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


# ---------------------------------------------------------------------------
# Helpers shared by S5-4 tests
# ---------------------------------------------------------------------------


def _two_layer_coverages(site):
    radar = np.zeros(site.dem.shape, dtype=bool)
    radar[:50, :] = True
    acoustic = np.zeros(site.dem.shape, dtype=bool)
    acoustic[:, 50:] = True
    return {SensorType.Radar: radar, SensorType.Acoustic: acoustic}


# ---------------------------------------------------------------------------
# render_layer_coverage_maps
# ---------------------------------------------------------------------------


class TestRenderLayerCoverageMaps:
    def test_returns_dict_keyed_by_sensor_type(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        result = render_layer_coverage_maps(site, layers, tmp_path)
        assert set(result.keys()) == set(layers.keys())

    def test_each_value_is_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        result = render_layer_coverage_maps(site, layers, tmp_path)
        for path in result.values():
            assert isinstance(path, Path)

    def test_each_file_exists(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        result = render_layer_coverage_maps(site, layers, tmp_path)
        for path in result.values():
            assert path.exists()

    def test_each_file_is_valid_png(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        result = render_layer_coverage_maps(site, layers, tmp_path)
        for path in result.values():
            img = Image.open(path)
            assert img.format == "PNG"

    def test_output_dir_created_if_missing(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        new_dir = tmp_path / "new_subdir"
        assert not new_dir.exists()
        render_layer_coverage_maps(site, layers, new_dir)
        assert new_dir.exists()

    def test_empty_layers_returns_empty_dict(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        result = render_layer_coverage_maps(site, {}, tmp_path)
        assert result == {}

    def test_all_four_sensor_types_accepted(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        cov = np.ones(site.dem.shape, dtype=bool)
        layers = {
            SensorType.Radar: cov,
            SensorType.EO_IR: cov,
            SensorType.RF: cov,
            SensorType.Acoustic: cov,
        }
        result = render_layer_coverage_maps(site, layers, tmp_path)
        assert len(result) == 4
        for path in result.values():
            assert path.exists()

    def test_sensor_positions_accepted(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        cx = site.origin_x + 50.0
        cy = site.origin_y - 50.0
        result = render_layer_coverage_maps(site, layers, tmp_path, sensor_positions=[(cx, cy)])
        for path in result.values():
            assert path.exists()


# ---------------------------------------------------------------------------
# render_composite_coverage_map
# ---------------------------------------------------------------------------


class TestRenderCompositeCoverageMap:
    def test_returns_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        out = tmp_path / "composite.png"
        result = render_composite_coverage_map(site, layers, out)
        assert result == out

    def test_file_exists(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        out = tmp_path / "composite.png"
        render_composite_coverage_map(site, layers, out)
        assert out.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        out = tmp_path / "composite.png"
        render_composite_coverage_map(site, layers, out)
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.size[0] > 0

    def test_empty_layers_renders(self, flat_dem_path, tmp_path):
        """Empty layer dict produces a hillshade-only map without error."""
        site = load_dem(flat_dem_path)
        out = tmp_path / "empty_composite.png"
        render_composite_coverage_map(site, {}, out)
        assert out.exists()

    def test_accepts_str_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        out = str(tmp_path / "composite_str.png")
        result = render_composite_coverage_map(site, layers, out)
        assert isinstance(result, Path)
        assert result.exists()

    def test_with_sensor_positions_and_boundary(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        out = tmp_path / "composite_annotated.png"
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
        cx, cy = site.origin_x + 50.0, site.origin_y - 50.0
        render_composite_coverage_map(
            site, layers, out, sensor_positions=[(cx, cy)], boundary=boundary
        )
        assert out.exists()

    def test_no_crs_skips_basemap_with_warning(self, flat_dem_path, tmp_path):
        """site.crs_epsg=None emits a warning but still produces a PNG."""
        import warnings as _warnings

        site = load_dem(flat_dem_path)
        object.__setattr__(site, "crs_epsg", None)
        layers = _two_layer_coverages(site)
        out = tmp_path / "no_crs.png"
        with _warnings.catch_warnings(record=True):
            _warnings.simplefilter("always")
            render_composite_coverage_map(site, layers, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# render_gap_map
# ---------------------------------------------------------------------------


class TestRenderGapMap:
    def test_returns_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        gaps = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "gaps.png"
        result = render_gap_map(site, composite, gaps, out)
        assert result == out

    def test_file_exists(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        gaps = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "gaps.png"
        render_gap_map(site, composite, gaps, out)
        assert out.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        gaps = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "gaps.png"
        render_gap_map(site, composite, gaps, out)
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.size[0] > 0

    def test_all_gaps_renders(self, flat_dem_path, tmp_path):
        """All cells as gaps (no coverage) must still render without error."""
        site = load_dem(flat_dem_path)
        composite = np.zeros(site.dem.shape, dtype=bool)
        gaps = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "all_gaps.png"
        render_gap_map(site, composite, gaps, out)
        assert out.exists()

    def test_no_gaps_renders(self, flat_dem_path, tmp_path):
        """No gaps (full coverage) must still render without error."""
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        gaps = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "no_gaps.png"
        render_gap_map(site, composite, gaps, out)
        assert out.exists()

    def test_partial_gaps_renders(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        composite[40:60, 40:60] = False
        gaps = ~composite
        out = tmp_path / "partial_gaps.png"
        render_gap_map(site, composite, gaps, out)
        assert out.exists()

    def test_accepts_str_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        gaps = np.zeros(site.dem.shape, dtype=bool)
        out = str(tmp_path / "gaps_str.png")
        result = render_gap_map(site, composite, gaps, out)
        assert isinstance(result, Path)

    def test_with_boundary_and_zones(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        composite[30:50, 30:50] = False
        gaps = ~composite
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
        zone = Zone(
            name="HQ",
            zone_type=ZoneType.critical_asset,
            geometry=Polygon(
                [(min_x, min_y), (min_x + 30, min_y), (min_x + 30, min_y + 30), (min_x, min_y + 30)]
            ),
        )
        out = tmp_path / "gap_annotated.png"
        render_gap_map(site, composite, gaps, out, boundary=boundary, zones=[zone])
        assert out.exists()

    def test_creates_parent_dir(self, flat_dem_path, tmp_path):
        """D-106: parent directory is created if it does not exist."""
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        gaps = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "new_subdir" / "gaps.png"
        assert not out.parent.exists()
        render_gap_map(site, composite, gaps, out)
        assert out.exists()


class TestRenderCompositeCoverageMapMkdir:
    def test_creates_parent_dir(self, flat_dem_path, tmp_path):
        """D-105: parent directory is created if it does not exist."""
        site = load_dem(flat_dem_path)
        layers = _two_layer_coverages(site)
        out = tmp_path / "new_subdir" / "composite.png"
        assert not out.parent.exists()
        render_composite_coverage_map(site, layers, out)
        assert out.exists()


class TestRenderCoverageMapMkdir:
    def test_creates_parent_dir(self, flat_dem_path, tmp_path):
        """D-109: render_coverage_map creates parent directory if it does not exist."""
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "new_subdir" / "cov.png"
        assert not out.parent.exists()
        render_coverage_map(site, coverage, out)
        assert out.exists()


class TestRenderGapMapGuards:
    def test_shape_mismatch_raises(self, flat_dem_path, tmp_path):
        """D-108: mismatched composite/gaps shapes raise ValueError."""
        site = load_dem(flat_dem_path)
        composite = np.ones(site.dem.shape, dtype=bool)
        gaps = np.zeros((site.dem.shape[0] + 1, site.dem.shape[1]), dtype=bool)
        out = tmp_path / "gaps.png"
        with pytest.raises(ValueError, match="composite shape"):
            render_gap_map(site, composite, gaps, out)

    def test_zero_size_gaps_raises(self, flat_dem_path, tmp_path):
        """D-107: zero-size gaps array raises ValueError."""
        site = load_dem(flat_dem_path)
        composite = np.ones((0, 0), dtype=bool)
        gaps = np.zeros((0, 0), dtype=bool)
        out = tmp_path / "gaps.png"
        with pytest.raises(ValueError, match="zero elements"):
            render_gap_map(site, composite, gaps, out)


class TestRenderLayerCoverageMapsGuards:
    def test_zero_size_coverage_raises(self, flat_dem_path, tmp_path):
        """D-107: zero-size coverage array raises ValueError."""
        site = load_dem(flat_dem_path)
        layers = {SensorType.Radar: np.ones((0, 0), dtype=bool)}
        with pytest.raises(ValueError, match="zero elements"):
            render_layer_coverage_maps(site, layers, tmp_path)


class TestRenderRedundancyMap:
    def _make_redundancy(self, site: object, value: int = 0) -> np.ndarray:
        from salus.models.site import SiteModel

        assert isinstance(site, SiteModel)
        return np.full(site.dem.shape, value, dtype=np.intp)

    def test_returns_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        rmap = self._make_redundancy(site, value=1)
        out = tmp_path / "redundancy.png"
        result = render_redundancy_map(site, rmap, out)
        assert isinstance(result, Path)

    def test_file_exists(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        rmap = self._make_redundancy(site, value=2)
        out = tmp_path / "redundancy.png"
        render_redundancy_map(site, rmap, out)
        assert out.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        rmap = self._make_redundancy(site, value=1)
        out = tmp_path / "redundancy.png"
        render_redundancy_map(site, rmap, out)
        img = Image.open(out)
        assert img.format == "PNG"

    def test_all_zeros_renders(self, flat_dem_path, tmp_path):
        """All uncovered cells (0) should still render without error."""
        site = load_dem(flat_dem_path)
        rmap = self._make_redundancy(site, value=0)
        out = tmp_path / "redundancy_zeros.png"
        render_redundancy_map(site, rmap, out)
        assert out.exists()

    def test_high_redundancy_clamped(self, flat_dem_path, tmp_path):
        """Values above 3 are clamped to 3 (dark green bucket)."""
        site = load_dem(flat_dem_path)
        rmap = np.full(site.dem.shape, 10, dtype=np.intp)
        out = tmp_path / "redundancy_high.png"
        render_redundancy_map(site, rmap, out)
        assert out.exists()

    def test_mixed_values_renders(self, flat_dem_path, tmp_path):
        """Array with values 0, 1, 2, 3 renders without error."""
        site = load_dem(flat_dem_path)
        rmap = np.zeros(site.dem.shape, dtype=np.intp)
        h, w = rmap.shape
        rmap[: h // 4, :] = 0
        rmap[h // 4 : h // 2, :] = 1
        rmap[h // 2 : 3 * h // 4, :] = 2
        rmap[3 * h // 4 :, :] = 3
        out = tmp_path / "redundancy_mixed.png"
        render_redundancy_map(site, rmap, out)
        assert out.exists()

    def test_accepts_str_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        rmap = self._make_redundancy(site, value=1)
        out = str(tmp_path / "redundancy_str.png")
        result = render_redundancy_map(site, rmap, out)
        assert isinstance(result, Path)

    def test_creates_parent_dir(self, flat_dem_path, tmp_path):
        """Parent directory is created if it does not exist."""
        site = load_dem(flat_dem_path)
        rmap = self._make_redundancy(site, value=1)
        out = tmp_path / "new_subdir" / "redundancy.png"
        assert not out.parent.exists()
        render_redundancy_map(site, rmap, out)
        assert out.exists()

    def test_with_sensor_positions_and_boundary(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        rmap = self._make_redundancy(site, value=2)
        min_x, max_x, min_y, max_y = site.extent
        boundary = Polygon([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
        out = tmp_path / "redundancy_annotated.png"
        render_redundancy_map(
            site,
            rmap,
            out,
            sensor_positions=[(cx, cy)],
            boundary=boundary,
        )
        assert out.exists()

    def test_non_2d_raises(self, flat_dem_path, tmp_path):
        """Non-2D redundancy_map raises ValueError."""
        site = load_dem(flat_dem_path)
        rmap = np.ones(site.dem.size, dtype=np.intp)  # 1-D
        out = tmp_path / "redundancy.png"
        with pytest.raises(ValueError, match="2-D"):
            render_redundancy_map(site, rmap, out)

    def test_zero_size_raises(self, flat_dem_path, tmp_path):
        """Zero-size array raises ValueError."""
        site = load_dem(flat_dem_path)
        rmap = np.zeros((0, 0), dtype=np.intp)
        out = tmp_path / "redundancy.png"
        with pytest.raises(ValueError, match="zero elements"):
            render_redundancy_map(site, rmap, out)

    def test_negative_values_raise(self, flat_dem_path, tmp_path):
        """D-112: negative sentinel values raise ValueError."""
        site = load_dem(flat_dem_path)
        rmap = np.full(site.dem.shape, -1, dtype=np.intp)
        out = tmp_path / "redundancy.png"
        with pytest.raises(ValueError, match="negative values"):
            render_redundancy_map(site, rmap, out)

    def test_shape_mismatch_raises(self, flat_dem_path, tmp_path):
        """D-113: shape mismatch with DEM raises ValueError."""
        site = load_dem(flat_dem_path)
        rmap = np.ones((site.dem.shape[0] + 1, site.dem.shape[1]), dtype=np.intp)
        out = tmp_path / "redundancy.png"
        with pytest.raises(ValueError, match="does not match"):
            render_redundancy_map(site, rmap, out)

    def test_float_dtype_raises(self, flat_dem_path, tmp_path):
        """D-114: float dtype raises ValueError."""
        site = load_dem(flat_dem_path)
        rmap = np.ones(site.dem.shape, dtype=np.float64)
        out = tmp_path / "redundancy.png"
        with pytest.raises(ValueError, match="integer dtype"):
            render_redundancy_map(site, rmap, out)
