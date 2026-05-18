"""
E01 Dramatic Terrain (high-resolution variant) — 1 m DEM.

Produces the *same* 2 km x 2 km physical terrain as ``generate.py`` (the 5 m
``dramatic_terrain.tif``), but sampled at 1 m so the walled compound carries
genuinely crisp detail instead of being limited by a 5 m cell.

Why a separate generator
------------------------
A GeoTIFF raster has a single geotransform — one fixed pixel size for the
whole grid. There is no way to encode "coarse here, fine there" natively in
one DEM. The practical answer is a single *uniform fine* grid: the open
terrain is smooth and carries no high-frequency detail, so sampling it at 1 m
costs only pixel count, not fidelity; the compound zone is where the 1 m cell
actually buys you something.

To make that resolution-independent, every terrain feature here is defined in
**metres** (not cell indices, as ``generate.py`` does) and converted to cells
via ``RES``. Setting ``RES = 5.0`` would reproduce the original terrain; at
``RES = 1.0`` the hills are identical and the compound is 5x sharper:

  ============  ===================  =====================
  Feature       generate.py (5 m)    this file (1 m)
  ============  ===================  =====================
  Grid          400 x 400            2000 x 2000
  Perimeter wall 2 cells (10 m blob)  2 cells (2 m, true)
  Gate gap      4 cells              20 cells (clean 20 m)
  Guard tower   2 x 2 cells          10 x 10 cells
  Main building 10 x 5 cells         50 x 25 cells
  ============  ===================  =====================

Usage
-----
Run from the repository root::

    python demo/explore/E01_dramatic_terrain/generate_hires.py

Outputs
-------
  demo/explore/E01_dramatic_terrain/dramatic_terrain_1m.tif  — 1 m DEM GeoTIFF
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

# ---------------------------------------------------------------------------
# Grid / coordinate constants
# ---------------------------------------------------------------------------

RES: float = 1.0  # metres per pixel — the whole point of this variant
SITE_M: float = 2000.0  # site is 2 km x 2 km (matches generate.py extent)
N: int = int(round(SITE_M / RES))  # 2000 x 2000 at 1 m

# EPSG:28354  GDA94 / MGA Zone 54 (eastern Australia) — same as generate.py
ORIGIN_E: float = 500000.0  # left
ORIGIN_N: float = 6102000.0  # top (rasterio uses the top-left convention)

# Compound centre in projected coords — dead centre of the site.
COMPOUND_E: float = 501000.0
COMPOUND_N: float = 6101000.0

# Compound centre as a metre offset from the top-left origin.
COMPOUND_Y_M: float = ORIGIN_N - COMPOUND_N  # metres south of the top edge
COMPOUND_X_M: float = COMPOUND_E - ORIGIN_E  # metres east of the left edge

# Compound centre as grid indices.
COMPOUND_R: int = int(round(COMPOUND_Y_M / RES))
COMPOUND_C: int = int(round(COMPOUND_X_M / RES))

BASE_ELEV: float = 150.0  # valley floor elevation (m ASL)

# Compound geometry (all in metres — converted to cells below).
COMPOUND_SIZE_M: float = 120.0
WALL_THICKNESS_M: float = 2.0
WALL_HEIGHT_M: float = 4.0
GATE_WIDTH_M: float = 20.0

OUT_DIR = Path(__file__).parent
DEM_PATH = OUT_DIR / "dramatic_terrain_1m.tif"


# ---------------------------------------------------------------------------
# Terrain helpers — all parameters in metres
# ---------------------------------------------------------------------------


def _gaussian(
    ym: np.ndarray,
    xm: np.ndarray,
    cy: float,
    cx: float,
    height: float,
    sigma_y: float,
    sigma_x: float,
) -> np.ndarray:
    """Return an additive Gaussian hill/depression centred at (cy, cx) metres."""
    return height * np.exp(-(((ym - cy) / sigma_y) ** 2 + ((xm - cx) / sigma_x) ** 2))


def _ridge(
    ym: np.ndarray,
    xm: np.ndarray,
    cy: float,
    x_start: float,
    x_end: float,
    height: float,
    sigma_y: float,
    sigma_x_falloff: float,
) -> np.ndarray:
    """Elongated ridge running west-east between x_start and x_end metres."""
    ridge_x = np.clip(xm, x_start, x_end)
    return height * np.exp(
        -(((ym - cy) / sigma_y) ** 2 + ((xm - ridge_x) / sigma_x_falloff) ** 2)
    )


# ---------------------------------------------------------------------------
# DEM builder
# ---------------------------------------------------------------------------


def build_terrain() -> np.ndarray:
    """Build the N x N DEM: dramatic terrain plus a crisply detailed compound."""
    # Metre-coordinate meshgrid: ym = metres south of the top, xm = metres east.
    ym, xm = np.meshgrid(
        np.arange(N) * RES, np.arange(N) * RES, indexing="ij"
    )

    dem = np.full((N, N), BASE_ELEV, dtype=np.float64)

    # ── Terrain features (identical physical terrain to generate.py) ─────────

    # Northern ridge — steep spine running full width.
    dem += _ridge(ym, xm, 200.0, 0.0, SITE_M, 370.0, 150.0, 150.0)
    # Peaks on the ridge for character.
    dem += _gaussian(ym, xm, 175.0, 500.0, 60.0, 100.0, 125.0)
    dem += _gaussian(ym, xm, 150.0, 1400.0, 80.0, 90.0, 110.0)

    # Eastern escarpment — steep cliff running N-S.
    dem += _gaussian(ym, xm, 600.0, 1800.0, 330.0, 300.0, 175.0)
    dem += _gaussian(ym, xm, 1300.0, 1775.0, 280.0, 275.0, 150.0)

    # SW hill.
    dem += _gaussian(ym, xm, 1650.0, 300.0, 310.0, 275.0, 250.0)
    # SE hill.
    dem += _gaussian(ym, xm, 1650.0, 1650.0, 290.0, 250.0, 225.0)
    # Small ridge between the SE hill and the east escarpment.
    dem += _gaussian(ym, xm, 1500.0, 1750.0, 180.0, 200.0, 125.0)

    # Western approach corridor — carve a saddle through the west hills.
    dem -= _gaussian(ym, xm, 1000.0, 0.0, 30.0, 200.0, 125.0)
    dem -= _gaussian(ym, xm, 1000.0, 100.0, 25.0, 175.0, 100.0)

    # Central valley floor — suppress the hill contributions near the compound.
    valley_suppress = 0.7 * np.exp(
        -(
            ((ym - COMPOUND_Y_M) / 300.0) ** 2
            + ((xm - COMPOUND_X_M) / 300.0) ** 2
        )
    )
    hill_contrib = dem - BASE_ELEV
    dem = BASE_ELEV + hill_contrib * (1.0 - valley_suppress)

    # Gentle undulation in the valley floor (same physical wavelength as the
    # 5 m generator: sin(row/12)/cos(col/15) at 5 m/px → metre periods 60/75).
    dem += 3.0 * np.sin(ym / 60.0) * np.cos(xm / 75.0)

    # No sea-level artefacts.
    dem = np.maximum(dem, BASE_ELEV - 20.0)

    # ── Compound features — crisp at 1 m ─────────────────────────────────────
    # Added after the terrain so they sit at a consistent height above the
    # local ground level.

    ground_elev = float(dem[COMPOUND_R, COMPOUND_C])

    half = int(round(COMPOUND_SIZE_M / RES / 2.0))  # centre → wall outer edge
    wt = int(round(WALL_THICKNESS_M / RES))  # wall thickness in cells
    r0, r1 = COMPOUND_R - half, COMPOUND_R + half
    c0, c1 = COMPOUND_C - half, COMPOUND_C + half

    # Flatten the compound interior to a level courtyard.
    dem[r0 + wt : r1 - wt + 1, c0 + wt : c1 - wt + 1] = ground_elev

    # Perimeter wall — WALL_HEIGHT_M above ground, WALL_THICKNESS_M thick.
    wall_elev = ground_elev + WALL_HEIGHT_M
    dem[r0 : r0 + wt, c0 : c1 + 1] = wall_elev  # north
    dem[r1 - wt + 1 : r1 + 1, c0 : c1 + 1] = wall_elev  # south (gate cut below)
    dem[r0 : r1 + 1, c0 : c0 + wt] = wall_elev  # west
    dem[r0 : r1 + 1, c1 - wt + 1 : c1 + 1] = wall_elev  # east

    # Gate gap — clear a GATE_WIDTH_M opening in the centre of the south wall.
    gate_half = int(round(GATE_WIDTH_M / RES / 2.0))
    gate_c0, gate_c1 = COMPOUND_C - gate_half, COMPOUND_C + gate_half
    dem[r1 - wt + 1 : r1 + 1, gate_c0 : gate_c1 + 1] = ground_elev

    # Helper: place a rectangular structure given metre footprint + height.
    def _structure(
        top_m: float, left_m: float, length_m: float, width_m: float, height_m: float
    ) -> None:
        rr0 = COMPOUND_R - half + int(round(top_m / RES))
        cc0 = COMPOUND_C - half + int(round(left_m / RES))
        rr1 = rr0 + int(round(width_m / RES))
        cc1 = cc0 + int(round(length_m / RES))
        dem[rr0:rr1, cc0:cc1] = ground_elev + height_m

    # Guard tower — NE corner, 10 m x 10 m, 30 m tall.
    _structure(top_m=4.0, left_m=COMPOUND_SIZE_M - 14.0, length_m=10.0, width_m=10.0, height_m=30.0)
    # Main building — N side, 50 m x 25 m, 15 m tall.
    _structure(top_m=6.0, left_m=12.0, length_m=50.0, width_m=25.0, height_m=15.0)
    # Barracks — SW quadrant, 40 m x 20 m, 8 m tall.
    _structure(top_m=COMPOUND_SIZE_M - 36.0, left_m=12.0, length_m=40.0, width_m=20.0, height_m=8.0)
    # Vehicle bay — SE quadrant, 50 m x 20 m, 6 m tall.
    _structure(
        top_m=COMPOUND_SIZE_M - 34.0,
        left_m=COMPOUND_SIZE_M - 62.0,
        length_m=50.0,
        width_m=20.0,
        height_m=6.0,
    )

    return dem


# ---------------------------------------------------------------------------
# Write GeoTIFF
# ---------------------------------------------------------------------------


def write_dem(dem: np.ndarray) -> None:
    """Write the DEM array to a compressed GeoTIFF at DEM_PATH."""
    transform = from_bounds(
        ORIGIN_E,
        ORIGIN_N - N * RES,
        ORIGIN_E + N * RES,
        ORIGIN_N,
        N,
        N,
    )
    crs = CRS.from_epsg(28354)

    DEM_PATH.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        DEM_PATH,
        mode="w",
        driver="GTiff",
        height=N,
        width=N,
        count=1,
        dtype=np.float32,
        crs=crs,
        transform=transform,
        # A 2000x2000 float32 grid is ~16 MB raw; the open terrain is smooth,
        # so deflate + the floating-point predictor compress it heavily.
        compress="deflate",
        predictor=3,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as ds:
        ds.write(dem.astype(np.float32), 1)

    finite = dem[np.isfinite(dem)]
    size_mb = DEM_PATH.stat().st_size / (1024 * 1024)
    km = N * RES / 1000
    print(f"DEM written → {DEM_PATH}")
    print(f"  Shape: {N} × {N} at {RES} m/px = {km:.1f} km × {km:.1f} km")
    print(f"  Elevation: {finite.min():.0f} m – {finite.max():.0f} m "
          f"(spread {finite.max() - finite.min():.0f} m)")
    print(f"  Compound centre grid: row {COMPOUND_R}, col {COMPOUND_C}")
    print(f"  Ground elevation at compound: {float(dem[COMPOUND_R, COMPOUND_C]):.1f} m")
    print(f"  File size: {size_mb:.2f} MB (deflate-compressed)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Building 1 m terrain…")
    write_dem(build_terrain())
