"""Tests for the Salus CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from salus.cli import main

# Bundled sensor definitions shipped with the package.
_BUNDLED_SENSOR_DIR: Path = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"


@pytest.fixture
def scenario_los_yaml(flat_dem_path, tmp_path):
    """Scenario YAML with one LOS sensor (Echodyne EchoGuard) at the DEM centre."""
    data = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [
            {
                "sensor_name": "Echodyne EchoGuard",
                "position_x": 500050.0,
                "position_y": 6100050.0,
                "bearing_deg": 0.0,
            }
        ],
    }
    path = tmp_path / "scenario_los.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


@pytest.fixture
def scenario_nonlos_yaml(flat_dem_path, tmp_path):
    """Scenario YAML with one non-LOS sensor (DroneShield RfOne Mk2)."""
    data = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [
            {
                "sensor_name": "DroneShield RfOne Mk2",
                "position_x": 500050.0,
                "position_y": 6100050.0,
                "bearing_deg": 0.0,
            }
        ],
    }
    path = tmp_path / "scenario_nonlos.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


@pytest.fixture
def scenario_unknown_sensor_yaml(flat_dem_path, tmp_path):
    """Scenario YAML referencing a sensor name that does not exist in the database."""
    data = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [
            {
                "sensor_name": "Nonexistent Sensor XYZ",
                "position_x": 500050.0,
                "position_y": 6100050.0,
                "bearing_deg": 0.0,
            }
        ],
    }
    path = tmp_path / "scenario_unknown.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


@pytest.fixture
def scenario_empty_placements_yaml(flat_dem_path, tmp_path):
    """Scenario YAML with no sensor placements."""
    data = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [],
    }
    path = tmp_path / "scenario_empty.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


class TestMainGroup:
    def test_help(self):
        """--help must exit 0 and mention salus."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "salus" in result.output.lower()

    def test_version(self):
        """--version must exit 0 and print a version string."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestViewshedCommand:
    def test_help(self):
        """viewshed --help must exit 0 and list required options."""
        runner = CliRunner()
        result = runner.invoke(main, ["viewshed", "--help"])
        assert result.exit_code == 0
        assert "--dem" in result.output
        assert "--x" in result.output
        assert "--y" in result.output

    def test_basic_run_produces_png(self, flat_dem_path, tmp_path):
        """viewshed must produce a PNG when given a valid DEM and observer."""
        runner = CliRunner()
        out = tmp_path / "output.png"
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(flat_dem_path),
                "--x",
                "500050",
                "--y",
                "6100050",
                "--height",
                "10",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_output_mentions_coverage_percentage(self, flat_dem_path, tmp_path):
        """CLI output must report the coverage percentage."""
        runner = CliRunner()
        out = tmp_path / "output.png"
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(flat_dem_path),
                "--x",
                "500050",
                "--y",
                "6100050",
                "--height",
                "10",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0
        assert "visible" in result.output

    def test_max_range_option(self, flat_dem_path, tmp_path):
        """--range option must be accepted and not cause errors."""
        runner = CliRunner()
        out = tmp_path / "ranged.png"
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(flat_dem_path),
                "--x",
                "500050",
                "--y",
                "6100050",
                "--height",
                "2",
                "--range",
                "30",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_custom_title(self, flat_dem_path, tmp_path):
        """--title option must be accepted without error."""
        runner = CliRunner()
        out = tmp_path / "titled.png"
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(flat_dem_path),
                "--x",
                "500050",
                "--y",
                "6100050",
                "--output",
                str(out),
                "--title",
                "Site Alpha",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_missing_dem_exits_nonzero(self, tmp_path):
        """A DEM path that does not exist must cause a non-zero exit."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(tmp_path / "nonexistent.tif"),
                "--x",
                "500050",
                "--y",
                "6100050",
                "--output",
                str(tmp_path / "out.png"),
            ],
        )
        assert result.exit_code != 0

    def test_observer_outside_extent_exits_nonzero(self, flat_dem_path, tmp_path):
        """An observer position outside the DEM extent must exit non-zero with an error message."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(flat_dem_path),
                "--x",
                "0",  # Well outside the 500000–500100 extent
                "--y",
                "6100050",
                "--output",
                str(tmp_path / "out.png"),
            ],
        )
        assert result.exit_code != 0
        assert "outside" in result.output.lower() or "extent" in result.output.lower()

    def test_unrecognised_output_extension_warns(self, flat_dem_path, tmp_path):
        """An unrecognised output extension must produce a warning in stderr."""
        runner = CliRunner()
        out = tmp_path / "output.xyz"
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(flat_dem_path),
                "--x",
                "500050",
                "--y",
                "6100050",
                "--output",
                str(out),
            ],
        )
        assert "Warning" in result.output or "unrecognised" in result.output

    def test_corrupt_dem_exits_nonzero(self, tmp_path):
        """A file that exists but is not a valid rasterio dataset must exit non-zero."""
        bad_dem = tmp_path / "bad.tif"
        bad_dem.write_text("not a geotiff")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(bad_dem),
                "--x",
                "500050",
                "--y",
                "6100050",
                "--output",
                str(tmp_path / "out.png"),
            ],
        )
        assert result.exit_code != 0

    def test_ridge_dem_runs(self, ridge_dem_path, tmp_path):
        """viewshed must complete successfully on the ridge DEM fixture."""
        runner = CliRunner()
        out = tmp_path / "ridge.png"
        result = runner.invoke(
            main,
            [
                "viewshed",
                "--dem",
                str(ridge_dem_path),
                "--x",
                "500100",
                "--y",
                "6100190",  # North of ridge (row ~10)
                "--height",
                "2",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()


class TestSimulateCommand:
    def test_help(self):
        """simulate --help must exit 0 and mention scenario."""
        runner = CliRunner()
        result = runner.invoke(main, ["simulate", "--help"])
        assert result.exit_code == 0
        assert "scenario" in result.output.lower()

    def test_los_sensor_produces_png(self, scenario_los_yaml, tmp_path):
        """A valid scenario with a LOS sensor must produce per-sensor and multi-sensor PNGs."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        # Per-sensor PNG must exist (D-120: exact check, not >= 1)
        assert (tmp_path / "Echodyne_EchoGuard_coverage.png").exists()
        # Multi-sensor maps must also be produced
        assert (tmp_path / "composite.png").exists()
        assert (tmp_path / "gaps.png").exists()
        assert (tmp_path / "redundancy.png").exists()

    def test_los_sensor_output_filename(self, scenario_los_yaml, tmp_path):
        """Output PNG filename must be derived from the sensor name."""
        runner = CliRunner()
        runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        expected = tmp_path / "Echodyne_EchoGuard_coverage.png"
        assert expected.exists()

    def test_coverage_percentage_reported(self, scenario_los_yaml, tmp_path):
        """CLI output must report a coverage percentage for the LOS sensor."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "%" in result.output

    def test_nonlos_sensor_skipped(self, scenario_nonlos_yaml, tmp_path):
        """Non-LOS sensors produce no per-sensor PNG but do produce multi-sensor maps."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_nonlos_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        # No per-sensor PNG for non-LOS
        assert not (tmp_path / "DroneShield_RfOne_Mk2_coverage.png").exists()
        # But multi-sensor maps are still produced
        assert (tmp_path / "composite.png").exists()
        assert (tmp_path / "gaps.png").exists()
        assert (tmp_path / "redundancy.png").exists()

    def test_unknown_sensor_exits_nonzero(self, scenario_unknown_sensor_yaml, tmp_path):
        """A sensor name not in the definitions must cause a non-zero exit."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_unknown_sensor_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code != 0

    def test_nonexistent_scenario_exits_nonzero(self, tmp_path):
        """A scenario file path that does not exist must cause a non-zero exit."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(tmp_path / "nonexistent.yaml"),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code != 0

    def test_nonexistent_output_dir_is_created(self, scenario_los_yaml, tmp_path):
        """An output directory that does not exist must be created automatically."""
        runner = CliRunner()
        out_dir = tmp_path / "new_subdir"
        assert not out_dir.exists()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out_dir.is_dir()

    def test_empty_placements_exits_zero(self, scenario_empty_placements_yaml, tmp_path):
        """A scenario with no placements must exit 0 with an informational message."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_empty_placements_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0

    def test_default_sensor_dir_used_when_not_specified(self, scenario_los_yaml, tmp_path):
        """When --sensors is omitted the bundled sensor database must be used."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        # Per-sensor PNG must exist; multi-sensor maps are also produced
        assert (tmp_path / "Echodyne_EchoGuard_coverage.png").exists()
        assert (tmp_path / "composite.png").exists()


