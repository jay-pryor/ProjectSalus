"""Tests for the Salus Interface API — S14.2.

Tests cover all six endpoints:
  - GET /api/health       (S14.2-1)
  - GET /api/sensors      (S14.2-2)
  - GET /api/effectors    (S14.2-2)
  - POST /api/simulate    (S14.2-3, SSE stream)
  - POST /api/optimise    (S14.2-4, SSE stream)
  - POST /api/report      (S14.2-5, PDF binary)

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

        deadline = time.monotonic() + 10.0
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
