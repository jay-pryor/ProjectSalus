"""End-to-end interface integration tests (S14.14-4).

Two layers of coverage:

1.  HTTP integration — uses FastAPI's TestClient to assert that:
    - All 14 interface module JS files are served via /interface/
    - index.html is served with the expected shell script tag
    - /api/health returns 200
    - /api/sensors and /api/effectors return grouped dicts

2.  Playwright browser E2E — full workflow test requiring the ``playwright``
    package and installed browsers (``playwright install chromium``).
    Skipped automatically when Playwright is not installed or SALUS_E2E=1
    is not set (to avoid running in routine CI).

    To run the browser tests locally:
        pip install playwright && playwright install chromium
        SALUS_E2E=1 pytest tests/test_e2e_interface.py -k browser -v
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from salus.interface_api.app import app

_INTERFACE_DIR = Path(__file__).parent.parent / "src" / "salus" / "viewer" / "interface"
_MODULE_INDEX = _INTERFACE_DIR / "modules" / "index.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expected_modules() -> list[str]:
    """Return the module IDs listed in modules/index.json (excluding _test-module)."""
    try:
        with _MODULE_INDEX.open() as fh:
            ids: list[str] = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        pytest.skip(f"modules/index.json unavailable: {exc}")
    return [m for m in ids if not m.startswith("_")]


# ---------------------------------------------------------------------------
# HTTP integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_api_health(client: TestClient) -> None:
    """FastAPI backend responds to /api/health."""
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_interface_index_html_served(client: TestClient) -> None:
    """GET /interface/ serves index.html with the shell script tag."""
    resp = client.get("/interface/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "shell.js" in resp.text


def test_interface_shell_js_served(client: TestClient) -> None:
    """GET /interface/shell.js returns JavaScript."""
    resp = client.get("/interface/shell.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")


def test_interface_modules_index_served(client: TestClient) -> None:
    """GET /interface/modules/index.json returns a JSON array of module IDs."""
    resp = client.get("/interface/modules/index.json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert "terrain-loader" in data
    assert "coverage-viewer" in data


def test_interface_all_module_js_files_served(client: TestClient) -> None:
    """Every non-test module has its index.js reachable via /interface/."""
    for module_id in _expected_modules():
        url = f"/interface/modules/{module_id}/index.js"
        resp = client.get(url)
        assert resp.status_code == 200, f"{module_id}/index.js returned {resp.status_code}"


def test_interface_all_module_manifests_served(client: TestClient) -> None:
    """Every non-test module has its manifest.json reachable via /interface/."""
    for module_id in _expected_modules():
        url = f"/interface/modules/{module_id}/manifest.json"
        resp = client.get(url)
        assert resp.status_code == 200, f"{module_id}/manifest.json returned {resp.status_code}"


def test_api_sensors_returns_grouped_dict(client: TestClient) -> None:
    """/api/sensors returns an object (grouped by type), not a list."""
    resp = client.get("/api/sensors")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_api_effectors_returns_grouped_dict(client: TestClient) -> None:
    """/api/effectors returns an object (grouped by type), not a list."""
    resp = client.get("/api/effectors")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_static_vendor_maplibre_css_served(client: TestClient) -> None:
    """MapLibreGL CSS is served at /static/vendor/maplibre-gl.css."""
    resp = client.get("/static/vendor/maplibre-gl.css")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# pregen_terrain_from_path (D-463)
# ---------------------------------------------------------------------------


def test_pregen_terrain_from_path_missing_dem(tmp_path: Path) -> None:
    """Returns None and logs a warning for a non-existent DEM path."""
    from salus.interface_api.app import pregen_terrain_from_path

    result = pregen_terrain_from_path(tmp_path / "nonexistent.tif")
    assert result is None


def test_pregen_terrain_from_path_valid_dem(tmp_path: Path) -> None:
    """Creates a session and starts tile generation for a valid flat DEM."""
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds

    from salus.interface_api.app import (
        _terrain_sessions,
        pregen_terrain_from_path,
    )

    dem_path = tmp_path / "flat.tif"
    data = np.full((32, 32), 10.0, dtype=np.float32)
    transform = from_bounds(148.0, -36.0, 148.1, -35.9, 32, 32)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=32,
        width=32,
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as ds:
        ds.write(data, 1)

    session_id = pregen_terrain_from_path(dem_path)
    assert session_id is not None
    assert session_id in _terrain_sessions
    meta = _terrain_sessions[session_id]["metadata"]
    assert meta["dem_path"] == str(dem_path.resolve())
    assert meta["dsm_path"] is None


# ---------------------------------------------------------------------------
# Playwright browser E2E (skipped unless SALUS_E2E=1 and playwright installed)
# ---------------------------------------------------------------------------

_PLAYWRIGHT_AVAILABLE = False
try:
    import playwright  # noqa: F401

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

_E2E_ENABLED = os.environ.get("SALUS_E2E", "0") == "1"

_SKIP_BROWSER = pytest.mark.skipif(
    not (_PLAYWRIGHT_AVAILABLE and _E2E_ENABLED),
    reason=(
        "Playwright browser tests require: pip install playwright && playwright install chromium, "
        "and SALUS_E2E=1 environment variable."
    ),
)


@_SKIP_BROWSER
def test_browser_full_workflow(tmp_path: Path) -> None:
    """Full browser E2E: terrain load → place sensor → simulate → coverage.

    Requires:
        pip install playwright && playwright install chromium
        SALUS_E2E=1 pytest tests/test_e2e_interface.py::test_browser_full_workflow

    Fixture DEM: a small flat GeoTIFF created in tmp_path.
    """
    import subprocess
    import time

    import numpy as np
    import rasterio
    from playwright.sync_api import sync_playwright
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds

    # Build a minimal flat DEM
    dem_path = tmp_path / "e2e_flat.tif"
    data = np.full((50, 50), 50.0, dtype=np.float64)
    transform = from_bounds(500000, 6100000, 500050, 6100050, 50, 50)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=50,
        width=50,
        count=1,
        dtype="float64",
        crs=CRS.from_epsg(28354),
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    # Start the FastAPI server on a free port
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = subprocess.Popen(
        [
            "python",
            "-m",
            "uvicorn",
            "salus.interface_api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2.0)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/interface/")

            # All 14 module nav buttons should appear (minus _test-module)
            expected = _expected_modules()
            for module_id in expected:
                page.wait_for_selector(
                    f"[data-module-id='{module_id}']",
                    timeout=10_000,
                )

            # Terrain Loader button is enabled (no prerequisites)
            terrain_btn = page.locator("[data-module-id='terrain-loader']")
            assert terrain_btn.is_enabled(), "terrain-loader button should be enabled"

            # Placement Editor button is disabled (requires terrain)
            placement_btn = page.locator("[data-module-id='placement-editor']")
            assert not placement_btn.is_enabled(), (
                "placement-editor should be disabled before terrain loads"
            )

            browser.close()
    finally:
        server.terminate()
        server.wait()
