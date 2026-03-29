"""Tests for SensorPlacement model (models/scenario.py)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from salus.models.scenario import SensorPlacement


class TestSensorPlacement:
    def test_valid_minimal(self):
        """Minimal valid SensorPlacement with required fields only."""
        sp = SensorPlacement(
            sensor_name="DroneShield RfOne Mk2",
            position_x=500050.0,
            position_y=6100050.0,
            bearing_deg=0.0,
        )
        assert sp.sensor_name == "DroneShield RfOne Mk2"
        assert sp.position_x == pytest.approx(500050.0)
        assert sp.position_y == pytest.approx(6100050.0)
        assert sp.bearing_deg == pytest.approx(0.0)
        assert sp.height_override_m is None

    def test_valid_with_height_override(self):
        """SensorPlacement with optional height_override_m set."""
        sp = SensorPlacement(
            sensor_name="Anduril WISP",
            position_x=0.0,
            position_y=0.0,
            bearing_deg=180.0,
            height_override_m=5.0,
        )
        assert sp.height_override_m == pytest.approx(5.0)

    def test_bearing_zero_valid(self):
        """bearing_deg=0.0 (north) is valid."""
        sp = SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=0.0)
        assert sp.bearing_deg == pytest.approx(0.0)

    def test_bearing_just_below_360_valid(self):
        """bearing_deg=359.9 is valid (just below exclusive upper bound)."""
        sp = SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=359.9)
        assert sp.bearing_deg == pytest.approx(359.9)

    def test_bearing_360_raises(self):
        """bearing_deg=360.0 is invalid — must be in [0, 360)."""
        with pytest.raises(ValidationError, match="bearing_deg"):
            SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=360.0)

    def test_bearing_negative_raises(self):
        """Negative bearing_deg is invalid."""
        with pytest.raises(ValidationError, match="bearing_deg"):
            SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=-1.0)

    def test_empty_sensor_name_raises(self):
        """Empty sensor_name is invalid."""
        with pytest.raises(ValidationError, match="sensor_name"):
            SensorPlacement(sensor_name="", position_x=0.0, position_y=0.0, bearing_deg=0.0)

    def test_whitespace_only_sensor_name_raises(self):
        """Whitespace-only sensor_name is invalid."""
        with pytest.raises(ValidationError, match="sensor_name"):
            SensorPlacement(sensor_name="   ", position_x=0.0, position_y=0.0, bearing_deg=0.0)

    def test_height_override_zero_valid(self):
        """height_override_m=0.0 is valid (ground level)."""
        sp = SensorPlacement(
            sensor_name="S",
            position_x=0.0,
            position_y=0.0,
            bearing_deg=0.0,
            height_override_m=0.0,
        )
        assert sp.height_override_m == pytest.approx(0.0)

    def test_height_override_negative_raises(self):
        """Negative height_override_m is invalid."""
        with pytest.raises(ValidationError, match="height_override_m"):
            SensorPlacement(
                sensor_name="S",
                position_x=0.0,
                position_y=0.0,
                bearing_deg=0.0,
                height_override_m=-1.0,
            )

    def test_height_override_none_valid(self):
        """height_override_m=None is valid (use sensor default)."""
        sp = SensorPlacement(
            sensor_name="S",
            position_x=0.0,
            position_y=0.0,
            bearing_deg=0.0,
            height_override_m=None,
        )
        assert sp.height_override_m is None

    def test_position_can_be_negative(self):
        """position_x and position_y can be any float including negative."""
        sp = SensorPlacement(
            sensor_name="S", position_x=-1000.0, position_y=-2000.0, bearing_deg=45.0
        )
        assert sp.position_x == pytest.approx(-1000.0)
        assert sp.position_y == pytest.approx(-2000.0)

    def test_bearing_90_east_valid(self):
        """bearing_deg=90.0 (east) is valid and stored exactly."""
        sp = SensorPlacement(sensor_name="S", position_x=0.0, position_y=0.0, bearing_deg=90.0)
        assert sp.bearing_deg == pytest.approx(90.0)
