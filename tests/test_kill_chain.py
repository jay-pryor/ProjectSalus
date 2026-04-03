"""Tests for kill-chain timeline computation (S7-2 and S7-3)."""

from __future__ import annotations

import pytest

from salus.engine.kill_chain import compute_all_kill_chains, compute_kill_chain
from salus.models.scenario import KillChainConfig, KillChainResult
from salus.models.sensor import EffectorDefinition, EffectorType

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_kc_config(
    track: float = 5.0,
    identify: float = 10.0,
    decide: float = 8.0,
    assess: float = 3.0,
) -> KillChainConfig:
    return KillChainConfig(
        track_time_s=track,
        identify_time_s=identify,
        decide_time_s=decide,
        assess_time_s=assess,
    )


def _make_effector(
    reaction: float = 2.0,
    reload: float = 5.0,
    name: str = "test_effector",
) -> EffectorDefinition:
    return EffectorDefinition(
        name=name,
        type=EffectorType.Kinetic,
        max_range_m=800.0,
        engagement_arc_deg=360.0,
        reaction_time_s=reaction,
        reload_time_s=reload,
        defeat_probability=0.8,
        defeat_mechanism="Test kinetic defeat",
    )


def _make_corridor_result(
    bearing_deg: float = 45.0,
    first_detection_distance_m: float | None = 600.0,
    coverage_pct: float = 80.0,
    threat_name: str = "test_threat",
):
    """Build a CorridorResult without needing a real DEM."""

    from salus.engine.threat_corridor import CorridorResult
    from salus.models.threat import ThreatCorridor

    corridor = ThreatCorridor(
        bearing_deg=bearing_deg,
        altitude_m=50.0,
        width_m=100.0,
        start_distance_m=1000.0,
    )
    return CorridorResult(
        corridor=corridor,
        threat_name=threat_name,
        coverage_pct=coverage_pct,
        first_detection_distance_m=first_detection_distance_m,
        last_gap_before_target_m=0.0,
        time_in_coverage_s=30.0,
        covered_cells=80,
        total_cells=100,
    )


# ---------------------------------------------------------------------------
# compute_kill_chain — S7-2
# ---------------------------------------------------------------------------


