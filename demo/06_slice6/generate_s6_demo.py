"""
Slice 6 demo — threat corridor analysis.

Creates a synthetic 1.5 km × 1.5 km terrain with a diagonal ridge, places four
sensors (Radar × 2, RF × 1, Acoustic × 1), runs the full Slice 5 coverage
pipeline, then runs the Slice 6 threat corridor analysis for all three bundled
threat profiles:

  - DJI Mavic 3 — Low Slow     (COTS rotary wing)
  - FPV Racing Drone — Fast Approach   (high-speed low-altitude)
  - Fixed-Wing ISR — High Altitude     (large autonomous ISR)

For each threat, produces:
  - corridor_<threat>_overlay.png   — approach corridors overlaid on coverage
  - corridor_<threat>_polar.png     — polar diagram of coverage by bearing

All outputs saved to demo/06_slice6/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

# Make package importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from salus.engine.coverage import (
    compute_composite_coverage,
    compute_layer_coverage,
)
from salus.engine.threat_corridor import find_worst_corridors
from salus.ingest.sensors import load_sensors, load_threats
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.report.maps import (
    render_corridor_overlay_map,
    render_corridor_polar_diagram,
    render_composite_coverage_map,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROWS, COLS = 300, 300       # 300 × 300 cells
RESOLUTION = 5.0            # 5 m per cell → 1 500 m × 1 500 m
ORIGIN_X, ORIGIN_Y = 500000.0, 6100000.0
EPSG = 28354                # MGA Zone 54

OUT_DIR = Path(__file__).parent
DEM_PATH = OUT_DIR / "demo_terrain.tif"
SENSOR_DIR = Path(__file__).parent.parent.parent / "src" / "salus" / "data" / "sensors"
THREAT_DIR = Path(__file__).parent.parent.parent / "src" / "salus" / "data" / "threats"

# Protected asset — centre of site
PROTECTED_POINT: tuple[float, float] = (
    ORIGIN_X + COLS * RESOLUTION * 0.5,
    ORIGIN_Y + ROWS * RESOLUTION * 0.5,
)


def _safe_filename(name: str) -> str:
    """Slugify a threat name for use in filenames."""
    return name.lower().replace(" ", "_").replace("—", "").replace("-", "_").strip("_")


def _make_terrain() -> np.ndarray:
    """Build a 300×300 DEM with a SW-NE diagonal ridge and a NE hillock."""
    dem = np.full((ROWS, COLS), 100.0, dtype=np.float64)
    for r in range(ROWS):
        for c in range(COLS):
            dist = abs(r + c - 270) / np.sqrt(2)
            ridge_width = 40.0
            if dist < ridge_width:
                dem[r, c] += 120.0 * (1.0 - dist / ridge_width)
    cy, cx = 60, 220
    for r in range(ROWS):
        for c in range(COLS):
            d = np.sqrt((r - cy) ** 2 + (c - cx) ** 2)
            if d < 50:
                dem[r, c] += 60.0 * (1.0 - d / 50.0)
    return dem


def _write_dem(dem: np.ndarray) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(
        ORIGIN_X, ORIGIN_Y,
        ORIGIN_X + COLS * RESOLUTION,
        ORIGIN_Y + ROWS * RESOLUTION,
        COLS, ROWS,
    )
    with rasterio.open(
        DEM_PATH, "w",
        driver="GTiff", height=ROWS, width=COLS,
        count=1, dtype="float64",
        crs=CRS.from_epsg(EPSG),
        transform=transform,
    ) as dst:
        dst.write(dem, 1)


def main() -> None:
    print("=== Salus Slice 6 Demo — Threat Corridor Analysis ===\n")

    # ---- Build terrain ----
    print("Building synthetic 1.5 km × 1.5 km terrain…")
    dem = _make_terrain()
    _write_dem(dem)
    print(f"  DEM saved: {DEM_PATH}")

    # ---- Load DEM ----
    site = load_dem(DEM_PATH)
    print(f"  Site: {site.rows}×{site.cols} cells at {site.resolution:.0f} m resolution")

    # ---- Load sensor definitions ----
    sensor_defs = {s.name: s for s in load_sensors(SENSOR_DIR)}
    print(f"  Loaded {len(sensor_defs)} sensor definitions")

    # ---- Define placements ----
    extent_w = ORIGIN_X + COLS * RESOLUTION
    extent_n = ORIGIN_Y + ROWS * RESOLUTION

    placement_specs = [
        ("HENSOLDT Spexer 500",       ORIGIN_X + 75,   ORIGIN_Y + 75),
        ("Echodyne EchoGuard",         extent_w - 150,  extent_n - 150),
        ("DroneShield RfOne Mk2",      ORIGIN_X + 150,  extent_n - 150),
        ("DroneShield DroneSentinel",  ORIGIN_X + COLS * RESOLUTION * 0.5,
                                       ORIGIN_Y + ROWS * RESOLUTION * 0.5),
    ]

    placements_by_type: dict = {}
    sensor_positions: list[tuple[float, float]] = []

    for name, px, py in placement_specs:
        if name not in sensor_defs:
            print(f"  WARNING: sensor '{name}' not found — skipping")
            continue
        sd = sensor_defs[name]
        sp = SensorPlacement(sensor_name=name, position_x=px, position_y=py, bearing_deg=0.0)
        placements_by_type.setdefault(sd.type, []).append((sd, sp))
        sensor_positions.append((px, py))
        print(f"  Placed [{sd.type.value}] {name} at ({px:.0f}, {py:.0f})")

    # ---- Coverage pipeline ----
    print("\nComputing coverage…")
    layer_coverages = compute_layer_coverage(site, placements_by_type)
    composite = compute_composite_coverage(layer_coverages)
    comp_pct = composite.sum() / composite.size * 100
    print(f"  Composite coverage: {comp_pct:.1f}%")

    # ---- Render composite for reference ----
    composite_path = OUT_DIR / "composite_coverage.png"
    render_composite_coverage_map(
        site, layer_coverages, composite_path,
        title=f"Composite Coverage — {comp_pct:.1f}% covered",
        sensor_positions=sensor_positions,
    )
    print(f"  → {composite_path.name}")

    # ---- Load threat profiles ----
    print(f"\nLoading threat profiles from {THREAT_DIR}…")
    threats = load_threats(THREAT_DIR)
    print(f"  Loaded {len(threats)} threat profile(s):")
    for t in threats:
        print(f"    • {t.name}  (alt {t.typical_altitude_m:.0f} m, "
              f"{t.max_speed_ms:.0f} m/s, evasion={t.evasion_capability})")

    # ---- Protected point ----
    print(f"\nProtected point: ({PROTECTED_POINT[0]:.0f}, {PROTECTED_POINT[1]:.0f})  "
          f"[site centre]")

    # ---- Corridor analysis per threat ----
    print("\nRunning threat corridor analysis…")
    for threat in threats:
        print(f"\n  ── {threat.name} ──")
        all_pairs = [pair for pairs in placements_by_type.values() for pair in pairs]
        results = find_worst_corridors(site, all_pairs, threat, PROTECTED_POINT)

        print(f"  {'Bearing':>8}  {'Coverage':>10}  {'First detect':>14}")
        print(f"  {'─' * 8}  {'─' * 10}  {'─' * 14}")
        for r in results[:5]:
            fd = (
                f"{r.first_detection_distance_m:.0f} m"
                if r.first_detection_distance_m is not None
                else "none"
            )
            print(f"  {r.corridor.bearing_deg:>7.1f}°  {r.coverage_pct:>9.1f}%  {fd:>14}")
        if len(results) > 5:
            print(f"  … {len(results) - 5} more corridors (worst shown first)")

        worst = results[0]
        best = results[-1]
        avg = sum(r.coverage_pct for r in results) / len(results)
        print(f"\n  Worst corridor: {worst.corridor.bearing_deg:.1f}°  "
              f"→ {worst.coverage_pct:.1f}% covered")
        print(f"  Best corridor:  {best.corridor.bearing_deg:.1f}°  "
              f"→ {best.coverage_pct:.1f}% covered")
        print(f"  Mean coverage across all {len(results)} bearings: {avg:.1f}%")

        safe = _safe_filename(threat.name)

        overlay_path = OUT_DIR / f"corridor_{safe}_overlay.png"
        render_corridor_overlay_map(
            site, composite, results, PROTECTED_POINT, overlay_path,
            title=f"Corridor Analysis — {threat.name}",
            sensor_positions=sensor_positions,
        )
        print(f"  → {overlay_path.name}")

        polar_path = OUT_DIR / f"corridor_{safe}_polar.png"
        render_corridor_polar_diagram(
            results, polar_path,
            title=f"Coverage by Bearing — {threat.name}",
        )
        print(f"  → {polar_path.name}")

    print(f"\nAll demo outputs saved to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
