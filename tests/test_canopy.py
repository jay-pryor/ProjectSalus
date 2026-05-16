"""Tests for S12.5 — Vegetation and Canopy Layer.

Tests are organised by component:
- derive_canopy_height_model (terrain.py)
- load_dem with canopy_path (terrain.py)
- SiteModel.canopy_height_m (models/site.py)
- SensorDefinition.vegetation_penetration (models/sensor.py)
- compute_viewshed_through_canopy (engine/viewshed.py)
- VEGETATION_COVERAGE_THRESHOLD and threshold parameters (engine/coverage.py)
- Canopy overlay in render_composite_coverage_map / render_gap_map (report/maps.py)
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from salus.models.sensor import SensorDefinition, SensorType
from salus.models.site import SiteModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_geotiff(path: Path, data: np.ndarray, resolution: float = 1.0) -> None:
    """Write a single-band float64 GeoTIFF for testing."""
    rows, cols = data.shape
    transform = from_origin(0.0, rows * resolution, resolution, resolution)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype=rasterio.float64,
        crs="EPSG:32654",
        transform=transform,
    ) as dst:
        dst.write(data, 1)


def _flat_site(rows: int = 10, cols: int = 10, elev: float = 0.0) -> SiteModel:
    dem = np.full((rows, cols), elev, dtype=np.float64)
    return SiteModel(dem=dem, resolution=1.0, origin_x=0.0, origin_y=float(rows))


# ---------------------------------------------------------------------------
# derive_canopy_height_model
# ---------------------------------------------------------------------------


def test_derive_chm_zero_on_flat_open_terrain(tmp_path: Path) -> None:
    """CHM is all-zero when DSM == DEM (open flat terrain)."""
    from salus.ingest.terrain import derive_canopy_height_model

    dem = np.full((5, 5), 10.0, dtype=np.float64)
    dsm = np.full((5, 5), 10.0, dtype=np.float64)
    dem_p = tmp_path / "dem.tif"
    dsm_p = tmp_path / "dsm.tif"
    out_p = tmp_path / "chm.tif"
    _write_geotiff(dem_p, dem)
    _write_geotiff(dsm_p, dsm)

    chm = derive_canopy_height_model(dem_p, dsm_p, out_p)

    assert chm.shape == (5, 5)
    np.testing.assert_array_almost_equal(chm, 0.0)
    assert out_p.exists()


def test_derive_chm_positive_where_dsm_greater(tmp_path: Path) -> None:
    """CHM is positive where DSM > DEM (vegetation / structure present)."""
    from salus.ingest.terrain import derive_canopy_height_model

    dem = np.full((5, 5), 5.0, dtype=np.float64)
    dsm = np.full((5, 5), 5.0, dtype=np.float64)
    dsm[2, 2] = 15.0  # 10 m tree at centre
    dem_p = tmp_path / "dem.tif"
    dsm_p = tmp_path / "dsm.tif"
    out_p = tmp_path / "chm.tif"
    _write_geotiff(dem_p, dem)
    _write_geotiff(dsm_p, dsm)

    chm = derive_canopy_height_model(dem_p, dsm_p, out_p)

    assert chm[2, 2] == pytest.approx(10.0)
    # All other cells should be zero
    expected = np.zeros((5, 5))
    expected[2, 2] = 10.0
    np.testing.assert_array_almost_equal(chm, expected)


def test_derive_chm_clamps_negative_and_warns(tmp_path: Path) -> None:
    """Negative CHM cells (DEM/DSM misregistration) are clamped to 0 with warning."""
    from salus.ingest.terrain import derive_canopy_height_model

    dem = np.full((5, 5), 10.0, dtype=np.float64)
    dsm = np.full((5, 5), 10.0, dtype=np.float64)
    dsm[1, 1] = 8.0  # DSM < DEM — misregistration offset
    dem_p = tmp_path / "dem.tif"
    dsm_p = tmp_path / "dsm.tif"
    out_p = tmp_path / "chm.tif"
    _write_geotiff(dem_p, dem)
    _write_geotiff(dsm_p, dsm)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        chm = derive_canopy_height_model(dem_p, dsm_p, out_p)

    assert chm[1, 1] == pytest.approx(0.0)
    assert not np.any(chm < 0)
    assert any("clamping" in str(warning.message).lower() for warning in w)


def test_derive_chm_dem_not_found_raises(tmp_path: Path) -> None:
    """FileNotFoundError when DEM does not exist."""
    from salus.ingest.terrain import derive_canopy_height_model

    dsm_p = tmp_path / "dsm.tif"
    _write_geotiff(dsm_p, np.zeros((5, 5)))

    with pytest.raises(FileNotFoundError, match="DEM not found"):
        derive_canopy_height_model(tmp_path / "no_dem.tif", dsm_p, tmp_path / "chm.tif")


def test_derive_chm_dsm_not_found_raises(tmp_path: Path) -> None:
    """FileNotFoundError when DSM does not exist."""
    from salus.ingest.terrain import derive_canopy_height_model

    dem_p = tmp_path / "dem.tif"
    _write_geotiff(dem_p, np.zeros((5, 5)))

    with pytest.raises(FileNotFoundError, match="DSM not found"):
        derive_canopy_height_model(dem_p, tmp_path / "no_dsm.tif", tmp_path / "chm.tif")


def test_derive_chm_output_dir_missing_raises(tmp_path: Path) -> None:
    """FileNotFoundError when output parent directory does not exist."""
    from salus.ingest.terrain import derive_canopy_height_model

    dem_p = tmp_path / "dem.tif"
    dsm_p = tmp_path / "dsm.tif"
    _write_geotiff(dem_p, np.zeros((5, 5)))
    _write_geotiff(dsm_p, np.zeros((5, 5)))

    with pytest.raises(FileNotFoundError, match="Output directory"):
        derive_canopy_height_model(dem_p, dsm_p, tmp_path / "nonexistent" / "chm.tif")


def test_derive_chm_shape_mismatch_raises(tmp_path: Path) -> None:
    """ValueError when DEM and DSM shapes differ."""
    from salus.ingest.terrain import derive_canopy_height_model

    dem_p = tmp_path / "dem.tif"
    dsm_p = tmp_path / "dsm.tif"
    _write_geotiff(dem_p, np.zeros((5, 5)))
    _write_geotiff(dsm_p, np.zeros((6, 5)))

    with pytest.raises(ValueError, match="shape"):
        derive_canopy_height_model(dem_p, dsm_p, tmp_path / "chm.tif")


def test_derive_chm_returns_non_negative_finite_values(tmp_path: Path) -> None:
    """All finite values in the returned CHM are >= 0."""
    from salus.ingest.terrain import derive_canopy_height_model

    dem = np.full((5, 5), 10.0, dtype=np.float64)
    dsm = np.full((5, 5), 12.0, dtype=np.float64)
    dem_p = tmp_path / "dem.tif"
    dsm_p = tmp_path / "dsm.tif"
    _write_geotiff(dem_p, dem)
    _write_geotiff(dsm_p, dsm)

    chm = derive_canopy_height_model(dem_p, dsm_p, tmp_path / "chm.tif")
    finite_vals = chm[np.isfinite(chm)]
    assert np.all(finite_vals >= 0.0)


# ---------------------------------------------------------------------------
# SiteModel.canopy_height_m
# ---------------------------------------------------------------------------


def test_site_model_canopy_height_m_none_by_default() -> None:
    """canopy_height_m defaults to None."""
    site = _flat_site()
    assert site.canopy_height_m is None


def test_site_model_canopy_height_m_accepts_matching_array() -> None:
    """canopy_height_m accepts a 2D array matching DEM shape."""
    dem = np.zeros((4, 4), dtype=np.float64)
    canopy = np.full((4, 4), 5.0, dtype=np.float64)
    site = SiteModel(dem=dem, canopy_height_m=canopy, resolution=1.0, origin_x=0.0, origin_y=4.0)
    assert site.canopy_height_m is not None
    np.testing.assert_array_equal(site.canopy_height_m, canopy)


def test_site_model_canopy_height_m_shape_mismatch_raises() -> None:
    """ValueError when canopy_height_m shape differs from DEM shape."""
    dem = np.zeros((4, 4))
    canopy = np.zeros((5, 4))
    with pytest.raises(ValueError, match="canopy_height_m shape"):
        SiteModel(dem=dem, canopy_height_m=canopy, resolution=1.0, origin_x=0.0, origin_y=4.0)


def test_site_model_canopy_height_m_must_be_2d() -> None:
    """ValueError when canopy_height_m is not 2D."""
    dem = np.zeros((4, 4))
    with pytest.raises(ValueError, match="2D"):
        SiteModel(
            dem=dem,
            canopy_height_m=np.zeros(16),
            resolution=1.0,
            origin_x=0.0,
            origin_y=4.0,
        )


def test_site_model_canopy_negative_finite_raises() -> None:
    """SiteModel rejects canopy_height_m with negative finite values (D-247 guard)."""
    dem = np.zeros((4, 4))
    canopy = np.zeros((4, 4), dtype=np.float64)
    canopy[2, 2] = -1.0  # negative finite value
    with pytest.raises(ValueError, match="negative finite"):
        SiteModel(dem=dem, canopy_height_m=canopy, resolution=1.0, origin_x=0.0, origin_y=4.0)


def test_site_model_canopy_nan_values_accepted() -> None:
    """SiteModel accepts canopy_height_m with NaN cells (nodata)."""
    dem = np.zeros((4, 4))
    canopy = np.zeros((4, 4), dtype=np.float64)
    canopy[1, 1] = np.nan
    site = SiteModel(dem=dem, canopy_height_m=canopy, resolution=1.0, origin_x=0.0, origin_y=4.0)
    assert np.isnan(site.canopy_height_m[1, 1])  # type: ignore[index]


# ---------------------------------------------------------------------------
# load_dem with canopy_path
# ---------------------------------------------------------------------------


def test_load_dem_attaches_canopy_to_site(tmp_path: Path) -> None:
    """load_dem with canopy_path populates site.canopy_height_m."""
    from salus.ingest.terrain import load_dem

    dem = np.full((5, 5), 10.0, dtype=np.float64)
    chm = np.full((5, 5), 3.0, dtype=np.float64)
    dem_p = tmp_path / "dem.tif"
    chm_p = tmp_path / "chm.tif"
    _write_geotiff(dem_p, dem)
    _write_geotiff(chm_p, chm)

    site = load_dem(dem_p, canopy_path=chm_p)

    assert site.canopy_height_m is not None
    assert site.canopy_height_m.shape == (5, 5)
    np.testing.assert_array_almost_equal(site.canopy_height_m, 3.0)


def test_load_dem_without_canopy_path_gives_none(tmp_path: Path) -> None:
    """load_dem without canopy_path leaves site.canopy_height_m as None."""
    from salus.ingest.terrain import load_dem

    dem_p = tmp_path / "dem.tif"
    _write_geotiff(dem_p, np.zeros((5, 5)))
    site = load_dem(dem_p)
    assert site.canopy_height_m is None


def test_load_dem_canopy_not_found_raises(tmp_path: Path) -> None:
    """FileNotFoundError when canopy_path does not exist."""
    from salus.ingest.terrain import load_dem

    dem_p = tmp_path / "dem.tif"
    _write_geotiff(dem_p, np.zeros((5, 5)))

    with pytest.raises(FileNotFoundError, match="Canopy Height Model not found"):
        load_dem(dem_p, canopy_path=tmp_path / "nonexistent_chm.tif")


# ---------------------------------------------------------------------------
# SensorDefinition.vegetation_penetration
# ---------------------------------------------------------------------------


def test_sensor_vegetation_penetration_default_zero() -> None:
    """vegetation_penetration defaults to 0.0."""
    sensor = SensorDefinition(
        name="Test RF",
        type=SensorType.RF,
        max_range_m=500.0,
        azimuth_coverage_deg=90.0,
        elevation_coverage_deg=45.0,
    )
    assert sensor.vegetation_penetration == pytest.approx(0.0)


def test_sensor_vegetation_penetration_accepts_valid_range() -> None:
    """vegetation_penetration accepts values in [0, 1]."""
    for val in [0.0, 0.2, 0.6, 0.9, 1.0]:
        sensor = SensorDefinition(
            name="S",
            type=SensorType.RF,
            max_range_m=100.0,
            azimuth_coverage_deg=360.0,
            elevation_coverage_deg=90.0,
            vegetation_penetration=val,
        )
        assert sensor.vegetation_penetration == pytest.approx(val)


def test_sensor_vegetation_penetration_rejects_negative() -> None:
    """vegetation_penetration rejects negative values."""
    with pytest.raises(ValueError, match="vegetation_penetration"):
        SensorDefinition(
            name="S",
            type=SensorType.RF,
            max_range_m=100.0,
            azimuth_coverage_deg=360.0,
            elevation_coverage_deg=90.0,
            vegetation_penetration=-0.1,
        )


def test_sensor_vegetation_penetration_rejects_above_one() -> None:
    """vegetation_penetration rejects values > 1."""
    with pytest.raises(ValueError, match="vegetation_penetration"):
        SensorDefinition(
            name="S",
            type=SensorType.RF,
            max_range_m=100.0,
            azimuth_coverage_deg=360.0,
            elevation_coverage_deg=90.0,
            vegetation_penetration=1.1,
        )


# ---------------------------------------------------------------------------
# compute_viewshed_through_canopy
# ---------------------------------------------------------------------------


def _site_with_canopy(canopy: np.ndarray) -> SiteModel:
    rows, cols = canopy.shape
    dem = np.zeros((rows, cols), dtype=np.float64)
    return SiteModel(
        dem=dem,
        canopy_height_m=canopy,
        resolution=1.0,
        origin_x=0.0,
        origin_y=float(rows),
    )


def test_viewshed_through_canopy_open_terrain_returns_float32() -> None:
    """Open terrain with no CHM returns float32 array identical to binary viewshed."""
    from salus.engine.viewshed import compute_viewshed, compute_viewshed_through_canopy

    site = _flat_site(10, 10, 0.0)
    binary = compute_viewshed(site, 5.0, 5.0, 2.0)
    result = compute_viewshed_through_canopy(site, 5.0, 5.0, 2.0)

    assert result.dtype == np.float32
    np.testing.assert_array_equal(result, binary.astype(np.float32))


def test_viewshed_through_canopy_zero_penetration_equals_binary() -> None:
    """vegetation_penetration=0.0 returns binary viewshed cast to float32."""
    from salus.engine.viewshed import compute_viewshed, compute_viewshed_through_canopy

    canopy = np.zeros((10, 10), dtype=np.float64)
    canopy[5, 5] = 8.0
    site = _site_with_canopy(canopy)

    binary = compute_viewshed(site, 0.0, 10.0, 2.0)
    result = compute_viewshed_through_canopy(site, 0.0, 10.0, 2.0, vegetation_penetration=0.0)

    assert result.dtype == np.float32
    np.testing.assert_array_equal(result, binary.astype(np.float32))


def test_viewshed_through_canopy_full_penetration_equals_binary() -> None:
    """vegetation_penetration=1.0 (transparent canopy) returns all-1.0 for visible cells."""
    from salus.engine.viewshed import compute_viewshed, compute_viewshed_through_canopy

    canopy = np.zeros((10, 10), dtype=np.float64)
    canopy[3:7, 3:7] = 5.0  # 4×4 canopy patch
    site = _site_with_canopy(canopy)

    binary = compute_viewshed(site, 0.0, 10.0, 2.0)
    result = compute_viewshed_through_canopy(site, 0.0, 10.0, 2.0, vegetation_penetration=1.0)

    assert result.dtype == np.float32
    # All visible cells should have transmission 1.0 with perfect penetration
    visible_mask = binary.astype(bool)
    assert np.all(result[visible_mask] == pytest.approx(1.0))


def test_viewshed_through_canopy_partial_penetration_between_zero_and_one() -> None:
    """Partial penetration produces intermediate transmission values."""
    from salus.engine.viewshed import compute_viewshed_through_canopy

    canopy = np.zeros((20, 20), dtype=np.float64)
    canopy[10, 10] = 10.0  # single canopy cell
    site = _site_with_canopy(canopy)

    result = compute_viewshed_through_canopy(site, 0.0, 20.0, 2.0, vegetation_penetration=0.5)

    # Canopy cell should have transmission between 0 and 1 (not 0, not 1)
    t = float(result[10, 10])
    assert 0.0 < t < 1.0, f"Expected 0 < transmission < 1, got {t}"


def test_viewshed_through_canopy_observer_above_canopy_self_cell_one() -> None:
    """Observer at or above the canopy top sees its own cell at transmission 1.0."""
    from salus.engine.viewshed import compute_viewshed_through_canopy

    canopy = np.full((10, 10), 5.0, dtype=np.float64)
    site = _site_with_canopy(canopy)

    # Observer height (8m) is above canopy top (5m) at the observer cell.
    result = compute_viewshed_through_canopy(site, 5.0, 5.0, 8.0, vegetation_penetration=0.1)

    obs_row, obs_col = 5, 5  # origin_y=10, y=5 → row=5; origin_x=0, x=5 → col=5
    assert result[obs_row, obs_col] == pytest.approx(1.0)


def test_viewshed_through_canopy_observer_under_canopy_attenuates_self_cell() -> None:
    """Observer buried under canopy gets a self-cell value < 1.0 (overhead canopy, D-505)."""
    from salus.engine.viewshed import _CANOPY_REFERENCE_HEIGHT_M, compute_viewshed_through_canopy

    canopy = np.full((10, 10), 15.0, dtype=np.float64)
    site = _site_with_canopy(canopy)

    penetration = 0.1
    observer_height = 2.0
    result = compute_viewshed_through_canopy(
        site, 5.0, 5.0, observer_height, vegetation_penetration=penetration
    )

    obs_row, obs_col = 5, 5
    canopy_above = 15.0 - observer_height
    expected = penetration ** (canopy_above / _CANOPY_REFERENCE_HEIGHT_M)
    assert result[obs_row, obs_col] == pytest.approx(expected, abs=1e-4)
    assert result[obs_row, obs_col] < 1.0


def test_viewshed_through_canopy_invalid_penetration_raises() -> None:
    """ValueError when vegetation_penetration is outside [0, 1]."""
    from salus.engine.viewshed import compute_viewshed_through_canopy

    site = _flat_site(10, 10)
    with pytest.raises(ValueError, match="vegetation_penetration"):
        compute_viewshed_through_canopy(site, 5.0, 5.0, 2.0, vegetation_penetration=1.5)

    with pytest.raises(ValueError, match="vegetation_penetration"):
        compute_viewshed_through_canopy(site, 5.0, 5.0, 2.0, vegetation_penetration=-0.1)


def test_viewshed_through_canopy_result_shape_matches_dem() -> None:
    """Output shape matches site.dem shape."""
    from salus.engine.viewshed import compute_viewshed_through_canopy

    site = _flat_site(8, 12)
    result = compute_viewshed_through_canopy(site, 0.0, 8.0, 1.0, vegetation_penetration=0.5)
    assert result.shape == (8, 12)


def test_viewshed_through_canopy_exponential_decay_along_ray() -> None:
    """Transmission decreases cumulatively along a ray through consecutive canopy cells.

    Places a strip of same-height canopy cells in a row. The cell further from the
    observer (more canopy cells on its ray path) must have lower transmission than
    the cell closer to the observer (fewer canopy cells on its path).
    """
    from salus.engine.viewshed import _CANOPY_REFERENCE_HEIGHT_M, compute_viewshed_through_canopy

    # 1×30 row: observer at col 0, canopy strip from col 10 to 25
    rows, cols = 30, 30
    canopy = np.zeros((rows, cols), dtype=np.float64)
    canopy_height = 5.0
    # Horizontal strip of canopy cells at row 15, cols 10–25
    canopy[15, 10:26] = canopy_height

    dem = np.zeros((rows, cols), dtype=np.float64)
    site = SiteModel(
        dem=dem,
        canopy_height_m=canopy,
        resolution=1.0,
        origin_x=0.0,
        origin_y=float(rows),
    )
    penetration = 0.5
    # Observer at (0.5, 15.5) — leftmost column, same row as canopy strip
    result = compute_viewshed_through_canopy(
        site, 0.5, 14.5, 2.0, vegetation_penetration=penetration
    )

    # Cell at col 10 has 1 canopy cell on its path; col 20 has ~10 canopy cells.
    # Transmission at col 20 must be strictly less than at col 10.
    t_near = float(result[15, 10])
    t_far = float(result[15, 20])

    # Both must be visible (non-zero) and far must be less than near
    assert t_near > 0.0, f"Near canopy cell should be visible, got {t_near}"
    assert t_far > 0.0, f"Far canopy cell should be visible, got {t_far}"
    assert t_far < t_near, (
        f"Transmission should decrease along ray through canopy: "
        f"t_near={t_near:.4f} t_far={t_far:.4f}"
    )

    # The near cell should match the single-step Bouguer-Lambert formula exactly
    expected_near = penetration ** (canopy_height / _CANOPY_REFERENCE_HEIGHT_M)
    assert t_near == pytest.approx(expected_near, abs=0.01), (
        f"Near cell transmission {t_near:.4f} should match penetration^(h/ref)={expected_near:.4f}"
    )


def test_viewshed_through_canopy_visible_cells_no_silent_perimeter_zeros() -> None:
    """Visible cells that no integer-rounded ray lands on retain transmission 1.0 (D-494).

    With a canopy-free site, every cell visible per the binary viewshed must have
    transmission == 1.0.  The buggy initialisation (zeros + max over rays) left
    perimeter cells missed by discrete rays at 0.0, indistinguishable from
    terrain-blocked.
    """
    from salus.engine.viewshed import compute_viewshed, compute_viewshed_through_canopy

    # Canopy is present (forces the attenuation code path) but every cell is
    # canopy-free, so no ray should reduce transmission.
    canopy = np.zeros((20, 20), dtype=np.float64)
    site = _site_with_canopy(canopy)

    binary = compute_viewshed(site, 0.0, 20.0, 2.0)
    result = compute_viewshed_through_canopy(site, 0.0, 20.0, 2.0, vegetation_penetration=0.1)

    visible = binary.astype(bool)
    # Every visible cell must be exactly 1.0 — no silent perimeter zeros.
    assert np.all(result[visible] == pytest.approx(1.0)), (
        f"Found visible cells with transmission < 1.0: min={float(result[visible].min()):.4f}"
    )


def test_viewshed_through_canopy_ray_does_not_contaminate_past_occluder() -> None:
    """Canopy attenuation does not bleed past a terrain occluder (D-495).

    Place a tall ridge between observer and a cell that is visible only over
    the top of the ridge (via DSM occlusion patterns).  The 2D ray path
    through the ridge column must not stamp canopy attenuation onto the
    far cell — instead the far cell either takes the unattenuated value from
    a clear ray, or stays at the binary default.
    """
    from salus.engine.viewshed import compute_viewshed_through_canopy

    rows, cols = 20, 20
    dem = np.zeros((rows, cols), dtype=np.float64)
    # Tall ridge at col 10 blocking direct east-west LOS at low observer height.
    dem[:, 10] = 50.0
    # Dense canopy on the ridge itself (canopy_height_m is measured ABOVE DEM, so
    # the canopy is *on top* of the ridge — never on the path of a ray that goes
    # *around* the ridge).
    canopy = np.zeros((rows, cols), dtype=np.float64)
    canopy[:, 10] = 20.0

    site = SiteModel(
        dem=dem,
        canopy_height_m=canopy,
        resolution=1.0,
        origin_x=0.0,
        origin_y=float(rows),
    )

    # Observer at row 10, col 0 with low height so the ridge blocks direct LOS.
    result = compute_viewshed_through_canopy(site, 0.5, 9.5, 2.0, vegetation_penetration=0.1)

    # Cells on the obs side of the ridge (col 0..9) should be visible.
    near_side = result[:, :10]
    assert np.any(near_side > 0.0)

    # Cells on the far side of the ridge along the east-west direction must
    # not be marked with attenuated transmission from a contaminated ray —
    # they should be either 0.0 (terrain-blocked, no ray reached them) or
    # 1.0 (visible via some path), but never an intermediate canopy-stained
    # value derived from a ray that walked through the ridge column.
    far_side = result[10, 11:]  # same row as observer, beyond the ridge
    intermediate = (far_side > 0.0) & (far_side < 1.0)
    assert not np.any(intermediate), (
        f"Found contaminated transmission values past occluder: {far_side[intermediate]}"
    )


def test_viewshed_through_canopy_ray_above_canopy_no_attenuation() -> None:
    """A LOS that skims above an intermediate canopy receives no attenuation (D-506).

    Observer well above the canopy looking at a distant ground target — the
    canopy cell sits *between* observer and target.  With a high observer the
    interpolated LOS at the canopy cell is well above the canopy top, so no
    attenuation accrues.  With a low observer the LOS dips into the canopy
    column at the same intermediate cell and accrues a penalty.
    """
    from salus.engine.viewshed import compute_viewshed_through_canopy

    rows, cols = 20, 20
    dem = np.zeros((rows, cols), dtype=np.float64)
    canopy = np.zeros((rows, cols), dtype=np.float64)
    # Intermediate canopy cell midway between observer (col 0) and target (col 15).
    canopy[10, 10] = 5.0

    site = SiteModel(
        dem=dem,
        canopy_height_m=canopy,
        resolution=1.0,
        origin_x=0.0,
        origin_y=float(rows),
    )

    # High observer (50m) — LOS to the ground target at col 15 stays well
    # above the 5m canopy top at col 10.
    result_high = compute_viewshed_through_canopy(site, 0.5, 9.5, 50.0, vegetation_penetration=0.1)

    # Low observer (1m) — LOS to the same target dips into the canopy column.
    result_low = compute_viewshed_through_canopy(site, 0.5, 9.5, 1.0, vegetation_penetration=0.1)

    # High observer: target beyond canopy must be unattenuated.
    assert result_high[10, 15] == pytest.approx(1.0), (
        f"High observer LOS should skim above canopy, got t={result_high[10, 15]:.4f}"
    )
    # Low observer: target beyond canopy must be attenuated.
    assert result_low[10, 15] < 1.0, (
        f"Low observer LOS should pass through canopy, got t={result_low[10, 15]:.4f}"
    )


# ---------------------------------------------------------------------------
# VEGETATION_COVERAGE_THRESHOLD and coverage_threshold parameter
# ---------------------------------------------------------------------------


def test_vegetation_coverage_threshold_constant_exists() -> None:
    """VEGETATION_COVERAGE_THRESHOLD is exported from coverage module."""
    from salus.engine.coverage import VEGETATION_COVERAGE_THRESHOLD

    assert isinstance(VEGETATION_COVERAGE_THRESHOLD, float)
    assert VEGETATION_COVERAGE_THRESHOLD == pytest.approx(0.5)


def test_coverage_threshold_applied_to_float_array(tmp_path: Path) -> None:
    """Cell with transmission >= threshold is covered; below threshold is not."""
    from salus.engine.coverage import VEGETATION_COVERAGE_THRESHOLD, compute_coverage_stats
    from salus.models.sensor import SensorType

    site = _flat_site(4, 4)
    # Simulate float layer arrays from canopy-attenuated viewsheds
    layer_high = np.full((4, 4), 0.6, dtype=np.float32)  # above default 0.5 threshold
    layer_low = np.full((4, 4), 0.3, dtype=np.float32)  # below default 0.5 threshold

    layer_coverages = {
        SensorType.RF: layer_high,
        SensorType.Radar: layer_low,
    }
    composite = (layer_high >= VEGETATION_COVERAGE_THRESHOLD).astype(bool)
    gaps = ~composite

    stats = compute_coverage_stats(site, layer_coverages, composite, gaps, [])

    assert stats.per_layer_coverage_pct[SensorType.RF] == pytest.approx(100.0)
    assert stats.per_layer_coverage_pct[SensorType.Radar] == pytest.approx(0.0)


def test_coverage_threshold_override_works() -> None:
    """Custom threshold changes which cells count as covered."""
    from salus.engine.coverage import compute_coverage_stats
    from salus.models.sensor import SensorType

    site = _flat_site(4, 4)
    layer = np.full((4, 4), 0.4, dtype=np.float32)
    composite = np.ones((4, 4), dtype=bool)
    gaps = np.zeros((4, 4), dtype=bool)
    layer_coverages = {SensorType.RF: layer}

    # With default threshold (0.5) — 0.4 < 0.5 → not covered
    stats_default = compute_coverage_stats(site, layer_coverages, composite, gaps, [])
    assert stats_default.per_layer_coverage_pct[SensorType.RF] == pytest.approx(0.0)

    # With override threshold (0.3) — 0.4 >= 0.3 → covered
    stats_low = compute_coverage_stats(
        site, layer_coverages, composite, gaps, [], coverage_threshold=0.3
    )
    assert stats_low.per_layer_coverage_pct[SensorType.RF] == pytest.approx(100.0)


def test_coverage_threshold_out_of_range_raises() -> None:
    """coverage_threshold outside [0, 1] raises ValueError (D-250 guard)."""
    from salus.engine.coverage import compute_coverage_stats
    from salus.models.sensor import SensorType

    site = _flat_site(4, 4)
    layer = np.ones((4, 4), dtype=bool)
    composite = np.ones((4, 4), dtype=bool)
    gaps = np.zeros((4, 4), dtype=bool)
    layer_coverages = {SensorType.RF: layer}

    with pytest.raises(ValueError, match="coverage_threshold"):
        compute_coverage_stats(site, layer_coverages, composite, gaps, [], coverage_threshold=1.5)

    with pytest.raises(ValueError, match="coverage_threshold"):
        compute_coverage_stats(site, layer_coverages, composite, gaps, [], coverage_threshold=-0.1)


# ---------------------------------------------------------------------------
# Canopy overlay in render_composite_coverage_map and render_gap_map
# ---------------------------------------------------------------------------


def test_render_composite_coverage_map_with_canopy(tmp_path: Path) -> None:
    """render_composite_coverage_map succeeds when site has canopy_height_m."""
    from salus.engine.coverage import VEGETATION_COVERAGE_THRESHOLD
    from salus.models.sensor import SensorType
    from salus.report.maps import render_composite_coverage_map

    canopy = np.zeros((10, 10), dtype=np.float64)
    canopy[3:7, 3:7] = 5.0
    site = _site_with_canopy(canopy)

    layer = {SensorType.RF: np.ones((10, 10), dtype=bool)}
    out = tmp_path / "composite.png"

    result = render_composite_coverage_map(
        site,
        layer,
        out,
        show_canopy=True,
        coverage_threshold=VEGETATION_COVERAGE_THRESHOLD,
    )

    assert result == out
    assert out.exists()


def test_render_composite_coverage_map_show_canopy_false(tmp_path: Path) -> None:
    """render_composite_coverage_map with show_canopy=False does not raise."""
    from salus.models.sensor import SensorType
    from salus.report.maps import render_composite_coverage_map

    canopy = np.full((10, 10), 3.0, dtype=np.float64)
    site = _site_with_canopy(canopy)
    layer = {SensorType.RF: np.ones((10, 10), dtype=bool)}
    out = tmp_path / "no_canopy.png"

    result = render_composite_coverage_map(site, layer, out, show_canopy=False)

    assert result.exists()


def test_render_gap_map_with_canopy(tmp_path: Path) -> None:
    """render_gap_map succeeds when site has canopy_height_m."""
    from salus.report.maps import render_gap_map

    canopy = np.zeros((10, 10), dtype=np.float64)
    canopy[2:5, 2:5] = 8.0
    site = _site_with_canopy(canopy)

    composite = np.ones((10, 10), dtype=bool)
    gaps = np.zeros((10, 10), dtype=bool)
    gaps[8, 8] = True
    out = tmp_path / "gap.png"

    result = render_gap_map(site, composite, gaps, out, show_canopy=True)

    assert result == out
    assert out.exists()


def test_render_gap_map_show_canopy_false(tmp_path: Path) -> None:
    """render_gap_map with show_canopy=False does not raise."""
    from salus.report.maps import render_gap_map

    canopy = np.full((10, 10), 5.0, dtype=np.float64)
    site = _site_with_canopy(canopy)
    composite = np.ones((10, 10), dtype=bool)
    gaps = np.zeros((10, 10), dtype=bool)
    gaps[0, 0] = True
    out = tmp_path / "gap_no_canopy.png"

    result = render_gap_map(site, composite, gaps, out, show_canopy=False)

    assert result.exists()
