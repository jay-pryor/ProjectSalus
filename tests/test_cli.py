"""Tests for the Salus CLI."""

from __future__ import annotations

from click.testing import CliRunner

from salus.cli import main


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
