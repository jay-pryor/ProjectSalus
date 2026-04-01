"""Tests for ThreatProfile and ThreatCorridor Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from salus.models.threat import (
    EvasionCapability,
    ThreatCorridor,
    ThreatProfile,
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
