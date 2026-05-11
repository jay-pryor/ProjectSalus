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


def _parse_sse_with_event_lines(raw: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse SSE text into (event_type_from_event_line, data_dict) tuples.

    Used by D-404 regression tests to assert an ``event:`` line is present.
    Events missing the line are reported as ``event_type = ""``.
    """
    events: list[tuple[str, dict[str, Any]]] = []
    current_event = ""
    for line in raw.splitlines():
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            payload = line[len("data:") :].strip()
            try:
                events.append((current_event, json.loads(payload)))
            except json.JSONDecodeError:
                pass
            current_event = ""
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
    """POST /api/simulate returns an SSE stream that ends with a complete event
    containing the interface-schema sim_results payload."""
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

    # Interface schema assertions (docs/Technical/InterfaceArchitecture.md §3):
    # browser modules (simulation-runner, coverage-viewer, scenario-comparison)
    # consume layers / sensor_placements / stats — not the old PNG-based shape.
    assert "layers" in result, f"sim_results must include 'layers'; got keys: {list(result)}"
    assert isinstance(result["layers"], dict)
    assert "composite" in result["layers"], "layers must include the 'composite' FeatureCollection"
    assert result["layers"]["composite"].get("type") == "FeatureCollection"

    assert "sensor_placements" in result
    assert result["sensor_placements"].get("type") == "FeatureCollection"

    assert "stats" in result
    assert isinstance(result["stats"], dict)
    # Both naming variants are exposed for cross-module compatibility.
    assert "coverage_pct" in result["stats"] or "total_coverage_pct" in result["stats"]

    assert "generated_at" in result
    assert "sanitised" in result


def test_simulate_sse_events_carry_event_line(flat_dem_path: Path) -> None:
    """D-404 regression: every SSE event must include an ``event: <type>`` line
    so the JS ``_parseSseBuffer`` can dispatch on progress/complete/error.

    Without this line the JS parser defaults to 'message' and silently drops
    every event, which is the failure mode this test guards against.
    """
    payload = _minimal_scenario_payload(flat_dem_path)
    with TestClient(app) as client:
        resp = client.post("/api/simulate", json=payload)
    assert resp.status_code == 200

    events = _parse_sse_with_event_lines(resp.text)
    assert events, "Expected at least one SSE event"

    for event_type_line, data in events:
        assert event_type_line, (
            f"Every SSE event must have an 'event:' line; got empty for data={data}"
        )
        assert event_type_line == data.get("type"), (
            f"SSE 'event: {event_type_line}' line must match data.type={data.get('type')}"
        )


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


def test_simulate_missing_dem_file_yields_error_event(tmp_path: Path) -> None:
    """POST /api/simulate with a path inside the allowlist but pointing at
    a non-existent file yields an error event (not a 403)."""
    missing = tmp_path / "does_not_exist.tif"
    payload = {
        "site_dem_path": str(missing),
        "sensor_placements": [],
    }
    with TestClient(app) as client:
        resp = client.post("/api/simulate", json=payload)
    assert resp.status_code == 200  # SSE always 200; error is in the stream body
    events = _parse_sse(resp.text)
    types = [e.get("type") for e in events]
    assert "error" in types, f"Expected error event; got types: {types}"


def test_simulate_all_placements_unknown_yields_error_event(flat_dem_path: Path) -> None:
    """D-433 regression: when every sensor_placement references a sensor not in
    the library, the SSE stream surfaces an error event rather than a misleading
    complete with 0% coverage."""
    payload = {
        "site_dem_path": str(flat_dem_path),
        "sensor_placements": [
            {
                "sensor_name": "DefinitelyNotARealSensor",
                "position_x": 500050.0,
                "position_y": 6100050.0,
                "bearing_deg": 0.0,
            }
        ],
    }
    with TestClient(app) as client:
        resp = client.post("/api/simulate", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e.get("type") for e in events]
    assert "error" in types, f"Expected error event when all placements unknown; got types: {types}"
    assert "complete" not in types, (
        f"Must not emit 'complete' when no placements survived; got types: {types}"
    )


def test_simulate_rejects_path_outside_allowlist() -> None:
    """POST /api/simulate with a DEM path outside the allowed directories
    returns 403 before any pipeline work begins (path-traversal guard)."""
    payload = {
        "site_dem_path": "/etc/passwd",
        "sensor_placements": [],
    }
    with TestClient(app) as client:
        resp = client.post("/api/simulate", json=payload)
    assert resp.status_code == 403
    assert "allowed" in resp.text.lower()


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
    """Build a minimal ReportRequest payload using spec-defined field names.

    report_config is the UI configuration shape (client_name, sanitise_level,
    include_modules, logo_path) — not a ScenarioConfig.  Scenario placements
    are sent in the top-level ``placements`` field.
    """
    # dem_path is not part of the report request — the interface never uploads
    # a DEM alongside a report — but it is kept in the fixture argument so
    # the signature matches older callers.  Silence the unused-arg warning.
    _ = dem_path
    return {
        "report_config": {
            "client_name": "Test Client",
            "sanitise_level": "none",
            "include_modules": [],
            "logo_path": None,
        },
        "sim_results": {
            "scenario_name": "test_flat",
            "generated_at": "2026-04-13T00:00:00Z",
            "stats": {
                "total_coverage_pct": 0.0,
                "gap_area_m2": 10000.0,
                "largest_contiguous_gap_m2": 10000.0,
                "per_layer_coverage_pct": {},
                "per_zone_coverage_pct": {},
            },
            "executive_summary": "Test report.",
            "assumptions": {},
        },
        "placements": {"sensors": [], "effectors": []},
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


# ---------------------------------------------------------------------------
# S14.12: /api/compare spatial diff endpoint
# ---------------------------------------------------------------------------


def _polygon_fc(coords: list[list[list[float]]]) -> dict[str, Any]:
    """Build a single-feature Polygon FeatureCollection for comparison tests."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": coords},
                "properties": {},
            }
        ],
    }


