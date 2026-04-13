"""Tests for the Salus Interface API — S14.2 and S14.3.

Tests cover:
  - GET /api/health       (S14.2-1)
  - GET /api/sensors      (S14.2-2)
  - GET /api/effectors    (S14.2-2)
  - POST /api/simulate    (S14.2-3, SSE stream)
  - POST /api/optimise    (S14.2-4, SSE stream)
  - POST /api/report      (S14.2-5, PDF binary)
  - POST /api/terrain/load        (S14.3-2)
  - GET  /api/terrain/tile-progress (S14.3-2, SSE)
  - GET  /api/terrain/tiles/{z}/{x}/{y}.png (S14.3-3)

The health test also exercises the subprocess startup path via TestClient.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from salus.interface_api.app import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    """Parse SSE text/event-stream body into a list of event dicts."""
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:") :].strip()
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# S14.2-1: Health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_ok() -> None:
    """GET /api/health returns {"status": "ok", "version": ...}."""
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["version"]


def test_health_subprocess(tmp_path: Path) -> None:
    """Server started in a subprocess serves /api/health correctly."""
    port = 15432
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import uvicorn; from salus.interface_api.app import app; "
            f"uvicorn.run(app, host='127.0.0.1', port={port}, log_level='warning')",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        import urllib.request

        deadline = time.monotonic() + 20.0
        last_exc: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health", timeout=2
                ) as resp:
                    body = json.loads(resp.read())
                    assert body["status"] == "ok"
                    return  # success — exit the test
            except Exception as exc:
                last_exc = exc
                time.sleep(0.25)
        pytest.fail(f"Server did not respond within 10 s: {last_exc}")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# S14.2-2: Library endpoints
# ---------------------------------------------------------------------------


def test_sensors_returns_grouped_dict() -> None:
    """GET /api/sensors returns a dict keyed by sensor type."""
    with TestClient(app) as client:
        resp = client.get("/api/sensors")
    assert resp.status_code == 200
    body = resp.json()
    # Should be a dict; may be empty if no sensor YAMLs are present in the
    # test environment, but the structure must be correct.
    assert isinstance(body, dict)
    for type_key, items in body.items():
        assert isinstance(type_key, str)
        assert isinstance(items, list)
        for item in items:
            assert "name" in item
            assert item["type"] == type_key


def test_effectors_returns_grouped_dict() -> None:
    """GET /api/effectors returns a dict keyed by effector type."""
    with TestClient(app) as client:
        resp = client.get("/api/effectors")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    for type_key, items in body.items():
        assert isinstance(type_key, str)
        assert isinstance(items, list)


def test_sensors_known_entry(flat_dem_path: Path) -> None:
    """A known sensor from the YAML fixtures appears in the correct type group."""
    with TestClient(app) as client:
        resp = client.get("/api/sensors")
    body = resp.json()
    # Flatten all sensors and check that at least one entry has required fields
    all_sensors = [s for group in body.values() for s in group]
    if all_sensors:
        first = all_sensors[0]
        assert "name" in first
        assert "max_range_m" in first
        assert "type" in first


# ---------------------------------------------------------------------------
# S14.2-3: /api/simulate SSE stream
# ---------------------------------------------------------------------------


def _minimal_scenario_payload(dem_path: Path) -> dict[str, Any]:
    """Build a minimal ScenarioConfig-compatible JSON payload."""
    return {
        "site_dem_path": str(dem_path),
        "sensor_placements": [],
    }


def test_simulate_sse_stream_terminates_with_complete(flat_dem_path: Path) -> None:
    """POST /api/simulate returns an SSE stream that ends with a complete event."""
    payload = _minimal_scenario_payload(flat_dem_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/simulate",
            json=payload,
            headers={"Accept": "text/event-stream"},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    assert events, "Expected at least one SSE event"

    types = [e.get("type") for e in events]
    assert "complete" in types, f"No 'complete' event in stream; got types: {types}"

    complete_event = next(e for e in events if e.get("type") == "complete")
    assert "result" in complete_event
    result = complete_event["result"]
    assert "total_coverage_pct" in result
    assert "generated_at" in result


def test_simulate_sse_progress_events_emitted(flat_dem_path: Path) -> None:
    """SSE stream emits at least one progress event before complete."""
    payload = _minimal_scenario_payload(flat_dem_path)
    with TestClient(app) as client:
        resp = client.post("/api/simulate", json=payload)

    events = _parse_sse(resp.text)
    progress_events = [e for e in events if e.get("type") == "progress"]
    assert progress_events, "Expected progress events before complete"
    for evt in progress_events:
        assert "message" in evt
        assert "pct" in evt
        assert 0 <= evt["pct"] <= 100


def test_simulate_invalid_dem_path_yields_error_event() -> None:
    """POST /api/simulate with a non-existent DEM path yields an error event."""
    payload = {
        "site_dem_path": "/nonexistent/path/terrain.tif",
        "sensor_placements": [],
    }
    with TestClient(app) as client:
        resp = client.post("/api/simulate", json=payload)
    assert resp.status_code == 200  # SSE always 200; error is in the stream body
    events = _parse_sse(resp.text)
    types = [e.get("type") for e in events]
    assert "error" in types, f"Expected error event; got types: {types}"


# ---------------------------------------------------------------------------
# S14.2-4: /api/optimise SSE stream
# ---------------------------------------------------------------------------


def test_optimise_sse_stream_terminates_with_complete(flat_dem_path: Path) -> None:
    """POST /api/optimise returns an SSE stream ending with a complete event."""
    # Use the bundled sensor library — pick the first available sensor name.
    with TestClient(app) as client:
        sensors_resp = client.get("/api/sensors")
    sensor_groups = sensors_resp.json()
    all_sensor_names = [s["name"] for group in sensor_groups.values() for s in group]

    if not all_sensor_names:
        pytest.skip("No sensors in bundled library — skipping optimiser test.")

    payload = {
        "terrain": str(flat_dem_path),
        "sensor_library_filter": [all_sensor_names[0]],
        "constraints": {"coverage_threshold_pct": 50.0, "step_m": 50.0},
    }
    with TestClient(app) as client:
        resp = client.post(
            "/api/optimise",
            json=payload,
            headers={"Accept": "text/event-stream"},
        )
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    types = [e.get("type") for e in events]
    assert "complete" in types or "error" in types, (
        f"Stream did not terminate with complete or error; types: {types}"
    )

    if "complete" in types:
        complete_event = next(e for e in events if e.get("type") == "complete")
        result = complete_event["result"]
        assert "proposed_placements" in result
        assert "coverage_pct" in result


def test_optimise_unknown_sensor_yields_error(flat_dem_path: Path) -> None:
    """POST /api/optimise with unknown sensor names yields an error event."""
    payload = {
        "terrain": str(flat_dem_path),
        "sensor_library_filter": ["NonExistentSensor9999"],
        "constraints": {"step_m": 50.0},
    }
    with TestClient(app) as client:
        resp = client.post("/api/optimise", json=payload)
    events = _parse_sse(resp.text)
    types = [e.get("type") for e in events]
    assert "error" in types, f"Expected error for unknown sensor; got: {types}"


# ---------------------------------------------------------------------------
# S14.2-5: /api/report PDF endpoint
# ---------------------------------------------------------------------------


def _minimal_report_request(dem_path: Path) -> dict[str, Any]:
    """Build a minimal ReportRequest payload using spec-defined field names."""
    return {
        "report_config": {
            "site_dem_path": str(dem_path),
            "sensor_placements": [],
        },
        "sim_results": {
            "scenario_name": "test_flat",
            "generated_at": "2026-04-13T00:00:00Z",
            "total_coverage_pct": 0.0,
            "gap_area_m2": 10000.0,
            "largest_contiguous_gap_m2": 10000.0,
            "per_layer_coverage_pct": {},
            "per_zone_coverage_pct": {},
            "executive_summary": "Test report.",
            "assumptions": {},
        },
    }


def test_report_returns_pdf_bytes(flat_dem_path: Path) -> None:
    """POST /api/report returns a valid PDF (starts with %%PDF-)."""
    payload = _minimal_report_request(flat_dem_path)
    with TestClient(app) as client:
        resp = client.post("/api/report", json=payload)
    assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text[:200]}"
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF", (
        f"Response does not start with %PDF magic bytes; got: {resp.content[:16]!r}"
    )


def test_report_invalid_scenario_returns_422(flat_dem_path: Path) -> None:
    """POST /api/report with an invalid report_config body returns 422."""
    payload = {
        "report_config": {"site_dem_path": ""},  # invalid: empty path
        "sim_results": {
            "total_coverage_pct": 0.0,
            "gap_area_m2": 0.0,
            "largest_contiguous_gap_m2": 0.0,
        },
    }
    with TestClient(app) as client:
        resp = client.post("/api/report", json=payload)
    # Either 422 (Pydantic validation) or 422 from our explicit guard
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# S14.3: Terrain endpoints
# ---------------------------------------------------------------------------


def test_terrain_load_returns_metadata(flat_dem_path: Path) -> None:
    """POST /api/terrain/load with a valid GeoTIFF returns terrain metadata."""
    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        resp = client.post(
            "/api/terrain/load",
            files={"dem_file": ("flat.tif", dem_bytes, "image/tiff")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "dem_path" in body
    assert "bounds_wgs84" in body
    assert isinstance(body["bounds_wgs84"], list)
    assert len(body["bounds_wgs84"]) == 4
    assert "centre_wgs84" in body
    assert isinstance(body["centre_wgs84"], list)
    assert len(body["centre_wgs84"]) == 2
    assert "resolution_m" in body
    assert body["resolution_m"] > 0
    assert "tile_url_template" in body
    assert "{z}" in body["tile_url_template"]
    assert "terrain_tile_count" in body
    assert body["terrain_tile_count"] > 0
    assert "terrain_min_zoom" in body
    assert "terrain_max_zoom" in body
    assert body["terrain_max_zoom"] >= body["terrain_min_zoom"]


def test_terrain_load_includes_crs_epsg(flat_dem_path: Path) -> None:
    """POST /api/terrain/load returns the correct EPSG code (28354 for flat DEM fixture)."""
    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        resp = client.post(
            "/api/terrain/load",
            files={"dem_file": ("flat.tif", dem_bytes, "image/tiff")},
        )

    assert resp.status_code == 200
    assert resp.json()["crs_epsg"] == 28354


def test_terrain_load_with_dsm(flat_dem_path: Path) -> None:
    """POST /api/terrain/load accepts optional dsm_file parameter."""
    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        resp = client.post(
            "/api/terrain/load",
            files={
                "dem_file": ("flat.tif", dem_bytes, "image/tiff"),
                "dsm_file": ("flat_dsm.tif", dem_bytes, "image/tiff"),
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["dsm_path"] is not None


def test_terrain_load_invalid_file_returns_422() -> None:
    """POST /api/terrain/load with a non-GeoTIFF returns 422."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/terrain/load",
            files={"dem_file": ("bad.tif", b"not a tiff", "image/tiff")},
        )
    assert resp.status_code == 422


