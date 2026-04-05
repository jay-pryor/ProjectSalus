"""
Slice 10–11 demo — Configuration Comparison and Effector Coverage.

Demonstrates the simulation modules added in Slices 10 and 11 on the shared
1.5 km × 1.5 km synthetic terrain used in the Slice 7–9 demo.

  S10 — Configuration Comparison (A vs B)
       Config A: Manual corner deployment — 3 sensors in three site corners.
       Config B: Greedy-optimised deployment — same 3 sensors placed by the
                 S9 optimiser.
       Produces:
         delta.png             — cell-level coverage delta (green=B-gains, red=A-only)
         side_by_side.png      — A and B coverage panels side by side
         comparison.png        — grouped per-zone bar chart
         statistics.png        — scalar metrics table

  S11 — Effector Coverage and Detection-Without-Engagement Gap Map
       3 × EOS Slinger effectors deployed around the protected asset
       (same positions as the S8 demo).
       Produces:
         effector_coverage.png       — teal engagement zone overlay
         detection_gap.png           — amber = detected but cannot engage

Run from the repository root:
    python demo/08_slice1011/generate_s1011_demo.py

All outputs are saved to demo/08_slice1011/.
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

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from salus.engine.comparison import (
    ConfigurationResult,
    compare_configs,
)
from salus.engine.coverage import (
    compute_composite_coverage,
    compute_coverage_stats,
    compute_gaps,
    compute_layer_coverage,
)
from salus.engine.effector_coverage import compute_effector_layer_coverage
from salus.engine.placement import (
    PlacementWeights,
    generate_candidate_positions,
    greedy_place_sensors,
)
from salus.ingest.sensors import load_effectors, load_sensors
from salus.ingest.terrain import load_dem
from salus.models.scenario import EffectorPlacement, SensorPlacement
from salus.report.charts import (
    render_comparison_statistics_table,
    render_coverage_comparison_chart,
)
from salus.report.maps import (
    render_delta_map,
    render_detection_without_engagement_map,
    render_effector_coverage_map,
    render_side_by_side_coverage_maps,
)

# ---------------------------------------------------------------------------
# Site geometry — identical to Slice 7–9 demo
# ---------------------------------------------------------------------------
ROWS, COLS = 300, 300
RESOLUTION = 5.0  # 5 m/cell → 1 500 m × 1 500 m site
ORIGIN_X, ORIGIN_Y = 500_000.0, 6_100_000.0
EPSG = 28354  # MGA Zone 54

EXTENT_E = ORIGIN_X + COLS * RESOLUTION  # 501 500
EXTENT_N = ORIGIN_Y + ROWS * RESOLUTION  # 6 101 500
PROTECTED = (
    ORIGIN_X + COLS * RESOLUTION * 0.5,
    ORIGIN_Y + ROWS * RESOLUTION * 0.5,
)

OUT_DIR = Path(__file__).parent
DEM_PATH = OUT_DIR / "demo_terrain.tif"

REPO_ROOT = Path(__file__).parent.parent.parent
SENSOR_DIR = REPO_ROOT / "src" / "salus" / "data" / "sensors"
EFFECTOR_DIR = REPO_ROOT / "src" / "salus" / "data" / "effectors"

# Cost estimates for S10 comparison (USD).
COST_CONFIG_A = 420_000.0   # manual deployment — no planning overhead removed
COST_CONFIG_B = 480_000.0   # +$60 K for optimisation consultancy


# ---------------------------------------------------------------------------
# Terrain helpers
# ---------------------------------------------------------------------------


def _make_terrain() -> np.ndarray:
    """300 × 300 DEM with a SW–NE ridge and NE hillock."""
    dem = np.full((ROWS, COLS), 100.0, dtype=np.float64)
    for r in range(ROWS):
        for c in range(COLS):
            dist = abs(r + c - 270) / np.sqrt(2)
            if dist < 40.0:
                dem[r, c] += 120.0 * (1.0 - dist / 40.0)
    cy, cx = 60, 220
    for r in range(ROWS):
        for c in range(COLS):
            d = np.sqrt((r - cy) ** 2 + (c - cx) ** 2)
            if d < 50:
                dem[r, c] += 60.0 * (1.0 - d / 50.0)
    return dem


def _write_dem(dem: np.ndarray) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(ORIGIN_X, ORIGIN_Y, EXTENT_E, EXTENT_N, COLS, ROWS)
    with rasterio.open(
        DEM_PATH,
        "w",
        driver="GTiff",
        height=ROWS,
        width=COLS,
        count=1,
        dtype="float64",
        crs=CRS.from_epsg(EPSG),
        transform=transform,
    ) as dst:
        dst.write(dem, 1)


# ---------------------------------------------------------------------------
# Build a ConfigurationResult from a list of SensorPlacements
# ---------------------------------------------------------------------------


def _build_config_result(
    site,
    sensor_defs: dict,
    placements: list[SensorPlacement],
    label: str,
    cost: float,
) -> tuple[ConfigurationResult, list[tuple[float, float]]]:
    """Run coverage pipeline and wrap in ConfigurationResult."""
    by_type: dict = {}
    positions: list[tuple[float, float]] = []
    for sp in placements:
        sd = sensor_defs[sp.sensor_name]
        by_type.setdefault(sd.type, []).append((sd, sp))
        positions.append((sp.position_x, sp.position_y))

    layer_coverages = compute_layer_coverage(site, by_type)
    composite = compute_composite_coverage(layer_coverages)
    gaps = compute_gaps(composite, composite)  # no bitmask — full site
    stats = compute_coverage_stats(site, layer_coverages, composite, gaps, site.zones)

    return (
        ConfigurationResult(
            label=label,
            composite=composite,
            layer_coverages=layer_coverages,
            stats=stats,
            cost_estimate=cost,
        ),
        positions,
    )


# ---------------------------------------------------------------------------
# S10 — Configuration Comparison
# ---------------------------------------------------------------------------


def _run_s10(site, sensor_defs: dict) -> None:
    print("\n" + "=" * 60)
    print("S10 — Configuration Comparison (A vs B)")
    print("=" * 60)

    margin = 75.0

    # Config A: three corner placements (manual)
    placements_a = [
        SensorPlacement(
            sensor_name="HENSOLDT Spexer 500",
            position_x=ORIGIN_X + margin,
            position_y=ORIGIN_Y + margin,
            bearing_deg=0.0,
        ),
        SensorPlacement(
            sensor_name="Echodyne EchoGuard",
            position_x=EXTENT_E - margin,
            position_y=EXTENT_N - margin,
            bearing_deg=0.0,
        ),
        SensorPlacement(
            sensor_name="DroneShield RfOne Mk2",
            position_x=ORIGIN_X + margin,
            position_y=EXTENT_N - margin,
            bearing_deg=0.0,
        ),
    ]

    # Config B: greedy-optimised placements
    sensors_to_place = [
        sensor_defs["HENSOLDT Spexer 500"],
        sensor_defs["Echodyne EchoGuard"],
        sensor_defs["DroneShield RfOne Mk2"],
    ]
    candidates = generate_candidate_positions(
        site, boundary=None, step_m=150.0, exclusion_zones=[]
    )
    weights = PlacementWeights(
        critical_asset=4.0, inner=2.5, perimeter=1.0, unzoned=1.0
    )
    placements_b = greedy_place_sensors(site, sensors_to_place, candidates, weights=weights)

    print(f"\n  Config A (manual corner deployment):")
    for sp in placements_a:
        print(f"    {sp.sensor_name:35s}  ({sp.position_x:.0f}, {sp.position_y:.0f})")

    print(f"\n  Config B (greedy-optimised):")
    for sp in placements_b:
        print(f"    {sp.sensor_name:35s}  ({sp.position_x:.0f}, {sp.position_y:.0f})")

    # Build ConfigurationResults
    cfg_a, pos_a = _build_config_result(
        site, sensor_defs, placements_a, "Config A — Manual", COST_CONFIG_A
    )
    cfg_b, pos_b = _build_config_result(
        site, sensor_defs, placements_b, "Config B — Optimised", COST_CONFIG_B
    )

    print(f"\n  Coverage summary:")
    print(f"    Config A: {cfg_a.stats.total_coverage_pct:.1f}%  (${COST_CONFIG_A:,.0f})")
    print(f"    Config B: {cfg_b.stats.total_coverage_pct:.1f}%  (${COST_CONFIG_B:,.0f})")

    # Compare
    comparison = compare_configs(cfg_a, cfg_b)
    delta = comparison.coverage_delta_pct
    cost_d = comparison.cost_delta

    print(f"\n  Comparison result:")
    print(f"    Coverage delta:  {delta:+.1f}%")
    if cost_d is not None:
        print(f"    Cost delta:      ${cost_d:+,.0f}")

    # Cell breakdown
    n = comparison.delta_grid.size
    n_both = int((comparison.delta_grid == 1).sum())
    n_a_only = int((comparison.delta_grid == 2).sum())
    n_b_only = int((comparison.delta_grid == 3).sum())
    print(f"    Both covered:    {n_both:>6}  ({n_both/n*100:.1f}%)")
    print(f"    A-only cells:    {n_a_only:>6}  ({n_a_only/n*100:.1f}%)  ← gaps B closed")
    print(f"    B-only cells:    {n_b_only:>6}  ({n_b_only/n*100:.1f}%)  ← B-only gains")

    # Render outputs
    print("\n  Rendering comparison outputs…")

    render_delta_map(
        site,
        comparison,
        OUT_DIR / "delta.png",
        title="Coverage Delta — Config A vs Config B",
        sensor_positions_a=pos_a,
        sensor_positions_b=pos_b,
    )
    print("    → delta.png")

    render_side_by_side_coverage_maps(
        site,
        comparison,
        OUT_DIR / "side_by_side.png",
        title="Coverage Comparison — Config A (left) vs Config B (right)",
        sensor_positions_a=pos_a,
        sensor_positions_b=pos_b,
    )
    print("    → side_by_side.png")

    render_coverage_comparison_chart(
        comparison,
        OUT_DIR / "comparison.png",
        title="Per-Zone Coverage — Config A vs Config B",
    )
    print("    → comparison.png")

    render_comparison_statistics_table(
        comparison,
        OUT_DIR / "statistics.png",
        title="Configuration Comparison — Scalar Metrics",
    )
    print("    → statistics.png")


# ---------------------------------------------------------------------------
# S11 — Effector Coverage + Detection-Without-Engagement
# ---------------------------------------------------------------------------


def _run_s11(site, sensor_defs: dict, effector_defs: dict) -> None:
    print("\n" + "=" * 60)
    print("S11 — Effector Coverage and Detection-Without-Engagement Map")
    print("=" * 60)

    # Sensor deployment: greedy-optimised (Config B from S10)
    sensors_to_place = [
        sensor_defs["HENSOLDT Spexer 500"],
        sensor_defs["Echodyne EchoGuard"],
        sensor_defs["DroneShield RfOne Mk2"],
    ]
    candidates = generate_candidate_positions(
        site, boundary=None, step_m=150.0, exclusion_zones=[]
    )
    weights = PlacementWeights(
        critical_asset=4.0, inner=2.5, perimeter=1.0, unzoned=1.0
    )
    sensor_placements = greedy_place_sensors(
        site, sensors_to_place, candidates, weights=weights
    )

    by_type: dict = {}
    sensor_positions: list[tuple[float, float]] = []
    for sp in sensor_placements:
        sd = sensor_defs[sp.sensor_name]
        by_type.setdefault(sd.type, []).append((sd, sp))
        sensor_positions.append((sp.position_x, sp.position_y))

    layer_coverages = compute_layer_coverage(site, by_type)
    sensor_composite = compute_composite_coverage(layer_coverages)
    sensor_pct = sensor_composite.sum() / sensor_composite.size * 100

    # 3 × EOS Slinger deployed around the protected asset at ~350 m range
    slinger = effector_defs["EOS Slinger"]
    effector_placements = [
        EffectorPlacement(
            effector_name="EOS Slinger",
            position_x=PROTECTED[0],
            position_y=PROTECTED[1] - 350.0,   # South
            bearing_deg=0.0,
            height_override_m=5.0,
        ),
        EffectorPlacement(
            effector_name="EOS Slinger",
            position_x=PROTECTED[0] - 303.0,   # West-NW
            position_y=PROTECTED[1] + 175.0,
            bearing_deg=0.0,
            height_override_m=5.0,
        ),
        EffectorPlacement(
            effector_name="EOS Slinger",
            position_x=PROTECTED[0] + 303.0,   # East-NE
            position_y=PROTECTED[1] + 175.0,
            bearing_deg=0.0,
            height_override_m=5.0,
        ),
    ]
    effector_pairs = [(slinger, ep) for ep in effector_placements]
    effector_positions = [(ep.position_x, ep.position_y) for ep in effector_placements]

    effector_coverage = compute_effector_layer_coverage(site, effector_pairs)
    effector_pct = effector_coverage.sum() / effector_coverage.size * 100

    # Gap analysis
    detected_not_engaged = sensor_composite & ~effector_coverage
    gap_pct = detected_not_engaged.sum() / sensor_composite.size * 100
    covered_both_pct = (sensor_composite & effector_coverage).sum() / sensor_composite.size * 100

    print(f"\n  Sensor composite coverage: {sensor_pct:.1f}%")
    print(f"  Effector coverage:         {effector_pct:.1f}%")
    print(f"  Both covered (detect+engage): {covered_both_pct:.1f}%")
    print(f"  Detection-without-engagement gap: {gap_pct:.1f}%  ← amber cells")

    print("\n  Rendering effector coverage outputs…")

    render_effector_coverage_map(
        site,
        effector_coverage,
        OUT_DIR / "effector_coverage.png",
        title=f"Effector Engagement Zone — {slinger.name} × 3",
        effector_positions=effector_positions,
    )
    print("    → effector_coverage.png")

    render_detection_without_engagement_map(
        site,
        sensor_composite,
        effector_coverage,
        OUT_DIR / "detection_gap.png",
        title="Detection-Without-Engagement Gap Map",
        sensor_positions=sensor_positions,
        effector_positions=effector_positions,
    )
    print("    → detection_gap.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== Project Salus — Slices 10 & 11 Demo ===\n")

    # Build terrain
    print("Building synthetic 1.5 km × 1.5 km terrain…")
    dem = _make_terrain()
    _write_dem(dem)
    site = load_dem(DEM_PATH)
    print(f"  {site.rows}×{site.cols} cells at {site.resolution:.0f} m/cell")
    print(f"  Elevation range: {site.dem.min():.0f}–{site.dem.max():.0f} m")

    # Load definitions
    sensor_defs = {s.name: s for s in load_sensors(SENSOR_DIR)}
    effector_defs = {e.name: e for e in load_effectors(EFFECTOR_DIR)}
    print(f"  Loaded {len(sensor_defs)} sensor defs, {len(effector_defs)} effector defs")

    _run_s10(site, sensor_defs)
    _run_s11(site, sensor_defs, effector_defs)

    print(f"\nAll outputs saved to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
