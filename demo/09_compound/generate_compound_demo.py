"""
Compound Defence Demo — Realistic Terrain with Walls, Buildings and Hills.

Generates a 1.5 km × 1.5 km site containing:

  Terrain
  -------
  - Base plateau at 180 m ASL
  - Five surrounding hills channelling threat approach vectors
  - A natural valley from the north that funnels threats toward the gate

  Compound (150 m × 150 m, centred in the site)
  -----------------------------------------------
  - 3.5 m perimeter wall with a 25 m south-facing gate gap
  - Main HQ building        (55 m × 30 m, 12 m high)
  - Barracks                (40 m × 20 m,  8 m high)
  - Vehicle bay             (55 m × 20 m,  6 m high)
  - Communications tower    (10 m × 10 m, 22 m high)

  Zones
  -----
  - compound_interior   — critical_asset  (inside the walls)
  - inner_approach      — inner           (0–300 m from compound centre)
  - outer_approach      — perimeter       (300–700 m from compound centre)

  Demo
  ----
  1. Greedy sensor placement (3 sensors) — optimiser must balance hilltops
     for range against proximity to the compound for close-in detection.
  2. Greedy effector placement (3 effectors) — engages threats in the
     approach corridors the hills create.
  3. S10 comparison: manual (wall-corner) vs optimised sensor deployment.
  4. S11 effector coverage + detection-without-engagement gap map.

Run from the repository root:
    python demo/09_compound/generate_compound_demo.py

All outputs are saved to demo/09_compound/.
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
from shapely.geometry import Point, Polygon

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from salus.engine.comparison import ConfigurationResult, compare_configs
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
from salus.models.zone import Zone, ZoneType
from salus.report.charts import (
    render_comparison_statistics_table,
    render_coverage_comparison_chart,
)
from salus.report.maps import (
    render_composite_coverage_map,
    render_delta_map,
    render_detection_without_engagement_map,
    render_effector_coverage_map,
    render_side_by_side_coverage_maps,
)

# ---------------------------------------------------------------------------
# Site constants
# ---------------------------------------------------------------------------
ROWS, COLS = 300, 300
RESOLUTION = 5.0        # 5 m/cell → 1 500 m × 1 500 m
ORIGIN_X = 500_000.0
ORIGIN_Y = 6_100_000.0
EPSG = 28354            # MGA Zone 54

MAX_X = ORIGIN_X + COLS * RESOLUTION   # 501 500
MAX_Y = ORIGIN_Y + ROWS * RESOLUTION   # 6 101 500

# Compound is placed slightly north of centre so the south gate opens into
# the approach valley.
COMPOUND_CENTRE_R = 140     # grid row (0 = top/north)
COMPOUND_CENTRE_C = 150     # grid col (0 = left/west)
COMPOUND_HALF = 15          # half-width in cells  → 30 cells = 150 m wall-to-wall

BASE_ELEV = 180.0           # plateau base elevation (m ASL)
WALL_HEIGHT = 3.5           # perimeter wall above plateau
GATE_HALF_W = 2             # half-width of south gate in cells

OUT_DIR = Path(__file__).parent
DEM_PATH = OUT_DIR / "compound_terrain.tif"

REPO_ROOT = Path(__file__).parent.parent.parent
SENSOR_DIR = REPO_ROOT / "src" / "salus" / "data" / "sensors"
EFFECTOR_DIR = REPO_ROOT / "src" / "salus" / "data" / "effectors"


# ---------------------------------------------------------------------------
# Helpers — grid ↔ CRS conversion
# ---------------------------------------------------------------------------

def _rc_to_xy(row: int, col: int) -> tuple[float, float]:
    """Centre of (row, col) cell in CRS metres (easting, northing)."""
    x = ORIGIN_X + (col + 0.5) * RESOLUTION
    # rasterio origin is top-left; northing increases upward.
    y = MAX_Y - (row + 0.5) * RESOLUTION
    return x, y


def _xy_to_polygon(min_r: int, max_r: int, min_c: int, max_c: int) -> Polygon:
    """Shapely Polygon for a cell rectangle (inclusive row/col bounds)."""
    x0 = ORIGIN_X + min_c * RESOLUTION
    x1 = ORIGIN_X + (max_c + 1) * RESOLUTION
    y0 = MAX_Y - (max_r + 1) * RESOLUTION   # south edge (lower northing)
    y1 = MAX_Y - min_r * RESOLUTION          # north edge (upper northing)
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


# ---------------------------------------------------------------------------
# Terrain generation
# ---------------------------------------------------------------------------

def _gaussian_hill(
    rows: np.ndarray,
    cols: np.ndarray,
    centre_r: float,
    centre_c: float,
    height: float,
    sigma_r: float,
    sigma_c: float,
) -> np.ndarray:
    """Vectorised Gaussian hill (returns additive elevation array)."""
    return height * np.exp(
        -0.5 * (((rows - centre_r) / sigma_r) ** 2 + ((cols - centre_c) / sigma_c) ** 2)
    )


def build_terrain() -> np.ndarray:
    """Build a 300 × 300 DEM with hills, a compound, walls and buildings.

    The compound is modelled by setting DEM cells to the appropriate height
    so the viewshed engine treats walls and buildings as opaque obstacles.
    """
    rr, cc = np.meshgrid(np.arange(ROWS), np.arange(COLS), indexing="ij")
    dem = np.full((ROWS, COLS), BASE_ELEV, dtype=np.float64)

    # ------------------------------------------------------------------
    # Surrounding hills — five distinct features that channel approach
    # vectors toward the north valley and south gate.
    # ------------------------------------------------------------------

    # Hill A — large NW massif  (good OP, masks western approach beyond it)
    dem += _gaussian_hill(rr, cc, 55, 55, 95.0, 55.0, 55.0)

    # Hill B — NE ridge  (elongated E-W, creates north approach corridor)
    dem += _gaussian_hill(rr, cc, 40, 220, 75.0, 35.0, 65.0)

    # Hill C — eastern spur  (overlooks east flank)
    dem += _gaussian_hill(rr, cc, 155, 265, 55.0, 40.0, 35.0)

    # Hill D — southern plateau edge  (rises behind compound to south)
    dem += _gaussian_hill(rr, cc, 265, 145, 70.0, 50.0, 75.0)

    # Hill E — small western knoll  (closer in, partial west coverage)
    dem += _gaussian_hill(rr, cc, 175, 38, 40.0, 28.0, 28.0)

    # ------------------------------------------------------------------
    # North valley — slight depression between Hill A and Hill B.
    # This is the primary threat approach axis from the north.
    # ------------------------------------------------------------------
    dem -= _gaussian_hill(rr, cc, 75, 138, 18.0, 25.0, 45.0)

    # ------------------------------------------------------------------
    # Compound perimeter walls
    # Rows/cols define the outer wall ring.  Gate is a gap in the south
    # wall.  Wall cells are set to BASE_ELEV + WALL_HEIGHT.
    # ------------------------------------------------------------------
    r0 = COMPOUND_CENTRE_R - COMPOUND_HALF
    r1 = COMPOUND_CENTRE_R + COMPOUND_HALF
    c0 = COMPOUND_CENTRE_C - COMPOUND_HALF
    c1 = COMPOUND_CENTRE_C + COMPOUND_HALF
    gate_c0 = COMPOUND_CENTRE_C - GATE_HALF_W
    gate_c1 = COMPOUND_CENTRE_C + GATE_HALF_W

    wall_elev = BASE_ELEV + WALL_HEIGHT

    # North wall
    dem[r0, c0:c1 + 1] = wall_elev
    # South wall — gap for the gate
    dem[r1, c0:gate_c0] = wall_elev
    dem[r1, gate_c1 + 1:c1 + 1] = wall_elev
    # West wall
    dem[r0:r1 + 1, c0] = wall_elev
    # East wall
    dem[r0:r1 + 1, c1] = wall_elev

    # ------------------------------------------------------------------
    # Internal buildings
    # Set interior cells to BASE_ELEV + building height.
    # Interior is rows r0+1 .. r1-1, cols c0+1 .. c1-1.
    # ------------------------------------------------------------------

    # Main HQ building — north-centre of compound, 12 m high
    dem[r0 + 2: r0 + 8, c0 + 4: c0 + 15] = BASE_ELEV + 12.0

    # Barracks — north-east quadrant, 8 m high
    dem[r0 + 2: r0 + 7, c1 - 12: c1 - 2] = BASE_ELEV + 8.0

    # Vehicle bay — south-west quadrant, 6 m high
    dem[r1 - 8: r1 - 2, c0 + 2: c0 + 13] = BASE_ELEV + 6.0

    # Communications tower — centre, very small footprint, 22 m high
    dem[COMPOUND_CENTRE_R - 1: COMPOUND_CENTRE_R + 2,
        COMPOUND_CENTRE_C - 1: COMPOUND_CENTRE_C + 2] = BASE_ELEV + 22.0

    return dem


# ---------------------------------------------------------------------------
# Site zone definitions
# ---------------------------------------------------------------------------

def build_zones() -> list[Zone]:
    """Create operational zones around the compound."""
    cx, cy = _rc_to_xy(COMPOUND_CENTRE_R, COMPOUND_CENTRE_C)
    compound_poly = _xy_to_polygon(
        COMPOUND_CENTRE_R - COMPOUND_HALF,
        COMPOUND_CENTRE_R + COMPOUND_HALF,
        COMPOUND_CENTRE_C - COMPOUND_HALF,
        COMPOUND_CENTRE_C + COMPOUND_HALF,
    )
    centre = Point(cx, cy)
    inner_poly = centre.buffer(300.0).difference(compound_poly)
    outer_poly = centre.buffer(700.0).difference(centre.buffer(300.0))

    return [
        Zone(name="Compound Interior", zone_type=ZoneType.critical_asset, geometry=compound_poly),
        Zone(name="Inner Approach",    zone_type=ZoneType.inner,           geometry=inner_poly),
        Zone(name="Outer Approach",    zone_type=ZoneType.perimeter,       geometry=outer_poly),
    ]


# ---------------------------------------------------------------------------
# Coverage pipeline helper
# ---------------------------------------------------------------------------

def _run_pipeline(
    site,
    sensor_defs: dict,
    placements: list[SensorPlacement],
    zones: list[Zone],
    label: str,
    cost: float,
) -> tuple[ConfigurationResult, list[tuple[float, float]]]:
    by_type: dict = {}
    positions: list[tuple[float, float]] = []
    for sp in placements:
        sd = sensor_defs[sp.sensor_name]
        by_type.setdefault(sd.type, []).append((sd, sp))
        positions.append((sp.position_x, sp.position_y))

    layer_coverages = compute_layer_coverage(site, by_type)
    composite = compute_composite_coverage(layer_coverages)
    gaps = compute_gaps(composite, composite)
    stats = compute_coverage_stats(site, layer_coverages, composite, gaps, zones)

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
# Main demo
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Project Salus — Compound Defence Demo ===\n")

    # Build and write DEM
    print("Building compound terrain…")
    dem = build_terrain()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(ORIGIN_X, ORIGIN_Y, MAX_X, MAX_Y, COLS, ROWS)
    with rasterio.open(
        DEM_PATH, "w",
        driver="GTiff", height=ROWS, width=COLS,
        count=1, dtype="float64",
        crs=CRS.from_epsg(EPSG),
        transform=transform,
    ) as dst:
        dst.write(dem, 1)
    site = load_dem(DEM_PATH)
    print(f"  {site.rows}×{site.cols} cells  |  {site.resolution:.0f} m/cell  "
          f"|  elev range {site.dem.min():.0f}–{site.dem.max():.0f} m ASL")

    # Load definitions
    sensor_defs = {s.name: s for s in load_sensors(SENSOR_DIR)}
    effector_defs = {e.name: e for e in load_effectors(EFFECTOR_DIR)}
    print(f"  {len(sensor_defs)} sensor defs  |  {len(effector_defs)} effector defs")

    # Build zones
    zones = build_zones()
    print(f"  {len(zones)} zones: "
          + ", ".join(f"{z.name} ({z.zone_type})" for z in zones))

    # Compound corners in CRS for wall-corner reference deployment
    r0 = COMPOUND_CENTRE_R - COMPOUND_HALF
    r1 = COMPOUND_CENTRE_R + COMPOUND_HALF
    c0 = COMPOUND_CENTRE_C - COMPOUND_HALF
    c1 = COMPOUND_CENTRE_C + COMPOUND_HALF

    # ------------------------------------------------------------------
    # Sensor selection: a long-range RF sweep sensor for outer detection,
    # a medium-range radar for perimeter approach, and an acoustic sensor
    # for close-in confirmation.  Covers all three modalities.
    # ------------------------------------------------------------------
    sensors_to_place = [
        sensor_defs["DroneShield RfOne Mk2"],    # RF  — 8 km range (approach corridor sweeper)
        sensor_defs["HENSOLDT Spexer 500"],       # Radar — 3 km range (approach tracking)
        sensor_defs["Echodyne EchoGuard"],        # Radar — 900 m range (perimeter guard)
    ]
    sensor_names = [s.name for s in sensors_to_place]

    # Effectors: mix kinetic (short-range close-in) + EW (long-range, no-LOS)
    effector_selection = [
        effector_defs["EOS Slinger"],               # kinetic, LOS, 800 m
        effector_defs["DroneShield DroneCannon Mk2"],  # EW, 2 km
        effector_defs["Raytheon HELWS"],            # DEW, 3 km
    ]
    effector_names = [e.name for e in effector_selection]

    # ------------------------------------------------------------------
    # Config A — Manual wall-corner deployment
    # Sensors placed at three of the four compound wall corners.
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Config A — Manual corner deployment")
    print("=" * 60)
    corner_xy = [
        _rc_to_xy(r0, c0),   # NW corner
        _rc_to_xy(r0, c1),   # NE corner
        _rc_to_xy(r1, c0),   # SW corner
    ]
    placements_a = [
        SensorPlacement(
            sensor_name=name,
            position_x=xy[0],
            position_y=xy[1],
            height_override_m=6.0,   # mast-mounted on wall
            bearing_deg=0.0,
        )
        for name, xy in zip(sensor_names, corner_xy)
    ]
    for sp in placements_a:
        print(f"  {sp.sensor_name:35s}  ({sp.position_x:.0f}, {sp.position_y:.0f})")

    cfg_a, pos_a = _run_pipeline(
        site, sensor_defs, placements_a, zones,
        label="Config A — Wall Corners", cost=380_000.0,
    )
    print(f"  → Coverage: {cfg_a.stats.total_coverage_pct:.1f}%")

    # ------------------------------------------------------------------
    # Config B — Greedy-optimised deployment
    # Candidates include hilltops, which should score strongly.
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Config B — Greedy-optimised deployment")
    print("=" * 60)
    # step_m=200 → ~8×8=64 candidates, keeping run-time to ~5 min.
    print("  Generating candidate positions (step = 200 m)…")
    candidates = generate_candidate_positions(
        site, boundary=None, step_m=200.0, exclusion_zones=[]
    )
    print(f"  {len(candidates)} candidates generated")

    weights = PlacementWeights(
        critical_asset=5.0,    # compound must be covered
        inner=2.5,             # approach corridors matter
        perimeter=1.0,
        unzoned=0.5,
    )
    placements_b = greedy_place_sensors(
        site, sensors_to_place, candidates, weights=weights
    )
    print("\n  Optimised placements:")
    for sp in placements_b:
        r_approx = int((MAX_Y - sp.position_y) / RESOLUTION)
        c_approx = int((sp.position_x - ORIGIN_X) / RESOLUTION)
        elev = float(dem[min(r_approx, ROWS-1), min(c_approx, COLS-1)])
        print(f"  {sp.sensor_name:35s}  ({sp.position_x:.0f}, {sp.position_y:.0f})  "
              f"elev={elev:.0f} m")

    cfg_b, pos_b = _run_pipeline(
        site, sensor_defs, placements_b, zones,
        label="Config B — Optimised", cost=440_000.0,
    )
    print(f"  → Coverage: {cfg_b.stats.total_coverage_pct:.1f}%")

    # ------------------------------------------------------------------
    # S10 — Comparison
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("S10 — Configuration Comparison")
    print("=" * 60)
    comparison = compare_configs(cfg_a, cfg_b)
    delta = comparison.coverage_delta_pct
    cost_d = comparison.cost_delta or 0.0
    print(f"  Coverage delta:   {delta:+.1f}%")
    print(f"  Cost delta:       ${cost_d:+,.0f}")

    n = comparison.delta_grid.size
    n_both   = int((comparison.delta_grid == 1).sum())
    n_a_only = int((comparison.delta_grid == 2).sum())
    n_b_only = int((comparison.delta_grid == 3).sum())
    print(f"  Both covered:     {n_both:>6}  ({n_both/n*100:.1f}%)")
    print(f"  A-only:           {n_a_only:>6}  ({n_a_only/n*100:.1f}%)")
    print(f"  B-only gains:     {n_b_only:>6}  ({n_b_only/n*100:.1f}%)")

    # Zone deltas
    if comparison.per_zone_delta_pct:
        print("  Per-zone coverage delta:")
        for zone_name, d in comparison.per_zone_delta_pct.items():
            za = comparison.per_zone_coverage_pct_a.get(zone_name, 0.0)
            zb = comparison.per_zone_coverage_pct_b.get(zone_name, 0.0)
            print(f"    {zone_name:25s}  A={za:.1f}%  B={zb:.1f}%  Δ={d:+.1f}%")

    print("\n  Rendering comparison outputs…")
    render_delta_map(
        site, comparison, OUT_DIR / "s10_delta.png",
        title="Coverage Delta — Wall Corners vs Optimised",
        sensor_positions_a=pos_a,
        sensor_positions_b=pos_b,
    )
    print("    → s10_delta.png")

    render_side_by_side_coverage_maps(
        site, comparison, OUT_DIR / "s10_side_by_side.png",
        title="Coverage — Wall Corners (left) vs Optimised (right)",
        sensor_positions_a=pos_a,
        sensor_positions_b=pos_b,
        zones=zones,
    )
    print("    → s10_side_by_side.png")

    render_coverage_comparison_chart(
        comparison, OUT_DIR / "s10_comparison.png",
        title="Per-Zone Coverage — Wall Corners vs Optimised",
    )
    print("    → s10_comparison.png")

    render_comparison_statistics_table(
        comparison, OUT_DIR / "s10_statistics.png",
        title="Configuration Comparison — Compound Deployment",
    )
    print("    → s10_statistics.png")

    # ------------------------------------------------------------------
    # S11 — Effector coverage (using optimised sensor deployment as base)
    # Effectors placed with greedy optimiser on the same candidate grid,
    # with an exclusion zone inside the compound walls (nothing inside).
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("S11 — Effector Coverage + Detection Gap Map")
    print("=" * 60)

    # Effectors are placed at three strategic positions:
    #   1. EOS Slinger (kinetic, 800 m LOS) — on the NW hill summit,
    #      covering the north valley approach corridor.
    #   2. DroneCannon Mk2 (EW, 2 km) — on the NE ridge, sweeping the
    #      north-east and eastern approach flanks.
    #   3. HELWS (DEW laser, 3 km) — on the compound comms tower,
    #      providing long-range engagement across most of the site.
    #
    # These positions were chosen by terrain analysis: the hill summits
    # (rows ~55,55 and ~40,220) and the compound comms tower give maximum
    # LOS depth into the approach corridors identified in the hill layout.
    slinger_xy    = _rc_to_xy(55,  55)   # NW hill summit
    cannon_xy     = _rc_to_xy(40, 220)   # NE ridge summit
    helws_xy      = _rc_to_xy(COMPOUND_CENTRE_R, COMPOUND_CENTRE_C)  # comms tower

    print("  Strategic effector positions:")
    strategic_effectors = [
        (effector_defs["EOS Slinger"],
         EffectorPlacement(effector_name="EOS Slinger",
                           position_x=slinger_xy[0], position_y=slinger_xy[1],
                           bearing_deg=0.0, height_override_m=3.0),
         slinger_xy),
        (effector_defs["DroneShield DroneCannon Mk2"],
         EffectorPlacement(effector_name="DroneShield DroneCannon Mk2",
                           position_x=cannon_xy[0], position_y=cannon_xy[1],
                           bearing_deg=0.0, height_override_m=3.0),
         cannon_xy),
        (effector_defs["Raytheon HELWS"],
         EffectorPlacement(effector_name="Raytheon HELWS",
                           position_x=helws_xy[0], position_y=helws_xy[1],
                           bearing_deg=0.0, height_override_m=22.0),  # on comms tower
         helws_xy),
    ]
    eff_pairs = []
    eff_positions: list[tuple[float, float]] = []
    for ed, ep, xy in strategic_effectors:
        r_approx = int((MAX_Y - xy[1]) / RESOLUTION)
        c_approx = int((xy[0] - ORIGIN_X) / RESOLUTION)
        elev = float(dem[min(r_approx, ROWS-1), min(c_approx, COLS-1)])
        print(f"  {ed.name:40s}  ({xy[0]:.0f}, {xy[1]:.0f})  elev={elev:.0f} m")
        eff_pairs.append((ed, ep))
        eff_positions.append(xy)

    effector_coverage = compute_effector_layer_coverage(site, eff_pairs)
    sensor_composite = cfg_b.composite   # use optimised sensor deployment
    eff_pct = effector_coverage.sum() / effector_coverage.size * 100
    sensor_pct = sensor_composite.sum() / sensor_composite.size * 100
    gap_cells = sensor_composite & ~effector_coverage
    gap_pct = gap_cells.sum() / sensor_composite.size * 100
    covered_both_pct = (sensor_composite & effector_coverage).sum() / sensor_composite.size * 100

    print(f"\n  Sensor composite coverage: {sensor_pct:.1f}%")
    print(f"  Effector engagement zone:  {eff_pct:.1f}%")
    print(f"  Detect + engage:           {covered_both_pct:.1f}%")
    print(f"  Detection-without-engagement gap: {gap_pct:.1f}%  ← amber zone")

    print("\n  Rendering effector coverage outputs…")
    render_effector_coverage_map(
        site, effector_coverage, OUT_DIR / "s11_effector_coverage.png",
        title=f"Effector Engagement Zone — 3-effector compound defence",
        effector_positions=eff_positions,
        zones=zones,
    )
    print("    → s11_effector_coverage.png")

    render_detection_without_engagement_map(
        site, sensor_composite, effector_coverage,
        OUT_DIR / "s11_detection_gap.png",
        title="Detection-Without-Engagement Gap — Compound Defence",
        sensor_positions=pos_b,
        effector_positions=eff_positions,
        zones=zones,
    )
    print("    → s11_detection_gap.png")

    # ------------------------------------------------------------------
    # Bonus: render the optimised composite coverage map alone
    # so you can see what the sensor network sees without effectors.
    # ------------------------------------------------------------------
    render_composite_coverage_map(
        site, cfg_b.layer_coverages, OUT_DIR / "sensor_composite.png",
        title=f"Sensor Composite Coverage — Optimised ({sensor_pct:.1f}%)",
        sensor_positions=pos_b,
        zones=zones,
    )
    print("    → sensor_composite.png")

    print(f"\nAll outputs saved to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
