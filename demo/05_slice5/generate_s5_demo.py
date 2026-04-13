"""
Slice 5 demo — multi-sensor coverage analysis.

Creates a synthetic 1.5 km × 1.5 km terrain with a diagonal ridge, places four
sensors (Radar × 2, RF × 1, Acoustic × 1), and runs the full Slice 5 pipeline:
  - per-layer coverage unions
  - composite coverage
  - gap analysis
  - coverage statistics
  - redundancy map

Saves all map PNGs to demo/05_slice5/.
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

# Make sure the package is importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from salus.engine.coverage import (
    build_gap_analysis,
    compute_composite_coverage,
    compute_coverage_stats,
    compute_gaps,
    compute_layer_coverage,
    boundary_mask,
)
from salus.ingest.sensors import load_sensors
from salus.ingest.terrain import load_dem
from salus.models.scenario import SensorPlacement
from salus.report.maps import (
    render_composite_coverage_map,
    render_gap_map,
    render_layer_coverage_maps,
    render_redundancy_map,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROWS, COLS = 300, 300       # 300 × 300 cells
RESOLUTION = 5.0            # 5 m per cell → 1 500 m × 1 500 m
ORIGIN_X, ORIGIN_Y = 500000.0, 6100000.0
EPSG = 28354                # MGA Zone 54

OUT_DIR = Path(__file__).parent / "05_slice5"
DEM_PATH = OUT_DIR / "demo_terrain.tif"
SENSOR_DIR = Path(__file__).parent.parent / "src" / "salus" / "data" / "sensors"


def _make_terrain() -> np.ndarray:
    """Build a 300×300 DEM with a SW-NE diagonal ridge."""
    dem = np.full((ROWS, COLS), 100.0, dtype=np.float64)
    # Diagonal ridge from (row=270,col=0) to (row=0,col=270) — peak 220 m
    for r in range(ROWS):
        for c in range(COLS):
            # Distance from the ridge line y = -x + 270 (normalised coords)
            dist = abs(r + c - 270) / np.sqrt(2)
            ridge_width = 40.0
            if dist < ridge_width:
                peak_boost = 120.0 * (1.0 - dist / ridge_width)
                dem[r, c] += peak_boost
    # Add a gentle hill in the NE quadrant
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
    print("=== Salus Slice 5 Demo ===\n")

    # ---- Build terrain ----
    print("Building synthetic 1.5 km × 1.5 km terrain with diagonal ridge…")
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
    # Four sensors: two Radar (LOS), one RF (non-LOS), one Acoustic (non-LOS)
    # Placed at SW, NW, NE and centre to show coverage asymmetry around the ridge.
    extent_w = ORIGIN_X + COLS * RESOLUTION
    extent_n = ORIGIN_Y + ROWS * RESOLUTION
    cx = ORIGIN_X + COLS * RESOLUTION * 0.5
    cy = ORIGIN_Y + ROWS * RESOLUTION * 0.5

    placements = [
        # HENSOLDT Spexer 500 — Radar 3 km, SW corner
        ("HENSOLDT Spexer 500", ORIGIN_X + 75, ORIGIN_Y + 75),
        # Echodyne EchoGuard — Radar 900 m, NE corner
        ("Echodyne EchoGuard", extent_w - 150, extent_n - 150),
        # DroneShield RfOne Mk2 — RF 8 km, NW corner
        ("DroneShield RfOne Mk2", ORIGIN_X + 150, extent_n - 150),
        # DroneShield DroneSentinel — Acoustic 300 m, centre
        ("DroneShield DroneSentinel", cx, cy),
    ]

    from salus.models.sensor import SensorType

    placements_by_type: dict = {}
    sensor_positions = []

    for name, px, py in placements:
        if name not in sensor_defs:
            print(f"  WARNING: sensor '{name}' not found — skipping")
            continue
        sd = sensor_defs[name]
        sp = SensorPlacement(sensor_name=name, position_x=px, position_y=py, bearing_deg=0.0)
        stype = sd.type
        placements_by_type.setdefault(stype, []).append((sd, sp))
        sensor_positions.append((px, py))
        print(f"  Placed [{sd.type.value}] {name} at ({px:.0f}, {py:.0f})")

    # ---- Run coverage pipeline ----
    print("\nComputing per-layer coverage unions…")
    layer_coverages = compute_layer_coverage(site, placements_by_type)
    for stype, arr in layer_coverages.items():
        pct = arr.sum() / arr.size * 100
        print(f"  [{stype.value}] layer: {pct:.1f}% covered")

    print("Computing composite coverage…")
    composite = compute_composite_coverage(layer_coverages)
    comp_pct = composite.sum() / composite.size * 100
    print(f"  Composite: {comp_pct:.1f}% covered")

    # Full-DEM boundary mask (no boundary GeoJSON in this demo)
    bitmask = np.ones((site.rows, site.cols), dtype=bool)
    gaps = compute_gaps(composite, bitmask)

    stats = compute_coverage_stats(site, layer_coverages, composite, gaps, site.zones)

    print("\n--- Coverage Summary ---")
    print(f"  Total coverage:          {stats.total_coverage_pct:.1f}%")
    print(f"  Gap area:                {stats.gap_area_m2:,.0f} m²")
    print(f"  Largest contiguous gap:  {stats.largest_contiguous_gap_m2:,.0f} m²")
    for stype, pct in stats.per_layer_coverage_pct.items():
        print(f"  [{stype.value}] layer:      {pct:.1f}%")

    # ---- Render maps ----
    print("\nRendering maps…")
    maps_dir = OUT_DIR / "maps"

    layer_paths = render_layer_coverage_maps(
        site, layer_coverages, maps_dir / "layers",
        title_prefix="Layer Coverage",
        sensor_positions=sensor_positions,
    )
    for st, p in layer_paths.items():
        print(f"  → {p.name}  ({st.value})")

    composite_path = maps_dir / "composite.png"
    render_composite_coverage_map(
        site, layer_coverages, composite_path,
        title=f"Composite Coverage — {stats.total_coverage_pct:.1f}% covered",
        sensor_positions=sensor_positions,
    )
    print(f"  → {composite_path.name}")

    gap_path = maps_dir / "gaps.png"
    render_gap_map(
        site, composite, gaps, gap_path,
        title=f"Coverage Gaps — {stats.gap_area_m2/1e6:.2f} km² uncovered",
        sensor_positions=sensor_positions,
    )
    print(f"  → {gap_path.name}")

    redundancy_path = maps_dir / "redundancy.png"
    render_redundancy_map(
        site, stats.redundancy_map, redundancy_path,
        title="Sensor Redundancy Map",
        sensor_positions=sensor_positions,
    )
    print(f"  → {redundancy_path.name}")

    print(f"\nAll demo outputs saved to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
