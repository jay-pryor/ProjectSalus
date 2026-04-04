"""
Slice 7–8–9 demo — Kill Chain, Saturation Analysis, and Sensor Placement.

Demonstrates the three simulation modules added in Slices 7, 8, and 9 on a
shared 1.5 km × 1.5 km synthetic terrain with a SW–NE diagonal ridge.

  S9 — Greedy Sensor Placement Optimisation
       Compares a naive manual deployment (sensors in three site corners) with
       the greedy optimiser's recommendation for the same sensor set.  Coverage
       improvement is printed and both maps are rendered.

  S7 — Kill Chain Timeline (D-T-I-D-E-A)
       Runs the kill-chain model against the worst 8 approach corridors for the
       DJI Mavic 3 threat (using the optimised sensor layout).  Produces a
       summary chart (worst / average / best corridors).

  S8 — Multi-Target Saturation Analysis
       Places three EOS Slinger kinetic effectors around the protected asset,
       then sweeps simultaneous-target count to find the saturation threshold,
       models the re-engagement timeline over a 60-second window, and shows
       per-effector utilisation at the saturation point.

Run from the repository root:
    python demo/07_slice789/generate_s789_demo.py

All outputs are saved to demo/07_slice789/.
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

# Make the salus package importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from salus.engine.coverage import compute_composite_coverage, compute_layer_coverage
from salus.engine.kill_chain import compute_all_kill_chains
from salus.engine.placement import (
    PlacementWeights,
    generate_candidate_positions,
    greedy_place_sensors,
)
from salus.engine.saturation import (
    compute_reengagement_timeline,
    find_saturation_threshold,
)
from salus.engine.threat_corridor import find_worst_corridors
from salus.ingest.sensors import load_effectors, load_sensors, load_threats
from salus.ingest.terrain import load_dem
from salus.models.saturation import (
    ApproachVector,
    PriorityRule,
    SaturationScenario,
    SaturationTarget,
)
from salus.models.scenario import (
    EffectorPlacement,
    KillChainConfig,
    SensorPlacement,
)
from salus.report.charts import (
    render_effector_utilisation_chart,
    render_engagement_timeline_chart,
    render_kill_chain_summary_chart,
    render_saturation_threshold_chart,
)
from salus.report.maps import render_composite_coverage_map

# ---------------------------------------------------------------------------
# Site geometry (shared across all slices)
# ---------------------------------------------------------------------------
ROWS, COLS = 300, 300
RESOLUTION = 5.0  # 5 m/cell → 1 500 m × 1 500 m site
ORIGIN_X, ORIGIN_Y = 500_000.0, 6_100_000.0
EPSG = 28354  # MGA Zone 54

EXTENT_E = ORIGIN_X + COLS * RESOLUTION  # 501 500
EXTENT_N = ORIGIN_Y + ROWS * RESOLUTION  # 6 101 500
PROTECTED = (
    ORIGIN_X + COLS * RESOLUTION * 0.5,  # 500 750
    ORIGIN_Y + ROWS * RESOLUTION * 0.5,  # 6 100 750
)

OUT_DIR = Path(__file__).parent
DEM_PATH = OUT_DIR / "demo_terrain.tif"

REPO_ROOT = Path(__file__).parent.parent.parent
SENSOR_DIR = REPO_ROOT / "src" / "salus" / "data" / "sensors"
EFFECTOR_DIR = REPO_ROOT / "src" / "salus" / "data" / "effectors"
THREAT_DIR = REPO_ROOT / "src" / "salus" / "data" / "threats"


# ---------------------------------------------------------------------------
# Terrain helpers
# ---------------------------------------------------------------------------


def _make_terrain() -> np.ndarray:
    """300 × 300 DEM: flat plateau at 100 m with a SW–NE ridge and NE hillock."""
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
    transform = from_bounds(
        ORIGIN_X, ORIGIN_Y, EXTENT_E, EXTENT_N, COLS, ROWS
    )
    with rasterio.open(
        DEM_PATH, "w",
        driver="GTiff", height=ROWS, width=COLS,
        count=1, dtype="float64",
        crs=CRS.from_epsg(EPSG),
        transform=transform,
    ) as dst:
        dst.write(dem, 1)


# ---------------------------------------------------------------------------
# S9 — Sensor Placement Optimisation
# ---------------------------------------------------------------------------


def _run_s9(site, sensor_defs: dict) -> tuple[list, list, list]:
    """Compare manual corner placements vs greedy-optimised placements.

    Returns (manual_positions, optimised_positions, sensor_objects_to_place).
    """
    print("\n" + "=" * 60)
    print("S9 — Sensor Placement Optimisation")
    print("=" * 60)

    sensors_to_place = [
        sensor_defs["HENSOLDT Spexer 500"],
        sensor_defs["Echodyne EchoGuard"],
        sensor_defs["DroneShield RfOne Mk2"],
    ]
    margin = 75.0  # metres inside site boundary

    # ---- Manual placements (three corners of site) ----
    manual_placements = [
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
    manual_by_type: dict = {}
    manual_positions: list[tuple[float, float]] = []
    for sp in manual_placements:
        sd = sensor_defs[sp.sensor_name]
        manual_by_type.setdefault(sd.type, []).append((sd, sp))
        manual_positions.append((sp.position_x, sp.position_y))

    manual_layer = compute_layer_coverage(site, manual_by_type)
    manual_composite = compute_composite_coverage(manual_layer)
    manual_pct = manual_composite.sum() / manual_composite.size * 100

    render_composite_coverage_map(
        site, manual_layer,
        OUT_DIR / "coverage_manual.png",
        title=f"Manual Placement — {manual_pct:.1f}% coverage",
        sensor_positions=manual_positions,
    )
    print(f"  Manual placement coverage:    {manual_pct:.1f}%")
    print(f"  → coverage_manual.png")

    # ---- Greedy-optimised placements ----
    candidates = generate_candidate_positions(
        site, boundary=None, step_m=150.0, exclusion_zones=[]
    )
    print(f"\n  Generated {len(candidates)} candidate positions (step = 150 m)")

    weights = PlacementWeights(
        critical_asset=4.0,
        inner=2.5,
        perimeter=1.0,
        unzoned=1.0,
    )
    optimised_placements = greedy_place_sensors(
        site, sensors_to_place, candidates, weights=weights
    )
    opt_by_type: dict = {}
    opt_positions: list[tuple[float, float]] = []
    for sp in optimised_placements:
        sd = sensor_defs[sp.sensor_name]
        opt_by_type.setdefault(sd.type, []).append((sd, sp))
        opt_positions.append((sp.position_x, sp.position_y))

    opt_layer = compute_layer_coverage(site, opt_by_type)
    opt_composite = compute_composite_coverage(opt_layer)
    opt_pct = opt_composite.sum() / opt_composite.size * 100

    render_composite_coverage_map(
        site, opt_layer,
        OUT_DIR / "coverage_optimised.png",
        title=f"Greedy Optimiser — {opt_pct:.1f}% coverage (+{opt_pct - manual_pct:.1f}%)",
        sensor_positions=opt_positions,
    )
    print(f"  Optimised placement coverage: {opt_pct:.1f}% (+{opt_pct - manual_pct:.1f}%)")
    print(f"  Optimised positions:")
    for sp in optimised_placements:
        print(f"    {sp.sensor_name:35s}  ({sp.position_x:.0f}, {sp.position_y:.0f})")
    print(f"  → coverage_optimised.png")

    return opt_positions, optimised_placements, sensors_to_place


# ---------------------------------------------------------------------------
# S7 — Kill Chain Timeline
# ---------------------------------------------------------------------------


def _run_s7(site, optimised_placements: list, sensor_defs: dict, effector_defs: dict) -> None:
    """Run kill-chain timeline analysis on the worst corridors."""
    print("\n" + "=" * 60)
    print("S7 — Kill Chain Timeline (D-T-I-D-E-A)")
    print("=" * 60)

    # Build placements_by_type for corridor analysis.
    by_type: dict = {}
    opt_positions: list[tuple[float, float]] = []
    for sp in optimised_placements:
        sd = sensor_defs[sp.sensor_name]
        by_type.setdefault(sd.type, []).append((sd, sp))
        opt_positions.append((sp.position_x, sp.position_y))

    threats = load_threats(THREAT_DIR)
    dji = next((t for t in threats if "Mavic" in t.name), threats[0])
    all_pairs = [pair for pairs in by_type.values() for pair in pairs]

    print(f"\n  Threat: {dji.name}  ({dji.max_speed_ms:.0f} m/s, alt={dji.typical_altitude_m:.0f} m)")
    corridor_results = find_worst_corridors(site, all_pairs, dji, PROTECTED)
    print(f"  Corridors evaluated: {len(corridor_results)} bearings")

    # D-T-I-D-E-A phase durations (representative operator times).
    kc_config = KillChainConfig(
        track_time_s=3.0,
        identify_time_s=5.0,
        decide_time_s=4.0,
        assess_time_s=3.0,
    )
    slinger = effector_defs["EOS Slinger"]
    print(f"  Effector: {slinger.name}  (react={slinger.reaction_time_s}s)")

    kc_results = compute_all_kill_chains(
        corridor_results, kc_config, [slinger], dji.max_speed_ms
    )

    feasible = sum(1 for r in kc_results if r.engagement_feasible)
    second = sum(1 for r in kc_results if r.second_engagement_possible)
    margins = [r.margin_s for r in kc_results if r.engagement_feasible]
    print(f"\n  Kill chain results:")
    print(f"    Feasible engagements:     {feasible}/{len(kc_results)}")
    print(f"    Second engagement window: {second}/{len(kc_results)}")
    if margins:
        print(f"    Margin range:             {min(margins):.1f}s – {max(margins):.1f}s")

    # Summary chart (worst / average / best).
    render_kill_chain_summary_chart(
        corridor_results,
        kc_results,
        kc_config,
        slinger,
        OUT_DIR / "killchain_summary.png",
        title=f"Kill Chain Summary — {dji.name} vs {slinger.name}",
    )
    print(f"  → killchain_summary.png")


# ---------------------------------------------------------------------------
# S8 — Saturation Analysis
# ---------------------------------------------------------------------------


def _run_s8(site, effector_defs: dict) -> None:
    """Run multi-target saturation analysis with three EOS Slingers."""
    print("\n" + "=" * 60)
    print("S8 — Multi-Target Saturation Analysis")
    print("=" * 60)

    slinger = effector_defs["EOS Slinger"]

    # Three EOS Slingers deployed around the protected asset.
    # Placed ~350 m from asset centre, roughly at 120° intervals.
    eff_placements = [
        EffectorPlacement(
            effector_name="EOS Slinger",
            position_x=PROTECTED[0],
            position_y=PROTECTED[1] - 350.0,  # South
            bearing_deg=0.0,
            height_override_m=5.0,
        ),
        EffectorPlacement(
            effector_name="EOS Slinger",
            position_x=PROTECTED[0] - 303.0,  # West-NW
            position_y=PROTECTED[1] + 175.0,
            bearing_deg=0.0,
            height_override_m=5.0,
        ),
        EffectorPlacement(
            effector_name="EOS Slinger",
            position_x=PROTECTED[0] + 303.0,  # East-NE
            position_y=PROTECTED[1] + 175.0,
            bearing_deg=0.0,
            height_override_m=5.0,
        ),
    ]
    effectors = [slinger]

    print(f"\n  Effector: {slinger.name} × {len(eff_placements)}")
    print(f"  Simultaneous engagement capacity (each): {slinger.simultaneous_engagements}")
    print(f"  Total capacity: {slinger.simultaneous_engagements * len(eff_placements)}")

    threats = load_threats(THREAT_DIR)
    dji = next((t for t in threats if "Mavic" in t.name), threats[0])
    print(f"  Sweep threat: {dji.name}")

    # ---- Saturation threshold sweep ----
    sat_result = find_saturation_threshold(
        effectors, eff_placements, site, PROTECTED, dji, max_targets=10
    )
    cap = sat_result.simultaneous_engagement_capacity
    thresh = sat_result.saturation_threshold_n
    print(f"\n  Saturation threshold sweep:")
    print(f"    Simultaneous engagement capacity: {cap}")
    print(f"    Saturation threshold:             {thresh} targets")
    if thresh <= 10:
        print(f"    Unengaged at threshold:           {sat_result.unengaged_count_at_threshold}")
    else:
        print(f"    Threshold not reached within N=10")

    # Build chart data — include threshold bar when it was reached.
    threshold_never_reached = thresh > 10
    if threshold_never_reached:
        max_n = min(max(cap, 1), 10)
    else:
        max_n = min(thresh, 10)  # always include the saturation bar
    threshold_data: dict[int, int] = {n: 0 for n in range(1, max_n + 1)}
    if not threshold_never_reached:
        threshold_data[thresh] = sat_result.unengaged_count_at_threshold

    chart_title = (
        f"Saturation Threshold — {dji.name} (not reached within N={max_n})"
        if threshold_never_reached
        else f"Saturation Threshold — {dji.name}"
    )
    threshold_line = max_n + 1 if threshold_never_reached else thresh

    render_saturation_threshold_chart(
        threshold_data, threshold_line,
        OUT_DIR / "saturation_threshold.png",
        title=chart_title,
    )
    print(f"  → saturation_threshold.png")

    # ---- Per-effector utilisation ----
    if sat_result.per_effector_utilisation:
        render_effector_utilisation_chart(
            sat_result,
            OUT_DIR / "saturation_utilisation.png",
            title=f"Effector Utilisation at Saturation — {dji.name}",
        )
        print(f"  → saturation_utilisation.png")
        for name, util in sat_result.per_effector_utilisation.items():
            print(f"    {name}: {util * 100:.0f}% utilisation")

    # ---- Re-engagement timeline ----
    # Scenario: two simultaneous threats from east and west.
    scenario = SaturationScenario(
        targets=[
            SaturationTarget(
                approach_vector=ApproachVector(bearing_deg=90.0, distance_m=500.0),
                altitude_m=dji.typical_altitude_m,
                speed_ms=dji.max_speed_ms,
                threat_profile_ref=dji.name,
            ),
            SaturationTarget(
                approach_vector=ApproachVector(bearing_deg=270.0, distance_m=500.0),
                altitude_m=dji.typical_altitude_m,
                speed_ms=dji.max_speed_ms,
                threat_profile_ref=dji.name,
            ),
        ],
        priority_rule=PriorityRule.CLOSEST_TO_ASSET,
    )

    reen_result = compute_reengagement_timeline(
        effectors, eff_placements, site, PROTECTED, scenario, window_s=60.0
    )
    print(f"\n  Re-engagement timeline (60 s window):")
    print(f"    Total engagements possible: {reen_result.total_engagements_possible}")
    print(f"    Cycle time:                 {reen_result.reengagement_cycle_time_s:.2f} s")
    for name, count in reen_result.per_effector_engagements.items():
        print(f"    {name}: {count} engagement(s)")

    effector_timing = {slinger.name: (slinger.reaction_time_s, slinger.reload_time_s)}
    render_engagement_timeline_chart(
        reen_result,
        effector_timing,
        OUT_DIR / "saturation_timeline.png",
        title=f"Re-engagement Timeline — {slinger.name} (60 s window)",
    )
    print(f"  → saturation_timeline.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== Project Salus — Slices 7, 8 & 9 Demo ===\n")

    # Build and write terrain.
    print("Building synthetic 1.5 km × 1.5 km terrain…")
    dem = _make_terrain()
    _write_dem(dem)
    site = load_dem(DEM_PATH)
    print(f"  {site.rows}×{site.cols} cells at {site.resolution:.0f} m/cell")
    print(f"  Elevation range: {site.dem.min():.0f}–{site.dem.max():.0f} m")

    # Load definitions.
    sensor_defs = {s.name: s for s in load_sensors(SENSOR_DIR)}
    effector_defs = {e.name: e for e in load_effectors(EFFECTOR_DIR)}
    print(f"  Loaded {len(sensor_defs)} sensor defs, {len(effector_defs)} effector defs")

    # Run each slice demo.
    _opt_positions, optimised_placements, _ = _run_s9(site, sensor_defs)
    _run_s7(site, optimised_placements, sensor_defs, effector_defs)
    _run_s8(site, effector_defs)

    print(f"\nAll outputs saved to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
