"""Tests for multi-target saturation analysis models and engine (S8)."""

from __future__ import annotations

import numpy as np
import pytest

from salus.engine.saturation import (
    allocate_effectors,
    compute_reengagement_timeline,
    find_saturation_threshold,
)
from salus.models.saturation import (
    AllocationResult,
    ApproachVector,
    PriorityRule,
    ReengagementResult,
    SaturationResult,
    SaturationScenario,
    SaturationTarget,
)
from salus.models.scenario import EffectorPlacement
from salus.models.sensor import EffectorDefinition, EffectorType
from salus.models.site import SiteModel
from salus.models.threat import EvasionCapability, ThreatProfile

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PROTECTED_POINT: tuple[float, float] = (500050.0, 6100050.0)

_FLAT_DEM_SIZE: int = 200
_FLAT_DEM_RESOLUTION: float = 1.0
_FLAT_DEM_ORIGIN_X: float = 500000.0
_FLAT_DEM_ORIGIN_Y: float = 6100200.0  # top-left corner, northing decreases downward


def _make_flat_site() -> SiteModel:
    """Create a 200×200 flat DEM at 1m resolution, elevation=50m."""
    dem = np.full((_FLAT_DEM_SIZE, _FLAT_DEM_SIZE), 50.0, dtype=np.float64)
    return SiteModel(
        dem=dem,
        resolution=_FLAT_DEM_RESOLUTION,
        origin_x=_FLAT_DEM_ORIGIN_X,
        origin_y=_FLAT_DEM_ORIGIN_Y,
    )


def _make_effector(
    name: str = "test_eff",
    max_range_m: float = 800.0,
    reaction_time_s: float = 2.0,
    reload_time_s: float = 5.0,
    simultaneous: int = 1,
    arc: float = 360.0,
    requires_los: bool = False,
) -> EffectorDefinition:
    return EffectorDefinition(
        name=name,
        type=EffectorType.Kinetic,
        max_range_m=max_range_m,
        engagement_arc_deg=arc,
        reaction_time_s=reaction_time_s,
        reload_time_s=reload_time_s,
        simultaneous_engagements=simultaneous,
        defeat_probability=0.85,
        defeat_mechanism="Test defeat",
        requires_los=requires_los,
    )


def _make_placement(
    name: str = "test_eff",
    pos_x: float = 500050.0,
    pos_y: float = 6100050.0,
    bearing_deg: float = 0.0,
    height_override_m: float | None = 2.0,
) -> EffectorPlacement:
    return EffectorPlacement(
        effector_name=name,
        position_x=pos_x,
        position_y=pos_y,
        bearing_deg=bearing_deg,
        height_override_m=height_override_m,
    )


def _make_target(
    bearing_deg: float = 0.0,
    distance_m: float = 500.0,
    altitude_m: float = 50.0,
    speed_ms: float = 20.0,
) -> SaturationTarget:
    return SaturationTarget(
        approach_vector=ApproachVector(bearing_deg=bearing_deg, distance_m=distance_m),
        altitude_m=altitude_m,
        speed_ms=speed_ms,
    )


def _make_scenario(
    distance_m: float | None = None,
    priority_rule: PriorityRule = PriorityRule.CLOSEST_TO_ASSET,
) -> SaturationScenario:
    tgt = _make_target() if distance_m is None else _make_target(distance_m=distance_m)
    return SaturationScenario(targets=[tgt], priority_rule=priority_rule)


def _make_threat_profile(
    name: str = "test_threat",
    altitude_m: float = 50.0,
    speed_ms: float = 20.0,
) -> ThreatProfile:
    return ThreatProfile(
        name=name,
        rcs_m2=0.01,
        rf_signature="2.4 GHz",
        max_speed_ms=speed_ms,
        typical_altitude_m=altitude_m,
        evasion_capability=EvasionCapability.none,
    )


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------


