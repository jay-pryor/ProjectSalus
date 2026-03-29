"""Tests for terrain ingestion and SiteModel."""

import numpy as np
import pytest

from salus.ingest.terrain import load_dem
from salus.models.site import SiteModel


class TestSiteModel:
    def test_create_basic(self):
        dem = np.zeros((10, 10))
        site = SiteModel(
            dem=dem,
            resolution=1.0,
            origin_x=0.0,
            origin_y=0.0,
        )
        assert site.rows == 10
        assert site.cols == 10
        assert site.resolution == 1.0
        assert site.dsm is None
        assert site.surface_array() is site.dem

    def test_surface_array_prefers_dsm(self):
        dem = np.zeros((10, 10))
        dsm = np.ones((10, 10))
        site = SiteModel(
            dem=dem,
            dsm=dsm,
            resolution=1.0,
            origin_x=0.0,
            origin_y=0.0,
        )
        assert site.surface_array() is site.dsm

    def test_rejects_1d_dem(self):
        with pytest.raises(ValueError, match="2D"):
            SiteModel(
                dem=np.zeros(10),
                resolution=1.0,
                origin_x=0.0,
                origin_y=0.0,
            )

    def test_extent(self):
        dem = np.zeros((100, 200))
        site = SiteModel(
            dem=dem,
            resolution=5.0,
            origin_x=1000.0,
            origin_y=2000.0,
        )
        min_x, max_x, min_y, max_y = site.extent
        assert min_x == 1000.0
        assert max_x == 1000.0 + 200 * 5.0
        assert max_y == 2000.0
        assert min_y == 2000.0 - 100 * 5.0


class TestLoadDem:
    def test_load_flat_dem(self, flat_dem_path):
        site = load_dem(flat_dem_path)
        assert site.rows == 100
        assert site.cols == 100
        assert site.resolution == pytest.approx(1.0)
        assert site.crs_epsg == 28354
        assert np.nanmean(site.dem) == pytest.approx(50.0)

    def test_load_ridge_dem(self, ridge_dem_path):
        site = load_dem(ridge_dem_path)
        assert site.rows == 200
        assert site.cols == 200
        # Ridge peak at row 100 should be 150m
        assert site.dem[100, 100] == pytest.approx(150.0)
        # Flat areas should be 50m
        assert site.dem[0, 0] == pytest.approx(50.0)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_dem("/nonexistent/path.tif")

    def test_dsm_shape_mismatch(self, flat_dem_path, ridge_dem_path):
        with pytest.raises(ValueError, match="shape"):
            load_dem(flat_dem_path, dsm_path=ridge_dem_path)

    def test_dsm_not_found(self, flat_dem_path, tmp_path):
        """Passing a nonexistent DSM path must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="DSM not found"):
            load_dem(flat_dem_path, dsm_path=tmp_path / "no_such_dsm.tif")

    def test_dem_nodata_replaced_with_nan(self, tmp_path):
        """DEM cells matching the nodata value must be converted to NaN."""
        import rasterio
        from rasterio.crs import CRS
        from rasterio.transform import from_bounds

        path = tmp_path / "nodata.tif"
        data = np.full((10, 10), 50.0, dtype=np.float32)
        data[5, 5] = -9999.0  # nodata cell
        transform = from_bounds(0, 0, 10, 10, 10, 10)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype="float32",
            crs=CRS.from_epsg(28354),
            transform=transform,
            nodata=-9999.0,
        ) as dst:
            dst.write(data, 1)

        site = load_dem(path)
        assert np.isnan(site.dem[5, 5])
        assert not np.isnan(site.dem[0, 0])
