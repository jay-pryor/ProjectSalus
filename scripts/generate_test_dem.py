"""Generate tests/fixtures/synthetic_site.tif — the canonical development DEM for Salus.

Run from the project root:
    python scripts/generate_test_dem.py

Regenerating produces an identical file (fully deterministic).
See tests/fixtures/README.md for terrain description.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

ROWS = 500
COLS = 500
RESOLUTION = 1.0        # metres per cell
ORIGIN_X = 500000.0     # Easting, GDA94 / MGA Zone 54
ORIGIN_Y = 6100500.0    # Northing, top-left corner
BASE_ELEV = 50.0        # Background elevation (m)
OUT_PATH = Path("tests/fixtures/synthetic_site.tif")


def generate() -> None:
    dem = np.full((ROWS, COLS), BASE_ELEV, dtype=np.float32)

    # Hill (NE quadrant): Gaussian peak at row 75, col 400, 120 m summit
    hill_row, hill_col = 75, 400
    rr, cc = np.mgrid[0:ROWS, 0:COLS]
    hill = 70.0 * np.exp(-(((rr - hill_row) ** 2 + (cc - hill_col) ** 2) / (2 * 40.0**2)))
    dem += hill.astype(np.float32)

    # E–W ridge: rows 200–249, triangular cross-section, peak 130 m at row 225
    for r in range(200, 250):
        ridge_height = max(0.0, 80.0 - abs(r - 225) * 3.2)
        dem[r, :] = np.maximum(dem[r, :], BASE_ELEV + ridge_height)

    # Valley: rows 250–349, cols 150–349, sinusoidal depression to 30 m
    for r in range(250, 350):
        depth = 20.0 * np.sin((r - 250) / 99.0 * np.pi)
        dem[r, 150:350] = np.minimum(dem[r, 150:350], BASE_ELEV - depth)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    transform = from_origin(ORIGIN_X, ORIGIN_Y, RESOLUTION, RESOLUTION)
    with rasterio.open(
        OUT_PATH,
        "w",
        driver="GTiff",
        height=ROWS,
        width=COLS,
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(28354),
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(dem, 1)

    size_kb = OUT_PATH.stat().st_size // 1024
    print(f"Written: {OUT_PATH}  ({ROWS}x{COLS} cells, {size_kb} KB)")
    print(f"Elevation range: {dem.min():.1f}–{dem.max():.1f} m")
    print(f"Observer suggestion: --x 500250 --y 6100050 --height 2")


if __name__ == "__main__":
    generate()
