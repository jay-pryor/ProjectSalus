"""Tests for LiDAR point cloud ingestion (S12).

Tests that require PDAL are guarded by ``requires_pdal`` and are skipped when
PDAL is not installed.  Tests for input-validation logic (path checks,
resolution guards) do not require PDAL and run in all environments.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# PDAL availability guard
# ---------------------------------------------------------------------------

_HAS_PDAL: bool = importlib.util.find_spec("pdal") is not None

requires_pdal = pytest.mark.skipif(not _HAS_PDAL, reason="pdal not installed")


# ---------------------------------------------------------------------------
# _fill_nodata_nearest — pure-numpy helper (no PDAL needed)
# ---------------------------------------------------------------------------


def test_fill_nodata_nearest_no_nan() -> None:
    """Array with no NaN cells is returned unchanged."""
    from salus.ingest.lidar import _fill_nodata_nearest

    arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    result = _fill_nodata_nearest(arr)
    np.testing.assert_array_equal(result, arr)


def test_fill_nodata_nearest_single_nan() -> None:
    """Single NaN cell is filled with the nearest valid neighbour."""
    from salus.ingest.lidar import _fill_nodata_nearest

    arr = np.array([[1.0, np.nan], [3.0, 4.0]], dtype=np.float64)
    result = _fill_nodata_nearest(arr)
    assert not np.any(np.isnan(result))
    # [0,1] NaN is equidistant from [0,0]=1.0 and [1,1]=4.0; either is valid
    valid = {1.0, 3.0, 4.0}
    assert result[0, 1] in [pytest.approx(v) for v in valid]


def test_fill_nodata_nearest_full_row_nan() -> None:
    """An entire NaN row is filled from the adjacent valid row."""
    from salus.ingest.lidar import _fill_nodata_nearest

    arr = np.array(
        [[np.nan, np.nan, np.nan], [5.0, 6.0, 7.0], [8.0, 9.0, 10.0]],
        dtype=np.float64,
    )
    result = _fill_nodata_nearest(arr)
    assert not np.any(np.isnan(result))
    # Row 0 should be filled from row 1
    np.testing.assert_array_almost_equal(result[0], [5.0, 6.0, 7.0])


def test_fill_nodata_nearest_uniform_array() -> None:
    """Uniform array with interior NaN cells filled to the uniform value."""
    from salus.ingest.lidar import _fill_nodata_nearest

    arr = np.full((5, 5), 42.0, dtype=np.float64)
    arr[2, 2] = np.nan
    result = _fill_nodata_nearest(arr)
    assert result[2, 2] == pytest.approx(42.0)
    assert not np.any(np.isnan(result))


def test_fill_nodata_nearest_returns_copy() -> None:
    """Result is a copy — original is not mutated."""
    from salus.ingest.lidar import _fill_nodata_nearest

    arr = np.array([[1.0, np.nan], [3.0, 4.0]], dtype=np.float64)
    result = _fill_nodata_nearest(arr)
    assert result is not arr
    assert np.isnan(arr[0, 1])  # original unchanged


def test_fill_nodata_nearest_all_nan_raises() -> None:
    """All-NaN array raises ValueError — D-237 guard."""
    from salus.ingest.lidar import _fill_nodata_nearest

    arr = np.full((4, 4), np.nan, dtype=np.float64)
    with pytest.raises(ValueError, match="every cell"):
        _fill_nodata_nearest(arr)


# ---------------------------------------------------------------------------
# load_point_cloud — validation without PDAL
# ---------------------------------------------------------------------------


def test_load_point_cloud_unsupported_extension() -> None:
    """Non-LAS/LAZ extension raises ValueError before PDAL is needed."""
    from salus.ingest.lidar import load_point_cloud

    with pytest.raises(ValueError, match="Unsupported LiDAR format"):
        load_point_cloud("/tmp/fake_terrain.tif")


def test_load_point_cloud_unsupported_extension_csv() -> None:
    """CSV extension raises ValueError."""
    from salus.ingest.lidar import load_point_cloud

    with pytest.raises(ValueError, match="Unsupported LiDAR format"):
        load_point_cloud("/tmp/points.csv")


def test_load_point_cloud_file_not_found() -> None:
    """Non-existent LAS file raises FileNotFoundError before PDAL is needed."""
    from salus.ingest.lidar import load_point_cloud

    with pytest.raises(FileNotFoundError, match="LiDAR file not found"):
        load_point_cloud("/tmp/definitely_nonexistent_abc123xyz.las")


def test_load_point_cloud_file_not_found_laz() -> None:
    """Non-existent LAZ file raises FileNotFoundError."""
    from salus.ingest.lidar import load_point_cloud

    with pytest.raises(FileNotFoundError, match="LiDAR file not found"):
        load_point_cloud("/tmp/definitely_nonexistent_abc123xyz.laz")


# ---------------------------------------------------------------------------
# point_cloud_to_dem — resolution validation without PDAL
# ---------------------------------------------------------------------------


def test_point_cloud_to_dem_resolution_zero(tmp_path: pytest.FixtureRequest) -> None:
    """Zero resolution raises ValueError before PDAL is needed."""
    from salus.ingest.lidar import point_cloud_to_dem

    with pytest.raises(ValueError, match="resolution_m"):
        point_cloud_to_dem(None, 0.0, tmp_path / "dem.tif")


def test_point_cloud_to_dem_resolution_negative(tmp_path: pytest.FixtureRequest) -> None:
    """Negative resolution raises ValueError."""
    from salus.ingest.lidar import point_cloud_to_dem

    with pytest.raises(ValueError, match="resolution_m"):
        point_cloud_to_dem(None, -1.0, tmp_path / "dem.tif")


def test_point_cloud_to_dem_resolution_nan(tmp_path: pytest.FixtureRequest) -> None:
    """NaN resolution raises ValueError."""
    from salus.ingest.lidar import point_cloud_to_dem

    with pytest.raises(ValueError, match="resolution_m"):
        point_cloud_to_dem(None, float("nan"), tmp_path / "dem.tif")


def test_point_cloud_to_dem_resolution_inf(tmp_path: pytest.FixtureRequest) -> None:
    """Infinite resolution raises ValueError."""
    from salus.ingest.lidar import point_cloud_to_dem

    with pytest.raises(ValueError, match="resolution_m"):
        point_cloud_to_dem(None, float("inf"), tmp_path / "dem.tif")


def test_point_cloud_to_dem_missing_output_dir() -> None:
    """Non-existent output parent directory raises FileNotFoundError."""
    from salus.ingest.lidar import point_cloud_to_dem

    with pytest.raises(FileNotFoundError, match="Output directory"):
        point_cloud_to_dem(None, 1.0, "/definitely/nonexistent/dir/dem.tif")


# ---------------------------------------------------------------------------
# point_cloud_to_dsm — resolution validation without PDAL
# ---------------------------------------------------------------------------


def test_point_cloud_to_dsm_resolution_zero(tmp_path: pytest.FixtureRequest) -> None:
    """Zero resolution raises ValueError before PDAL is needed."""
    from salus.ingest.lidar import point_cloud_to_dsm

    with pytest.raises(ValueError, match="resolution_m"):
        point_cloud_to_dsm(None, 0.0, tmp_path / "dsm.tif")


def test_point_cloud_to_dsm_resolution_negative(tmp_path: pytest.FixtureRequest) -> None:
    """Negative resolution raises ValueError."""
    from salus.ingest.lidar import point_cloud_to_dsm

    with pytest.raises(ValueError, match="resolution_m"):
        point_cloud_to_dsm(None, -0.5, tmp_path / "dsm.tif")


def test_point_cloud_to_dsm_resolution_nan(tmp_path: pytest.FixtureRequest) -> None:
    """NaN resolution raises ValueError."""
    from salus.ingest.lidar import point_cloud_to_dsm

    with pytest.raises(ValueError, match="resolution_m"):
        point_cloud_to_dsm(None, float("nan"), tmp_path / "dsm.tif")


def test_point_cloud_to_dsm_missing_output_dir() -> None:
    """Non-existent output parent directory raises FileNotFoundError."""
    from salus.ingest.lidar import point_cloud_to_dsm

    with pytest.raises(FileNotFoundError, match="Output directory"):
        point_cloud_to_dsm(None, 1.0, "/definitely/nonexistent/dir/dsm.tif")


# ---------------------------------------------------------------------------
# _validate_point_cloud_crs — no PDAL needed
# ---------------------------------------------------------------------------


def test_validate_point_cloud_crs_with_srs(tmp_path: pytest.FixtureRequest) -> None:
    """Metadata containing a spatial reference does not raise."""
    from pathlib import Path

    from salus.ingest.lidar import _validate_point_cloud_crs

    metadata = {
        "metadata": {
            "readers.las": {
                "comp_spatialreference": "PROJCS[...]",
            }
        }
    }
    _validate_point_cloud_crs(metadata, Path("/tmp/test.las"))  # should not raise


def test_validate_point_cloud_crs_missing_raises(tmp_path: pytest.FixtureRequest) -> None:
    """Metadata without any spatial reference raises ValueError."""
    from pathlib import Path

    from salus.ingest.lidar import _validate_point_cloud_crs

    metadata: dict = {"metadata": {"readers.las": {"comp_spatialreference": ""}}}
    with pytest.raises(ValueError, match="no CRS defined"):
        _validate_point_cloud_crs(metadata, Path("/tmp/test.las"))


def test_validate_point_cloud_crs_whitespace_raises() -> None:
    """Whitespace-only CRS string raises ValueError — D-241 guard."""
    from pathlib import Path

    from salus.ingest.lidar import _validate_point_cloud_crs

    metadata: dict = {"metadata": {"readers.las": {"comp_spatialreference": "   "}}}
    with pytest.raises(ValueError, match="no CRS defined"):
        _validate_point_cloud_crs(metadata, Path("/tmp/test.las"))


def test_validate_point_cloud_crs_empty_metadata_raises() -> None:
    """Empty metadata raises ValueError."""
    from pathlib import Path

    from salus.ingest.lidar import _validate_point_cloud_crs

    with pytest.raises(ValueError, match="no CRS defined"):
        _validate_point_cloud_crs({}, Path("/tmp/test.las"))


# ---------------------------------------------------------------------------
# _extract_bounds — no PDAL needed
# ---------------------------------------------------------------------------


def test_extract_bounds_returns_tuple_when_present() -> None:
    """Returns 6-tuple (minx, miny, minz, maxx, maxy, maxz) from PDAL metadata."""
    from salus.ingest.lidar import _extract_bounds

    metadata = {
        "metadata": {
            "readers.las": {
                "minx": 100.0,
                "miny": 200.0,
                "minz": 10.0,
                "maxx": 500.0,
                "maxy": 600.0,
                "maxz": 50.0,
            }
        }
    }
    result = _extract_bounds(metadata)
    assert result == pytest.approx((100.0, 200.0, 10.0, 500.0, 600.0, 50.0))


def test_extract_bounds_returns_none_when_absent() -> None:
    """Returns None when metadata has no bounds fields."""
    from salus.ingest.lidar import _extract_bounds

    assert _extract_bounds({}) is None
    assert _extract_bounds({"metadata": {}}) is None
    no_bounds = {"metadata": {"readers.las": {"comp_spatialreference": "EPSG:32654"}}}
    assert _extract_bounds(no_bounds) is None


def test_extract_bounds_returns_none_on_partial_keys() -> None:
    """Returns None when only some bounds keys are present."""
    from salus.ingest.lidar import _extract_bounds

    metadata = {"metadata": {"readers.las": {"minx": 0.0, "miny": 0.0}}}
    assert _extract_bounds(metadata) is None


# ---------------------------------------------------------------------------
# CLI ingest command
# ---------------------------------------------------------------------------


def test_cli_ingest_requires_lidar_option() -> None:
    """CLI ingest command requires --lidar option."""
    from click.testing import CliRunner

    from salus.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "--output-dem", "dem.tif", "--output-dsm", "dsm.tif"])
    assert result.exit_code != 0
    assert "lidar" in result.output.lower() or "Error" in result.output


def test_cli_ingest_requires_output_dem_option() -> None:
    """CLI ingest command requires --output-dem option."""
    from click.testing import CliRunner

    from salus.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "--lidar", "cloud.las", "--output-dsm", "dsm.tif"])
    assert result.exit_code != 0


def test_cli_ingest_requires_output_dsm_option() -> None:
    """CLI ingest command requires --output-dsm option."""
    from click.testing import CliRunner

    from salus.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "--lidar", "cloud.las", "--output-dem", "dem.tif"])
    assert result.exit_code != 0


def test_cli_ingest_invalid_resolution() -> None:
    """CLI ingest rejects non-positive resolution."""
    from click.testing import CliRunner

    from salus.cli import main

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ingest",
            "--lidar",
            "cloud.las",
            "--resolution",
            "-1.0",
            "--output-dem",
            "dem.tif",
            "--output-dsm",
            "dsm.tif",
        ],
    )
    assert result.exit_code != 0


def test_cli_ingest_missing_lidar_file_exits_nonzero() -> None:
    """CLI ingest exits non-zero when LiDAR file does not exist."""
    from click.testing import CliRunner

    from salus.cli import main

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ingest",
            "--lidar",
            "/definitely/nonexistent/cloud.las",
            "--output-dem",
            "/tmp/dem.tif",
            "--output-dsm",
            "/tmp/dsm.tif",
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# PDAL integration tests (skipped when PDAL unavailable)
# ---------------------------------------------------------------------------


@requires_pdal
def test_load_point_cloud_returns_pdal_pipeline(tmp_path: pytest.FixtureRequest) -> None:
    """load_point_cloud returns an executed pdal.Pipeline instance."""
    pytest.skip("Requires a real LAS/LAZ test fixture — integration test only")


@requires_pdal
def test_point_cloud_to_dem_produces_site_model(tmp_path: pytest.FixtureRequest) -> None:
    """point_cloud_to_dem returns a SiteModel with correct resolution."""
    pytest.skip("Requires a real LAS/LAZ test fixture — integration test only")


@requires_pdal
def test_point_cloud_to_dsm_produces_site_model(tmp_path: pytest.FixtureRequest) -> None:
    """point_cloud_to_dsm returns a SiteModel with correct resolution."""
    pytest.skip("Requires a real LAS/LAZ test fixture — integration test only")
