"""Tests for YAML sensor/effector database loader."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest

from salus.ingest.sensors import load_effectors, load_sensors
from salus.models.sensor import EffectorType, SensorType

# ---------------------------------------------------------------------------
# YAML fixtures (written to tmp_path in each test)
# ---------------------------------------------------------------------------

VALID_SENSOR_YAML = textwrap.dedent("""\
    name: Test RF Sensor
    type: RF
    max_range_m: 3000.0
    min_range_m: 50.0
    azimuth_coverage_deg: 360.0
    elevation_coverage_deg: 90.0
    frequency_bands:
      - "2.4 GHz"
      - "5.8 GHz"
    requires_los: false
    mounting_height_m: 3.0
    cost_aud: 95000.0
""")

VALID_SENSOR_MINIMAL_YAML = textwrap.dedent("""\
    name: Minimal Radar
    type: Radar
    max_range_m: 500.0
    azimuth_coverage_deg: 90.0
    elevation_coverage_deg: 45.0
""")

VALID_SENSOR_LIST_YAML = textwrap.dedent("""\
    - name: Sensor Alpha
      type: RF
      max_range_m: 1000.0
      azimuth_coverage_deg: 360.0
      elevation_coverage_deg: 90.0
    - name: Sensor Beta
      type: EO_IR
      max_range_m: 2000.0
      azimuth_coverage_deg: 60.0
      elevation_coverage_deg: 30.0
""")

VALID_EFFECTOR_YAML = textwrap.dedent("""\
    name: Test RF Jammer
    type: RF_Jammer
    max_range_m: 500.0
    min_range_m: 5.0
    engagement_arc_deg: 360.0
    reaction_time_s: 2.0
    simultaneous_engagements: 2
    reload_time_s: 0.5
    defeat_probability: 0.95
    requires_los: false
    defeat_mechanism: Disrupts RF control link between operator and UAS
""")

VALID_EFFECTOR_LIST_YAML = textwrap.dedent("""\
    - name: Effector Alpha
      type: RF_Jammer
      max_range_m: 300.0
      engagement_arc_deg: 180.0
      reaction_time_s: 1.5
      defeat_probability: 0.9
      requires_los: false
      defeat_mechanism: RF jamming
    - name: Effector Beta
      type: Kinetic
      max_range_m: 800.0
      engagement_arc_deg: 360.0
      reaction_time_s: 3.0
      defeat_probability: 0.85
      requires_los: true
      defeat_mechanism: Kinetic intercept