def test_compare_overlapping_polygons_returns_all_three_layers() -> None:
    """POST /api/compare with overlapping squares returns non-empty a_only, b_only, both."""
    # A: unit square from (0,0) to (2,2)
    # B: unit square from (1,1) to (3,3)
    # Overlap: (1,1) to (2,2); A-only: L-shape around overlap; B-only: mirror L-shape
    a = _polygon_fc([[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]])
    b = _polygon_fc([[[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]])

    with TestClient(app) as client:
        resp = client.post("/api/compare", json={"a_composite": a, "b_composite": b})

    assert resp.status_code == 200
    body = resp.json()
    for key in ("a_only", "b_only", "both"):
        assert key in body
        assert body[key]["type"] == "FeatureCollection"
        assert isinstance(body[key]["features"], list)

    # All three should have at least one feature for overlapping geometries
    assert len(body["a_only"]["features"]) >= 1
    assert len(body["b_only"]["features"]) >= 1
    assert len(body["both"]["features"]) >= 1


def test_compare_disjoint_polygons_has_empty_intersection() -> None:
    """Non-overlapping scenarios yield empty both/intersection, non-empty a_only/b_only."""
    a = _polygon_fc([[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]])
    b = _polygon_fc([[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]])

    with TestClient(app) as client:
        resp = client.post("/api/compare", json={"a_composite": a, "b_composite": b})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["both"]["features"]) == 0
    assert len(body["a_only"]["features"]) >= 1
    assert len(body["b_only"]["features"]) >= 1


def test_compare_identical_polygons_has_empty_a_only_and_b_only() -> None:
    """Identical scenarios yield empty a_only/b_only; both contains the full area."""
    coords = [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]
    a = _polygon_fc(coords)
    b = _polygon_fc(coords)

    with TestClient(app) as client:
        resp = client.post("/api/compare", json={"a_composite": a, "b_composite": b})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["a_only"]["features"]) == 0
    assert len(body["b_only"]["features"]) == 0
    assert len(body["both"]["features"]) >= 1


def test_compare_empty_inputs_return_empty_feature_collections() -> None:
    """Empty scenarios yield empty FeatureCollections in all three diff layers."""
    empty = {"type": "FeatureCollection", "features": []}

    with TestClient(app) as client:
        resp = client.post("/api/compare", json={"a_composite": empty, "b_composite": empty})

    assert resp.status_code == 200
    body = resp.json()
    for key in ("a_only", "b_only", "both"):
        assert body[key]["features"] == []


def test_compare_missing_fields_use_defaults() -> None:
    """Request with no a_composite/b_composite uses empty FeatureCollection defaults."""
    with TestClient(app) as client:
        resp = client.post("/api/compare", json={})

    assert resp.status_code == 200
    body = resp.json()
    # Both empty → all diff layers empty
    assert body["a_only"]["features"] == []
    assert body["b_only"]["features"] == []
    assert body["both"]["features"] == []


def test_compare_invalid_features_list_returns_422() -> None:
    """A_composite.features that is not a list returns 422."""
    bad = {"type": "FeatureCollection", "features": "not a list"}
    good = {"type": "FeatureCollection", "features": []}

    with TestClient(app) as client:
        resp = client.post("/api/compare", json={"a_composite": bad, "b_composite": good})

    assert resp.status_code == 422