class TestApproachVector:
    def test_valid_construction(self):
        av = ApproachVector(bearing_deg=90.0, distance_m=500.0)
        assert av.bearing_deg == 90.0
        assert av.distance_m == 500.0

    def test_zero_bearing_accepted(self):
        av = ApproachVector(bearing_deg=0.0, distance_m=100.0)
        assert av.bearing_deg == 0.0

    def test_bearing_359_accepted(self):
        av = ApproachVector(bearing_deg=359.9, distance_m=100.0)
        assert av.bearing_deg == 359.9

    def test_bearing_360_rejected(self):
        with pytest.raises(ValueError):
            ApproachVector(bearing_deg=360.0, distance_m=100.0)

    def test_negative_bearing_rejected(self):
        with pytest.raises(ValueError):
            ApproachVector(bearing_deg=-1.0, distance_m=100.0)

    def test_zero_distance_rejected(self):
        with pytest.raises(ValueError):
            ApproachVector(bearing_deg=0.0, distance_m=0.0)

    def test_negative_distance_rejected(self):
        with pytest.raises(ValueError):
            ApproachVector(bearing_deg=0.0, distance_m=-10.0)


class TestSaturationTarget:
    def test_valid_construction(self):
        t = _make_target()
        assert t.altitude_m == 50.0
        assert t.speed_ms == 20.0

    def test_zero_altitude_accepted(self):
        t = _make_target(altitude_m=0.0)
        assert t.altitude_m == 0.0

    def test_negative_altitude_rejected(self):
        with pytest.raises(ValueError):
            _make_target(altitude_m=-1.0)

    def test_zero_speed_rejected(self):
        with pytest.raises(ValueError):
            _make_target(speed_ms=0.0)

    def test_threat_profile_ref_defaults_empty(self):
        t = SaturationTarget(
            approach_vector=ApproachVector(bearing_deg=0.0, distance_m=100.0),
            altitude_m=50.0,
            speed_ms=20.0,
        )
        assert t.threat_profile_ref == ""


class TestSaturationScenario:
    def test_valid_construction(self):
        s = SaturationScenario(
            targets=[_make_target()], priority_rule=PriorityRule.CLOSEST_TO_ASSET
        )
        assert len(s.targets) == 1

    def test_empty_targets_rejected(self):
        with pytest.raises(ValueError):
            SaturationScenario(targets=[], priority_rule=PriorityRule.CLOSEST_TO_ASSET)

    def test_default_priority_rule(self):
        s = SaturationScenario(targets=[_make_target()])
        assert s.priority_rule == PriorityRule.CLOSEST_TO_ASSET


# ---------------------------------------------------------------------------
# allocate_effectors tests
# ---------------------------------------------------------------------------


