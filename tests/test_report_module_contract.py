"""Tests for the modular PDF report contract (I-12).

Covers:
- ``ExecutiveSummaryModule`` conforms to the ``ReportModule`` Protocol.
- ``build_report`` skips modules whose ``is_applicable`` returns False and
  still produces a valid PDF when at least one applicable module remains.
- ``ExecutiveSummaryModule.render`` reproduces the same executive-summary
  text as ``generate_executive_summary`` for a known fixture.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from salus.engine.coverage import CoverageStats
from salus.models.scenario import ScenarioConfig
from salus.models.sensor import SensorType
from salus.models.site import SiteModel
from salus.report.builder import build_report
from salus.report.modules import (
    ExecutiveSummaryModule,
    ModuleManifest,
    RenderContext,
    RenderedSection,
    ReportModule,
)
from salus.report.pdf import SimulationResults, generate_executive_summary


def _make_site(rows: int = 20, cols: int = 20) -> SiteModel:
    dem = np.full((rows, cols), 50.0, dtype=np.float64)
    return SiteModel(dem=dem, resolution=5.0, origin_x=500000.0, origin_y=6100000.0)


def _make_stats(coverage_pct: float = 75.0) -> CoverageStats:
    return CoverageStats(
        total_coverage_pct=coverage_pct,
        per_layer_coverage_pct={SensorType.RF: coverage_pct},
        per_zone_coverage_pct={},
        gap_area_m2=10000.0 * (1.0 - coverage_pct / 100.0),
        redundancy_map=np.zeros((20, 20), dtype=np.intp),
        largest_contiguous_gap_m2=5000.0 * (1.0 - coverage_pct / 100.0),
    )


def _make_sim(flat_dem_path: Path, coverage_pct: float = 75.0) -> SimulationResults:
    return SimulationResults(
        site=_make_site(),
        scenario=ScenarioConfig(site_dem_path=flat_dem_path, sensor_placements=[]),
        composite=np.zeros((20, 20), dtype=bool),
        layer_coverages={},
        stats=_make_stats(coverage_pct),
        sensor_defs=[],
    )


class _AlwaysSkippedModule:
    """Module whose ``is_applicable`` returns False — orchestrator must skip it."""

    manifest = ModuleManifest(
        id="always_skipped",
        title="Always Skipped",
        placement="body",
        page_break_before=True,
        landscape=False,
        optional=True,
    )

    def is_applicable(self, sim: SimulationResults) -> bool:  # noqa: ARG002
        return False

    def render(  # noqa: ARG002 — orchestrator must never call this; method exists to satisfy Protocol
        self, sim: SimulationResults, ctx: RenderContext
    ) -> RenderedSection:
        raise AssertionError("render() must not be called when is_applicable returns False")


class _RaisingModule:
    """Module whose render() raises — orchestrator must wrap with module-id context."""

    manifest = ModuleManifest(
        id="boom",
        title="Boom",
        placement="body",
        page_break_before=True,
        landscape=False,
        optional=True,
    )

    def is_applicable(self, sim: SimulationResults) -> bool:  # noqa: ARG002
        return True

    def render(  # noqa: ARG002
        self, sim: SimulationResults, ctx: RenderContext
    ) -> RenderedSection:
        raise ValueError("boom!")


class TestProtocolConformance:
    def test_executive_summary_module_is_a_report_module(self) -> None:
        assert isinstance(ExecutiveSummaryModule(), ReportModule)

    def test_skip_helper_is_a_report_module(self) -> None:
        assert isinstance(_AlwaysSkippedModule(), ReportModule)

    def test_manifest_metadata(self) -> None:
        m = ExecutiveSummaryModule().manifest
        assert m.id == "executive_summary"
        assert m.title == "Executive Summary"
        assert m.placement == "body"
        assert m.page_break_before is True
        assert m.landscape is False
        assert m.optional is True


class TestBuildReportSkipsInapplicableModules:
    def test_inapplicable_module_is_skipped_and_pdf_is_valid(
        self, flat_dem_path: Path, tmp_path: Path
    ) -> None:
        sim = _make_sim(flat_dem_path)
        out = tmp_path / "skip_test.pdf"
        result = build_report(
            sim,
            [_AlwaysSkippedModule(), ExecutiveSummaryModule()],
            out,
        )
        assert result.exists()
        assert result.stat().st_size > 1000

    def test_render_pipeline_returns_resolved_path(
        self, flat_dem_path: Path, tmp_path: Path
    ) -> None:
        sim = _make_sim(flat_dem_path)
        out = tmp_path / "executive_only.pdf"
        result = build_report(sim, [ExecutiveSummaryModule()], out)
        assert result.is_absolute()
        assert result.exists()


class TestBuildReportFailsLoud:
    def test_empty_modules_raises_value_error(self, flat_dem_path: Path, tmp_path: Path) -> None:
        sim = _make_sim(flat_dem_path)
        out = tmp_path / "empty.pdf"
        with pytest.raises(ValueError, match="No modules applicable"):
            build_report(sim, [], out)
        assert not out.exists()

    def test_all_inapplicable_raises_value_error(self, flat_dem_path: Path, tmp_path: Path) -> None:
        sim = _make_sim(flat_dem_path)
        out = tmp_path / "all_skipped.pdf"
        with pytest.raises(ValueError, match="No modules applicable"):
            build_report(sim, [_AlwaysSkippedModule()], out)
        assert not out.exists()

    def test_module_render_exception_is_wrapped_with_module_id(
        self, flat_dem_path: Path, tmp_path: Path
    ) -> None:
        sim = _make_sim(flat_dem_path)
        out = tmp_path / "boom.pdf"
        with pytest.raises(RuntimeError, match="Module boom render"):
            build_report(sim, [_RaisingModule()], out)


class TestExecutiveSummaryParityWithLegacy:
    def test_rendered_html_contains_legacy_prose(self, flat_dem_path: Path, tmp_path: Path) -> None:
        sim = _make_sim(flat_dem_path, coverage_pct=72.5)
        legacy_prose = generate_executive_summary(
            sim.stats, sim.kill_chain_results, sim.saturation_result
        )

        import jinja2

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                str(Path(__file__).parent.parent / "src" / "salus" / "report" / "templates")
            ),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        ctx = RenderContext(
            template_env=env,
            scenario_name=flat_dem_path.stem,
            generated_at="2026-05-11T00:00:00Z",
        )
        section = ExecutiveSummaryModule().render(sim, ctx)
        assert section.module_id == "executive_summary"
        assert "Executive Summary" in section.html
        first_para = legacy_prose.split("\n\n", 1)[0]
        # The template wraps each paragraph in <p>; assert the prose appears verbatim.
        assert first_para in section.html
