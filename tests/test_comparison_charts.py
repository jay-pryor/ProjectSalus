"""Tests for S10 chart and map rendering — render_coverage_comparison_chart, render_delta_map."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from salus.engine.comparison import (
    ComparisonResult,
    ConfigurationResult,
    compare_configs,
)
from salus.engine.coverage import CoverageStats
from salus.ingest.terrain import load_dem
from salus.report.charts import render_comparison_statistics_table, render_coverage_comparison_chart
from salus.report.maps import render_delta_map, render_side_by_side_coverage_maps

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stats(
    total: float = 50.0,
    zones: dict[str, float] | None = None,
) -> CoverageStats:
    shape = (4, 4)
    return CoverageStats(
        total_coverage_pct=total,
        per_layer_coverage_pct={},
        per_zone_coverage_pct=zones or {},
        gap_area_m2=0.0,
        redundancy_map=np.zeros(shape, dtype=np.intp),
        largest_contiguous_gap_m2=0.0,
    )


def _make_comparison(
    shape: tuple[int, int] = (4, 4),
    total_a: float = 40.0,
    total_b: float = 70.0,
    zones_a: dict[str, float] | None = None,
    zones_b: dict[str, float] | None = None,
    cost_a: float | None = None,
    cost_b: float | None = None,
) -> ComparisonResult:
    comp_a = np.zeros(shape, dtype=bool)
    comp_b = np.zeros(shape, dtype=bool)
    # Cover top half with A, bottom half with B.
    mid = shape[0] // 2
    comp_a[:mid, :] = True
    comp_b[mid:, :] = True

    cfg_a = ConfigurationResult(
        label="Config A",
        composite=comp_a,
        stats=_make_stats(total=total_a, zones=zones_a),
        cost_estimate=cost_a,
    )
    cfg_b = ConfigurationResult(
        label="Config B",
        composite=comp_b,
        stats=_make_stats(total=total_b, zones=zones_b),
        cost_estimate=cost_b,
    )
    return compare_configs(cfg_a, cfg_b)


def _is_valid_png(path: Path) -> bool:
    with open(path, "rb") as f:
        header = f.read(8)
    return header == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# render_coverage_comparison_chart
# ---------------------------------------------------------------------------


class TestRenderCoverageComparisonChart:
    def test_returns_path_to_png(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "comparison.png"
        result = render_coverage_comparison_chart(comparison, out)
        assert result == out
        assert out.exists()

    def test_output_is_valid_png(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "comparison.png"
        render_coverage_comparison_chart(comparison, out)
        assert _is_valid_png(out)

    def test_creates_parent_directory(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "subdir" / "deep" / "chart.png"
        render_coverage_comparison_chart(comparison, out)
        assert out.exists()

    def test_accepts_string_path(self, tmp_path):
        comparison = _make_comparison()
        out = str(tmp_path / "chart.png")
        result = render_coverage_comparison_chart(comparison, out)
        assert isinstance(result, Path)
        assert result.exists()

    def test_with_zones(self, tmp_path):
        comparison = _make_comparison(
            zones_a={"north": 30.0, "south": 50.0},
            zones_b={"north": 55.0, "south": 45.0},
        )
        out = tmp_path / "comparison_zones.png"
        render_coverage_comparison_chart(comparison, out)
        assert out.exists()

    def test_no_zones_overall_only(self, tmp_path):
        """Chart with no zones should still render (overall bar only)."""
        comparison = _make_comparison()
        out = tmp_path / "comparison_no_zones.png"
        render_coverage_comparison_chart(comparison, out)
        assert out.exists()

    def test_custom_title(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "titled.png"
        render_coverage_comparison_chart(comparison, out, title="My Custom Title")
        assert out.exists()

    def test_type_error_on_wrong_input(self, tmp_path):
        out = tmp_path / "bad.png"
        with pytest.raises(TypeError, match="ComparisonResult"):
            render_coverage_comparison_chart("not a comparison", out)  # type: ignore[arg-type]

    def test_overwrite_existing_file(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "comparison.png"
        out.write_bytes(b"garbage")
        render_coverage_comparison_chart(comparison, out)
        assert _is_valid_png(out)

    def test_single_zone(self, tmp_path):
        comparison = _make_comparison(
            zones_a={"perimeter": 60.0},
            zones_b={"perimeter": 80.0},
        )
        out = tmp_path / "single_zone.png"
        render_coverage_comparison_chart(comparison, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# render_delta_map
# ---------------------------------------------------------------------------


class TestRenderDeltaMap:
    def test_returns_path_to_png(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "delta.png"
        result = render_delta_map(site, comparison, out)
        assert result == out
        assert out.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "delta.png"
        render_delta_map(site, comparison, out)
        assert _is_valid_png(out)

    def test_creates_parent_directory(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "nested" / "delta.png"
        render_delta_map(site, comparison, out)
        assert out.exists()

    def test_accepts_string_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = str(tmp_path / "delta.png")
        result = render_delta_map(site, comparison, out)
        assert isinstance(result, Path)
        assert result.exists()

    def test_custom_title(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "titled_delta.png"
        render_delta_map(site, comparison, out, title="Custom Delta Title")
        assert out.exists()

    def test_with_sensor_positions(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "delta_sensors.png"
        positions_a = [(500010.0, 6100090.0), (500050.0, 6100050.0)]
        positions_b = [(500020.0, 6100080.0)]
        render_delta_map(
            site,
            comparison,
            out,
            sensor_positions_a=positions_a,
            sensor_positions_b=positions_b,
        )
        assert out.exists()

    def test_sensor_positions_none(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "delta_no_sensors.png"
        render_delta_map(site, comparison, out, sensor_positions_a=None, sensor_positions_b=None)
        assert out.exists()

    def test_type_error_on_wrong_comparison(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        out = tmp_path / "bad.png"
        with pytest.raises(TypeError, match="ComparisonResult"):
            render_delta_map(site, "not a comparison", out)  # type: ignore[arg-type]

    def test_all_b_coverage(self, flat_dem_path, tmp_path):
        """All cells covered by B only — no A coverage."""
        site = load_dem(flat_dem_path)
        shape = site.dem.shape
        comp_a = np.zeros(shape, dtype=bool)
        comp_b = np.ones(shape, dtype=bool)
        cfg_a = ConfigurationResult(
            label="Empty A",
            composite=comp_a,
            stats=_make_stats(total=0.0),
        )
        cfg_b = ConfigurationResult(
            label="Full B",
            composite=comp_b,
            stats=_make_stats(total=100.0),
        )
        comparison = compare_configs(cfg_a, cfg_b)
        out = tmp_path / "all_b.png"
        render_delta_map(site, comparison, out)
        assert out.exists()

    def test_all_coverage_both(self, flat_dem_path, tmp_path):
        """All cells covered by both — entire grid is DELTA_BOTH."""
        site = load_dem(flat_dem_path)
        shape = site.dem.shape
        comp = np.ones(shape, dtype=bool)
        cfg_a = ConfigurationResult(label="A Full", composite=comp, stats=_make_stats(total=100.0))
        cfg_b = ConfigurationResult(label="B Full", composite=comp, stats=_make_stats(total=100.0))
        comparison = compare_configs(cfg_a, cfg_b)
        out = tmp_path / "all_both.png"
        render_delta_map(site, comparison, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# render_side_by_side_coverage_maps
# ---------------------------------------------------------------------------


class TestRenderSideBySideCoverageMaps:
    def test_returns_path_to_png(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "side_by_side.png"
        result = render_side_by_side_coverage_maps(site, comparison, out)
        assert result == out
        assert out.exists()

    def test_output_is_valid_png(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "side_by_side.png"
        render_side_by_side_coverage_maps(site, comparison, out)
        assert _is_valid_png(out)

    def test_creates_parent_directory(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "nested" / "side_by_side.png"
        render_side_by_side_coverage_maps(site, comparison, out)
        assert out.exists()

    def test_accepts_string_path(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = str(tmp_path / "side_by_side.png")
        result = render_side_by_side_coverage_maps(site, comparison, out)
        assert isinstance(result, Path)
        assert result.exists()

    def test_with_sensor_positions(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "sbs_sensors.png"
        render_side_by_side_coverage_maps(
            site,
            comparison,
            out,
            sensor_positions_a=[(500010.0, 6100090.0)],
            sensor_positions_b=[(500020.0, 6100080.0)],
        )
        assert out.exists()

    def test_custom_title(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        comparison = _make_comparison(shape=site.dem.shape)
        out = tmp_path / "sbs_title.png"
        render_side_by_side_coverage_maps(site, comparison, out, title="My Custom Title")
        assert out.exists()

    def test_type_error_on_wrong_comparison(self, flat_dem_path, tmp_path):
        site = load_dem(flat_dem_path)
        out = tmp_path / "bad.png"
        with pytest.raises(TypeError, match="ComparisonResult"):
            render_side_by_side_coverage_maps(site, "not a comparison", out)  # type: ignore[arg-type]

    def test_all_b_coverage(self, flat_dem_path, tmp_path):
        """All cells B-only renders without error."""
        site = load_dem(flat_dem_path)
        shape = site.dem.shape
        cfg_a = ConfigurationResult(
            label="A", composite=np.zeros(shape, dtype=bool), stats=_make_stats()
        )
        cfg_b = ConfigurationResult(
            label="B", composite=np.ones(shape, dtype=bool), stats=_make_stats(total=100.0)
        )
        comparison = compare_configs(cfg_a, cfg_b)
        out = tmp_path / "sbs_all_b.png"
        render_side_by_side_coverage_maps(site, comparison, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# render_comparison_statistics_table
# ---------------------------------------------------------------------------


class TestRenderComparisonStatisticsTable:
    def test_returns_path_to_png(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "stats.png"
        result = render_comparison_statistics_table(comparison, out)
        assert result == out
        assert out.exists()

    def test_output_is_valid_png(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "stats.png"
        render_comparison_statistics_table(comparison, out)
        assert _is_valid_png(out)

    def test_creates_parent_directory(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "nested" / "stats.png"
        render_comparison_statistics_table(comparison, out)
        assert out.exists()

    def test_accepts_string_path(self, tmp_path):
        comparison = _make_comparison()
        out = str(tmp_path / "stats.png")
        result = render_comparison_statistics_table(comparison, out)
        assert isinstance(result, Path)
        assert result.exists()

    def test_custom_title(self, tmp_path):
        comparison = _make_comparison()
        out = tmp_path / "stats_titled.png"
        render_comparison_statistics_table(comparison, out, title="My Stats Table")
        assert out.exists()

    def test_with_optional_metrics(self, tmp_path):
        """cost_delta, capacity_delta, saturation_delta all present."""
        comparison = _make_comparison(cost_a=100_000.0, cost_b=250_000.0)
        out = tmp_path / "stats_full.png"
        render_comparison_statistics_table(comparison, out)
        assert out.exists()

    def test_with_zones(self, tmp_path):
        comparison = _make_comparison(
            zones_a={"north": 30.0, "south": 50.0},
            zones_b={"north": 60.0, "south": 40.0},
        )
        out = tmp_path / "stats_zones.png"
        render_comparison_statistics_table(comparison, out)
        assert out.exists()

    def test_type_error_on_wrong_input(self, tmp_path):
        out = tmp_path / "bad.png"
        with pytest.raises(TypeError, match="ComparisonResult"):
            render_comparison_statistics_table("not a comparison", out)  # type: ignore[arg-type]
