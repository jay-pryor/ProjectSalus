"""Tests for the scenario YAML loader (ingest/scenario.py)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from salus.ingest.scenario import load_scenario
from salus.models.scenario import ScenarioConfig


def _write_yaml(path: Path, content: str) -> Path:
    """Write dedented YAML content to *path* and return it."""
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


class TestLoadScenarioValid:
    def test_minimal_scenario(self, tmp_path):
        """A scenario with only site_dem_path loads successfully."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            """\
            site_dem_path: site.tif
            """,
        )
        sc = load_scenario(scenario_file)
        assert isinstance(sc, ScenarioConfig)
        assert sc.site_dem_path == (tmp_path / "site.tif").resolve()

    def test_relative_paths_resolved_to_absolute(self, tmp_path):
        """Relative paths in YAML are resolved relative to the scenario file directory."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            """\
            site_dem_path: data/dem.tif
            site_dsm_path: data/dsm.tif
            boundary_path: data/boundary.geojson
            """,
        )
        sc = load_scenario(scenario_file)
        assert sc.site_dem_path == (tmp_path / "data" / "dem.tif").resolve()
        assert sc.site_dsm_path == (tmp_path / "data" / "dsm.tif").resolve()
        assert sc.boundary_path == (tmp_path / "data" / "boundary.geojson").resolve()

    def test_absolute_paths_preserved(self, tmp_path):
        """Absolute paths in YAML are preserved as-is."""
        abs_path = tmp_path / "dem.tif"
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            f"site_dem_path: {abs_path}\n",
        )
        sc = load_scenario(scenario_file)
        assert sc.site_dem_path == abs_path.resolve()

    def test_string_path_to_load_scenario(self, tmp_path):
        """load_scenario accepts a str path, not just Path."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            "site_dem_path: site.tif\n",
        )
        sc = load_scenario(str(scenario_file))
        assert isinstance(sc, ScenarioConfig)

    def test_sensor_placements_loaded(self, tmp_path):
        """Sensor placements in YAML are parsed into SensorPlacement instances."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            """\
            site_dem_path: site.tif
            sensor_placements:
              - sensor_name: DroneShield RfOne Mk2
                position_x: 500050.0
                position_y: 6100050.0
                bearing_deg: 0.0
              - sensor_name: Echodyne EchoGuard
                position_x: 500080.0
                position_y: 6100080.0
                bearing_deg: 90.0
            """,
        )
        sc = load_scenario(scenario_file)
        assert len(sc.sensor_placements) == 2
        assert sc.sensor_placements[0].sensor_name == "DroneShield RfOne Mk2"
        assert sc.sensor_placements[1].bearing_deg == pytest.approx(90.0)

    def test_effector_placements_loaded(self, tmp_path):
        """Effector placements in YAML are parsed into EffectorPlacement instances."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            """\
            site_dem_path: site.tif
            effector_placements:
              - effector_name: EOS Slinger
                position_x: 500060.0
                position_y: 6100060.0
                bearing_deg: 180.0
            """,
        )
        sc = load_scenario(scenario_file)
        assert len(sc.effector_placements) == 1
        assert sc.effector_placements[0].effector_name == "EOS Slinger"

    def test_threat_profiles_loaded(self, tmp_path):
        """threat_profiles list is loaded from YAML."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            """\
            site_dem_path: site.tif
            threat_profiles:
              - DJI Phantom 4
              - Autel EVO II
            """,
        )
        sc = load_scenario(scenario_file)
        assert sc.threat_profiles == ["DJI Phantom 4", "Autel EVO II"]

    def test_optional_fields_absent_give_defaults(self, tmp_path):
        """Absent optional fields default to None / empty list."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            "site_dem_path: site.tif\n",
        )
        sc = load_scenario(scenario_file)
        assert sc.site_dsm_path is None
        assert sc.boundary_path is None
        assert sc.sensor_placements == []
        assert sc.effector_placements == []
        assert sc.threat_profiles == []

    def test_full_scenario_round_trip(self, tmp_path):
        """A fully-populated scenario file loads correctly end-to-end."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            """\
            site_dem_path: dem.tif
            site_dsm_path: dsm.tif
            boundary_path: boundary.geojson
            sensor_placements:
              - sensor_name: DroneShield RfOne Mk2
                position_x: 500050.0
                position_y: 6100050.0
                bearing_deg: 0.0
                height_override_m: 3.0
            effector_placements:
              - effector_name: DroneShield DroneCannon Mk2
                position_x: 500055.0
                position_y: 6100055.0
                bearing_deg: 45.0
            threat_profiles:
              - DJI Phantom 4
            """,
        )
        sc = load_scenario(scenario_file)
        assert sc.site_dem_path == (tmp_path / "dem.tif").resolve()
        assert sc.site_dsm_path == (tmp_path / "dsm.tif").resolve()
        assert sc.boundary_path == (tmp_path / "boundary.geojson").resolve()
        assert len(sc.sensor_placements) == 1
        assert sc.sensor_placements[0].height_override_m == pytest.approx(3.0)
        assert len(sc.effector_placements) == 1
        assert sc.threat_profiles == ["DJI Phantom 4"]


class TestLoadScenarioErrors:
    def test_file_not_found_raises(self, tmp_path):
        """Missing scenario file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Scenario file not found"):
            load_scenario(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        """A file with invalid YAML syntax raises ValueError."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("key: [unclosed bracket\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_scenario(bad_yaml)

    def test_empty_file_raises(self, tmp_path):
        """An empty YAML file raises ValueError."""
        empty = tmp_path / "empty.yaml"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            load_scenario(empty)

    def test_list_yaml_raises(self, tmp_path):
        """A YAML file with a top-level list (not a mapping) raises ValueError."""
        list_yaml = tmp_path / "list.yaml"
        list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapping"):
            load_scenario(list_yaml)

    def test_missing_required_field_raises(self, tmp_path):
        """Missing site_dem_path raises ValueError."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            "threat_profiles:\n  - DJI Phantom 4\n",
        )
        with pytest.raises(ValueError, match="Invalid scenario"):
            load_scenario(scenario_file)

    def test_invalid_placement_raises(self, tmp_path):
        """A sensor placement with an invalid bearing raises ValueError."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            """\
            site_dem_path: site.tif
            sensor_placements:
              - sensor_name: MySensor
                position_x: 0.0
                position_y: 0.0
                bearing_deg: 400.0
            """,
        )
        with pytest.raises(ValueError, match="Invalid scenario"):
            load_scenario(scenario_file)

    def test_non_string_path_field_raises(self, tmp_path):
        """A YAML path field with a non-string value (e.g. integer) raises ValueError."""
        scenario_file = tmp_path / "scenario.yaml"
        # YAML integer 42 for site_dem_path
        scenario_file.write_text("site_dem_path: 42\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a string path"):
            load_scenario(scenario_file)


class TestLoadScenarioTrajectory:
    """Tests for trajectory_path resolution and DroneTrajectory loading."""

    _TRAJ_YAML = """\
        speed_ms: 15.0
        waypoints:
          - x: 500000.0
            y: 6100000.0
            z_agl: 80.0
          - x: 500300.0
            y: 6100000.0
            z_agl: 50.0
          - x: 500600.0
            y: 6100000.0
            z_agl: 20.0
        """

    def test_trajectory_loaded_when_path_set(self, tmp_path):
        """When trajectory_path is set, load_scenario populates trajectory."""
        traj_file = _write_yaml(tmp_path / "approach.yaml", self._TRAJ_YAML)
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            f"site_dem_path: site.tif\ntrajectory_path: {traj_file.name}\n",
        )
        sc = load_scenario(scenario_file)
        assert sc.trajectory is not None
        assert len(sc.trajectory.waypoints) == 3
        assert sc.trajectory.speed_ms == pytest.approx(15.0)
        assert sc.trajectory.waypoints[0].z_agl == pytest.approx(80.0)

    def test_trajectory_path_resolved_to_absolute(self, tmp_path):
        """trajectory_path is resolved to absolute just like other path fields."""
        _write_yaml(tmp_path / "approach.yaml", self._TRAJ_YAML)
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            "site_dem_path: site.tif\ntrajectory_path: approach.yaml\n",
        )
        sc = load_scenario(scenario_file)
        assert sc.trajectory_path == (tmp_path / "approach.yaml").resolve()

    def test_trajectory_none_when_path_absent(self, tmp_path):
        """trajectory is None when trajectory_path is not in the scenario file."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            "site_dem_path: site.tif\n",
        )
        sc = load_scenario(scenario_file)
        assert sc.trajectory is None
        assert sc.trajectory_path is None

    def test_trajectory_file_not_found_raises(self, tmp_path):
        """Missing trajectory file raises FileNotFoundError."""
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            "site_dem_path: site.tif\ntrajectory_path: nonexistent.yaml\n",
        )
        with pytest.raises(FileNotFoundError, match="Trajectory file not found"):
            load_scenario(scenario_file)

    def test_invalid_trajectory_yaml_raises(self, tmp_path):
        """A trajectory file with invalid YAML raises ValueError."""
        bad = tmp_path / "bad_traj.yaml"
        bad.write_text("speed_ms: [unclosed\n", encoding="utf-8")
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            f"site_dem_path: site.tif\ntrajectory_path: {bad.name}\n",
        )
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_scenario(scenario_file)

    def test_invalid_trajectory_content_raises(self, tmp_path):
        """A trajectory file with valid YAML but invalid DroneTrajectory raises ValueError."""
        bad = _write_yaml(
            tmp_path / "bad_traj.yaml",
            "speed_ms: 0.0\nwaypoints:\n  - {x: 0.0, y: 0.0, z_agl: 50.0}\n",
        )
        scenario_file = _write_yaml(
            tmp_path / "scenario.yaml",
            f"site_dem_path: site.tif\ntrajectory_path: {bad.name}\n",
        )
        with pytest.raises(ValueError, match="Invalid trajectory"):
            load_scenario(scenario_file)
