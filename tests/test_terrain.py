"""Tests for terrain ingestion and SiteModel."""

import numpy as np
import pytest
from shapely.geometry import Polygon

from salus.ingest.terrain import load_dem
from salus.models.site import SiteModel
from salus.models.zone import Zone, ZoneType


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

    def test_zones_default_empty(self):
        """SiteModel zones must default to an empty list."""
        dem = np.zeros((10, 10))
        site = SiteModel(dem=dem, resolution=1.0, origin_x=0.0, origin_y=0.0)
        assert site.zones == []

    def test_zones_accepts_zone_list(self):
        """SiteModel must accept a list of Zone objects."""
        dem = np.zeros((10, 10))
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        zone = Zone(name="Test", zone_type=ZoneType.perimeter, geometry=poly)
        site = SiteModel(dem=dem, resolution=1.0, origin_x=0.0, origin_y=0.0, zones=[zone])
        assert len(site.zones) == 1
        assert site.zones[0].name == "Test"

    def test_dsm_shape_mismatch_in_constructor(self):
        """SiteModel must reject a DSM whose shape differs from the DEM."""
        dem = np.zeros((10, 10))
        dsm = np.zeros((20, 20))
        with pytest.raises(ValueError, match="shape"):
            SiteModel(dem=dem, dsm=dsm, resolution=1.0, origin_x=0.0, origin_y=0.0)

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

    def test_rejects_zero_resolution(self):
        with pytest.raises(ValueError, match="resolution"):
            SiteModel(dem=np.zeros((10, 10)), resolution=0.0, origin_x=0.0, origin_y=0.0)

    def test_rejects_negative_resolution(self):
        with pytest.raises(ValueError, match="resolution"):
            SiteModel(dem=np.zeros((10, 10)), resolution=-5.0, origin_x=0.0, origin_y=0.0)

    def test_rejects_infinite_resolution(self):
        with pytest.raises(ValueError, match="finite"):
            SiteModel(dem=np.zeros((10, 10)), resolution=float("inf"), origin_x=0.0, origin_y=0.0)

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

    def test_dem_undefined_crs_raises(self, tmp_path):
        """A DEM with no CRS defined must raise ValueError."""
        import rasterio
        from rasterio.transform import from_bounds

        path = tmp_path / "no_crs.tif"
        data = np.full((10, 10), 50.0, dtype=np.float64)
        transform = from_bounds(0, 0, 10, 10, 10, 10)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype="float64",
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        with pytest.raises(ValueError, match="CRS"):
            load_dem(path)

    def test_dsm_undefined_crs_raises(self, flat_dem_path, tmp_path):
        """A DSM with no CRS defined must raise ValueError."""
        import rasterio
        from rasterio.transform import from_bounds

        dsm_path = tmp_path / "dsm_no_crs.tif"
        data = np.full((100, 100), 52.0, dtype=np.float64)
        transform = from_bounds(500000, 6100000, 500100, 6100100, 100, 100)
        with rasterio.open(
            dsm_path,
            "w",
            driver="GTiff",
            height=100,
            width=100,
            count=1,
            dtype="float64",
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        with pytest.raises(ValueError, match="CRS"):
            load_dem(flat_dem_path, dsm_path=dsm_path)

    def test_dsm_crs_mismatch_warns_and_reprojects(self, flat_dem_path, tmp_path):
        """A DSM with a different CRS must be reprojected with a warning."""
        import rasterio
        from pyproj import Transformer
        from rasterio.crs import CRS
        from rasterio.transform import from_bounds

        # Convert DEM bounds from EPSG:28354 to WGS84 for the DSM
        t = Transformer.from_crs(28354, 4326, always_xy=True)
        left, bottom = t.transform(500000.0, 6100000.0)
        right, top = t.transform(500100.0, 6100100.0)

        dsm_path = tmp_path / "dsm_wgs84.tif"
        dsm_data = np.full((50, 50), 52.0, dtype=np.float64)
        transform = from_bounds(left, bottom, right, top, 50, 50)
        with rasterio.open(
            dsm_path,
            "w",
            driver="GTiff",
            height=50,
            width=50,
            count=1,
            dtype="float64",
            crs=CRS.from_epsg(4326),
            transform=transform,
        ) as dst:
            dst.write(dsm_data, 1)

        with pytest.warns(UserWarning, match="eprojecting"):
            site = load_dem(flat_dem_path, dsm_path=dsm_path)

        assert site.dsm is not None
        assert site.dsm.shape == site.dem.shape

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
