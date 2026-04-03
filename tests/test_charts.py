"""Tests for kill-chain chart rendering (S7-4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from salus.models.scenario import KillChainConfig, KillChainResult
from salus.models.sensor import EffectorDefinition, EffectorType

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_kc_config() -> KillChainConfig:
    return KillChainConfig(
        track_time_s=5.0,
        identify_time_s=10.0,
        decide_time_s=8.0,
        assess_time_s=3.0,
    )


def _make_effector() -> EffectorDefinition:
    return EffectorDefinition(
        name="test_kinetic",
        type=EffectorType.Kinetic,
        max_range_m=800.0,
        engagement_arc_deg=360.0,
        reaction_time_s=2.0,
        reload_time_s=5.0,
        defeat_probability=0.8,
        defeat_mechanism="Test defeat",
    )


def _make_corridor_result(bearing_deg: float = 45.0, first_det: float | None = 600.0):
    from salus.engine.threat_corridor import CorridorResult
    from salus.models.threat import ThreatCorridor

    return CorridorResult(
        corridor=ThreatCorridor(
            bearing_deg=bearing_deg, altitude_m=50.0, width_m=100.0, start_distance_m=1000.0
        ),
        threat_name="test_threat",
        coverage_pct=75.0,
        first_detection_distance_m=first_det,
        last_gap_before_target_m=0.0,
        time_in_coverage_s=20.0,
        covered_cells=75,
        total_cells=100,
    )


def _make_kc_result(
    available: float = 30.0,
    required: float = 28.0,
    first_det: float | None = 600.0,
) -> KillChainResult:
    margin = available - required
    return KillChainResult(
        available_time_s=available,
        required_time_s=required,
        margin_s=margin,
        first_detection_range_m=first_det,
        engagement_feasible=margin >= 0.0,
        second_engagement_possible=margin > 10.0,
    )


def _is_valid_png(path: Path) -> bool:
    """Return True if the file starts with a valid PNG header."""
    with open(path, "rb") as f:
        header = f.read(8)
    return header == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# render_kill_chain_chart
# ---------------------------------------------------------------------------


class TestRenderKillChainChart:
    """Tests for the per-corridor Gantt chart."""

    def test_returns_path(self, tmp_path):
        """render_kill_chain_chart returns a Path."""
        from salus.report.charts import render_kill_chain_chart

        cr = [_make_corridor_result()]
        kc = [_make_kc_result()]
        out = render_kill_chain_chart(
            cr, kc, _make_kc_config(), _make_effector(), tmp_path / "kc.png"
        )
        assert isinstance(out, Path)

    def test_file_exists(self, tmp_path):
        """Output PNG file exists after rendering."""
        from salus.report.charts import render_kill_chain_chart

        out_path = tmp_path / "kc.png"
        render_kill_chain_chart(
            [_make_corridor_result()],
            [_make_kc_result()],
            _make_kc_config(),
            _make_effector(),
            out_path,
        )
        assert out_path.exists()

    def test_output_is_valid_png(self, tmp_path):
        """Output file is a valid PNG."""
        from salus.report.charts import render_kill_chain_chart

        out_path = tmp_path / "kc.png"
        render_kill_chain_chart(
            [_make_corridor_result()],
            [_make_kc_result()],
            _make_kc_config(),
            _make_effector(),
            out_path,
        )
        assert _is_valid_png(out_path)

    def test_creates_parent_dir(self, tmp_path):
        """Parent directory is created if it does not exist."""
        from salus.report.charts import render_kill_chain_chart

        out_path = tmp_path / "subdir" / "kc.png"
        render_kill_chain_chart(
            [_make_corridor_result()],
            [_make_kc_result()],
            _make_kc_config(),
            _make_effector(),
            out_path,
        )
        assert out_path.exists()

    def test_accepts_str_path(self, tmp_path):
        """Output path may be a str (converted to Path internally)."""
        from salus.report.charts import render_kill_chain_chart

        out_path = str(tmp_path / "kc.png")
        result = render_kill_chain_chart(
            [_make_corridor_result()],
            [_make_kc_result()],
            _make_kc_config(),
            _make_effector(),
            out_path,
        )
        assert isinstance(result, Path)
        assert result.exists()

    def test_multiple_corridors(self, tmp_path):
        """Renders chart for multiple corridors without error."""
        from salus.report.charts import render_kill_chain_chart

        crs = [_make_corridor_result(bearing_deg=float(b)) for b in range(0, 360, 30)]
        kcs = [_make_kc_result(available=30.0 + b / 10.0) for b in range(0, 360, 30)]
        out = render_kill_chain_chart(
            crs, kcs, _make_kc_config(), _make_effector(), tmp_path / "multi.png"
        )
        assert out.exists()

    def test_infeasible_corridor_renders(self, tmp_path):
        """A corridor with negative margin renders without error."""
        from salus.report.charts import render_kill_chain_chart

        kc_bad = KillChainResult(
            available_time_s=5.0,
            required_time_s=28.0,
            margin_s=-23.0,
            first_detection_range_m=100.0,
            engagement_feasible=False,
            second_engagement_possible=False,
        )
        out = render_kill_chain_chart(
            [_make_corridor_result()],
            [kc_bad],
            _make_kc_config(),
            _make_effector(),
            tmp_path / "infeasible.png",
        )
        assert out.exists()

    def test_no_detection_corridor_renders(self, tmp_path):
        """A corridor with no detection renders without error."""
        from salus.report.charts import render_kill_chain_chart

        kc_no_det = KillChainResult(
            available_time_s=0.0,
            required_time_s=28.0,
            margin_s=-28.0,
            first_detection_range_m=None,
            engagement_feasible=False,
            second_engagement_possible=False,
        )
        out = render_kill_chain_chart(
            [_make_corridor_result(first_det=None)],
            [kc_no_det],
            _make_kc_config(),
            _make_effector(),
            tmp_path / "no_det.png",
        )
        assert out.exists()

    def test_mismatched_lengths_raises(self, tmp_path):
        """Mismatched corridor/result list lengths raise ValueError."""
        from salus.report.charts import render_kill_chain_chart

        with pytest.raises(ValueError, match="same length"):
            render_kill_chain_chart(
                [_make_corridor_result()],
                [_make_kc_result(), _make_kc_result()],
                _make_kc_config(),
                _make_effector(),
                tmp_path / "err.png",
            )

    def test_empty_lists_raises(self, tmp_path):
        """Empty corridor/result lists raise ValueError."""
        from salus.report.charts import render_kill_chain_chart

        with pytest.raises(ValueError):
            render_kill_chain_chart(
                [], [], _make_kc_config(), _make_effector(), tmp_path / "empty.png"
            )


# ---------------------------------------------------------------------------
# render_kill_chain_summary_chart
# ---------------------------------------------------------------------------


class TestRenderKillChainSummaryChart:
    """Tests for the worst/average/best summary chart."""

    def test_returns_valid_png(self, tmp_path):
        """Summary chart produces a valid PNG."""
        from salus.report.charts import render_kill_chain_summary_chart

        crs = [_make_corridor_result(bearing_deg=float(b)) for b in range(0, 360, 45)]
        kcs = [_make_kc_result(available=float(20 + i * 5)) for i in range(len(crs))]
        out = render_kill_chain_summary_chart(
            crs, kcs, _make_kc_config(), _make_effector(), tmp_path / "summary.png"
        )
        assert out.exists()
        assert _is_valid_png(out)

    def test_single_corridor(self, tmp_path):
        """Summary chart works with a single corridor (worst=avg=best)."""
        from salus.report.charts import render_kill_chain_summary_chart

        out = render_kill_chain_summary_chart(
            [_make_corridor_result()],
            [_make_kc_result()],
            _make_kc_config(),
            _make_effector(),
            tmp_path / "single.png",
        )
        assert out.exists()

    def test_empty_raises(self, tmp_path):
        """Empty inputs raise ValueError."""
        from salus.report.charts import render_kill_chain_summary_chart

        with pytest.raises(ValueError):
            render_kill_chain_summary_chart(
                [], [], _make_kc_config(), _make_effector(), tmp_path / "empty.png"
            )
