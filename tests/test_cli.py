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
        """A valid scenario with a LOS sensor must produce a coverage PNG."""
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
        pngs = list(tmp_path.glob("*.png"))
        assert len(pngs) == 1

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
        """Non-LOS sensors must be skipped; no PNG produced and exit 0."""
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
        pngs = list(tmp_path.glob("*.png"))
        assert len(pngs) == 0

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

    def test_nonexistent_output_dir_exits_nonzero(self, scenario_los_yaml, tmp_path):
        """An output directory that does not exist must cause a non-zero exit."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "simulate",
                str(scenario_los_yaml),
                "--sensors",
                str(_BUNDLED_SENSOR_DIR),
                "--output-dir",
                str(tmp_path / "does_not_exist"),
            ],
        )
        assert result.exit_code != 0

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
        pngs = list(tmp_path.glob("*.png"))
        assert len(pngs) == 1