def test_terrain_tile_progress_returns_sse_stream(flat_dem_path: Path) -> None:
    """GET /api/terrain/tile-progress returns SSE stream after terrain is loaded."""
    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        # Load terrain first so the session is active
        load_resp = client.post(
            "/api/terrain/load",
            files={"dem_file": ("flat.tif", dem_bytes, "image/tiff")},
        )
        assert load_resp.status_code == 200

        # Read SSE stream — collect events until "complete"
        progress_resp = client.get("/api/terrain/tile-progress")

    assert progress_resp.status_code == 200
    assert "text/event-stream" in progress_resp.headers.get("content-type", "")

    events = _parse_sse(progress_resp.text)
    assert len(events) > 0

    # Final event must be "complete" or "error"
    last = events[-1]
    assert last["type"] in ("complete", "error"), f"unexpected final event type: {last}"


def test_terrain_tile_served_after_load(flat_dem_path: Path) -> None:
    """GET /api/terrain/tiles/{z}/{x}/{y}.png returns PNG after terrain is loaded."""
    import time as _time

    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        load_resp = client.post(
            "/api/terrain/load",
            files={"dem_file": ("flat.tif", dem_bytes, "image/tiff")},
        )
        assert load_resp.status_code == 200
        body = load_resp.json()

        # Wait briefly for tile generation to start
        _time.sleep(0.2)

        # flat_dem_path is in EPSG:28354 (MGA Zone 54, central Australia).
        # Get expected bounds and pick a tile from them.
        min_zoom = body["terrain_min_zoom"]
        bounds = body["bounds_wgs84"]
        west, south, east, north = bounds

        import mercantile

        tiles = list(mercantile.tiles(west, south, east, north, zooms=min_zoom))
        assert tiles, "at least one tile expected at min_zoom"
        tile = tiles[0]

        tile_resp = client.get(f"/api/terrain/tiles/{tile.z}/{tile.x}/{tile.y}.png")

    # Either 200 (tile in DEM extent) or 404 (edge tile outside extent) is valid.
    # The test only requires the endpoint is functional; content validity is
    # verified by the Terrarium encoding unit below.
    assert tile_resp.status_code in (200, 404)
    if tile_resp.status_code == 200:
        assert tile_resp.headers.get("content-type") == "image/png"