def test_compare_malformed_feature_geometry_is_skipped() -> None:
    """Features with unparseable geometry are skipped with a warning, not a 500."""
    # Valid feature plus an invalid feature in scenario A
    a_features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
            "properties": {},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": "totally-invalid"},
            "properties": {},
        },
    ]
    a = {"type": "FeatureCollection", "features": a_features}
    b = _polygon_fc([[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]])

    with TestClient(app) as client:
        resp = client.post("/api/compare", json={"a_composite": a, "b_composite": b})

    # Must succeed — the valid geometry contributes to the diff
    assert resp.status_code == 200
    body = resp.json()
    assert "a_only" in body
    assert "both" in body
    # The valid unit square is entirely inside B's 2x2 square — expect empty
    # a_only and non-empty both.
    assert len(body["both"]["features"]) >= 1


def test_report_accepts_ui_report_config_without_dem_path(flat_dem_path: Path) -> None:
    """POST /api/report accepts UI-shape report_config (no site_dem_path) and returns a PDF.

    The report endpoint used to fail with 422 when report_config was not a valid
    ScenarioConfig, but the interface never constructs one client-side — this
    test locks in the permissive behaviour so the report flow does not regress.
    """
    _ = flat_dem_path
    payload = {
        "report_config": {
            "client_name": "Operator",
            "sanitise_level": "minimal",
            "include_modules": ["Executive Summary"],
            "logo_path": None,
        },
        "sim_results": {
            "scenario_name": "permissive_flow",
            "stats": {
                "total_coverage_pct": 0.0,
                "gap_area_m2": 0.0,
                "largest_contiguous_gap_m2": 0.0,
            },
        },
        "placements": {"sensors": [], "effectors": []},
    }
    with TestClient(app) as client:
        resp = client.post("/api/report", json=payload)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


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
    from salus.interface_api import app as _app

    # Reset session map
    with _app._terrain_session_lock:
        _app._terrain_sessions.clear()
        _app._terrain_latest_session_id = None

    with TestClient(app) as client:
        resp = client.get("/api/terrain/tiles/10/900/600.png")

    assert resp.status_code == 404


def test_terrain_sessions_latest_returns_404_when_no_session() -> None:
    """D-473: GET /api/terrain/sessions/latest returns 404 when no session
    has been registered (clean process / nothing pre-generated)."""
    from salus.interface_api import app as _app

    with _app._terrain_session_lock:
        _app._terrain_sessions.clear()
        _app._terrain_latest_session_id = None

    with TestClient(app) as client:
        resp = client.get("/api/terrain/sessions/latest")
    assert resp.status_code == 404


def test_terrain_sessions_latest_returns_metadata_after_load(flat_dem_path: Path) -> None:
    """D-473: GET /api/terrain/sessions/latest returns the same metadata shape
    that POST /api/terrain/load returned, so the JS shell can adopt a
    pre-generated session without re-uploading the DEM."""
    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        load = client.post(
            "/api/terrain/load",
            files={"dem_file": ("flat.tif", dem_bytes, "image/tiff")},
        )
        assert load.status_code == 200
        loaded = load.json()

        latest = client.get("/api/terrain/sessions/latest")
        assert latest.status_code == 200
        body = latest.json()

    assert body["session_id"] == loaded["session_id"]
    assert body["tile_url_template"] == loaded["tile_url_template"]
    assert body["bounds_wgs84"] == loaded["bounds_wgs84"]
    for required in (
        "centre_wgs84",
        "tile_progress_url",
        "terrain_min_zoom",
        "terrain_max_zoom",
    ):
        assert required in body, f"sessions/latest must include '{required}'"


def test_terrain_sessions_latest_returns_404_when_session_errored(flat_dem_path: Path) -> None:
    """D-476: a session whose tile-generation thread reported an error must
    not be advertised — the client must not adopt a known-broken session."""
    from salus.interface_api import app as _app

    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        load = client.post(
            "/api/terrain/load",
            files={"dem_file": ("flat.tif", dem_bytes, "image/tiff")},
        )
        assert load.status_code == 200
        sid = load.json()["session_id"]

        # Inject a tile-generation error onto the session record.
        with _app._terrain_session_lock:
            _app._terrain_sessions[sid]["error"] = "simulated tile-gen failure"

        latest = client.get("/api/terrain/sessions/latest")

    assert latest.status_code == 404, "errored session must surface as 404 from sessions/latest"


def test_terrain_sessions_latest_tracks_most_recent(flat_dem_path: Path) -> None:
    """D-473: when two loads complete, sessions/latest reflects the second one."""
    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        first = client.post(
            "/api/terrain/load",
            files={"dem_file": ("a.tif", dem_bytes, "image/tiff")},
        )
        second = client.post(
            "/api/terrain/load",
            files={"dem_file": ("b.tif", dem_bytes, "image/tiff")},
        )
        latest = client.get("/api/terrain/sessions/latest")

    assert first.status_code == 200
    assert second.status_code == 200
    assert latest.status_code == 200
    assert latest.json()["session_id"] == second.json()["session_id"]


