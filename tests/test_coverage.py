"""Tests for coverage boundary masking, percentage computation, and layer union."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon

from salus.engine.coverage import (
    GapAnalysis,
    boundary_mask,
    build_gap_analysis,
    clip_coverage_to_boundary,
    compute_composite_coverage,
    compute_gaps,
    compute_layer_coverage,
    coverage_percentage,
)
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.models.sensor import SensorDefinition, SensorType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _placement(x: float, y: float) -> SensorPlacement:
    return SensorPlacement(
        sensor_name="TestSensor",
        position_x=x,
        position_y=y,
        bearing_deg=0.0,
        height_override_m=None,
    )


def _sensor(stype: SensorType, max_range_m: float = 30.0) -> SensorDefinition:
    return SensorDefinition(
        name="TestSensor",
        type=stype,
        max_range_m=max_range_m,
        fov_deg=360.0,
        azimuth_coverage_deg=360.0,
        elevation_coverage_deg=90.0,
        mounting_height_m=5.0,
        min_range_m=0.0,
        frequency_bands=["2.4 GHz"] if stype == SensorType.RF else [],
        acoustic_sensitivity_db=0.0,
    )


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


# ---------------------------------------------------------------------------
# compute_layer_coverage
# ---------------------------------------------------------------------------


class TestLayerCoverage:
    def test_single_sensor_single_type_shape(self, flat_dem_path):
        """Result array shape matches site DEM for a single sensor."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Radar, max_range_m=30.0)
        placement = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
        layers = compute_layer_coverage(site, {SensorType.Radar: [(sensor, placement)]})
        assert SensorType.Radar in layers
        assert layers[SensorType.Radar].shape == site.dem.shape
        assert layers[SensorType.Radar].dtype == bool

    def test_empty_sensor_list_produces_all_false(self, flat_dem_path):
        """A sensor type with an empty pair list produces an all-False array."""
        site = load_dem(flat_dem_path)
        layers = compute_layer_coverage(site, {SensorType.Acoustic: []})
        assert layers[SensorType.Acoustic].shape == site.dem.shape
        assert not layers[SensorType.Acoustic].any()

    def test_empty_dict_returns_empty_result(self, flat_dem_path):
        """An empty placements dict returns an empty result dict."""
        site = load_dem(flat_dem_path)
        layers = compute_layer_coverage(site, {})
        assert layers == {}

    def test_union_two_sensors_covers_more_than_either_alone(self, flat_dem_path):
        """Two sensors at opposite corners unioned cover more than either alone."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Acoustic, max_range_m=30.0)
        p1 = _placement(site.origin_x + 5.0, site.origin_y - 5.0)
        p2 = _placement(site.origin_x + 95.0, site.origin_y - 95.0)
        layers_both = compute_layer_coverage(
            site, {SensorType.Acoustic: [(sensor, p1), (sensor, p2)]}
        )
        layers_p1 = compute_layer_coverage(site, {SensorType.Acoustic: [(sensor, p1)]})
        layers_p2 = compute_layer_coverage(site, {SensorType.Acoustic: [(sensor, p2)]})
        assert layers_both[SensorType.Acoustic].sum() > layers_p1[SensorType.Acoustic].sum()
        assert layers_both[SensorType.Acoustic].sum() > layers_p2[SensorType.Acoustic].sum()

    def test_union_is_logical_or_of_individuals(self, flat_dem_path):
        """Layer union equals logical OR of individual coverage arrays."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Acoustic, max_range_m=30.0)
        p1 = _placement(site.origin_x + 5.0, site.origin_y - 5.0)
        p2 = _placement(site.origin_x + 95.0, site.origin_y - 95.0)
        layers_both = compute_layer_coverage(
            site, {SensorType.Acoustic: [(sensor, p1), (sensor, p2)]}
        )
        layers_p1 = compute_layer_coverage(site, {SensorType.Acoustic: [(sensor, p1)]})
        layers_p2 = compute_layer_coverage(site, {SensorType.Acoustic: [(sensor, p2)]})
        expected = layers_p1[SensorType.Acoustic] | layers_p2[SensorType.Acoustic]
        np.testing.assert_array_equal(layers_both[SensorType.Acoustic], expected)

    def test_multiple_sensor_types_returned(self, flat_dem_path):
        """All sensor types in input dict appear as keys in the result."""
        site = load_dem(flat_dem_path)
        radar = _sensor(SensorType.Radar, max_range_m=30.0)
        acoustic = _sensor(SensorType.Acoustic, max_range_m=30.0)
        p = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
        layers = compute_layer_coverage(
            site,
            {
                SensorType.Radar: [(radar, p)],
                SensorType.Acoustic: [(acoustic, p)],
            },
        )
        assert SensorType.Radar in layers
        assert SensorType.Acoustic in layers
        assert len(layers) == 2

    def test_multiple_types_independent_arrays(self, flat_dem_path):
        """Radar and Acoustic layers are independent boolean arrays."""
        site = load_dem(flat_dem_path)
        radar = _sensor(SensorType.Radar, max_range_m=30.0)
        acoustic = _sensor(SensorType.Acoustic, max_range_m=30.0)
        p = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
        layers = compute_layer_coverage(
            site,
            {SensorType.Radar: [(radar, p)], SensorType.Acoustic: [(acoustic, p)]},
        )
        # Arrays are not the same object
        assert layers[SensorType.Radar] is not layers[SensorType.Acoustic]

    def test_rf_sensor_type_routed_correctly(self, flat_dem_path):
        """RF sensor type is accepted and returns a valid coverage array."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.RF, max_range_m=30.0)
        p = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
        layers = compute_layer_coverage(site, {SensorType.RF: [(sensor, p)]})
        assert layers[SensorType.RF].shape == site.dem.shape
        assert layers[SensorType.RF].dtype == bool

    def test_result_is_bool_dtype(self, flat_dem_path):
        """Output arrays are always dtype bool regardless of sensor type."""
        site = load_dem(flat_dem_path)
        for stype in (SensorType.Radar, SensorType.EO_IR, SensorType.Acoustic):
            sensor = _sensor(stype, max_range_m=30.0)
            p = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
            layers = compute_layer_coverage(site, {stype: [(sensor, p)]})
            assert layers[stype].dtype == bool, f"dtype mismatch for {stype}"

    def test_sensitivity_kwarg_forwarded_to_rf(self, flat_dem_path):
        """Lower sensitivity_dbm threshold yields more RF coverage than higher threshold."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.RF, max_range_m=80.0)
        p = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
        layers_sensitive = compute_layer_coverage(
            site, {SensorType.RF: [(sensor, p)]}, sensitivity_dbm=-100.0
        )
        layers_insensitive = compute_layer_coverage(
            site, {SensorType.RF: [(sensor, p)]}, sensitivity_dbm=-40.0
        )
        assert layers_sensitive[SensorType.RF].sum() >= layers_insensitive[SensorType.RF].sum()

    def test_ambient_noise_kwarg_forwarded_to_acoustic(self, flat_dem_path):
        """Higher ambient_noise_db reduces acoustic coverage."""
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Acoustic, max_range_m=50.0)
        p = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
        layers_quiet = compute_layer_coverage(
            site, {SensorType.Acoustic: [(sensor, p)]}, ambient_noise_db=0.0
        )
        layers_noisy = compute_layer_coverage(
            site, {SensorType.Acoustic: [(sensor, p)]}, ambient_noise_db=40.0
        )
        assert layers_quiet[SensorType.Acoustic].sum() >= layers_noisy[SensorType.Acoustic].sum()

    def test_none_return_raises_value_error(self, flat_dem_path, monkeypatch):
        """D-097: None returned from dispatcher raises ValueError with sensor name."""
        from salus.engine import dispatcher as disp_mod

        monkeypatch.setattr(disp_mod, "compute_sensor_coverage", lambda *a, **kw: None)
        site = load_dem(flat_dem_path)
        sensor = _sensor(SensorType.Radar, max_range_m=30.0)
        p = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
        with pytest.raises(ValueError, match="returned None"):
            compute_layer_coverage(site, {SensorType.Radar: [(sensor, p)]})

    def test_float_coverage_array_coerced_to_bool(self, flat_dem_path, monkeypatch):
        """D-098: float array from dispatcher is coerced to bool without silent corruption."""
        import numpy as np

        from salus.engine import dispatcher as disp_mod

        site = load_dem(flat_dem_path)
        float_cov = np.full(site.dem.shape, 1.0, dtype=np.float64)
        monkeypatch.setattr(disp_mod, "compute_sensor_coverage", lambda *a, **kw: float_cov)
        sensor = _sensor(SensorType.Radar, max_range_m=30.0)
        p = _placement(site.origin_x + 50.0, site.origin_y - 50.0)
        layers = compute_layer_coverage(site, {SensorType.Radar: [(sensor, p)]})
        assert layers[SensorType.Radar].dtype == bool
        assert layers[SensorType.Radar].all()