""")


# ---------------------------------------------------------------------------
# load_sensors
# ---------------------------------------------------------------------------


class TestLoadSensors:
    def test_single_sensor_from_yaml(self, tmp_path):
        """A single-mapping YAML file loads as one SensorDefinition."""
        (tmp_path / "sensor.yaml").write_text(VALID_SENSOR_YAML)
        sensors = load_sensors(tmp_path)
        assert len(sensors) == 1
        s = sensors[0]
        assert s.name == "Test RF Sensor"
        assert s.type == SensorType.RF
        assert s.max_range_m == pytest.approx(3000.0)
        assert s.frequency_bands == ["2.4 GHz", "5.8 GHz"]
        assert s.requires_los is False

    def test_minimal_sensor_defaults_applied(self, tmp_path):
        """Optional fields use their defaults when not specified."""
        (tmp_path / "minimal.yaml").write_text(VALID_SENSOR_MINIMAL_YAML)
        sensors = load_sensors(tmp_path)
        assert len(sensors) == 1
        s = sensors[0]
        assert s.min_range_m == pytest.approx(0.0)
        assert s.frequency_bands == []
        assert s.requires_los is True
        assert s.mounting_height_m == pytest.approx(0.0)
        assert s.cost_aud is None

    def test_list_yaml_loads_multiple_sensors(self, tmp_path):
        """A YAML file with a list of mappings loads multiple sensors."""
        (tmp_path / "multi.yaml").write_text(VALID_SENSOR_LIST_YAML)
        sensors = load_sensors(tmp_path)
        assert len(sensors) == 2
        assert sensors[0].name == "Sensor Alpha"
        assert sensors[1].name == "Sensor Beta"
        assert sensors[1].type == SensorType.EO_IR

    def test_multiple_files_aggregated(self, tmp_path):
        """Sensors from multiple YAML files are combined into one list."""
        (tmp_path / "a.yaml").write_text(VALID_SENSOR_YAML)
        (tmp_path / "b.yaml").write_text(VALID_SENSOR_MINIMAL_YAML)
        sensors = load_sensors(tmp_path)
        assert len(sensors) == 2

    def test_yml_extension_recognised(self, tmp_path):
        """Files with .yml extension are loaded as well as .yaml."""
        (tmp_path / "sensor.yml").write_text(VALID_SENSOR_YAML)
        sensors = load_sensors(tmp_path)
        assert len(sensors) == 1

    def test_non_yaml_files_ignored(self, tmp_path):
        """Non-YAML files in the directory are silently ignored."""
        (tmp_path / "sensor.yaml").write_text(VALID_SENSOR_YAML)
        (tmp_path / "readme.txt").write_text("ignore me")
        (tmp_path / "notes.md").write_text("# ignore me too")
        sensors = load_sensors(tmp_path)
        assert len(sensors) == 1

    def test_empty_directory_warns(self, tmp_path):
        """An empty directory returns an empty list and emits a warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            sensors = load_sensors(tmp_path)
        assert sensors == []
        assert any("No YAML files" in str(w.message) for w in caught)

    def test_directory_not_found_raises(self, tmp_path):
        """A non-existent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="sensor"):
            load_sensors(tmp_path / "nonexistent")

    def test_path_is_file_raises(self, tmp_path):
        """Passing a file path instead of a directory raises NotADirectoryError."""
        f = tmp_path / "not_a_dir.yaml"
        f.write_text(VALID_SENSOR_YAML)
        with pytest.raises(NotADirectoryError):
            load_sensors(f)

    def test_invalid_yaml_syntax_raises(self, tmp_path):
        """A file with invalid YAML syntax raises ValueError with the filename."""
        (tmp_path / "bad.yaml").write_text("name: [unclosed bracket")
        with pytest.raises(ValueError, match="bad.yaml"):
            load_sensors(tmp_path)

    def test_invalid_sensor_data_raises(self, tmp_path):
        """A sensor with invalid field values raises ValueError with the filename."""
        bad = textwrap.dedent("""\
            name: Bad
            type: RF
            max_range_m: -100.0
            azimuth_coverage_deg: 360.0
            elevation_coverage_deg: 90.0
        """)
        (tmp_path / "bad.yaml").write_text(bad)
        with pytest.raises(ValueError, match="bad.yaml"):
            load_sensors(tmp_path)

    def test_accepts_path_object(self, tmp_path):
        """load_sensors accepts a pathlib.Path as well as a string."""
        (tmp_path / "sensor.yaml").write_text(VALID_SENSOR_YAML)
        assert len(load_sensors(Path(tmp_path))) == 1

    def test_accepts_string_path(self, tmp_path):
        """load_sensors accepts a plain string path."""
        (tmp_path / "sensor.yaml").write_text(VALID_SENSOR_YAML)
        assert len(load_sensors(str(tmp_path))) == 1

    def test_empty_yaml_file_skipped(self, tmp_path):
        """An empty YAML file contributes zero records without error."""
        (tmp_path / "empty.yaml").write_text("")
        (tmp_path / "real.yaml").write_text(VALID_SENSOR_YAML)
        sensors = load_sensors(tmp_path)
        assert len(sensors) == 1

    def test_list_with_non_dict_entry_raises(self, tmp_path):
        """A YAML list containing a non-mapping entry raises ValueError."""
        bad = textwrap.dedent("""\
            - name: OK
              type: RF
              max_range_m: 100.0
              azimuth_coverage_deg: 360.0
              elevation_coverage_deg: 90.0
            - just_a_scalar
        """)
        (tmp_path / "bad.yaml").write_text(bad)
        with pytest.raises(ValueError, match="bad.yaml"):
            load_sensors(tmp_path)


# ---------------------------------------------------------------------------
# load_effectors
# ---------------------------------------------------------------------------


class TestLoadEffectors:
    def test_single_effector_from_yaml(self, tmp_path):
        """A single-mapping YAML file loads as one EffectorDefinition."""
        (tmp_path / "effector.yaml").write_text(VALID_EFFECTOR_YAML)
        effectors = load_effectors(tmp_path)
        assert len(effectors) == 1
        e = effectors[0]
        assert e.name == "Test RF Jammer"
        assert e.type == EffectorType.RF_Jammer
        assert e.defeat_probability == pytest.approx(0.95)
        assert e.simultaneous_engagements == 2

    def test_list_yaml_loads_multiple_effectors(self, tmp_path):
        """A YAML list file loads multiple effectors."""
        (tmp_path / "multi.yaml").write_text(VALID_EFFECTOR_LIST_YAML)
        effectors = load_effectors(tmp_path)
        assert len(effectors) == 2
        assert effectors[0].type == EffectorType.RF_Jammer
        assert effectors[1].type == EffectorType.Kinetic

    def test_directory_not_found_raises(self, tmp_path):
        """A non-existent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="effector"):
            load_effectors(tmp_path / "nonexistent")

    def test_invalid_effector_data_raises(self, tmp_path):
        """An effector with defeat_probability > 1 raises ValueError."""
        bad = textwrap.dedent("""\
            name: Bad Effector
            type: Kinetic
            max_range_m: 500.0
            engagement_arc_deg: 360.0
            reaction_time_s: 1.0
            defeat_probability: 1.5
            defeat_mechanism: Impossible
        """)
        (tmp_path / "bad.yaml").write_text(bad)
        with pytest.raises(ValueError, match="bad.yaml"):
            load_effectors(tmp_path)

    def test_empty_directory_warns(self, tmp_path):
        """Empty effector directory returns empty list and warns."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            effectors = load_effectors(tmp_path)
        assert effectors == []
        assert any("No YAML files" in str(w.message) for w in caught)