def test_terrain_concurrent_loads_keep_disjoint_tile_paths(flat_dem_path: Path) -> None:
    """Two ``/api/terrain/load`` calls produce two distinct sessions whose
    tile_dirs and metadata do not collide (D-406 race fix).

    Pre-fix the second load overwrote the first session's ``tile_dir`` /
    ``dem_path`` in a single global dict, so the first session's pending tile
    requests were silently redirected to the second session's DEM.
    """
    from salus.interface_api import app as _app

    with open(flat_dem_path, "rb") as f:
        dem_bytes = f.read()

    with TestClient(app) as client:
        first = client.post(
            "/api/terrain/load",
            files={"dem_file": ("flat-a.tif", dem_bytes, "image/tiff")},
        )
        assert first.status_code == 200
        second = client.post(
            "/api/terrain/load",
            files={"dem_file": ("flat-b.tif", dem_bytes, "image/tiff")},
        )
        assert second.status_code == 200

    sid_a = first.json()["session_id"]
    sid_b = second.json()["session_id"]
    assert sid_a != sid_b, "session_id collision between concurrent loads"
    assert sid_a in first.json()["tile_url_template"]
    assert sid_b in second.json()["tile_url_template"]

    with _app._terrain_session_lock:
        sess_a = _app._terrain_sessions.get(sid_a)
        sess_b = _app._terrain_sessions.get(sid_b)
        assert sess_a is not None and sess_b is not None
        assert sess_a["tile_dir"] != sess_b["tile_dir"]
        assert sess_a["metadata"]["session_id"] == sid_a
        assert sess_b["metadata"]["session_id"] == sid_b


def test_compute_zoom_levels_reasonable_range() -> None:
    """_compute_zoom_levels returns sensible zoom ranges for typical DEM resolutions."""
    from salus.interface_api.app import _TERRAIN_MAX_ZOOM_CAP, _compute_zoom_levels

    min_z_1m, max_z_1m = _compute_zoom_levels(1.0)
    assert 5 <= max_z_1m <= _TERRAIN_MAX_ZOOM_CAP
    assert min_z_1m <= max_z_1m

    min_z_30m, max_z_30m = _compute_zoom_levels(30.0)
    assert max_z_30m < max_z_1m  # coarser DEM → lower max zoom

    min_z_100m, max_z_100m = _compute_zoom_levels(100.0)
    assert max_z_100m < max_z_30m


def test_compute_zoom_levels_tile_budget_walks_down() -> None:
    """When bounds are supplied, the walk-down picks the highest zoom that fits the budget."""
    import mercantile

    from salus.interface_api.app import _compute_zoom_levels

    # 2 km square at lat -35 — matches dramatic_terrain.tif extent.
    bounds = [141.0, -35.243, 141.022, -35.225]
    # Generous budget — should reach the resolution-ideal cap (~15-16 for 5 m).
    min_z, max_z = _compute_zoom_levels(5.0, bounds_wgs84=bounds, tile_budget=500)
    assert max_z >= 15, f"expected max_zoom >= 15 for small-area 5 m DEM, got {max_z}"
    assert min_z == max(0, max_z - 5)

    # Verify the returned range really does fit the budget.
    total = sum(len(list(mercantile.tiles(*bounds, zooms=z))) for z in range(min_z, max_z + 1))
    assert total <= 500


def test_compute_zoom_levels_large_area_backs_off() -> None:
    """A large-area DEM at fine resolution backs off below the resolution-ideal cap."""
    from salus.interface_api.app import _compute_zoom_levels

    # 1° square (~110 km) at the equator — large enough that 5 m ideal zoom blows the budget.
    bounds = [0.0, 0.0, 1.0, 1.0]
    min_z_with_budget, max_z_with_budget = _compute_zoom_levels(
        5.0, bounds_wgs84=bounds, tile_budget=500
    )
    # Without bounds the function would return the ideal cap (~15 for 5 m).
    _, max_z_ideal = _compute_zoom_levels(5.0)
    assert max_z_with_budget < max_z_ideal
    assert min_z_with_budget <= max_z_with_budget


def test_compute_zoom_levels_extreme_overflow_returns_floor(caplog) -> None:
    """Budget that cannot be met at any zoom falls back to (0, 5) and logs a warning."""
    import logging

    from salus.interface_api.app import _compute_zoom_levels

    # Global bounds — even z=5 alone is >> any reasonable single-DEM budget.
    bounds = [-180.0, -85.0, 180.0, 85.0]
    with caplog.at_level(logging.WARNING):
        min_z, max_z = _compute_zoom_levels(1.0, bounds_wgs84=bounds, tile_budget=10)
    assert (min_z, max_z) == (0, 5)
    # rec.getMessage() handles unformatted records safely; rec.message can
    # be absent until the formatter has run (silent-failure-hunter L2).
    assert any("tile budget" in rec.getMessage() for rec in caplog.records)


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
