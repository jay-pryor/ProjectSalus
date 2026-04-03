"""Tests for ThreatProfile and ThreatCorridor Pydantic models."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from salus.models.threat import (
    DroneTrajectory,
    EvasionCapability,
    ThreatCorridor,
    ThreatProfile,
    TrajectoryWaypoint,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_profile(**overrides) -> dict:
    base = {
        "name": "Test Threat",
        "rcs_m2": 0.01,
        "rf_signature": "2.4 GHz control link",
        "max_speed_ms": 15.0,
        "typical_altitude_m": 50.0,
    }
    base.update(overrides)
    return base


def _valid_corridor(**overrides) -> dict:
    base = {
        "bearing_deg": 45.0,
        "altitude_m": 50.0,
        "width_m": 50.0,
        "start_distance_m": 2000.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ThreatProfile — valid construction
# ---------------------------------------------------------------------------


class TestThreatProfileValid:
    def test_minimal_required_fields(self):
        p = ThreatProfile(**_valid_profile())
        assert p.name == "Test Threat"
        assert p.rcs_m2 == 0.01
        assert p.max_speed_ms == 15.0
        assert p.typical_altitude_m == 50.0

    def test_defaults(self):
        p = ThreatProfile(**_valid_profile())
        assert p.approach_vectors == []
        assert p.evasion_capability == EvasionCapability.none

    def test_approach_vectors_stored(self):
        p = ThreatProfile(**_valid_profile(approach_vectors=["NE", "N"]))
        assert p.approach_vectors == ["NE", "N"]

    def test_evasion_capability_advanced(self):
        p = ThreatProfile(**_valid_profile(evasion_capability="advanced"))
        assert p.evasion_capability == EvasionCapability.advanced

    def test_evasion_capability_basic(self):
        p = ThreatProfile(**_valid_profile(evasion_capability="basic"))
        assert p.evasion_capability == EvasionCapability.basic

    def test_zero_altitude_allowed(self):
        p = ThreatProfile(**_valid_profile(typical_altitude_m=0.0))
        assert p.typical_altitude_m == 0.0

    def test_very_small_rcs(self):
        p = ThreatProfile(**_valid_profile(rcs_m2=1e-4))
        assert p.rcs_m2 == pytest.approx(1e-4)


# ---------------------------------------------------------------------------
# ThreatProfile — validation errors
# ---------------------------------------------------------------------------


class TestThreatProfileInvalid:
    def test_empty_name_raises(self):
        with pytest.raises(ValidationError, match="name"):
            ThreatProfile(**_valid_profile(name=""))

    def test_whitespace_name_raises(self):
        with pytest.raises(ValidationError, match="name"):
            ThreatProfile(**_valid_profile(name="   "))

    def test_empty_rf_signature_raises(self):
        with pytest.raises(ValidationError, match="rf_signature"):
            ThreatProfile(**_valid_profile(rf_signature=""))

    def test_whitespace_rf_signature_raises(self):
        with pytest.raises(ValidationError, match="rf_signature"):
            ThreatProfile(**_valid_profile(rf_signature="  "))

    def test_zero_rcs_raises(self):
        with pytest.raises(ValidationError, match="rcs_m2"):
            ThreatProfile(**_valid_profile(rcs_m2=0.0))

    def test_negative_rcs_raises(self):
        with pytest.raises(ValidationError, match="rcs_m2"):
            ThreatProfile(**_valid_profile(rcs_m2=-0.01))

    def test_zero_speed_raises(self):
        with pytest.raises(ValidationError, match="max_speed_ms"):
            ThreatProfile(**_valid_profile(max_speed_ms=0.0))

    def test_negative_speed_raises(self):
        with pytest.raises(ValidationError, match="max_speed_ms"):
            ThreatProfile(**_valid_profile(max_speed_ms=-5.0))

    def test_negative_altitude_raises(self):
        with pytest.raises(ValidationError, match="typical_altitude_m"):
            ThreatProfile(**_valid_profile(typical_altitude_m=-1.0))

    def test_invalid_evasion_capability_raises(self):
        with pytest.raises(ValidationError):
            ThreatProfile(**_valid_profile(evasion_capability="extreme"))

    def test_nan_rcs_raises(self):
        with pytest.raises(ValidationError, match="rcs_m2"):
            ThreatProfile(**_valid_profile(rcs_m2=float("nan")))

    def test_nan_speed_raises(self):
        with pytest.raises(ValidationError, match="max_speed_ms"):
            ThreatProfile(**_valid_profile(max_speed_ms=float("nan")))

    def test_nan_altitude_raises(self):
        with pytest.raises(ValidationError, match="typical_altitude_m"):
            ThreatProfile(**_valid_profile(typical_altitude_m=float("nan")))


# ---------------------------------------------------------------------------
# ThreatCorridor — valid construction
# ---------------------------------------------------------------------------


class TestThreatCorridorValid:
    def test_minimal_required_fields(self):
        c = ThreatCorridor(**_valid_corridor())
        assert c.bearing_deg == 45.0
        assert c.altitude_m == 50.0

    def test_defaults(self):
        c = ThreatCorridor(bearing_deg=90.0, altitude_m=30.0)
        assert c.width_m == 50.0
        assert c.start_distance_m == 3000.0

    def test_bearing_zero(self):
        c = ThreatCorridor(**_valid_corridor(bearing_deg=0.0))
        assert c.bearing_deg == 0.0

    def test_bearing_just_below_360(self):
        c = ThreatCorridor(**_valid_corridor(bearing_deg=359.9))
        assert c.bearing_deg == pytest.approx(359.9)

    def test_zero_altitude_allowed(self):
        c = ThreatCorridor(**_valid_corridor(altitude_m=0.0))
        assert c.altitude_m == 0.0

    def test_zero_start_distance_allowed(self):
        c = ThreatCorridor(**_valid_corridor(start_distance_m=0.0))
        assert c.start_distance_m == 0.0

    def test_minimum_width(self):
        c = ThreatCorridor(**_valid_corridor(width_m=1.0))
        assert c.width_m == 1.0


# ---------------------------------------------------------------------------
# ThreatCorridor — validation errors
# ---------------------------------------------------------------------------


class TestThreatCorridorInvalid:
    def test_bearing_360_raises(self):
        with pytest.raises(ValidationError, match="bearing_deg"):
            ThreatCorridor(**_valid_corridor(bearing_deg=360.0))

    def test_bearing_negative_raises(self):
        with pytest.raises(ValidationError, match="bearing_deg"):
            ThreatCorridor(**_valid_corridor(bearing_deg=-1.0))

    def test_negative_altitude_raises(self):
        with pytest.raises(ValidationError, match="altitude_m"):
            ThreatCorridor(**_valid_corridor(altitude_m=-10.0))

    def test_width_below_minimum_raises(self):
        with pytest.raises(ValidationError, match="width_m"):
            ThreatCorridor(**_valid_corridor(width_m=0.5))

    def test_zero_width_raises(self):
        with pytest.raises(ValidationError, match="width_m"):
            ThreatCorridor(**_valid_corridor(width_m=0.0))

    def test_negative_start_distance_raises(self):
        with pytest.raises(ValidationError, match="start_distance_m"):
            ThreatCorridor(**_valid_corridor(start_distance_m=-1.0))

    def test_nan_altitude_raises(self):
        with pytest.raises(ValidationError, match="altitude_m"):
            ThreatCorridor(**_valid_corridor(altitude_m=float("nan")))

    def test_nan_width_raises(self):
        with pytest.raises(ValidationError, match="width_m"):
            ThreatCorridor(**_valid_corridor(width_m=float("nan")))

    def test_nan_start_distance_raises(self):
        with pytest.raises(ValidationError, match="start_distance_m"):
            ThreatCorridor(**_valid_corridor(start_distance_m=float("nan")))


# ---------------------------------------------------------------------------
# EvasionCapability enum
# ---------------------------------------------------------------------------


class TestEvasionCapability:
    def test_values(self):
        assert EvasionCapability.none == "none"
        assert EvasionCapability.basic == "basic"
        assert EvasionCapability.advanced == "advanced"

    def test_str_roundtrip(self):
        assert EvasionCapability("none") is EvasionCapability.none
        assert EvasionCapability("advanced") is EvasionCapability.advanced


# ---------------------------------------------------------------------------
# TrajectoryWaypoint
# ---------------------------------------------------------------------------


def _wp(x: float = 0.0, y: float = 0.0, z_agl: float = 50.0) -> dict:
    return {"x": x, "y": y, "z_agl": z_agl}


class TestTrajectoryWaypointValid:
    def test_basic_construction(self):
        wp = TrajectoryWaypoint(**_wp(100.0, 200.0, 75.0))
        assert wp.x == 100.0
        assert wp.y == 200.0
        assert wp.z_agl == 75.0

    def test_negative_coordinates_allowed(self):
        wp = TrajectoryWaypoint(**_wp(-500.0, -1000.0, 0.0))
        assert wp.x == -500.0
        assert wp.y == -1000.0

    def test_zero_agl_allowed(self):
        wp = TrajectoryWaypoint(**_wp(z_agl=0.0))
        assert wp.z_agl == 0.0


class TestTrajectoryWaypointInvalid:
    def test_nan_x_raises(self):
        with pytest.raises(ValidationError, match="finite"):
            TrajectoryWaypoint(**_wp(x=float("nan")))

    def test_nan_y_raises(self):
        with pytest.raises(ValidationError, match="finite"):
            TrajectoryWaypoint(**_wp(y=float("nan")))

    def test_nan_z_agl_raises(self):
        with pytest.raises(ValidationError, match="finite"):
            TrajectoryWaypoint(**_wp(z_agl=float("nan")))

    def test_inf_x_raises(self):
        with pytest.raises(ValidationError, match="finite"):
            TrajectoryWaypoint(**_wp(x=float("inf")))

    def test_inf_z_agl_raises(self):
        with pytest.raises(ValidationError, match="finite"):
            TrajectoryWaypoint(**_wp(z_agl=float("-inf")))

    def test_negative_z_agl_raises(self):
        with pytest.raises(ValidationError, match="z_agl"):
            TrajectoryWaypoint(**_wp(z_agl=-1.0))


# ---------------------------------------------------------------------------
# DroneTrajectory
# ---------------------------------------------------------------------------


def _two_waypoints() -> list[dict]:
    return [_wp(0.0, 0.0, 50.0), _wp(1000.0, 0.0, 30.0)]


class TestDroneTrajectoryValid:
    def test_two_waypoints_minimum(self):
        traj = DroneTrajectory(waypoints=_two_waypoints(), speed_ms=15.0)
        assert len(traj.waypoints) == 2
        assert traj.speed_ms == 15.0

    def test_many_waypoints(self):
        wps = [_wp(float(i) * 100, 0.0, 50.0) for i in range(5)]
        traj = DroneTrajectory(waypoints=wps, speed_ms=20.0)
        assert len(traj.waypoints) == 5

    def test_waypoints_are_waypoint_instances(self):
        traj = DroneTrajectory(waypoints=_two_waypoints(), speed_ms=10.0)
        assert all(isinstance(wp, TrajectoryWaypoint) for wp in traj.waypoints)

    def test_small_speed_allowed(self):
        traj = DroneTrajectory(waypoints=_two_waypoints(), speed_ms=0.1)
        assert traj.speed_ms == pytest.approx(0.1)


class TestDroneTrajectoryInvalid:
    def test_single_waypoint_raises(self):
        with pytest.raises(ValidationError, match="at least 2"):
            DroneTrajectory(waypoints=[_wp()], speed_ms=10.0)

    def test_zero_waypoints_raises(self):
        with pytest.raises(ValidationError, match="at least 2"):
            DroneTrajectory(waypoints=[], speed_ms=10.0)

    def test_zero_speed_raises(self):
        with pytest.raises(ValidationError, match="speed_ms"):
            DroneTrajectory(waypoints=_two_waypoints(), speed_ms=0.0)

    def test_negative_speed_raises(self):
        with pytest.raises(ValidationError, match="speed_ms"):
            DroneTrajectory(waypoints=_two_waypoints(), speed_ms=-5.0)

    def test_nan_speed_raises(self):
        with pytest.raises(ValidationError, match="speed_ms"):
            DroneTrajectory(waypoints=_two_waypoints(), speed_ms=float("nan"))

    def test_inf_speed_raises(self):
        with pytest.raises(ValidationError, match="speed_ms"):
            DroneTrajectory(waypoints=_two_waypoints(), speed_ms=float("inf"))

    def test_waypoint_with_nan_coord_raises(self):
        bad_wps = [_wp(float("nan"), 0.0, 50.0), _wp(1000.0, 0.0, 30.0)]
        with pytest.raises(ValidationError, match="finite"):
            DroneTrajectory(waypoints=bad_wps, speed_ms=10.0)


class TestDroneTrajectoryYamlRoundTrip:
    def test_roundtrip_preserves_values(self):
        original = DroneTrajectory(
            waypoints=[
                TrajectoryWaypoint(x=500000.0, y=6100000.0, z_agl=100.0),
                TrajectoryWaypoint(x=500500.0, y=6100000.0, z_agl=60.0),
                TrajectoryWaypoint(x=501000.0, y=6100200.0, z_agl=20.0),
            ],
            speed_ms=18.5,
        )
        serialised = yaml.dump(original.model_dump(), default_flow_style=False)
        raw = yaml.safe_load(serialised)
        restored = DroneTrajectory(**raw)
        assert len(restored.waypoints) == 3
        assert restored.speed_ms == pytest.approx(18.5)
        assert restored.waypoints[0].x == pytest.approx(500000.0)
        assert restored.waypoints[2].z_agl == pytest.approx(20.0)

    def test_roundtrip_two_waypoints(self):
        original = DroneTrajectory(
            waypoints=[
                TrajectoryWaypoint(x=0.0, y=0.0, z_agl=50.0),
                TrajectoryWaypoint(x=200.0, y=300.0, z_agl=50.0),
            ],
            speed_ms=12.0,
        )
        raw = yaml.safe_load(yaml.dump(original.model_dump()))
        restored = DroneTrajectory(**raw)
        assert restored.waypoints[1].y == pytest.approx(300.0)