class TestAllocateEffectors:
    def test_single_target_engaged(self):
        """One target within range is assigned when capacity allows."""
        site = _make_flat_site()
        eff = _make_effector()
        placement = _make_placement()
        targets = [_make_target(bearing_deg=0.0, distance_m=100.0)]
        result = allocate_effectors(
            targets, [eff], [placement], PriorityRule.CLOSEST_TO_ASSET, site, _PROTECTED_POINT
        )
        assert isinstance(result, AllocationResult)
        assert 0 in result.engaged_indices
        assert result.unengaged_indices == []

    def test_target_out_of_range_unengaged(self):
        """Target beyond max_range_m is left unengaged."""
        site = _make_flat_site()
        eff = _make_effector(max_range_m=50.0)  # very short range
        placement = _make_placement()
        # Target 200m away — out of range
        targets = [_make_target(bearing_deg=0.0, distance_m=200.0)]
        result = allocate_effectors(
            targets, [eff], [placement], PriorityRule.CLOSEST_TO_ASSET, site, _PROTECTED_POINT
        )
        assert 0 in result.unengaged_indices
        assert result.engaged_indices == []

    def test_simultaneous_capacity_limits_assignments(self):
        """Effector with simultaneous_engagements=1 handles only one target."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=1)
        placement = _make_placement()
        targets = [
            _make_target(bearing_deg=0.0, distance_m=100.0),
            _make_target(bearing_deg=90.0, distance_m=100.0),
        ]
        result = allocate_effectors(
            targets, [eff], [placement], PriorityRule.CLOSEST_TO_ASSET, site, _PROTECTED_POINT
        )
        assert len(result.engaged_indices) == 1
        assert len(result.unengaged_indices) == 1

    def test_multiple_placements_handle_multiple_targets(self):
        """Two placements of the same effector can engage two simultaneous targets."""
        site = _make_flat_site()
        eff = _make_effector(name="gun", simultaneous=1)
        p1 = _make_placement(name="gun", pos_x=500050.0, pos_y=6100050.0)
        p2 = _make_placement(name="gun", pos_x=500060.0, pos_y=6100060.0)
        targets = [
            _make_target(bearing_deg=90.0, distance_m=50.0),
            _make_target(bearing_deg=270.0, distance_m=50.0),
        ]
        result = allocate_effectors(
            targets, [eff], [p1, p2], PriorityRule.CLOSEST_TO_ASSET, site, _PROTECTED_POINT
        )
        assert len(result.engaged_indices) == 2

    def test_priority_closest_to_asset(self):
        """CLOSEST_TO_ASSET engages nearest target when capacity = 1."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=1)
        placement = _make_placement()
        # Target 0 is farther (200m), target 1 is closer (50m)
        targets = [
            _make_target(bearing_deg=0.0, distance_m=200.0),
            _make_target(bearing_deg=90.0, distance_m=50.0),
        ]
        result = allocate_effectors(
            targets, [eff], [placement], PriorityRule.CLOSEST_TO_ASSET, site, _PROTECTED_POINT
        )
        # Target 1 (closer) should be engaged
        assert 1 in result.engaged_indices
        assert 0 in result.unengaged_indices

    def test_priority_highest_threat(self):
        """HIGHEST_THREAT engages fastest target when capacity = 1."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=1)
        placement = _make_placement()
        targets = [
            _make_target(bearing_deg=0.0, distance_m=100.0, speed_ms=10.0),  # slow
            _make_target(bearing_deg=90.0, distance_m=100.0, speed_ms=30.0),  # fast
        ]
        result = allocate_effectors(
            targets, [eff], [placement], PriorityRule.HIGHEST_THREAT, site, _PROTECTED_POINT
        )
        # Target 1 (faster) should be engaged
        assert 1 in result.engaged_indices
        assert 0 in result.unengaged_indices

    def test_priority_user_defined_preserves_order(self):
        """USER_DEFINED engages first target in list when capacity = 1."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=1)
        placement = _make_placement()
        targets = [
            _make_target(bearing_deg=0.0, distance_m=100.0),
            _make_target(bearing_deg=90.0, distance_m=50.0),
        ]
        result = allocate_effectors(
            targets, [eff], [placement], PriorityRule.USER_DEFINED, site, _PROTECTED_POINT
        )
        assert 0 in result.engaged_indices

    def test_assignments_map_target_to_effector_name(self):
        """assignments dict maps target index to effector name string."""
        site = _make_flat_site()
        eff = _make_effector(name="my_gun")
        placement = _make_placement(name="my_gun")
        targets = [_make_target()]
        result = allocate_effectors(
            targets, [eff], [placement], PriorityRule.CLOSEST_TO_ASSET, site, _PROTECTED_POINT
        )
        assert result.assignments.get(0) == "my_gun"

    def test_empty_targets_raises(self):
        """Empty targets list raises ValueError."""
        site = _make_flat_site()
        with pytest.raises(ValueError, match="targets must not be empty"):
            allocate_effectors(
                [],
                [_make_effector()],
                [_make_placement()],
                PriorityRule.CLOSEST_TO_ASSET,
                site,
                _PROTECTED_POINT,
            )

    def test_empty_effectors_raises(self):
        """Empty effectors list raises ValueError."""
        site = _make_flat_site()
        with pytest.raises(ValueError, match="effectors must not be empty"):
            allocate_effectors(
                [_make_target()],
                [],
                [_make_placement()],
                PriorityRule.CLOSEST_TO_ASSET,
                site,
                _PROTECTED_POINT,
            )

    def test_empty_placements_raises(self):
        """Empty placements list raises ValueError."""
        site = _make_flat_site()
        with pytest.raises(ValueError, match="placements must not be empty"):
            allocate_effectors(
                [_make_target()],
                [_make_effector()],
                [],
                PriorityRule.CLOSEST_TO_ASSET,
                site,
                _PROTECTED_POINT,
            )

    def test_simultaneous_capacity_two(self):
        """Effector with simultaneous_engagements=2 handles two targets."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=2)
        placement = _make_placement()
        targets = [
            _make_target(bearing_deg=0.0, distance_m=100.0),
            _make_target(bearing_deg=180.0, distance_m=100.0),
        ]
        result = allocate_effectors(
            targets, [eff], [placement], PriorityRule.CLOSEST_TO_ASSET, site, _PROTECTED_POINT
        )
        assert len(result.engaged_indices) == 2
        assert result.unengaged_indices == []


# ---------------------------------------------------------------------------
# find_saturation_threshold tests
# ---------------------------------------------------------------------------


class TestFindSaturationThreshold:
    def test_returns_saturation_result(self):
        """find_saturation_threshold returns a SaturationResult."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=1)
        placement = _make_placement()
        threat = _make_threat_profile()
        result = find_saturation_threshold([eff], [placement], site, _PROTECTED_POINT, threat)
        assert isinstance(result, SaturationResult)

    def test_saturation_at_two_with_single_slot(self):
        """Single-slot effector saturates at N=2."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=1)
        placement = _make_placement()
        threat = _make_threat_profile()
        result = find_saturation_threshold([eff], [placement], site, _PROTECTED_POINT, threat)
        assert result.saturation_threshold_n == 2

    def test_capacity_equals_simultaneous_sum(self):
        """simultaneous_engagement_capacity = sum of simultaneous_engagements across placements."""
        site = _make_flat_site()
        eff = _make_effector(name="gun", simultaneous=3)
        p1 = _make_placement(name="gun", pos_x=500050.0, pos_y=6100050.0)
        p2 = _make_placement(name="gun", pos_x=500060.0, pos_y=6100060.0)
        threat = _make_threat_profile()
        result = find_saturation_threshold(
            [eff], [p1, p2], site, _PROTECTED_POINT, threat, max_targets=10
        )
        assert result.simultaneous_engagement_capacity == 6  # 3 × 2 placements

    def test_unengaged_count_at_threshold_positive(self):
        """unengaged_count_at_threshold > 0 when threshold is reached."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=1)
        placement = _make_placement()
        threat = _make_threat_profile()
        result = find_saturation_threshold([eff], [placement], site, _PROTECTED_POINT, threat)
        if result.saturation_threshold_n <= 20:
            assert result.unengaged_count_at_threshold > 0

    def test_threshold_beyond_max_when_not_saturated(self):
        """saturation_threshold_n = max_targets + 1 when system handles all targets."""
        site = _make_flat_site()
        eff = _make_effector(simultaneous=20)  # can handle 20 targets at once
        placement = _make_placement()
        threat = _make_threat_profile()
        result = find_saturation_threshold(
            [eff], [placement], site, _PROTECTED_POINT, threat, max_targets=5
        )
        assert result.saturation_threshold_n == 6  # max_targets + 1

    def test_per_effector_utilisation_present(self):
        """per_effector_utilisation contains the effector name key."""
        site = _make_flat_site()
        eff = _make_effector(name="my_eff", simultaneous=2)
        placement = _make_placement(name="my_eff")
        threat = _make_threat_profile()
        result = find_saturation_threshold([eff], [placement], site, _PROTECTED_POINT, threat)
        assert "my_eff" in result.per_effector_utilisation

    def test_empty_effectors_raises(self):
        """Empty effectors list raises ValueError."""
        site = _make_flat_site()
        threat = _make_threat_profile()
        with pytest.raises(ValueError, match="effectors must not be empty"):
            find_saturation_threshold([], [_make_placement()], site, _PROTECTED_POINT, threat)

    def test_empty_placements_raises(self):
        """Empty placements list raises ValueError."""
        site = _make_flat_site()
        threat = _make_threat_profile()
        with pytest.raises(ValueError, match="placements must not be empty"):
            find_saturation_threshold([_make_effector()], [], site, _PROTECTED_POINT, threat)

    def test_invalid_max_targets_raises(self):
        """max_targets < 1 raises ValueError."""
        site = _make_flat_site()
        threat = _make_threat_profile()
        with pytest.raises(ValueError, match="max_targets must be >= 1"):
            find_saturation_threshold(
                [_make_effector()],
                [_make_placement()],
                site,
                _PROTECTED_POINT,
                threat,
                max_targets=0,
            )


