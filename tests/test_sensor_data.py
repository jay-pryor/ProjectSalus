"""Smoke tests for the bundled sensor YAML data files.

These tests verify that every YAML file in src/salus/data/sensors/ loads and
validates against SensorDefinition without error. They are intentionally
lightweight — the authoritative validation logic is tested in test_sensors_ingest.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from salus.ingest.sensors import load_sensors
from salus.models.sensor import SensorType

DATA_DIR = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bundled_sensors():
    """Load all bundled sensor YAML files once for the module."""
    return load_sensors(DATA_DIR)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBundledSensorData:
    def test_at_least_five_sensors_present(self, bundled_sensors):
        """The bundled database must contain at least 5 sensor definitions."""
        assert len(bundled_sensors) >= 5

    def test_all_sensor_types_represented(self, bundled_sensors):
        """At least one sensor of each required type must be present."""
        types_present = {s.type for s in bundled_sensors}
        assert SensorType.RF in types_present
        assert SensorType.Radar in types_present
        assert SensorType.EO_IR in types_present
        assert SensorType.Acoustic in types_present

    def test_all_sensors_have_non_empty_names(self, bundled_sensors):
        """Every sensor must have a non-empty name."""
        for sensor in bundled_sensors:
            assert sensor.name.strip(), f"Empty name in sensor: {sensor}"

    def test_all_max_ranges_positive(self, bundled_sensors):
        """Every sensor must have a positive max_range_m."""
        for sensor in bundled_sensors:
            assert sensor.max_range_m > 0, f"Non-positive range for {sensor.name}"

    def test_all_min_ranges_less_than_max(self, bundled_sensors):
        """Every sensor's min_range_m must be less than max_range_m."""
        for sensor in bundled_sensors:
            assert sensor.min_range_m < sensor.max_range_m, (
                f"min_range >= max_range for {sensor.name}"
            )

    def test_all_azimuths_valid(self, bundled_sensors):
        """Every sensor must have azimuth_coverage_deg in (0, 360]."""
        for sensor in bundled_sensors:
            assert 0 < sensor.azimuth_coverage_deg <= 360, (
                f"Invalid azimuth for {sensor.name}: {sensor.azimuth_coverage_deg}"
            )

    def test_rf_sensors_do_not_require_los(self, bundled_sensors):
        """RF (passive) sensors must not require LOS."""
        rf_sensors = [s for s in bundled_sensors if s.type == SensorType.RF]
        for sensor in rf_sensors:
            assert sensor.requires_los is False, f"RF sensor {sensor.name} incorrectly requires LOS"

    def test_radar_sensors_require_los(self, bundled_sensors):
        """Radar sensors must require LOS."""
        radar_sensors = [s for s in bundled_sensors if s.type == SensorType.Radar]
        for sensor in radar_sensors:
            assert sensor.requires_los is True, (
                f"Radar sensor {sensor.name} incorrectly does not require LOS"
            )

    def test_eoir_sensors_require_los(self, bundled_sensors):
        """EO/IR sensors must require LOS."""
        eoir_sensors = [s for s in bundled_sensors if s.type == SensorType.EO_IR]
        for sensor in eoir_sensors:
            assert sensor.requires_los is True, (
                f"EO/IR sensor {sensor.name} incorrectly does not require LOS"
            )

    def test_no_cost_data_present(self, bundled_sensors):
        """Cost data is not publicly available; all cost_aud fields should be None."""
        for sensor in bundled_sensors:
            assert sensor.cost_aud is None, (
                f"Unexpected cost data for {sensor.name}: {sensor.cost_aud}"
            )
