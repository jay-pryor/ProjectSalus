"""Tests for SensorDefinition and EffectorDefinition Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from salus.models.sensor import (
    EffectorDefinition,
    EffectorType,
    SensorDefinition,
    SensorType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_sensor(**overrides) -> dict:
    base = {
        "name": "Test RF Sensor",
        "type": SensorType.RF,
        "max_range_m": 1000.0,
        "min_range_m": 10.0,
        "azimuth_coverage_deg": 360.0,
        "elevation_coverage_deg": 90.0,
        "requires_los": True,
        "mounting_height_m": 2.0,
    }
    base.update(overrides)
    return base


def _valid_effector(**overrides) -> dict:
    base = {
        "name": "Test RF Jammer",
        "type": EffectorType.RF_Jammer,
        "max_range_m": 500.0,
        "min_range_m": 5.0,
        "engagement_arc_deg": 360.0,
        "reaction_time_s": 2.0,
        "simultaneous_engagements": 1,
        "reload_time_s": 0.0,
        "defeat_probability": 0.9,
        "requires_los": False,
        "defeat_mechanism": "RF jamming of control link",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# SensorDefinition — valid construction
# ---------------------------------------------------------------------------


class TestSensorDefinitionValid:
    def test_minimal_required_fields(self):
        s = SensorDefinition(
            name="Basic",
            type=SensorType.Radar,
            max_range_m=500.0,
            azimuth_coverage_deg=90.0,
            elevation_coverage_deg=45.0,
        )
        assert s.min_range_m == 0.0
        assert s.frequency_bands == []
        assert s.requires_los is True
        assert s.mounting_height_m == 0.0
        assert s.cost_aud is None

    def test_all_fields(self):
        s = SensorDefinition(
            **_valid_sensor(
                frequency_bands=["2.4 GHz", "5.8 GHz"],
                cost_aud=95000.0,
            )
        )
        assert s.name == "Test RF Sensor"
        assert s.type == SensorType.RF
        assert s.frequency_bands == ["2.4 GHz", "5.8 GHz"]
        assert s.cost_aud == 95000.0

    def test_all_sensor_types(self):
        for sensor_type in SensorType:
            s = SensorDefinition(**_valid_sensor(type=sensor_type))
            assert s.type == sensor_type

    def test_full_azimuth_360(self):
        s = SensorDefinition(**_valid_sensor(azimuth_coverage_deg=360.0))
        assert s.azimuth_coverage_deg == 360.0

    def test_cost_aud_none(self):
        s = SensorDefinition(**_valid_sensor(cost_aud=None))
        assert s.cost_aud is None

    def test_cost_aud_zero(self):
        s = SensorDefinition(**_valid_sensor(cost_aud=0.0))
        assert s.cost_aud == 0.0


# ---------------------------------------------------------------------------
# SensorDefinition — validation failures
# ---------------------------------------------------------------------------


class TestSensorDefinitionInvalid:
    def test_max_range_zero_rejected(self):
        with pytest.raises(ValidationError, match="max_range_m"):
            SensorDefinition(**_valid_sensor(max_range_m=0.0))

    def test_max_range_negative_rejected(self):
        with pytest.raises(ValidationError, match="max_range_m"):
            SensorDefinition(**_valid_sensor(max_range_m=-100.0))

    def test_min_range_negative_rejected(self):
        with pytest.raises(ValidationError, match="min_range_m"):
            SensorDefinition(**_valid_sensor(min_range_m=-1.0))

    def test_min_range_equals_max_range_rejected(self):
        with pytest.raises(ValidationError, match="min_range_m"):
            SensorDefinition(**_valid_sensor(min_range_m=1000.0, max_range_m=1000.0))

    def test_min_range_exceeds_max_range_rejected(self):
        with pytest.raises(ValidationError, match="min_range_m"):
            SensorDefinition(**_valid_sensor(min_range_m=2000.0, max_range_m=1000.0))

    def test_azimuth_zero_rejected(self):
        with pytest.raises(ValidationError, match="azimuth_coverage_deg"):
            SensorDefinition(**_valid_sensor(azimuth_coverage_deg=0.0))

    def test_azimuth_exceeds_360_rejected(self):
        with pytest.raises(ValidationError, match="azimuth_coverage_deg"):
            SensorDefinition(**_valid_sensor(azimuth_coverage_deg=361.0))

    def test_elevation_zero_rejected(self):
        with pytest.raises(ValidationError, match="elevation_coverage_deg"):
            SensorDefinition(**_valid_sensor(elevation_coverage_deg=0.0))

    def test_elevation_exceeds_180_rejected(self):
        with pytest.raises(ValidationError, match="elevation_coverage_deg"):
            SensorDefinition(**_valid_sensor(elevation_coverage_deg=181.0))

    def test_mounting_height_negative_rejected(self):
        with pytest.raises(ValidationError, match="mounting_height_m"):
            SensorDefinition(**_valid_sensor(mounting_height_m=-1.0))

    def test_cost_aud_negative_rejected(self):
        with pytest.raises(ValidationError, match="cost_aud"):
            SensorDefinition(**_valid_sensor(cost_aud=-1.0))

    def test_invalid_sensor_type_rejected(self):
        with pytest.raises(ValidationError):
            SensorDefinition(**_valid_sensor(type="LIDAR"))

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            SensorDefinition(**_valid_sensor(name=""))

    def test_whitespace_name_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            SensorDefinition(**_valid_sensor(name="   "))


# ---------------------------------------------------------------------------
# EffectorDefinition — valid construction
# ---------------------------------------------------------------------------


class TestEffectorDefinitionValid:
    def test_minimal_construction(self):
        e = EffectorDefinition(**_valid_effector())
        assert e.simultaneous_engagements == 1
        assert e.reload_time_s == 0.0
        assert e.requires_los is False

    def test_all_effector_types(self):
        for eff_type in EffectorType:
            e = EffectorDefinition(**_valid_effector(type=eff_type))
            assert e.type == eff_type

    def test_defeat_probability_zero(self):
        e = EffectorDefinition(**_valid_effector(defeat_probability=0.0))
        assert e.defeat_probability == 0.0

    def test_defeat_probability_one(self):
        e = EffectorDefinition(**_valid_effector(defeat_probability=1.0))
        assert e.defeat_probability == 1.0

    def test_multiple_simultaneous_engagements(self):
        e = EffectorDefinition(**_valid_effector(simultaneous_engagements=4))
        assert e.simultaneous_engagements == 4


# ---------------------------------------------------------------------------
# EffectorDefinition — validation failures
# ---------------------------------------------------------------------------


class TestEffectorDefinitionInvalid:
    def test_max_range_zero_rejected(self):
        with pytest.raises(ValidationError, match="max_range_m"):
            EffectorDefinition(**_valid_effector(max_range_m=0.0))

    def test_max_range_negative_rejected(self):
        with pytest.raises(ValidationError, match="max_range_m"):
            EffectorDefinition(**_valid_effector(max_range_m=-1.0))

    def test_min_range_negative_rejected(self):
        with pytest.raises(ValidationError, match="min_range_m"):
            EffectorDefinition(**_valid_effector(min_range_m=-1.0))

    def test_min_range_equals_max_range_rejected(self):
        with pytest.raises(ValidationError, match="min_range_m"):
            EffectorDefinition(**_valid_effector(min_range_m=500.0, max_range_m=500.0))

    def test_min_range_exceeds_max_range_rejected(self):
        with pytest.raises(ValidationError, match="min_range_m"):
            EffectorDefinition(**_valid_effector(min_range_m=600.0, max_range_m=500.0))

    def test_engagement_arc_zero_rejected(self):
        with pytest.raises(ValidationError, match="engagement_arc_deg"):
            EffectorDefinition(**_valid_effector(engagement_arc_deg=0.0))

    def test_engagement_arc_exceeds_360_rejected(self):
        with pytest.raises(ValidationError, match="engagement_arc_deg"):
            EffectorDefinition(**_valid_effector(engagement_arc_deg=361.0))

    def test_reaction_time_zero_rejected(self):
        with pytest.raises(ValidationError, match="reaction_time_s"):
            EffectorDefinition(**_valid_effector(reaction_time_s=0.0))

    def test_reaction_time_negative_rejected(self):
        with pytest.raises(ValidationError, match="reaction_time_s"):
            EffectorDefinition(**_valid_effector(reaction_time_s=-1.0))

    def test_simultaneous_engagements_zero_rejected(self):
        with pytest.raises(ValidationError, match="simultaneous_engagements"):
            EffectorDefinition(**_valid_effector(simultaneous_engagements=0))

    def test_reload_time_negative_rejected(self):
        with pytest.raises(ValidationError, match="reload_time_s"):
            EffectorDefinition(**_valid_effector(reload_time_s=-1.0))

    def test_defeat_probability_below_zero_rejected(self):
        with pytest.raises(ValidationError, match="defeat_probability"):
            EffectorDefinition(**_valid_effector(defeat_probability=-0.1))

    def test_defeat_probability_above_one_rejected(self):
        with pytest.raises(ValidationError, match="defeat_probability"):
            EffectorDefinition(**_valid_effector(defeat_probability=1.1))

    def test_invalid_effector_type_rejected(self):
        with pytest.raises(ValidationError):
            EffectorDefinition(**_valid_effector(type="Laser"))

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            EffectorDefinition(**_valid_effector(name=""))

    def test_empty_defeat_mechanism_rejected(self):
        with pytest.raises(ValidationError, match="defeat_mechanism"):
            EffectorDefinition(**_valid_effector(defeat_mechanism=""))

    def test_whitespace_defeat_mechanism_rejected(self):
        with pytest.raises(ValidationError, match="defeat_mechanism"):
            EffectorDefinition(**_valid_effector(defeat_mechanism="   "))