class TestSimulateCommandS56:
    """Tests for the S5-6 multi-sensor analysis pipeline extensions."""

    def test_composite_map_produced(self, scenario_los_yaml, tmp_path):
        """simulate must produce a composite.png in the output directory."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "composite.png").exists()

    def test_gap_map_produced(self, scenario_los_yaml, tmp_path):
        """simulate must produce a gaps.png in the output directory."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "gaps.png").exists()

    def test_redundancy_map_produced(self, scenario_los_yaml, tmp_path):
        """simulate must produce a redundancy.png in the output directory."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "redundancy.png").exists()

    def test_layer_maps_subdir_produced(self, scenario_los_yaml, tmp_path):
        """simulate must produce per-layer PNGs in a layers/ subdirectory."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        layers_dir = tmp_path / "layers"
        assert layers_dir.is_dir()
        assert len(list(layers_dir.glob("*.png"))) >= 1

    def test_summary_stats_printed(self, scenario_los_yaml, tmp_path):
        """simulate must print coverage percentage in the summary."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Total coverage" in result.output
        assert "%" in result.output

    def test_output_dir_created_when_absent(self, scenario_los_yaml, tmp_path):
        """--output-dir that does not exist must be created automatically."""
        runner = CliRunner()
        new_dir = tmp_path / "auto_created"
        assert not new_dir.exists()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(new_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert new_dir.is_dir()


# ---------------------------------------------------------------------------
# S6-5: Threat corridor analysis integration tests
# ---------------------------------------------------------------------------

_BUNDLED_THREAT_DIR: Path = Path(__file__).parent.parent / "src" / "salus" / "data" / "threats"
# Name of one bundled threat profile (matches dji_mavic_low_slow.yaml)
_DJI_MAVIC_NAME: str = "DJI Mavic 3 — Low Slow"
# Centre of the flat DEM fixture (500000–500100, 6100000–6100100)
_DEM_CENTRE: tuple[float, float] = (500050.0, 6100050.0)


@pytest.fixture
def scenario_threat_yaml(flat_dem_path, tmp_path):
    """Scenario with one RF sensor + one bundled threat + protected_point."""
    data = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [
            {
                "sensor_name": "DroneShield RfOne Mk2",
                "position_x": 500050.0,
                "position_y": 6100050.0,
                "bearing_deg": 0.0,
            }
        ],
        "threat_profiles": [_DJI_MAVIC_NAME],
        "protected_point": list(_DEM_CENTRE),
    }
    path = tmp_path / "scenario_threat.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


@pytest.fixture
def scenario_threat_no_point_yaml(flat_dem_path, tmp_path):
    """Scenario with threat_profiles but no protected_point."""
    data = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [
            {
                "sensor_name": "DroneShield RfOne Mk2",
                "position_x": 500050.0,
                "position_y": 6100050.0,
                "bearing_deg": 0.0,
            }
        ],
        "threat_profiles": [_DJI_MAVIC_NAME],
    }
    path = tmp_path / "scenario_threat_nopoint.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


@pytest.fixture
def scenario_unknown_threat_yaml(flat_dem_path, tmp_path):
    """Scenario referencing a threat that does not exist in the database."""
    data = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [
            {
                "sensor_name": "DroneShield RfOne Mk2",
                "position_x": 500050.0,
                "position_y": 6100050.0,
                "bearing_deg": 0.0,
            }
        ],
        "threat_profiles": ["Nonexistent Threat XYZ"],
        "protected_point": list(_DEM_CENTRE),
    }
    path = tmp_path / "scenario_unknown_threat.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


class TestSimulateCommandS65:
    """Integration tests for S6-5 threat corridor analysis in salus simulate."""

    def test_corridor_overlay_png_created(self, scenario_threat_yaml, tmp_path):
        """simulate with threat_profiles must write a corridor overlay PNG."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_threat_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--threats",
                str(_BUNDLED_THREAT_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        overlays = list(tmp_path.glob("corridor_*_overlay.png"))
        assert len(overlays) >= 1, "Expected at least one corridor overlay PNG"

    def test_corridor_polar_png_created(self, scenario_threat_yaml, tmp_path):
        """simulate with threat_profiles must write a corridor polar PNG."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_threat_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--threats",
                str(_BUNDLED_THREAT_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        polars = list(tmp_path.glob("corridor_*_polar.png"))
        assert len(polars) >= 1, "Expected at least one corridor polar PNG"

    def test_corridor_output_printed_to_console(self, scenario_threat_yaml, tmp_path):
        """Corridor analysis results must appear in stdout."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_threat_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--threats",
                str(_BUNDLED_THREAT_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Threat" in result.output or "corridor" in result.output.lower()

    def test_no_protected_point_warns_and_skips(self, scenario_threat_no_point_yaml, tmp_path):
        """When threat_profiles set but protected_point absent, warn and skip."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_threat_no_point_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "protected_point" in result.output or "skipping" in result.output.lower()
        overlays = list(tmp_path.glob("corridor_*.png"))
        assert len(overlays) == 0, "No corridor PNGs expected when protected_point absent"

    def test_unknown_threat_warns(self, scenario_unknown_threat_yaml, tmp_path):
        """Referencing an unknown threat name must print a warning."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_unknown_threat_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--threats",
                str(_BUNDLED_THREAT_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Warning" in result.output or "not found" in result.output

    def test_no_threats_in_scenario_skips_analysis(self, scenario_los_yaml, tmp_path):
        """When threat_profiles is empty, no corridor output is produced."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        overlays = list(tmp_path.glob("corridor_*.png"))
        assert len(overlays) == 0, "No corridor PNGs expected when threat_profiles empty"

    def test_threats_flag_accepts_custom_dir(self, scenario_threat_yaml, tmp_path):
        """--threats flag must accept a valid directory path."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_threat_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--threats",
                str(_BUNDLED_THREAT_DIR),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
