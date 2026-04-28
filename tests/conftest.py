"""Shared test fixtures for Salus."""

import tempfile
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _allow_tmp_dem_dirs():
    """Register the pytest tmp root and fixtures directory with the interface
    API path-traversal allowlist (D-407) so DEMs created under ``tmp_path``
    pass the security guard, then restore the original allowlist on teardown
    so cross-test mutation cannot widen the allowlist beyond what each test
    expects (D-425).

    Any future negative-allowlist test must use a path outside ``/tmp`` —
    ``tempfile.gettempdir()`` is registered here, so a future test that posts
    a ``/tmp/...`` path expecting a 403 would silently start passing.

    Imports the interface API lazily — tests that never touch the API should
    not be forced to import FastAPI.  We narrow the import-failure handler to
    ``ImportError`` so a typo or partial install in the API surfaces rather
    than being silently swallowed (silent_failure_hunter D-415 sibling).
    """
    try:
        from salus.interface_api import app as _app
    except ImportError:
        yield
        return
    snapshot = list(_app._ALLOWED_DEM_DIRS)
    _app._register_allowed_dem_dir(Path(tempfile.gettempdir()))
    _app._register_allowed_dem_dir(FIXTURES_DIR)
    try:
        yield
    finally:
        _app._ALLOWED_DEM_DIRS[:] = snapshot


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


@pytest.fixture
def valley_dem_path(tmp_path):
    """Create a 200x200 DEM with two parallel ridges enclosing a central valley.

    Terrain layout (by column index, west→east):
    - Cols   0– 39: west ridge at 100 m elevation
    - Cols  40– 79: west slope ramping down from 100 m to 10 m
    - Cols  80–119: valley floor at 10 m elevation
    - Cols 120–159: east slope ramping up from 10 m to 100 m
    - Cols 160–199: east ridge at 100 m elevation

    A sensor placed on the east ridge (col ~180) cannot see the valley floor
    (cols 80–119) because the east ridge itself creates a terrain shadow at
    low altitude — useful for testing that valley-floor cells have detection
    count 0 and that adversarial paths prefer the valley.
    """
    path = tmp_path / "valley.tif"
    data = np.full((200, 200), 10.0, dtype=np.float64)
    # West ridge
    data[:, :40] = 100.0
    # West slope: linear ramp from 100 → 10 over cols 40–79
    for c in range(40, 80):
        data[:, c] = 100.0 - (c - 40) * (90.0 / 40.0)
    # Valley floor (cols 80–119) already set to 10 m
    # East slope: linear ramp from 10 → 100 over cols 120–159
    for c in range(120, 160):
        data[:, c] = 10.0 + (c - 120) * (90.0 / 40.0)
    # East ridge
    data[:, 160:] = 100.0
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
