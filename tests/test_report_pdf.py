"""Tests for S13 PDF report generation (pdf.py and 'salus report' CLI)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np
import pytest
import yaml
from click.testing import CliRunner

matplotlib.use("Agg")

from salus.cli import main
from salus.engine.coverage import CoverageStats
from salus.models.saturation import SaturationResult
from salus.models.scenario import KillChainResult, ScenarioConfig
from salus.models.sensor import SensorType
from salus.models.site import SiteModel
from salus.report.pdf import (
    ReportData,
    ReportRenderError,
    SimulationResults,
    assemble_report_data,
    generate_executive_summary,
    render_pdf,
)

_BUNDLED_SENSOR_DIR = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_site(rows: int = 20, cols: int = 20) -> SiteModel:
    """Create a minimal flat SiteModel for testing."""
    dem = np.full((rows, cols), 50.0, dtype=np.float64)
    return SiteModel(dem=dem, resolution=5.0, origin_x=500000.0, origin_y=6100000.0)


def _make_stats(coverage_pct: float = 75.0) -> CoverageStats:
    """Create a CoverageStats with the given total coverage percentage."""
    return CoverageStats(
        total_coverage_pct=coverage_pct,
        per_layer_coverage_pct={SensorType.RF: coverage_pct},
        per_zone_coverage_pct={},
        gap_area_m2=10000.0 * (1.0 - coverage_pct / 100.0),
        redundancy_map=np.zeros((20, 20), dtype=np.intp),
        largest_contiguous_gap_m2=5000.0 * (1.0 - coverage_pct / 100.0),
    )


def _make_kill_chain_result(feasible: bool = True, margin: float = 5.0) -> KillChainResult:
    return KillChainResult(
        available_time_s=20.0,
        required_time_s=15.0 if feasible else 25.0,
        margin_s=margin if feasible else -5.0,
        first_detection_range_m=500.0,
        engagement_feasible=feasible,
        second_engagement_possible=feasible and margin > 10.0,
    )


def _make_scenario(dem_path: Path) -> ScenarioConfig:
    """Build a minimal ScenarioConfig pointing at a given DEM path."""
    return ScenarioConfig(
        site_dem_path=dem_path,
        sensor_placements=[],
    )


# ---------------------------------------------------------------------------
# Tests: generate_executive_summary
# ---------------------------------------------------------------------------


class TestGenerateExecutiveSummary:
    def test_good_coverage_produces_comprehensive_language(self):
        stats = _make_stats(85.0)
        result = generate_executive_summary(stats, [], None)
        assert "comprehensive" in result
        assert "85.0%" in result

    def test_adequate_coverage_produces_partial_language(self):
        stats = _make_stats(70.0)
        result = generate_executive_summary(stats, [], None)
        assert "partial" in result
        assert "70.0%" in result

    def test_poor_coverage_produces_limited_language(self):
        stats = _make_stats(40.0)
        result = generate_executive_summary(stats, [], None)
        assert "limited" in result
        assert "40.0%" in result

    def test_includes_per_layer_when_present(self):
        stats = CoverageStats(
            total_coverage_pct=75.0,
            per_layer_coverage_pct={SensorType.RF: 70.0, SensorType.Radar: 60.0},
            per_zone_coverage_pct={},
            gap_area_m2=1000.0,
            redundancy_map=np.zeros((5, 5), dtype=np.intp),
            largest_contiguous_gap_m2=500.0,
        )
        result = generate_executive_summary(stats, [], None)
        assert "RF" in result
        assert "Radar" in result

    def test_includes_zone_coverage_when_present(self):
        stats = CoverageStats(
            total_coverage_pct=75.0,
            per_layer_coverage_pct={},
            per_zone_coverage_pct={"Perimeter": 90.0, "Airfield": 50.0},
            gap_area_m2=1000.0,
            redundancy_map=np.zeros((5, 5), dtype=np.intp),
            largest_contiguous_gap_m2=500.0,
        )
        result = generate_executive_summary(stats, [], None)
        assert "Perimeter" in result
        assert "Airfield" in result

    def test_kill_chain_all_feasible(self):
        stats = _make_stats(80.0)
        results = [_make_kill_chain_result(True), _make_kill_chain_result(True)]
        result = generate_executive_summary(stats, results, None)
        assert "all 2 assessed approach corridor(s)" in result

    def test_kill_chain_none_feasible(self):
        stats = _make_stats(60.0)
        results = [_make_kill_chain_result(False), _make_kill_chain_result(False)]
        result = generate_executive_summary(stats, results, None)
        assert "no assessed approach corridors" in result

    def test_kill_chain_partial_feasible(self):
        stats = _make_stats(70.0)
        results = [_make_kill_chain_result(True), _make_kill_chain_result(False)]
        result = generate_executive_summary(stats, results, None)
        assert "1 of 2" in result

    def test_saturation_not_reached(self):
        stats = _make_stats(80.0)
        sat = SaturationResult(
            simultaneous_engagement_capacity=5,
            saturation_threshold_n=6,
            unengaged_count_at_threshold=0,
            per_effector_utilisation={},
        )
        result = generate_executive_summary(stats, [], sat)
        assert "not reached" in result.lower()

    def test_saturation_critical(self):
        stats = _make_stats(70.0)
        sat = SaturationResult(
            simultaneous_engagement_capacity=2,
            saturation_threshold_n=2,
            unengaged_count_at_threshold=1,
            per_effector_utilisation={},
        )
        result = generate_executive_summary(stats, [], sat)
        assert "critical vulnerability" in result.lower()

    def test_returns_non_empty_string(self):
        stats = _make_stats(50.0)
        result = generate_executive_summary(stats, [], None)
        assert isinstance(result, str)
        assert len(result) > 50

    def test_paragraphs_separated_by_double_newline(self):
        stats = CoverageStats(
            total_coverage_pct=75.0,
            per_layer_coverage_pct={SensorType.RF: 75.0},
            per_zone_coverage_pct={},
            gap_area_m2=1000.0,
            redundancy_map=np.zeros((5, 5), dtype=np.intp),
            largest_contiguous_gap_m2=500.0,
        )
        result = generate_executive_summary(stats, [], None)
        assert "\n\n" in result


# ---------------------------------------------------------------------------
# Tests: assemble_report_data
# ---------------------------------------------------------------------------


class TestAssembleReportData:
    def test_returns_report_data_instance(self, flat_dem_path):
        site = SiteModel(
            dem=np.full((20, 20), 50.0),
            resolution=5.0,
            origin_x=500000.0,
            origin_y=6100000.0,
        )
        sc = _make_scenario(flat_dem_path)
        composite = np.zeros((20, 20), dtype=bool)
        layer_coverages = {SensorType.RF: composite}
        stats = _make_stats(0.0)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=composite,
            layer_coverages=layer_coverages,
            stats=stats,
            sensor_defs=[],
        )
        result = assemble_report_data(sc, sim)
        assert isinstance(result, ReportData)

    def test_executive_summary_populated(self, flat_dem_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        composite = np.zeros((20, 20), dtype=bool)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=composite,
            layer_coverages={},
            stats=_make_stats(60.0),
            sensor_defs=[],
        )
        result = assemble_report_data(sc, sim)
        assert len(result.executive_summary) > 10

    def test_assumptions_has_required_sections(self, flat_dem_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(),
            sensor_defs=[],
        )
        result = assemble_report_data(sc, sim)
        assert "Terrain Model" in result.assumptions
        assert "Sensor Modelling" in result.assumptions
        assert "Propagation Model" in result.assumptions
        assert "Threat Model" in result.assumptions

    def test_scenario_name_derived_from_dem_stem(self, flat_dem_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(),
            sensor_defs=[],
        )
        result = assemble_report_data(sc, sim)
        assert result.scenario_name == flat_dem_path.stem

    def test_generated_at_is_iso8601(self, flat_dem_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(),
            sensor_defs=[],
        )
        result = assemble_report_data(sc, sim)
        assert "T" in result.generated_at
        assert "Z" in result.generated_at

    def test_no_kill_chain_chart_when_no_results(self, flat_dem_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(),
            sensor_defs=[],
        )
        result = assemble_report_data(sc, sim)
        assert result.kill_chain_chart_b64 is None

    def test_no_saturation_chart_when_no_result(self, flat_dem_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(),
            sensor_defs=[],
        )
        result = assemble_report_data(sc, sim)
        assert result.saturation_chart_b64 is None

    def test_uses_provided_gaps_array(self, flat_dem_path):
        """When sim_results.gaps is provided, assemble_report_data uses it directly."""
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        composite = np.zeros((20, 20), dtype=bool)
        gaps = np.ones((20, 20), dtype=bool)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=composite,
            layer_coverages={},
            stats=_make_stats(0.0),
            sensor_defs=[],
            gaps=gaps,
        )
        # Should not raise — if the wrong gaps shape was passed the render would fail
        result = assemble_report_data(sc, sim)
        assert isinstance(result, ReportData)


# ---------------------------------------------------------------------------
# Tests: render_pdf
# ---------------------------------------------------------------------------


class TestRenderPdf:
    def test_produces_pdf_file(self, flat_dem_path, tmp_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(65.0),
            sensor_defs=[],
        )
        report_data = assemble_report_data(sc, sim)
        out = tmp_path / "test_report.pdf"
        result = render_pdf(report_data, out)
        assert result.exists()
        assert result.stat().st_size > 1000

    def test_raises_on_missing_template_dir(self, flat_dem_path, tmp_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(),
            sensor_defs=[],
        )
        report_data = assemble_report_data(sc, sim)
        with pytest.raises(FileNotFoundError):
            render_pdf(report_data, tmp_path / "out.pdf", template_dir=tmp_path / "no_such_dir")

    def test_creates_parent_directories(self, flat_dem_path, tmp_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(),
            sensor_defs=[],
        )
        report_data = assemble_report_data(sc, sim)
        deep_path = tmp_path / "deep" / "nested" / "report.pdf"
        result = render_pdf(report_data, deep_path)
        assert result.exists()

    def test_returns_resolved_path(self, flat_dem_path, tmp_path):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=np.zeros((20, 20), dtype=bool),
            layer_coverages={},
            stats=_make_stats(),
            sensor_defs=[],
        )
        report_data = assemble_report_data(sc, sim)
        out = tmp_path / "r.pdf"
        result = render_pdf(report_data, out)
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# Tests: I-16 section-criticality policy (D-496 + D-502)
# ---------------------------------------------------------------------------


class TestSectionCriticality:
    """Verify the I-16 raise-vs-record-and-omit failure policy.

    Required sections (cover, executive_summary, site_overview,
    coverage_analysis, gap_analysis, assumptions, appendix_sensors) raise
    ReportRenderError on template or asset failure.  Optional sections
    (threat_analysis, kill_chain, saturation) append to section_failures
    and are omitted from the PDF.
    """

    def _base_sim(self, flat_dem_path) -> tuple[ScenarioConfig, SimulationResults]:
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        composite = np.zeros((20, 20), dtype=bool)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=composite,
            layer_coverages={SensorType.RF: composite},
            stats=_make_stats(60.0),
            sensor_defs=[],
        )
        return sc, sim

    def test_section_failures_empty_on_clean_render(self, flat_dem_path):
        sc, sim = self._base_sim(flat_dem_path)
        result = assemble_report_data(sc, sim)
        assert result.section_failures == []

    def test_required_composite_map_failure_raises(self, flat_dem_path, monkeypatch):
        sc, sim = self._base_sim(flat_dem_path)

        def _boom(*_args, **_kwargs):
            raise RuntimeError("composite map render exploded")

        monkeypatch.setattr("salus.report.maps.render_composite_coverage_map", _boom)
        with pytest.raises(ReportRenderError, match="composite_map"):
            assemble_report_data(sc, sim)

    def test_required_gap_map_failure_raises(self, flat_dem_path, monkeypatch):
        sc, sim = self._base_sim(flat_dem_path)

        def _boom(*_args, **_kwargs):
            raise RuntimeError("gap map render exploded")

        monkeypatch.setattr("salus.report.maps.render_gap_map", _boom)
        with pytest.raises(ReportRenderError, match="gap_analysis.gap_map"):
            assemble_report_data(sc, sim)

    def test_optional_kill_chain_chart_failure_records(self, flat_dem_path, monkeypatch):
        """Kill-chain inputs present but chart render fails — record + omit."""
        from salus.models.scenario import KillChainConfig
        from salus.models.sensor import EffectorDefinition

        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        composite = np.zeros((20, 20), dtype=bool)
        kcr = _make_kill_chain_result(feasible=True, margin=8.0)
        effector = EffectorDefinition(
            name="TestEffector",
            type="Kinetic",
            max_range_m=1000.0,
            engagement_arc_deg=120.0,
            reaction_time_s=5.0,
            defeat_probability=0.85,
            defeat_mechanism="kinetic",
        )
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=composite,
            layer_coverages={SensorType.RF: composite},
            stats=_make_stats(60.0),
            sensor_defs=[],
            effector_defs=[effector],
            corridor_results=[object()],  # truthy; not opened by chart helper
            kill_chain_results=[kcr],
            kill_chain_config=KillChainConfig(
                track_time_s=2.0,
                identify_time_s=3.0,
                decide_time_s=2.0,
                assess_time_s=2.0,
            ),
        )

        def _boom(*_args, **_kwargs):
            raise RuntimeError("chart broke")

        monkeypatch.setattr("salus.report.charts.render_kill_chain_chart", _boom)
        result = assemble_report_data(sc, sim)
        assert result.kill_chain_chart_b64 is None
        assert any(entry.startswith("kill_chain:") for entry in result.section_failures)

    def test_optional_saturation_chart_failure_records(self, flat_dem_path, monkeypatch):
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        composite = np.zeros((20, 20), dtype=bool)
        sat = SaturationResult(
            simultaneous_engagement_capacity=2,
            saturation_threshold_n=3,
            unengaged_count_at_threshold=1,
            per_effector_utilisation={},
        )
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=composite,
            layer_coverages={SensorType.RF: composite},
            stats=_make_stats(60.0),
            sensor_defs=[],
            saturation_result=sat,
            saturation_threshold_data={1: 0, 2: 0, 3: 1, 4: 2},
        )

        def _boom(*_args, **_kwargs):
            raise RuntimeError("sat chart broke")

        monkeypatch.setattr("salus.report.charts.render_saturation_threshold_chart", _boom)
        result = assemble_report_data(sc, sim)
        assert result.saturation_chart_b64 is None
        assert any(entry.startswith("saturation:") for entry in result.section_failures)

    def test_per_layer_failure_records_and_continues(self, flat_dem_path, monkeypatch):
        """One layer map fails — section_failures records it, other layers still render."""
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        composite = np.zeros((20, 20), dtype=bool)
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=composite,
            layer_coverages={
                SensorType.RF: composite,
                SensorType.Radar: composite,
            },
            stats=_make_stats(60.0),
            sensor_defs=[],
        )

        from salus.report import maps as _maps

        real_render = _maps.render_composite_coverage_map
        call_count = {"n": 0}

        def _selective_boom(site_arg, layer_coverages, *args, **kwargs):
            # First call is the composite map (multi-layer) — let it succeed.
            # Second call is per-layer for RF — fail it.
            # Third call is per-layer for RADAR — let it succeed.
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("RF layer render exploded")
            return real_render(site_arg, layer_coverages, *args, **kwargs)

        monkeypatch.setattr(_maps, "render_composite_coverage_map", _selective_boom)
        result = assemble_report_data(sc, sim)
        # RF failed, RADAR survived
        assert SensorType.RF.value not in result.layer_maps_b64
        assert SensorType.Radar.value in result.layer_maps_b64
        assert any(
            entry.startswith(f"coverage_analysis.{SensorType.RF.value}:")
            for entry in result.section_failures
        )

    def test_required_template_error_raises(self, flat_dem_path, tmp_path):
        """Syntax error in a REQUIRED template aborts render_pdf with ReportRenderError."""
        import shutil

        from salus.report.pdf import _DEFAULT_TEMPLATE_DIR

        bad_dir = tmp_path / "bad_templates"
        shutil.copytree(_DEFAULT_TEMPLATE_DIR, bad_dir)
        # cover.html is REQUIRED — break it with a Jinja syntax error
        (bad_dir / "cover.html").write_text("{% if foo %}{# unclosed")

        sc, sim = self._base_sim(flat_dem_path)
        report_data = assemble_report_data(sc, sim)
        with pytest.raises(ReportRenderError, match="cover"):
            render_pdf(report_data, tmp_path / "out.pdf", template_dir=bad_dir)

    def test_optional_template_not_found_records(self, flat_dem_path, tmp_path):
        """Missing OPTIONAL template — record in section_failures and continue."""
        import shutil

        from salus.models.scenario import KillChainConfig
        from salus.models.sensor import EffectorDefinition
        from salus.report.pdf import _DEFAULT_TEMPLATE_DIR

        partial_dir = tmp_path / "partial_templates"
        shutil.copytree(_DEFAULT_TEMPLATE_DIR, partial_dir)
        # Remove the kill_chain template (OPTIONAL)
        (partial_dir / "kill_chain.html").unlink()

        # Build a sim with kill_chain data so the section would be included
        site = _make_site()
        sc = _make_scenario(flat_dem_path)
        composite = np.zeros((20, 20), dtype=bool)
        kcr = _make_kill_chain_result(feasible=True, margin=8.0)
        effector = EffectorDefinition(
            name="TestEffector",
            type="Kinetic",
            max_range_m=1000.0,
            engagement_arc_deg=120.0,
            reaction_time_s=5.0,
            defeat_probability=0.85,
            defeat_mechanism="kinetic",
        )
        sim = SimulationResults(
            site=site,
            scenario=sc,
            composite=composite,
            layer_coverages={SensorType.RF: composite},
            stats=_make_stats(60.0),
            sensor_defs=[],
            effector_defs=[effector],
            corridor_results=[object()],
            kill_chain_results=[kcr],
            kill_chain_config=KillChainConfig(
                track_time_s=2.0,
                identify_time_s=3.0,
                decide_time_s=2.0,
                assess_time_s=2.0,
            ),
        )
        report_data = assemble_report_data(sc, sim)
        out = tmp_path / "partial_report.pdf"
        result_path = render_pdf(report_data, out, template_dir=partial_dir)
        # PDF still produced
        assert result_path.exists()
        # And the failure was recorded
        assert any(entry.startswith("kill_chain:") for entry in report_data.section_failures)


# ---------------------------------------------------------------------------
# Tests: CLI 'salus report'
# ---------------------------------------------------------------------------


@pytest.fixture
def report_scenario_yaml(flat_dem_path, tmp_path):
    """Minimal scenario YAML for report tests."""
    data = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [
            {
                "sensor_name": "DroneShield RfOne Mk2",
                "position_x": 500050.0,
                "position_y": 6100050.0,
                "bearing_deg": 0.0,
            }
        ],
    }
    path = tmp_path / "report_scenario.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


class TestCliReport:
    def test_report_command_produces_pdf(self, report_scenario_yaml, tmp_path):
        runner = CliRunner()
        out_pdf = tmp_path / "report.pdf"
        result = runner.invoke(
            main,
            [
                "report",
                str(report_scenario_yaml),
                "--output",
                str(out_pdf),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out_pdf.exists()
        assert out_pdf.stat().st_size > 1000

    def test_report_command_output_message(self, report_scenario_yaml, tmp_path):
        runner = CliRunner()
        out_pdf = tmp_path / "report.pdf"
        result = runner.invoke(
            main,
            [
                "report",
                str(report_scenario_yaml),
                "--output",
                str(out_pdf),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
            ],
        )
        assert "Report written" in result.output

    def test_save_results_creates_json(self, report_scenario_yaml, tmp_path):
        runner = CliRunner()
        results_json = tmp_path / "results.json"
        out_dir = tmp_path / "out"
        result = runner.invoke(
            main,
            [
                "simulate",
                str(report_scenario_yaml),
                "--output-dir",
                str(out_dir),
                "--save-results",
                str(results_json),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
            ],
        )
        assert result.exit_code == 0, result.output
        assert results_json.exists()
        payload = json.loads(results_json.read_text())
        assert "stats" in payload
        assert "schema_version" in payload
        assert payload["stats"]["total_coverage_pct"] >= 0.0

    def test_report_with_results_flag_produces_pdf(self, report_scenario_yaml, tmp_path):
        """salus report --results <json> should skip simulation and still produce a PDF."""
        runner = CliRunner()
        # First, generate a results JSON via simulate
        results_json = tmp_path / "results.json"
        out_dir = tmp_path / "sim_out"
        runner.invoke(
            main,
            [
                "simulate",
                str(report_scenario_yaml),
                "--output-dir",
                str(out_dir),
                "--save-results",
                str(results_json),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
            ],
        )
        assert results_json.exists(), "Pre-condition: results.json must be created by simulate"

        # Now generate report from pre-computed results
        out_pdf = tmp_path / "report_from_results.pdf"
        result = runner.invoke(
            main,
            [
                "report",
                str(report_scenario_yaml),
                "--output",
                str(out_pdf),
                "--results",
                str(results_json),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out_pdf.exists()
        assert out_pdf.stat().st_size > 1000

    def test_report_missing_scenario_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "report",
                str(tmp_path / "nonexistent.yaml"),
                "--output",
                str(tmp_path / "out.pdf"),
            ],
        )
        assert result.exit_code != 0

    def test_report_unreadable_boundary_exits_nonzero(self, flat_dem_path, tmp_path):
        """D-482: a scenario referencing a non-existent boundary file must abort,
        not silently fall back to the full-DEM bitmask (which would inflate the
        reported coverage percentage)."""
        scenario_data = {
            "site_dem_path": str(flat_dem_path),
            "boundary_path": str(tmp_path / "nonexistent_boundary.geojson"),
            "sensor_placements": [
                {
                    "sensor_name": "DroneShield RfOne Mk2",
                    "position_x": 500050.0,
                    "position_y": 6100050.0,
                    "bearing_deg": 0.0,
                }
            ],
        }
        scenario_path = tmp_path / "scenario_bad_boundary.yaml"
        scenario_path.write_text(yaml.dump(scenario_data), encoding="utf-8")
        out_pdf = tmp_path / "report.pdf"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "report",
                str(scenario_path),
                "--output",
                str(out_pdf),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
            ],
        )
        assert result.exit_code != 0, result.output
        assert "Error loading boundary" in result.output
        assert not out_pdf.exists()
