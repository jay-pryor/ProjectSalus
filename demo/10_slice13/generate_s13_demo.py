"""
S13 PDF Report Demo — Professional PDF Report Generation.

Demonstrates the full S13 report pipeline on the compound defence site
(1.5 km × 1.5 km, three-sensor layered air-defence network):

  Pipeline A — Full simulation → PDF
  -----------------------------------
  Runs ingest → viewshed → coverage → PDF in a single command.
  Produces:  demo/10_slice13/compound_report.pdf

  Pipeline B — Simulate → save results → fast-render PDF
  -------------------------------------------------------
  First pass:  salus simulate (saves maps + stats as JSON)
  Second pass: salus report --results (skips re-simulation)
  Produces:  demo/10_slice13/results.json
             demo/10_slice13/compound_report_fast.pdf

  Python API path
  ---------------
  Calls assemble_report_data / render_pdf directly to show
  the public API without the CLI wrapper.
  Produces:  demo/10_slice13/compound_report_api.pdf

Run from the repository root:
    python demo/10_slice13/generate_s13_demo.py

All outputs are saved to demo/10_slice13/.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from salus.engine.coverage import (
    compute_composite_coverage,
    compute_coverage_stats,
    compute_gaps,
    compute_layer_coverage,
)
from salus.ingest.sensors import load_sensors
from salus.ingest.terrain import load_dem
from salus.models.scenario import ScenarioConfig, SensorPlacement
from salus.models.sensor import SensorType
from salus.report.pdf import SimulationResults, assemble_report_data, render_pdf

HERE = Path(__file__).parent
REPO = HERE.parent.parent
TERRAIN_PATH = HERE / ".." / "09_compound" / "compound_terrain.tif"
SCENARIO_PATH = HERE / "demo_scenario.yaml"
SENSOR_DIR = REPO / "src" / "salus" / "data" / "sensors"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hr(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print("─" * 60)


def _run(cmd: list[str], label: str) -> float:
    """Run a CLI command, stream output, return elapsed seconds."""
    # Prefer the installed 'salus' entry-point; fall back to python -m salus.cli
    if cmd[0] == "salus":
        import shutil
        if not shutil.which("salus"):
            cmd = [sys.executable, "-m", "salus.cli"] + cmd[1:]
    print(f"\n$ {' '.join(cmd)}\n")
    t0 = time.perf_counter()
    result = subprocess.run(cmd, cwd=str(REPO), capture_output=False)
    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        print(f"\n[ERROR] {label} exited {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)
    return elapsed


# ---------------------------------------------------------------------------
# Pipeline A — Full simulation → PDF via CLI
# ---------------------------------------------------------------------------


def pipeline_a() -> None:
    _hr("Pipeline A — salus report (full simulation)")

    output_pdf = str(HERE / "compound_report.pdf")
    elapsed = _run(
        [
            "salus", "report", str(SCENARIO_PATH),
            "--output", output_pdf,
            "--sensors", str(SENSOR_DIR),
        ],
        "salus report (full)",
    )

    pdf_path = Path(output_pdf)
    size_kb = pdf_path.stat().st_size / 1024
    print(f"\n✓  Generated: {pdf_path.name}  ({size_kb:.0f} KB)  in {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# Pipeline B — Simulate → save results → fast-render via CLI
# ---------------------------------------------------------------------------


def pipeline_b() -> None:
    _hr("Pipeline B — salus simulate --save-results, then salus report --results")

    sim_output = str(HERE / "sim_output")
    results_json = str(HERE / "results.json")
    fast_pdf = str(HERE / "compound_report_fast.pdf")

    # Step 1: simulate and save results
    print("Step 1: Run simulation and persist results JSON")
    t1 = _run(
        [
            "salus", "simulate", str(SCENARIO_PATH),
            "--output-dir", sim_output,
            "--sensors", str(SENSOR_DIR),
            "--save-results", results_json,
        ],
        "salus simulate --save-results",
    )
    print(f"\n✓  Simulation complete in {t1:.1f}s")
    print(f"   Results JSON: {Path(results_json).name}  "
          f"({Path(results_json).stat().st_size / 1024:.0f} KB)")

    # Step 2: render PDF from pre-computed results (skips viewshed/coverage)
    print("\nStep 2: Render PDF from pre-computed results (no re-simulation)")
    t2 = _run(
        [
            "salus", "report", str(SCENARIO_PATH),
            "--output", fast_pdf,
            "--sensors", str(SENSOR_DIR),
            "--results", results_json,
        ],
        "salus report --results",
    )
    fast_path = Path(fast_pdf)
    size_kb = fast_path.stat().st_size / 1024
    print(f"\n✓  Generated: {fast_path.name}  ({size_kb:.0f} KB)  in {t2:.1f}s")
    print(f"   (Simulation skipped — only DEM + template render required)")


# ---------------------------------------------------------------------------
# Pipeline C — Python API path (no CLI)
# ---------------------------------------------------------------------------


def pipeline_c() -> None:
    _hr("Pipeline C — Python API (assemble_report_data + render_pdf)")

    print("Loading terrain and sensors…")
    site = load_dem(str(TERRAIN_PATH))
    sensor_defs = load_sensors(SENSOR_DIR)
    sensor_map = {s.name: s for s in sensor_defs}

    # Build placements matching demo_scenario.yaml
    placements = [
        SensorPlacement(
            sensor_name="Anduril WISP",
            position_x=500750.0, position_y=6100750.0,
            bearing_deg=0.0, height_override_m=22.0,
        ),
        SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=500200.0, position_y=6101300.0,
            bearing_deg=135.0, height_override_m=5.0,
        ),
        SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=501200.0, position_y=6100200.0,
            bearing_deg=315.0, height_override_m=5.0,
        ),
    ]

    # Build placements_by_type (LOS-capable sensors only)
    placements_by_type: dict = {}
    for p in placements:
        s = sensor_map.get(p.sensor_name)
        if s is None or not s.requires_los:
            continue
        placements_by_type.setdefault(s.type, []).append((s, p))

    print("Running coverage pipeline…")
    t0 = time.perf_counter()
    layer_coverages = compute_layer_coverage(site, placements_by_type)
    composite = compute_composite_coverage(layer_coverages)
    bitmask = np.ones((site.rows, site.cols), dtype=bool)
    gaps = compute_gaps(composite, bitmask)
    stats = compute_coverage_stats(site, layer_coverages, composite, gaps, site.zones or [])
    elapsed_sim = time.perf_counter() - t0

    pct = stats.total_coverage_pct
    gap_km2 = stats.gap_area_m2 / 1e6
    print(f"  Coverage: {pct:.1f}%   Gap area: {gap_km2:.3f} km²  ({elapsed_sim:.1f}s)")

    # Build a minimal ScenarioConfig for metadata
    sc = ScenarioConfig(
        site_dem_path=str(TERRAIN_PATH),
        sensor_placements=placements,
    )

    sim_results = SimulationResults(
        site=site,
        scenario=sc,
        composite=composite,
        layer_coverages=layer_coverages,
        stats=stats,
        sensor_defs=sensor_defs,
        gaps=gaps,
    )

    print("Assembling report data (rendering maps to base64)…")
    t1 = time.perf_counter()
    report_data = assemble_report_data(sc, sim_results)
    elapsed_assemble = time.perf_counter() - t1
    print(f"  Executive summary: {len(report_data.executive_summary)} chars  ({elapsed_assemble:.1f}s)")

    print("Rendering PDF via WeasyPrint…")
    api_pdf = HERE / "compound_report_api.pdf"
    t2 = time.perf_counter()
    out = render_pdf(report_data, api_pdf)
    elapsed_render = time.perf_counter() - t2
    size_kb = out.stat().st_size / 1024
    print(f"\n✓  Generated: {out.name}  ({size_kb:.0f} KB)  in {elapsed_render:.1f}s")


# ---------------------------------------------------------------------------
# Summary panel
# ---------------------------------------------------------------------------


def print_summary() -> None:
    _hr("Summary")

    outputs = [
        HERE / "compound_report.pdf",
        HERE / "compound_report_fast.pdf",
        HERE / "compound_report_api.pdf",
        HERE / "results.json",
    ]

    for p in outputs:
        if p.exists():
            size_kb = p.stat().st_size / 1024
            tag = "PDF" if p.suffix == ".pdf" else "JSON"
            print(f"  [{tag}]  {p.name:<35}  {size_kb:>6.0f} KB")

    print()
    print("All three pathways produce equivalent PDF reports:")
    print("  A. salus report (full)     — end-to-end, one command")
    print("  B. salus report --results  — fast re-render from cached simulation")
    print("  C. Python API              — programmatic, no CLI dependency")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("=" * 60)
    print("  S13 — Professional PDF Report Demo")
    print("  Compound Defence Site — 1.5 km × 1.5 km")
    print("=" * 60)

    pipeline_a()
    pipeline_b()
    pipeline_c()
    print_summary()
