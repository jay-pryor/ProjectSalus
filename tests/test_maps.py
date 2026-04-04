"""Tests for coverage map rendering."""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pytest
from PIL import Image

matplotlib.use("Agg")  # Non-interactive backend — must be set before importing pyplot

from shapely.geometry import MultiPolygon, Polygon

from salus.engine.threat_corridor import CorridorResult
from salus.engine.trajectory import DetectionEvent, TrajectoryResult
from salus.ingest.terrain import load_dem
from salus.models.sensor import SensorType
from salus.models.threat import DroneTrajectory, ThreatCorridor, TrajectoryWaypoint
from salus.models.zone import Zone, ZoneType
from salus.report.maps import (
    _hillshade,
    render_composite_coverage_map,
    render_corridor_overlay_map,
    render_corridor_polar_diagram,
    render_coverage_map,
    render_detection_without_engagement_map,
    render_effector_coverage_map,
    render_gap_map,
    render_layer_coverage_maps,
    render_redundancy_map,
    render_trajectory_map,
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
        site = load_dem(flat_dem_path)
        object.__setattr__(site, "crs_epsg", None)
        layers = _two_layer_coverages(site)
        out = tmp_path / "no_crs.png"
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
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


# ---------------------------------------------------------------------------
# Shared helpers for corridor map tests
# ---------------------------------------------------------------------------


def _make_corridor_result(bearing_deg: float, coverage_pct: float) -> CorridorResult:
    """Helper to construct a CorridorResult with a given bearing and coverage."""
    corridor = ThreatCorridor(bearing_deg=bearing_deg, altitude_m=50.0, start_distance_m=500.0)
    return CorridorResult(
        corridor=corridor,
        threat_name="Test Threat",
        coverage_pct=coverage_pct,
        first_detection_distance_m=250.0 if coverage_pct > 0 else None,
        last_gap_before_target_m=0.0 if coverage_pct == 100.0 else 50.0,
        time_in_coverage_s=10.0,
        covered_cells=5,
        total_cells=10,
    )


# ---------------------------------------------------------------------------
# render_corridor_overlay_map (S6-4)
# ---------------------------------------------------------------------------


class TestRenderCorridorOverlayMap:
    def _site_and_coverage(self, flat_dem_path):
        from salus.ingest.terrain import load_dem

        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        return site, coverage

    def _centre(self, site):
        cx = site.origin_x + site.cols * site.resolution / 2
        cy = site.origin_y - site.rows * site.resolution / 2
        return (cx, cy)

    def test_returns_path(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        results = [_make_corridor_result(b, 80.0) for b in [0.0, 90.0, 180.0, 270.0]]
        out = tmp_path / "corridor_overlay.png"
        result = render_corridor_overlay_map(site, cov, results, self._centre(site), out)
        assert result == out

    def test_file_exists(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        results = [_make_corridor_result(b, 50.0) for b in [0.0, 90.0]]
        out = tmp_path / "overlay.png"
        render_corridor_overlay_map(site, cov, results, self._centre(site), out)
        assert out.exists()

    def test_valid_png(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        results = [_make_corridor_result(0.0, 100.0)]
        out = tmp_path / "overlay.png"
        render_corridor_overlay_map(site, cov, results, self._centre(site), out)
        img = Image.open(out)
        assert img.format == "PNG"

    def test_empty_corridor_list_renders(self, flat_dem_path, tmp_path):
        """Empty corridor list is allowed — just renders composite background."""
        site, cov = self._site_and_coverage(flat_dem_path)
        out = tmp_path / "overlay_empty.png"
        render_corridor_overlay_map(site, cov, [], self._centre(site), out)
        assert out.exists()

    def test_creates_parent_dir(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        out = tmp_path / "new_dir" / "overlay.png"
        render_corridor_overlay_map(site, cov, [], self._centre(site), out)
        assert out.exists()

    def test_str_path_accepted(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        out = str(tmp_path / "overlay_str.png")
        result = render_corridor_overlay_map(site, cov, [], self._centre(site), out)
        assert isinstance(result, Path)

    def test_non_2d_composite_raises(self, flat_dem_path, tmp_path):
        site, _ = self._site_and_coverage(flat_dem_path)
        bad = np.ones((10,), dtype=bool)
        out = tmp_path / "overlay.png"
        with pytest.raises(ValueError, match="2D"):
            render_corridor_overlay_map(site, bad, [], self._centre(site), out)

    def test_empty_composite_raises(self, flat_dem_path, tmp_path):
        site, _ = self._site_and_coverage(flat_dem_path)
        bad = np.ones((0, 0), dtype=bool)
        out = tmp_path / "overlay.png"
        with pytest.raises(ValueError, match="empty"):
            render_corridor_overlay_map(site, bad, [], self._centre(site), out)

    def test_shape_mismatch_raises(self, flat_dem_path, tmp_path):
        site, _ = self._site_and_coverage(flat_dem_path)
        bad = np.ones((5, 5), dtype=bool)
        out = tmp_path / "overlay.png"
        with pytest.raises(ValueError, match="shape"):
            render_corridor_overlay_map(site, bad, [], self._centre(site), out)

    def test_nan_protected_point_raises(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        out = tmp_path / "overlay.png"
        with pytest.raises(ValueError, match="finite"):
            render_corridor_overlay_map(site, cov, [], (float("nan"), 0.0), out)


# ---------------------------------------------------------------------------
# render_corridor_polar_diagram (S6-4)
# ---------------------------------------------------------------------------


class TestRenderCorridorPolarDiagram:
    def test_returns_path(self, tmp_path):
        results = [_make_corridor_result(b, float(b) / 3.6) for b in range(0, 360, 10)]
        out = tmp_path / "polar.png"
        result = render_corridor_polar_diagram(results, out)
        assert result == out

    def test_file_exists(self, tmp_path):
        results = [_make_corridor_result(b, 50.0) for b in [0.0, 90.0, 180.0, 270.0]]
        out = tmp_path / "polar.png"
        render_corridor_polar_diagram(results, out)
        assert out.exists()

    def test_valid_png(self, tmp_path):
        results = [_make_corridor_result(b, 75.0) for b in [0.0, 90.0, 180.0, 270.0]]
        out = tmp_path / "polar.png"
        render_corridor_polar_diagram(results, out)
        img = Image.open(out)
        assert img.format == "PNG"

    def test_single_corridor_renders(self, tmp_path):
        results = [_make_corridor_result(0.0, 100.0)]
        out = tmp_path / "polar_single.png"
        render_corridor_polar_diagram(results, out)
        assert out.exists()

    def test_creates_parent_dir(self, tmp_path):
        results = [_make_corridor_result(0.0, 50.0)]
        out = tmp_path / "new_sub" / "polar.png"
        render_corridor_polar_diagram(results, out)
        assert out.exists()

    def test_str_path_accepted(self, tmp_path):
        results = [_make_corridor_result(0.0, 0.0)]
        out = str(tmp_path / "polar_str.png")
        result = render_corridor_polar_diagram(results, out)
        assert isinstance(result, Path)

    def test_empty_results_raises(self, tmp_path):
        out = tmp_path / "polar.png"
        with pytest.raises(ValueError, match="empty"):
            render_corridor_polar_diagram([], out)

    def test_all_zero_coverage(self, tmp_path):
        """0% coverage for all bearings renders without error."""
        results = [_make_corridor_result(b, 0.0) for b in [0.0, 90.0, 180.0, 270.0]]
        out = tmp_path / "polar_zero.png"
        render_corridor_polar_diagram(results, out)
        assert out.exists()

    def test_all_100_coverage(self, tmp_path):
        """100% coverage for all bearings renders without error."""
        results = [_make_corridor_result(b, 100.0) for b in [0.0, 90.0, 180.0, 270.0]]
        out = tmp_path / "polar_full.png"
        render_corridor_polar_diagram(results, out)
        assert out.exists()

    def test_duplicate_bearings_raises(self, tmp_path):
        """Two results with the same bearing_deg produce bar_width=0 → ValueError."""
        results = [
            _make_corridor_result(90.0, 50.0),
            _make_corridor_result(90.0, 75.0),
        ]
        out = tmp_path / "polar_dup.png"
        with pytest.raises(ValueError, match="duplicate bearings"):
            render_corridor_polar_diagram(results, out)


# ---------------------------------------------------------------------------
# Helpers for trajectory map tests
# ---------------------------------------------------------------------------


def _make_trajectory_result(
    time_to_asset_s: float = 10.0,
    time_in_detection_s: float = 5.0,
    with_events: bool = True,
) -> TrajectoryResult:
    """Construct a minimal TrajectoryResult for rendering tests."""
    events: tuple[DetectionEvent, ...]
    if with_events:
        event = DetectionEvent(
            sensor_name="TestSensor",
            time_s=2.0,
            position_x=500050.0,
            position_y=6100080.0,
            position_z_agl=5.0,
            distance_to_asset_m=30.0,
            segment_index=0,
        )
        events = (event,)
    else:
        events = ()
    first = events[0] if events else None
    time_undetected = time_to_asset_s - time_in_detection_s
    return TrajectoryResult(
        detection_events=events,
        first_detection=first,
        time_to_asset_s=time_to_asset_s,
        time_in_detection_s=time_in_detection_s,
        time_undetected_s=time_undetected,
        asset_reached_undetected=time_in_detection_s == 0.0,
        last_gap_before_asset_m=0.0 if time_in_detection_s > 0 else 10.0,
    )


def _make_drone_trajectory(
    x_start: float = 500050.0,
    y_start: float = 6100090.0,
    x_end: float = 500050.0,
    y_end: float = 6100050.0,
) -> DroneTrajectory:
    """Construct a 2-waypoint DroneTrajectory inside the flat DEM extent."""
    return DroneTrajectory(
        waypoints=[
            TrajectoryWaypoint(x=x_start, y=y_start, z_agl=10.0),
            TrajectoryWaypoint(x=x_end, y=y_end, z_agl=0.0),
        ],
        speed_ms=10.0,
    )


# ---------------------------------------------------------------------------
# render_trajectory_map (S6.5-1)
# ---------------------------------------------------------------------------


class TestRenderTrajectoryMap:
    def _site_and_coverage(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        return site, coverage

    def _centre(self, site):
        cx = site.origin_x + site.cols * site.resolution / 2.0
        cy = site.origin_y - site.rows * site.resolution / 2.0
        return (cx, cy)

    def test_returns_path(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result()
        out = tmp_path / "traj_map.png"
        result = render_trajectory_map(site, cov, [(traj, result_obj)], self._centre(site), out)
        assert result == out

    def test_file_exists(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result()
        out = tmp_path / "traj_map.png"
        render_trajectory_map(site, cov, [(traj, result_obj)], self._centre(site), out)
        assert out.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result()
        out = tmp_path / "traj_map.png"
        render_trajectory_map(site, cov, [(traj, result_obj)], self._centre(site), out)
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.size[0] > 0

    def test_multiple_trajectories(self, flat_dem_path, tmp_path):
        """Multiple (trajectory, result) pairs render without error."""
        site, cov = self._site_and_coverage(flat_dem_path)
        pairs = [
            (_make_drone_trajectory(), _make_trajectory_result(time_in_detection_s=2.0)),
            (
                _make_drone_trajectory(x_start=500060.0),
                _make_trajectory_result(time_in_detection_s=8.0),
            ),
        ]
        out = tmp_path / "traj_multi.png"
        render_trajectory_map(site, cov, pairs, self._centre(site), out)
        assert out.exists()

    def test_no_detection_events(self, flat_dem_path, tmp_path):
        """Trajectory with no detection events renders without error."""
        site, cov = self._site_and_coverage(flat_dem_path)
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result(time_in_detection_s=0.0, with_events=False)
        out = tmp_path / "traj_no_events.png"
        render_trajectory_map(site, cov, [(traj, result_obj)], self._centre(site), out)
        assert out.exists()

    def test_accepts_str_path(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result()
        out = str(tmp_path / "traj_str.png")
        result = render_trajectory_map(site, cov, [(traj, result_obj)], self._centre(site), out)
        assert isinstance(result, Path)

    def test_creates_parent_dir(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result()
        out = tmp_path / "new_sub" / "traj_map.png"
        assert not out.parent.exists()
        render_trajectory_map(site, cov, [(traj, result_obj)], self._centre(site), out)
        assert out.exists()

    def test_empty_trajectory_results_raises(self, flat_dem_path, tmp_path):
        site, cov = self._site_and_coverage(flat_dem_path)
        out = tmp_path / "traj_empty.png"
        with pytest.raises(ValueError, match="empty"):
            render_trajectory_map(site, cov, [], self._centre(site), out)

    def test_with_sensor_positions(self, flat_dem_path, tmp_path):
        """sensor_positions are drawn without error."""
        site, cov = self._site_and_coverage(flat_dem_path)
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result()
        cx, cy = self._centre(site)
        out = tmp_path / "traj_sensors.png"
        render_trajectory_map(
            site, cov, [(traj, result_obj)], (cx, cy), out, sensor_positions=[(cx, cy)]
        )
        assert out.exists()

    def test_all_undetected(self, flat_dem_path, tmp_path):
        """Asset reached undetected still renders (single-value normalisation)."""
        site, cov = self._site_and_coverage(flat_dem_path)
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result(time_in_detection_s=0.0, with_events=False)
        out = tmp_path / "traj_undetected.png"
        render_trajectory_map(site, cov, [(traj, result_obj)], self._centre(site), out)
        assert out.exists()


# ---------------------------------------------------------------------------
# render_corridor_polar_diagram — trajectory_results_and_bearings extension (S6.5-1)
# ---------------------------------------------------------------------------


class TestRenderCorridorPolarDiagramTrajectoryOverlay:
    def test_trajectory_only_renders(self, tmp_path):
        """trajectory_results_and_bearings alone (empty corridor_results) renders."""
        traj_result = _make_trajectory_result(time_in_detection_s=3.0)
        pairs = [(0.0, traj_result), (90.0, traj_result), (180.0, traj_result)]
        out = tmp_path / "polar_traj_only.png"
        render_corridor_polar_diagram([], out, trajectory_results_and_bearings=pairs)
        assert out.exists()

    def test_trajectory_only_valid_png(self, tmp_path):
        traj_result = _make_trajectory_result(time_in_detection_s=3.0)
        pairs = [(45.0, traj_result), (225.0, traj_result)]
        out = tmp_path / "polar_traj_png.png"
        render_corridor_polar_diagram([], out, trajectory_results_and_bearings=pairs)
        img = Image.open(out)
        assert img.format == "PNG"

    def test_combined_corridor_and_trajectory(self, tmp_path):
        """Both corridor and trajectory data render together without error."""
        corridor_results = [_make_corridor_result(0.0, 60.0), _make_corridor_result(180.0, 80.0)]
        traj_result = _make_trajectory_result(time_in_detection_s=4.0)
        pairs = [(90.0, traj_result), (270.0, traj_result)]
        out = tmp_path / "polar_combined.png"
        render_corridor_polar_diagram(corridor_results, out, trajectory_results_and_bearings=pairs)
        assert out.exists()

    def test_empty_both_raises(self, tmp_path):
        """Both empty raises ValueError."""
        out = tmp_path / "polar_both_empty.png"
        with pytest.raises(ValueError, match="empty"):
            render_corridor_polar_diagram([], out, trajectory_results_and_bearings=None)

    def test_zero_time_to_asset(self, tmp_path):
        """time_to_asset_s=0 is handled without division by zero."""
        traj_result = TrajectoryResult(
            detection_events=(),
            first_detection=None,
            time_to_asset_s=0.0,
            time_in_detection_s=0.0,
            time_undetected_s=0.0,
            asset_reached_undetected=True,
            last_gap_before_asset_m=0.0,
        )
        out = tmp_path / "polar_zero_time.png"
        render_corridor_polar_diagram([], out, trajectory_results_and_bearings=[(0.0, traj_result)])
        assert out.exists()

    def test_returns_path(self, tmp_path):
        traj_result = _make_trajectory_result()
        out = tmp_path / "polar_traj_ret.png"
        result = render_corridor_polar_diagram(
            [], out, trajectory_results_and_bearings=[(0.0, traj_result)]
        )
        assert result == out


# ---------------------------------------------------------------------------
# render_adversarial_map (S6.6-3)
# ---------------------------------------------------------------------------


class TestRenderAdversarialMap:
    def _setup(self, flat_dem_path):
        from salus.engine.path_planner import build_detection_cost_grid

        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        cost_grid = build_detection_cost_grid(site, [], altitude_bands_m=[50.0])
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result()
        cx = site.origin_x + site.cols * site.resolution / 2.0
        cy = site.origin_y - site.rows * site.resolution / 2.0
        return site, coverage, cost_grid, traj, result_obj, (cx, cy)

    def test_returns_path(self, flat_dem_path, tmp_path):
        from salus.report.maps import render_adversarial_map

        site, cov, cost_grid, traj, result_obj, centre = self._setup(flat_dem_path)
        out = tmp_path / "adv_map.png"
        result = render_adversarial_map(site, cov, cost_grid, traj, result_obj, centre, out)
        assert result == out

    def test_file_exists(self, flat_dem_path, tmp_path):
        from salus.report.maps import render_adversarial_map

        site, cov, cost_grid, traj, result_obj, centre = self._setup(flat_dem_path)
        out = tmp_path / "adv_map.png"
        render_adversarial_map(site, cov, cost_grid, traj, result_obj, centre, out)
        assert out.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        from salus.report.maps import render_adversarial_map

        site, cov, cost_grid, traj, result_obj, centre = self._setup(flat_dem_path)
        out = tmp_path / "adv_map.png"
        render_adversarial_map(site, cov, cost_grid, traj, result_obj, centre, out)
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.size[0] > 0

    def test_creates_parent_dir(self, flat_dem_path, tmp_path):
        from salus.report.maps import render_adversarial_map

        site, cov, cost_grid, traj, result_obj, centre = self._setup(flat_dem_path)
        out = tmp_path / "new_sub" / "adv_map.png"
        assert not out.parent.exists()
        render_adversarial_map(site, cov, cost_grid, traj, result_obj, centre, out)
        assert out.exists()

    def test_accepts_str_path(self, flat_dem_path, tmp_path):
        from salus.report.maps import render_adversarial_map

        site, cov, cost_grid, traj, result_obj, centre = self._setup(flat_dem_path)
        out = str(tmp_path / "adv_str.png")
        result = render_adversarial_map(site, cov, cost_grid, traj, result_obj, centre, out)
        assert isinstance(result, Path)

    def test_with_sensor_positions(self, flat_dem_path, tmp_path):
        from salus.report.maps import render_adversarial_map

        site, cov, cost_grid, traj, result_obj, centre = self._setup(flat_dem_path)
        out = tmp_path / "adv_sensors.png"
        render_adversarial_map(
            site, cov, cost_grid, traj, result_obj, centre, out, sensor_positions=[centre]
        )
        assert out.exists()

    def test_nonzero_cost_grid(self, flat_dem_path, tmp_path):
        """Cost grid with nonzero values renders the detection heatmap without error."""
        from pathlib import Path as PyPath

        from salus.engine.path_planner import build_detection_cost_grid
        from salus.ingest.sensors import load_sensors
        from salus.models.scenario import SensorPlacement
        from salus.report.maps import render_adversarial_map

        site = load_dem(flat_dem_path)
        coverage = np.ones(site.dem.shape, dtype=bool)
        sensor_dir = PyPath(__file__).parent.parent / "src" / "salus" / "data" / "sensors"
        sensors_db = {s.name: s for s in load_sensors(sensor_dir)}
        sdef = sensors_db["Echodyne EchoGuard"]
        spl = SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=500050.0,
            position_y=6100050.0,
            bearing_deg=0.0,
        )
        cost_grid = build_detection_cost_grid(site, [(sdef, spl)], altitude_bands_m=[50.0])
        traj = _make_drone_trajectory()
        result_obj = _make_trajectory_result()
        cx = site.origin_x + site.cols * site.resolution / 2.0
        cy = site.origin_y - site.rows * site.resolution / 2.0
        out = tmp_path / "adv_nonzero.png"
        render_adversarial_map(site, coverage, cost_grid, traj, result_obj, (cx, cy), out)
        assert out.exists()


# ---------------------------------------------------------------------------
# S11-2: Effector coverage map tests
# ---------------------------------------------------------------------------


class TestRenderEffectorCoverageMap:
    """Tests for render_effector_coverage_map (S11-2)."""

    def test_returns_resolved_path(self, flat_dem_path, tmp_path):
        """Function must return the resolved output path."""
        site = load_dem(flat_dem_path)
        cov = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "effector.png"
        result = render_effector_coverage_map(site, cov, out)
        assert result == out.resolve()
        assert result.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        """Output must be a readable PNG image."""
        site = load_dem(flat_dem_path)
        cov = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "effector.png"
        render_effector_coverage_map(site, cov, out)
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.size[0] > 0

    def test_all_false_coverage_still_renders(self, flat_dem_path, tmp_path):
        """An all-False effector coverage array must still produce a valid PNG."""
        site = load_dem(flat_dem_path)
        cov = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "effector_empty.png"
        result = render_effector_coverage_map(site, cov, out)
        assert result.exists()
        img = Image.open(out)
        assert img.format == "PNG"

    def test_partial_coverage_renders(self, flat_dem_path, tmp_path):
        """Partial coverage must render without error."""
        site = load_dem(flat_dem_path)
        cov = np.zeros(site.dem.shape, dtype=bool)
        cov[:50, :50] = True
        out = tmp_path / "effector_partial.png"
        result = render_effector_coverage_map(site, cov, out)
        assert result.exists()

    def test_creates_parent_directory(self, flat_dem_path, tmp_path):
        """Missing parent directories must be created."""
        site = load_dem(flat_dem_path)
        cov = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "nested" / "dirs" / "effector.png"
        result = render_effector_coverage_map(site, cov, out)
        assert result.exists()

    def test_effector_positions_accepted(self, flat_dem_path, tmp_path):
        """effector_positions kwarg must be accepted without error."""
        site = load_dem(flat_dem_path)
        cov = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "effector_pos.png"
        cx = site.origin_x + site.cols * site.resolution / 2.0
        cy = site.origin_y - site.rows * site.resolution / 2.0
        result = render_effector_coverage_map(site, cov, out, effector_positions=[(cx, cy)])
        assert result.exists()

    def test_non_2d_raises(self, flat_dem_path, tmp_path):
        """Non-2D input must raise ValueError."""
        site = load_dem(flat_dem_path)
        bad_cov = np.ones(100, dtype=bool)
        out = tmp_path / "effector.png"
        with pytest.raises(ValueError, match="2-D"):
            render_effector_coverage_map(site, bad_cov, out)

    def test_zero_element_array_raises(self, flat_dem_path, tmp_path):
        """Zero-element array must raise ValueError."""
        site = load_dem(flat_dem_path)
        bad_cov = np.zeros((0, 0), dtype=bool)
        out = tmp_path / "effector.png"
        with pytest.raises(ValueError, match="zero elements"):
            render_effector_coverage_map(site, bad_cov, out)

    def test_custom_title_accepted(self, flat_dem_path, tmp_path):
        """Custom title kwarg must be accepted."""
        site = load_dem(flat_dem_path)
        cov = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "effector_title.png"
        result = render_effector_coverage_map(site, cov, out, title="My Effector Map")
        assert result.exists()

    def test_nan_dem_raises(self, flat_dem_path, tmp_path):
        """NaN values in site.dem must raise ValueError before rendering."""
        site = load_dem(flat_dem_path)
        site.dem[0, 0] = float("nan")
        cov = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "effector_nan.png"
        with pytest.raises(ValueError, match="NaN"):
            render_effector_coverage_map(site, cov, out)

    def test_shape_mismatch_vs_dem_raises(self, flat_dem_path, tmp_path):
        """effector_coverage shape != site.dem.shape must raise ValueError."""
        site = load_dem(flat_dem_path)
        bad_cov = np.ones((10, 10), dtype=bool)  # wrong shape
        out = tmp_path / "effector_shape.png"
        with pytest.raises(ValueError, match="shape"):
            render_effector_coverage_map(site, bad_cov, out)


class TestRenderDetectionWithoutEngagementMap:
    """Tests for render_detection_without_engagement_map (S11-2)."""

    def test_returns_resolved_path(self, flat_dem_path, tmp_path):
        """Function must return the resolved output path."""
        site = load_dem(flat_dem_path)
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "dwe_gap.png"
        result = render_detection_without_engagement_map(site, sensor, effector, out)
        assert result == out.resolve()
        assert result.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        """Output must be a readable PNG image."""
        site = load_dem(flat_dem_path)
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "dwe_gap.png"
        render_detection_without_engagement_map(site, sensor, effector, out)
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.size[0] > 0

    def test_full_gap_scenario_renders(self, flat_dem_path, tmp_path):
        """All sensor coverage, no effector coverage — worst-case gap — must render."""
        site = load_dem(flat_dem_path)
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "full_gap.png"
        result = render_detection_without_engagement_map(site, sensor, effector, out)
        assert result.exists()

    def test_no_gap_scenario_renders(self, flat_dem_path, tmp_path):
        """Full effector coverage matching sensor coverage — zero gap — must render."""
        site = load_dem(flat_dem_path)
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "no_gap.png"
        result = render_detection_without_engagement_map(site, sensor, effector, out)
        assert result.exists()

    def test_partial_gap_renders(self, flat_dem_path, tmp_path):
        """Partial gap (some cells covered by both, some only sensor) must render."""
        site = load_dem(flat_dem_path)
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.zeros(site.dem.shape, dtype=bool)
        effector[:50, :50] = True  # effectors only cover top-left quadrant
        out = tmp_path / "partial_gap.png"
        result = render_detection_without_engagement_map(site, sensor, effector, out)
        assert result.exists()

    def test_creates_parent_directory(self, flat_dem_path, tmp_path):
        """Missing parent directories must be created."""
        site = load_dem(flat_dem_path)
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "nested" / "dwe.png"
        result = render_detection_without_engagement_map(site, sensor, effector, out)
        assert result.exists()

    def test_sensor_and_effector_positions_accepted(self, flat_dem_path, tmp_path):
        """Both sensor_positions and effector_positions kwargs accepted without error."""
        site = load_dem(flat_dem_path)
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "dwe_pos.png"
        cx = site.origin_x + site.cols * site.resolution / 2.0
        cy = site.origin_y - site.rows * site.resolution / 2.0
        result = render_detection_without_engagement_map(
            site,
            sensor,
            effector,
            out,
            sensor_positions=[(cx, cy)],
            effector_positions=[(cx - 10.0, cy - 10.0)],
        )
        assert result.exists()

    def test_shape_mismatch_raises(self, flat_dem_path, tmp_path):
        """Shape mismatch between sensor_composite and effector_coverage must raise ValueError."""
        site = load_dem(flat_dem_path)
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.ones((10, 10), dtype=bool)  # wrong shape
        out = tmp_path / "dwe.png"
        with pytest.raises(ValueError, match="shape"):
            render_detection_without_engagement_map(site, sensor, effector, out)

    def test_zero_element_arrays_raise(self, flat_dem_path, tmp_path):
        """Zero-element arrays must raise ValueError."""
        site = load_dem(flat_dem_path)
        bad = np.zeros((0, 0), dtype=bool)
        out = tmp_path / "dwe.png"
        with pytest.raises(ValueError, match="zero elements"):
            render_detection_without_engagement_map(site, bad, bad, out)

    def test_no_sensor_coverage_renders(self, flat_dem_path, tmp_path):
        """Zero sensor coverage (nothing detected) must render without error."""
        site = load_dem(flat_dem_path)
        sensor = np.zeros(site.dem.shape, dtype=bool)
        effector = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "no_sensor.png"
        result = render_detection_without_engagement_map(site, sensor, effector, out)
        assert result.exists()

    def test_nan_dem_raises(self, flat_dem_path, tmp_path):
        """NaN values in site.dem must raise ValueError before rendering."""
        site = load_dem(flat_dem_path)
        site.dem[0, 0] = float("nan")
        sensor = np.ones(site.dem.shape, dtype=bool)
        effector = np.ones(site.dem.shape, dtype=bool)
        out = tmp_path / "dwe_nan.png"
        with pytest.raises(ValueError, match="NaN"):
            render_detection_without_engagement_map(site, sensor, effector, out)

    def test_shape_mismatch_vs_dem_raises(self, flat_dem_path, tmp_path):
        """sensor_composite shape != site.dem.shape must raise ValueError."""
        site = load_dem(flat_dem_path)
        bad = np.ones((10, 10), dtype=bool)  # wrong shape but they match each other
        out = tmp_path / "dwe_dem_shape.png"
        with pytest.raises(ValueError, match="shape"):
            render_detection_without_engagement_map(site, bad, bad, out)

    def test_empty_sensor_warns(self, flat_dem_path, tmp_path):
        """All-False sensor composite must emit a UserWarning about blank map."""
        site = load_dem(flat_dem_path)
        sensor = np.zeros(site.dem.shape, dtype=bool)
        effector = np.zeros(site.dem.shape, dtype=bool)
        out = tmp_path / "dwe_empty_warn.png"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            render_detection_without_engagement_map(site, sensor, effector, out)
        assert any(issubclass(w.category, UserWarning) for w in caught), (
            "Expected a UserWarning when sensor_composite is all-False"
        )
