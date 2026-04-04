"""Tests for saturation analysis chart rendering (S8-5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from salus.models.saturation import ReengagementResult, SaturationResult
from salus.report.charts import (
    render_effector_utilisation_chart,
    render_engagement_timeline_chart,
    render_saturation_threshold_chart,
)

# ---------------------------------------------------------------------------
# render_saturation_threshold_chart
# ---------------------------------------------------------------------------


class TestRenderSaturationThresholdChart:
    def test_writes_png(self, tmp_path: Path):
        """render_saturation_threshold_chart creates a PNG file."""
        data = {1: 0, 2: 0, 3: 1, 4: 2}
        out = tmp_path / "sat.png"
        result = render_saturation_threshold_chart(data, saturation_threshold_n=3, output_path=out)
        assert result.exists()
        assert result.suffix == ".png"

    def test_returns_resolved_path(self, tmp_path: Path):
        """Returned path is resolved (absolute)."""
        data = {1: 0, 2: 1}
        out = tmp_path / "sat.png"
        result = render_saturation_threshold_chart(data, saturation_threshold_n=2, output_path=out)
        assert result.is_absolute()

    def test_creates_parent_directories(self, tmp_path: Path):
        """Parent directories are created automatically."""
        out = tmp_path / "subdir" / "sat.png"
        render_saturation_threshold_chart({1: 0, 2: 1}, saturation_threshold_n=2, output_path=out)
        assert out.exists()

    def test_empty_threshold_data_raises(self, tmp_path: Path):
        """Empty threshold_data raises ValueError."""
        with pytest.raises(ValueError, match="threshold_data must not be empty"):
            render_saturation_threshold_chart(
                {}, saturation_threshold_n=1, output_path=tmp_path / "x.png"
            )

    def test_threshold_not_in_data_no_line(self, tmp_path: Path):
        """Chart renders without error when saturation_threshold_n is not in data."""
        data = {1: 0, 2: 0}
        out = tmp_path / "sat.png"
        render_saturation_threshold_chart(data, saturation_threshold_n=10, output_path=out)
        assert out.exists()

    def test_single_entry(self, tmp_path: Path):
        """Chart renders with a single-entry threshold_data dict."""
        data = {1: 1}
        out = tmp_path / "sat.png"
        render_saturation_threshold_chart(data, saturation_threshold_n=1, output_path=out)
        assert out.exists()

    def test_all_zeros_unengaged(self, tmp_path: Path):
        """Chart renders when all targets are engaged (no saturation)."""
        data = {1: 0, 2: 0, 3: 0}
        out = tmp_path / "sat.png"
        render_saturation_threshold_chart(data, saturation_threshold_n=4, output_path=out)
        assert out.exists()


# ---------------------------------------------------------------------------
# render_engagement_timeline_chart
# ---------------------------------------------------------------------------


class TestRenderEngagementTimelineChart:
    def _make_result(
        self, engagements: dict[str, int], window_s: float = 60.0
    ) -> ReengagementResult:
        return ReengagementResult(
            window_s=window_s,
            total_engagements_possible=sum(engagements.values()),
            reengagement_cycle_time_s=7.0,
            per_effector_engagements=engagements,
        )

    def test_writes_png(self, tmp_path: Path):
        """render_engagement_timeline_chart creates a PNG file."""
        result = self._make_result({"GunA": 8})
        timing = {"GunA": (2.0, 5.0)}
        out = tmp_path / "timeline.png"
        path = render_engagement_timeline_chart(result, timing, out)
        assert path.exists()

    def test_returns_resolved_path(self, tmp_path: Path):
        result = self._make_result({"GunA": 8})
        timing = {"GunA": (2.0, 5.0)}
        out = tmp_path / "timeline.png"
        path = render_engagement_timeline_chart(result, timing, out)
        assert path.is_absolute()

    def test_multiple_effectors(self, tmp_path: Path):
        """Chart renders with multiple effectors without error."""
        result = self._make_result({"GunA": 8, "JammerB": 12}, window_s=60.0)
        timing = {"GunA": (2.0, 5.0), "JammerB": (5.0, 0.0)}
        out = tmp_path / "timeline.png"
        path = render_engagement_timeline_chart(result, timing, out)
        assert path.exists()

    def test_empty_engagements_raises(self, tmp_path: Path):
        """Empty per_effector_engagements raises ValueError."""
        result = ReengagementResult(
            window_s=60.0,
            total_engagements_possible=0,
            reengagement_cycle_time_s=7.0,
            per_effector_engagements={},
        )
        with pytest.raises(ValueError, match="must not be empty"):
            render_engagement_timeline_chart(result, {}, tmp_path / "x.png")

    def test_missing_timing_key_raises(self, tmp_path: Path):
        """Missing key in effector_timing raises ValueError."""
        result = self._make_result({"GunA": 8})
        with pytest.raises(ValueError, match="missing keys"):
            render_engagement_timeline_chart(result, {}, tmp_path / "x.png")

    def test_creates_parent_directories(self, tmp_path: Path):
        """Parent directories are created automatically."""
        result = self._make_result({"GunA": 8})
        timing = {"GunA": (2.0, 5.0)}
        out = tmp_path / "sub" / "timeline.png"
        render_engagement_timeline_chart(result, timing, out)
        assert out.exists()

    def test_zero_reload_effector(self, tmp_path: Path):
        """Chart renders for jammer with reload_time_s=0."""
        result = self._make_result({"Jammer": 12})
        timing = {"Jammer": (5.0, 0.0)}
        out = tmp_path / "timeline.png"
        path = render_engagement_timeline_chart(result, timing, out)
        assert path.exists()


# ---------------------------------------------------------------------------
# render_effector_utilisation_chart
# ---------------------------------------------------------------------------


class TestRenderEffectorUtilisationChart:
    def _make_result(self, utilisation: dict[str, float]) -> SaturationResult:
        return SaturationResult(
            simultaneous_engagement_capacity=len(utilisation),
            saturation_threshold_n=3,
            unengaged_count_at_threshold=1,
            per_effector_utilisation=utilisation,
        )

    def test_writes_png(self, tmp_path: Path):
        """render_effector_utilisation_chart creates a PNG file."""
        result = self._make_result({"GunA": 0.75, "JammerB": 1.0})
        out = tmp_path / "util.png"
        path = render_effector_utilisation_chart(result, out)
        assert path.exists()

    def test_returns_resolved_path(self, tmp_path: Path):
        result = self._make_result({"GunA": 0.5})
        out = tmp_path / "util.png"
        path = render_effector_utilisation_chart(result, out)
        assert path.is_absolute()

    def test_empty_utilisation_raises(self, tmp_path: Path):
        """Empty per_effector_utilisation raises ValueError."""
        result = SaturationResult(
            simultaneous_engagement_capacity=0,
            saturation_threshold_n=1,
            unengaged_count_at_threshold=0,
            per_effector_utilisation={},
        )
        with pytest.raises(ValueError, match="must not be empty"):
            render_effector_utilisation_chart(result, tmp_path / "x.png")

    def test_creates_parent_directories(self, tmp_path: Path):
        """Parent directories are created automatically."""
        result = self._make_result({"GunA": 1.0})
        out = tmp_path / "sub" / "util.png"
        render_effector_utilisation_chart(result, out)
        assert out.exists()

    def test_full_utilisation(self, tmp_path: Path):
        """100% utilisation renders without error."""
        result = self._make_result({"GunA": 1.0})
        out = tmp_path / "util.png"
        path = render_effector_utilisation_chart(result, out)
        assert path.exists()

    def test_multiple_effectors(self, tmp_path: Path):
        """Chart with multiple effectors at various utilisation levels."""
        result = self._make_result({"GunA": 0.5, "GunB": 0.8, "Jammer": 1.0})
        out = tmp_path / "util.png"
        path = render_effector_utilisation_chart(result, out)
        assert path.exists()