class TestComputeKillChain:
    """Unit tests for compute_kill_chain."""

    def test_returns_kill_chain_result(self):
        """compute_kill_chain returns a KillChainResult."""
        cr = _make_corridor_result(first_detection_distance_m=600.0)
        cfg = _make_kc_config()
        eff = _make_effector(reaction=2.0, reload=5.0)
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        assert isinstance(result, KillChainResult)

    def test_available_time_correct(self):
        """available_time_s = first_detection_range_m / drone_speed."""
        cr = _make_corridor_result(first_detection_distance_m=400.0)
        cfg = _make_kc_config()
        eff = _make_effector(reaction=2.0, reload=5.0)
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        # 400 m / 20 m/s = 20 s
        assert abs(result.available_time_s - 20.0) < 1e-9

    def test_required_time_sum_of_phases(self):
        """required_time_s = track + identify + decide + reaction + assess."""
        cr = _make_corridor_result(first_detection_distance_m=600.0)
        cfg = _make_kc_config(track=5.0, identify=10.0, decide=8.0, assess=3.0)
        eff = _make_effector(reaction=2.0)
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        expected = 5.0 + 10.0 + 8.0 + 2.0 + 3.0  # 28.0 s
        assert abs(result.required_time_s - expected) < 1e-9

    def test_margin_equals_available_minus_required(self):
        """margin_s = available_time_s - required_time_s."""
        cr = _make_corridor_result(first_detection_distance_m=600.0)
        cfg = _make_kc_config(track=5.0, identify=10.0, decide=8.0, assess=3.0)
        eff = _make_effector(reaction=2.0, reload=5.0)
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        # available = 600 / 20 = 30 s; required = 28 s; margin = 2 s
        assert abs(result.margin_s - (result.available_time_s - result.required_time_s)) < 1e-9

    def test_engagement_feasible_when_positive_margin(self):
        """engagement_feasible is True when margin_s >= 0."""
        cr = _make_corridor_result(first_detection_distance_m=1000.0)
        cfg = _make_kc_config(track=5.0, identify=5.0, decide=5.0, assess=3.0)
        eff = _make_effector(reaction=2.0, reload=5.0)
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        # available = 50 s; required = 20 s; margin = 30 s ≥ 0
        assert result.engagement_feasible is True

    def test_engagement_infeasible_when_negative_margin(self):
        """engagement_feasible is False when margin_s < 0."""
        # Detection at 100 m; speed 20 m/s → 5 s available; required = 28 s.
        cr = _make_corridor_result(first_detection_distance_m=100.0)
        cfg = _make_kc_config(track=5.0, identify=10.0, decide=8.0, assess=3.0)
        eff = _make_effector(reaction=2.0, reload=5.0)
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        assert result.engagement_feasible is False
        assert result.margin_s < 0.0

    def test_no_detection_infeasible(self):
        """No detection → engagement_feasible=False and available_time_s=0."""
        cr = _make_corridor_result(first_detection_distance_m=None)
        cfg = _make_kc_config()
        eff = _make_effector(reaction=2.0, reload=5.0)
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        assert result.engagement_feasible is False
        assert result.available_time_s == 0.0
        assert result.first_detection_range_m is None

    def test_second_engagement_possible_when_large_margin(self):
        """second_engagement_possible is True when margin > reload + reaction + assess."""
        # 2000 m at 20 m/s → 100 s available; required ~28 s; margin ~72 s
        cr = _make_corridor_result(first_detection_distance_m=2000.0)
        cfg = _make_kc_config(track=5.0, identify=10.0, decide=8.0, assess=3.0)
        eff = _make_effector(reaction=2.0, reload=5.0)
        # second threshold = 5 + 2 + 3 = 10 s; margin ≈ 72 > 10
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        assert result.second_engagement_possible is True

    def test_second_engagement_not_possible_when_small_margin(self):
        """second_engagement_possible is False when margin <= reload + reaction + assess."""
        # Design: available=30 s, required=28 s → margin=2 s; threshold=10 s → 2 < 10
        cr = _make_corridor_result(first_detection_distance_m=600.0)
        cfg = _make_kc_config(track=5.0, identify=10.0, decide=8.0, assess=3.0)
        eff = _make_effector(reaction=2.0, reload=5.0)
        # margin ≈ 2 s; second threshold = 5 + 2 + 3 = 10 s → not possible
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        assert result.second_engagement_possible is False

    def test_invalid_speed_raises(self):
        """Non-positive threat_speed_ms raises ValueError."""
        cr = _make_corridor_result(first_detection_distance_m=600.0)
        cfg = _make_kc_config()
        eff = _make_effector()
        with pytest.raises(ValueError):
            compute_kill_chain(cr, cfg, eff, threat_speed_ms=0.0)

    def test_negative_speed_raises(self):
        """Negative threat_speed_ms raises ValueError."""
        cr = _make_corridor_result(first_detection_distance_m=600.0)
        cfg = _make_kc_config()
        eff = _make_effector()
        with pytest.raises(ValueError):
            compute_kill_chain(cr, cfg, eff, threat_speed_ms=-10.0)

    def test_first_detection_range_preserved(self):
        """first_detection_range_m in result equals input corridor value."""
        cr = _make_corridor_result(first_detection_distance_m=750.0)
        cfg = _make_kc_config()
        eff = _make_effector()
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=15.0)
        assert result.first_detection_range_m == 750.0

    def test_zero_detection_distance_infeasible(self):
        """first_detection_distance_m=0 treats as no detection."""
        cr = _make_corridor_result(first_detection_distance_m=0.0)
        cfg = _make_kc_config()
        eff = _make_effector()
        result = compute_kill_chain(cr, cfg, eff, threat_speed_ms=20.0)
        assert result.engagement_feasible is False


