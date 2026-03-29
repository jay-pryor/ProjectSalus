"""Shared test fixtures for Salus."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    """Path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def flat_dem_path(tmp_path):
    """Create a flat 100x100 DEM at 1m resolution, 50m elevation, EPSG:28354 (MGA Zone 54)."""
    path = tmp_path / "flat.tif"
    data = np.full((100, 100), 50.0, dtype=np.float64)
    transform = from_bounds(500000, 6100000, 500100, 6100100, 100, 100)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=100,
        width=100,
        count=1,
        dtype="float64",
        crs=CRS.from_epsg(28354),
        transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path


@pytest.fixture
def ridge_dem_path(tmp_path):
    """Create a 200x200 DEM with a ridge across the middle.

    Elevation is 50m everywhere except rows 95-105 which ramp up to 150m,
    creating a ridge that blocks line-of-sight from one side to the other.
    """
    path = tmp_path / "ridge.tif"
    data = np.full((200, 200), 50.0, dtype=np.float64)
    # Ridge: rows 95-105, peak at row 100
    for r in range(95, 106):
        height = 150.0 - abs(r - 100) * 10.0
        data[r, :] = max(height, 50.0)
    transform = from_bounds(500000, 6100000, 500200, 6100200, 200, 200)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=200,
        width=200,
        count=1,
        dtype="float64",
        crs=CRS.from_epsg(28354),
        transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path