# ---------------------------------------------------------------------------
# compute_reengagement_timeline tests
# ---------------------------------------------------------------------------


class TestComputeReengagementTimeline:
    def test_returns_reengagement_result(self):
        """compute_reengagement_timeline returns a ReengagementResult."""
        site = _make_flat_site()
        eff = _make_effector(reaction_time_s=2.0, reload_time_s=5.0)
        placement = _make_placement()
        scenario = SaturationScenario(
            targets=[_make_target(bearing_deg=0.0, distance_m=100.0)],
            priority_rule=PriorityRule.CLOSEST_TO_ASSET,
        )
        result = compute_reengagement_timeline([eff], [placement], site, _PROTECTED_POINT, scenario)
        assert isinstance(result, ReengagementResult)

    def test_window_preserved_in_result(self):
        """window_s in result matches the supplied window."""
        site = _make_flat_site()
        eff = _make_effector()
        placement = _make_placement()
        scenario = _make_scenario()
        result = compute_reengagement_timeline(
            [eff], [placement], site, _PROTECTED_POINT, scenario, window_s=30.0
        )
        assert result.window_s == 30.0

    def test_total_engagements_positive(self):
        """total_engagements_possible > 0 when at least one target is engaged."""
        site = _make_flat_site()
        eff = _make_effector(reaction_time_s=2.0, reload_time_s=5.0)
        placement = _make_placement()
        scenario = SaturationScenario(
            targets=[_make_target(distance_m=100.0)],
            priority_rule=PriorityRule.CLOSEST_TO_ASSET,
        )
        result = compute_reengagement_timeline(
            [eff], [placement], site, _PROTECTED_POINT, scenario, window_s=60.0
        )
        assert result.total_engagements_possible > 0

    def test_cycle_time_is_reaction_plus_reload(self):
        """reengagement_cycle_time_s = reaction_time_s + reload_time_s."""
        site = _make_flat_site()
        eff = _make_effector(reaction_time_s=3.0, reload_time_s=7.0)
        placement = _make_placement()
        scenario = _make_scenario(distance_m=100.0)
        result = compute_reengagement_timeline(
            [eff], [placement], site, _PROTECTED_POINT, scenario, window_s=60.0
        )
        assert abs(result.reengagement_cycle_time_s - 10.0) < 1e-9

    def test_per_effector_engagements_key_present(self):
        """per_effector_engagements contains the effector name when engaged."""
        site = _make_flat_site()
        eff = _make_effector(name="cannon")
        placement = _make_placement(name="cannon")
        scenario = _make_scenario(distance_m=100.0)
        result = compute_reengagement_timeline(
            [eff], [placement], site, _PROTECTED_POINT, scenario, window_s=60.0
        )
        assert "cannon" in result.per_effector_engagements

    def test_jammer_zero_reload_fires_many_times(self):
        """Effector with reload_time_s=0 fires as often as window/reaction allows."""
        site = _make_flat_site()
        eff = _make_effector(name="jammer", reaction_time_s=5.0, reload_time_s=0.0)
        placement = _make_placement(name="jammer")
        scenario = _make_scenario(distance_m=100.0)
        result = compute_reengagement_timeline(
            [eff], [placement], site, _PROTECTED_POINT, scenario, window_s=60.0
        )
        # 60 / 5 = 12 engagements
        assert result.per_effector_engagements.get("jammer", 0) == 12

    def test_invalid_window_raises(self):
        """window_s <= 0 raises ValueError."""
        site = _make_flat_site()
        eff = _make_effector()
        scenario = _make_scenario()
        with pytest.raises(ValueError, match="window_s must be a finite value > 0"):
            compute_reengagement_timeline(
                [eff], [_make_placement()], site, _PROTECTED_POINT, scenario, window_s=0.0
            )

    def test_empty_effectors_raises(self):
        """Empty effectors raises ValueError."""
        site = _make_flat_site()
        scenario = _make_scenario()
        with pytest.raises(ValueError, match="effectors must not be empty"):
            compute_reengagement_timeline([], [_make_placement()], site, _PROTECTED_POINT, scenario)

    def test_empty_placements_raises(self):
        """Empty placements raises ValueError."""
        site = _make_flat_site()
        eff = _make_effector()
        scenario = _make_scenario()
        with pytest.raises(ValueError, match="placements must not be empty"):
            compute_reengagement_timeline([eff], [], site, _PROTECTED_POINT, scenario)