# ---------------------------------------------------------------------------
# compute_all_kill_chains — S7-3
# ---------------------------------------------------------------------------


class TestComputeAllKillChains:
    """Unit tests for compute_all_kill_chains."""

    def test_returns_list_of_same_length(self):
        """Result list has same length as corridor_results."""
        crs = [_make_corridor_result(bearing_deg=float(b)) for b in range(0, 360, 10)]
        cfg = _make_kc_config()
        effectors = [_make_effector()]
        results = compute_all_kill_chains(crs, cfg, effectors, threat_speed_ms=20.0)
        assert len(results) == len(crs)

    def test_all_results_are_kill_chain_results(self):
        """Every element in the result list is a KillChainResult."""
        crs = [
            _make_corridor_result(bearing_deg=0.0),
            _make_corridor_result(bearing_deg=90.0),
        ]
        cfg = _make_kc_config()
        results = compute_all_kill_chains(crs, cfg, [_make_effector()], threat_speed_ms=20.0)
        for r in results:
            assert isinstance(r, KillChainResult)

    def test_empty_effectors_raises(self):
        """Empty effectors list raises ValueError."""
        crs = [_make_corridor_result()]
        cfg = _make_kc_config()
        with pytest.raises(ValueError, match="effectors must not be empty"):
            compute_all_kill_chains(crs, cfg, [], threat_speed_ms=20.0)

    def test_best_effector_selected_per_corridor(self):
        """When two effectors given, the one with shorter required time wins."""
        cr = _make_corridor_result(first_detection_distance_m=400.0)
        cfg = _make_kc_config(track=5.0, identify=5.0, decide=5.0, assess=2.0)
        fast = _make_effector(reaction=1.0, reload=2.0, name="fast")  # required=18s
        slow = _make_effector(reaction=10.0, reload=2.0, name="slow")  # required=27s
        # available = 20 s; fast margin=2 s; slow margin=-7 s
        results = compute_all_kill_chains([cr], cfg, [fast, slow], threat_speed_ms=20.0)
        # Best effector gives positive margin
        assert results[0].margin_s >= 0.0

    def test_identifies_failure_corridors(self):
        """Corridors with no detection have engagement_feasible=False."""
        cr_good = _make_corridor_result(first_detection_distance_m=2000.0)
        cr_bad = _make_corridor_result(first_detection_distance_m=None)
        cfg = _make_kc_config()
        results = compute_all_kill_chains(
            [cr_good, cr_bad], cfg, [_make_effector()], threat_speed_ms=20.0
        )
        assert results[0].engagement_feasible is True
        assert results[1].engagement_feasible is False

    def test_identifies_single_engagement_corridors(self):
        """Corridor where margin>0 but margin<=second_threshold is single-engagement."""
        # available=30s, required=28s, margin=2s; threshold=10s → single engagement
        cr = _make_corridor_result(first_detection_distance_m=600.0)
        cfg = _make_kc_config(track=5.0, identify=10.0, decide=8.0, assess=3.0)
        eff = _make_effector(reaction=2.0, reload=5.0)
        results = compute_all_kill_chains([cr], cfg, [eff], threat_speed_ms=20.0)
        assert results[0].engagement_feasible is True
        assert results[0].second_engagement_possible is False

    def test_result_order_matches_input(self):
        """Results are in the same order as input corridors."""
        bearings = [0.0, 90.0, 180.0, 270.0]
        crs = [
            _make_corridor_result(bearing_deg=b, first_detection_distance_m=b + 100.0)
            for b in bearings
        ]
        cfg = _make_kc_config()
        results = compute_all_kill_chains(crs, cfg, [_make_effector()], threat_speed_ms=20.0)
        expected_avail = [(b + 100.0) / 20.0 for b in bearings]
        for result, expected in zip(results, expected_avail):
            assert abs(result.available_time_s - expected) < 1e-9
