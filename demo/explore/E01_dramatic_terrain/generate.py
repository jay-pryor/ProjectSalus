"""
E01 Dramatic Terrain — High-Relief Site for 3D Viewer Testing.

Generates a 2 km × 2 km synthetic DEM with dramatic terrain features and a
walled compound in the central valley, then packages the Salus interactive
viewer so the terrain can be inspected in 3D.

Terrain design
--------------
  Base valley:        ~150 m ASL  (compound area, flat floor)
  Northern ridge:     520 m peak  (370 m rise, steep south face)
  Eastern escarpment: 480 m peak  (cliff face dropping to valley)
  SW hill:            460 m peak
  SE hill:            440 m peak
  Western corridor:   155 m       (natural low approach from west)

Compound (120 m × 120 m, centred on site)
-----------------------------------------
  Perimeter wall:     4 m above ground, 2 cells thick (10 m) for DEM resolution
  Guard tower (NE):   30 m above ground — clearly visible from viewer overview
  Main building (N):  15 m above ground
  Barracks (SW):       8 m above ground
  Vehicle bay (SE):    6 m above ground
  Interior:            base elevation (open courtyard)

The walls and buildings are encoded directly in the DEM so they affect both
the 3D viewer and viewshed / LOS calculations.

Usage
-----
Run from the repository root::

    python demo/explore/E01_dramatic_terrain/generate.py

Outputs
-------
  demo/explore/E01_dramatic_terrain/dramatic_terrain.tif   — DEM GeoTIFF
  demo/explore/E01_dramatic_terrain/viewer/                — packaged viewer
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

# ---------------------------------------------------------------------------
# Grid / coordinate constants
# ---------------------------------------------------------------------------

ROWS: int = 400
COLS: int = 400
RES: float = 5.0  # metres per pixel

# EPSG:28354  GDA94 / MGA Zone 54 (eastern Australia)
ORIGIN_E: float = 500000.0  # left
ORIGIN_N: float = 6102000.0  # top  (rasterio uses top-left convention)

# Compound centre in projected coords
COMPOUND_E: float = 501000.0
COMPOUND_N: float = 6101000.0

# Derived grid indices for compound centre
COMPOUND_R: int = int((ORIGIN_N - COMPOUND_N) / RES)  # row index (top-down)
COMPOUND_C: int = int((COMPOUND_E - ORIGIN_E) / RES)  # col index

BASE_ELEV: float = 150.0  # valley floor elevation (m ASL)

OUT_DIR = Path(__file__).parent
DEM_PATH = OUT_DIR / "dramatic_terrain.tif"
VIEWER_PATH = OUT_DIR / "viewer"


# ---------------------------------------------------------------------------
# Terrain helpers
# ---------------------------------------------------------------------------


def _gaussian(
    rr: np.ndarray,
    cc: np.ndarray,
    row: float,
    col: float,
    height: float,
    sigma_r: float,
    sigma_c: float,
) -> np.ndarray:
    """Return an additive Gaussian hill/depression centred at (row, col)."""
    return height * np.exp(-(((rr - row) / sigma_r) ** 2 + ((cc - col) / sigma_c) ** 2))


def _ridge(
    rr: np.ndarray,
    cc: np.ndarray,
    row: float,
    col_start: float,
    col_end: float,
    height: float,
    sigma_r: float,
) -> np.ndarray:
    """Elongated ridge running horizontally across columns col_start→col_end."""
    ridge_col = np.clip(cc, col_start, col_end)
    return height * np.exp(-(((rr - row) / sigma_r) ** 2 + ((cc - ridge_col) / 30.0) ** 2))


# ---------------------------------------------------------------------------
# DEM builder
# ---------------------------------------------------------------------------


def build_terrain() -> np.ndarray:
    """Build a 400 × 400 DEM with dramatic terrain and a walled compound."""
    rr, cc = np.meshgrid(np.arange(ROWS), np.arange(COLS), indexing="ij")

    dem = np.full((ROWS, COLS), BASE_ELEV, dtype=np.float64)

    # ── Terrain features ────────────────────────────────────────────────────

    # Northern ridge — steep spine running full width, peaks near row 50
    dem += _ridge(rr, cc, 40, 0, 399, 370.0, 30.0)
    # Add a couple of peaks on the ridge for character
    dem += _gaussian(rr, cc, 35, 100, 60.0, 20.0, 25.0)
    dem += _gaussian(rr, cc, 30, 280, 80.0, 18.0, 22.0)

    # Eastern escarpment — steep cliff running N-S near col 350
    dem += _gaussian(rr, cc, 120, 360, 330.0, 60.0, 35.0)
    dem += _gaussian(rr, cc, 260, 355, 280.0, 55.0, 30.0)

    # SW hill
    dem += _gaussian(rr, cc, 330, 60, 310.0, 55.0, 50.0)

    # SE hill
    dem += _gaussian(rr, cc, 330, 330, 290.0, 50.0, 45.0)

    # Small ridge between SE hill and east escarpment
    dem += _gaussian(rr, cc, 300, 350, 180.0, 40.0, 25.0)

    # Western approach corridor — valley / saddle in the hills
    # Subtract a depression to carve a pass through the west hills
    dem -= _gaussian(rr, cc, 200, 0, 30.0, 40.0, 25.0)
    dem -= _gaussian(rr, cc, 200, 20, 25.0, 35.0, 20.0)

    # Central valley floor — flatten the area around the compound
    # Use a suppression term so the valley floor stays near BASE_ELEV
    valley_suppress = 0.7 * np.exp(
        -(((rr - COMPOUND_R) / 60.0) ** 2 + ((cc - COMPOUND_C) / 60.0) ** 2)
    )
    # Scale down the hill contributions in the valley
    hill_contrib = dem - BASE_ELEV
    dem = BASE_ELEV + hill_contrib * (1.0 - valley_suppress)

    # Gentle undulation in the valley floor for realism
    dem += 3.0 * np.sin(rr / 12.0) * np.cos(cc / 15.0)

    # Clip minimum to BASE_ELEV − 20 (no sea level artefacts)
    dem = np.maximum(dem, BASE_ELEV - 20.0)

    # ── Compound features ────────────────────────────────────────────────────
    # The compound is a 120 m × 120 m (24 × 24 cell) rectangle centred on
    # COMPOUND_R / COMPOUND_C.  Features are added after terrain so they always
    # sit at a consistent height above the local ground level.

    # Compute the elevation at the compound centre (post-terrain, pre-compound)
    ground_elev = float(dem[COMPOUND_R, COMPOUND_C])

    half = 12  # cells → 60 m from centre to wall outside edge
    r0, r1 = COMPOUND_R - half, COMPOUND_R + half
    c0, c1 = COMPOUND_C - half, COMPOUND_C + half

    # Flatten compound interior to a level courtyard
    dem[r0 + 2 : r1 - 1, c0 + 2 : c1 - 1] = ground_elev

    # Perimeter wall — 4 m above ground, 2 cells thick for DEM visibility
    wall_elev = ground_elev + 4.0
    # North wall
    dem[r0 : r0 + 2, c0 : c1 + 1] = wall_elev
    # South wall — leave a 20 m gate gap (4 cells) in the centre
    gate_c0 = COMPOUND_C - 2
    gate_c1 = COMPOUND_C + 2
    dem[r1 - 1 : r1 + 1, c0:gate_c0] = wall_elev
    dem[r1 - 1 : r1 + 1, gate_c1 : c1 + 1] = wall_elev
    # East wall
    dem[r0 : r1 + 1, c1 - 1 : c1 + 1] = wall_elev
    # West wall
    dem[r0 : r1 + 1, c0 : c0 + 2] = wall_elev

    # Guard tower — NE corner, 10 m × 10 m (2 × 2 cells), 30 m above ground
    dem[r0 + 1 : r0 + 3, c1 - 3 : c1 - 1] = ground_elev + 30.0

    # Main building — N side, 50 m × 25 m (10 × 5 cells), 15 m above ground
    dem[r0 + 2 : r0 + 7, c0 + 3 : c0 + 13] = ground_elev + 15.0

    # Barracks — SW quadrant, 40 m × 20 m (8 × 4 cells), 8 m above ground
    dem[r1 - 8 : r1 - 4, c0 + 3 : c0 + 11] = ground_elev + 8.0

    # Vehicle bay — SE quadrant, 50 m × 20 m (10 × 4 cells), 6 m above ground
    dem[r1 - 7 : r1 - 3, c1 - 12 : c1 - 2] = ground_elev + 6.0

    return dem


# ---------------------------------------------------------------------------
# Write GeoTIFF
# ---------------------------------------------------------------------------


def write_dem(dem: np.ndarray) -> None:
    """Write the DEM array to a GeoTIFF at DEM_PATH."""
    transform = from_bounds(
        ORIGIN_E,
        ORIGIN_N - ROWS * RES,
        ORIGIN_E + COLS * RES,
        ORIGIN_N,
        COLS,
        ROWS,
    )
    crs = CRS.from_epsg(28354)

    DEM_PATH.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        DEM_PATH,
        mode="w",
        driver="GTiff",
        height=ROWS,
        width=COLS,
        count=1,
        dtype=np.float32,
        crs=crs,
        transform=transform,
    ) as ds:
        ds.write(dem.astype(np.float32), 1)

    finite = dem[np.isfinite(dem)]
    print(f"DEM written → {DEM_PATH}")
    km = ROWS * RES / 1000
    print(f"  Shape: {ROWS} × {COLS} at {RES} m/px = {km:.1f} km × {km:.1f} km")
    spread = finite.max() - finite.min()
    print(f"  Elevation: {finite.min():.0f} m – {finite.max():.0f} m  (spread {spread:.0f} m)")
    print(f"  Compound centre grid: row {COMPOUND_R}, col {COMPOUND_C}")
    print(f"  Ground elevation at compound: {float(dem[COMPOUND_R, COMPOUND_C]):.1f} m")


# ---------------------------------------------------------------------------
# Package viewer
# ---------------------------------------------------------------------------


def package_viewer() -> None:
    """Run the salus viewer CLI to package the 3D viewer."""
    import subprocess

    scenario_path = OUT_DIR / "scenario.yaml"
    if not scenario_path.exists():
        print("  scenario.yaml not found — skipping viewer packaging.")
        return

    try:
        result = subprocess.run(
            [
                "salus",
                "viewer",
                str(scenario_path),
                "--output",
                str(VIEWER_PATH),
                "--sanitise",
                "none",
            ],
            capture_output=False,
            cwd=str(Path(__file__).parent.parent.parent.parent),
        )
    except FileNotFoundError:
        print("  salus CLI not found on PATH — skipping viewer packaging.")
        return
    if result.returncode == 0:
        print(f"\nViewer packaged → {VIEWER_PATH}/")
        print("  Serve with:  python -m http.server 8080  (from viewer dir)")
    else:
        print(f"  Viewer packaging failed (exit {result.returncode}) — check salus CLI.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Building terrain…")
    dem = build_terrain()
    write_dem(dem)
    print("\nPackaging 3D viewer…")
    package_viewer()