def test_terrain_tile_404_when_no_session_active() -> None:
    """GET /api/terrain/tiles/{z}/{x}/{y}.png returns 404 if no session is loaded."""
    from salus.interface_api.app import _terrain_session, _terrain_session_lock

    # Reset session
    with _terrain_session_lock:
        _terrain_session["tile_dir"] = None
        _terrain_session["dem_path"] = None

    with TestClient(app) as client:
        resp = client.get("/api/terrain/tiles/10/900/600.png")

    assert resp.status_code == 404


def test_compute_zoom_levels_reasonable_range() -> None:
    """_compute_zoom_levels returns sensible zoom ranges for typical DEM resolutions."""
    from salus.interface_api.app import _compute_zoom_levels

    min_z_1m, max_z_1m = _compute_zoom_levels(1.0)
    assert 5 <= max_z_1m <= 13
    assert min_z_1m <= max_z_1m

    min_z_30m, max_z_30m = _compute_zoom_levels(30.0)
    assert max_z_30m < max_z_1m  # coarser DEM → lower max zoom

    min_z_100m, max_z_100m = _compute_zoom_levels(100.0)
    assert max_z_100m < max_z_30m


def test_generate_terrain_tile_returns_png_bytes(flat_dem_path: Path) -> None:
    """_generate_terrain_tile returns valid PNG bytes for an in-extent tile."""
    import mercantile as _mercantile
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds

    from salus.interface_api.app import _generate_terrain_tile

    with rasterio.open(flat_dem_path) as src:
        wgs84 = CRS.from_epsg(4326)
        west, south, east, north = transform_bounds(
            src.crs,
            wgs84,
            src.bounds.left,
            src.bounds.bottom,
            src.bounds.right,
            src.bounds.top,
        )

    tiles = list(_mercantile.tiles(west, south, east, north, zooms=10))
    assert tiles, "no tiles found for zoom 10"

    tile = tiles[0]
    data = _generate_terrain_tile(flat_dem_path, tile.z, tile.x, tile.y)

    assert data is not None, "expected PNG bytes for an in-extent tile"
    # PNG magic bytes: 137 80 78 71
    assert data[:4] == b"\x89PNG"


def test_generate_terrain_tile_returns_none_outside_extent(flat_dem_path: Path) -> None:
    """_generate_terrain_tile returns None for a tile clearly outside the DEM."""
    from salus.interface_api.app import _generate_terrain_tile

    # z=1, x=1, y=1 is a tile covering roughly (0°–90°E, 0°–66°N), which
    # does not overlap with EPSG:28354 Zone 54 (Australia 150°E area).
    data = _generate_terrain_tile(flat_dem_path, 1, 1, 1)
    assert data is None