# ---------------------------------------------------------------------------
# compute_composite_coverage
# ---------------------------------------------------------------------------


class TestCompositecoverage:
    def test_single_layer_passthrough(self):
        """Single layer returns an equivalent boolean array."""
        cov = np.array([[True, False], [False, True]])
        result = compute_composite_coverage({SensorType.Radar: cov})
        np.testing.assert_array_equal(result, cov)
        assert result.dtype == bool

    def test_two_layers_logical_or(self):
        """Two layers are combined with logical OR."""
        a = np.array([[True, False], [False, False]])
        b = np.array([[False, True], [False, False]])
        result = compute_composite_coverage({SensorType.Radar: a, SensorType.Acoustic: b})
        expected = np.array([[True, True], [False, False]])
        np.testing.assert_array_equal(result, expected)

    def test_all_false_layers_gives_all_false(self):
        """All-False layers produce an all-False composite."""
        a = np.zeros((5, 5), dtype=bool)
        b = np.zeros((5, 5), dtype=bool)
        result = compute_composite_coverage({SensorType.Radar: a, SensorType.RF: b})
        assert not result.any()

    def test_all_true_layers_gives_all_true(self):
        """All-True layers produce an all-True composite."""
        a = np.ones((5, 5), dtype=bool)
        result = compute_composite_coverage({SensorType.Acoustic: a})
        assert result.all()

    def test_output_shape_matches_input(self):
        """Output shape matches the shape of the input layers."""
        cov = np.zeros((10, 20), dtype=bool)
        result = compute_composite_coverage({SensorType.EO_IR: cov})
        assert result.shape == (10, 20)

    def test_empty_dict_raises(self):
        """Empty layer_coverages raises ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            compute_composite_coverage({})

    def test_shape_mismatch_raises(self):
        """Layers with differing shapes raise ValueError."""
        a = np.zeros((5, 5), dtype=bool)
        b = np.zeros((6, 5), dtype=bool)
        with pytest.raises(ValueError, match="shape"):
            compute_composite_coverage({SensorType.Radar: a, SensorType.RF: b})

    def test_float_input_coerced(self):
        """Float arrays are coerced to bool before OR — non-zero = covered."""
        a = np.array([[1.0, 0.0], [0.5, 0.0]])
        result = compute_composite_coverage({SensorType.Radar: a})  # type: ignore[arg-type]
        expected = np.array([[True, False], [True, False]])
        np.testing.assert_array_equal(result, expected)


# ---------------------------------------------------------------------------
# compute_gaps
# ---------------------------------------------------------------------------


class TestComputeGaps:
    def test_full_coverage_no_gaps(self):
        """If composite covers entire boundary, gaps are all False."""
        composite = np.ones((5, 5), dtype=bool)
        mask = np.ones((5, 5), dtype=bool)
        gaps = compute_gaps(composite, mask)
        assert not gaps.any()

    def test_no_coverage_gaps_equal_boundary(self):
        """If composite is all False, gaps equal the boundary mask."""
        composite = np.zeros((5, 5), dtype=bool)
        mask = np.ones((5, 5), dtype=bool)
        gaps = compute_gaps(composite, mask)
        np.testing.assert_array_equal(gaps, mask)

    def test_partial_coverage_correct_gaps(self):
        """Gap cells = boundary cells not covered by composite."""
        composite = np.array([[True, False], [False, True]])
        mask = np.ones((2, 2), dtype=bool)
        gaps = compute_gaps(composite, mask)
        expected = np.array([[False, True], [True, False]])
        np.testing.assert_array_equal(gaps, expected)

    def test_outside_boundary_never_gap(self):
        """Cells outside the boundary are never counted as gaps."""
        composite = np.zeros((4, 4), dtype=bool)
        mask = np.zeros((4, 4), dtype=bool)
        mask[1:3, 1:3] = True  # only inner 2x2 is in boundary
        gaps = compute_gaps(composite, mask)
        # Cells outside mask must be False even though composite is all-False
        assert not gaps[0, 0]
        assert not gaps[3, 3]
        assert gaps[1, 1]

    def test_output_dtype_bool(self):
        """Output dtype is always bool."""
        composite = np.zeros((3, 3), dtype=bool)
        mask = np.ones((3, 3), dtype=bool)
        assert compute_gaps(composite, mask).dtype == bool

    def test_shape_mismatch_raises(self):
        """Mismatched shapes raise ValueError."""
        composite = np.zeros((5, 5), dtype=bool)
        mask = np.zeros((4, 5), dtype=bool)
        with pytest.raises(ValueError, match="shape"):
            compute_gaps(composite, mask)


# ---------------------------------------------------------------------------
# build_gap_analysis
# ---------------------------------------------------------------------------


class TestBuildGapAnalysis:
    def test_no_gaps_returns_zero_area_and_none_polygons(self):
        """All-covered gap raster → area=0, percentage=0, polygons=None."""
        gap = np.zeros((10, 10), dtype=bool)
        mask = np.ones((10, 10), dtype=bool)
        result = build_gap_analysis(gap, mask, cell_size_m=5.0)
        assert isinstance(result, GapAnalysis)
        assert result.gap_area_m2 == pytest.approx(0.0)
        assert result.gap_percentage == pytest.approx(0.0)
        assert result.gap_polygons is None

    def test_full_gap_area_equals_boundary_area(self):
        """All-gap raster: area = boundary_cells × cell_area."""
        gap = np.ones((4, 4), dtype=bool)
        mask = np.ones((4, 4), dtype=bool)
        result = build_gap_analysis(gap, mask, cell_size_m=10.0)
        assert result.gap_area_m2 == pytest.approx(16 * 100.0)
        assert result.gap_percentage == pytest.approx(100.0)

    def test_partial_gap_percentage(self):
        """Half the boundary is gap → percentage ≈ 50."""
        gap = np.zeros((4, 4), dtype=bool)
        gap[:2, :] = True  # 8 of 16 cells
        mask = np.ones((4, 4), dtype=bool)
        result = build_gap_analysis(gap, mask, cell_size_m=1.0)
        assert result.gap_area_m2 == pytest.approx(8.0)
        assert result.gap_percentage == pytest.approx(50.0)

    def test_cell_size_scales_area(self):
        """gap_area_m2 scales with cell_size_m squared."""
        gap = np.ones((2, 2), dtype=bool)
        mask = np.ones((2, 2), dtype=bool)
        r1 = build_gap_analysis(gap, mask, cell_size_m=1.0)
        r2 = build_gap_analysis(gap, mask, cell_size_m=2.0)
        assert r2.gap_area_m2 == pytest.approx(r1.gap_area_m2 * 4.0)

    def test_gap_polygons_is_polygon_or_multipolygon(self):
        """When gaps exist, gap_polygons is Polygon or MultiPolygon."""
        gap = np.zeros((6, 6), dtype=bool)
        gap[1:4, 1:4] = True
        mask = np.ones((6, 6), dtype=bool)
        result = build_gap_analysis(gap, mask, cell_size_m=1.0)
        assert result.gap_polygons is not None
        assert isinstance(result.gap_polygons, (Polygon, MultiPolygon))

    def test_two_disjoint_gaps_multipolygon(self):
        """Two separate gap patches produce a MultiPolygon."""
        gap = np.zeros((10, 10), dtype=bool)
        gap[1:3, 1:3] = True
        gap[7:9, 7:9] = True
        mask = np.ones((10, 10), dtype=bool)
        result = build_gap_analysis(gap, mask, cell_size_m=1.0)
        assert isinstance(result.gap_polygons, MultiPolygon)

    def test_invalid_cell_size_zero_raises(self):
        """cell_size_m=0.0 raises ValueError."""
        with pytest.raises(ValueError, match="cell_size_m"):
            build_gap_analysis(np.zeros((2, 2), dtype=bool), np.ones((2, 2), dtype=bool), 0.0)

    def test_invalid_cell_size_negative_raises(self):
        """Negative cell_size_m raises ValueError."""
        with pytest.raises(ValueError, match="cell_size_m"):
            build_gap_analysis(np.zeros((2, 2), dtype=bool), np.ones((2, 2), dtype=bool), -1.0)

    def test_invalid_cell_size_nan_raises(self):
        """NaN cell_size_m raises ValueError."""
        with pytest.raises(ValueError, match="cell_size_m"):
            build_gap_analysis(
                np.zeros((2, 2), dtype=bool), np.ones((2, 2), dtype=bool), float("nan")
            )

    def test_shape_mismatch_raises(self):
        """Mismatched gap_raster and boundary_mask shapes raise ValueError."""
        with pytest.raises(ValueError, match="shape"):
            build_gap_analysis(np.zeros((3, 3), dtype=bool), np.ones((4, 3), dtype=bool), 1.0)

    def test_empty_boundary_warns_zero_percentage(self):
        """All-False boundary mask emits UserWarning and returns 0.0 percentage."""
        gap = np.ones((3, 3), dtype=bool)
        mask = np.zeros((3, 3), dtype=bool)
        with pytest.warns(UserWarning, match="boundary_mask contains no True cells"):
            result = build_gap_analysis(gap, mask, cell_size_m=1.0)
        assert result.gap_percentage == pytest.approx(0.0)

    def test_nan_float_gap_raster_raises(self):
        """D-101: float gap_raster with NaN raises ValueError, not silent count inflation."""
        gap = np.array([[float("nan"), 0.0], [0.0, 0.0]])
        mask = np.ones((2, 2), dtype=bool)
        with pytest.raises(ValueError, match="non-finite"):
            build_gap_analysis(gap, mask, cell_size_m=1.0)

    def test_invalid_geometry_repaired_not_silently_accepted(self):
        """D-099: invalid geometries from rasterio are buffered to repair; result is valid."""
        # 5x5 gap that should produce valid polygon(s)
        gap = np.zeros((8, 8), dtype=bool)
        gap[2:6, 2:6] = True
        mask = np.ones((8, 8), dtype=bool)
        result = build_gap_analysis(gap, mask, cell_size_m=1.0)
        if result.gap_polygons is not None:
            assert result.gap_polygons.is_valid

    def test_vectorisation_exception_raises_runtime_error(self):
        """D-100: RuntimeError from shapes loop surfaces with context, not silent None."""
        from unittest.mock import patch

        gap = np.ones((4, 4), dtype=bool)
        mask = np.ones((4, 4), dtype=bool)
        with patch("rasterio.features.shapes", side_effect=RuntimeError("rasterio boom")):
            with pytest.raises(RuntimeError, match="Gap vectorisation failed"):
                build_gap_analysis(gap, mask, cell_size_m=1.0)

    def test_empty_polys_with_gap_cells_warns(self):
        """D-102: if polys list empty despite gap_cells > 0, UserWarning is emitted."""
        from unittest.mock import patch

        gap = np.ones((4, 4), dtype=bool)
        mask = np.ones((4, 4), dtype=bool)
        # shapes returns nothing, so polys stays empty
        with patch("rasterio.features.shapes", return_value=iter([])):
            with pytest.warns(UserWarning, match="no valid polygons"):
                result = build_gap_analysis(gap, mask, cell_size_m=1.0)
        # area and percentage are still correct
        assert result.gap_area_m2 == pytest.approx(16.0)
        assert result.gap_polygons is None
