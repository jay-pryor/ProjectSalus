"""Tests verifying the synthetic_site.tif fixture has the expected terrain features."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from salus.ingest.terrain import load_dem

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_site.tif"
BASE_ELEV = 50.0


@pytest.fixture(scope="module")
def synthetic_site():
    """Load the synthetic site DEM once for all tests in this module."""
    if not FIXTURE.exists():
        pytest.skip(f"Fixture not found: {FIXTURE} — run scripts/generate_test_dem.py")
    return load_dem(FIXTURE)


class TestSyntheticSiteFixture:
    def test_fixture_file_exists(self):
        """The fixture GeoTIFF must be present in the repository."""
        assert FIXTURE.exists(), f"Missing fixture: {FIXTURE}"

    def test_dimensions(self, synthetic_site):
        """DEM must be 500×500 cells."""
        assert synthetic_site.rows == 500
        assert synthetic_site.cols == 500

    def test_resolution(self, synthetic_site):
        """Resolution must be 1.0 m/cell."""
        assert synthetic_site.resolution == pytest.approx(1.0)

    def test_crs(self, synthetic_site):
        """CRS must be EPSG:28354 (GDA94 / MGA Zone 54)."""
        assert synthetic_site.crs_epsg == 28354

    def test_base_elevation(self, synthetic_site):
        """Southern flat area (rows 400–499, cols 0–149) must be ~50 m."""
        flat_region = synthetic_site.dem[400:500, 0:150]
        assert flat_region.mean() == pytest.approx(50.0, abs=1.0)

    def test_hill_peak(self, synthetic_site):
        """NE hill peak (around row 75, col 400) must be above 100 m."""
        peak_region = synthetic_site.dem[60:90, 380:420]
        assert peak_region.max() > 100.0

    def test_ridge_peak(self, synthetic_site):
        """Ridge peak (row 225) must be above 120 m."""
        assert synthetic_site.dem[225, 250] == pytest.approx(130.0, abs=2.0)

    def test_ridge_blocks_elevation(self, synthetic_site):
        """Ridge rows 200–249 must all be above base elevation."""
        ridge = synthetic_site.dem[200:250, :]
        assert ridge.min() > BASE_ELEV - 1.0

    def test_valley_depression(self, synthetic_site):
        """Valley centre (row 300, cols 150–349) must be below 40 m."""
        valley_centre = synthetic_site.dem[300, 150:350]
        assert valley_centre.min() < 40.0

    def test_no_nodata(self, synthetic_site):
        """Synthetic DEM must contain no NaN values."""
        assert not np.any(np.isnan(synthetic_site.dem))

    def test_elevation_range(self, synthetic_site):
        """Elevation must stay within 25–135 m (sanity bounds)."""
        assert synthetic_site.dem.min() >= 25.0
        assert synthetic_site.dem.max() <= 135.0
